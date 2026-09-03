import html
import json
import logging
import time
from typing import NamedTuple
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.config import settings
from app.core.http_errors import api_error, spotify_http_error
from app.core.origins import origini_ammesse
from app.db import get_db
from app.integrations.spotify import (
    SpotifyError,
    SpotifyNotConfigured,
    SpotifyWebClient,
    build_authorize_url,
    make_state,
)
from app.repositories import get_setlist
from app.services.app_state import get_language

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/spotify", tags=["spotify"])


class _Pending(NamedTuple):
    """Un login iniziato e non ancora tornato: quando e' partito (per scaderlo)
    e dove va riportato l'utente. La destinazione viaggia con lo state e non
    nella query del callback perche' quella la riscrive Spotify: e' l'unico
    posto in cui non puo' essere scelta da chi apre l'URL."""
    issued: float
    return_to: str | None


# Stato OAuth in memoria: app locale mono-utente, sufficiente per il flusso.
# Dict state->_Pending per scadere i login abbandonati (niente crescita illimitata).
_STATE_TTL_SECONDS = 600  # 10 min: oltre, lo state CSRF e' considerato scaduto
_pending_states: dict[str, _Pending] = {}


def _remember_state(state: str, return_to: str | None = None) -> None:
    now = time.monotonic()
    for s, pending in list(_pending_states.items()):  # prune dei login mai completati
        if now - pending.issued > _STATE_TTL_SECONDS:
            del _pending_states[s]
    _pending_states[state] = _Pending(issued=now, return_to=return_to)


def _consume_state(state: str | None) -> tuple[bool, str | None]:
    """(state valido e non scaduto, destinazione di ritorno ricordata).
    In ogni caso lo state viene rimosso (one-shot).

    La destinazione torna anche per uno state scaduto: era gia' stata validata
    all'emissione, e riportare l'utente dentro l'app con un errore leggibile e'
    meglio che lasciarlo su una pagina morta."""
    if not state:
        return False, None
    pending = _pending_states.pop(state, None)
    if pending is None:
        return False, None
    return (time.monotonic() - pending.issued) <= _STATE_TTL_SECONDS, pending.return_to


def _ritorno_ammesso(url: str | None) -> str | None:
    """La destinazione di ritorno chiesta dalla pagina, se e' una delle origini
    che questa installazione riconosce (le stesse del CORS, `tauri://localhost`
    inclusa). Fuori da quelle e' None: il parametro arriva dalla query string, e
    prenderlo com'e' farebbe di /callback un redirect aperto — con un codice di
    autorizzazione Spotify addosso.

    Query e fragment vengono scartati: quella query la scrive il callback."""
    if not url:
        return None
    parti = urlsplit(url)
    if not parti.scheme or not parti.netloc:
        return None
    if f"{parti.scheme}://{parti.netloc}" not in origini_ammesse(settings.frontend_origin):
        return None
    return urlunsplit((parti.scheme, parti.netloc, parti.path or "/", "", ""))


def _destinazione(return_to: str | None) -> str:
    """Dove torna l'utente a fine login. Senza `return_to` ricordato resta il
    comportamento storico: frontend_origin puo' essere una lista CSV (dev 3000,
    preview 3001), e per il redirect serve UNA origine — la prima e' la
    canonica; l'intera stringa produrrebbe un Location invalido (la virgola
    finisce dentro l'host)."""
    if return_to:
        return return_to
    first_origin = settings.frontend_origin.split(",")[0].strip()
    return f"{first_origin}/settings"


# (riuscito, fallito, etichetta del link). Il testo segue l'esito: questa
# pagina si vede solo quando il salto automatico non parte, ed e' esattamente
# il momento in cui dire "collegato" dopo un errore sarebbe una bugia.
_TESTI_RITORNO = {
    "it": ("Spotify collegato.", "Login Spotify non riuscito.", "Torna a Cratory"),
    "en": ("Spotify connected.", "Spotify login failed.", "Back to Cratory"),
}


def _pagina_di_ritorno(dest: str, lang: str, riuscito: bool) -> str:
    """La paginetta che riporta il webview dentro l'app.

    Serve perche' nel bundle la pagina sta su `tauri://localhost` mentre questo
    callback risponde da `http://127.0.0.1:8000`: un `Location:` verso uno
    schema custom e' terreno incerto per WKWebView, mentre una navigazione
    fatta dalla pagina e' quella che il webview gia' esegue di suo. E se anche
    quella non partisse, qui dentro c'e' un link: la finestra dell'app non ha
    barra degli indirizzi, quindi l'alternativa a una frase e un link sarebbe
    un vicolo cieco."""
    ok, ko, link = _TESTI_RITORNO.get(lang, _TESTI_RITORNO["it"])
    titolo = ok if riuscito else ko
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Cratory</title></head>"
        "<body style=\"font-family:system-ui,sans-serif;padding:2rem\">"
        f"<p>{html.escape(titolo)}</p>"
        f"<p><a href=\"{html.escape(dest, quote=True)}\">{html.escape(link)}</a></p>"
        f"<script>location.replace({json.dumps(dest)})</script>"
        "</body></html>"
    )


def _torna_alla_pagina(return_to: str | None, db: Session, **esito: str) -> Response:
    """L'esito del login, consegnato alla pagina che lo aveva chiesto."""
    dest = f"{_destinazione(return_to)}?{urlencode(esito)}"
    if urlsplit(dest).scheme in ("http", "https"):
        return RedirectResponse(dest)
    return HTMLResponse(
        _pagina_di_ritorno(dest, get_language(db), esito.get("spotify") == "connected")
    )


@router.get("/status")
def status(db: Session = Depends(get_db)):
    configured = bool(runtime_settings.spotify_client_id()
                      and runtime_settings.spotify_client_secret())
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
def login(return_to: str | None = None):
    """`return_to`: la pagina dice dove vuole tornare a login finito. Senza,
    si torna a /settings sulla prima origine di FRONTEND_ORIGIN — che nel
    bundle desktop non e' dove sta la pagina, ed e' esattamente il motivo per
    cui questo parametro esiste."""
    state = make_state()
    _remember_state(state, _ritorno_ammesso(return_to))
    try:
        return RedirectResponse(build_authorize_url(state))
    except SpotifyNotConfigured as exc:
        raise spotify_http_error(exc) from exc


@router.get("/callback")
def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    # Lo state si consuma per primo anche quando il login e' gia' fallito: e'
    # da li' che si sa dove riportare l'utente, e un esito d'errore consegnato
    # a una pagina morta e' il difetto peggiore dei due.
    valido, return_to = _consume_state(state)
    if error or not code:
        return _torna_alla_pagina(return_to, db, spotify="error", detail=error or "no_code")
    if not valido:
        return _torna_alla_pagina(return_to, db, spotify="error", detail="invalid_state")
    client = SpotifyWebClient(db)
    try:
        client.exchange_code(code)
    except SpotifyError as exc:
        logger.error("OAuth Spotify fallito: %s", exc)
        return _torna_alla_pagina(return_to, db, spotify="error", detail="token_exchange")
    finally:
        client.close()
    return _torna_alla_pagina(return_to, db, spotify="connected")


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
        raise spotify_http_error(exc) from exc
    finally:
        client.close()
    skipped = len(setlist.tracks) - len(track_ids)
    return {"playlist_url": url, "tracks_added": len(track_ids), "tracks_skipped": skipped}
