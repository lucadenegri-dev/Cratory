"""PUT /api/playlists/{id}/order: ordine completo (drag-and-drop) + kind riordinabili."""
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


def _pl(db, kind="manual"):
    pl = Playlist(platform="manual", name="P", kind=kind)
    db.add(pl); db.flush()
    return pl


def _members(db, pl, n):
    ids = []
    for i in range(n):
        t = Track(source_type="local_files", title=f"T{i}", artist="A")
        db.add(t); db.flush()
        add_track_to_playlist(db, t, pl)
        ids.append(t.id)
    db.commit()
    return ids


def test_set_order_permuta(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 4)
    r = client.put(f"/api/playlists/{pl.id}/order", json={"track_ids": [ids[2], ids[0], ids[3], ids[1]]})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["T2", "T0", "T3", "T1"]
    assert [t["playlist_position"] for t in client.get(f"/api/playlists/{pl.id}/tracks").json()] == [1, 2, 3, 4]


def test_set_order_mismatch_422(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 3)
    r = client.put(f"/api/playlists/{pl.id}/order", json={"track_ids": [ids[0], ids[1]]})
    assert r.status_code == 422


def test_set_order_409_su_kind_non_riordinabile(client_db):
    client, db = client_db
    pl = _pl(db, kind="playlist")
    ids = _members(db, pl, 2)
    assert client.put(f"/api/playlists/{pl.id}/order", json={"track_ids": ids}).status_code == 409


def test_set_order_404_playlist_inesistente(client_db):
    client, _ = client_db
    assert client.put("/api/playlists/9999/order", json={"track_ids": [1]}).status_code == 404


def test_reorder_singolo_su_shazam_ok(client_db):
    client, db = client_db
    pl = _pl(db, kind="shazam")
    ids = _members(db, pl, 3)
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": ids[2], "position": 1})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["T2", "T0", "T1"]
