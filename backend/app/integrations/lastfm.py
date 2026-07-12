"""Client Last.fm concreto (Fase F, Discovery mode).

Last.fm e' la fonte di SIMILARITA' del Discovery: dato un artista o una traccia
restituisce artisti/tracce affini (e tracce top per tag/genere). E' gratuito,
affidabile e disponibile anche per app non in produzione — a differenza dell'endpoint
Spotify `/recommendations`, deprecato a fine 2024 per le app nuove / in development.

Regole del progetto:
- Last.fm NON fornisce BPM/key/mood: quelli arrivano dopo, dall'enrichment esterno.
- L'identita' di streaming (id Spotify, ISRC, cover) viene risolta a valle da Spotify.
- httpx iniettabile -> test senza rete.
"""

import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.integrations import SimilarityClient
from app.integrations._http import ClosableHttpClient, get_json

logger = logging.getLogger(__name__)

API = "https://ws.audioscrobbler.com/2.0/"
# Le ToS Last.fm richiedono uno User-Agent identificativo (stessa convenzione
# di Discogs/MusicBrainz): senza, l'app e' indistinguibile da uno scraper.
_USER_AGENT = "Cratory/0.1 (+http://localhost)"

# Cache in-memory con TTL: gli expand del Discovery richiamano gli stessi
# artisti/tag a distanza di secondi (varianti, refresh UI) e il budget
# rate-limit di Last.fm e' limitato — 5 minuti coprono la sessione di expand
# senza servire dati stantii.
CACHE_TTL_SECONDS = 300
# Guardia dumb sulla dimensione: oltre la soglia si svuota tutto. Niente LRU:
# la cache e' piccola, ricostruirla costa una manciata di richieste.
CACHE_MAX_ENTRIES = 500

# {chiave: (scadenza monotonic, risposta)} — condivisa tra le istanze del client.
_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}

# Clock iniettabile: i test lo monkeypatchano per simulare lo scadere del TTL.
_now = time.monotonic


def clear_cache() -> None:
    """Svuota la cache (helper per i test)."""
    _cache.clear()


class LastFMError(Exception):
    pass


class LastFMNotConfigured(LastFMError):
    pass


def _as_list(value: Any) -> list[dict]:
    """Last.fm restituisce un dict singolo quando c'e' un solo elemento: normalizza a lista."""
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _match(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


class LastFMClient(SimilarityClient, ClosableHttpClient):
    name = "lastfm"

    def __init__(self, api_key: str, http: httpx.Client | None = None):
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=15, headers={"User-Agent": _USER_AGENT})

    # ---- HTTP -----------------------------------------------------------

    def _get(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {**params, "method": method, "api_key": self.api_key, "format": "json"}
        # Chiave: metodo + parametri completi (api_key inclusa). Le chiavi del
        # dict sono uniche, quindi sorted() non confronta mai i valori.
        cache_key = (method, tuple(sorted(query.items())))
        hit = _cache.get(cache_key)
        if hit is not None:
            expires_at, cached = hit
            if _now() < expires_at:
                return cached
            del _cache[cache_key]  # scaduta: rimuovi e ricadi sulla rete
        data = get_json(
            self.http, API, params=query, error_cls=LastFMError, name="Last.fm",
            rate_limit_message="Last.fm: rate limit (riprova piu' tardi).",
            text_preview=80, context=f" su {method}",
        )
        if isinstance(data, dict) and data.get("error"):
            raise LastFMError(f"Last.fm errore {data.get('error')}: {data.get('message')}")
        # Solo i successi finiscono in cache: gli errori (raise sopra) si
        # ritentano subito alla prossima chiamata.
        if len(_cache) >= CACHE_MAX_ENTRIES:
            _cache.clear()
        _cache[cache_key] = (_now() + CACHE_TTL_SECONDS, data)
        return data

    # ---- SimilarityClient ------------------------------------------------

    def similar_artists(self, artist: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if not artist:
            return []
        try:
            data = self._get("artist.getsimilar", {"artist": artist, "limit": limit, "autocorrect": 1})
        except LastFMError as exc:
            logger.warning("Last.fm similar_artists(%r) fallito: %s", artist, exc)
            return []
        items = _as_list((data.get("similarartists") or {}).get("artist"))
        return [
            {"name": it["name"], "match": _match(it.get("match"))}
            for it in items if it.get("name")
        ]

    def similar_tracks(self, artist: str, title: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if not artist or not title:
            return []
        try:
            data = self._get("track.getsimilar", {
                "artist": artist, "track": title, "limit": limit, "autocorrect": 1,
            })
        except LastFMError as exc:
            logger.warning("Last.fm similar_tracks(%r/%r) fallito: %s", artist, title, exc)
            return []
        out: list[dict[str, Any]] = []
        for it in _as_list((data.get("similartracks") or {}).get("track")):
            name = it.get("name")
            a = (it.get("artist") or {}).get("name")
            if name and a:
                out.append({"artist": a, "title": name, "match": _match(it.get("match"))})
        return out

    def artist_top_tracks(self, artist: str, *, limit: int = 10) -> list[dict[str, Any]]:
        if not artist:
            return []
        try:
            data = self._get("artist.gettoptracks", {"artist": artist, "limit": limit, "autocorrect": 1})
        except LastFMError as exc:
            logger.warning("Last.fm artist_top_tracks(%r) fallito: %s", artist, exc)
            return []
        out: list[dict[str, Any]] = []
        for it in _as_list((data.get("toptracks") or {}).get("track")):
            name = it.get("name")
            a = (it.get("artist") or {}).get("name")
            if name and a:
                out.append({"artist": a, "title": name})
        return out

    def top_tracks_by_tag(self, tag: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if not tag:
            return []
        try:
            data = self._get("tag.gettoptracks", {"tag": tag, "limit": limit})
        except LastFMError as exc:
            logger.warning("Last.fm top_tracks_by_tag(%r) fallito: %s", tag, exc)
            return []
        out: list[dict[str, Any]] = []
        for it in _as_list((data.get("tracks") or {}).get("track")):
            name = it.get("name")
            a = (it.get("artist") or {}).get("name")
            if name and a:
                out.append({"artist": a, "title": name})
        return out

# ---- factory ------------------------------------------------------------


def lastfm_configured() -> bool:
    return bool(settings.lastfm_api_key)


def get_lastfm_client() -> LastFMClient:
    if not settings.lastfm_api_key:
        raise LastFMNotConfigured(
            "LASTFM_API_KEY mancante in backend/.env: serve per il Discovery "
            "(chiave gratuita su last.fm/api)."
        )
    return LastFMClient(settings.lastfm_api_key)
