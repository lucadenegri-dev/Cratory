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
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
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
_MAX_LOOKUP_CANDIDATES = 6
_VERSION_TERMS = (
    "radio edit", "extended mix", "original mix", "club mix", "edit", "mix",
    "remix", "remaster", "remastered", "version", "vip", "dub", "instrumental",
    "mono", "stereo", "live", "demo", "rework", "bootleg",
)
_SEP_VERSION_RE = re.compile(
    r"\s+[-–—]\s+.*\b(" + "|".join(re.escape(t) for t in _VERSION_TERMS) + r")\b.*$",
    re.IGNORECASE,
)
_PAREN_RE = re.compile(r"\s*[\(\[].*?[\)\]]")
_FEAT_RE = re.compile(r"\s+(feat\.?|ft\.?|featuring|with)\s+.+$", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class LookupCandidate:
    title: str
    artist: str | None
    source: str


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
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not title:
            return None
        fallback: dict[str, Any] | None = None
        attempts = 0
        for candidate in self._lookup_candidates(title=title, artist=artist):
            attempts += 1
            lookup_str = f"song:{candidate.title}" + (
                f" artist:{candidate.artist}" if candidate.artist else ""
            )
            try:
                data = self._get("/search/", {"type": "both", "lookup": lookup_str})
            except FeatureProviderError as exc:
                logger.warning("GetSongBPM lookup fallito (%r): %s", lookup_str, exc)
                return fallback
            results = data.get("search")
            if not isinstance(results, list) or not results:
                continue
            best = self._best_match(
                results, candidate.title, candidate.artist, duration_seconds=duration_seconds
            )
            parsed = self._parse_song(best, artist=candidate.artist, title=candidate.title) if best else None
            if not parsed:
                continue
            parsed["lookup_source"] = candidate.source
            parsed["lookup_title"] = candidate.title
            if candidate.artist:
                parsed["lookup_artist"] = candidate.artist
            parsed["lookup_attempts"] = attempts
            if "bpm" in parsed or "camelot_key" in parsed:
                return parsed
            fallback = fallback or parsed
        return fallback

    # ---- parsing (testabile senza rete) ---------------------------------

    @staticmethod
    def _norm_text(value: str | None) -> str:
        value = (value or "").lower().replace("&", " and ")
        value = re.sub(r"[^\w\s]", " ", value)
        return _SPACE_RE.sub(" ", value).strip()

    @classmethod
    def _clean_title(cls, title: str | None) -> str:
        out = (title or "").strip()
        out = _SEP_VERSION_RE.sub("", out)
        out = _FEAT_RE.sub("", out)

        def keep_or_drop(match: re.Match[str]) -> str:
            inner = match.group(0).strip(" ()[]").lower()
            return "" if any(term in inner for term in _VERSION_TERMS) else match.group(0)

        out = _PAREN_RE.sub(keep_or_drop, out)
        return _SPACE_RE.sub(" ", out).strip()

    @staticmethod
    def _primary_artist(artist: str | None) -> str | None:
        if not artist:
            return None
        parts = re.split(r"\s*(?:,|;|\sx\s|\s&\s|\sand\s|\sfeat\.?\s|\sft\.?\s|\sfeaturing\s)\s*", artist)
        primary = next((p.strip() for p in parts if p.strip()), "")
        return primary or artist.strip() or None

    @classmethod
    def _lookup_candidates(cls, *, title: str, artist: str | None) -> list[LookupCandidate]:
        clean_title = cls._clean_title(title)
        primary_artist = cls._primary_artist(artist)
        raw_artist = artist.strip() if artist else None
        pairs = [
            LookupCandidate(title.strip(), raw_artist, "original"),
            LookupCandidate(clean_title, raw_artist, "clean_title"),
            LookupCandidate(clean_title, primary_artist, "clean_title_primary_artist"),
            LookupCandidate(title.strip(), primary_artist, "primary_artist"),
            LookupCandidate(clean_title, None, "clean_title_no_artist"),
        ]
        seen: set[tuple[str, str | None]] = set()
        out: list[LookupCandidate] = []
        for cand in pairs:
            key = (cls._norm_text(cand.title), cls._norm_text(cand.artist) if cand.artist else None)
            if not key[0] or key in seen:
                continue
            seen.add(key)
            out.append(cand)
            if len(out) >= _MAX_LOOKUP_CANDIDATES:
                break
        return out

    @staticmethod
    def _duration_seconds(song: dict) -> int | None:
        for key in ("duration", "duration_seconds", "length"):
            value = song.get(key)
            if value in (None, ""):
                continue
            try:
                seconds = int(float(value))
                return seconds // 1000 if seconds > 10_000 else seconds
            except (TypeError, ValueError):
                pass
        return None

    @classmethod
    def _best_match(
        cls,
        results: list[dict],
        title: str | None,
        artist: str | None,
        duration_seconds: int | None = None,
    ) -> dict | None:
        artist_l = cls._norm_text(artist)
        title_l = cls._norm_text(cls._clean_title(title))

        def score(item: dict) -> float:
            a = cls._norm_text((item.get("artist") or {}).get("name"))
            t = cls._norm_text(cls._clean_title(item.get("title")))
            s = 0.0
            if title_l and t:
                title_ratio = SequenceMatcher(None, title_l, t).ratio()
                s += title_ratio * 65
                if title_l in t or t in title_l:
                    s += 10
            if artist_l and a:
                artist_ratio = SequenceMatcher(None, artist_l, a).ratio()
                s += artist_ratio * 30
                if artist_l in a or a in artist_l:
                    s += 8
            if duration_seconds:
                item_duration = cls._duration_seconds(item)
                if item_duration:
                    diff = abs(item_duration - duration_seconds)
                    if diff <= 3:
                        s += 8
                    elif diff <= 10:
                        s += 4
                    elif diff > 45:
                        s -= 10
            if item.get("tempo") not in (None, ""):
                s += 3
            if item.get("key_of"):
                s += 3
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

    def _parse_song(self, song: dict, *, artist: str | None, title: str | None = None) -> dict[str, Any] | None:
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
        out["confidence"] = self._confidence(song, artist, title=title)
        return out

    @classmethod
    def _confidence(cls, song: dict, artist: str | None, title: str | None = None) -> int:
        a = cls._norm_text((song.get("artist") or {}).get("name"))
        al = cls._norm_text(artist)
        t = cls._norm_text(cls._clean_title(song.get("title")))
        tl = cls._norm_text(cls._clean_title(title))
        artist_score = SequenceMatcher(None, al, a).ratio() if al and a else 0.0
        title_score = SequenceMatcher(None, tl, t).ratio() if tl and t else 0.0
        if not tl and artist_score >= 0.85:
            return 80
        if artist_score >= 0.85 and (not tl or title_score >= 0.85):
            return 85
        if al and a and (al in a or a in al):
            return 80
        if title_score >= 0.8:
            return 65
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

    def lookup(self, *, title, artist, isrc=None, duration_seconds=None, context=None):
        merged: dict[str, Any] = dict(context) if context else {}
        confidences: list[int] = []
        getsongbpm: list[MusicFeatureProvider] = []

        def merge(data: dict[str, Any] | None) -> None:
            if not data:
                return
            for k, v in data.items():
                if k == "confidence":
                    if v is not None:
                        confidences.append(int(v))
                elif v is not None and k not in merged:
                    merged[k] = v

        # `merged` viene passato come context: un provider vede i campi gia' raccolti
        # dai precedenti (es. AcousticBrainz legge l'`mbid` di MusicBrainz).
        for p in self.providers:
            if getattr(p, "name", "") == "getsongbpm":
                getsongbpm.append(p)
            try:
                data = p.lookup(
                    title=title, artist=artist, isrc=isrc,
                    duration_seconds=duration_seconds, context=merged,
                )
            except FeatureProviderError as exc:
                logger.warning("Provider %s fallito nella catena: %s", getattr(p, "name", "?"), exc)
                continue
            merge(data)
        has_core = "bpm" in merged or "camelot_key" in merged
        canonical_title = merged.get("canonical_title")
        canonical_artist = merged.get("canonical_artist")
        if not has_core and getsongbpm and (
            canonical_title and canonical_title != title or canonical_artist and canonical_artist != artist
        ):
            for p in getsongbpm:
                try:
                    data = p.lookup(
                        title=canonical_title or title,
                        artist=canonical_artist or artist,
                        isrc=isrc,
                        duration_seconds=duration_seconds,
                        context=merged,
                    )
                except FeatureProviderError as exc:
                    logger.warning("Retry canonicale %s fallito: %s", getattr(p, "name", "?"), exc)
                    continue
                if data:
                    data = {**data, "canonical_retry": True}
                merge(data)
                if "bpm" in merged or "camelot_key" in merged:
                    break
        if not merged:
            return None
        merged["confidence"] = max(confidences) if confidences else 0
        return merged


# ---- factory ------------------------------------------------------------


def _configured_names() -> list[str]:
    # Ordine = ordine nella catena (vedi get_feature_provider).
    names: list[str] = []
    if settings.deezer_enabled:
        names.append("deezer")
    if settings.musicbrainz_user_agent:
        names.append("musicbrainz")
        # AcousticBrainz e' indicizzato per MBID: ha senso solo con MusicBrainz attivo.
        if settings.acousticbrainz_enabled:
            names.append("acousticbrainz")
    if settings.getsongbpm_api_key:
        names.append("getsongbpm")
    if settings.lastfm_api_key:
        names.append("lastfm")
    return names


def feature_provider_configured() -> bool:
    return bool(_configured_names())


def configured_provider_name() -> str | None:
    names = _configured_names()
    return " + ".join(names) if names else None


def get_feature_provider() -> MusicFeatureProvider:
    # Ordine della catena = priorita' (il primo che riempie un campo vince), pensato
    # per privilegiare le fonti basate su IDENTITA' (ISRC/MBID) rispetto al fuzzy:
    #   Deezer (ISRC->bpm) -> MusicBrainz (ISRC->mbid/label/genere/canonical)
    #   -> AcousticBrainz (mbid->bpm/key/mood/dance/voce) -> GetSongBPM (fuzzy, fallback)
    #   -> Last.fm (mood/genere, fallback).
    providers: list[MusicFeatureProvider] = []
    if settings.deezer_enabled:
        # Deezer: BPM via ISRC, senza API key. Match esatto = identita' certa.
        from app.integrations.deezer import DeezerProvider
        providers.append(DeezerProvider())
    if settings.musicbrainz_user_agent:
        # import locale: evita di legare questo modulo a musicbrainz se non configurato
        from app.integrations.musicbrainz import MusicBrainzProvider
        providers.append(MusicBrainzProvider(settings.musicbrainz_user_agent))
        if settings.acousticbrainz_enabled:
            # AcousticBrainz: analisi audio reale via MBID (lo prende dal context della
            # catena, quindi DEVE stare dopo MusicBrainz). Senza API key.
            from app.integrations.acousticbrainz import AcousticBrainzProvider
            providers.append(AcousticBrainzProvider())
    if settings.getsongbpm_api_key:
        providers.append(GetSongBPMProvider(settings.getsongbpm_api_key))
    if settings.lastfm_api_key:
        # Last.fm: mood + genere (fallback) dai tag.
        from app.integrations.lastfm import LastFMClient, LastFmTagProvider
        providers.append(LastFmTagProvider(LastFMClient(settings.lastfm_api_key)))
    if not providers:
        raise FeatureProviderNotConfigured(
            "Nessun provider di feature musicali configurato: abilita DEEZER_ENABLED "
            "(BPM via ISRC, gratis e senza chiave) e/o imposta GETSONGBPM_API_KEY (BPM/key) "
            "o MUSICBRAINZ_USER_AGENT (label/release/genere + AcousticBrainz) in backend/.env."
        )
    return providers[0] if len(providers) == 1 else ChainedFeatureProvider(providers)
