"""Identificazione delle tracce di un mix DJ (port dell'approccio di mix-id).

Pipeline DETERMINISTICA:
1. download dell'audio dall'URL (yt-dlp);
2. campionamento a segmenti sovrapposti (ffmpeg) lungo la durata;
3. riconoscimento di ogni segmento (AudioRecognizer, iniettato);
4. dedup dei match consecutivi (gestisce le transizioni del DJ).

Il cuore (`plan_offsets`, `dedup_consecutive`, `identify_from_recognizer`) e' puro e
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


def dedup_consecutive(samples: list[tuple[int, dict[str, Any] | None]]) -> list[IdentifiedTrack]:
    """Collassa i match CONSECUTIVI identici (stessa traccia campionata piu' volte).

    `samples` = [(offset, match|None), ...] in ordine di offset. Un brano che riappare
    piu' tardi, dopo un altro, e' una nuova voce (il DJ l'ha rimesso)."""
    out: list[IdentifiedTrack] = []
    last_key: tuple | None = None
    for offset, match in samples:
        if not match:
            last_key = None  # un buco rompe la sequenza
            continue
        key = _match_key(match)
        if key == last_key:
            continue
        last_key = key
        out.append(IdentifiedTrack(
            position=len(out) + 1,
            start_offset_seconds=offset,
            artist=match["artist"],
            title=match["title"],
            isrc=match.get("isrc"),
            apple_id=match.get("apple_id"),
            confidence=int(match.get("confidence") or 0),
        ))
    return out


ProgressFn = Callable[[int, int], None]


def identify_from_recognizer(
    duration_seconds: int,
    recognize_at: Callable[[int], dict[str, Any] | None],
    *,
    on_progress: ProgressFn | None = None,
) -> list[IdentifiedTrack]:
    """Campiona gli offset, riconosce e deduplica. `recognize_at(offset)->match|None`
    isola l'I/O: i test passano una funzione finta."""
    offsets = plan_offsets(duration_seconds)
    samples: list[tuple[int, dict[str, Any] | None]] = []
    consecutive_errors = 0
    for i, offset in enumerate(offsets, start=1):
        try:
            match = recognize_at(offset)
            consecutive_errors = 0
        except RecognizerError as exc:
            logger.warning("Riconoscimento fallito a %ss: %s", offset, exc)
            match = None
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error("Troppi errori di riconoscimento consecutivi: interrompo.")
                break
        samples.append((offset, match))
        if on_progress:
            on_progress(i, len(offsets))
    return dedup_consecutive(samples)


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
