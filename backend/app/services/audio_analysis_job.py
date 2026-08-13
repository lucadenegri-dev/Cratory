"""Job di analisi BPM/key in background (pattern scan_job: mono-utente,
un job alla volta, stato in memoria con lock).

Scrive SOLO analysis_* + analyzed_at/analysis_error; l'unico ponte automatico
verso i canonici e' auto_apply_missing (campi vuoti, nessun conflitto). Il resto
passa dall'apply esplicito del router."""

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.db import SessionLocal
from app.integrations import essentia_engine
from app.models import Track, utcnow
from app.services.audio_analysis import auto_apply_missing
from app.services.job_spawn import spawn as _spawn

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "processed": 0, "total": 0,
    "analyzed": 0, "failed": 0, "applied": 0,
    "current_label": None, "error": None,
    "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _select_tracks(db, scope: str, track_ids: list[int] | None) -> list[Track]:
    q = select(Track).where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
    if track_ids:
        q = q.where(Track.id.in_(track_ids))
    elif scope == "missing":
        q = q.where(or_(Track.bpm.is_(None), Track.camelot_key.is_(None),
                        Track.camelot_key == ""))
    return list(db.scalars(q).all())


def _run_job(scope: str, track_ids: list[int] | None) -> None:
    db = SessionLocal()
    try:
        tracks = _select_tracks(db, scope, track_ids)
        _state["total"] = len(tracks)
        analyzed = failed = applied = 0
        for i, t in enumerate(tracks, start=1):
            _state.update(processed=i,
                          current_label=f"{t.artist or '?'} — {t.title or '?'}")
            try:
                res = essentia_engine.analyze_subprocess(t.local_path)
                t.analysis_bpm, t.analysis_camelot = res.bpm, res.camelot
                t.analysis_error = None
                analyzed += 1
            except Exception as exc:  # noqa: BLE001 — file illeggibile: il batch prosegue
                t.analysis_error = "analysis_decode_failed"
                failed += 1
                logger.warning("Analisi fallita per %s: %s", t.local_path, exc)
            t.analyzed_at = utcnow()
            if auto_apply_missing(t):
                applied += 1
            db.commit()  # commit per traccia: il progresso sopravvive a un'interruzione
            _state.update(analyzed=analyzed, failed=failed, applied=applied)
        _state.update(status="done")
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Job di analisi fallito")
    finally:
        _state.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      current_label=None)
        db.close()


def start_job(scope: str = "missing", track_ids: list[int] | None = None) -> dict:
    """Avvia il job. No-op (stato invariato) se gia' in corso."""
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(status="running", processed=0, total=0, analyzed=0,
                      failed=0, applied=0, current_label=None, error=None,
                      started_at=datetime.now(timezone.utc).isoformat(),
                      finished_at=None)
    _spawn(lambda: _run_job(scope, track_ids))
    return job_state()
