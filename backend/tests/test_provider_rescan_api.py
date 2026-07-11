# backend/tests/test_provider_rescan_api.py
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot
from app.services import provider_rescan_job

client = TestClient(app)


def _override(db, file_id, conf, status="open"):
    db.add(Issue(file_id=file_id, type="provider_override", field="genre",
                 severity="info", detail="x",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "House", "source": "provider",
                                     "confidence": conf}, status=status))


def _file(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", genre="x")
    db.add(f); db.flush()
    return f


def test_accepts_artist_title_fields(monkeypatch):
    # artist/title sono ora campi override validi (riscrittura completa da provider).
    # Neutralizzo il job: qui verifico solo che lo schema li accetti (niente rete).
    monkeypatch.setattr(provider_rescan_job, "start_job",
                        lambda **kw: {"status": "running"})
    r = client.post("/api/issues/provider-rescan",
                    json={"fields": ["artist", "title"]})
    assert r.status_code == 200


def test_rejects_unknown_field():
    r = client.post("/api/issues/provider-rescan", json={"fields": ["bpm"]})
    assert r.status_code == 422


def test_status_endpoint_returns_state():
    r = client.get("/api/issues/provider-rescan/status")
    assert r.status_code == 200
    assert set(r.json()) >= {"status", "phase", "processed", "total", "result"}


def test_accept_high_only_accepts_high(db):
    f = _file(db)
    _override(db, f.id, "high")
    f2 = AudioFile(root_id=f.root_id, path="/m/b.mp3", ext="mp3", size_bytes=1,
                   hash_method="file", status="present", genre="y")
    db.add(f2); db.flush()
    _override(db, f2.id, "text")
    db.commit()

    r = client.post("/api/issues/provider-override/accept-high")
    assert r.status_code == 200 and r.json()["updated"] == 1
    highs = db.query(Issue).filter_by(type="provider_override").all()
    by_conf = {i.suggested_fix_json["confidence"]: i.status for i in highs}
    assert by_conf == {"high": "accepted", "text": "open"}
