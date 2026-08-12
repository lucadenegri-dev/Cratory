"""Endpoint /api/library/index: avvio job e polling stato."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_409_senza_library_root(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", "")
    r = client.post("/api/library/index")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "library_root_not_configured"


def test_avvio_e_status(monkeypatch, tmp_path):
    """Da F4 Task 3 /api/library/index è un alias di scan_job: stesso job che
    serve /api/organize/scan, invocato con locations=None (tutte le radici)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.config import settings
    from app.db import Base
    from app.organize.services import scan_job

    # Isola il job dal DB reale di sviluppo: engine SQLite in memoria dedicato.
    # StaticPool: il job gira nel thread della route (TestClient), serve la
    # connessione unica condivisa (vedi test_track_lookup.py).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(scan_job, "SessionLocal",
                        sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(settings, "archive_root", "")
    monkeypatch.setattr(settings, "slskd_download_dir", "")

    class _SyncThread:
        """niente thread reale nel test: il job gira sincrono. scan_job non ha
        un `_spawn` separato come library_index_job: si sostituisce
        direttamente threading.Thread con una chiamata inline."""

        def __init__(self, target=None, args=(), daemon=None, **kw):
            self._target, self._args = target, args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(scan_job.threading, "Thread", _SyncThread)

    r = client.post("/api/library/index")
    assert r.status_code == 202
    s = client.get("/api/library/index/status").json()
    assert s["status"] == "done"
    assert s["result"]["found"] == 0  # cartella vuota
