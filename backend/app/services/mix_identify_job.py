"""Job in background per l'identificazione di un mix DJ via Shazam.

App locale mono-utente: un solo job alla volta, stato in memoria con lock (stesso
pattern di services/enrichment_job). Il download + le chiamate Shazam sono lenti, la
UI lancia e fa polling. I risultati vengono persistiti come DjSet + DjSetTrack
(separati dalla libreria). Un URL gia' identificato non viene rianalizzato (cache).
"""

import logging
import threading
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import DjSet, DjSetTrack
from app.repositories import get_dj_set_by_url

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",   # idle | running | done | error
    "phase": None,
    "processed": 0,
    "total": 0,
    "dj_set_id": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def _state_snapshot() -> dict:
    """Copia di `_state` senza acquisire `_lock`: solo per uso interno da un
    chiamante che lo tiene gia' (vedi `start_job`) — `threading.Lock` non e'
    rientrante, un secondo acquire dallo stesso thread si bloccherebbe."""
    return dict(_state)


def job_state() -> dict:
    with _lock:
        return _state_snapshot()


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run_job(dj_set_id: int, url: str) -> None:
    from app.integrations.shazam import ShazamioRecognizer
    from app.services.mix_identify import identify_set

    db = SessionLocal()
    recognizer = ShazamioRecognizer()

    def on_progress(processed: int, total: int) -> None:
        _state.update(processed=processed, total=total, phase=f"Riconosco i brani… ({processed}/{total})")

    try:
        dj_set = db.get(DjSet, dj_set_id)
        _state.update(phase="Scarico l'audio del mix…")
        meta, tracks, aborted_at = identify_set(url, recognizer=recognizer, on_progress=on_progress)

        dj_set.title = meta.title
        dj_set.dj_name = meta.dj_name
        dj_set.platform = meta.platform
        dj_set.duration_seconds = meta.duration_seconds
        dj_set.artwork_url = meta.artwork_url
        dj_set.identified_count = len(tracks)
        dj_set.status = "done"
        dj_set.analyzed_at = datetime.now(timezone.utc)
        for t in tracks:
            db.add(DjSetTrack(
                dj_set_id=dj_set.id, position=t.position, start_offset_seconds=t.start_offset_seconds,
                artist=t.artist, title=t.title, isrc=t.isrc, apple_id=t.apple_id, confidence=t.confidence,
            ))
        db.commit()
        _state.update(status="done", phase=None, dj_set_id=dj_set.id)
        logger.info("Mix identificato: set %s, %s tracce", dj_set.id, len(tracks))
    except Exception as exc:  # noqa: BLE001 - qualsiasi fallimento -> stato error, job non crasha
        logger.exception("Identificazione mix fallita")
        try:
            dj_set = db.get(DjSet, dj_set_id)
            if dj_set:
                dj_set.status = "error"
                dj_set.error = str(exc)[:500]
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        _state.update(status="error", error=str(exc), phase=None)
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        recognizer.close()
        db.close()


def start_job(url: str) -> dict:
    """Avvia (o riusa) l'identificazione di un mix. Ritorna {dj_set_id, cached, ...stato}.

    Se l'URL e' gia' stato identificato con successo, ritorna quel set senza rianalisi.
    Se un job e' gia' in corso, ritorna lo stato corrente senza avviarne un altro.
    """
    url = url.strip()
    db = SessionLocal()
    try:
        existing = get_dj_set_by_url(db, url)
        if existing and existing.status == "done":
            return {**job_state(), "dj_set_id": existing.id, "cached": True}
        with _lock:
            if _state["status"] == "running":
                # _state_snapshot(), non job_state(): il lock e' gia' tenuto qui
                # (Lock non e' rientrante, un secondo acquire si bloccherebbe).
                return {**_state_snapshot(), "cached": False}
            if existing:
                dj_set = db.get(DjSet, existing.id)
                # ripulisci un eventuale tentativo precedente fallito
                for t in list(dj_set.tracks):
                    db.delete(t)
                dj_set.status = "identifying"
                dj_set.error = None
                dj_set.identified_count = 0
            else:
                dj_set = DjSet(source_url=url, status="identifying")
                db.add(dj_set)
            db.commit()
            dj_set_id = dj_set.id
            _state.update(
                status="running", phase="Avvio…", processed=0, total=0,
                dj_set_id=dj_set_id, error=None,
                started_at=datetime.now(timezone.utc).isoformat(), finished_at=None,
            )
    finally:
        db.close()
    threading.Thread(target=_run_job, args=(dj_set_id, url), daemon=True).start()
    return {**job_state(), "cached": False}
