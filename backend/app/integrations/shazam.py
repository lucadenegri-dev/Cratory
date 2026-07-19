"""Riconoscimento audio (fingerprinting) per identificare le tracce in un mix.

ABC `AudioRecognizer` + implementazione concreta su `shazamio` (endpoint pubblico
Shazam, senza API key). Dietro un'interfaccia iniettabile: `services/mix_identify`
e i test usano un recognizer finto, senza rete ne' audio.

Nota: shazamio e' async; qui lo incapsuliamo in un'API sincrona (`recognize_file`).
`ShazamioRecognizer` viene istanziato una volta per job (vedi
`services/mix_identify_job`) e `recognize_file` e' chiamato in serie per ogni
segmento del mix: loop asyncio e client Shazam vengono creati alla prima chiamata
e riusati per tutte le successive, invece di ricrearli (e riaprire una connessione)
ad ogni segmento. `close()` libera il loop; se il chiamante non lo invoca (caso
attuale di `mix_identify_job`), un finalizer lo chiude comunque alla garbage
collection dell'istanza.
"""

import asyncio
import logging
import time
import weakref
from abc import ABC, abstractmethod
from typing import Any, Callable

logger = logging.getLogger(__name__)

RECOGNIZE_TIMEOUT = 30  # secondi: oltre, un segmento bloccato non deve impallare tutto il job
MIN_CALL_INTERVAL = 1.0  # secondi tra l'inizio di due riconoscimenti: non martellare l'endpoint
BACKOFF_WAITS = (5, 15, 45)  # attese (s) dei retry interni su errore, prima di dichiararlo



class RecognizerError(Exception):
    pass


class AudioRecognizer(ABC):
    """Riconosce un breve segmento audio. Ritorna un match normalizzato o None.

    Match: {"artist": str, "title": str, "isrc": str|None, "apple_id": str|None}.
    None = nessun riconoscimento per quel segmento. La confidence la calcola
    `mix_identify` dai campioni concordi.
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
    }


def _close_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Callback del finalizer: non deve referenziare l'istanza, solo il loop."""
    if loop is not None and not loop.is_closed():
        try:
            loop.close()
        except Exception:  # noqa: BLE001 - cleanup best-effort, spesso a interprete in chiusura
            pass


class ShazamioRecognizer(AudioRecognizer):
    name = "shazamio"

    def __init__(
        self,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        # sleep/monotonic iniettabili: i test verificano pacing e backoff senza dormire
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_call_at: float | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shazam: Any = None

    def _pace(self) -> None:
        """Distanzia l'inizio di due riconoscimenti di almeno MIN_CALL_INTERVAL."""
        if self._last_call_at is not None:
            remaining = MIN_CALL_INTERVAL - (self._monotonic() - self._last_call_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_call_at = self._monotonic()

    def _ensure_client(self) -> tuple[asyncio.AbstractEventLoop, Any]:
        """Crea loop+client alla prima chiamata, poi li riusa per i segmenti successivi."""
        if self._loop is None or self._loop.is_closed():
            from shazamio import Shazam

            self._loop = asyncio.new_event_loop()
            self._shazam = Shazam()
            # Rete di sicurezza se close() non viene mai chiamato dal chiamante
            # (es. mix_identify_job crea un ShazamioRecognizer per job e non lo chiude).
            weakref.finalize(self, _close_event_loop, self._loop)
        return self._loop, self._shazam

    def recognize_file(self, path: str) -> dict[str, Any] | None:
        """Riconosce un segmento, con pacing e backoff con ripresa.

        Una raffica di 429/timeout dell'endpoint pubblico non deve diventare
        subito RecognizerError (il core abortirebbe l'analisi): si riprova con
        attese crescenti e si solleva solo a guasto persistente."""
        loop, shazam = self._ensure_client()
        recognize = getattr(shazam, "recognize", None) or getattr(shazam, "recognize_song")

        async def _go() -> dict[str, Any] | None:
            return await asyncio.wait_for(recognize(path), timeout=RECOGNIZE_TIMEOUT)

        last_exc: Exception | None = None
        for wait in (0, *BACKOFF_WAITS):
            if wait:
                logger.warning("Riconoscimento fallito (%s): riprovo tra %ss", last_exc, wait)
                self._sleep(wait)
            self._pace()
            try:
                raw = loop.run_until_complete(_go())
            except Exception as exc:  # noqa: BLE001 - rete/decodifica/timeout: si ritenta col backoff
                last_exc = exc
                continue
            return parse_shazam(raw)
        raise RecognizerError(str(last_exc)) from last_exc

    def close(self) -> None:
        """Chiude il loop riusato. Idempotente; da chiamare a fine job se possibile."""
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
        self._loop = None
        self._shazam = None
