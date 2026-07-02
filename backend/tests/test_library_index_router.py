"""Endpoint /api/library/index: avvio job e polling stato."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_409_senza_library_root(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", "")
    r = client.post("/api/library/index")
    assert r.status_code == 409
    assert "LIBRARY_ROOT" in r.json()["detail"]


def test_avvio_e_status(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.config import settings
    from app.db import Base
    from app.services import library_index_job

    # Isola il job dal DB reale di sviluppo: engine SQLite in memoria dedicato.
    # StaticPool: il job gira nel thread della route (TestClient), serve la
    # connessione unica condivisa (vedi test_track_lookup.py).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(library_index_job, "SessionLocal",
                        sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    # niente thread reale nel test: il job gira sincrono
    monkeypatch.setattr(library_index_job, "_spawn", lambda fn: fn())
    r = client.post("/api/library/index")
    assert r.status_code == 202
    s = client.get("/api/library/index/status").json()
    assert s["status"] == "done"
    assert s["scanned"] == 0  # cartella vuota
