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
