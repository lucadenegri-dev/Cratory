"""Collega un file audio acquisito a una Track esistente (ownership).

Non tocca lo status di enrichment ne' le feature musicali. Calcola l'audio-hash
(best-effort): e' la chiave di riaggancio quando DjOrganizer rinomina/sposta il
file nella libreria canonica.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.integrations.local_files import LocalFilesError, audio_hash
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
