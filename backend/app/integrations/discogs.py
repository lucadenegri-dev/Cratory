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

from app.core import runtime_settings
from app.integrations._http import ClosableHttpClient, get_json

logger = logging.getLogger(__name__)

BASE = "https://api.discogs.com"
# Discogs richiede uno User-Agent identificativo (come MusicBrainz), altrimenti 403.
_USER_AGENT = "Cratory/0.1 (+http://localhost)"
SEARCH_PER_PAGE = 100  # max consentito da Discogs: massimizza il volume per chiamata
# Ordinamento del bacino: per DOMANDA. Senza `sort`, Discogs restituisce un ordine
# arbitrario: su style=Acid House (43k release) le prime 300 non contengono NEMMENO UNA
# release con have>1000 e il 46% ne ha meno di 5. Con sort=want la prima pagina e' il
# canone (Phuture, Underground Resistance). Misurato, non supposto.
SORT_WANT = "want"
SORT_DESC = "desc"
# Tetto duro di Discogs: pagina 101 -> 404. Con per_page=100 sono 10.000 release.
DISCOGS_MAX_PAGES = 100


class DiscogsError(Exception):
    pass


class DiscogsClient(ClosableHttpClient):
    def __init__(self, token: str | None = None, http: httpx.Client | None = None):
        self.token = token if token is not None else (runtime_settings.discogs_token() or None)
        headers = {"User-Agent": _USER_AGENT}
        if self.token:
            headers["Authorization"] = f"Discogs token={self.token}"
        self.http = http or httpx.Client(timeout=15, follow_redirects=True, headers=headers)

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        return get_json(
            self.http, f"{BASE}{path}", params=params, error_cls=DiscogsError, name="Discogs",
            rate_limit_message="Discogs: rate limit (riprova piu' tardi o imposta DISCOGS_TOKEN).",
        )

    def _filters(
        self, style: str | None, genre: str | None, label: str | None, query: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"type": "release"}
        if style:
            params["style"] = style
        if genre:
            params["genre"] = genre
        if label:
            params["label"] = label
        if query:
            params["q"] = query
        return params

    def count_releases(
        self, *, style: str | None = None, genre: str | None = None,
        label: str | None = None, query: str | None = None,
    ) -> int:
        """Quante release ha il seme. Sonda economica (per_page=1): serve a sapere
        quanto e' alta la pila PRIMA di scegliere in che punto pescare."""
        params = self._filters(style, genre, label, query)
        if len(params) == 1:  # solo `type`: nessun filtro
            return 0
        data = self._get("/database/search", params={**params, "per_page": 1, "page": 1})
        return int((data.get("pagination") or {}).get("items") or 0)

    def search_releases(
        self, *, style: str | None = None, genre: str | None = None,
        label: str | None = None, query: str | None = None,
        pages: list[int] | None = None, sort: str | None = None,
        sort_order: str | None = None, per_page: int = SEARCH_PER_PAGE,
    ) -> list[dict[str, Any]]:
        """Release da `/database/search`, per le PAGINE richieste dal chiamante.

        Il motore decide quali pagine (la finestra scelta da `depth`); il client le
        scarica e basta.

        Errori: la PRIMA pagina richiesta che fallisce SOLLEVA DiscogsError (rate limit o
        token mancante non devono sembrare 'zero risultati': il router li traduce in 502
        esplicito); una pagina successiva in errore degrada ai risultati gia' raccolti
        (best-effort, con warning nel log).
        """
        params = self._filters(style, genre, label, query)
        if len(params) == 1:
            return []
        params["per_page"] = per_page
        if sort:
            params["sort"] = sort
        if sort_order:
            params["sort_order"] = sort_order

        # `pages=None` -> default pagina 1; `pages=[]` ESPLICITO -> zero richieste.
        # `pages or [1]` non distingueva i due casi e una lista vuota scaricava
        # comunque la pagina 1: scostamento muto dal contratto "le pagine che il
        # chiamante chiede".
        results: list[dict[str, Any]] = []
        for i, page in enumerate([1] if pages is None else pages):
            try:
                data = self._get("/database/search", params={**params, "page": page})
            except DiscogsError as exc:
                if i == 0:
                    raise
                logger.warning(
                    "Discogs search_releases(%s) pagina %d fallita: %s — "
                    "ritorno i %d risultati gia' raccolti",
                    params, page, exc, len(results),
                )
                # Ci si FERMA, non si salta la pagina: il modo di fallire dominante e' il
                # rate limit (~25 req/min senza token, ~60 col token). Se la pagina N
                # fallisce la quota e' quasi sempre esaurita, quindi anche le successive
                # fallirebbero: insistere spende richieste gia' condannate e fa aspettare
                # l'utente per niente.
                break
            results.extend(data.get("results") or [])
        return results

    def get_release(self, release_id: int) -> dict[str, Any]:
        """Dettaglio di una release, inclusa la tracklist reale.

        Come search_releases, l'errore Discogs SOLLEVA DiscogsError: il chiamante
        (l'endpoint del dettaglio) deve poterlo distinguere e mostrarlo come 502
        esplicito, mai propagarlo come 500 grezzo.
        """
        return self._get(f"/releases/{release_id}")
