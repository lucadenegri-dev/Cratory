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
import re
from typing import Any

import httpx

from app.core.config import settings
from app.integrations import MusicFeatureProvider, SimilarityClient
from app.integrations._http import get_with_retries

logger = logging.getLogger(__name__)

API = "https://ws.audioscrobbler.com/2.0/"

# Tag Last.fm che esprimono un MOOD -> mood normalizzato del modello.
_MOOD_TAGS = {
    "dark": "dark", "melancholic": "melancholic", "melancholy": "melancholic", "sad": "melancholic",
    "moody": "dark", "chill": "chill", "chillout": "chill", "relaxing": "chill", "mellow": "chill",
    "calm": "chill", "dreamy": "dreamy", "ethereal": "dreamy", "atmospheric": "atmospheric",
    "uplifting": "uplifting", "happy": "happy", "feel good": "happy", "euphoric": "euphoric",
    "energetic": "energetic", "banger": "energetic", "aggressive": "aggressive", "dark techno": "dark",
    "groovy": "groovy", "funky": "groovy", "hypnotic": "hypnotic", "driving": "driving",
    "emotional": "emotional", "epic": "epic", "romantic": "romantic", "sexy": "sensual",
}
# Tag-spazzatura (collezioni/giudizi personali) da non usare come genere.
_TAG_JUNK = {
    "favorites", "favourite", "favourites", "favorite", "seen live", "loved", "spotify",
    "beautiful", "best", "awesome", "good", "amazing", "my music", "albums i own", "want to see",
    "love", "cool", "wtf", "overrated", "underrated", "masterpiece",
}
_DECADE_RE = re.compile(r"^\d{2,4}s$")  # "90s", "00s", "2010s"...


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


class LastFMClient(SimilarityClient):
    name = "lastfm"

    def __init__(self, api_key: str, http: httpx.Client | None = None):
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=15)

    # ---- HTTP -----------------------------------------------------------

    def _get(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {**params, "method": method, "api_key": self.api_key, "format": "json"}
        r = get_with_retries(self.http, API, params=query, error_cls=LastFMError)
        if r.status_code == 429:
            raise LastFMError("Last.fm: rate limit (riprova piu' tardi).")
        if r.status_code >= 400:
            raise LastFMError(f"Last.fm {r.status_code} su {method}: {r.text[:80]}")
        try:
            data = r.json()
        except ValueError as exc:
            raise LastFMError("Last.fm: risposta non JSON") from exc
        if isinstance(data, dict) and data.get("error"):
            raise LastFMError(f"Last.fm errore {data.get('error')}: {data.get('message')}")
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

    def top_tags(self, artist: str, title: str, *, limit: int = 8) -> list[str]:
        """Tag piu' votati di una traccia (per ricavare mood/genere). Ordine = popolarita'."""
        if not artist or not title:
            return []
        try:
            data = self._get("track.gettoptags", {"artist": artist, "track": title, "autocorrect": 1})
        except LastFMError as exc:
            logger.warning("Last.fm top_tags(%r/%r) fallito: %s", artist, title, exc)
            return []
        tags = _as_list((data.get("toptags") or {}).get("tag"))
        return [t["name"].strip() for t in tags if t.get("name")][:limit]

    def canonical_track(self, artist: str, title: str) -> dict[str, str] | None:
        """Title/artist canonici secondo Last.fm autocorrect."""
        if not artist or not title:
            return None
        try:
            data = self._get("track.getInfo", {"artist": artist, "track": title, "autocorrect": 1})
        except LastFMError as exc:
            logger.warning("Last.fm canonical_track(%r/%r) fallito: %s", artist, title, exc)
            return None
        track = data.get("track") or {}
        canonical_title = track.get("name")
        canonical_artist = (track.get("artist") or {}).get("name")
        if not canonical_title and not canonical_artist:
            return None
        out: dict[str, str] = {}
        if canonical_title:
            out["canonical_title"] = canonical_title
        if canonical_artist:
            out["canonical_artist"] = canonical_artist
        return out


# ---- provider feature (mood/genere da tag) ------------------------------


def _derive_mood(tags: list[str]) -> str | None:
    for t in tags:
        mood = _MOOD_TAGS.get(t.strip().lower())
        if mood:
            return mood
    return None


def _derive_genre(tags: list[str]) -> str | None:
    for t in tags:
        tl = t.strip().lower()
        if tl in _MOOD_TAGS or tl in _TAG_JUNK or _DECADE_RE.match(tl):
            continue
        return t.strip()
    return None


class LastFmTagProvider(MusicFeatureProvider):
    """Ricava mood e (in fallback) genere dai top tag Last.fm. NON fornisce BPM/key.

    I tag sono crowd-sourced: confidenza bassa. Nel ChainedFeatureProvider il genere
    di MusicBrainz (piu' autorevole) vince; Last.fm completa mood e i generi mancanti.
    """

    name = "lastfm"

    def __init__(self, client: "LastFMClient"):
        self.client = client

    def lookup(self, *, title, artist, isrc=None, duration_seconds=None, context=None):
        if not title or not artist:
            return None
        canonical = self.client.canonical_track(artist, title)
        tags = self.client.top_tags(artist, title)
        out: dict[str, Any] = {}
        if canonical:
            out.update(canonical)
        if tags:
            genre = _derive_genre(tags)
            mood = _derive_mood(tags)
            if genre:
                out["genre_primary"] = genre
            if mood:
                out["mood"] = mood
        if not out:
            return None
        out["confidence"] = 45 if tags else 35  # tag crowd-sourced: affidabilita' moderata
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
