import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import SessionLocal, get_db
from app.integrations.spotify import (
    SpotifyError,
    SpotifyNotConfigured,
    SpotifyNotConnected,
    SpotifyWebClient,
    build_authorize_url,
    make_state,
)
from app.repositories import get_setlist
from app.services.enrichment import enrich_library

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/spotify", tags=["spotify"])

# Stato OAuth in memoria: app locale mono-utente, sufficiente per il flusso.
_pending_states: set[str] = set()

# Stato del job di enrichment (app locale mono-utente: in memoria con lock).
_enrich_lock = threading.Lock()
_enrich_state: dict = {
    "status": "idle",  # idle | running | done | error
    "phase": None,
    "processed": 0,
    "total": 0,
    "result": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def _http_error(exc: SpotifyError) -> HTTPException:
    if isinstance(exc, SpotifyNotConfigured):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, SpotifyNotConnected):
        return HTTPException(status_code=401, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/status")
def status(db: Session = Depends(get_db)):
    configured = bool(settings.spotify_client_id and settings.spotify_client_secret)
    return {
        "configured": configured,
        "user_connected": SpotifyWebClient(db).user_connected() if configured else False,
        # mostrato in UI: deve combaciare ESATTAMENTE col Redirect URI nel dashboard Spotify
        "redirect_uri": settings.spotify_redirect_uri,
    }


@router.get("/login")
def login():
    state = make_state()
    _pending_states.add(state)
    try:
        return RedirectResponse(build_authorize_url(state))
    except SpotifyNotConfigured as exc:
        raise _http_error(exc) from exc


@router.get("/callback")
def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    frontend = f"{settings.frontend_origin}/settings"
    if error or not code:
        return RedirectResponse(f"{frontend}?spotify=error&detail={error or 'no_code'}")
    if state not in _pending_states:
        return RedirectResponse(f"{frontend}?spotify=error&detail=invalid_state")
    _pending_states.discard(state)
    try:
        SpotifyWebClient(db).exchange_code(code)
    except SpotifyError as exc:
        logger.error("OAuth Spotify fallito: %s", exc)
        return RedirectResponse(f"{frontend}?spotify=error&detail=token_exchange")
    return RedirectResponse(f"{frontend}?spotify=connected")


def _run_enrich_job(force: bool) -> None:
    """Eseguito in un thread separato: usa una sessione DB dedicata."""
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        _enrich_state["processed"] = processed
        _enrich_state["total"] = total
        _enrich_state["phase"] = phase

    try:
        result = enrich_library(db, SpotifyWebClient(db), force=force, on_progress=on_progress)
        _enrich_state["result"] = result
        _enrich_state["status"] = "done"
        logger.info("Job enrichment completato: %s", result)
    except SpotifyError as exc:
        _enrich_state["error"] = str(exc)
        _enrich_state["status"] = "error"
        logger.error("Job enrichment fallito (Spotify): %s", exc)
    except Exception as exc:  # noqa: BLE001
        _enrich_state["error"] = str(exc)
        _enrich_state["status"] = "error"
        logger.exception("Job enrichment fallito (errore inatteso)")
    finally:
        _enrich_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


@router.post("/enrich")
def enrich(force: bool = Query(default=False)):
    """Avvia l'enrichment in background e ritorna subito. Seguire /enrich/status."""
    if not (settings.spotify_client_id and settings.spotify_client_secret):
        raise _http_error(SpotifyNotConfigured(
            "Credenziali Spotify mancanti: impostare SPOTIFY_CLIENT_ID e "
            "SPOTIFY_CLIENT_SECRET in backend/.env."
        ))
    with _enrich_lock:
        if _enrich_state["status"] == "running":
            return {"status": "running", "processed": _enrich_state["processed"],
                    "total": _enrich_state["total"], "phase": _enrich_state["phase"]}
        _enrich_state.update(status="running", phase=None, processed=0, total=0,
                             result=None, error=None,
                             started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
    threading.Thread(target=_run_enrich_job, args=(force,), daemon=True).start()
    return {"status": "running", "processed": 0, "total": 0, "phase": None}


@router.get("/enrich/status")
def enrich_status():
    return dict(_enrich_state)


class CreatePlaylistRequest(BaseModel):
    setlist_id: int
    name: str | None = None


@router.post("/create-playlist")
def create_playlist(req: CreatePlaylistRequest, db: Session = Depends(get_db)):
    setlist = get_setlist(db, req.setlist_id)
    if setlist is None:
        raise HTTPException(status_code=404, detail="Set non trovato")
    track_ids = [st.track.spotify_id for st in setlist.tracks if st.track.spotify_id]
    if not track_ids:
        raise HTTPException(status_code=422, detail="Il set non contiene tracce Spotify")
    try:
        url = SpotifyWebClient(db).create_playlist(req.name or setlist.name, track_ids)
    except SpotifyError as exc:
        raise _http_error(exc) from exc
    skipped = len(setlist.tracks) - len(track_ids)
    return {"playlist_url": url, "tracks_added": len(track_ids), "tracks_skipped": skipped}
