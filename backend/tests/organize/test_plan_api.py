from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, ScanRoot


def _seed(db):
    db.add(ScanRoot(id=3, path="/lib"))
    db.add(AudioFile(id=1, root_id=3, path="/lib/varie/x.mp3", ext="mp3", size_bytes=1000,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    db.commit()


def test_get_plan_404_when_absent(db):
    with TestClient(app) as client:
        assert client.get("/api/organize/plan").status_code == 404


def test_post_then_get_plan(db, monkeypatch):
    from app.core.config import settings
    from app.organize.services import scan_job

    # Da F3b la destinazione è planning.target_root() (settings.library_root),
    # non più ScanRoot.path: allinealo alla radice seminata da _seed().
    monkeypatch.setattr(settings, "library_root", "/lib")
    # `with TestClient(app)` fa scattare il lifespan reale (main.py), che con
    # library_root="/lib" appena impostato innescherebbe una VERA
    # scan_job.start_job_if_due() in background — corsa con l'AudioFile
    # seminata sotto: se il job la riconcilia (0 file trovati sotto "/lib")
    # prima della POST, la segna "missing" e il piano non trova più nulla da
    # spostare (flaky, dipendente dai tempi del thread). Non è l'auto-scan
    # sotto test qui: va disinnescato.
    monkeypatch.setattr(scan_job, "start_job_if_due", lambda: None)
    _seed(db)
    with TestClient(app) as client:
        created = client.post("/api/organize/plan")
        assert created.status_code == 200
        body = created.json()
        assert body["stats"]["n_move"] == 1
        assert body["ops"][0]["after"]["path"] == "/lib/House/A/A - T.mp3"
        got = client.get("/api/organize/plan").json()
        assert got["id"] == body["id"]


def test_plan_reports_conflict_on_missing_data(db):
    db.add(ScanRoot(id=3, path="/lib"))
    db.add(AudioFile(id=1, root_id=3, path="/lib/x.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre=None))  # genre mancante
    db.commit()
    with TestClient(app) as client:
        body = client.post("/api/organize/plan").json()
        # il conflitto è segnalato ma non blocca: il file resta semplicemente fermo
        assert any(c["kind"] == "missing_template_data" for c in body["conflicts"])
        assert body["ops"] == []
        assert body["stats"]["blocking"] is False
