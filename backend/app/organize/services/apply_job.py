"""Job Apply in background. App locale: un apply alla volta, stato in memoria + lock."""

import logging
import threading

from sqlalchemy import select

from app.db import SessionLocal
from app.organize.models import Plan, utcnow
from app.organize.services.apply import apply_plan

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_state: dict = {"status": "idle", "phase": None, "processed": 0, "total": 0,
                "result": None, "error": None, "started_at": None, "finished_at": None}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run() -> None:
    db = SessionLocal()

    def on_progress(processed, total, phase):
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        plan = db.scalar(select(Plan).where(Plan.status == "draft").order_by(Plan.id.desc()))
        if plan is None:
            with _lock:
                _state.update(status="error", error="nessun piano draft",
                              finished_at=utcnow().isoformat())
            return
        result = apply_plan(db, plan, on_progress=on_progress)
        with _lock:
            _state.update(status="done", phase=None,
                          result=result.model_dump(mode="json"),
                          finished_at=utcnow().isoformat())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Apply fallito")
        with _lock:
            _state.update(status="error", error=str(exc), finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job() -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(status="running", phase="applying", processed=0, total=0,
                      result=None, error=None, started_at=utcnow().isoformat(), finished_at=None)
        snapshot = dict(_state)
    threading.Thread(target=_run, daemon=True).start()
    return snapshot
