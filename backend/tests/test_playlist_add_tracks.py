"""POST /api/playlists/{id}/add-tracks: aggiunta idempotente a playlist esistente."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Track, playlist_tracks


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _pl(db):
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl); db.flush()
    return pl


def _tracks(db, n):
    ids = []
    for i in range(n):
        t = Track(source_type="local_files", platform="local_files",
                  title=f"T{i}", artist="A")
        db.add(t); db.flush(); ids.append(t.id)
    db.commit()
    return ids


def test_add_tracks_aggiunge_e_marca_cratory(client_db):
    client, db = client_db
    pl = _pl(db); db.commit()
    ids = _tracks(db, 2)

    r = client.post(f"/api/playlists/{pl.id}/add-tracks", json={"track_ids": ids})
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 2 and body["skipped"] == 0
    assert body["playlist"]["track_count"] == 2

    added_by = db.execute(
        select(playlist_tracks.c.added_by).where(playlist_tracks.c.playlist_id == pl.id)
    ).scalars().all()
    assert added_by == ["cratory", "cratory"]


def test_add_tracks_e_idempotente(client_db):
    client, db = client_db
    pl = _pl(db); db.commit()
    ids = _tracks(db, 2)
    client.post(f"/api/playlists/{pl.id}/add-tracks", json={"track_ids": ids})

    r = client.post(f"/api/playlists/{pl.id}/add-tracks", json={"track_ids": ids})
    assert r.status_code == 200
    assert r.json()["added"] == 0 and r.json()["skipped"] == 2
    assert r.json()["playlist"]["track_count"] == 2


def test_add_tracks_404_playlist_inesistente(client_db):
    client, db = client_db
    ids = _tracks(db, 1)
    assert client.post("/api/playlists/9999/add-tracks",
                       json={"track_ids": ids}).status_code == 404


def test_add_tracks_422_track_inesistente(client_db):
    client, db = client_db
    pl = _pl(db); db.commit()
    r = client.post(f"/api/playlists/{pl.id}/add-tracks", json={"track_ids": [99999]})
    assert r.status_code == 422
