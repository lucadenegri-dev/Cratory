import time

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    # F1: un solo processo, un solo health check (app/main.py, non sotto
    # /api/organize): il main.py di Sortory che ne definiva uno proprio e'
    # stato assorbito in quello di Cratory.
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_scan_endpoint_end_to_end(tmp_path, copy_fixture, monkeypatch):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        # Dopo l'avvio (guardia _no_real_library_scan intatta durante il
        # lifespan): scan_job deriva ora le radici da roots.radici(), che deve
        # vedere `lib` come LIBRARY_ROOT per adottare la sorgente appena creata.
        from app.core.config import settings
        monkeypatch.setattr(settings, "library_root", str(lib))
        started = client.post("/api/organize/scan", json={"locations": ["library"]})
        assert started.status_code == 200

        deadline = time.time() + 5
        status = {}
        while time.time() < deadline:
            status = client.get("/api/organize/scan/status").json()
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        assert status["status"] == "done"
        assert status["result"]["inserted"] == 1
