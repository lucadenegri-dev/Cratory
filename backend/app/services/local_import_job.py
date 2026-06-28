"""Job di import cartella locale in background.

App locale mono-utente: un solo job alla volta, stato in memoria con lock. La UI
lo avvia e poi fa polling di job_state() via /api/playlists/import-local/status.
La fase pesante (tag + hash) riporta il progresso processed/total.
"""

import logging
import threading
from datetime import datetime, timezone

from app.db import SessionLocal
from app.services.local_import import import_local_folder

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "processed": 0,
    "total": 0,
    "created": 0,
    "updated": 0,
    "failed": 0,
    "playlist_id": None,
    "errors": [],
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def job_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _autoenrich(playlist_id: int | None) -> None:
    """Avvia l'enrichment dopo l'import (best-effort: se non configurato, no-op)."""
    if playlist_id is None:
        return
    try:
        from app.integrations.getsongbpm import FeatureProviderNotConfigured
        from app.services import enrichment_job

        enrichment_job.start_job(playlist_id=playlist_id)
    except FeatureProviderNotConfigured:
        logger.info("Auto-enrichment saltato: nessun provider di feature configurato.")
    except Exception:  # noqa: BLE001
        logger.exception("Auto-enrichment post import locale fallito (non bloccante).")


def _run_job(path: str, name: str | None) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int) -> None:
        _state.update(processed=processed, total=total)

    try:
        report = import_local_folder(db, path=path, name=name, on_progress=on_progress)
        _state.update(
            status="done",
            created=report.get("created", 0),
            updated=report.get("updated", 0),
            failed=report.get("failed", 0),
            playlist_id=report.get("playlist_id"),
            errors=report.get("errors", []),
            total=report.get("total", _state["total"]),
        )
        logger.info("Import locale completato: %s", {k: report.get(k) for k in
                    ("playlist_id", "created", "updated", "failed", "total")})
        _autoenrich(report.get("playlist_id"))
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Import locale fallito (inatteso)")
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


def start_job(*, path: str, name: str | None = None) -> dict:
    """Avvia il job in background e ritorna subito lo stato. No-op se già in corso."""
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(
            status="running", processed=0, total=0, created=0, updated=0, failed=0,
            playlist_id=None, errors=[], error=None,
            started_at=datetime.now(timezone.utc).isoformat(), finished_at=None,
        )
    threading.Thread(target=_run_job, args=(path, name), daemon=True).start()
    return job_state()
