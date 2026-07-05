"""Collega un file audio acquisito a una Track esistente (ownership).

Non tocca lo status di enrichment ne' le feature musicali. Calcola l'audio-hash
(best-effort): e' la chiave di riaggancio quando DjOrganizer rinomina/sposta il
file nella libreria canonica.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.integrations.local_files import (
    AUDIO_EXTENSIONS, LocalFilesError, audio_hash, read_audio_quality,
)
from app.models import Track

logger = logging.getLogger(__name__)


def attach_local_file(db: Session, track: Track, *, path: str,
                      fmt: str | None = None, bitrate: int | None = None) -> Track:
    track.has_local_file = True
    track.local_path = path
    track.local_format = fmt
    track.local_bitrate = bitrate
    try:
        track.audio_hash = audio_hash(path)
    except LocalFilesError as exc:
        # L'hash e' il riaggancio futuro, non un requisito del possesso: non bloccare.
        logger.warning("Audio-hash non calcolabile per %s: %s", path, exc)
    db.commit()
    db.refresh(track)
    return track


class LinkFileError(ValueError):
    """Percorso non valido per il collegamento manuale (inesistente o non audio)."""


def link_local_file(db: Session, track: Track, *, path: str) -> Track:
    """Collegamento manuale di un file su disco: valida e azzera l'esito download.

    L'uscita dall'archivio "da sistemare" avviene qui, qualunque sia la pagina
    da cui si collega (dettaglio traccia o archivio).
    """
    p = Path(path).expanduser()
    if not p.is_file():
        raise LinkFileError(f"File non trovato: {p}")
    if p.suffix.lower() not in AUDIO_EXTENSIONS:
        raise LinkFileError(f"Estensione non audio: {p.suffix or '(nessuna)'}")
    quality = read_audio_quality(p)
    track = attach_local_file(db, track, path=str(p), fmt=quality["format"],
                              bitrate=quality["bitrate"])
    track.last_download_outcome = None
    track.last_download_reason = None
    db.commit()
    db.refresh(track)
    return track
