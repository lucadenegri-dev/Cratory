"""Discogs come provider di metadati TESTUALI per una singola traccia.
Cerca la miglior release per 'Artista Titolo' e ne estrae label/stile/anno.
Distinto da un eventuale uso discovery (search per genere/etichetta) di Cratory.
Senza token ~25/min; con DISCOGS_TOKEN ~60/min. httpx iniettabile → test senza rete."""

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.integrations._http import get_with_retries

logger = logging.getLogger(__name__)
BASE = "https://api.discogs.com"
_USER_AGENT = "Sortory/0.1 (+http://localhost)"


class DiscogsError(Exception):
    pass


class DiscogsMetaClient:
    def __init__(self, token: str | None = None, http: httpx.Client | None = None):
        self.token = token if token is not None else (settings.discogs_token or None)
        headers = {"User-Agent": _USER_AGENT}
        if self.token:
            headers["Authorization"] = f"Discogs token={self.token}"
        self.http = http or httpx.Client(timeout=15, follow_redirects=True, headers=headers)

    def lookup(self, *, artist: str | None, title: str | None) -> dict[str, Any] | None:
        if not title:
            return None
        q = f"{artist} {title}".strip() if artist else title
        try:
            r = get_with_retries(self.http, f"{BASE}/database/search",
                                 params={"type": "release", "q": q, "per_page": 5},
                                 error_cls=DiscogsError)
        except DiscogsError as exc:
            logger.warning("Discogs lookup '%s' fallito: %s", q, exc)
            return None
        if r.status_code >= 400:
            logger.warning("Discogs %s per '%s'", r.status_code, q)
            return None
        try:
            results = (r.json() or {}).get("results") or []
        except ValueError:
            return None
        if not results:
            return None
        top = results[0]
        out: dict[str, Any] = {}
        labels = top.get("label") or []
        if labels:
            out["label"] = labels[0]
        # style è più specifico del genre generico Discogs ("Electronic"): preferiscilo.
        styles, genres = top.get("style") or [], top.get("genre") or []
        if styles:
            out["genre_primary"] = styles[0]
        elif genres:
            out["genre_primary"] = genres[0]
        if top.get("year"):
            out["release_date"] = str(top["year"])
        return out or None

    def cover(self, *, artist: str | None, title: str | None) -> dict[str, Any] | None:
        """Copertina (full + thumb) della miglior release per 'Artista Titolo'.
        None se nessun risultato o nessuna immagine. Match TESTUALE → confidenza 'text'."""
        if not title:
            return None
        q = f"{artist} {title}".strip() if artist else title
        try:
            r = get_with_retries(self.http, f"{BASE}/database/search",
                                 params={"type": "release", "q": q, "per_page": 5},
                                 error_cls=DiscogsError)
        except DiscogsError as exc:
            logger.warning("Discogs cover '%s' fallito: %s", q, exc)
            return None
        if r.status_code >= 400:
            return None
        try:
            results = (r.json() or {}).get("results") or []
        except ValueError:
            return None
        for top in results:
            full = top.get("cover_image")
            thumb = top.get("thumb") or full
            if full:
                return {"full_url": full, "thumb_url": thumb}
        return None
