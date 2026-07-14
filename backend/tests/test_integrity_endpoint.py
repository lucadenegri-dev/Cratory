from fastapi.testclient import TestClient

from app.main import app
from app.services import integrity_job

client = TestClient(app)


def test_integrity_check_reports_unavailable_without_ffmpeg(monkeypatch):
    monkeypatch.setattr(integrity_job, "ffmpeg_available", lambda: False)
    r = client.post("/api/issues/integrity-check", json={"force": False})
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_integrity_status_shape():
    r = client.get("/api/issues/integrity-check/status")
    assert r.status_code == 200
    assert "status" in r.json()
