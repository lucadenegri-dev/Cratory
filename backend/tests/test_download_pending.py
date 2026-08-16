"""Esiti download persistiti sulla Track + sezione "da sistemare"."""
from types import SimpleNamespace

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


def test_il_runner_persiste_esito_sulla_traccia(monkeypatch):
    from app.services import download_queue as q
    from app.services import download_runner as runner

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="spotify", spotify_id="s1", platform_track_id="s1",
              title="T", artist="A")
    db.add(t); db.commit()

    monkeypatch.setattr(runner, "SessionLocal", factory)
    # _process_item e' monkeypatchato sotto e non tocca il client: basta un
    # oggetto con close() (chiamato da _run_soulseek nel finally).
    monkeypatch.setattr(runner, "get_slskd_client",
                        lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(runner, "_process_item",
                        lambda *a, **k: ("needs_review", "confidenza sotto soglia", None))
    q.enqueue(db, [t.id])
    runner.run_item(q.claim_next(db).id)

    db.expire_all()
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


def test_retry_pending_accoda_le_da_sistemare(monkeypatch):
    from app.routers import downloads as downloads_router
    from app.services import download_queue as q

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="spotify", spotify_id="r1", platform_track_id="r1",
              title="Pend", artist="A", last_download_outcome="not_found")
    # posseduta: non e' da sistemare, non deve finire in coda
    db.add_all([t, Track(source_type="spotify", spotify_id="r2",
                         platform_track_id="r2", title="Ok", artist="A",
                         has_local_file=True, last_download_outcome="downloaded")])
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(downloads_router, "fill", lambda: None)

    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post("/api/downloads/retry-pending")
        assert r.status_code == 200
        assert r.json() == {"enqueued": 1, "skipped": 0, "replaced": 0}
        assert [i.track_id for i in q.list_items(factory())] == [t.id]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_retry_pending_409_senza_slskd(monkeypatch):
    from app.routers import downloads as downloads_router
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    assert TestClient(app).post("/api/downloads/retry-pending").status_code == 409
