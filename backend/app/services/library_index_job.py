"""Job di indicizzazione libreria in background (pattern di local_import_job:
mono-utente, un job alla volta, stato in memoria con lock)."""

import logging
import threading
from datetime import datetime, timezone

from app.core.config import settings
from app.db import SessionLocal
from app.services.app_state import set_state
from app.services.library_index import index_library

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "processed": 0, "total": 0,
    "scanned": 0, "matched": 0, "created": 0, "relinked": 0, "duplicates": 0, "lost": 0, "failed": 0,
    "unchanged": 0, "archived": 0,
    "errors": [], "error": None, "root": None,
    "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _spawn(fn) -> None:
    """Separato per i test (che lo rendono sincrono)."""
    threading.Thread(target=fn, daemon=True).start()


def _run_job(root: str) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int) -> None:
        _state.update(processed=processed, total=total)

    try:
        report = index_library(db, root=root,
                               archive_root=settings.archive_root or None,
                               on_progress=on_progress)
        set_state(db, "last_index_at", datetime.now(timezone.utc).isoformat())
        _state.update(status="done", **{k: report[k] for k in
                      ("scanned", "matched", "created", "relinked", "duplicates", "lost", "failed", "unchanged", "archived", "errors")})
        # Enrichment non piu' avviato qui: e' ora responsabilita' di DjOrganizer.
        logger.info("Indicizzazione libreria completata: %s", {
            k: report[k] for k in ("scanned", "matched", "created", "relinked", "lost", "failed", "unchanged", "archived")})
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Indicizzazione libreria fallita")
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


def start_job() -> dict:
    """Avvia il job sulla LIBRARY_ROOT configurata. No-op se già in corso."""
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(status="running", processed=0, total=0, scanned=0, matched=0,
                      created=0, relinked=0, duplicates=0, lost=0, failed=0, unchanged=0, archived=0, errors=[], error=None,
                      root=settings.library_root,
                      started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
    _spawn(lambda: _run_job(settings.library_root))
    return job_state()
