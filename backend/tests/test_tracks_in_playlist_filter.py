"""GET /api/tracks?in_playlist=<id>: solo le tracce dentro quella playlist."""
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


def _tr(db, title, genre=None):
    t = Track(source_type="local_files", platform="local_files", title=title,
              artist="A", genre=genre)
    db.add(t); db.flush()
    return t


def test_in_playlist_filtra_solo_membri(client_db):
    client, db = client_db
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl); db.flush()
    a, b, c = _tr(db, "in1"), _tr(db, "in2"), _tr(db, "out")
    add_track_to_playlist(db, a, pl)
    add_track_to_playlist(db, b, pl)
    db.commit()

    r = client.get("/api/tracks", params={"in_playlist": pl.id})
    assert r.status_code == 200
    titles = sorted(t["title"] for t in r.json()["items"])
    assert titles == ["in1", "in2"]


def test_in_playlist_combina_con_genre(client_db):
    client, db = client_db
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl); db.flush()
    house = _tr(db, "h", genre="House")
    techno = _tr(db, "t", genre="Techno")
    add_track_to_playlist(db, house, pl)
    add_track_to_playlist(db, techno, pl)
    db.commit()

    r = client.get("/api/tracks", params={"in_playlist": pl.id, "genre": "House"})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()["items"]] == ["h"]


def test_in_playlist_unione_di_piu_playlist(client_db):
    client, db = client_db
    pa = Playlist(platform="manual", name="A", kind="manual")
    pb = Playlist(platform="manual", name="B", kind="manual")
    db.add_all([pa, pb]); db.flush()
    a, b, c = _tr(db, "a"), _tr(db, "b"), _tr(db, "c")
    add_track_to_playlist(db, a, pa)
    add_track_to_playlist(db, b, pb)
    db.commit()  # c non e' in nessuna delle due

    r = client.get("/api/tracks", params={"in_playlist": [pa.id, pb.id]})
    assert r.status_code == 200
    assert sorted(t["title"] for t in r.json()["items"]) == ["a", "b"]
