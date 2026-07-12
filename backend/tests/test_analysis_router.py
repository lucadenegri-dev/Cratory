"""Router /api/analysis: start (503/409/202), overview, divergences, apply."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


@pytest.fixture()
def client():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)

    def _get_db():
        db = S()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app), S
    app.dependency_overrides.clear()


def _seed_divergent(S):
    with S() as s:
        s.add(Track(id=1, source_type="spotify", has_local_file=True,
                    local_path="/x/a.mp3", artist="A", title="T",
                    bpm=128.0, bpm_source="rekordbox",
                    camelot_key="8A", key_source="rekordbox",
                    analysis_bpm=130.0, analysis_camelot="9A"))
        s.commit()


def test_start_503_senza_motore(client, monkeypatch):
    from app.routers import analysis as ar
    c, _ = client
    monkeypatch.setattr(ar.essentia_engine, "is_available", lambda: False)
    r = c.post("/api/analysis/start", json={"scope": "missing"})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "analysis_engine_unavailable"


def test_start_409_se_gia_in_corso(client, monkeypatch):
    from app.routers import analysis as ar
    c, _ = client
    monkeypatch.setattr(ar.essentia_engine, "is_available", lambda: True)
    monkeypatch.setattr(ar.audio_analysis_job, "is_running", lambda: True)
    r = c.post("/api/analysis/start", json={"scope": "all"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "analysis_already_running"


def test_start_202_avvia(client, monkeypatch):
    from app.routers import analysis as ar
    c, _ = client
    monkeypatch.setattr(ar.essentia_engine, "is_available", lambda: True)
    monkeypatch.setattr(ar.audio_analysis_job, "is_running", lambda: False)
    monkeypatch.setattr(ar.audio_analysis_job, "start_job",
                        lambda scope, track_ids: {"status": "running", "processed": 0,
                                                  "total": 0, "analyzed": 0, "failed": 0,
                                                  "applied": 0, "current_label": None,
                                                  "error": None, "started_at": None,
                                                  "finished_at": None})
    r = c.post("/api/analysis/start", json={"scope": "missing"})
    assert r.status_code == 202 and r.json()["status"] == "running"


def test_overview_e_divergences(client):
    c, S = client
    _seed_divergent(S)
    ov = c.get("/api/analysis/overview").json()
    assert ov["owned"] == 1 and ov["divergent"] == 1 and ov["analyzed"] == 0
    rows = c.get("/api/analysis/divergences").json()
    assert len(rows) == 1
    assert rows[0]["bpm_delta"] == 2.0 and rows[0]["key_compatibility"] == "compatible"


def test_apply_track_ids(client):
    c, S = client
    _seed_divergent(S)
    r = c.post("/api/analysis/apply", json={"track_ids": [1]})
    assert r.status_code == 200 and r.json()["applied"] == 1
    with S() as s:
        t = s.get(Track, 1)
        assert t.bpm == 130.0 and t.bpm_source == "cratory"
        assert t.camelot_key == "9A" and t.key_source == "cratory"


def test_apply_all_richiede_force(client):
    c, S = client
    _seed_divergent(S)
    r = c.post("/api/analysis/apply", json={"mode": "all"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "analysis_force_required"
    r = c.post("/api/analysis/apply", json={"mode": "all", "force": True})
    assert r.status_code == 200


def test_apply_vuoto_422(client):
    c, _ = client
    r = c.post("/api/analysis/apply", json={})
    assert r.status_code == 422
