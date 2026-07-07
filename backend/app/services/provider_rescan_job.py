"""Job di rescan provider in background. Mono-job con stato in memoria (come
scan_job): la UI lancia e poi fa polling di job_state()."""

import logging
import threading

from app.core.config import settings
from app.db import SessionLocal
from app.integrations import acoustid
from app.models import utcnow
from app.services import provider_rescan

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle", "phase": None, "processed": 0, "total": 0,
    "result": None, "error": None, "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run(folder, genre, fields, include_accepted, include_dismissed) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        from app.integrations.discogs_meta import DiscogsMetaClient
        from app.integrations.musicbrainz import MusicBrainzProvider

        mb = MusicBrainzProvider(user_agent=settings.musicbrainz_user_agent)
        discogs = DiscogsMetaClient()
        ac_client = None
        if acoustid.acoustid_configured() and acoustid.fpcalc_available():
            try:
                ac_client = acoustid.get_acoustid_client()
            except acoustid.AcoustIDError:
                ac_client = None
        result = provider_rescan.rescan(
            db, folder=folder, genre=genre, fields=fields,
            mb=mb, discogs=discogs, ac_client=ac_client, on_progress=on_progress,
            include_accepted=include_accepted, include_dismissed=include_dismissed)
        with _lock:
            _state.update(status="done", phase=None, result=result,
                          finished_at=utcnow().isoformat())
        logger.info("Rescan provider completato: %s", result)
    except Exception as exc:  # noqa: BLE001 — il job non deve propagare
        logger.exception("Rescan provider fallito")
        with _lock:
            _state.update(status="error", error=str(exc), finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job(folder=None, genre=None, fields=None,
              include_accepted=False, include_dismissed=False) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(
            status="running", phase="looking_up", processed=0, total=0,
            result=None, error=None, started_at=utcnow().isoformat(), finished_at=None,
        )
        snapshot = dict(_state)
    threading.Thread(
        target=_run, args=(folder, genre, fields, include_accepted, include_dismissed),
        daemon=True).start()
    return snapshot
