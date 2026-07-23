"""POST /api/playlists/{id}/reorder: riordino manuale (solo playlist manuali)."""
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


def test_reorder_sposta_e_rinumera(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 5)  # T0..T4 in posizioni 1..5
    # sposta l'ultima (T4) in posizione 1
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": ids[4], "position": 1})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["T4", "T0", "T1", "T2", "T3"]


def test_reorder_clamp_oltre_la_fine(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 3)
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": ids[0], "position": 999})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["T1", "T2", "T0"]


def test_reorder_409_su_non_manuale(client_db):
    client, db = client_db
    pl = _pl(db, kind="playlist")
    ids = _members(db, pl, 2)
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": ids[0], "position": 1})
    assert r.status_code == 409


def test_reorder_404_traccia_non_membro(client_db):
    client, db = client_db
    pl = _pl(db)
    _members(db, pl, 2)
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": 99999, "position": 1})
    assert r.status_code == 404


def test_reorder_404_playlist_inesistente(client_db):
    client, _ = client_db
    r = client.post("/api/playlists/9999/reorder", json={"track_id": 1, "position": 1})
    assert r.status_code == 404
