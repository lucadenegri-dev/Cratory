"""Job di enrichment feature in background, condiviso tra i router.

App locale mono-utente: un solo job alla volta, stato in memoria con lock.
Usato sia dall'avvio manuale (router enrichment) sia dall'auto-enrichment dopo
l'import e dal ri-arricchimento di una singola playlist (router playlists).
La UI lancia e poi fa polling di `job_state()` via /api/enrichment/features/status.
"""

import logging
import threading
from datetime import datetime, timezone

from app.db import SessionLocal
from app.integrations.getsongbpm import (
    FeatureProviderError,
    FeatureProviderNotConfigured,
    feature_provider_configured,
    get_feature_provider,
)
from app.services.feature_enrichment import enrich_features

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "phase": None,
    "processed": 0,
    "total": 0,
    "result": None,
    "error": None,
    "playlist_id": None,
    "started_at": None,
    "finished_at": None,
}


def job_state() -> dict:
    """Snapshot dello stato corrente del job (per il polling della UI)."""
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _run_job(force: bool, playlist_id: int | None, track_ids: list[int] | None) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        _state.update(processed=processed, total=total, phase=phase)

    try:
        provider = get_feature_provider()
        result = enrich_features(
            db, provider, force=force, playlist_id=playlist_id, track_ids=track_ids,
            on_progress=on_progress,
        )
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


def start_job(*, force: bool = False, playlist_id: int | None = None,
              track_ids: list[int] | None = None) -> dict:
    """Avvia il job in background e ritorna subito lo stato.

    Se un job e' gia' in esecuzione, ritorna lo stato corrente senza avviarne un altro.
    Solleva FeatureProviderNotConfigured se nessun provider di feature e' configurato.
    """
    if not feature_provider_configured():
        raise FeatureProviderNotConfigured(
            "Nessun provider di feature musicali configurato: abilita DEEZER_ENABLED "
            "(BPM via ISRC, gratis e senza chiave) e/o imposta GETSONGBPM_API_KEY (BPM/key) "
            "o LASTFM_API_KEY (genere/mood) in backend/.env."
        )
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(
            status="running", phase=None, processed=0, total=0, result=None,
            error=None, playlist_id=playlist_id,
            started_at=datetime.now(timezone.utc).isoformat(), finished_at=None,
        )
    threading.Thread(target=_run_job, args=(force, playlist_id, track_ids), daemon=True).start()
    return job_state()
