"""Identificazione delle tracce di un mix DJ (port dell'approccio di mix-id).

Pipeline DETERMINISTICA:
1. download dell'audio dall'URL (yt-dlp);
2. campionamento a segmenti sovrapposti (ffmpeg) lungo la durata;
3. riconoscimento di ogni segmento con retry sui buchi (AudioRecognizer, iniettato);
4. conferma dei match singoli e dedup con finestra sui buchi (gestisce le transizioni del DJ).

Il cuore (`plan_offsets`, `group_samples`/`build_tracks`, `identify_from_recognizer`) e' puro e
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
MAX_SEGMENTS = 100       # tetto ai segmenti (= chiamate al recognizer) per mix
MAX_CONSECUTIVE_ERRORS = 8  # oltre questo numero di errori di fila, interrompe
MERGE_MAX_GAPS = 2       # buchi consecutivi oltre i quali la stessa traccia e' una voce nuova
CONFIDENCE_CONFIRMED = 90  # 2+ campioni concordi
CONFIDENCE_DUBIOUS = 45    # campione singolo mai confermato
MAX_EXTRA_CALLS = 50     # budget per retry sui buchi + conferme dei singoli (per mix)
CONFIRM_DELTA = 4        # secondi di scarto del campione di conferma


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


def group_samples(samples: list[tuple[int, dict[str, Any] | None]]) -> list[MatchRun]:
    """Raggruppa i campioni in serie per traccia, con finestra sui buchi.

    `samples` = [(offset, match|None), ...] in ordine di offset. Campioni consecutivi
    con la stessa chiave si sommano (`hits`). La stessa chiave che ricompare dopo
    soli buchi (fino a MERGE_MAX_GAPS consecutivi) si fonde con la serie precedente;
    con piu' buchi, o un'altra traccia in mezzo, e' una serie nuova (il DJ l'ha
    rimessa davvero)."""
    runs: list[MatchRun] = []
    gap_count = 0
    for offset, match in samples:
        if not match:
            gap_count += 1
            continue
        key = _match_key(match)
        if runs and runs[-1].key == key and gap_count <= MERGE_MAX_GAPS:
            runs[-1].hits += 1
        else:
            runs.append(MatchRun(key=key, offset=offset, match=match))
        gap_count = 0
    return runs


def build_tracks(runs: list[MatchRun]) -> list[IdentifiedTrack]:
    """Serie -> tracklist. La confidence deriva dai campioni concordi: 2+ =
    confermata, 1 = dubbia (resta in lista, la UI la marca)."""
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


def _retry_delta(step: int) -> int:
    """Spostamento del retry su un buco: mezzo passo, tra 6 e 20 secondi."""
    return max(6, min(step // 2, 20))


def identify_from_recognizer(
    duration_seconds: int,
    recognize_at: Callable[[int], dict[str, Any] | None],
    *,
    on_progress: ProgressFn | None = None,
    max_extra_calls: int = MAX_EXTRA_CALLS,
) -> list[IdentifiedTrack]:
    """Campiona gli offset, riconosce, conferma e deduplica.

    `recognize_at(offset)->match|None` isola l'I/O: i test passano una funzione
    finta. Robustezza (tutto entro `max_extra_calls` chiamate oltre la griglia):
    un buco viene ritentato una volta a offset spostato (le transizioni sono la
    causa principale); le serie con un solo campione ricevono un campione di
    conferma a +-CONFIRM_DELTA, e restano in lista come dubbie se non confermate.
    Il campione di un retry riuscito resta registrato all'offset pianificato."""
    offsets = plan_offsets(duration_seconds)
    step = offsets[1] - offsets[0] if len(offsets) > 1 else SEGMENT_LENGTH
    budget = max_extra_calls
    consecutive_errors = 0

    def try_recognize(offset: int) -> dict[str, Any] | None:
        nonlocal consecutive_errors
        try:
            match = recognize_at(offset)
            consecutive_errors = 0
            return match
        except RecognizerError as exc:
            logger.warning("Riconoscimento fallito a %ss: %s", offset, exc)
            consecutive_errors += 1
            return None

    samples: list[tuple[int, dict[str, Any] | None]] = []
    for i, offset in enumerate(offsets, start=1):
        match = try_recognize(offset)
        if match is None and budget > 0 and consecutive_errors < MAX_CONSECUTIVE_ERRORS:
            retry_at = offset + _retry_delta(step)
            if duration_seconds > 0:
                retry_at = min(retry_at, max(0, duration_seconds - SEGMENT_LENGTH))
            if retry_at > offset:
                budget -= 1
                match = try_recognize(retry_at)
        samples.append((offset, match))
        if on_progress:
            on_progress(i, len(offsets))
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            logger.error("Troppi errori di riconoscimento consecutivi: interrompo.")
            break

    runs = group_samples(samples)

    to_confirm = [r for r in runs if r.hits == 1]
    total = len(offsets) + len(to_confirm)
    done = len(offsets)
    for run in to_confirm:
        if budget <= 0:
            break  # budget esaurito: i singoli restano dubbi
        budget -= 1
        confirm_at = run.offset + CONFIRM_DELTA
        if duration_seconds > 0 and confirm_at + SEGMENT_LENGTH > duration_seconds:
            confirm_at = max(0, run.offset - CONFIRM_DELTA)
        match = try_recognize(confirm_at)
        if match is not None and _match_key(match) == run.key:
            run.hits += 1
        done += 1
        if on_progress:
            on_progress(done, total)

    return build_tracks(runs)


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


def extract_segment(audio_path: str, offset: int, out_path: str, length: int = SEGMENT_LENGTH) -> None:
    """Estrae un segmento WAV mono 16kHz a partire da `offset` (per il recognizer)."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
         "-ss", str(offset), "-t", str(length), "-i", audio_path,
         "-ac", "1", "-ar", "16000", "-vn", "-f", "wav", out_path],
        check=True,
    )


def identify_set(
    url: str,
    *,
    recognizer: AudioRecognizer,
    on_progress: ProgressFn | None = None,
) -> tuple[SetMeta, list[IdentifiedTrack]]:
    """Scarica, campiona e identifica un mix. Usa una dir temporanea, pulita a fine."""
    with tempfile.TemporaryDirectory(prefix="djmix_") as workdir:
        audio_path, meta = download_audio(url, workdir)
        duration = meta.duration_seconds or 0
        if not duration:
            # yt-dlp senza durata (alcuni extractor/live): ffprobe sul file scaricato.
            duration = probe_duration(audio_path) or 0
            meta.duration_seconds = duration or None

        def recognize_at(offset: int) -> dict[str, Any] | None:
            seg = os.path.join(workdir, f"seg_{offset}.wav")
            try:
                extract_segment(audio_path, offset, seg)
                return recognizer.recognize_file(seg)
            finally:
                if os.path.exists(seg):
                    os.remove(seg)

        tracks = identify_from_recognizer(duration, recognize_at, on_progress=on_progress)
    return meta, tracks
