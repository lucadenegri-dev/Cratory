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
    from app.core.config import settings
    from app.services import library_index_job

    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    # niente thread reale nel test: il job gira sincrono
    monkeypatch.setattr(library_index_job, "_spawn", lambda fn: fn())
    r = client.post("/api/library/index")
    assert r.status_code == 202
    s = client.get("/api/library/index/status").json()
    assert s["status"] == "done"
    assert s["scanned"] == 0  # cartella vuota
