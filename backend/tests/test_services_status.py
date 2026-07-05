import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    # Neutralizza Spotify: senza chiavi l'endpoint non costruisce SpotifyWebClient
    # ne' interroga il DB — il test riguarda solo la voce slskd.
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")
    return TestClient(app)


def test_services_status_includes_slskd_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "slskd_url", "http://slskd.local:5030")
    monkeypatch.setattr(settings, "slskd_download_dir", "/music/dl")
    r = client.get("/api/services/status")
    assert r.status_code == 200
    slskd = next((s for s in r.json()["services"] if s["key"] == "slskd"), None)
    assert slskd is not None
    assert slskd["configured"] is True
    assert {"SLSKD_URL", "SLSKD_API_KEY", "SLSKD_DOWNLOAD_DIR"}.issubset(set(slskd["env"]))


def test_services_status_slskd_unconfigured_without_url_or_dir(client, monkeypatch):
    monkeypatch.setattr(settings, "slskd_url", "")
    monkeypatch.setattr(settings, "slskd_download_dir", "/music/dl")
    r = client.get("/api/services/status")
    slskd = next(s for s in r.json()["services"] if s["key"] == "slskd")
    assert slskd["configured"] is False


def _acoustid(client):
    r = client.get("/api/services/status")
    assert r.status_code == 200
    return next(s for s in r.json()["services"] if s["key"] == "acoustid")


def test_services_status_acoustid_collegato_con_chiave_e_fpcalc(client, monkeypatch):
    from app.routers import services as services_router
    monkeypatch.setattr(settings, "acoustid_api_key", "k", raising=False)
    monkeypatch.setattr(services_router, "fpcalc_available", lambda: True)
    acoustid = _acoustid(client)
    assert acoustid["configured"] is True
    assert acoustid["connected"] is True  # chiave + fpcalc = pronto
    assert "ACOUSTID_API_KEY" in acoustid["env"]


def test_services_status_acoustid_da_collegare_senza_fpcalc(client, monkeypatch):
    from app.routers import services as services_router
    monkeypatch.setattr(settings, "acoustid_api_key", "k", raising=False)
    monkeypatch.setattr(services_router, "fpcalc_available", lambda: False)
    acoustid = _acoustid(client)
    assert acoustid["configured"] is True
    assert acoustid["connected"] is False  # manca il binario fpcalc


def test_services_status_acoustid_non_configurato_senza_chiave(client, monkeypatch):
    monkeypatch.setattr(settings, "acoustid_api_key", "", raising=False)
    acoustid = _acoustid(client)
    assert acoustid["configured"] is False
    assert acoustid["connected"] is None  # senza chiave il binario non conta
