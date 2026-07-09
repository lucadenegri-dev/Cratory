"""Esiti download persistiti sulla Track + sezione "da sistemare"."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


def _engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return e, sessionmaker(bind=e, expire_on_commit=False)


def test_job_persiste_esito_sulla_traccia(monkeypatch):
    from app.services import soulseek_download_job as job

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="spotify", spotify_id="s1", platform_track_id="s1",
              title="T", artist="A")
    db.add(t); db.commit()

    monkeypatch.setattr(job, "SessionLocal", factory)
    monkeypatch.setattr(job, "get_slskd_client", lambda: object())
    monkeypatch.setattr(job, "_process_item",
                        lambda *a, **k: ("needs_review", "confidenza sotto soglia", None))
    job._run([(t.id, None)], None)

    db.refresh(t)
    assert t.last_download_outcome == "needs_review"
    assert t.last_download_reason == "confidenza sotto soglia"
    assert t.last_download_path is None


def test_pending_endpoint_filtra_giusto():
    engine, factory = _engine()
    db = factory()
    # pendente vera
    db.add(Track(source_type="spotify", spotify_id="p1", platform_track_id="p1",
                 title="Pend", artist="A", last_download_outcome="needs_review",
                 last_download_reason="x"))
    # posseduta: non deve comparire anche se ha un esito storico
    db.add(Track(source_type="spotify", spotify_id="p2", platform_track_id="p2",
                 title="Own", artist="A", has_local_file=True,
                 last_download_outcome="failed"))
    # scartata: fuori
    db.add(Track(source_type="spotify", spotify_id="p3", platform_track_id="p3",
                 title="Arch", artist="A", archived=True,
                 last_download_outcome="not_found"))
    # senza esito: fuori
    db.add(Track(source_type="spotify", spotify_id="p4", platform_track_id="p4",
                 title="Clean", artist="A"))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).get("/api/downloads/pending")
        assert r.status_code == 200
        rows = r.json()
        assert [x["title"] for x in rows] == ["Pend"]
        assert rows[0]["last_download_outcome"] == "needs_review"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_retry_pending_avvia_il_job(monkeypatch):
    from app.routers import downloads as downloads_router
    from app.services import soulseek_download_job as job

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="spotify", spotify_id="r1", platform_track_id="r1",
              title="Pend", artist="A", last_download_outcome="not_found")
    db.add(t); db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    started = []
    monkeypatch.setattr(job, "_start", lambda items, pid: started.append(items) or {"status": "running"})
    monkeypatch.setattr(job, "SessionLocal", factory)

    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post("/api/downloads/retry-pending")
        assert r.status_code == 202
        assert started == [[(t.id, None)]]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_retry_pending_409_senza_slskd(monkeypatch):
    from app.routers import downloads as downloads_router
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    assert TestClient(app).post("/api/downloads/retry-pending").status_code == 409
