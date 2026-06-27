import time

from fastapi.testclient import TestClient

from app.main import app


def test_analyze_endpoint(tmp_path, copy_fixture):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        root_id = client.post("/api/sources", json={"path": str(lib)}).json()["id"]
        # scan popola audio_file; poi analyze ricalcola
        client.post("/api/scan", json={"root_ids": [root_id]})
        deadline = time.time() + 5
        while time.time() < deadline:
            if client.get("/api/scan/status").json()["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        resp = client.post("/api/analyze")
        assert resp.status_code == 200
        body = resp.json()
        assert "issues_total" in body and "dup_groups" in body


def test_scan_job_runs_analysis(tmp_path, copy_fixture):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        root_id = client.post("/api/sources", json={"path": str(lib)}).json()["id"]
        client.post("/api/scan", json={"root_ids": [root_id]})
        deadline = time.time() + 5
        status = {}
        while time.time() < deadline:
            status = client.get("/api/scan/status").json()
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        assert status["status"] == "done"
        assert status["result"]["inserted"] == 1          # campo scan invariato (compat chunk 1)
        assert "analysis" in status["result"]             # analisi agganciata
        assert "issues_total" in status["result"]["analysis"]
