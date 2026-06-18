"""Riconoscimento audio (fingerprinting) per identificare le tracce in un mix.

ABC `AudioRecognizer` + implementazione concreta su `shazamio` (endpoint pubblico
Shazam, senza API key). Dietro un'interfaccia iniettabile: `services/mix_identify`
e i test usano un recognizer finto, senza rete ne' audio.

Nota: shazamio e' async; qui lo incapsuliamo in un'API sincrona (`recognize_file`)
eseguendo il coroutine con asyncio.run nel thread del worker.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class RecognizerError(Exception):
    pass


class AudioRecognizer(ABC):
    """Riconosce un breve segmento audio. Ritorna un match normalizzato o None.

    Match: {"artist": str, "title": str, "isrc": str|None, "apple_id": str|None,
            "confidence": int}. None = nessun riconoscimento per quel segmento.
    """

    @abstractmethod
    def recognize_file(self, path: str) -> dict[str, Any] | None: ...


def parse_shazam(result: dict[str, Any] | None) -> dict[str, Any] | None:
    """Estrae artista/titolo/ISRC dal payload grezzo di Shazam. Testabile senza rete."""
    if not result:
        return None
    track = result.get("track") or {}
    title = (track.get("title") or "").strip()
    artist = (track.get("subtitle") or "").strip()
    if not title or not artist:
        return None
    isrc = track.get("isrc")
    apple_id = None
    for action in (track.get("hub") or {}).get("actions") or []:
        if action.get("type") == "applemusicplay" and action.get("id"):
            apple_id = str(action["id"])
            break
    return {
        "artist": artist,
        "title": title,
        "isrc": isrc.strip() if isinstance(isrc, str) and isrc.strip() else None,
        "apple_id": apple_id,
        "confidence": 80,  # Shazam non da' uno score: match = confidenza alta ma non certa
    }


class ShazamioRecognizer(AudioRecognizer):
    name = "shazamio"

    def recognize_file(self, path: str) -> dict[str, Any] | None:
        import asyncio

        from shazamio import Shazam

        async def _go() -> dict[str, Any] | None:
            shazam = Shazam()
            recognize = getattr(shazam, "recognize", None) or getattr(shazam, "recognize_song")
            return await recognize(path)

        try:
            raw = asyncio.run(_go())
        except Exception as exc:  # noqa: BLE001 - rete/decodifica: il chiamante gestisce come "nessun match"
            raise RecognizerError(str(exc)) from exc
        return parse_shazam(raw)
