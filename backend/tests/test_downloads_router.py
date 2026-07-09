import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import app
from app.routers import downloads as downloads_router

client = TestClient(app)


def _engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return e, sessionmaker(bind=e, expire_on_commit=False)


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


def test_search_409_when_not_configured(monkeypatch):
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.post("/api/downloads/search", json={"query": "aphex twin"})
    assert r.status_code == 409


def test_search_returns_candidates(monkeypatch):
    from app.integrations.slskd import SlskdFile

    class _C:
        def search(self, a, t, **k):
            return [SlskdFile(username="u", filename="Aphex Twin - Xtal.flac", size=1,
                              bitrate=None, length=None, has_free_slot=True, queue_length=0)]

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _C())
    r = client.post("/api/downloads/search", json={"query": "Aphex Twin Xtal"})
    assert r.status_code == 200
    body = r.json()
    assert body and body[0]["format"] == "flac"


def test_manual_409_when_not_configured(monkeypatch):
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.post("/api/downloads/manual",
                    json={"candidate": {"username": "u", "filename": "x.flac"}})
    assert r.status_code == 409


def test_manual_starts_job(monkeypatch):
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router.job, "is_running", lambda: False)
    started = {}

    def _fake_start(file):
        started["user"] = file.username
        return {"status": "running", "downloaded": 0}

    monkeypatch.setattr(downloads_router.job, "start_manual_job", _fake_start)
    r = client.post("/api/downloads/manual",
                    json={"candidate": {"username": "bob", "filename": "bob/x.flac"}})
    assert r.status_code == 202
    assert started["user"] == "bob"
    assert r.json()["available"] is True


def test_candidates_usa_durata_attesa(monkeypatch):
    # Con la durata attesa nel body, la versione con la durata giusta vince
    # anche contro un formato migliore con durata sbagliata.
    from app.integrations.slskd import SlskdFile

    class _C:
        def search(self, a, t, **k):
            return [
                SlskdFile(username="u1", filename="A - B.flac", size=1, bitrate=None,
                          length=500, has_free_slot=True, queue_length=0),
                SlskdFile(username="u2", filename="A - B.mp3", size=1, bitrate=320,
                          length=300, has_free_slot=True, queue_length=0),
            ]

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _C())
    r = client.post("/api/downloads/candidates",
                    json={"artist": "A", "title": "B", "duration_seconds": 300})
    assert r.status_code == 200
    body = r.json()
    assert body[0]["format"] == "mp3"


def test_track_auto_starts_autopick_job(monkeypatch):
    from app.routers import downloads as downloads_router
    from app.services import soulseek_download_job as job
    from app.models import Track

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="Night Signal", artist="Voiron")
    db.add(t)
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(job, "is_running", lambda: False)
    started = []
    monkeypatch.setattr(job, "_start", lambda items, pid: started.append(items) or {"status": "running"})

    r = client.post("/api/downloads/track/auto", json={"track_id": t.id})
    assert r.status_code == 202
    assert started == [[(t.id, None)]]


def test_track_auto_404_when_track_missing(monkeypatch):
    from app.routers import downloads as downloads_router
    from app.services import soulseek_download_job as job

    _, factory = _engine()
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(job, "is_running", lambda: False)

    r = client.post("/api/downloads/track/auto", json={"track_id": 999})
    assert r.status_code == 404


def test_track_auto_409_when_not_configured(monkeypatch):
    from app.routers import downloads as downloads_router
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.post("/api/downloads/track/auto", json={"track_id": 1})
    assert r.status_code == 409
