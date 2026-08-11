"""Job di revisione generi in background. Mono-job con stato in memoria (come
provider_rescan_job): la UI lancia e poi fa polling di job_state()."""

import logging
import threading

from app.core.config import settings
from app.db import SessionLocal
from app.organize.models import utcnow
from app.organize.services import ai_tags, genre_review

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle", "phase": None, "processed": 0, "total": 0,
    "result": None, "error": None, "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run(folder, genre, redo) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        from app.organize.integrations.discogs_meta import DiscogsMetaClient
        from app.organize.integrations.musicbrainz import MusicBrainzProvider

        mb = MusicBrainzProvider(user_agent=settings.musicbrainz_user_agent)
        discogs = DiscogsMetaClient()
        result = genre_review.review(
            db, mb=mb, discogs=discogs, ai_fn=ai_tags.review_genres,
            folder=folder, genre=genre, redo=redo, on_progress=on_progress)
        with _lock:
            _state.update(status="done", phase=None, result=result,
                          finished_at=utcnow().isoformat())
        logger.info("Revisione generi completata: %s", result)
    except Exception as exc:  # noqa: BLE001 — il job non deve propagare
        logger.exception("Revisione generi fallita")
        with _lock:
            _state.update(status="error", error=str(exc),
                          finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job(folder=None, genre=None, redo=False) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(
            status="running", phase="looking_up", processed=0, total=0,
            result=None, error=None, started_at=utcnow().isoformat(),
            finished_at=None,
        )
        snapshot = dict(_state)
    threading.Thread(target=_run, args=(folder, genre, redo),
                     daemon=True).start()
    return snapshot
