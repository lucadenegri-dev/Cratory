# backend/tests/test_issue_current_value.py
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def test_current_value_reflects_file_tag(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", genre="house")
    db.add(f); db.flush()
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="x",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "House", "source": "provider",
                                     "confidence": "high"}, status="open"))
    db.commit()
    row = next(i for i in client.get("/api/issues").json()
               if i["type"] == "provider_override")
    assert row["current_value"] == "house"
