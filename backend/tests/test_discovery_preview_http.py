import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def _clear_release_cache():
    from app.routers import discovery
    discovery._release_cache.clear()
    yield
    discovery._release_cache.clear()


@pytest.fixture()
def client():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)

    def _get_db():
        db = S()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_preview_itunes_hit(client, monkeypatch):
    from app.integrations.itunes import ItunesClient

    monkeypatch.setattr(
        ItunesClient, "search",
        lambda self, term, limit=5: [
            {"trackName": "Acid Trip", "artistName": "Artist", "previewUrl": "http://p", "trackViewUrl": "http://v"}
        ],
    )
    r = client.get("/api/discovery/preview", params={"artist": "Artist", "title": "Acid Trip"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "itunes"
    assert body["audio_url"] == "http://p"


def test_preview_youtube_fallback(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient
    from app.integrations.itunes import ItunesClient

    monkeypatch.setattr(ItunesClient, "search", lambda self, term, limit=5: [])
    monkeypatch.setattr(
        DiscogsClient, "get_release",
        lambda self, rid: {"videos": [{"uri": "https://youtu.be/abcdefghijk", "title": "Artist - Acid Trip", "duration": 200}]},
    )
    r = client.get("/api/discovery/preview", params={"artist": "Artist", "title": "Acid Trip", "discogs_id": 42})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "youtube"
    assert body["youtube_video_id"] == "abcdefghijk"


def test_preview_none(client, monkeypatch):
    from app.integrations.itunes import ItunesClient

    monkeypatch.setattr(ItunesClient, "search", lambda self, term, limit=5: [])
    r = client.get("/api/discovery/preview", params={"artist": "X", "title": "Y"})
    assert r.status_code == 200
    assert r.json()["kind"] == "none"


def test_preview_provider_exceptions_degrade_to_none(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient
    from app.integrations.itunes import ItunesClient

    def _boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ItunesClient, "search", _boom)
    monkeypatch.setattr(DiscogsClient, "get_release", _boom)
    r = client.get("/api/discovery/preview", params={"artist": "X", "title": "Y", "discogs_id": 42})
    assert r.status_code == 200
    assert r.json()["kind"] == "none"
