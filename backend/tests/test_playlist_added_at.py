"""GET /playlists/{id}/tracks espone la data di aggiunta per-playlist."""
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

import app.models  # noqa: F401
from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Track
from app.repositories import add_track_to_playlist


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


def test_playlist_added_at_valorizzato(client_db):
    client, db = client_db
    pl = Playlist(platform="manual", name="P", kind="manual")
    a = Track(source_type="manual", title="a", artist="A")
    b = Track(source_type="manual", title="b", artist="A")
    db.add_all([pl, a, b])
    db.flush()
    add_track_to_playlist(db, a, pl, added_at=datetime(2026, 3, 15, 12, 0, 0))
    db.commit()

    r = client.get(f"/api/playlists/{pl.id}/tracks")
    assert r.status_code == 200
    rows = {t["title"]: t for t in r.json()}
    assert rows["a"]["playlist_added_at"].startswith("2026-03-15T12:00:00")


def test_playlist_added_at_assente_su_get_tracks(client_db):
    client, db = client_db
    t = Track(source_type="manual", title="solo", artist="A")
    db.add(t)
    db.commit()

    r = client.get("/api/tracks")
    assert r.status_code == 200
    assert r.json()["items"][0]["playlist_added_at"] is None
