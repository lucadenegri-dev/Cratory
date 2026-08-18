"""Prova reale delle credenziali: una chiamata minima per provider.

Il `detail` riporta il messaggio del provider così com'è, non una nostra
parafrasi: è quello che permette all'utente di capire se ha sbagliato il
segreto, se l'account non ha credito o se è la rete a non funzionare.

Le funzioni si chiamano `check_*` e non `test_*` di proposito: `test_*` in un
modulo importato dalla suite sarebbe raccolto da pytest come caso di test.
"""
from __future__ import annotations

import base64
import logging

import httpx

from app.core import runtime_settings
from app.integrations.llm import DEFAULT_MODEL
from app.services import system_probe

log = logging.getLogger(__name__)

SERVICES = ("spotify", "anthropic", "discogs", "acoustid")
_TIMEOUT_S = 15.0

_NOT_CONFIGURED = {"ok": False, "code": "not_configured", "detail": ""}


def _ok(detail: str = "", code: str = "ok") -> dict:
    return {"ok": True, "code": code, "detail": detail}


def _ko(detail: str, code: str = "invalid") -> dict:
    return {"ok": False, "code": code, "detail": detail}


def _error_message(err: object) -> str:
    """Messaggio testuale da un valore 'error', qualunque forma abbia:
    dict con 'message', stringa diretta, o qualsiasi altra forma (lista,
    numero, null) per cui non c'è un messaggio da estrarre -> stringa
    vuota, mai un'eccezione."""
    if isinstance(err, dict):
        msg = err.get("message")
        return str(msg) if msg else ""
    if isinstance(err, str):
        return err
    return ""


def _provider_message(res: httpx.Response) -> str:
    """Messaggio d'errore del provider, qualunque forma abbia il suo JSON."""
    try:
        body = res.json()
    except ValueError:
        return res.text[:300] or f"HTTP {res.status_code}"
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = _error_message(err)
            if msg:
                return msg
        elif isinstance(err, str):
            return str(body.get("error_description") or err)
        if body.get("message"):
            return str(body["message"])
    return f"HTTP {res.status_code}"


def check_spotify(client: httpx.Client) -> dict:
    client_id = runtime_settings.spotify_client_id()
    client_secret = runtime_settings.spotify_client_secret()
    if not client_id or not client_secret:
        return dict(_NOT_CONFIGURED)
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    res = client.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}"},
        timeout=_TIMEOUT_S,
    )
    if res.status_code == 200:
        return _ok()
    return _ko(_provider_message(res))


def check_anthropic(client: httpx.Client) -> dict:
    api_key = runtime_settings.ai_api_key()
    if not api_key:
        return dict(_NOT_CONFIGURED)
    res = client.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": runtime_settings.ai_model() or DEFAULT_MODEL,
              "max_tokens": 1,
              "messages": [{"role": "user", "content": "ping"}]},
        timeout=_TIMEOUT_S,
    )
    if res.status_code == 200:
        return _ok()
    return _ko(_provider_message(res))


def check_discogs(client: httpx.Client) -> dict:
    """Senza token il dig funziona lo stesso, a rate ridotto: è un esito
    valido, non un errore da segnalare in rosso."""
    token = runtime_settings.discogs_token()
    if not token:
        return _ok(code="no_token")
    res = client.get(
        "https://api.discogs.com/oauth/identity",
        headers={"Authorization": f"Discogs token={token}"},
        timeout=_TIMEOUT_S,
    )
    if res.status_code == 200:
        try:
            body = res.json()
        except ValueError:
            return _ok()
        # Se il body non è un dict, il token è stato accettato ma
        # il username non può essere letto
        if isinstance(body, dict):
            return _ok(str(body.get("username", "")))
        return _ok()
    return _ko(_provider_message(res))


def check_acoustid(client: httpx.Client) -> dict:
    """Servono chiave E binario. La lookup viene mandata con una fingerprint
    non valida di proposito: se AcoustID protesta per la fingerprint vuol dire
    che la chiave l'ha accettata."""
    api_key = runtime_settings.acoustid_api_key()
    if not api_key:
        return dict(_NOT_CONFIGURED)
    if system_probe.resolve_binary("fpcalc", env_override="FPCALC") is None:
        return _ko("", code="fpcalc_missing")
    res = client.get(
        "https://api.acoustid.org/v2/lookup",
        params={"client": api_key, "duration": 120, "fingerprint": "sonda"},
        timeout=_TIMEOUT_S,
    )
    try:
        body = res.json()
    except ValueError:
        return _ko(f"HTTP {res.status_code}")
    # Se il body non è un dict, non riusciamo ad interpretarlo
    # come OK o come errore specifico
    if not isinstance(body, dict):
        return _ko(f"HTTP {res.status_code}")
    if body.get("status") == "ok":
        return _ok()
    message = _error_message(body.get("error"))
    if "api key" in message.lower():
        return _ko(message)
    return _ok(message, code="key_accepted")


_CHECKS = {
    "spotify": check_spotify,
    "anthropic": check_anthropic,
    "discogs": check_discogs,
    "acoustid": check_acoustid,
}


def check(service: str, client: httpx.Client | None = None) -> dict:
    """Esito della prova. Un errore di rete non deve propagare: il wizard deve
    poter mostrare 'non raggiungibile' invece di un 500."""
    if service not in _CHECKS:
        raise KeyError(service)
    owned = client is None
    client = client or httpx.Client()
    try:
        return _CHECKS[service](client)
    except httpx.HTTPError as exc:
        log.info("prova %s fallita: %s", service, exc)
        return _ko(str(exc), code="network_error")
    finally:
        if owned:
            client.close()
