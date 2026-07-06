import io

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track

_XML = b"""<DJ_PLAYLISTS><COLLECTION>
<TRACK Name="Dreamscapes" Artist="SLV" AverageBpm="128.00" Tonality="8A"
       Location="file://localhost/music/a.mp3"/>
</COLLECTION></DJ_PLAYLISTS>"""


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_import_endpoint_applies():
    db = _db()
    t = Track(source_type="spotify", has_local_file=True, local_path="/music/a.mp3")
    db.add(t); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post("/api/rekordbox/import",
                        files={"file": ("rekordbox.xml", io.BytesIO(_XML), "text/xml")})
        assert r.status_code == 200
        assert r.json()["bpm_set"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_pending_counts_owned_without_features():
    db = _db()
    db.add(Track(source_type="spotify", has_local_file=True, local_path="/m/x.mp3"))
    db.add(Track(source_type="spotify", has_local_file=True, bpm=120.0, camelot_key="8A"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).get("/api/rekordbox/pending")
        assert r.json()["pending"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_import_malformed_xml_returns_400():
    """Security: malformed/malicious XML upload → HTTP 400"""
    db = _db()
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post("/api/rekordbox/import",
                        files={"file": ("bad.xml", io.BytesIO(b"<not-xml"), "text/xml")})
        assert r.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_import_empty_file_returns_400():
    """Empty file → HTTP 400"""
    db = _db()
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post("/api/rekordbox/import",
                        files={"file": ("empty.xml", io.BytesIO(b""), "text/xml")})
        assert r.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)
