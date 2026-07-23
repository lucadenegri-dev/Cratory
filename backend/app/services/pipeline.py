"""Snapshot per la pipeline di orientamento in dashboard.

Un'unica lettura che risponde a "a che punto del ciclo sono?": conteggi DB
(playlist, tracce senza key, wishlist, pronte per set) e il conteggio dei file
audio in inbox. Deterministico: niente euristiche opache. Cartella non
configurata o assente -> campo None (fase neutra, non errore).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.config import settings
from app.models import Playlist, Track
from app.services import soulseek_download_job
from app.services.local_import import scan_folder

# La striscia di orientamento fa polling ogni 2s: senza cache ogni poll
# rifaceva il walk dell'inbox (os.walk su tutta la cartella). App personale,
# mono-utente: 10s di scarto tra conteggio e realta' del disco e' invisibile
# nella UI, ma evita di ripetere il walk ad ogni poll. Invalidazione SOLO a
# scadenza TTL (nessuna invalidazione su scrittura: non serve qui).
INBOX_CACHE_TTL_SECONDS = 10.0

# root -> (timestamp letto con `clock`, conteggio file audio)
_inbox_count_cache: dict[str, tuple[float, int]] = {}


def _count_audio_files(
    root: str, *, ttl: float = INBOX_CACHE_TTL_SECONDS, clock: Callable[[], float] = time.monotonic,
) -> int | None:
    """Conta i file audio sotto `root` (walk senza hashing: veloce anche su
    librerie grandi). None se la cartella non e' configurata o non esiste.

    Il conteggio e' cachato per `ttl` secondi: `clock` e' iniettabile nei test."""
    if not root or not Path(root).is_dir():
        return None
    now = clock()
    cached = _inbox_count_cache.get(root)
    if cached is not None and now - cached[0] < ttl:
        return cached[1]
    count = len(scan_folder(root))
    _inbox_count_cache[root] = (now, count)
    return count


def pipeline_snapshot(
    db: Session, *, ttl: float = INBOX_CACHE_TTL_SECONDS, clock: Callable[[], float] = time.monotonic,
) -> dict:
    def count(*conds) -> int:
        q = select(func.count()).select_from(Track)
        if conds:
            q = q.where(*conds)
        return db.scalar(q) or 0

    total = count()
    with_key = count(Track.camelot_key.is_not(None), Track.camelot_key != "")
    with_local_file = count(Track.has_local_file.is_(True))
    analyze_pending = count(
        Track.has_local_file.is_(True),
        (Track.bpm.is_(None)) | (Track.camelot_key.is_(None)) | (Track.camelot_key == ""),
    )

    inbox_files = _count_audio_files(runtime_settings.slskd_download_dir(), ttl=ttl, clock=clock)

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
        "analyze_pending": analyze_pending,
        "ready_for_set": count(Track.status == "ready_for_set"),
        "download_active": download_active,
        "download_pending": max(download["total"] - download["processed"], 0) if download_active else 0,
        "inbox_files": inbox_files,
        "organizer_url": settings.organizer_url or None,
    }
