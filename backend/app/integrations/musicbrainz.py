"""Provider di identificazione/metadati: MusicBrainz.

Copre cio' che GetSongBPM non da': identita' via ISRC, label, data di release,
genere (dai tag). NON fornisce BPM/key. Pensato per stare in coda a GetSongBPM
in `ChainedFeatureProvider`. Dietro l'ABC `MusicFeatureProvider`.

MusicBrainz richiede uno User-Agent identificativo e applica un rate limit di
~1 richiesta/secondo: il throttling reale e' responsabilita' del chiamante
(l'enrichment processa una traccia alla volta).
"""

import logging
import time
from difflib import SequenceMatcher
from typing import Any

import httpx

from app.integrations import MusicFeatureProvider
from app.integrations._http import get_with_retries, tls12_context
from app.integrations.getsongbpm import FeatureProviderError

logger = logging.getLogger(__name__)

BASE = "https://musicbrainz.org/ws/2"


class MusicBrainzProvider(MusicFeatureProvider):
    name = "musicbrainz"
    _MIN_INTERVAL = 1.1  # MusicBrainz: max ~1 richiesta/secondo, altrimenti 503/ban

    def __init__(self, user_agent: str, http: httpx.Client | None = None):
        self.user_agent = user_agent
        # verify=tls12_context(): la handshake TLS 1.3 verso musicbrainz.org viene
        # interrotta da middlebox di rete (UNEXPECTED_EOF). Su TLS 1.2 funziona.
        self.http = http or httpx.Client(
            timeout=15, headers={"User-Agent": user_agent}, verify=tls12_context(),
        )
        self._last_request = 0.0

    # ---- HTTP -----------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        # Throttle: rispetta il rate limit di MusicBrainz (~1 req/s).
        wait = self._MIN_INTERVAL - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
        r = get_with_retries(
            self.http, f"{BASE}{path}",
            params={**params, "fmt": "json"},
            error_cls=FeatureProviderError,
        )
        if r.status_code == 503:
            raise FeatureProviderError("MusicBrainz: rate limit (riprova piu' tardi).")
        if r.status_code >= 400:
            raise FeatureProviderError(f"MusicBrainz {r.status_code}: {r.text[:160]}")
        try:
            return r.json()
        except ValueError as exc:
            raise FeatureProviderError("MusicBrainz: risposta non JSON") from exc

    # ---- MusicFeatureProvider -------------------------------------------

    def lookup(self, *, title, artist, isrc=None, duration_seconds=None, context=None):
        rec: dict | None = None
        exact = False
        if isrc:
            try:
                data = self._get(f"/isrc/{isrc}", {"inc": "releases+tags"})
                recs = data.get("recordings") or []
                rec, exact = (recs[0] if recs else None), bool(recs)
            except FeatureProviderError as exc:
                logger.warning("MusicBrainz ISRC %s fallito: %s", isrc, exc)
        if rec is None and title:
            query = f'recording:"{title}"' + (f' AND artist:"{artist}"' if artist else "")
            try:
                data = self._get("/recording", {"query": query, "limit": 5, "inc": "releases+tags"})
            except FeatureProviderError as exc:
                logger.warning("MusicBrainz search '%s' fallito: %s", title, exc)
                return None
            rec = self._best_recording(data.get("recordings") or [], title, artist)
        return self._parse_recording(rec, isrc=isrc, exact=exact) if rec else None

    # ---- parsing (testabile senza rete) ---------------------------------

    @staticmethod
    def _best_recording(recordings: list[dict], title: str | None, artist: str | None) -> dict | None:
        title_l = (title or "").lower()
        artist_l = (artist or "").lower()

        def score(rec: dict) -> float:
            s = float(rec.get("score") or 0)  # 0-100 fornito da MusicBrainz
            s += SequenceMatcher(None, title_l, (rec.get("title") or "").lower()).ratio() * 20
            credit = " ".join(
                (c.get("name") or (c.get("artist") or {}).get("name") or "")
                for c in (rec.get("artist-credit") or [])
            ).lower()
            if artist_l and credit:
                s += SequenceMatcher(None, artist_l, credit).ratio() * 20
            return s

        return max(recordings, key=score, default=None)

    @staticmethod
    def _release_date(rec: dict) -> str | None:
        for rel in rec.get("releases") or []:
            date = rel.get("date") or (rel.get("release-group") or {}).get("first-release-date")
            if date:
                return date
        return None

    @staticmethod
    def _label(rec: dict) -> str | None:
        for rel in rec.get("releases") or []:
            for li in rel.get("label-info") or []:
                name = (li.get("label") or {}).get("name")
                if name:
                    return name
        return None

    @staticmethod
    def _top_tag(rec: dict) -> str | None:
        tags = [t for t in (rec.get("tags") or []) if t.get("name")]
        if not tags:
            return None
        return max(tags, key=lambda t: t.get("count", 0))["name"]

    @staticmethod
    def _artist_credit(rec: dict) -> str | None:
        for credit in rec.get("artist-credit") or []:
            name = credit.get("name") or (credit.get("artist") or {}).get("name")
            if name:
                return name
        return None

    def _parse_recording(self, rec: dict, *, isrc: str | None, exact: bool) -> dict[str, Any] | None:
        out: dict[str, Any] = {}
        # L'MBID (Recording) e' la chiave che apre l'analisi audio di AcousticBrainz:
        # lo pubblichiamo nel `context` della catena anche se non e' un campo del modello.
        if rec.get("id"):
            out["mbid"] = rec["id"]
        if rec.get("title"):
            out["canonical_title"] = rec["title"]
        if artist := self._artist_credit(rec):
            out["canonical_artist"] = artist
        if (label := self._label(rec)):
            out["label"] = label
        if (rd := self._release_date(rec)):
            out["release_date"] = rd
        if (genre := self._top_tag(rec)):
            out["genre_primary"] = genre
        if isrc:
            out["isrc"] = isrc
        if not out:
            return None
        # ISRC = identita' certa; altrimenti usa lo score di ricerca MusicBrainz.
        out["confidence"] = 95 if exact else min(90, int(rec.get("score") or 60))
        return out
