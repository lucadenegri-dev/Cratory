"""POST /api/playlists/{id}/tracks/remove: rimozione bulk con cleanup lead orfani."""
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


def test_bulk_remove_toglie_membership_e_orfani(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 4)  # lead: has_local_file False, in nessun'altra playlist/set
    r = client.post(f"/api/playlists/{pl.id}/tracks/remove", json={"track_ids": ids[:2]})
    assert r.status_code == 200
    assert r.json()["removed"] == 2
    assert r.json()["deleted_tracks"] == 2
    rest = client.get(f"/api/playlists/{pl.id}/tracks").json()
    assert [t["title"] for t in rest] == ["T2", "T3"]
    assert client.get(f"/api/playlists/{pl.id}").json()["track_count"] == 2


def test_bulk_remove_ignora_non_membri(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 2)
    r = client.post(f"/api/playlists/{pl.id}/tracks/remove", json={"track_ids": [ids[0], 99999]})
    assert r.status_code == 200
    assert r.json()["removed"] == 1


def test_bulk_remove_non_tocca_tracce_possedute(client_db):
    client, db = client_db
    pl = _pl(db)
    t = Track(source_type="local_files", title="Owned", artist="A", has_local_file=True)
    db.add(t); db.flush()
    add_track_to_playlist(db, t, pl)
    db.commit()
    r = client.post(f"/api/playlists/{pl.id}/tracks/remove", json={"track_ids": [t.id]})
    assert r.status_code == 200
    assert r.json() == {"removed": 1, "deleted_tracks": 0}
    assert db.get(Track, t.id) is not None


def test_bulk_remove_playlist_inesistente_404(client_db):
    client, _ = client_db
    assert client.post("/api/playlists/9999/tracks/remove", json={"track_ids": [1]}).status_code == 404
