"""Discogs: sorgente di PROFONDITA' per la Discovery (crate digging).

A differenza di Spotify (dev-mode: search `label:` cap 10, mainstream) e SoundCloud
(API chiusa a nuove app), Discogs e' aperto e profondissimo: `Acid House` -> decine di
migliaia di release, una singola etichetta -> migliaia. Endpoint `/database/search`
con filtro `style`/`genre`/`label` restituisce release con titolo "Artista - Titolo",
stili, etichette e statistiche community (have/want, segnale di "deep cut").

Cosa da' / cosa NON da':
- Identita' + metadati editoriali + stili/etichette + segnale di rarita' (have/want).
- NON da' audio ne' BPM/key: l'audio si risolve su Spotify SOLO al salvataggio del lead.

Funziona anche senza token (rate ~25/min); col token (`DISCOGS_TOKEN`) sale a ~60/min.
httpx iniettabile -> test senza rete.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.integrations._http import get_with_retries

logger = logging.getLogger(__name__)

BASE = "https://api.discogs.com"
# Discogs richiede uno User-Agent identificativo (come MusicBrainz), altrimenti 403.
_USER_AGENT = "Cratory/0.1 (+http://localhost)"
SEARCH_PER_PAGE = 100  # max consentito da Discogs: massimizza il volume per chiamata


class DiscogsError(Exception):
    pass


class DiscogsClient:
    def __init__(self, token: str | None = None, http: httpx.Client | None = None):
        self.token = token if token is not None else (settings.discogs_token or None)
        headers = {"User-Agent": _USER_AGENT}
        if self.token:
            headers["Authorization"] = f"Discogs token={self.token}"
        self.http = http or httpx.Client(timeout=15, follow_redirects=True, headers=headers)

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        r = get_with_retries(self.http, f"{BASE}{path}", error_cls=DiscogsError, params=params)
        if r.status_code == 429:
            raise DiscogsError("Discogs: rate limit (riprova piu' tardi o imposta DISCOGS_TOKEN).")
        if r.status_code >= 400:
            raise DiscogsError(f"Discogs {r.status_code}: {r.text[:160]}")
        try:
            return r.json()
        except ValueError as exc:
            raise DiscogsError("Discogs: risposta non JSON") from exc

    def search_releases(
        self, *, style: str | None = None, genre: str | None = None,
        label: str | None = None, query: str | None = None, per_page: int = SEARCH_PER_PAGE,
    ) -> list[dict[str, Any]]:
        """Release da `/database/search` filtrate per stile/genere/etichetta.

        Una forma unica e coerente (titolo "Artista - Titolo", stili, etichette,
        community) per tutti i semi del dig. Errore -> lista vuota (mai eccezione al router).
        """
        params: dict[str, Any] = {"type": "release", "per_page": per_page}
        if style:
            params["style"] = style
        if genre:
            params["genre"] = genre
        if label:
            params["label"] = label
        if query:
            params["q"] = query
        if not (style or genre or label or query):
            return []
        try:
            data = self._get("/database/search", params=params)
        except DiscogsError as exc:
            logger.warning("Discogs search_releases(%s) fallito: %s", params, exc)
            return []
        return data.get("results") or []
