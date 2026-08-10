from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, ScanRoot


def _seed(db):
    db.add(ScanRoot(id=1, path="/lib"))
    db.add(AudioFile(id=1, root_id=1, path="/lib/varie/x.mp3", ext="mp3", size_bytes=1000,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    db.commit()


def test_get_plan_404_when_absent(db):
    with TestClient(app) as client:
        assert client.get("/api/plan").status_code == 404


def test_post_then_get_plan(db):
    _seed(db)
    with TestClient(app) as client:
        created = client.post("/api/plan")
        assert created.status_code == 200
        body = created.json()
        assert body["stats"]["n_move"] == 1
        assert body["ops"][0]["after"]["path"] == "/lib/House/A/A - T.mp3"
        got = client.get("/api/plan").json()
        assert got["id"] == body["id"]


def test_plan_reports_conflict_on_missing_data(db):
    db.add(ScanRoot(id=1, path="/lib"))
    db.add(AudioFile(id=1, root_id=1, path="/lib/x.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre=None))  # genre mancante
    db.commit()
    with TestClient(app) as client:
        body = client.post("/api/plan").json()
        # il conflitto è segnalato ma non blocca: il file resta semplicemente fermo
        assert any(c["kind"] == "missing_template_data" for c in body["conflicts"])
        assert body["ops"] == []
        assert body["stats"]["blocking"] is False
