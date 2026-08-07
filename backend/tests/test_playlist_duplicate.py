"""POST /api/playlists/{id}/duplicate: fork in copia manuale editabile."""
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


def test_duplicate_crea_copia_manuale_ordinata(client_db):
    client, db = client_db
    pl = _pl(db, kind="playlist")  # anche una playlist sincronizzata si può forkare
    _members(db, pl, 3)
    r = client.post(f"/api/playlists/{pl.id}/duplicate", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "manual" and body["platform"] == "manual"
    assert body["name"] == "P (copia)"
    assert body["track_count"] == 3
    copied = client.get(f"/api/playlists/{body['id']}/tracks").json()
    assert [t["title"] for t in copied] == ["T0", "T1", "T2"]


def test_duplicate_membership_protette_dal_prune(client_db):
    client, db = client_db
    pl = _pl(db)
    _members(db, pl, 1)
    r = client.post(f"/api/playlists/{pl.id}/duplicate", json={})
    assert r.status_code == 201
    from app.repositories import cratory_added_track_ids
    assert len(cratory_added_track_ids(db, r.json()["id"])) == 1


def test_duplicate_nome_custom(client_db):
    client, db = client_db
    pl = _pl(db)
    _members(db, pl, 1)
    r = client.post(f"/api/playlists/{pl.id}/duplicate", json={"name": "Mia copia"})
    assert r.status_code == 201
    assert r.json()["name"] == "Mia copia"


def test_duplicate_404(client_db):
    client, _ = client_db
    assert client.post("/api/playlists/9999/duplicate", json={}).status_code == 404
