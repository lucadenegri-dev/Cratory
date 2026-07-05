"""Job di fingerprinting AcoustID in background (pattern enrichment_job).

App locale mono-utente: un solo job alla volta, stato in memoria con lock.
La UI lancia POST /api/library/fingerprint e fa polling dello stato.
"""

import logging
import threading
from datetime import datetime, timezone

from app.db import SessionLocal
from app.integrations.acoustid import (
    AcoustIDNotConfigured,
    acoustid_configured,
    fpcalc_available,
    get_acoustid_client,
)
from app.services.fingerprint import fingerprint_tracks

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
    """Snapshot dello stato corrente del job (per il polling della UI)."""
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _spawn(fn) -> None:
    """Separato per i test (che lo rendono sincrono)."""
    threading.Thread(target=fn, daemon=True).start()


def fingerprint_ready() -> dict:
    """Prerequisiti del fingerprinting, per la UI: chiave e binario fpcalc."""
    return {
        "configured": acoustid_configured() and fpcalc_available(),
        "api_key": acoustid_configured(),
        "fpcalc": fpcalc_available(),
    }


def _run_job(force: bool, track_ids: list[int] | None) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        _state.update(processed=processed, total=total, phase=phase)

    try:
        client = get_acoustid_client()
        result = fingerprint_tracks(
            db, client, force=force, track_ids=track_ids, on_progress=on_progress,
        )
        _state.update(status="done", result=result, phase=None)
        logger.info("Job fingerprint completato: %s", result)
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Job fingerprint fallito")
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


def start_job(*, force: bool = False, track_ids: list[int] | None = None) -> dict:
    """Avvia il job in background e ritorna subito lo stato.

    Se un job e' gia' in esecuzione, ritorna lo stato corrente senza avviarne un
    altro. Solleva AcoustIDNotConfigured se mancano chiave o fpcalc.
    """
    ready = fingerprint_ready()
    if not ready["configured"]:
        missing = []
        if not ready["api_key"]:
            missing.append("ACOUSTID_API_KEY in backend/.env (gratuita su acoustid.org)")
        if not ready["fpcalc"]:
            missing.append("binario fpcalc/Chromaprint (brew install chromaprint, o env FPCALC)")
        raise AcoustIDNotConfigured("Fingerprinting non configurato: manca " + " e ".join(missing) + ".")
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(
            status="running", phase=None, processed=0, total=0, result=None,
            error=None, started_at=datetime.now(timezone.utc).isoformat(), finished_at=None,
        )
    _spawn(lambda: _run_job(force, track_ids))
    return job_state()
