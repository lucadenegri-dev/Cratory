"""Ignora (azzera esito) una traccia dall'archivio download problematici."""
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


def test_ignora_azzera_esito():
    db = _db()
    t = Track(source_type="spotify", spotify_id="i1", platform_track_id="i1",
              title="T", artist="A", last_download_outcome="not_found",
              last_download_reason="nessun risultato")
    db.add(t); db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).delete(f"/api/downloads/pending/{t.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["last_download_outcome"] is None
        assert body["last_download_reason"] is None
        db.refresh(t)
        assert t.last_download_outcome is None
        assert t.last_download_reason is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_ignora_404_su_traccia_inesistente():
    db = _db()
    app.dependency_overrides[get_db] = lambda: db
    try:
        assert TestClient(app).delete("/api/downloads/pending/9999").status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
