"""GET /api/pipeline: snapshot unico per la striscia di orientamento."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    # StaticPool: TestClient esegue la route in un altro thread, serve la
    # connessione unica condivisa (vedi test_track_lookup.py).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_get_pipeline(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "organizer_url", "")

    r = client.get("/api/pipeline")
    assert r.status_code == 200
    body = r.json()
    assert body["total_tracks"] == 0
    assert body["download_active"] is False
    assert body["inbox_files"] is None
    assert body["index_mismatch"] is None
    assert body["organizer_url"] is None
