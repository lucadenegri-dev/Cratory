"""Provider MusicBrainz: identità + metadati testuali (label, data, genere via tag).
NON fornisce BPM/key. Standalone (nessuna ABC): usato dalla catena text_providers.
Rate limit ~1 req/s (throttle interno) + breaker sulle connessioni troncate."""

import logging
import time
from difflib import SequenceMatcher
from typing import Any

import httpx

from app.integrations._http import get_with_retries, tls12_context

logger = logging.getLogger(__name__)
BASE = "https://musicbrainz.org/ws/2"


class MusicBrainzError(Exception):
    pass


class MusicBrainzProvider:
    name = "musicbrainz"
    _MIN_INTERVAL = 1.1
    _BREAKER_AFTER = 2

    def __init__(self, user_agent: str, http: httpx.Client | None = None):
        self.user_agent = user_agent
        self.http = http or httpx.Client(
            timeout=15, headers={"User-Agent": user_agent}, verify=tls12_context())
        self._last_request = 0.0
        self._conn_failures = 0
        self._suspended = False

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        wait = self._MIN_INTERVAL - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
        try:
            r = get_with_retries(self.http, f"{BASE}{path}",
                                 params={**params, "fmt": "json"}, error_cls=MusicBrainzError)
        except MusicBrainzError:
            self._conn_failures += 1
            if self._conn_failures >= self._BREAKER_AFTER and not self._suspended:
                self._suspended = True
                logger.warning("MusicBrainz: connessioni troncate — provider sospeso per il run.")
            raise
        self._conn_failures = 0
        if r.status_code == 503:
            raise MusicBrainzError("MusicBrainz: rate limit.")
        if r.status_code >= 400:
            raise MusicBrainzError(f"MusicBrainz {r.status_code}: {r.text[:160]}")
        try:
            return r.json()
        except ValueError as exc:
            raise MusicBrainzError("MusicBrainz: risposta non JSON") from exc

    def lookup(self, *, title, artist, isrc=None, mbid=None):
        if self._suspended:
            return None
        if mbid:
            try:
                rec = self._get(f"/recording/{mbid}", {"inc": "releases+tags+artist-credits+release-groups"})
                parsed = self._parse_recording(rec, isrc=isrc, exact=True) if rec else None
                if parsed:
                    return parsed
            except MusicBrainzError as exc:
                logger.warning("MusicBrainz recording %s fallito: %s", mbid, exc)
        rec, exact = None, False
        if isrc:
            try:
                data = self._get(f"/isrc/{isrc}", {"inc": "releases+tags+artist-credits+release-groups"})
                recs = data.get("recordings") or []
                rec, exact = (recs[0] if recs else None), bool(recs)
            except MusicBrainzError as exc:
                logger.warning("MusicBrainz ISRC %s fallito: %s", isrc, exc)
        if rec is None and title:
            query = f'recording:"{title}"' + (f' AND artist:"{artist}"' if artist else "")
            try:
                data = self._get("/recording", {"query": query, "limit": 5, "inc": "releases+tags+artist-credits+release-groups"})
            except MusicBrainzError as exc:
                logger.warning("MusicBrainz search '%s' fallito: %s", title, exc)
                return None
            rec = self._best_recording(data.get("recordings") or [], title, artist)
        return self._parse_recording(rec, isrc=isrc, exact=exact) if rec else None

    @staticmethod
    def _best_recording(recordings, title, artist):
        title_l, artist_l = (title or "").lower(), (artist or "").lower()

        def score(rec):
            s = float(rec.get("score") or 0)
            s += SequenceMatcher(None, title_l, (rec.get("title") or "").lower()).ratio() * 20
            credit = " ".join((c.get("name") or (c.get("artist") or {}).get("name") or "")
                              for c in (rec.get("artist-credit") or [])).lower()
            if artist_l and credit:
                s += SequenceMatcher(None, artist_l, credit).ratio() * 20
            return s

        return max(recordings, key=score, default=None)

    @staticmethod
    def _is_studio_album(rel):
        """True se la release è un album in studio (non singolo/EP, non
        compilation/DJ-mix/remix). È da preferire come fonte di album/label/anno:
        una registrazione vive su molte release e MB le elenca in ordine
        arbitrario (a volte il singolo prima dell'album)."""
        rg = rel.get("release-group") or {}
        if (rg.get("primary-type") or "") != "Album":
            return False
        secondary = {s.lower() for s in (rg.get("secondary-types") or [])}
        return not (secondary & {"compilation", "dj-mix", "remix", "live"})

    @staticmethod
    def _release_rank(rel):
        # 0 = album in studio, 1 = altra release non-VA-comp, 2 = VA-comp.
        if MusicBrainzProvider._is_va_comp(rel):
            return 2
        return 0 if MusicBrainzProvider._is_studio_album(rel) else 1

    @staticmethod
    def _prioritized_releases(rec):
        """Release ordinate per preferenza (studio album prima). Sort stabile:
        a parità di rango resta l'ordine di MB."""
        return sorted(rec.get("releases") or [],
                      key=MusicBrainzProvider._release_rank)

    @staticmethod
    def _release_date(rec):
        for rel in MusicBrainzProvider._prioritized_releases(rec):
            date = rel.get("date") or (rel.get("release-group") or {}).get("first-release-date")
            if date:
                return date
        return None

    @staticmethod
    def _is_va_comp(rel):
        """True se la release è una compilation Various Artists o un DJ-mix.
        Una traccia che compare solo su una compilation-mix non ha lì il suo
        album/label 'reale' (es. 'Progressive'): quella release va scartata come
        fonte per album e label. Richiede inc=artist-credits+release-groups."""
        credit = " ".join(
            (c.get("name") or (c.get("artist") or {}).get("name") or "")
            for c in (rel.get("artist-credit") or [])
        ).strip().lower()
        if credit == "various artists":
            return True
        secondary = (rel.get("release-group") or {}).get("secondary-types") or []
        return any(s in ("Compilation", "DJ-mix") for s in secondary)

    @staticmethod
    def _label(rec):
        for rel in MusicBrainzProvider._prioritized_releases(rec):
            if MusicBrainzProvider._is_va_comp(rel):
                continue
            for li in rel.get("label-info") or []:
                name = (li.get("label") or {}).get("name")
                if name:
                    return name
        return None

    @staticmethod
    def _album(rec):
        for rel in MusicBrainzProvider._prioritized_releases(rec):
            if MusicBrainzProvider._is_va_comp(rel):
                continue
            title = rel.get("title")
            if title:
                return title
        return None

    @staticmethod
    def _top_tag(rec):
        tags = [t for t in (rec.get("tags") or []) if t.get("name")]
        return max(tags, key=lambda t: t.get("count", 0))["name"] if tags else None

    @staticmethod
    def _all_tags(rec):
        """Tutti i tag con nome, ordinati per popolarità decrescente."""
        tags = [t for t in (rec.get("tags") or []) if t.get("name")]
        return [t["name"] for t in
                sorted(tags, key=lambda t: t.get("count", 0), reverse=True)]

    @staticmethod
    def _release_mbids(rec):
        return [rel["id"] for rel in MusicBrainzProvider._prioritized_releases(rec)
                if rel.get("id")]

    @staticmethod
    def _artist_credit(rec):
        for credit in rec.get("artist-credit") or []:
            name = credit.get("name") or (credit.get("artist") or {}).get("name")
            if name:
                return name
        return None

    def _parse_recording(self, rec, *, isrc, exact):
        out: dict[str, Any] = {}
        if rec.get("id"):
            out["mbid"] = rec["id"]
        if rec.get("title"):
            out["canonical_title"] = rec["title"]
        if artist := self._artist_credit(rec):
            out["canonical_artist"] = artist
        if label := self._label(rec):
            out["label"] = label
        if album := self._album(rec):
            out["canonical_album"] = album
        if rd := self._release_date(rec):
            out["release_date"] = rd
        if genre := self._top_tag(rec):
            out["genre_primary"] = genre
        if cands := self._all_tags(rec):
            out["genre_candidates"] = cands
        if isrc:
            out["isrc"] = isrc
        if rels := self._release_mbids(rec):
            out["release_mbids"] = rels
        if not out:
            return None
        out["confidence"] = 95 if exact else min(90, int(rec.get("score") or 60))
        return out
