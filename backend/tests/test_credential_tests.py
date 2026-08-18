"""La prova di una credenziale deve riportare l'errore VERO del provider:
è la differenza fra un wizard che diagnostica e uno che dice 'errore'."""
import httpx
import pytest

from app.core import runtime_settings as rs
from app.core.config import settings
from app.services import credential_tests as ct


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_spotify_credenziali_valide(db, monkeypatch):
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")
    rs.apply(db, "spotify_client_id", "id")
    rs.apply(db, "spotify_client_secret", "secret")
    with _client(lambda req: httpx.Response(200, json={"access_token": "t"})) as c:
        assert ct.check("spotify", client=c)["ok"] is True


def test_spotify_riporta_il_messaggio_del_provider(db, monkeypatch):
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")
    rs.apply(db, "spotify_client_id", "id")
    rs.apply(db, "spotify_client_secret", "sbagliata")
    payload = {"error": "invalid_client", "error_description": "Invalid client secret"}
    with _client(lambda req: httpx.Response(400, json=payload)) as c:
        res = ct.check("spotify", client=c)
    assert res["ok"] is False
    assert "Invalid client secret" in res["detail"]


def test_servizio_non_configurato_non_chiama_la_rete(db, monkeypatch):
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")

    def esplodi(req):
        raise AssertionError("non doveva chiamare la rete")

    with _client(esplodi) as c:
        res = ct.check("spotify", client=c)
    assert res == {"ok": False, "code": "not_configured", "detail": ""}


def test_anthropic_ok(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "")
    rs.apply(db, "ai_api_key", "sk-test")
    with _client(lambda req: httpx.Response(200, json={"id": "msg_1"})) as c:
        assert ct.check("anthropic", client=c)["ok"] is True


def test_anthropic_chiave_invalida(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "")
    rs.apply(db, "ai_api_key", "sk-sbagliata")
    payload = {"error": {"message": "invalid x-api-key"}}
    with _client(lambda req: httpx.Response(401, json=payload)) as c:
        res = ct.check("anthropic", client=c)
    assert res["ok"] is False
    assert "invalid x-api-key" in res["detail"]


def test_discogs_senza_token_e_valido(db, monkeypatch):
    """Il dig funziona anche senza token, a rate ridotto: non è un errore."""
    monkeypatch.setattr(settings, "discogs_token", "")

    def esplodi(req):
        raise AssertionError("senza token non c'è niente da provare")

    with _client(esplodi) as c:
        res = ct.check("discogs", client=c)
    assert res == {"ok": True, "code": "no_token", "detail": ""}


def test_discogs_token_valido(db, monkeypatch):
    monkeypatch.setattr(settings, "discogs_token", "")
    rs.apply(db, "discogs_token", "tok")
    with _client(lambda req: httpx.Response(200, json={"username": "dj"})) as c:
        res = ct.check("discogs", client=c)
    assert res["ok"] is True
    assert "dj" in res["detail"]


def test_acoustid_senza_fpcalc_non_e_pronto(db, monkeypatch):
    """Chiave e binario servono entrambi: senza dirlo, l'utente mette la chiave
    e resta col bottone grigio senza capire perché."""
    monkeypatch.setattr(settings, "acoustid_api_key", "")
    rs.apply(db, "acoustid_api_key", "aid")
    monkeypatch.setattr(ct.system_probe, "resolve_binary", lambda *a, **k: None)

    def esplodi(req):
        raise AssertionError("senza fpcalc non serve chiamare AcoustID")

    with _client(esplodi) as c:
        res = ct.check("acoustid", client=c)
    assert res["ok"] is False
    assert res["code"] == "fpcalc_missing"


def test_acoustid_chiave_invalida(db, monkeypatch):
    monkeypatch.setattr(settings, "acoustid_api_key", "")
    rs.apply(db, "acoustid_api_key", "sbagliata")
    monkeypatch.setattr(ct.system_probe, "resolve_binary", lambda *a, **k: "/usr/bin/fpcalc")
    payload = {"status": "error", "error": {"message": "invalid API key"}}
    with _client(lambda req: httpx.Response(200, json=payload)) as c:
        res = ct.check("acoustid", client=c)
    assert res["ok"] is False


def test_acoustid_altro_errore_non_e_colpa_della_chiave(db, monkeypatch):
    """Una fingerprint finta fa protestare AcoustID: significa che la chiave
    è stata accettata."""
    monkeypatch.setattr(settings, "acoustid_api_key", "")
    rs.apply(db, "acoustid_api_key", "buona")
    monkeypatch.setattr(ct.system_probe, "resolve_binary", lambda *a, **k: "/usr/bin/fpcalc")
    payload = {"status": "error", "error": {"message": "invalid fingerprint"}}
    with _client(lambda req: httpx.Response(200, json=payload)) as c:
        assert ct.check("acoustid", client=c)["ok"] is True


def test_servizio_sconosciuto():
    with pytest.raises(KeyError):
        ct.check("pippo")


def test_errore_di_rete_non_propaga(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "")
    rs.apply(db, "ai_api_key", "sk-test")

    def timeout(req):
        raise httpx.ConnectTimeout("timeout")

    with _client(timeout) as c:
        res = ct.check("anthropic", client=c)
    assert res["ok"] is False
    assert res["code"] == "network_error"
