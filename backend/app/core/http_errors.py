"""Errori HTTP con codice stabile: il frontend traduce `code` nella lingua
attiva; `message` (inglese) è il fallback leggibile per debug/curl."""
from fastapi import HTTPException

from app.integrations.spotify import SpotifyError, SpotifyNotConfigured, SpotifyNotConnected


def api_error(status_code: int, code: str, message: str, **params) -> HTTPException:
    detail: dict = {"code": code, "message": message}
    if params:
        detail["params"] = params
    return HTTPException(status_code=status_code, detail=detail)


def spotify_http_error(exc: SpotifyError) -> HTTPException:
    """Mappatura condivisa tra routers/playlists.py e routers/spotify.py: stessa
    famiglia di eccezioni Spotify, stessi codici (409/401/502)."""
    if isinstance(exc, SpotifyNotConfigured):
        return api_error(409, "spotify_not_configured", str(exc), reason=str(exc))
    if isinstance(exc, SpotifyNotConnected):
        return api_error(401, "spotify_not_connected", str(exc), reason=str(exc))
    return api_error(502, "spotify_error", str(exc), reason=str(exc))
