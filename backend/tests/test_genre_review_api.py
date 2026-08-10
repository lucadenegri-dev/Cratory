"""Router del job revisione generi: start/status/preview."""

import time

from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile
from app.services import genre_review_job


def _seed(db, fid, **kw):
    db.add(AudioFile(id=fid, root_id=1, path=f"/m/{fid}.mp3", ext="mp3",
                     size_bytes=1, hash_method="file", status="present",
                     has_cover=False, **kw))
    db.commit()


def test_start_without_key_not_configured(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as client:
        r = client.post("/api/genre-review").json()
        assert r["configured"] is False


def test_start_passes_body_to_job(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    captured = {}

    def fake_start(folder=None, genre=None, redo=False):
        captured.update(folder=folder, genre=genre, redo=redo)
        return {"status": "running"}

    monkeypatch.setattr(genre_review_job, "start_job", fake_start)
    with TestClient(app) as client:
        r = client.post("/api/genre-review",
                        json={"folder": "House", "redo": True}).json()
        assert r["status"] == "running"
        assert captured == {"folder": "House", "genre": None, "redo": True}


def test_status_returns_job_state(db):
    with TestClient(app) as client:
        r = client.get("/api/genre-review/status").json()
        assert r["status"] in ("idle", "running", "done", "error")


def test_preview_counts_candidates(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    _seed(db, 1, artist="A", title="T")
    with TestClient(app) as client:
        r = client.get("/api/genre-review/preview").json()
        assert r == {"configured": True, "files": 1}


def test_job_runs_review_and_finishes(db, monkeypatch):
    """start_job → thread → review mockata → stato done col risultato."""
    from app.services import genre_review as gr_service

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    result = {"configured": True, "files": 0, "proposed": 0, "confirmed": 0,
              "unresolved": 0, "skipped": 0}
    monkeypatch.setattr(gr_service, "review", lambda *a, **k: result)
    state = genre_review_job.start_job()
    assert state["status"] == "running"
    for _ in range(100):  # max ~5s
        if genre_review_job.job_state()["status"] != "running":
            break
        time.sleep(0.05)
    final = genre_review_job.job_state()
    assert final["status"] == "done"
    assert final["result"] == result
