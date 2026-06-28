"""Lettura metadati e identità dei file audio locali.

Modulo puro (nessun DB): legge i tag con mutagen e calcola un hash dello stream
audio decodificato con ffmpeg (già richiesto dal modulo Shazam). L'hash ignora i
tag, quindi è stabile a rinomine/spostamenti e a correzioni dei metadati.

L'app NON conserva l'audio: qui si legge soltanto. Le feature di mixing (BPM/key)
NON si derivano dall'audio, restano alla catena di enrichment esterna.
"""

import hashlib
import logging
import subprocess
from pathlib import Path

import mutagen

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".m4a", ".aac", ".aiff", ".aif", ".wav", ".ogg", ".opus", ".wma",
}

HASH_SECONDS = 60


class LocalFilesError(Exception):
    """ffmpeg assente o impossibile decodificare/leggere il file."""


def _id3_text(tags, frame: str) -> str | None:
    f = tags.get(frame)
    if f is not None and getattr(f, "text", None):
        return str(f.text[0])
    return None


def _id3_text_safe(tags, frame: str) -> str | None:
    try:
        return _id3_text(tags, frame)
    except Exception:  # noqa: BLE001
        return None


def read_tags(path: str | Path) -> dict:
    """Legge i tag principali. Valori assenti -> None. Non solleva su file taggati male."""
    out = {"title": None, "artist": None, "album": None, "year": None,
           "duration_seconds": None, "isrc": None}
    try:
        audio = mutagen.File(str(path))
    except Exception as exc:  # noqa: BLE001 — file corrotto/illeggibile: tag vuoti, non fatale
        logger.warning("Tag illeggibili da %s: %s", path, exc)
        return out
    if audio is None:
        return out
    if audio.info is not None and getattr(audio.info, "length", None):
        out["duration_seconds"] = int(audio.info.length)
    tags = getattr(audio, "tags", None)
    if tags is None:
        return out
    date = None
    if hasattr(tags, "getall") and ("TIT2" in tags or _id3_text_safe(tags, "TIT2") is not None):
        # ID3 (mp3 / wav con ID3)
        out["title"] = _id3_text(tags, "TIT2")
        out["artist"] = _id3_text(tags, "TPE1")
        out["album"] = _id3_text(tags, "TALB")
        out["isrc"] = _id3_text(tags, "TSRC")
        date = _id3_text(tags, "TDRC")
    else:
        # Vorbis comment (flac/ogg/opus): chiavi minuscole; MP4 (m4a): atom "©nam" ecc.
        # `tags.get` puo' sollevare (es. mutagen Vorbis rifiuta gli atom MP4 come "\xa9day"
        # perche' non sono chiavi Vorbis valide): si tratta come "chiave assente".
        def first(*keys: str):
            for k in keys:
                try:
                    v = tags.get(k)
                except (ValueError, KeyError):
                    v = None
                if v:
                    return str(v[0])
            return None

        out["title"] = first("title", "\xa9nam")
        out["artist"] = first("artist", "\xa9ART")
        out["album"] = first("album", "\xa9alb")
        out["isrc"] = first("isrc")  # MP4 tiene l'ISRC in atom freeform: non coperto in v1
        date = first("date", "\xa9day")
    if date and str(date)[:4].isdigit():
        out["year"] = int(str(date)[:4])
    return out


def audio_hash(path: str | Path, *, seconds: int = HASH_SECONDS) -> str:
    """SHA-256 dei primi `seconds` di audio decodificato (mono 22050 Hz s16le).

    Solleva LocalFilesError se ffmpeg manca o non riesce a decodificare il file.
    """
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-t", str(seconds), "-ac", "1", "-ar", "22050", "-f", "s16le", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise LocalFilesError("ffmpeg non trovato: necessario per l'hash audio dei file locali.") from exc
    except subprocess.CalledProcessError as exc:
        raise LocalFilesError(f"ffmpeg non ha potuto decodificare {path}") from exc
    if not proc.stdout:
        raise LocalFilesError(f"Nessuno stream audio decodificato da {path}")
    return hashlib.sha256(proc.stdout).hexdigest()
