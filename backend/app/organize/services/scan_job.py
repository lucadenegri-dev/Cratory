"""Job di scan in background. App locale mono-utente: un job alla volta, stato
in memoria con lock. La UI lancia e poi fa polling di job_state()."""

import logging
import threading
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.organize.models import utcnow
from app.organize.services import analysis
from app.organize.services.roots import radici
from app.organize.services.scanner import scan
from app.services.app_state import get_state, set_state

logger = logging.getLogger(__name__)

# Auto-indicizzazione allo startup: salta se l'ultima è finita da meno di così
# (evita la re-indicizzazione a ogni reload di uvicorn in sviluppo). Assorbito
# da library_index_job (F4 Task 3): stesso valore, stesso comportamento.
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
        # Alimenta l'avvio automatico (start_job_if_due): senza questa scrittura
        # l'auto-indicizzazione ripartirebbe a ogni reload di uvicorn in sviluppo.
        # Assorbito da library_index_job (F4 Task 3), stessa chiave app_state.
        #
        # Solo se la libreria è stata davvero indicizzata: `summary.linking` è
        # None quando lo scan non ha camminato LIBRARY_ROOT (es. `locations=
        # ["inbox"]`, un clic dal filtro Inbox). Scrivere la data lì
        # soddisferebbe un gate che dice «la libreria è stata indicizzata di
        # recente» senza che lo sia, rimandando di AUTO_INDEX_MIN_INTERVAL_MIN
        # la prima indicizzazione vera dopo il boot.
        if summary.linking is not None:
            set_state(db, "last_index_at", utcnow().isoformat())
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


def start_job_if_due() -> dict | None:
    """Avvio automatico allo startup: parte solo se l'ultima scansione è
    abbastanza vecchia. Il pulsante «Indicizza»/«Scava» usa invece start_job()
    e non è mai soggetto a questo gate. Assorbito da library_index_job (F4
    Task 3): stessa finestra, stessa chiave app_state (`last_index_at`)."""
    db = SessionLocal()
    try:
        last = get_state(db, "last_index_at")
    finally:
        db.close()
    if not _auto_index_due(last, datetime.now(timezone.utc)):
        logger.info("Scansione automatica saltata: ultimo run recente (%s)", last)
        return None
    return start_job()
