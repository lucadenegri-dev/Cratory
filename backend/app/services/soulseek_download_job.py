"""Job in background per scaricare tracce via slskd e collegarle alle Track.

Mono-utente, uno-job-per-volta (come local_import_job): threading + stato in
memoria + lock. Per ogni traccia: ricerca -> selezione -> enqueue -> polling
del transfer -> link del file alla Track. Un errore su una traccia non ferma
il job.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.db import SessionLocal
from app.integrations.local_files import read_audio_quality
from app.integrations.slskd import (
    SlskdFile, classify_transfer_state, get_slskd_client,
)
from app.repositories import get_track, tracks_without_local_file
from app.services.acquisition import attach_local_file
from app.services.soulseek_select import best_for_auto

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
DOWNLOAD_TIMEOUT = 180.0

_lock = threading.Lock()
_state: dict = {
    "status": "idle",
    "processed": 0,
    "total": 0,
    "downloaded": 0,
    "needs_review": 0,
    "not_found": 0,
    "failed": 0,
    "playlist_id": None,
    "items": [],
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def job_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _resolve_local_path(download_dir: str, filename: str) -> str | None:
    base = Path(filename.replace("\\", "/")).name
    root = Path(download_dir)
    if not root.exists():
        return None
    matches = [p for p in root.rglob(base) if p.is_file()]
    if not matches:
        return None
    if len(matches) > 1:
        logger.warning("Più file con basename %r in %s: scelgo il più recente", base, download_dir)
    return str(max(matches, key=lambda p: p.stat().st_mtime).resolve())


def _wait_for_download(client, file: SlskdFile) -> str:
    waited = 0.0
    while waited < DOWNLOAD_TIMEOUT:
        state = client.transfer_state(file.username, file.filename)
        cls = classify_transfer_state((state or {}).get("state", ""))
        if cls in ("completed", "failed"):
            return cls
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    return "failed"


def _process_item(db, client, download_dir, track, chosen: SlskdFile | None) -> str:
    if chosen is None:
        files = client.search(track.artist or "", track.title or "")
        best = best_for_auto(files, artist=track.artist or "", title=track.title or "")
        if best is None:
            return "needs_review" if files else "not_found"
        chosen = best.file
    client.enqueue_download(chosen)
    if _wait_for_download(client, chosen) != "completed":
        return "failed"
    path = _resolve_local_path(download_dir, chosen.filename)
    if not path:
        return "failed"
    quality = read_audio_quality(path)
    attach_local_file(db, track, path=path, fmt=quality["format"],
                      bitrate=quality["bitrate"])
    return "downloaded"


def _run(items: list[tuple[int, SlskdFile | None]], playlist_id: int | None) -> None:
    db = SessionLocal()
    try:
        client = get_slskd_client()
        download_dir = settings.slskd_download_dir
        _state.update(total=len(items), playlist_id=playlist_id)
        for i, (track_id, chosen) in enumerate(items, start=1):
            track = get_track(db, track_id)
            if track is None:
                outcome = "failed"
            else:
                try:
                    outcome = _process_item(db, client, download_dir, track, chosen)
                except Exception:  # noqa: BLE001 — un fallimento non ferma il job
                    logger.exception("Download Soulseek fallito per track_id=%s", track_id)
                    outcome = "failed"
            _state[outcome] = _state.get(outcome, 0) + 1
            _state["processed"] = i
            _state["items"].append({
                "track_id": track_id,
                "artist": getattr(track, "artist", None),
                "title": getattr(track, "title", None),
                "outcome": outcome,
            })
        _state.update(status="done")
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Job di download Soulseek interrotto: %s", exc)
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


def _start(items, playlist_id) -> dict:
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(status="running", processed=0, total=len(items),
                      downloaded=0, needs_review=0, not_found=0, failed=0,
                      playlist_id=playlist_id, items=[], error=None,
                      started_at=datetime.now(timezone.utc).isoformat(),
                      finished_at=None)
    threading.Thread(target=_run, args=(items, playlist_id), daemon=True).start()
    return job_state()


def start_playlist_job(playlist_id: int) -> dict:
    db = SessionLocal()
    try:
        items = [(t.id, None) for t in tracks_without_local_file(db, playlist_id)]
    finally:
        db.close()
    return _start(items, playlist_id)


def start_track_job(track_id: int, chosen: SlskdFile) -> dict:
    return _start([(track_id, chosen)], None)
