"""Client Spotify Web API concreto (MVP 2).

Due flussi token:
- client_credentials: solo metadata (tracks/artists), nessun login richiesto.
- authorization_code (utente): necessario per creare playlist.

Regola inderogabile: questo client NON fornisce mai BPM o tonalita'.
"""

import base64
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations import SpotifyClient
from app.models import SpotifyToken

logger = logging.getLogger(__name__)

ACCOUNTS = "https://accounts.spotify.com"
API = "https://api.spotify.com/v1"
SCOPES = (
    "playlist-modify-private playlist-modify-public "
    "playlist-read-private playlist-read-collaborative user-library-read"
)
MAX_RETRY_WAIT = 30  # oltre questa attesa (s) su 429 si abortisce invece di dormire


class SpotifyError(Exception):
    pass


class SpotifyNotConfigured(SpotifyError):
    pass


class SpotifyNotConnected(SpotifyError):
    """Manca il login utente (serve per le playlist)."""


def _require_credentials() -> tuple[str, str]:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise SpotifyNotConfigured(
            "Credenziali Spotify mancanti: impostare SPOTIFY_CLIENT_ID e "
            "SPOTIFY_CLIENT_SECRET nel file backend/.env (app su developer.spotify.com)."
        )
    return settings.spotify_client_id, settings.spotify_client_secret


def build_authorize_url(state: str) -> str:
    client_id, _ = _require_credentials()
    params = httpx.QueryParams({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": SCOPES,
        "state": state,
        # Forza la schermata di consenso: se l'utente ha gia' autorizzato con
        # scope piu' ristretti (es. prima dell'aggiunta di playlist-read-*),
        # senza questo Spotify riuserebbe il vecchio grant e il token resterebbe
        # senza i nuovi scope (-> 403 "Insufficient client scope" su /me/playlists).
        "show_dialog": "true",
    })
    return f"{ACCOUNTS}/authorize?{params}"


def make_state() -> str:
    return secrets.token_urlsafe(24)


class SpotifyWebClient(SpotifyClient):
    def __init__(self, db: Session):
        self.db = db
        self.http = httpx.Client(timeout=20)

    # ---- gestione token -------------------------------------------------

    def _save_token(self, kind: str, payload: dict[str, Any]) -> SpotifyToken:
        token = self.db.query(SpotifyToken).filter_by(kind=kind).one_or_none()
        if token is None:
            token = SpotifyToken(kind=kind, access_token="", expires_at=datetime.now(timezone.utc))
            self.db.add(token)
        token.access_token = payload["access_token"]
        if payload.get("refresh_token"):
            token.refresh_token = payload["refresh_token"]
        token.scope = payload.get("scope")
        token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload.get("expires_in", 3600))
        self.db.commit()
        return token

    def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        client_id, client_secret = _require_credentials()
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        try:
            r = self.http.post(f"{ACCOUNTS}/api/token", data=data,
                               headers={"Authorization": f"Basic {basic}"})
        except httpx.HTTPError as exc:
            raise SpotifyError(f"Spotify non raggiungibile durante il token exchange: {exc}") from exc
        if r.status_code != 200:
            raise SpotifyError(f"Token Spotify rifiutato ({r.status_code}): {r.text[:200]}")
        return r.json()

    def exchange_code(self, code: str) -> None:
        payload = self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.spotify_redirect_uri,
        })
        self._save_token("user", payload)

    def user_connected(self) -> bool:
        return self.db.query(SpotifyToken).filter_by(kind="user").one_or_none() is not None

    def _access_token(self, *, user: bool) -> str:
        kind = "user" if user else "client"
        token = self.db.query(SpotifyToken).filter_by(kind=kind).one_or_none()
        now = datetime.now(timezone.utc)

        def expired(t: SpotifyToken) -> bool:
            exp = t.expires_at if t.expires_at.tzinfo else t.expires_at.replace(tzinfo=timezone.utc)
            return exp <= now + timedelta(seconds=60)

        if token is not None and not expired(token):
            return token.access_token

        if user:
            if token is None or not token.refresh_token:
                raise SpotifyNotConnected(
                    "Account Spotify non collegato: usare il login da Settings."
                )
            payload = self._token_request({
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
            })
            return self._save_token("user", payload).access_token

        payload = self._token_request({"grant_type": "client_credentials"})
        return self._save_token("client", payload).access_token

    # ---- chiamate API con rate limit ------------------------------------

    def _get(self, path: str, *, user: bool = False, params: dict | None = None) -> dict[str, Any]:
        return self._call("GET", path, user=user, params=params)

    def _call(self, method: str, path: str, *, user: bool = False,
              params: dict | None = None, json: dict | None = None) -> dict[str, Any]:
        for attempt in range(4):
            token = self._access_token(user=user)
            try:
                r = self.http.request(method, f"{API}{path}", params=params, json=json,
                                      headers={"Authorization": f"Bearer {token}"})
            except httpx.HTTPError as exc:
                raise SpotifyError(f"Spotify non raggiungibile ({method} {path}): {exc}") from exc
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "2")) + 1
                if wait > MAX_RETRY_WAIT:
                    # Spotify puo' rispondere con Retry-After di ore: non bloccare,
                    # riporta un errore chiaro con il tempo di attesa.
                    mins = round(wait / 60)
                    raise SpotifyError(
                        f"Spotify ha applicato un rate limit prolungato (riprova tra ~{mins} "
                        f"minuti). Capita in development mode dopo molte richieste ravvicinate."
                    )
                logger.warning("Spotify rate limit, attesa %ss", wait)
                time.sleep(wait)
                continue
            if r.status_code == 401 and attempt == 0:
                # token scaduto/revocato lato server: azzera solo l'access
                # token, cosi' _access_token imbocca il ramo refresh (kind
                # 'user' ha un refresh_token da preservare). Per kind='client'
                # (client credentials, nessun refresh possibile) la riga va
                # comunque ricreata da zero.
                kind = "user" if user else "client"
                token = self.db.query(SpotifyToken).filter_by(kind=kind).one_or_none()
                if user and token is not None and token.refresh_token:
                    token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                else:
                    self.db.query(SpotifyToken).filter_by(kind=kind).delete()
                self.db.commit()
                continue
            if r.status_code >= 400:
                raise SpotifyError(f"Spotify API {r.status_code} su {path}: {r.text[:80]}")
            return r.json()
        raise SpotifyError(f"Spotify API: troppi tentativi su {path}")

    # ---- interfaccia SpotifyClient ---------------------------------------

    def get_track_metadata(self, spotify_track_id: str) -> dict[str, Any]:
        return self._get(f"/tracks/{spotify_track_id}")

    def get_album(self, spotify_album_id: str) -> dict[str, Any]:
        """Album COMPLETO (GET /albums/{id}): include `label`, assente nell'album
        semplificato annidato nelle tracce di playlist/liked. GET singola: in
        development mode evita il 403 del batch e tiene il conteggio richieste basso."""
        return self._get(f"/albums/{spotify_album_id}")

    # ---- resolver Discovery (Fase F) ------------------------------------

    def search_track(self, artist: str, title: str) -> dict[str, Any] | None:
        """Risolve 'artista + titolo' (es. da Last.fm) in una traccia Spotify reale.

        L'endpoint /search funziona anche in development mode (a differenza di
        /recommendations). Ritorna il dict traccia Spotify o None se nessun match.
        """
        if not artist or not title:
            return None
        query = f'track:{title} artist:{artist}'
        try:
            data = self._get("/search", params={"q": query, "type": "track", "limit": 5})
        except SpotifyError as exc:
            logger.warning("Spotify search_track(%r/%r) fallito: %s", artist, title, exc)
            return None
        items = (data.get("tracks") or {}).get("items") or []
        return items[0] if items else None

    # ---- import playlist (nuovo flusso) ---------------------------------

    def _paginate(self, path: str, *, params: dict | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Scorre un endpoint paginato dell'utente raccogliendo tutti gli `items`."""
        items: list[dict[str, Any]] = []
        params = {**(params or {}), "limit": limit, "offset": 0}
        while True:
            page = self._get(path, user=True, params=params)
            items.extend(page.get("items") or [])
            if not page.get("next"):
                break
            params["offset"] += limit
        return items

    def current_user_id(self) -> str:
        return self._get("/me", user=True)["id"]

    def list_user_playlists(self) -> list[dict[str, Any]]:
        return self._paginate("/me/playlists")

    def get_playlist_meta(self, playlist_id: str) -> dict[str, Any]:
        return self._get(f"/playlists/{playlist_id}", user=True)

    def get_playlist_tracks(self, playlist_id: str) -> list[dict[str, Any]]:
        # Endpoint /items (non /tracks): per le app in Development Mode Spotify
        # risponde 403 Forbidden su /playlists/{id}/tracks, mentre /items (la forma
        # canonica attuale, che include anche gli episodi) funziona. La normalizzazione
        # gestisce entrambe le forme item (item["item"] vs item["track"]).
        return self._paginate(f"/playlists/{playlist_id}/items")

    def get_liked_tracks(self) -> list[dict[str, Any]]:
        return self._paginate("/me/tracks")

    def create_playlist(self, name: str, track_ids: list[str]) -> str:
        me = self._get("/me", user=True)
        playlist = self._call("POST", f"/users/{me['id']}/playlists", user=True, json={
            "name": name,
            "public": False,
            "description": "Creata da Cratory",
        })
        uris = [f"spotify:track:{tid}" for tid in track_ids]
        for i in range(0, len(uris), 100):
            self._call("POST", f"/playlists/{playlist['id']}/tracks", user=True,
                       json={"uris": uris[i:i + 100]})
        return playlist["external_urls"]["spotify"]

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        """Aggiunge tracce a una playlist esistente dell'utente (chunk da 100)."""
        uris = [f"spotify:track:{tid}" for tid in track_ids]
        for i in range(0, len(uris), 100):
            self._call("POST", f"/playlists/{playlist_id}/tracks", user=True,
                       json={"uris": uris[i:i + 100]})
