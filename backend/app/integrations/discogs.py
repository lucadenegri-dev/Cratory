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
# Paginazione limitata: piu' volume per il dig (fino a 300 release per seme) senza
# bruciare il rate limit Discogs (~60 req/min col token, ~25 senza). 3 pagine sono
# il compromesso: un dig consuma al massimo 3 richieste, non l'intero budget.
SEARCH_MAX_PAGES = 3


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
        community) per tutti i semi del dig. Pagina fino a SEARCH_MAX_PAGES e
        concatena i risultati; si ferma prima se una pagina e' corta o
        `pagination.pages` dice che non ce ne sono altre.

        Errori: la PRIMA pagina che fallisce SOLLEVA DiscogsError (rate limit o
        token mancante non devono sembrare 'zero risultati': il router li traduce
        in 502 esplicito); una pagina successiva in errore degrada ai risultati
        gia' raccolti (best-effort, con warning nel log).
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
        results: list[dict[str, Any]] = []
        for page in range(1, SEARCH_MAX_PAGES + 1):
            try:
                data = self._get("/database/search", params={**params, "page": page})
            except DiscogsError as exc:
                if page == 1:
                    raise
                logger.warning(
                    "Discogs search_releases(%s) pagina %d fallita: %s — "
                    "ritorno i %d risultati gia' raccolti",
                    params, page, exc, len(results),
                )
                break
            page_results = data.get("results") or []
            results.extend(page_results)
            total_pages = (data.get("pagination") or {}).get("pages")
            # pagina corta o ultima pagina dichiarata -> niente chiamate extra
            if len(page_results) < per_page or (total_pages is not None and page >= total_pages):
                break
        return results

    def get_release(self, release_id: int) -> dict[str, Any]:
        """Dettaglio di una release, inclusa la tracklist reale.

        Come search_releases, l'errore Discogs SOLLEVA DiscogsError: il chiamante
        (l'endpoint del dettaglio) deve poterlo distinguere e mostrarlo come 502
        esplicito, mai propagarlo come 500 grezzo.
        """
        return self._get(f"/releases/{release_id}")
