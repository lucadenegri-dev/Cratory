import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import downloads as downloads_router

client = TestClient(app)


def test_status_reports_unavailable_when_not_configured(monkeypatch):
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.get("/api/downloads/status")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_candidates_409_when_not_configured(monkeypatch):
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.post("/api/downloads/candidates", json={"artist": "A", "title": "B"})
    assert r.status_code == 409


def test_candidates_returns_ranked(monkeypatch):
    from app.integrations.slskd import SlskdFile

    class _C:
        def search(self, a, t, **k):
            return [SlskdFile(username="u", filename="A - B.flac", size=1, bitrate=None,
                              length=None, has_free_slot=True, queue_length=0)]

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _C())
    r = client.post("/api/downloads/candidates", json={"artist": "A", "title": "B"})
    assert r.status_code == 200
    body = r.json()
    assert body and body[0]["format"] == "flac"
    assert "confidence" in body[0]
