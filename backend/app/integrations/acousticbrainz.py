"""Provider di feature musicali: AcousticBrainz. MBID -> BPM, key, mood, danceability, voce.

AcousticBrainz e' un archivio gratuito di analisi audio (Essentia) indicizzato per
MusicBrainz Recording MBID. Il progetto ha chiuso le nuove submission nel 2022, ma
l'API e i dati restano accessibili: copre bene il catalogo storico/popolare, NON le
uscite recentissime. Dove c'e', e' la fonte piu' ricca disponibile gratis perche'
e' analisi audio REALE (non crowd-sourced come i tag): BPM, tonalita' (-> Camelot),
danceability, mood, voce/strumentale (-> vocalness).

Richiede l'MBID, che risolve MusicBrainz: in `ChainedFeatureProvider` va DOPO
`MusicBrainzProvider` e legge l'MBID dal `context` accumulato. Senza MBID (nessun
match MusicBrainz, o MusicBrainz non configurato) restituisce None.

Endpoint per-MBID (ultima submission):
- /api/v1/{mbid}/low-level  -> rhythm.bpm, tonal.key_key + tonal.key_scale
- /api/v1/{mbid}/high-level -> danceability, mood_*, voice_instrumental

httpx iniettabile -> test senza rete.
"""

import logging
from typing import Any

import httpx

from app.integrations import MusicFeatureProvider
from app.integrations._http import get_with_retries
from app.integrations.getsongbpm import FeatureProviderError
from app.services.camelot import pitch_to_camelot

logger = logging.getLogger(__name__)

BASE = "https://acousticbrainz.org/api/v1"
_USER_AGENT = "DJAssistant/0.1 (+http://localhost)"

# Classificatori mood_* di AcousticBrainz -> mood normalizzato del modello
# (coerente col vocabolario di integrations/lastfm.py). La tupla e' (classe "attiva"
# nella risposta, mood normalizzato).
_MOOD_MAP: dict[str, tuple[str, str]] = {
    "mood_happy": ("happy", "happy"),
    "mood_sad": ("sad", "melancholic"),
    "mood_aggressive": ("aggressive", "aggressive"),
    "mood_relaxed": ("relaxed", "chill"),
    "mood_party": ("party", "energetic"),
}
_MOOD_THRESHOLD = 0.6  # serve una probabilita' netta verso il lato "attivo"


class AcousticBrainzProvider(MusicFeatureProvider):
    name = "acousticbrainz"

    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(
            timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        )

    # ---- HTTP -----------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any] | None:
        r = get_with_retries(self.http, f"{BASE}{path}", error_cls=FeatureProviderError)
        if r.status_code == 404:
            return None  # MBID assente dal dataset: normale, non e' un errore
        if r.status_code == 429:
            raise FeatureProviderError("AcousticBrainz: rate limit (riprova piu' tardi).")
        if r.status_code >= 400:
            raise FeatureProviderError(f"AcousticBrainz {r.status_code}: {r.text[:160]}")
        try:
            return r.json()
        except ValueError as exc:
            raise FeatureProviderError("AcousticBrainz: risposta non JSON") from exc

    # ---- MusicFeatureProvider -------------------------------------------

    def lookup(self, *, title, artist, isrc=None, duration_seconds=None, context=None):
        mbid = (context or {}).get("mbid")
        if not mbid:
            return None  # senza MBID (da MusicBrainz) non c'e' nulla da interrogare
        out: dict[str, Any] = {}
        try:
            low = self._get(f"/{mbid}/low-level")
        except FeatureProviderError as exc:
            logger.warning("AcousticBrainz low-level %s fallito: %s", mbid, exc)
            low = None
        if low:
            out.update(self._parse_low_level(low))
        try:
            high = self._get(f"/{mbid}/high-level")
        except FeatureProviderError as exc:
            logger.warning("AcousticBrainz high-level %s fallito: %s", mbid, exc)
            high = None
        if high:
            out.update(self._parse_high_level(high))
        if not out:
            return None
        # Analisi audio reale; l'identita' dipende dall'MBID risolto da MusicBrainz.
        out["confidence"] = 80
        return out

    # ---- parsing (testabile senza rete) ---------------------------------

    @classmethod
    def _parse_low_level(cls, data: dict) -> dict[str, Any]:
        doc = cls._unwrap(data)
        out: dict[str, Any] = {}
        bpm = (doc.get("rhythm") or {}).get("bpm")
        try:
            if bpm not in (None, "") and float(bpm) > 0:
                out["bpm"] = round(float(bpm), 1)
        except (TypeError, ValueError):
            pass
        tonal = doc.get("tonal") or {}
        camelot = cls._camelot(tonal.get("key_key"), tonal.get("key_scale"))
        if camelot:
            out["camelot_key"] = camelot
        return out

    @classmethod
    def _parse_high_level(cls, data: dict) -> dict[str, Any]:
        doc = cls._unwrap(data)
        hl = doc.get("highlevel") or {}
        out: dict[str, Any] = {}
        dance = ((hl.get("danceability") or {}).get("all") or {}).get("danceable")
        if isinstance(dance, (int, float)):
            out["danceability"] = int(round(float(dance) * 100))
        voice = ((hl.get("voice_instrumental") or {}).get("all") or {}).get("voice")
        if isinstance(voice, (int, float)):
            out["vocalness"] = int(round(float(voice) * 100))
        mood = cls._dominant_mood(hl)
        if mood:
            out["mood"] = mood
        return out

    @staticmethod
    def _unwrap(data: dict) -> dict:
        """Estrae il documento di analisi qualunque sia l'incapsulamento della risposta.

        Gli endpoint per-MBID restituiscono il documento direttamente (chiavi 'rhythm'/
        'tonal' o 'highlevel'); l'API bulk lo annida sotto {mbid: {offset: doc}}.
        """
        markers = ("highlevel", "rhythm", "tonal")
        if any(k in data for k in markers):
            return data
        for value in data.values():
            if not isinstance(value, dict):
                continue
            if any(k in value for k in markers):
                return value
            for inner in value.values():
                if isinstance(inner, dict) and any(k in inner for k in markers):
                    return inner
        return data

    @staticmethod
    def _camelot(key_key: str | None, key_scale: str | None) -> str | None:
        if not key_key:
            return None
        suffix = "m" if (key_scale or "").strip().lower().startswith("min") else ""
        return pitch_to_camelot(f"{key_key}{suffix}")

    @classmethod
    def _dominant_mood(cls, hl: dict) -> str | None:
        """Mood col supporto piu' alto tra i classificatori, se supera la soglia."""
        best_mood: str | None = None
        best_prob = _MOOD_THRESHOLD
        for field, (active_value, mood) in _MOOD_MAP.items():
            block = (hl.get(field) or {}).get("all") or {}
            prob = block.get(active_value)
            if isinstance(prob, (int, float)) and float(prob) > best_prob:
                best_prob, best_mood = float(prob), mood
        return best_mood
