"""Job di indicizzazione libreria in background (pattern di local_import_job:
mono-utente, un job alla volta, stato in memoria con lock)."""

import logging
import threading
from datetime import datetime, timedelta, timezone

from app.core import runtime_settings
from app.db import SessionLocal
from app.services.app_state import get_state, set_state
from app.services.library_index import index_library

logger = logging.getLogger(__name__)

# Auto-indicizzazione allo startup: salta se l'ultima è finita da meno di così
# (evita la re-indicizzazione a ogni reload di uvicorn in sviluppo).
AUTO_INDEX_MIN_INTERVAL_MIN = 15


def _auto_index_due(last_iso: str | None, now: datetime,
                    min_interval_min: int = AUTO_INDEX_MIN_INTERVAL_MIN) -> bool:
    """True se conviene rilanciare l'indicizzazione automatica (mai indicizzato, oppure
    l'ultimo run è abbastanza vecchio). Valore corrotto → procedi."""
    if not last_iso:
        return True
    try:
        return now - datetime.fromisoformat(last_iso) >= timedelta(minutes=min_interval_min)
    except ValueError:
        return True

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
                               archive_root=runtime_settings.archive_root() or None,
                               on_progress=on_progress)
        set_state(db, "last_index_at", datetime.now(timezone.utc).isoformat())
        _state.update(status="done", **{k: report[k] for k in
                      ("scanned", "matched", "created", "relinked", "duplicates", "lost", "failed", "unchanged", "archived", "errors")})
        # Enrichment non piu' avviato qui: e' ora responsabilita' di Sortory.
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
                      root=runtime_settings.library_root(),
                      started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
    _spawn(lambda: _run_job(runtime_settings.library_root()))
    return job_state()


def start_job_if_due() -> dict | None:
    """Avvio automatico allo startup: parte solo se l'ultima indicizzazione è
    abbastanza vecchia. Il pulsante «Indicizza» usa invece start_job() e non è
    mai soggetto a questo gate."""
    db = SessionLocal()
    try:
        last = get_state(db, "last_index_at")
    finally:
        db.close()
    if not _auto_index_due(last, datetime.now(timezone.utc)):
        logger.info("Indicizzazione automatica saltata: ultimo run recente (%s)", last)
        return None
    return start_job()
