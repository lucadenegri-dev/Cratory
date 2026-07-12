"""Cross-match libreria per le tracce Shazam nel dettaglio di un DjSet (A2 residuo).

Ogni traccia identificata riceve library_track_id/library_status, calcolati in modo
deterministico: ISRC anzitutto, poi artista+titolo esatto (case-insensitive). "owned"
se la Track matchata ha un file locale, "in_library" se e' solo un lead.
"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import DjSet, DjSetTrack, Track


def _client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app), session


def _teardown(session):
    app.dependency_overrides.pop(get_db, None)
    session.close()


def test_match_per_isrc_traccia_posseduta():
    client, db = _client_db()
    try:
        db.add(Track(
            source_type="local_files", title="Xtal", artist="Aphex Twin",
            isrc="GBAAA0000001", has_local_file=True,
        ))
        s = DjSet(source_url="http://x", title="Set", status="done", identified_count=1)
        db.add(s); db.flush()
        db.add(DjSetTrack(dj_set_id=s.id, position=1, artist="Aphex Twin", title="Xtal", isrc="GBAAA0000001"))
        db.commit()

        r = client.get(f"/api/shazam/sets/{s.id}")
        assert r.status_code == 200
        trk = r.json()["tracks"][0]
        assert trk["library_status"] == "owned"
        assert trk["library_track_id"] is not None
    finally:
        _teardown(db)


def test_match_per_artista_titolo_case_insensitive_lead_in_library():
    client, db = _client_db()
    try:
        lead = Track(source_type="manual", title="Roygbiv", artist="Boards of Canada", has_local_file=False)
        db.add(lead)
        s = DjSet(source_url="http://y", title="Set2", status="done", identified_count=1)
        db.add(s); db.flush()
        # niente ISRC sul lato Shazam, il match avviene su artista+titolo (case diverso)
        db.add(DjSetTrack(dj_set_id=s.id, position=1, artist="boards of canada", title="ROYGBIV", isrc=None))
        db.commit()

        r = client.get(f"/api/shazam/sets/{s.id}")
        assert r.status_code == 200
        trk = r.json()["tracks"][0]
        assert trk["library_status"] == "in_library"
        assert trk["library_track_id"] == lead.id
    finally:
        _teardown(db)


def test_nessun_match_restituisce_null():
    client, db = _client_db()
    try:
        s = DjSet(source_url="http://z", title="Set3", status="done", identified_count=1)
        db.add(s); db.flush()
        db.add(DjSetTrack(dj_set_id=s.id, position=1, artist="Sconosciuto", title="Mai sentito"))
        db.commit()

        r = client.get(f"/api/shazam/sets/{s.id}")
        assert r.status_code == 200
        trk = r.json()["tracks"][0]
        assert trk["library_status"] is None
        assert trk["library_track_id"] is None
    finally:
        _teardown(db)


def test_isrc_prevale_su_match_per_nome_divergente():
    """Se l'ISRC matcha una Track diversa da quella che matcherebbe per nome, vince l'ISRC."""
    client, db = _client_db()
    try:
        by_name = Track(source_type="manual", title="One", artist="A", has_local_file=False)
        by_isrc = Track(source_type="local_files", title="Other Title", artist="Other Artist",
                         isrc="ISRC123", has_local_file=True)
        db.add_all([by_name, by_isrc])
        s = DjSet(source_url="http://w", title="Set4", status="done", identified_count=1)
        db.add(s); db.flush()
        db.add(DjSetTrack(dj_set_id=s.id, position=1, artist="A", title="One", isrc="ISRC123"))
        db.commit()

        r = client.get(f"/api/shazam/sets/{s.id}")
        trk = r.json()["tracks"][0]
        assert trk["library_track_id"] == by_isrc.id
        assert trk["library_status"] == "owned"
    finally:
        _teardown(db)
