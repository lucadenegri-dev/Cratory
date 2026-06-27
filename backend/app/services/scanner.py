"""Motore Scanner deterministico: walk del FS, lettura, upsert in DB."""

import os
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations import content_hash, tagio
from app.models import AudioFile, ScanRoot, utcnow
from app.schemas import ScanSummary

_TAG_FIELDS = (
    "bitrate", "sample_rate", "channels", "duration_s", "artist", "title", "album",
    "album_artist", "genre", "year", "label", "track_no", "comment", "has_cover",
)


def _iter_audio_files(root_path: str) -> Iterator[tuple[str, str]]:
    for dirpath, _dirs, names in os.walk(root_path):
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext in settings.audio_exts:
                yield os.path.join(dirpath, name), ext


def _scan_file_fields(path: str, ext: str) -> dict:
    """Campi aggiornabili di AudioFile per un file, con errori isolati per-file."""
    h, method = content_hash.compute(path, ext)
    fields = {
        "ext": ext.lstrip("."),
        "size_bytes": os.path.getsize(path),
        "content_hash": h,
        "hash_method": method,
        "scan_error": None,
        "has_cover": False,
    }
    for key in _TAG_FIELDS:
        fields.setdefault(key, None)
    try:
        info = tagio.read_info(path)
        tags = tagio.read_tags(path)
    except tagio.TagReadError as exc:
        fields["scan_error"] = str(exc)
        return fields
    fields.update(
        bitrate=info.bitrate, sample_rate=info.sample_rate,
        channels=info.channels, duration_s=info.duration_s,
        artist=tags.artist, title=tags.title, album=tags.album,
        album_artist=tags.album_artist, genre=tags.genre, year=tags.year,
        label=tags.label, track_no=tags.track_no, comment=tags.comment,
        has_cover=tags.has_cover,
    )
    return fields


def scan(db: Session, roots: list[ScanRoot], on_progress=None) -> ScanSummary:
    summary = ScanSummary(roots=[r.id for r in roots], started_at=utcnow())
    work = [(root, p, e) for root in roots for p, e in _iter_audio_files(root.path)]
    summary.found = len(work)
    for index, (root, path, ext) in enumerate(work):
        fields = _scan_file_fields(path, ext)
        existing = db.scalar(
            select(AudioFile).where(AudioFile.root_id == root.id, AudioFile.path == path)
        )
        if existing is None:
            db.add(AudioFile(
                root_id=root.id, path=path, status="present",
                first_seen_at=utcnow(), last_scanned_at=utcnow(), **fields,
            ))
            summary.inserted += 1
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.status = "present"
            existing.last_scanned_at = utcnow()
            summary.updated += 1
        if fields["scan_error"]:
            summary.errors += 1
        if on_progress is not None:
            on_progress(index + 1, summary.found, "scanning")
    for root in roots:
        root.last_scanned_at = utcnow()
    db.commit()
    summary.finished_at = utcnow()
    return summary
