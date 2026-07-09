"""Revisione di un download andato in needs_review-per-durata.

Il file dubbio è già nell'inbox slskd (path in Track.last_download_path). L'utente
può tenerlo (aggancio come possesso) o scartarlo (cancellazione + sgancio). La
lettura dei tag reali serve al confronto atteso-vs-scaricato in UI.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.integrations.local_files import read_audio_quality, read_tags
from app.models import Track
from app.services.acquisition import attach_local_file

logger = logging.getLogger(__name__)


def review_detail(db: Session, track: Track) -> dict:
    """Atteso (dalla Track) + file scaricato (tag reali dall'inbox), per il confronto."""
    downloaded = None
    path = track.last_download_path
    if path and Path(path).is_file():
        quality = read_audio_quality(path)
        downloaded = {
            "path": path,
            "name": Path(path).name,
            "format": quality.get("format"),
            "bitrate": quality.get("bitrate"),
            "duration_seconds": read_tags(path).get("duration_seconds"),
            "size": Path(path).stat().st_size,
        }
    return {
        "expected": {
            "artist": track.artist,
            "title": track.title,
            "duration_seconds": track.duration_seconds,
        },
        "downloaded": downloaded,
        "reason": track.last_download_reason,
    }


class NoReviewFileError(ValueError):
    """La traccia non ha un file dubbio da tenere/scartare."""


def keep_downloaded(db: Session, track: Track) -> Track:
    """Tieni il file dubbio: aggancialo come possesso e svuota l'esito."""
    path = track.last_download_path
    if not path or not Path(path).is_file():
        raise NoReviewFileError("Nessun file dubbio da tenere.")
    quality = read_audio_quality(path)
    track = attach_local_file(db, track, path=path, fmt=quality["format"],
                              bitrate=quality["bitrate"])
    track.last_download_outcome = None
    track.last_download_reason = None
    track.last_download_path = None
    db.commit()
    db.refresh(track)
    return track


def discard_downloaded(db: Session, track: Track) -> Track:
    """Scarta il file dubbio: cancellalo dall'inbox e sgancia la traccia dall'archivio."""
    path = track.last_download_path
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as exc:  # file lockato / permessi: non bloccare lo sgancio
            logger.warning("Rimozione file dubbio fallita per %s: %s", path, exc)
    track.last_download_outcome = None
    track.last_download_reason = None
    track.last_download_path = None
    db.commit()
    db.refresh(track)
    return track
