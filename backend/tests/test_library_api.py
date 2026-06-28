from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, DupGroup, DupMember, Issue, ScanRoot


def _seed_stats(db):
    db.add(ScanRoot(id=1, path="/m", label="M"))
    db.add(AudioFile(id=1, root_id=1, path="/m/a.flac", ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(AudioFile(id=2, root_id=1, path="/m/b.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(AudioFile(id=3, root_id=1, path="/m/c.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="missing", has_cover=False))
    db.add(Issue(file_id=1, type="bad_bitrate", field=None, severity="error",
                 detail="x", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=2, type="missing_metadata", field="genre", severity="warning",
                 detail="x", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=2, type="resolved_one", field="x", severity="info",
                 detail="x", suggested_fix_json=None, status="dismissed"))
    db.add(DupGroup(id=1, match_kind="hash", keeper_file_id=1, signature="s1"))
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    db.commit()


def test_library_stats(db):
    _seed_stats(db)
    with TestClient(app) as client:
        s = client.get("/api/library/stats").json()
        assert s["files_total"] == 2          # solo i present
        assert s["by_ext"] == {"flac": 1, "mp3": 1}
        assert s["issues_by_severity"] == {"error": 1, "warning": 1}  # la dismissed esclusa
        assert s["dup_groups"] == 1
        assert s["sources"] == 1
