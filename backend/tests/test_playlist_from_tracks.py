"""POST /api/playlists/create-from-tracks: playlist componendo dalla libreria."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


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


def test_crea_playlist_da_tracce(client_db):
    client, db = client_db
    ids = []
    for i in range(3):
        t = Track(source_type="local_files", platform="local_files",
                  platform_track_id=f"d{i}", title=f"T{i}", artist="A")
        db.add(t); db.commit(); ids.append(t.id)

    r = client.post("/api/playlists/create-from-tracks",
                    json={"name": "Warmup", "track_ids": ids})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Warmup" and body["track_count"] == 3

    tracks = client.get(f"/api/playlists/{body['id']}/tracks").json()
    assert sorted(t["title"] for t in tracks) == ["T0", "T1", "T2"]


def test_delete_endpoint_ritorna_conteggio_orfani(client_db):
    from app.models import Playlist
    from app.repositories import add_track_to_playlist

    client, db = client_db
    pl = Playlist(platform="spotify", name="P", kind="playlist")
    t = Track(source_type="spotify", title="Lead", artist="A")
    db.add_all([pl, t]); db.flush()
    add_track_to_playlist(db, t, pl); db.commit()

    r = client.delete(f"/api/playlists/{pl.id}")
    assert r.status_code == 200
    assert r.json() == {"deleted_tracks": 1}
    assert db.query(Track).count() == 0


def test_delete_endpoint_404_su_inesistente(client_db):
    client, _ = client_db
    assert client.delete("/api/playlists/9999").status_code == 404


def test_422_su_input_vuoti(client_db):
    client, _ = client_db
    assert client.post("/api/playlists/create-from-tracks",
                       json={"name": "", "track_ids": [1]}).status_code == 422
    assert client.post("/api/playlists/create-from-tracks",
                       json={"name": "X", "track_ids": []}).status_code == 422


def test_422_su_track_id_inesistente(client_db):
    client, _ = client_db
    r = client.post("/api/playlists/create-from-tracks",
                    json={"name": "X", "track_ids": [99999]})
    assert r.status_code == 422
