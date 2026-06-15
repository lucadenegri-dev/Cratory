"""Provider di feature musicali concreto: GetSongBPM (getsongbpm.com).

Fornisce BPM, tonalita' e danceability a partire da titolo + artista. NON e' una
fonte di identita' (niente ISRC): il match e' su artista/titolo, con una confidenza
stimata. La tonalita' viene normalizzata in Camelot (mai inventata: se non
interpretabile resta vuota). Dietro l'ABC `MusicFeatureProvider`.

Regola del progetto: i dati esterni completano i campi vuoti; BPM/key gia'
presenti (es. da Rekordbox) non vengono mai sovrascritti (lo garantisce
services/feature_enrichment.apply_features).
"""

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.integrations import MusicFeatureProvider
from app.integrations._http import get_with_retries
from app.services.camelot import parse_camelot, pitch_to_camelot

logger = logging.getLogger(__name__)

BASE = "https://api.getsong.co"
# Alcuni server (incl. getsong.co) rispondono in modo anomalo senza uno User-Agent
# esplicito: lo impostiamo per ridurre i reset di connessione/TLS.
_USER_AGENT = "DJAssistant/0.1 (+http://localhost)"


class FeatureProviderError(Exception):
    pass


class FeatureProviderNotConfigured(FeatureProviderError):
    pass


class GetSongBPMProvider(MusicFeatureProvider):
    name = "getsongbpm"

    def __init__(self, api_key: str, http: httpx.Client | None = None):
        self.api_key = api_key
        self.http = http or httpx.Client(
            timeout=15, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        )

    # ---- HTTP -----------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        r = get_with_retries(
            self.http, f"{BASE}{path}",
            params={**params, "api_key": self.api_key},
            error_cls=FeatureProviderError,
        )
        if r.status_code == 429:
            raise FeatureProviderError("GetSongBPM: rate limit (riprova piu' tardi).")
        if r.status_code >= 400:
            raise FeatureProviderError(f"GetSongBPM {r.status_code}: {r.text[:160]}")
        try:
            return r.json()
        except ValueError as exc:
            raise FeatureProviderError("GetSongBPM: risposta non JSON") from exc

    # ---- MusicFeatureProvider -------------------------------------------

    def lookup(
        self, *, title: str | None, artist: str | None,
        isrc: str | None = None, duration_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        if not title:
            return None
        lookup_str = f"song:{title}" + (f" artist:{artist}" if artist else "")
        try:
            data = self._get("/search/", {"type": "both", "lookup": lookup_str})
        except FeatureProviderError as exc:
            logger.warning("GetSongBPM lookup fallito (%r): %s", title, exc)
            return None
        results = data.get("search")
        if not isinstance(results, list) or not results:
            return None
        best = self._best_match(results, title, artist)
        return self._parse_song(best, artist=artist) if best else None

    # ---- parsing (testabile senza rete) ---------------------------------

    @staticmethod
    def _best_match(results: list[dict], title: str | None, artist: str | None) -> dict | None:
        artist_l = (artist or "").lower()
        title_l = (title or "").lower()

        def score(item: dict) -> int:
            a = ((item.get("artist") or {}).get("name") or "").lower()
            t = (item.get("title") or "").lower()
            s = 0
            if artist_l and a and (artist_l in a or a in artist_l):
                s += 2
            if title_l and t and title_l in t:
                s += 1
            return s

        return max(results, key=score, default=None)

    @staticmethod
    def _camelot(song: dict) -> str | None:
        raw = song.get("key_of")
        if not raw:
            return None
        raw = str(raw).strip()
        if parse_camelot(raw):  # gia' Camelot (es. "8A")
            return raw.upper()
        return pitch_to_camelot(raw)  # key musicale (es. "Am", "C#") -> Camelot

    def _parse_song(self, song: dict, *, artist: str | None) -> dict[str, Any] | None:
        out: dict[str, Any] = {}
        tempo = song.get("tempo")
        if tempo not in (None, ""):
            try:
                out["bpm"] = float(tempo)
            except (TypeError, ValueError):
                pass
        camelot = self._camelot(song)
        if camelot:
            out["camelot_key"] = camelot
        dance = song.get("danceability")
        if dance not in (None, ""):
            try:
                out["danceability"] = max(0, min(100, int(float(dance))))
            except (TypeError, ValueError):
                pass
        if not out:
            return None  # nessun dato utile: trattalo come "non trovato"
        out["confidence"] = self._confidence(song, artist)
        return out

    @staticmethod
    def _confidence(song: dict, artist: str | None) -> int:
        a = ((song.get("artist") or {}).get("name") or "").lower()
        al = (artist or "").lower()
        if al and a and (al in a or a in al):
            return 80
        return 55


class ChainedFeatureProvider(MusicFeatureProvider):
    """Combina piu' provider: ognuno completa i campi che l'altro non copre.

    Ordine = priorita': il primo provider che fornisce un campo vince. Tipico:
    GetSongBPM (bpm/key) -> MusicBrainz (label/release/genere). La confidenza
    risultante e' la massima tra i contributori.
    """

    name = "chain"

    def __init__(self, providers: list[MusicFeatureProvider]):
        self.providers = providers

    def lookup(self, *, title, artist, isrc=None, duration_seconds=None):
        merged: dict[str, Any] = {}
        confidences: list[int] = []
        for p in self.providers:
            try:
                data = p.lookup(title=title, artist=artist, isrc=isrc, duration_seconds=duration_seconds)
            except FeatureProviderError as exc:
                logger.warning("Provider %s fallito nella catena: %s", getattr(p, "name", "?"), exc)
                continue
            if not data:
                continue
            for k, v in data.items():
                if k == "confidence":
                    if v is not None:
                        confidences.append(int(v))
                elif v is not None and k not in merged:
                    merged[k] = v
        if not merged:
            return None
        merged["confidence"] = max(confidences) if confidences else 0
        return merged


# ---- factory ------------------------------------------------------------


def _configured_names() -> list[str]:
    names: list[str] = []
    if settings.getsongbpm_api_key:
        names.append("getsongbpm")
    if settings.musicbrainz_user_agent:
        names.append("musicbrainz")
    if settings.lastfm_api_key:
        names.append("lastfm")
    return names


def feature_provider_configured() -> bool:
    return bool(_configured_names())


def configured_provider_name() -> str | None:
    names = _configured_names()
    return " + ".join(names) if names else None


def get_feature_provider() -> MusicFeatureProvider:
    providers: list[MusicFeatureProvider] = []
    if settings.getsongbpm_api_key:
        providers.append(GetSongBPMProvider(settings.getsongbpm_api_key))
    if settings.musicbrainz_user_agent:
        # import locale: evita di legare questo modulo a musicbrainz se non configurato
        from app.integrations.musicbrainz import MusicBrainzProvider
        providers.append(MusicBrainzProvider(settings.musicbrainz_user_agent))
    if settings.lastfm_api_key:
        # Last.fm: mood + genere (fallback) dai tag. BPM/key restano da GetSongBPM.
        from app.integrations.lastfm import LastFMClient, LastFmTagProvider
        providers.append(LastFmTagProvider(LastFMClient(settings.lastfm_api_key)))
    if not providers:
        raise FeatureProviderNotConfigured(
            "Nessun provider di feature musicali configurato: imposta GETSONGBPM_API_KEY "
            "(BPM/key) e/o MUSICBRAINZ_USER_AGENT (label/release/genere) in backend/.env."
        )
    return providers[0] if len(providers) == 1 else ChainedFeatureProvider(providers)
