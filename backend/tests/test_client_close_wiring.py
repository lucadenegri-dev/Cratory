"""E11: i client HTTP delle integrazioni (SpotifyWebClient/DiscogsClient/...) hanno
close()/context-manager (ClosableHttpClient) ma finche' i chiamanti non lo invocano
ogni request perde un httpx.Client. Verifica che i router li chiudano sempre,
successo o errore, con TestClient end-to-end su due endpoint rappresentativi."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import Base, get_db
from app.main import app
from app.integrations.discogs import DiscogsClient
from app.integrations.spotify import SpotifyWebClient


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_spotify_status_closes_client(client_db, monkeypatch):
    """GET /api/spotify/status crea un SpotifyWebClient(db) SOLO per user_connected():
    deve chiuderlo prima di rispondere, non lasciarlo aperto per il GC."""
    client, db = client_db
    closed = []
    monkeypatch.setattr(SpotifyWebClient, "close",
                        lambda self: closed.append(self))
    monkeypatch.setattr(SpotifyWebClient, "user_connected", lambda self: False)
    monkeypatch.setattr(settings, "spotify_client_id", "cid")
    monkeypatch.setattr(settings, "spotify_client_secret", "secret")

    resp = client.get("/api/spotify/status")

    assert resp.status_code == 200
    assert len(closed) == 1


def test_spotify_status_closes_client_even_on_error(client_db, monkeypatch):
    """Anche se user_connected() esplode, il client va comunque chiuso (finally)."""
    client, db = client_db
    closed = []
    monkeypatch.setattr(SpotifyWebClient, "close",
                        lambda self: closed.append(self))

    def boom(self):
        raise RuntimeError("rete giu'")

    monkeypatch.setattr(SpotifyWebClient, "user_connected", boom)
    monkeypatch.setattr(settings, "spotify_client_id", "cid")
    monkeypatch.setattr(settings, "spotify_client_secret", "secret")

    with pytest.raises(RuntimeError):
        client.get("/api/spotify/status")

    assert len(closed) == 1


def test_discogs_release_detail_closes_client(client_db, monkeypatch):
    """GET /api/discovery/release?id= crea un DiscogsClient() per una singola
    chiamata get_release(): deve chiuderlo prima di rispondere."""
    client, db = client_db
    closed = []
    monkeypatch.setattr(DiscogsClient, "close",
                        lambda self: closed.append(self))
    monkeypatch.setattr(DiscogsClient, "get_release", lambda self, rid: {
        "title": "T", "artists": [{"name": "A"}], "labels": [], "images": [],
        "uri": "/release/1", "year": 2020, "tracklist": [],
    })

    resp = client.get("/api/discovery/release", params={"id": "1"})

    assert resp.status_code == 200
    assert len(closed) == 1


def test_discogs_release_detail_closes_client_on_error(client_db, monkeypatch):
    """Anche in errore (DiscogsError -> 502) il client va chiuso, non solo sul
    percorso felice."""
    from app.integrations.discogs import DiscogsError

    client, db = client_db
    closed = []
    monkeypatch.setattr(DiscogsClient, "close",
                        lambda self: closed.append(self))

    def boom(self, rid):
        raise DiscogsError("rate limit")

    monkeypatch.setattr(DiscogsClient, "get_release", boom)

    resp = client.get("/api/discovery/release", params={"id": "1"})

    assert resp.status_code == 502
    assert len(closed) == 1
