"""Job integrita' in background. Mono-job con stato in memoria (come
provider_rescan_job): la UI lancia e fa polling di job_state()."""

import logging
import threading

from app.db import SessionLocal
from app.integrations.integrity import ffmpeg_available
from app.models import utcnow
from app.services import analysis, integrity

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle", "phase": None, "processed": 0, "total": 0,
    "result": None, "error": None, "available": True,
    "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run(force: bool) -> None:
    db = SessionLocal()

    def on_progress(processed, total, phase):
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        result = integrity.run_integrity(db, force=force, on_progress=on_progress)
        # Rigenera le issue dall'Inspector: è qui che i file marcati corrupt
        # diventano issue 'corrupt_file' visibili (come lo scan fa dopo lo scan).
        with _lock:
            _state.update(phase="analyzing")
        analysis.recompute(db)
        with _lock:
            _state.update(status="done", phase=None, result=result,
                          finished_at=utcnow().isoformat())
    except Exception as exc:  # noqa: BLE001
        logger.exception("integrity job fallito")
        with _lock:
            _state.update(status="error", error=str(exc),
                          finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job(force: bool = False) -> dict:
    if not ffmpeg_available():
        with _lock:
            _state.update(status="error", available=False,
                          error="ffmpeg non disponibile")
            return dict(_state)
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(status="running", phase="checking", processed=0, total=0,
                      result=None, error=None, available=True,
                      started_at=utcnow().isoformat(), finished_at=None)
        snapshot = dict(_state)
    threading.Thread(target=_run, args=(force,), daemon=True).start()
    return snapshot
