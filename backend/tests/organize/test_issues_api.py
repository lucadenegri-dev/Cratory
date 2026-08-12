from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, Issue


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
        all_issues = client.get("/api/organize/issues").json()
        assert len(all_issues) == 2
        assert all_issues[0]["file_path"] == "/m/a.mp3"
        warn = client.get("/api/organize/issues", params={"severity": "warning"}).json()
        assert len(warn) == 2
        casing = client.get("/api/organize/issues", params={"type": "inconsistent_casing"}).json()
        assert len(casing) == 1


def test_set_status(db):
    _seed(db)
    with TestClient(app) as client:
        casing_id = client.get("/api/organize/issues",
                               params={"type": "inconsistent_casing"}).json()[0]["id"]
        ok = client.post(f"/api/organize/issues/{casing_id}/status", json={"status": "accepted"})
        assert ok.status_code == 200 and ok.json()["status"] == "accepted"


def test_accept_non_fixable_rejected(db):
    _seed(db)
    with TestClient(app) as client:
        genre_id = client.get("/api/organize/issues",
                              params={"type": "missing_metadata"}).json()[0]["id"]
        resp = client.post(f"/api/organize/issues/{genre_id}/status", json={"status": "accepted"})
        assert resp.status_code == 400


def test_bulk_dismiss(db):
    _seed(db)
    with TestClient(app) as client:
        resp = client.post("/api/organize/issues/bulk", json={"severity": "warning",
                                                     "status": "dismissed"})
        assert resp.json()["updated"] == 2
        assert all(i["status"] == "dismissed" for i in client.get("/api/organize/issues").json())


def test_bulk_accept_skips_non_fixable(db):
    """bulk accept: solo le issue con suggested_fix_json vengono accettate."""
    _seed(db)  # 1 fixable (inconsistent_casing), 1 non-fixable (missing_metadata)
    with TestClient(app) as client:
        resp = client.post("/api/organize/issues/bulk", json={"status": "accepted"})
        assert resp.status_code == 200
        assert resp.json() == {"updated": 1}

        all_issues = client.get("/api/organize/issues").json()
        fixable = next(i for i in all_issues if i["type"] == "inconsistent_casing")
        non_fixable = next(i for i in all_issues if i["type"] == "missing_metadata")
        assert fixable["status"] == "accepted"
        assert non_fixable["status"] == "open"


def test_issue_read_has_location(db):
    _seed(db)
    with TestClient(app) as client:
        rows = client.get("/api/organize/issues").json()
        assert all("location" in r for r in rows)
        assert rows[0]["location"] == "inbox"


def test_list_filtra_per_location(db):
    """Il filtro ?location= deve escludere, non solo essere accettato: due file
    con collocazione opposta, ognuno con un'issue propria."""
    db.add(AudioFile(id=1, root_id=1, path="/m/in.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     location="inbox"))
    db.add(AudioFile(id=2, root_id=1, path="/m/lib.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     location="library"))
    db.flush()
    db.add(Issue(file_id=1, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=2, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante", suggested_fix_json=None, status="open"))
    db.commit()
    with TestClient(app) as client:
        inbox = client.get("/api/organize/issues", params={"location": "inbox"}).json()
        assert [r["file_id"] for r in inbox] == [1]
        library = client.get("/api/organize/issues", params={"location": "library"}).json()
        assert [r["file_id"] for r in library] == [2]


def test_fix_sets_retag_and_accepts(db):
    _seed(db)
    with TestClient(app) as client:
        genre_id = client.get("/api/organize/issues",
                              params={"type": "missing_metadata"}).json()[0]["id"]
        resp = client.post(f"/api/organize/issues/{genre_id}/fix", json={"value": "House"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["suggested_fix_json"] == {"field": "genre",
                                              "action": "retag", "to": "House"}


def test_fix_rejects_non_retaggable_field(db):
    f = AudioFile(id=2, root_id=1, path="/m/b.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", has_cover=False)
    db.add(f)
    db.add(Issue(file_id=2, type="bad_bitrate", field="file", severity="error",
                 detail="128<256", suggested_fix_json=None, status="open"))
    db.commit()
    with TestClient(app) as client:
        iid = client.get("/api/organize/issues", params={"type": "bad_bitrate"}).json()[0]["id"]
        resp = client.post(f"/api/organize/issues/{iid}/fix", json={"value": "x"})
        assert resp.status_code == 400


def test_fix_rejects_empty_value(db):
    _seed(db)
    with TestClient(app) as client:
        genre_id = client.get("/api/organize/issues",
                              params={"type": "missing_metadata"}).json()[0]["id"]
        resp = client.post(f"/api/organize/issues/{genre_id}/fix", json={"value": "   "})
        assert resp.status_code == 400


def test_fix_404(db):
    with TestClient(app) as client:
        assert client.post("/api/organize/issues/999/fix", json={"value": "x"}).status_code == 404


def test_only_new_filters_issues_by_fresh_files(db):
    from datetime import datetime, timedelta
    t0 = datetime(2020, 1, 1)
    new = AudioFile(id=1, root_id=1, path="/m/new.mp3", ext="mp3", size_bytes=1,
                    hash_method="file", status="present", artist="A", title="T",
                    first_seen_at=t0, last_scanned_at=t0)
    old = AudioFile(id=2, root_id=1, path="/m/old.mp3", ext="mp3", size_bytes=1,
                    hash_method="file", status="present", artist="B", title="U",
                    first_seen_at=t0, last_scanned_at=t0 + timedelta(days=1))
    db.add_all([new, old])
    db.add(Issue(file_id=1, type="missing_metadata", field="genre", severity="warning",
                 detail="x", status="open"))
    db.add(Issue(file_id=2, type="missing_metadata", field="genre", severity="warning",
                 detail="x", status="open"))
    db.commit()
    with TestClient(app) as client:
        only_new = client.get("/api/organize/issues", params={"only_new": True}).json()
        assert [i["file_path"] for i in only_new] == ["/m/new.mp3"]
        all_ = client.get("/api/organize/issues").json()
        assert len(all_) == 2
        by_path = {i["file_path"]: i["is_new"] for i in all_}
        assert by_path == {"/m/new.mp3": True, "/m/old.mp3": False}
