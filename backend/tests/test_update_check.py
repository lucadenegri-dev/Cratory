"""Tre esiti, e restano tre. Il terzo — "non è stato possibile controllare" —
non deve mai assomigliare al primo."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import update_check as uc


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _release(tag: str) -> dict:
    return {"tag_name": tag, "html_url": f"https://esempio.invalid/{tag}",
            "body": "note di rilascio"}


def test_ce_ne_una_piu_recente(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(200, json=_release("v0.10.0"))) as c:
        esito = uc.check(client=c)
    assert esito["update_available"] is True
    assert esito["latest"] == "0.10.0"
    assert esito["current"] == "0.9.0"
    assert esito["url"].endswith("v0.10.0")
    assert esito["notes"] == "note di rilascio"


def test_siamo_aggiornati(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(200, json=_release("v0.9.0"))) as c:
        esito = uc.check(client=c)
    assert esito["update_available"] is False
    assert esito["latest"] == "0.9.0"


def test_una_release_piu_vecchia_non_e_un_aggiornamento(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.10.0")
    with _client(lambda r: httpx.Response(200, json=_release("v0.9.0"))) as c:
        assert uc.check(client=c)["update_available"] is False


def test_il_404_non_diventa_mai_sei_aggiornato(monkeypatch):
    """GitHub risponde 404 sia per un repository irraggiungibile sia per uno
    pubblico senza release, e le due cose non si distinguono. Dire "sei
    aggiornato" a chi non ha potuto verificare niente è l'errore che questa
    separazione esiste per impedire."""
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(404, json={"message": "Not Found"})) as c:
        with pytest.raises(uc.NoReleasePublished):
            uc.check(client=c)


def test_errore_di_rete(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")

    def esplodi(r):
        raise httpx.ConnectTimeout("timeout")

    with _client(esplodi) as c:
        with pytest.raises(uc.UpdateCheckFailed):
            uc.check(client=c)


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(403, json={"message": "rate limit"})) as c:
        with pytest.raises(uc.UpdateCheckFailed):
            uc.check(client=c)


def test_tag_illeggibile_non_e_un_aggiornamento(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(200, json=_release("release-di-prova"))) as c:
        esito = uc.check(client=c)
    assert esito["update_available"] is False


def test_endpoint_esito_positivo(monkeypatch):
    monkeypatch.setattr(uc, "check", lambda client=None: {
        "current": "0.9.0", "latest": "0.10.0", "update_available": True,
        "url": "https://esempio.invalid/v0.10.0", "notes": "note"})
    body = TestClient(app).get("/api/updates/check").json()
    assert body["update_available"] is True


def test_endpoint_non_verificabile(monkeypatch):
    def fallisci(client=None):
        raise uc.UpdateCheckFailed("rete assente")

    monkeypatch.setattr(uc, "check", fallisci)
    res = TestClient(app).get("/api/updates/check")
    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "update_check_failed"


def test_endpoint_nessuna_release(monkeypatch):
    def nessuna(client=None):
        raise uc.NoReleasePublished("404")

    monkeypatch.setattr(uc, "check", nessuna)
    res = TestClient(app).get("/api/updates/check")
    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "update_no_release"
