from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", genre="x")
    db.add(f); db.flush()
    db.add(Issue(file_id=f.id, type="missing_metadata", field="comment",
                 severity="info", detail="normale info", status="open"))
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="override",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "House", "source": "provider",
                                     "confidence": "high"}, status="open"))
    db.add(Issue(file_id=f.id, type="genre_review", field="genre",
                 severity="info", detail="AI: genre → Techno",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "ai",
                                     "confidence": "high"}, status="open"))
    db.commit()


def test_dismiss_all_info_spares_override(db):
    _seed(db)
    r = client.post("/api/issues/bulk", json={"severity": "info", "status": "dismissed"})
    assert r.status_code == 200
    ov = db.query(Issue).filter_by(type="provider_override").one()
    assert ov.status == "open"  # non toccata


def test_dismiss_all_info_spares_genre_review(db):
    _seed(db)
    r = client.post("/api/issues/bulk", json={"severity": "info", "status": "dismissed"})
    assert r.status_code == 200
    gr = db.query(Issue).filter_by(type="genre_review").one()
    assert gr.status == "open"  # non toccata: proposta AI pagata in ricerche web


def test_bulk_targeting_override_type_still_works(db):
    _seed(db)
    r = client.post("/api/issues/bulk",
                    json={"type": "provider_override", "status": "dismissed"})
    assert r.status_code == 200 and r.json()["updated"] == 1
    ov = db.query(Issue).filter_by(type="provider_override").one()
    assert ov.status == "dismissed"


def test_bulk_targeting_genre_review_type_still_works(db):
    _seed(db)
    r = client.post("/api/issues/bulk",
                    json={"type": "genre_review", "status": "dismissed"})
    assert r.status_code == 200 and r.json()["updated"] == 1
    gr = db.query(Issue).filter_by(type="genre_review").one()
    assert gr.status == "dismissed"
