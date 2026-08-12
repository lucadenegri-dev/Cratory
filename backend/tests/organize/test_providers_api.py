from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_providers_lists_all_four():
    body = client.get("/api/organize/providers").json()
    keys = [p["key"] for p in body]
    assert keys == ["musicbrainz", "discogs", "acoustid", "anthropic"]
    for p in body:
        assert p["name"] and p["category"] and p["description"]
        assert isinstance(p["env_vars"], list) and p["env_vars"]
        assert p["docs_url"].startswith("http")
        assert p["status"] in ("configured", "connected", "missing")


def test_musicbrainz_always_connected():
    body = client.get("/api/organize/providers").json()
    mb = next(p for p in body if p["key"] == "musicbrainz")
    assert mb["status"] == "connected"


def test_discogs_status_reflects_token(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.discogs_token", "tok")
    body = client.get("/api/organize/providers").json()
    assert next(p for p in body if p["key"] == "discogs")["status"] == "configured"
    monkeypatch.setattr("app.core.config.settings.discogs_token", None)
    body = client.get("/api/organize/providers").json()
    assert next(p for p in body if p["key"] == "discogs")["status"] == "connected"


def test_anthropic_status_reflects_key(monkeypatch):
    monkeypatch.setattr("app.organize.routers.providers.ai_tags.is_configured", lambda: True)
    body = client.get("/api/organize/providers").json()
    assert next(p for p in body if p["key"] == "anthropic")["status"] == "configured"
    monkeypatch.setattr("app.organize.routers.providers.ai_tags.is_configured", lambda: False)
    body = client.get("/api/organize/providers").json()
    assert next(p for p in body if p["key"] == "anthropic")["status"] == "missing"


def test_acoustid_status_reflects_config(monkeypatch):
    monkeypatch.setattr("app.organize.routers.providers.acoustid.acoustid_configured", lambda: True)
    monkeypatch.setattr("app.organize.routers.providers.acoustid.fpcalc_available", lambda: True)
    body = client.get("/api/organize/providers").json()
    assert next(p for p in body if p["key"] == "acoustid")["status"] == "configured"
    monkeypatch.setattr("app.organize.routers.providers.acoustid.fpcalc_available", lambda: False)
    body = client.get("/api/organize/providers").json()
    assert next(p for p in body if p["key"] == "acoustid")["status"] == "missing"
