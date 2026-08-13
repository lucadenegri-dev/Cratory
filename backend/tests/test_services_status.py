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


def test_elenco_unificato_sette_voci(client):
    r = client.get("/api/services/status")
    assert r.status_code == 200
    services = r.json()["services"]
    assert [s["key"] for s in services] == [
        "spotify", "anthropic", "discogs", "musicbrainz", "acoustid",
        "slskd", "soundcloud",
    ]
    for s in services:
        assert isinstance(s["env"], list)
        assert isinstance(s["optional_env"], list)
        assert s["optional_ok"] in (True, False, None)
        assert s["docs"].startswith("http")


def test_discogs_configurato_di_suo_token_opzionale(client, monkeypatch):
    monkeypatch.setattr(settings, "discogs_token", "")
    d = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "discogs")
    assert d["configured"] is True          # funziona senza token
    assert d["optional_env"] == ["DISCOGS_TOKEN"]
    assert d["optional_ok"] is False        # token consigliato, non presente
    monkeypatch.setattr(settings, "discogs_token", "tok")
    d = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "discogs")
    assert d["optional_ok"] is True


def test_musicbrainz_sempre_attivo(client):
    mb = next(s for s in client.get("/api/services/status").json()["services"]
              if s["key"] == "musicbrainz")
    assert mb["configured"] is True and mb["connected"] is None


def test_acoustid_richiede_chiave_e_fpcalc(client, monkeypatch):
    monkeypatch.setattr("app.routers.services.acoustid.acoustid_configured", lambda: True)
    monkeypatch.setattr("app.routers.services.acoustid.fpcalc_available", lambda: True)
    a = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "acoustid")
    assert a["configured"] is True
    monkeypatch.setattr("app.routers.services.acoustid.fpcalc_available", lambda: False)
    a = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "acoustid")
    assert a["configured"] is False


def test_anthropic_documenta_la_chiave_nuova(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "k")
    a = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "anthropic")
    assert a["configured"] is True
    assert a["env"] == ["ANTHROPIC_API_KEY"]
    assert "AI_API_KEY" not in a["env"]     # la UI documenta solo il nome nuovo
    monkeypatch.setattr(settings, "ai_api_key", "")
    a = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "anthropic")
    assert a["configured"] is False


def test_soundcloud_riflette_ytdlp(client, monkeypatch):
    monkeypatch.setattr("app.routers.services.soundcloud_available", lambda: True)
    sc = next(s for s in client.get("/api/services/status").json()["services"]
              if s["key"] == "soundcloud")
    assert sc["configured"] is True
    monkeypatch.setattr("app.routers.services.soundcloud_available", lambda: False)
    sc = next(s for s in client.get("/api/services/status").json()["services"]
              if s["key"] == "soundcloud")
    assert sc["configured"] is False


def test_organize_providers_rimosso(client):
    """Il vecchio duplicato non deve rispondere: la fonte e' una sola."""
    assert client.get("/api/organize/providers").status_code == 404


