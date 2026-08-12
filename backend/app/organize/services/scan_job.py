"""Job di scan in background. App locale mono-utente: un job alla volta, stato
in memoria con lock. La UI lancia e poi fa polling di job_state()."""

import logging
import threading

from app.db import SessionLocal
from app.organize.models import utcnow
from app.organize.services import analysis
from app.organize.services.roots import radici
from app.organize.services.scanner import scan

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


def _run(locations: list[str] | None) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        # Le radici non sono più righe scelte dall'utente: sono le due cartelle
        # di Settings, derivate (e create/riallineate se serve) da roots.radici.
        tutte = radici(db)
        roots = ([tutte[loc] for loc in locations if loc in tutte] if locations
                 else list(tutte.values()))
        summary = scan(db, roots, on_progress=on_progress)
        analysis_summary = analysis.recompute(db, on_progress=on_progress)
        result = summary.model_dump(mode="json")
        if result.get("linking"):
            # `created_ids` è utile solo a chi vuole agire sulle Track appena
            # create (nessun chiamante in-process, oggi); esposto tal quale in
            # `job_state()["result"]` porterebbe ogni poll di
            # GET /api/organize/scan/status a trascinare, su una prima
            # indicizzazione da 20k brani, altrettanti interi. `library_index_job`
            # copiava di proposito solo le chiavi aggregate: stesso principio qui,
            # sul solo report esposto (`summary.linking` interno resta intero).
            result["linking"] = {k: v for k, v in result["linking"].items()
                                 if k != "created_ids"}
        result["analysis"] = analysis_summary.model_dump(mode="json")
        with _lock:
            _state.update(
                status="done", phase=None, result=result,
                finished_at=utcnow().isoformat(),
            )
        logger.info("Scan+analisi completati: %s", result)
    except Exception as exc:  # noqa: BLE001 — il job non deve propagare
        logger.exception("Scan fallito")
        with _lock:
            _state.update(status="error", error=str(exc), finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job(locations: list[str] | None = None) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(
            status="running", phase="scanning", processed=0, total=0,
            result=None, error=None, started_at=utcnow().isoformat(), finished_at=None,
        )
        snapshot = dict(_state)
    threading.Thread(target=_run, args=(locations,), daemon=True).start()
    return snapshot
