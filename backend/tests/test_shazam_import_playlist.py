"""Import di un set Shazam come playlist di lead."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import DjSet, DjSetTrack, Playlist, Track
from app.services.manual_import import import_track_pairs


def test_import_track_pairs_crea_lead_con_isrc(db):
    items = [("Aphex Twin", "Xtal", "GBAAA0000001"), ("Boards of Canada", "Roygbiv", None)]
    rep = import_track_pairs(db, name="Set X", items=items)

    assert rep["created"] == 2 and rep["total"] == 2
    pl = db.query(Playlist).filter_by(id=rep["playlist_id"]).one()
    assert pl.kind == "manual" and pl.track_count == 2
    t = db.query(Track).filter_by(title="Xtal").one()
    assert t.source_type == "manual" and t.isrc == "GBAAA0000001"
    assert t.has_local_file is not True  # è un lead


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


def test_endpoint_importa_set_come_playlist(client_db):
    client, db = client_db
    s = DjSet(source_url="http://x", title="Boiler Room", status="done", identified_count=2)
    db.add(s); db.flush()
    db.add_all([
        DjSetTrack(dj_set_id=s.id, position=1, artist="A", title="One", isrc="I1"),
        DjSetTrack(dj_set_id=s.id, position=2, artist="B", title="Two"),
        DjSetTrack(dj_set_id=s.id, position=3, artist=None, title=None),  # non identificata → skip
    ])
    db.commit()

    r = client.post(f"/api/shazam/sets/{s.id}/import-playlist")
    assert r.status_code == 201
    body = r.json()
    assert body["created"] == 2
    pl = db.query(Playlist).filter_by(id=body["playlist_id"]).one()
    assert pl.track_count == 2
    assert pl.platform == "shazam"  # source della playlist = SHAZAM
    t = db.query(Track).filter_by(title="One", isrc="I1").one()
    assert t.source_type == "shazam"


def test_endpoint_404_su_set_inesistente(client_db):
    client, _ = client_db
    assert client.post("/api/shazam/sets/9999/import-playlist").status_code == 404


def test_endpoint_blocca_reimport_se_playlist_esiste(client_db):
    client, db = client_db
    s = DjSet(source_url="http://x", title="Set", status="done", identified_count=1)
    db.add(s); db.flush()
    db.add(DjSetTrack(dj_set_id=s.id, position=1, artist="A", title="One"))
    db.commit()

    assert client.post(f"/api/shazam/sets/{s.id}/import-playlist").status_code == 201
    # seconda import mentre la playlist esiste ancora: bloccata
    assert client.post(f"/api/shazam/sets/{s.id}/import-playlist").status_code == 409


def test_endpoint_reimport_dopo_delete_playlist(client_db):
    from app.repositories import delete_playlist

    client, db = client_db
    s = DjSet(source_url="http://y", title="Set2", status="done", identified_count=1)
    db.add(s); db.flush()
    db.add(DjSetTrack(dj_set_id=s.id, position=1, artist="A", title="One"))
    db.commit()

    pid = client.post(f"/api/shazam/sets/{s.id}/import-playlist").json()["playlist_id"]
    delete_playlist(db, pid)  # tolta dalle playlist → re-import di nuovo possibile
    assert client.post(f"/api/shazam/sets/{s.id}/import-playlist").status_code == 201
