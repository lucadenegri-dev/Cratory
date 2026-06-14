"""Enrichment feature musicali (Fase B): BPM, key/Camelot, danceability.

Qui si ottengono le feature che servono al Set Builder e che lo streaming non da':
BPM/key (GetSongBPM), label/release/genere (MusicBrainz), genere/mood dai tag (Last.fm),
energia stimata. Job asincrono in background: la UI lancia e poi fa polling dello stato.
"""

import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.db import SessionLocal
from app.integrations.getsongbpm import (
    FeatureProviderError,
    FeatureProviderNotConfigured,
    configured_provider_name,
    feature_provider_configured,
    get_feature_provider,
)
from app.services.feature_enrichment import enrich_features

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/enrichment", tags=["enrichment"])

# App locale mono-utente: un job alla volta, stato in memoria con lock.
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


@router.get("/status")
def status():
    return {"configured": feature_provider_configured(), "provider": configured_provider_name()}


def _run_job(force: bool) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        _state.update(processed=processed, total=total, phase=phase)

    try:
        provider = get_feature_provider()
        result = enrich_features(db, provider, force=force, on_progress=on_progress)
        _state.update(status="done", result=result, phase=None)
        logger.info("Job feature enrichment completato: %s", result)
    except FeatureProviderError as exc:
        _state.update(status="error", error=str(exc))
        logger.error("Job feature enrichment fallito: %s", exc)
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Job feature enrichment fallito (inatteso)")
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


@router.post("/features")
def enrich(force: bool = Query(default=False)):
    """Avvia l'enrichment feature in background e ritorna subito. Seguire /features/status."""
    if not feature_provider_configured():
        raise HTTPException(
            status_code=409,
            detail=str(FeatureProviderNotConfigured(
                "Nessun provider di feature musicali configurato: imposta GETSONGBPM_API_KEY "
                "in backend/.env (chiave gratuita su getsongbpm.com/api)."
            )),
        )
    with _lock:
        if _state["status"] == "running":
            return {"status": "running", "processed": _state["processed"],
                    "total": _state["total"], "phase": _state["phase"]}
        _state.update(status="running", phase=None, processed=0, total=0, result=None,
                      error=None, started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
    threading.Thread(target=_run_job, args=(force,), daemon=True).start()
    return {"status": "running", "processed": 0, "total": 0, "phase": None}


@router.get("/features/status")
def features_status():
    return dict(_state)
