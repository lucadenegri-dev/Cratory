"""Fingerprinting AcoustID: dall'audio del file al MusicBrainz Recording MBID.

Identita' ACUSTICA certa per le tracce possedute: niente fuzzy matching sui tag.
Il fingerprint Chromaprint viene calcolato dal binario `fpcalc` (via pyacoustid)
e cercato sulla web API AcoustID, che risponde con i recording MBID candidati e
uno score 0..1. L'applicazione (soglia, cache, colonna mbid) sta in
services/fingerprint.py; qui solo il client.

Dipendenze: pyacoustid (pip, import lazy) + fpcalc nel PATH o env FPCALC.
Il fingerprinter e' iniettabile -> test senza fpcalc ne' rete (pattern Shazam).
Rate limit AcoustID: ~3 richieste/secondo (throttle a carico del chiamante).
"""

import logging
from typing import Any, Callable

import httpx

from app.core import runtime_settings
from app.organize.integrations._http import post_with_retries
from app.services import system_probe

logger = logging.getLogger(__name__)

LOOKUP_URL = "https://api.acoustid.org/v2/lookup"
_USER_AGENT = "Sortory/0.1 (+http://localhost)"

# (duration_seconds, fingerprint) dal file audio; il default usa pyacoustid/fpcalc.
Fingerprinter = Callable[[str], tuple[int, bytes | str]]


class AcoustIDError(Exception):
    pass


class AcoustIDNotConfigured(AcoustIDError):
    pass


def acoustid_configured() -> bool:
    return bool(runtime_settings.acoustid_api_key())


def fpcalc_available() -> bool:
    """True se il binario fpcalc di Chromaprint e' raggiungibile (env FPCALC,
    CRATORY_BIN_DIR o PATH). Delega al seam unico di system_probe, cosi' il
    wizard e questo controllo non possono piu' disaccordarsi sullo stesso
    binario."""
    return system_probe.resolve_binary("fpcalc", env_override="FPCALC") is not None


def parse_lookup(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Candidati {mbid, score} dal payload di /v2/lookup: ordinati per score
    decrescente, dedup per mbid (vince lo score piu' alto). Puro, testabile."""
    def _score(result: Any) -> float:
        try:
            return float(result.get("score") or 0.0) if isinstance(result, dict) else 0.0
        except (TypeError, ValueError):
            return 0.0

    # Result processati per score decrescente: a parita' di score i recording del
    # match piu' forte restano davanti (dict e sorted sono stabili).
    best: dict[str, float] = {}
    results = [r for r in payload.get("results") or [] if isinstance(r, dict)]
    for result in sorted(results, key=_score, reverse=True):
        score = _score(result)
        for rec in result.get("recordings") or []:
            mbid = rec.get("id") if isinstance(rec, dict) else None
            if mbid and (mbid not in best or score > best[mbid]):
                best[mbid] = score
    return [
        {"mbid": mbid, "score": score}
        for mbid, score in sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    ]


def _default_fingerprinter(path: str) -> tuple[int, bytes | str]:
    """Fingerprint via pyacoustid (che invoca fpcalc). Import lazy: il pacchetto
    serve solo col fingerprinting attivo."""
    import acoustid as pyacoustid  # noqa: PLC0415

    return pyacoustid.fingerprint_file(path)


class AcoustIDClient:
    name = "acoustid"

    def __init__(
        self,
        api_key: str,
        fingerprinter: Fingerprinter | None = None,
        http: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.fingerprinter = fingerprinter or _default_fingerprinter
        self.http = http or httpx.Client(
            timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        )

    def identify(self, path: str) -> list[dict[str, Any]]:
        """Candidati {mbid, score} per il file. Lista vuota = non nel DB AcoustID
        (esito definitivo). Solleva AcoustIDError su fingerprint/rete/API falliti
        (esito NON definitivo: il chiamante non deve cacharlo)."""
        try:
            duration, fingerprint = self.fingerprinter(path)
        except Exception as exc:  # fpcalc mancante, file illeggibile, decodifica
            raise AcoustIDError(f"fingerprint fallito per {path}: {exc}") from exc
        if isinstance(fingerprint, bytes):
            fingerprint = fingerprint.decode("ascii", errors="strict")
        r = post_with_retries(
            self.http, LOOKUP_URL,
            data={
                "client": self.api_key,
                "format": "json",
                "duration": int(duration),
                "fingerprint": fingerprint,
                "meta": "recordings",
            },
            error_cls=AcoustIDError,
        )
        if r.status_code == 429:
            raise AcoustIDError("AcoustID: rate limit (riprova piu' tardi).")
        if r.status_code >= 400:
            raise AcoustIDError(f"AcoustID {r.status_code}: {r.text[:160]}")
        try:
            payload = r.json()
        except ValueError as exc:
            raise AcoustIDError("AcoustID: risposta non JSON") from exc
        if payload.get("status") != "ok":
            message = (payload.get("error") or {}).get("message", "errore sconosciuto")
            raise AcoustIDError(f"AcoustID: {message}")
        return parse_lookup(payload)


def get_acoustid_client() -> AcoustIDClient:
    api_key = runtime_settings.acoustid_api_key()
    if not api_key:
        raise AcoustIDNotConfigured(
            "Chiave AcoustID mancante: impostarla dalla configurazione guidata "
            "(/setup) o come ACOUSTID_API_KEY in backend/.env."
        )
    if not fpcalc_available():
        raise AcoustIDNotConfigured(
            "Binario fpcalc (Chromaprint) non trovato: installa chromaprint "
            "(brew install chromaprint) o imposta la env FPCALC."
        )
    return AcoustIDClient(api_key)
