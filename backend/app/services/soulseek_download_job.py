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
from app.services.soulseek_select import AUTO_PICK_MIN_CONFIDENCE, rank_candidates

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
DOWNLOAD_TIMEOUT = 180.0       # tetto per un transfer che sta effettivamente scaricando
QUEUE_PATIENCE = 45.0          # oltre questo, se resta solo in coda, si prova un altro utente
MAX_ATTEMPTS = 4               # quanti candidati (utenti diversi) provare per traccia

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
    """Attende l'esito di un transfer.

    Se il transfer sta scaricando ("InProgress") si concede fino a DOWNLOAD_TIMEOUT;
    se invece resta solo in coda (Queued/Requested) oltre QUEUE_PATIENCE ci si arrende,
    cosi' il chiamante puo' provare un altro utente col fallback.
    """
    waited = 0.0
    queued = 0.0
    while waited < DOWNLOAD_TIMEOUT:
        state = (client.transfer_state(file.username, file.filename) or {}).get("state", "")
        cls = classify_transfer_state(state)
        if cls in ("completed", "failed"):
            return cls
        if "inprogress" in state.lower():
            queued = 0.0
        else:
            queued += POLL_INTERVAL
            if queued >= QUEUE_PATIENCE:
                return "failed"
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    return "failed"


def _download_candidate(client, download_dir, file: SlskdFile) -> str | None:
    """Accoda un candidato, attende l'esito e risolve il path locale. None se fallisce."""
    try:
        client.enqueue_download(file)
    except Exception:  # noqa: BLE001 — un candidato che non parte non ferma il fallback
        logger.exception("enqueue fallito user=%s", file.username)
        return None
    if _wait_for_download(client, file) != "completed":
        return None
    return _resolve_local_path(download_dir, file.filename)


def _attempt_download(db, client, download_dir, track, file: SlskdFile) -> bool:
    """Scarica un candidato e lo collega a una Track esistente. True se riuscito."""
    path = _download_candidate(client, download_dir, file)
    if not path:
        return False
    quality = read_audio_quality(path)
    attach_local_file(db, track, path=path, fmt=quality["format"],
                      bitrate=quality["bitrate"])
    return True


def _import_to_library(db, path: str) -> None:
    """Cataloga un file scaricato manualmente in libreria (playlist virtuale 'Soulseek').

    Riusa la pipeline dei file locali: legge i tag, identita' via hash audio, dedup.
    La pipeline locale imposta solo local_path, quindi marca esplicitamente il possesso
    (has_local_file/local_format/local_bitrate) via attach_local_file.
    """
    from sqlalchemy import select

    from app.models import Track
    from app.services.local_import import build_normalized
    from app.services.playlist_import import identity_normalize, import_playlist

    nt = build_normalized(path)  # LocalFilesError se ffmpeg/hash fallisce
    import_playlist(db, platform="local_files", name="Soulseek", items=[nt],
                    normalize=identity_normalize, kind="local",
                    platform_playlist_id="soulseek-manual", prune=False)
    track = db.scalar(select(Track).where(
        Track.platform == "local_files",
        Track.platform_track_id == nt.platform_track_id,
    ))
    if track is not None:
        quality = read_audio_quality(path)
        attach_local_file(db, track, path=path, fmt=quality["format"],
                          bitrate=quality["bitrate"])


def _process_manual(db, client, download_dir, file: SlskdFile) -> str:
    """Ricerca manuale: scarica il candidato scelto e lo cataloga in libreria."""
    path = _download_candidate(client, download_dir, file)
    if not path:
        return "failed"
    try:
        _import_to_library(db, path)
    except Exception:  # noqa: BLE001
        logger.exception("Catalogazione in libreria fallita per %s", path)
        return "failed"
    return "downloaded"


def _process_item(db, client, download_dir, track, chosen: SlskdFile | None) -> str:
    # Discovery/singola: candidato gia' scelto dall'utente, un solo tentativo.
    if chosen is not None:
        return "downloaded" if _attempt_download(db, client, download_dir, track, chosen) else "failed"

    files = client.search(track.artist or "", track.title or "")
    if not files:
        return "not_found"
    ranked = rank_candidates(files, artist=track.artist or "", title=track.title or "")
    if not ranked or ranked[0].confidence < AUTO_PICK_MIN_CONFIDENCE:
        return "needs_review"
    # Fallback: prova i migliori candidati, un utente diverso alla volta, finche' uno riesce.
    tried: set[str] = set()
    for cand in ranked:
        if len(tried) >= MAX_ATTEMPTS:
            break
        if cand.file.username in tried:
            continue
        tried.add(cand.file.username)
        if _attempt_download(db, client, download_dir, track, cand.file):
            return "downloaded"
    return "failed"


def _run(items: list[tuple[int, SlskdFile | None]], playlist_id: int | None) -> None:
    db = SessionLocal()
    try:
        client = get_slskd_client()
        download_dir = settings.slskd_download_dir
        _state.update(total=len(items), playlist_id=playlist_id)
        for i, (track_id, chosen) in enumerate(items, start=1):
            track = None
            if track_id is None:  # ricerca manuale: scarica + cataloga in libreria
                try:
                    outcome = _process_manual(db, client, download_dir, chosen) if chosen else "failed"
                except Exception:  # noqa: BLE001 — un fallimento non ferma il job
                    logger.exception("Download Soulseek manuale fallito")
                    outcome = "failed"
                title = chosen.filename if chosen else None
            else:
                track = get_track(db, track_id)
                if track is None:
                    outcome = "failed"
                else:
                    try:
                        outcome = _process_item(db, client, download_dir, track, chosen)
                    except Exception:  # noqa: BLE001 — un fallimento non ferma il job
                        logger.exception("Download Soulseek fallito per track_id=%s", track_id)
                        outcome = "failed"
                title = getattr(track, "title", None)
            _state[outcome] = _state.get(outcome, 0) + 1
            _state["processed"] = i
            _state["items"].append({
                "track_id": track_id,
                "artist": getattr(track, "artist", None),
                "title": title,
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


def start_manual_job(chosen: SlskdFile) -> dict:
    """Ricerca manuale: scarica il candidato scelto e lo cataloga in libreria."""
    return _start([(None, chosen)], None)
