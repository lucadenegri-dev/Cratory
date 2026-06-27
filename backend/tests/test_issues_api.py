from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue


def _seed(db):
    f = AudioFile(id=1, root_id=1, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", has_cover=False, artist="A", title="T")
    db.add(f)
    db.add(Issue(file_id=1, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=1, type="inconsistent_casing", field="artist", severity="warning",
                 detail="casing", suggested_fix_json={"field": "artist", "action": "retag",
                 "from": "a", "to": "A"}, status="open"))
    db.commit()


def test_list_and_filter(db):
    _seed(db)
    with TestClient(app) as client:
        all_issues = client.get("/api/issues").json()
        assert len(all_issues) == 2
        assert all_issues[0]["file_path"] == "/m/a.mp3"
        warn = client.get("/api/issues", params={"severity": "warning"}).json()
        assert len(warn) == 2
        casing = client.get("/api/issues", params={"type": "inconsistent_casing"}).json()
        assert len(casing) == 1


def test_set_status(db):
    _seed(db)
    with TestClient(app) as client:
        casing_id = client.get("/api/issues",
                               params={"type": "inconsistent_casing"}).json()[0]["id"]
        ok = client.post(f"/api/issues/{casing_id}/status", json={"status": "accepted"})
        assert ok.status_code == 200 and ok.json()["status"] == "accepted"


def test_accept_non_fixable_rejected(db):
    _seed(db)
    with TestClient(app) as client:
        genre_id = client.get("/api/issues",
                              params={"type": "missing_metadata"}).json()[0]["id"]
        resp = client.post(f"/api/issues/{genre_id}/status", json={"status": "accepted"})
        assert resp.status_code == 400


def test_bulk_dismiss(db):
    _seed(db)
    with TestClient(app) as client:
        resp = client.post("/api/issues/bulk", json={"severity": "warning",
                                                     "status": "dismissed"})
        assert resp.json()["updated"] == 2
        assert all(i["status"] == "dismissed" for i in client.get("/api/issues").json())
