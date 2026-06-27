"""Job di scan in background. App locale mono-utente: un job alla volta, stato
in memoria con lock. La UI lancia e poi fa polling di job_state()."""

import logging
import threading

from app.db import SessionLocal
from app.models import ScanRoot, utcnow
from app.services.scanner import scan

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "phase": None,
    "processed": 0,
    "total": 0,
    "result": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run(root_ids: list[int] | None) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        query = db.query(ScanRoot)
        roots = query.filter(ScanRoot.id.in_(root_ids)).all() if root_ids else query.all()
        summary = scan(db, roots, on_progress=on_progress)
        with _lock:
            _state.update(
                status="done", phase=None,
                result=summary.model_dump(mode="json"),
                finished_at=utcnow().isoformat(),
            )
        logger.info("Scan completato: %s", summary.model_dump())
    except Exception as exc:  # noqa: BLE001 — il job non deve propagare
        logger.exception("Scan fallito")
        with _lock:
            _state.update(status="error", error=str(exc), finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job(root_ids: list[int] | None = None) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(
            status="running", phase="scanning", processed=0, total=0,
            result=None, error=None, started_at=utcnow().isoformat(), finished_at=None,
        )
    threading.Thread(target=_run, args=(root_ids,), daemon=True).start()
    return job_state()
