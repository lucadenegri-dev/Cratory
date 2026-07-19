"""Identificazione delle tracce di un mix DJ (port dell'approccio di mix-id).

Pipeline DETERMINISTICA:
1. download dell'audio dall'URL (yt-dlp);
2. campionamento a segmenti sovrapposti (ffmpeg) lungo la durata;
3. riconoscimento di ogni segmento con retry sui buchi e compensazione del pitch
   del DJ (AudioRecognizer, iniettato);
4. fusione temporale delle serie concordi, conferma a due lati dei match singoli e
   scarto degli smentiti (gestisce transizioni e falsi positivi del DJ mixing).

Il cuore (`plan_offsets`, `group_samples`/`merge_same_key_runs`/`build_tracks`,
`identify_from_recognizer`) e' puro e
testabile senza rete ne' audio: l'I/O (yt-dlp/ffmpeg) sta in funzioni separate e il
recognizer e' iniettato. Le tracce identificate NON entrano in libreria.
"""

import logging
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable

from app.integrations.shazam import AudioRecognizer, RecognizerError

logger = logging.getLogger(__name__)

SEGMENT_LENGTH = 12      # secondi di audio per ogni tentativo di riconoscimento
MAX_SEGMENTS = 200       # tetto ai segmenti (= chiamate al recognizer) per mix: su 2h il
                         # passo e' ~39s, cosi' quasi ogni traccia raccoglie 2+ campioni
                         # e il voto di conferma separa le vere dai falsi positivi
MAX_CONSECUTIVE_ERRORS = 3  # errori di fila oltre cui interrompe: basso perche' ogni
                            # errore ha gia' assorbito il backoff del recognizer (~220s di
                            # attesa vera, senza richieste), quindi 3 = ~11 min di endpoint giu'
MERGE_WINDOW_SECONDS = 240  # stessa chiave che ricompare entro questa distanza = stessa esecuzione
CONFIDENCE_CONFIRMED = 90  # 2+ campioni concordi
CONFIDENCE_DUBIOUS = 45    # campione singolo mai verificato (i verificati e smentiti si scartano)
MAX_EXTRA_CALLS = 50     # budget per retry sui buchi, tentativi pitch e conferme (per mix)
PITCH_RATES = (0.96, 1.04, 0.92, 1.08)  # moltiplicatori di compensazione del pitch del DJ:
                                        # oltre ~2% di pitch l'impronta Shazam non matcha piu';
                                        # +-4% poi +-8% coprono l'escursione classica dei deck
PITCH_PROBE_HOLES = 3    # buchi sondati a scala completa prima di abbandonare l'ipotesi
                         # pitch (mix non pitchato / brani fuori catalogo): senza tetto,
                         # un mix pieno di brani introvabili brucerebbe il budget in pitch


@dataclass
class IdentifiedTrack:
    position: int
    start_offset_seconds: int
    artist: str
    title: str
    isrc: str | None = None
    apple_id: str | None = None
    confidence: int = 0


@dataclass
class SetMeta:
    source_url: str
    title: str | None = None
    dj_name: str | None = None
    platform: str | None = None
    duration_seconds: int | None = None
    artwork_url: str | None = None


# ---- cuore deterministico (testabile senza I/O) ----------------------------


def plan_offsets(duration_seconds: int, *, segment_length: int = SEGMENT_LENGTH,
                 max_segments: int = MAX_SEGMENTS) -> list[int]:
    """Offset (in secondi) dei segmenti da campionare lungo il mix.

    Passo adattivo: cresce sui mix lunghi per non superare `max_segments` chiamate.
    """
    if duration_seconds <= 0:
        return [0]
    step = max(segment_length, math.ceil(duration_seconds / max_segments))
    offsets = list(range(0, max(1, duration_seconds - segment_length // 2), step))
    return offsets or [0]


def _match_key(match: dict[str, Any]) -> tuple:
    if match.get("isrc"):
        return ("isrc", match["isrc"])
    return ("ta", (match.get("artist") or "").strip().lower(), (match.get("title") or "").strip().lower())


@dataclass
class MatchRun:
    """Serie di campioni concordi sulla stessa traccia."""
    key: tuple
    offset: int  # offset del primo campione della serie
    match: dict[str, Any]
    hits: int = 1
    last_offset: int = 0       # offset dell'ultimo campione concorde della serie
    confirm_attempted: bool = False  # almeno un campione di conferma e' stato tentato


def group_samples(samples: list[tuple[int, dict[str, Any] | None]]) -> list[MatchRun]:
    """Collassa i campioni STRETTAMENTE consecutivi con la stessa chiave.

    `samples` = [(offset, match|None), ...] in ordine di offset. Un buco o un
    match diverso spezzano la serie: le ricomparse ravvicinate le ricuce
    `merge_same_key_runs` (finestra temporale)."""
    runs: list[MatchRun] = []
    prev_matched = False
    for offset, match in samples:
        if not match:
            prev_matched = False
            continue
        key = _match_key(match)
        if runs and prev_matched and runs[-1].key == key:
            runs[-1].hits += 1
            runs[-1].last_offset = offset
        else:
            runs.append(MatchRun(key=key, offset=offset, match=match, last_offset=offset))
        prev_matched = True
    return runs


def merge_same_key_runs(runs: list[MatchRun], *, window: int = MERGE_WINDOW_SECONDS) -> list[MatchRun]:
    """Rifonde la stessa chiave che ricompare entro `window` secondi.

    Anche sopra un match diverso in mezzo: e' il caso reale del falso positivo
    dentro una traccia lunga o dell'overlap di mixaggio (il match in mezzo resta
    una voce sua). Due campioni distanti e concordi valgono cosi' come conferma
    (`hits` sommati). Oltre la finestra la ricomparsa e' una voce nuova (il DJ
    l'ha rimessa davvero)."""
    out: list[MatchRun] = []
    last_by_key: dict[tuple, MatchRun] = {}
    for run in runs:
        prev = last_by_key.get(run.key)
        if prev is not None and run.offset - prev.last_offset <= window:
            prev.hits += run.hits
            prev.last_offset = run.last_offset
        else:
            out.append(run)
            last_by_key[run.key] = run
    return out


def build_tracks(runs: list[MatchRun]) -> list[IdentifiedTrack]:
    """Serie -> tracklist. La confidence deriva dai campioni concordi: 2+ =
    confermata, 1 = dubbia (mai verificata; la UI la marca)."""
    return [
        IdentifiedTrack(
            position=i,
            start_offset_seconds=run.offset,
            artist=run.match["artist"],
            title=run.match["title"],
            isrc=run.match.get("isrc"),
            apple_id=run.match.get("apple_id"),
            confidence=CONFIDENCE_CONFIRMED if run.hits >= 2 else CONFIDENCE_DUBIOUS,
        )
        for i, run in enumerate(runs, start=1)
    ]


ProgressFn = Callable[[int, int], None]


def _clamped_delta(step: int, cap: int) -> int:
    """Mezzo passo, con floor a 6s e cap variabile — spostamento del retry sul
    buco (cap 20) e distanza del campione di conferma (cap 30, piu' lontano
    dalla transizione che ha generato un eventuale falso)."""
    return max(6, min(step // 2, cap))


def identify_from_recognizer(
    duration_seconds: int,
    recognize_at: Callable[[int], dict[str, Any] | None],
    *,
    on_progress: ProgressFn | None = None,
    max_extra_calls: int = MAX_EXTRA_CALLS,
) -> tuple[list[IdentifiedTrack], int | None]:
    """Campiona gli offset, riconosce, conferma, fonde e scarta il rumore.

    `recognize_at(offset, rate)->match|None` isola l'I/O: i test passano una
    funzione finta (`rate` e' il moltiplicatore di compensazione pitch, 1.0 =
    audio com'e'). Robustezza (tutto entro `max_extra_calls` chiamate oltre la
    griglia): un buco viene ritentato una volta a offset spostato, poi con la
    scala pitch-compensata (vedi `PITCH_RATES`: il primo rate che matcha diventa
    quello preferito per i buchi successivi e per le conferme del run — il pitch
    di un set e' perlopiu' globale); le serie con un solo campione ricevono fino
    a due campioni di conferma a +-_confirm_delta — concorde = confermata,
    smentita = scartata (rumore da transizione), mai verificata
    (budget/recognizer/audio corto) = resta in lista come dubbia. Il campione di
    un retry riuscito resta registrato all'offset pianificato.

    Ritorna `(tracks, aborted_at)`: `aborted_at` e' l'offset a cui la griglia si
    e' interrotta per errori consecutivi (endpoint giu'), None a completamento."""
    offsets = plan_offsets(duration_seconds)
    step = offsets[1] - offsets[0] if len(offsets) > 1 else SEGMENT_LENGTH
    budget = max_extra_calls
    consecutive_errors = 0
    aborted_at: int | None = None
    pitch_rate: float | None = None      # rate prevalente scoperto (sticky per il mix)
    pitch_probes_left = PITCH_PROBE_HOLES
    rate_by_offset: dict[int, float] = {}  # offset del campione -> rate che l'ha risolto

    def try_recognize(offset: int, rate: float = 1.0) -> tuple[dict[str, Any] | None, bool]:
        """Ritorna (match, errored). `errored` distingue il guasto del recognizer
        (endpoint giu', gia' passato per pacing+backoff) da un buco genuino: solo
        il buco merita il retry sul buco e vale come tentativo di verifica."""
        nonlocal consecutive_errors
        try:
            match = recognize_at(offset, rate)
            consecutive_errors = 0
            return match, False
        except RecognizerError as exc:
            logger.warning("Riconoscimento fallito a %ss (rate %s): %s", offset, rate, exc)
            consecutive_errors += 1
            return None, True

    def try_pitch(offset: int) -> dict[str, Any] | None:
        """Scala pitch-compensata su un buco rimasto tale dopo il retry spostato.

        Col rate preferito gia' scoperto prova solo quello (un miss = brano fuori
        catalogo, non un pitch diverso); senza, sonda l'intera scala ma solo sui
        primi PITCH_PROBE_HOLES buchi, poi l'ipotesi pitch decade per il mix."""
        nonlocal pitch_rate, pitch_probes_left, budget
        if pitch_rate is not None:
            rates: tuple[float, ...] = (pitch_rate,)
        elif pitch_probes_left > 0:
            pitch_probes_left -= 1
            rates = PITCH_RATES
        else:
            return None
        for rate in rates:
            if budget <= 0 or consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                return None
            budget -= 1
            match, errored = try_recognize(offset, rate)
            if errored:
                return None  # endpoint giu': inutile insistere sulla scala
            if match is not None:
                pitch_rate = rate
                rate_by_offset[offset] = rate
                return match
        return None

    samples: list[tuple[int, dict[str, Any] | None]] = []
    for i, offset in enumerate(offsets, start=1):
        match, errored = try_recognize(offset)
        # Retry solo su un buco genuino: su errore il recognizer ha gia' ritentato
        # col backoff, insistere raddoppierebbe l'attesa verso un endpoint giu'.
        if match is None and not errored and budget > 0 and consecutive_errors < MAX_CONSECUTIVE_ERRORS:
            retry_at = offset + _clamped_delta(step, 20)
            if duration_seconds > 0:
                retry_at = min(retry_at, max(0, duration_seconds - SEGMENT_LENGTH))
            if retry_at > offset:
                budget -= 1
                match, errored = try_recognize(retry_at)
        if match is None and not errored and budget > 0 and consecutive_errors < MAX_CONSECUTIVE_ERRORS:
            match = try_pitch(offset)
        samples.append((offset, match))
        if on_progress:
            on_progress(i, len(offsets))
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            logger.error("Troppi errori di riconoscimento consecutivi: interrompo a %ss.", offset)
            aborted_at = offset
            break

    runs = merge_same_key_runs(group_samples(samples))

    to_confirm = [r for r in runs if r.hits == 1]
    total = len(offsets) + len(to_confirm)
    done = len(offsets)
    delta = _clamped_delta(step, 30)
    for run in to_confirm:
        if budget <= 0 or consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            break  # nessuna verifica possibile: i singoli non verificati restano dubbi
        # Un run nato da un match pitch-compensato va confermato allo stesso rate:
        # a rate naturale la conferma tornerebbe muta e smentirebbe una traccia vera.
        run_rate = rate_by_offset.get(run.offset, 1.0)
        for confirm_at in (run.offset + delta, run.offset - delta):
            if confirm_at == run.offset or confirm_at < 0:
                continue
            if duration_seconds > 0 and confirm_at + SEGMENT_LENGTH > duration_seconds:
                continue
            if budget <= 0 or consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                break
            budget -= 1
            match, errored = try_recognize(confirm_at, run_rate)
            if errored:
                continue  # endpoint giu': non e' una verifica, la voce resta dubbia
            run.confirm_attempted = True
            if match is not None and _match_key(match) == run.key:
                run.hits += 1
                break
        done += 1
        if on_progress:
            on_progress(done, total)

    # Verificata e smentita = rumore da transizione: fuori dalla tracklist.
    # Mai verificata = dubbia: assenza di prove, non prova contraria.
    kept = [r for r in runs if r.hits >= 2 or not r.confirm_attempted]
    return build_tracks(kept), aborted_at


# ---- I/O: download (yt-dlp) + segmentazione (ffmpeg) -----------------------


def download_audio(url: str, workdir: str) -> tuple[str, SetMeta]:
    """Scarica l'audio del mix e ne estrae i metadati. Solleva RuntimeError se fallisce."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        # Evita che yt-dlp riceva file://, schemi locali o host vuoti (SSRF / lettura file).
        raise RuntimeError("URL non valido: ammessi solo link http(s).")

    import yt_dlp

    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(workdir, "mix.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Download fallito: {exc}") from exc
    if not os.path.exists(path):
        # alcuni extractor cambiano estensione dopo il merge: prendi il primo file scaricato
        files = [os.path.join(workdir, f) for f in os.listdir(workdir)]
        path = max(files, key=os.path.getsize) if files else path
    meta = SetMeta(
        source_url=url,
        title=info.get("title"),
        dj_name=info.get("uploader") or info.get("artist") or info.get("channel"),
        platform=(info.get("extractor_key") or info.get("extractor") or "").lower() or None,
        duration_seconds=int(info["duration"]) if info.get("duration") else None,
        artwork_url=info.get("thumbnail"),
    )
    return path, meta


def probe_duration(audio_path: str) -> int | None:
    """Durata in secondi del file audio via ffprobe. None se non determinabile.

    Fallback per i mix di cui yt-dlp non espone la durata (A18): senza, il
    campionamento vedrebbe durata 0 -> un solo segmento -> tracklist di 1 brano.
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
        return int(float(out)) if out else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def _pitch_filter(rate: float) -> list[str]:
    """Argomenti ffmpeg per la compensazione pitch: normalizza a 16k, "rietichetta"
    il sample rate (shift di pitch E tempo insieme, come un pitch fader senza
    keylock), poi torna a 16k. A rate 1.0 nessun filtro."""
    if rate == 1.0:
        return []
    return ["-af", f"aresample=16000,asetrate={round(16000 * rate)},aresample=16000"]


def extract_segment(audio_path: str, offset: int, out_path: str,
                    length: int = SEGMENT_LENGTH, rate: float = 1.0) -> None:
    """Estrae un segmento WAV mono 16kHz a partire da `offset` (per il recognizer).

    `rate` != 1.0 applica la compensazione pitch (vedi `_pitch_filter`)."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
         "-ss", str(offset), "-t", str(length), "-i", audio_path,
         "-ac", "1", "-ar", "16000", *_pitch_filter(rate), "-vn", "-f", "wav", out_path],
        check=True,
    )


def identify_set(
    url: str,
    *,
    recognizer: AudioRecognizer,
    on_progress: ProgressFn | None = None,
) -> tuple[SetMeta, list[IdentifiedTrack], int | None]:
    """Scarica, campiona e identifica un mix. Usa una dir temporanea, pulita a fine.

    Il terzo elemento e' `aborted_at`: offset (secondi) a cui l'analisi si e'
    interrotta per errori persistenti del recognizer, None se completata."""
    with tempfile.TemporaryDirectory(prefix="djmix_") as workdir:
        audio_path, meta = download_audio(url, workdir)
        duration = meta.duration_seconds or 0
        if not duration:
            # yt-dlp senza durata (alcuni extractor/live): ffprobe sul file scaricato.
            duration = probe_duration(audio_path) or 0
            meta.duration_seconds = duration or None

        def recognize_at(offset: int, rate: float = 1.0) -> dict[str, Any] | None:
            seg = os.path.join(workdir, f"seg_{offset}.wav")
            try:
                extract_segment(audio_path, offset, seg, rate=rate)
                return recognizer.recognize_file(seg)
            finally:
                if os.path.exists(seg):
                    os.remove(seg)

        tracks, aborted_at = identify_from_recognizer(duration, recognize_at, on_progress=on_progress)
    return meta, tracks, aborted_at
