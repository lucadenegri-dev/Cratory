"""iTunes Search API: sorgente di PREVIEW audio (clip 30s) per la Discovery.

API pubblica di Apple, nessun token/auth: `GET https://itunes.apple.com/search`.
Restituisce brani con `previewUrl` (clip AAC 30s). Usato SOLO per la preview dei
lead del dig; non fornisce BPM/key né identità (quella resta Discogs/Spotify).
httpx iniettabile -> test senza rete.
"""

import logging

import httpx

from app.integrations._http import ClosableHttpClient, get_json

logger = logging.getLogger(__name__)

BASE = "https://itunes.apple.com"


class ItunesError(Exception):
    pass


class ItunesClient(ClosableHttpClient):
    def __init__(self, http: httpx.Client | None = None):
        # Nessun token né User-Agent speciale: l'endpoint è pubblico.
        self.http = http or httpx.Client(timeout=15, follow_redirects=True)

    def search(self, term: str, *, limit: int = 5) -> list[dict]:
        payload = get_json(
            self.http, f"{BASE}/search",
            params={"term": term, "media": "music", "entity": "song", "limit": limit},
            error_cls=ItunesError, name="iTunes",
            rate_limit_message="iTunes: rate limit (riprova tra poco).",
        )
        return payload.get("results", []) or []
