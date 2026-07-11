from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db, has_cover=False):
    root = ScanRoot(path="/music")
    db.add(root)
    db.flush()
    f = AudioFile(root_id=root.id, path="/music/a.flac", ext="flac", size_bytes=1,
                  hash_method="full", artist="A", title="T", has_cover=has_cover,
                  status="present")
    db.add(f)
    db.flush()
    # una issue testuale aperta → il file entra nella passata provider
    db.add(Issue(file_id=f.id, type="missing_metadata", field="genre",
                 severity="info", detail="genere mancante", status="open"))
    db.commit()
    return f.id


class _Resolved:
    fields = {}
    release_mbids = ["REL-1"]
    confidence = "high"


def test_provider_suggest_creates_missing_cover_issue(db, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    fid = _seed(db)
    fake_cover = __import__("app.integrations.cover_art", fromlist=["CoverResult"]).CoverResult(
        thumb_bytes=b"\xff\xd8T", full_url="http://f.jpg", source="caa", confidence="high")
    with patch("app.routers.issues.text_providers.resolve", return_value=_Resolved()), \
         patch("app.routers.issues.acoustid.acoustid_configured", return_value=False), \
         patch("app.integrations.cover_art.lookup_cover", return_value=fake_cover):
        r = client.post("/api/issues/provider-suggest", json={"covers": True})
    assert r.status_code == 200
    assert r.json()["covers"] == 1
    iss = db.query(Issue).filter(Issue.type == "missing_cover").one()
    assert iss.field == "cover"
    assert iss.suggested_fix_json["source"] == "caa"
    assert iss.suggested_fix_json["confidence"] == "high"
    assert iss.suggested_fix_json["thumb_ref"] == f"cover_cache/{fid}.jpg"


def test_cover_thumb_endpoint_serves_bytes(db, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.services import cover_cache
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    cover_cache.save_thumb(7, b"\xff\xd8IMG")
    r = client.get("/api/issues/cover-thumb/7")
    assert r.status_code == 200 and r.content == b"\xff\xd8IMG"
    assert r.headers["content-type"].startswith("image/jpeg")


def test_cover_thumb_404_when_missing(db, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    assert client.get("/api/issues/cover-thumb/12345").status_code == 404


def test_covers_skipped_when_flag_false(db, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    _seed(db)
    with patch("app.routers.issues.text_providers.resolve", return_value=_Resolved()), \
         patch("app.routers.issues.acoustid.acoustid_configured", return_value=False):
        r = client.post("/api/issues/provider-suggest", json={"covers": False})
    assert r.json()["covers"] == 0
    assert db.query(Issue).filter(Issue.type == "missing_cover").count() == 0


def _run_with_cover(db, tmp_path, monkeypatch, cover):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    with patch("app.routers.issues.text_providers.resolve", return_value=_Resolved()), \
         patch("app.routers.issues.acoustid.acoustid_configured", return_value=False), \
         patch("app.integrations.cover_art.lookup_cover", return_value=cover):
        return client.post("/api/issues/provider-suggest", json={"covers": True})


def test_accepted_cover_issue_not_clobbered(db, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.services import cover_cache
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    fid = _seed(db)
    cover_cache.save_thumb(fid, b"ORIGINAL")
    prev = {"field": "cover", "source": "discogs", "confidence": "text",
            "full_url": "http://old.jpg", "thumb_ref": f"cover_cache/{fid}.jpg"}
    db.add(Issue(file_id=fid, type="missing_cover", field="cover", severity="info",
                 detail="copertina mancante", status="accepted", suggested_fix_json=prev))
    db.commit()
    new_cover = __import__("app.integrations.cover_art", fromlist=["CoverResult"]).CoverResult(
        thumb_bytes=b"NEWDIFFERENT", full_url="http://new.jpg", source="caa", confidence="high")
    r = _run_with_cover(db, tmp_path, monkeypatch, new_cover)
    assert r.status_code == 200
    iss = db.query(Issue).filter(Issue.type == "missing_cover").one()
    assert iss.status == "accepted"
    assert iss.suggested_fix_json == prev
    assert cover_cache.read_thumb(fid) == b"ORIGINAL"


def test_dismissed_cover_issue_not_resurrected(db, tmp_path, monkeypatch):
    fid = _seed(db)
    prev = {"field": "cover", "source": "discogs", "confidence": "text",
            "full_url": "http://old.jpg", "thumb_ref": f"cover_cache/{fid}.jpg"}
    db.add(Issue(file_id=fid, type="missing_cover", field="cover", severity="info",
                 detail="copertina mancante", status="dismissed", suggested_fix_json=prev))
    db.commit()
    new_cover = __import__("app.integrations.cover_art", fromlist=["CoverResult"]).CoverResult(
        thumb_bytes=b"\xff\xd8NEW", full_url="http://new.jpg", source="caa", confidence="high")
    r = _run_with_cover(db, tmp_path, monkeypatch, new_cover)
    assert r.status_code == 200
    iss = db.query(Issue).filter(Issue.type == "missing_cover").one()
    assert iss.status == "dismissed"
    assert iss.suggested_fix_json == prev
