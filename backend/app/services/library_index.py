# backend/app/services/library_index.py
"""Indicizzazione della libreria canonica (disk-first): il disco È la libreria.

Deterministico, senza AI. Per ogni file audio sotto LIBRARY_ROOT:
hash → match (audio_hash → digest legacy → ISRC → fuzzy artist+title) → upsert
del possesso (local_path/has_local_file/formato/bitrate/audio_hash). I tag del
file riempiono SOLO i campi identità vuoti: enrichment e correzioni manuali
restano autorevoli (regola: mai sovrascrivere).
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.local_files import (
    LocalFilesError,
    audio_hash,
    read_audio_quality,
    read_tags,
)
from app.models import Track
from app.services.manual_import import parse_line
from app.services.local_import import scan_folder
from app.services.track_status import refresh_status

logger = logging.getLogger(__name__)

PLATFORM = "local_files"


def _find_track(db: Session, *, digest: str, tags: dict) -> tuple[Track | None, str]:
    """Match nell'ordine di affidabilità. Ritorna (track, come) — come ∈ hash|digest|isrc|fuzzy."""
    hit = db.scalar(select(Track).where(Track.audio_hash == digest))
    if hit:
        return hit, "hash"
    # Import locali storici: il digest viveva in platform_track_id.
    hit = db.scalar(select(Track).where(
        Track.platform == PLATFORM, Track.platform_track_id == digest))
    if hit:
        return hit, "digest"
    if tags.get("isrc"):
        hit = db.scalar(select(Track).where(Track.isrc == tags["isrc"]))
        if hit:
            return hit, "isrc"
    artist, title = tags.get("artist"), tags.get("title")
    if artist and title:
        hit = db.scalar(select(Track).where(
            Track.artist.ilike(artist), Track.title.ilike(title)))
        if hit:
            return hit, "fuzzy"
    return None, ""


def _fill_identity(track: Track, tags: dict, path: Path) -> None:
    """Riempie SOLO i campi vuoti dai tag (fallback dal nome file, come l'import locale)."""
    artist, title = tags.get("artist"), tags.get("title")
    if not artist or not title:
        parsed = parse_line(path.stem)
        if parsed is not None:
            artist = artist or parsed[0]
            title = title or parsed[1]
    track.title = track.title or title
    track.artist = track.artist or artist
    track.album = track.album or tags.get("album")
    track.year = track.year or tags.get("year")
    track.duration_seconds = track.duration_seconds or tags.get("duration_seconds")
    track.isrc = track.isrc or tags.get("isrc")


def _own(track: Track, *, path: Path, digest: str) -> None:
    quality = read_audio_quality(path)
    stat = path.stat()
    track.local_path = str(path.resolve())
    track.has_local_file = True
    track.local_format = quality["format"]
    track.local_bitrate = quality["bitrate"]
    track.audio_hash = digest
    track.local_mtime = stat.st_mtime
    track.local_size = stat.st_size
    track.archived = False  # il possesso in Libreria vince sullo scarto


def _discard(track: Track, *, path: Path, digest: str) -> None:
    """Il file vive nell'archivio: traccia scartata, non posseduta.

    local_path punta al file in archivio (si sa dov'e' finita); mtime/size
    servono allo skip incrementale anche per l'archivio.
    """
    stat = path.stat()
    track.archived = True
    track.has_local_file = False
    track.local_path = str(path.resolve())
    track.local_format = None
    track.local_bitrate = None
    track.audio_hash = digest
    track.local_mtime = stat.st_mtime
    track.local_size = stat.st_size


def index_library(db: Session, *, root: str | Path,
                  archive_root: str | Path | None = None, on_progress=None) -> dict:
    """Indicizza la libreria canonica e (se configurato) l'archivio delle scartate."""
    files = scan_folder(root)
    archive_files: list[Path] = []
    if archive_root and Path(archive_root).is_dir():
        archive_files = scan_folder(archive_root)
    total = len(files) + len(archive_files)
    report = {"scanned": len(files), "matched": 0, "created": 0,
              "relinked": 0, "duplicates": 0, "lost": 0, "failed": 0,
              "unchanged": 0, "archived": 0, "errors": []}
    seen_paths: set[str] = set()
    seen_digests: set[str] = set()

    # Passata 1 — incrementale (Libreria E archivio): i file invariati (path noto,
    # mtime+size uguali) reclamano subito path e hash SENZA ri-hash. Va fatta PRIMA
    # della passata completa: altrimenti una copia nuova dello stesso audio, se
    # scansionata prima dell'originale invariato, gli ruberebbe la traccia.
    done = 0
    pending: list[tuple[Path, bool]] = []
    for path, in_archive in ([(p, False) for p in files]
                             + [(p, True) for p in archive_files]):
        resolved = str(path.resolve())
        stat = path.stat()
        known = db.scalar(select(Track).where(Track.local_path == resolved))
        if (known is not None and known.local_mtime == stat.st_mtime
                and known.local_size == stat.st_size):
            report["unchanged"] += 1
            seen_paths.add(resolved)
            if known.audio_hash:
                seen_digests.add(known.audio_hash)
            done += 1
            if on_progress is not None:
                on_progress(done, total)
        else:
            pending.append((path, in_archive))

    # Passata 2 — flusso completo per i soli file nuovi o modificati.
    # La Libreria viene prima dell'archivio: a parita' di audio il possesso vince.
    for path, in_archive in pending:
        done += 1
        i = done
        try:
            digest = audio_hash(path)
        except LocalFilesError as exc:
            report["failed"] += 1
            report["errors"].append({"path": str(path), "error": str(exc)})
            logger.warning("File saltato %s: %s", path, exc)
            continue
        if digest in seen_digests:
            # Due file con lo stesso audio nello stesso run: il primo vince, gli altri
            # si contano soltanto (la dedup su disco e' compito di DjOrganizer).
            report["duplicates"] += 1
            logger.warning("Audio duplicato nello stesso run: %s (digest gia' visto)", path)
            if on_progress is not None:
                on_progress(i, total)
            continue
        seen_digests.add(digest)
        tags = read_tags(path)
        track, how = _find_track(db, digest=digest, tags=tags)
        if in_archive:
            # In archivio non si creano tracce nuove: un file mai visto da
            # Cratory che scarti non e' una wishlist da ricordare.
            if track is not None:
                _fill_identity(track, tags, path)
                _discard(track, path=path, digest=digest)
                refresh_status(track)
                report["archived"] += 1
                seen_paths.add(str(path.resolve()))
            if on_progress is not None:
                on_progress(i, total)
            continue
        if track is None:
            track = Track(source_type=PLATFORM, platform=PLATFORM, platform_track_id=digest)
            db.add(track)
            report["created"] += 1
        else:
            report["matched"] += 1
            if track.local_path != str(path.resolve()):
                report["relinked"] += 1
        _fill_identity(track, tags, path)
        _own(track, path=path, digest=digest)
        refresh_status(track)
        seen_paths.add(str(path.resolve()))
        if on_progress is not None:
            on_progress(i, total)

    # Anti-unmount (stesso principio dell'import locale): una radice vuota o
    # illeggibile (path sbagliato, disco smontato) non deve azzerare i possessi.
    if not files:
        db.commit()
        return report

    # Riconciliazione: possessi il cui file non esiste piu' (spostato in archive/,
    # cancellato a mano, inbox ripulita). L'audio_hash resta: se il file ricompare
    # altrove, il riaggancio e' immediato.
    owned = db.scalars(select(Track).where(Track.has_local_file.is_(True))).all()
    for track in owned:
        if not track.local_path or track.local_path in seen_paths:
            continue
        if Path(track.local_path).exists():
            continue
        track.has_local_file = False
        track.local_path = None
        track.local_format = None
        track.local_bitrate = None
        refresh_status(track)
        report["lost"] += 1

    db.commit()
    return report
