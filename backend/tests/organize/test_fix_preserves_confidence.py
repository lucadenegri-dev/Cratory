from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _override(db, to="Tech House", conf="high"):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", genre="house")
    db.add(f); db.flush()
    iss = Issue(file_id=f.id, type="provider_override", field="genre",
                severity="info", detail="x",
                suggested_fix_json={"field": "genre", "action": "retag", "to": to,
                                    "source": "provider", "confidence": conf},
                status="open")
    db.add(iss); db.commit()
    return iss


def test_fix_preserves_source_and_confidence(db):
    iss = _override(db, conf="high")
    r = client.post(f"/api/issues/{iss.id}/fix", json={"value": "Tech House"})
    assert r.status_code == 200
    db.refresh(iss)
    assert iss.status == "accepted"
    assert iss.suggested_fix_json["source"] == "provider"
    assert iss.suggested_fix_json["confidence"] == "high"
    assert iss.suggested_fix_json["to"] == "Tech House"


def test_fix_on_plain_issue_has_no_markers(db):
    root = ScanRoot(path="/m2"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m2/b.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present")
    db.add(f); db.flush()
    iss = Issue(file_id=f.id, type="missing_required_tag", field="artist",
                severity="error", detail="x", status="open")
    db.add(iss); db.commit()
    r = client.post(f"/api/issues/{iss.id}/fix", json={"value": "ANNA"})
    assert r.status_code == 200
    db.refresh(iss)
    assert iss.suggested_fix_json == {"field": "artist", "action": "retag", "to": "ANNA"}
