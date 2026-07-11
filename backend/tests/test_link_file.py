"""Collegamento manuale di un file locale alla traccia."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _track(db, **kw):
    t = Track(source_type="spotify", spotify_id="l1", platform_track_id="l1",
              title="T", artist="A", **kw)
    db.add(t); db.commit()
    return t


def test_collega_file_e_azzera_esito(tmp_path):
    db = _db()
    t = _track(db, last_download_outcome="not_found", last_download_reason="x")
    f = tmp_path / "song.mp3"
    f.write_bytes(b"finto audio")

    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post(f"/api/tracks/{t.id}/link-file", json={"path": str(f)})
        assert r.status_code == 200
        body = r.json()
        assert body["has_local_file"] is True
        assert body["local_path"] == str(f)
        assert body["local_format"] == "mp3"
        assert body["last_download_outcome"] is None
        assert body["last_download_reason"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_400_su_file_inesistente(tmp_path):
    db = _db()
    t = _track(db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post(f"/api/tracks/{t.id}/link-file",
                                 json={"path": str(tmp_path / "manca.mp3")})
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert detail["code"] == "track_link_failed"
        assert "non trovato" in detail["params"]["reason"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_400_su_estensione_non_audio(tmp_path):
    db = _db()
    t = _track(db)
    f = tmp_path / "note.txt"
    f.write_text("no")
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post(f"/api/tracks/{t.id}/link-file", json={"path": str(f)})
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert detail["code"] == "track_link_failed"
        assert "non audio" in detail["params"]["reason"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_404_su_traccia_inesistente(tmp_path):
    db = _db()
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    app.dependency_overrides[get_db] = lambda: db
    try:
        assert TestClient(app).post("/api/tracks/9999/link-file",
                                    json={"path": str(f)}).status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
