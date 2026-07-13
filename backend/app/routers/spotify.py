import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_errors import api_error
from app.db import get_db
from app.integrations.spotify import (
    SpotifyError,
    SpotifyNotConfigured,
    SpotifyNotConnected,
    SpotifyWebClient,
    build_authorize_url,
    make_state,
)
from app.repositories import get_setlist

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/spotify", tags=["spotify"])

# Stato OAuth in memoria: app locale mono-utente, sufficiente per il flusso.
# Dict state->istante per scadere i login abbandonati (niente crescita illimitata).
_STATE_TTL_SECONDS = 600  # 10 min: oltre, lo state CSRF e' considerato scaduto
_pending_states: dict[str, float] = {}


def _remember_state(state: str) -> None:
    now = time.monotonic()
    for s, ts in list(_pending_states.items()):  # prune dei login mai completati
        if now - ts > _STATE_TTL_SECONDS:
            del _pending_states[s]
    _pending_states[state] = now


def _consume_state(state: str | None) -> bool:
    """True se lo state e' valido e non scaduto. In ogni caso lo rimuove (one-shot)."""
    if not state:
        return False
    issued = _pending_states.pop(state, None)
    return issued is not None and (time.monotonic() - issued) <= _STATE_TTL_SECONDS


def _http_error(exc: SpotifyError) -> HTTPException:
    if isinstance(exc, SpotifyNotConfigured):
        return api_error(409, "spotify_not_configured", str(exc), reason=str(exc))
    if isinstance(exc, SpotifyNotConnected):
        return api_error(401, "spotify_not_connected", str(exc), reason=str(exc))
    return api_error(502, "spotify_error", str(exc), reason=str(exc))


@router.get("/status")
def status(db: Session = Depends(get_db)):
    configured = bool(settings.spotify_client_id and settings.spotify_client_secret)
    user_connected = False
    if configured:
        client = SpotifyWebClient(db)
        try:
            user_connected = client.user_connected()
        finally:
            client.close()
    return {
        "configured": configured,
        "user_connected": user_connected,
        # mostrato in UI: deve combaciare ESATTAMENTE col Redirect URI nel dashboard Spotify
        "redirect_uri": settings.spotify_redirect_uri,
    }


@router.get("/login")
def login():
    state = make_state()
    _remember_state(state)
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
    # frontend_origin puo' essere una lista CSV (dev 3000, preview 3001): per il
    # redirect serve UNA origine — la prima e' la canonica; l'intera stringa
    # produrrebbe un Location invalido (la virgola finisce dentro l'host).
    first_origin = settings.frontend_origin.split(",")[0].strip()
    frontend = f"{first_origin}/settings"
    if error or not code:
        return RedirectResponse(f"{frontend}?spotify=error&detail={error or 'no_code'}")
    if not _consume_state(state):
        return RedirectResponse(f"{frontend}?spotify=error&detail=invalid_state")
    client = SpotifyWebClient(db)
    try:
        client.exchange_code(code)
    except SpotifyError as exc:
        logger.error("OAuth Spotify fallito: %s", exc)
        return RedirectResponse(f"{frontend}?spotify=error&detail=token_exchange")
    finally:
        client.close()
    return RedirectResponse(f"{frontend}?spotify=connected")


class CreatePlaylistRequest(BaseModel):
    setlist_id: int
    name: str | None = None


@router.post("/create-playlist")
def create_playlist(req: CreatePlaylistRequest, db: Session = Depends(get_db)):
    setlist = get_setlist(db, req.setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    track_ids = [st.track.spotify_id for st in setlist.tracks if st.track.spotify_id]
    if not track_ids:
        raise api_error(422, "set_no_spotify_tracks", "The set has no Spotify tracks")
    client = SpotifyWebClient(db)
    try:
        url = client.create_playlist(req.name or setlist.name, track_ids)
    except SpotifyError as exc:
        raise _http_error(exc) from exc
    finally:
        client.close()
    skipped = len(setlist.tracks) - len(track_ids)
    return {"playlist_url": url, "tracks_added": len(track_ids), "tracks_skipped": skipped}
