"""Provider di feature musicali: Deezer. ISRC -> BPM, senza API key.

Deezer espone un endpoint pubblico read-only (niente OAuth, niente API key) che,
dato un ISRC, restituisce la traccia con il campo `bpm` (0 quando Deezer non lo
conosce). E' un match ESATTO sull'ISRC che gia' possediamo dall'import Spotify:
nessun fuzzy matching, nessun falso positivo.

Cosa da' / cosa NON da':
- BPM (alta affidabilita', identita' certa via ISRC).
- NON fornisce key/mood/danceability: completa solo il BPM. Sta in testa alla
  catena proprio per coprire il BPM con l'identificatore piu' solido che abbiamo.

Tracce senza ISRC: Deezer ritorna None e il BPM resta a GetSongBPM/AcousticBrainz.
Dietro l'ABC MusicFeatureProvider, httpx iniettabile -> test senza rete.
"""

import logging
from typing import Any

import httpx

from app.integrations import MusicFeatureProvider
from app.integrations._http import get_with_retries
from app.integrations.getsongbpm import FeatureProviderError

logger = logging.getLogger(__name__)

BASE = "https://api.deezer.com"
_USER_AGENT = "Cratory/0.1 (+http://localhost)"


class DeezerProvider(MusicFeatureProvider):
    name = "deezer"

    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(
            timeout=15, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        )

    # ---- HTTP -----------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
        r = get_with_retries(self.http, f"{BASE}{path}", error_cls=FeatureProviderError)
        if r.status_code == 429:
            raise FeatureProviderError("Deezer: rate limit (riprova piu' tardi).")
        if r.status_code >= 400:
            raise FeatureProviderError(f"Deezer {r.status_code}: {r.text[:160]}")
        try:
            return r.json()
        except ValueError as exc:
            raise FeatureProviderError("Deezer: risposta non JSON") from exc

    # ---- MusicFeatureProvider -------------------------------------------

    def lookup(self, *, title, artist, isrc=None, duration_seconds=None, context=None):
        # Deezer identifica per ISRC: senza ISRC non c'e' un match affidabile.
        if not isrc:
            return None
        try:
            data = self._get(f"/track/isrc:{isrc}")
        except FeatureProviderError as exc:
            logger.warning("Deezer ISRC %s fallito: %s", isrc, exc)
            return None
        # Deezer ritorna {"error": {...}} quando l'ISRC non esiste nel catalogo.
        if not isinstance(data, dict) or data.get("error"):
            return None
        return self._parse(data)

    # ---- parsing (testabile senza rete) ---------------------------------

    @staticmethod
    def _parse(track: dict[str, Any]) -> dict[str, Any] | None:
        out: dict[str, Any] = {}
        bpm = track.get("bpm")
        try:
            bpm_f = float(bpm) if bpm not in (None, "") else 0.0
        except (TypeError, ValueError):
            bpm_f = 0.0
        if bpm_f > 0:  # Deezer usa 0 per "BPM sconosciuto": non e' un dato.
            out["bpm"] = round(bpm_f, 1)
        if not out:
            return None
        out["confidence"] = 90  # match esatto su ISRC = identita' certa
        return out
