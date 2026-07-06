# backend/tests/test_provider_suggest_api.py
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", artist="SLV", title="Dreamscapes", status="present")
    db.add(f); db.flush()
    db.add(Issue(file_id=f.id, type="missing_metadata", field="label",
                 severity="info", detail="manca label", status="open"))
    db.commit()
    return f


def test_provider_suggest_fills_label(db, monkeypatch):
    _seed(db)
    monkeypatch.setattr("app.core.config.settings.musicbrainz_user_agent", "t/0.1")
    monkeypatch.setattr("app.routers.issues.text_providers.lookup",
                        lambda file, **kw: {"label": "Drumcode"})
    r = client.post("/api/issues/provider-suggest")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True and body["suggested"] == 1
    iss = db.query(Issue).filter_by(field="label").one()
    assert iss.suggested_fix_json == {"field": "label", "action": "retag", "to": "Drumcode"}
    assert iss.status == "open"
