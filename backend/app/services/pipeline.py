"""Snapshot per la pipeline di orientamento in dashboard.

Un'unica lettura che risponde a "a che punto del ciclo sono?": conteggi DB
(playlist, tracce senza key, wishlist, pronte per set), conteggi disco (file
audio in inbox e in Libreria) e stato indicizzazione. Deterministico: il
disallineamento disco/DB e' un confronto di conteggi, niente euristiche opache.
Cartella non configurata o assente -> campo None (fase neutra, non errore).
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Playlist, Track
from app.services import soulseek_download_job
from app.services.app_state import get_state
from app.services.local_import import scan_folder


def _count_audio_files(root: str) -> int | None:
    """Conta i file audio sotto `root` (walk senza hashing: veloce anche su
    librerie grandi). None se la cartella non e' configurata o non esiste."""
    if not root or not Path(root).is_dir():
        return None
    return len(scan_folder(root))


def pipeline_snapshot(db: Session) -> dict:
    def count(*conds) -> int:
        q = select(func.count()).select_from(Track)
        if conds:
            q = q.where(*conds)
        return db.scalar(q) or 0

    total = count()
    with_key = count(Track.camelot_key.is_not(None), Track.camelot_key != "")
    with_local_file = count(Track.has_local_file.is_(True))

    inbox_files = _count_audio_files(settings.slskd_download_dir)
    files_on_disk = _count_audio_files(settings.library_root)

    download = soulseek_download_job.job_state()
    download_active = download["status"] == "running"

    return {
        "playlists": db.scalar(select(func.count()).select_from(Playlist)) or 0,
        "total_tracks": total,
        "missing_key": total - with_key,
        "wishlist": count(Track.archived.is_not(True),
                          (Track.has_local_file.is_(False)) | (Track.has_local_file.is_(None))),
        "archived_count": count(Track.archived.is_(True)),
        "with_local_file": with_local_file,
        "ready_for_set": count(Track.status == "ready_for_set"),
        "download_active": download_active,
        "download_pending": max(download["total"] - download["processed"], 0) if download_active else 0,
        "inbox_files": inbox_files,
        "files_on_disk": files_on_disk,
        "index_mismatch": None if files_on_disk is None else files_on_disk != with_local_file,
        "last_index_at": get_state(db, "last_index_at"),
        "organizer_url": settings.organizer_url or None,
    }
