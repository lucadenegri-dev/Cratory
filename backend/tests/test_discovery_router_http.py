"""Copertura HTTP (TestClient) del router /api/discovery: /status, /genres, /dig,
/expand. La logica di discover_for_playlist/dig e' gia' testata a fondo a livello
di funzione in tests/test_discovery.py (anche chiamando dig_endpoint/get_release_detail
direttamente) e tests/test_discovery_dig.py: qui si copre lo strato HTTP mancante
(shape JSON via TestClient, error codes sui casi non ancora esercitati a quel
livello: 409 lastfm_not_configured). Il 502 su dig e' gia' coperto in test_discovery.py,
non duplicato qui."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Track
from app.repositories import add_track_to_playlist


@pytest.fixture()
def client():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)

    def _get_db():
        db = S()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app), S
    app.dependency_overrides.clear()


# --- /status --------------------------------------------------------------------


def test_status_riflette_lastfm_spotify_ai(client, monkeypatch):
    from app.routers import discovery as dr

    c, _ = client
    monkeypatch.setattr(dr, "lastfm_configured", lambda: True)
    monkeypatch.setattr(dr, "_spotify_configured", lambda: False)
    monkeypatch.setattr(dr, "llm_configured", lambda: False)

    r = c.get("/api/discovery/status")
    assert r.status_code == 200
    assert r.json() == {"configured": True, "spotify_resolver": False, "ai_explanations": False}


# --- /genres ----------------------------------------------------------------------


def test_genres_200_include_libreria_e_stili_curati(client):
    c, S = client
    with S() as s:
        s.add(Track(source_type="spotify", title="T1", artist="A", genre="Acid House"))
        s.add(Track(source_type="spotify", title="T2", artist="B", genre="Acid House"))  # duplicato
        s.add(Track(source_type="spotify", title="T3", artist="C", genre="Ambient"))
        s.add(Track(source_type="spotify", title="T4", artist="D", genre=None))  # ignorato
        s.commit()

    r = c.get("/api/discovery/genres")
    assert r.status_code == 200
    body = r.json()
    assert body["library"] == ["Acid House", "Ambient"]  # ordinato, senza duplicati
    assert "House" in body["styles"]  # stile curato sempre presente


def test_genres_200_libreria_vuota(client):
    c, _ = client
    r = c.get("/api/discovery/genres")
    assert r.status_code == 200
    assert r.json()["library"] == []


# --- /dig -----------------------------------------------------------------------


def _fake_release(title="Cult - Grail", *, label="Lbl", style="Acid House"):
    return {
        "id": 1, "title": title, "year": 2024,
        "label": [label], "style": [style],
        "community": {"have": 3, "want": 120}, "format": ["Vinyl"],
        "uri": "/release/1", "cover_image": "http://img",
    }


def test_dig_200_via_http(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient

    c, _ = client
    monkeypatch.setattr(DiscogsClient, "search_releases", lambda self, **kw: [_fake_release()])

    r = c.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Acid House"})
    assert r.status_code == 200
    body = r.json()
    assert body["seed_type"] == "genre"
    assert body["value"] == "Acid House"
    assert len(body["leads"]) == 1
    assert body["leads"][0]["artist"] == "Cult"
    assert body["leads"][0]["title"] == "Grail"


def test_dig_422_seed_type_non_valido(client):
    c, _ = client
    r = c.post("/api/discovery/dig", json={"seed_type": "not_a_seed_type", "value": "x"})
    assert r.status_code == 422  # Literal["genre", "label"] non rispettato


# --- /expand ----------------------------------------------------------------------


def test_expand_409_senza_lastfm(client, monkeypatch):
    from app.routers import discovery as dr

    c, S = client
    monkeypatch.setattr(dr, "lastfm_configured", lambda: False)
    with S() as s:
        pl = Playlist(platform="spotify", name="Seed", kind="playlist")
        s.add(pl)
        s.commit()
        playlist_id = pl.id

    r = c.post("/api/discovery/expand", json={"playlist_id": playlist_id})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "lastfm_not_configured"


def test_expand_404_playlist_inesistente(client, monkeypatch):
    from app.routers import discovery as dr

    c, _ = client
    monkeypatch.setattr(dr, "lastfm_configured", lambda: True)
    monkeypatch.setattr(dr, "_spotify_configured", lambda: False)

    class _EmptySimilarity:
        name = "fake"

        def similar_artists(self, artist, *, limit=20):
            return []

        def similar_tracks(self, artist, title, *, limit=20):
            return []

        def artist_top_tracks(self, artist, *, limit=10):
            return []

        def top_tracks_by_tag(self, tag, *, limit=20):
            return []

        def close(self):
            pass

    monkeypatch.setattr(dr, "get_lastfm_client", lambda: _EmptySimilarity())

    r = c.post("/api/discovery/expand", json={"playlist_id": 999999})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "discovery_not_found"


def test_expand_200_via_http(client, monkeypatch):
    from app.routers import discovery as dr

    c, S = client
    monkeypatch.setattr(dr, "lastfm_configured", lambda: True)
    monkeypatch.setattr(dr, "_spotify_configured", lambda: False)

    class _FakeSimilarity:
        name = "fake"

        def similar_artists(self, artist, *, limit=20):
            return [{"name": "NewBand", "match": 0.9}] if artist == "Artist 0" else []

        def similar_tracks(self, artist, title, *, limit=20):
            return []

        def artist_top_tracks(self, artist, *, limit=10):
            return [{"artist": "NewBand", "title": "Fresh Cut"}] if artist == "NewBand" else []

        def top_tracks_by_tag(self, tag, *, limit=20):
            return []

        def close(self):
            pass

    monkeypatch.setattr(dr, "get_lastfm_client", lambda: _FakeSimilarity())

    with S() as s:
        pl = Playlist(platform="spotify", name="Seed Playlist", kind="playlist")
        s.add(pl)
        s.flush()
        t = Track(source_type="spotify", platform="spotify", status="ready_for_set",
                  artist="Artist 0", title="Song A")
        s.add(t)
        s.flush()
        add_track_to_playlist(s, t, pl)
        s.commit()
        playlist_id = pl.id

    r = c.post("/api/discovery/expand", json={"playlist_id": playlist_id, "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "expand"
    assert body["scope"] == "Seed Playlist"
    titles = {cand["title"] for cand in body["candidates"]}
    assert "Fresh Cut" in titles


def test_release_detail_exposes_youtube_videos(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient

    c, _ = client
    payload = {
        "id": 42,
        "title": "Artist - EP",
        "artists": [{"name": "Artist"}],
        "labels": [{"name": "Lbl"}],
        "images": [],
        "uri": "/release/42",
        "year": 2001,
        "tracklist": [{"type_": "track", "position": "A", "title": "Acid Trip", "duration": "5:00"}],
        "videos": [
            {"uri": "https://www.youtube.com/watch?v=abcdefghijk", "title": "Artist - Acid Trip", "duration": 300},
            {"uri": "https://vimeo.com/1", "title": "nope", "duration": 1},
        ],
    }
    monkeypatch.setattr(DiscogsClient, "get_release", lambda self, rid: payload)

    r = c.get("/api/discovery/release/42")
    assert r.status_code == 200
    body = r.json()
    assert body["videos"] == [
        {"youtube_video_id": "abcdefghijk", "title": "Artist - Acid Trip", "duration_seconds": 300}
    ]
