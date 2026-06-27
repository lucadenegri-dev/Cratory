import time

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_sources_crud(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    with TestClient(app) as client:
        created = client.post("/api/sources", json={"path": str(lib), "label": "Main"})
        assert created.status_code == 201
        root_id = created.json()["id"]
        assert created.json()["file_count"] == 0

        listed = client.get("/api/sources").json()
        assert len(listed) == 1 and listed[0]["label"] == "Main"

        assert client.delete(f"/api/sources/{root_id}").status_code == 204
        assert client.get("/api/sources").json() == []


def test_add_source_rejects_missing_path():
    with TestClient(app) as client:
        resp = client.post("/api/sources", json={"path": "/percorso/inesistente/xyz"})
        assert resp.status_code == 400


def test_scan_endpoint_end_to_end(tmp_path, copy_fixture):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        root_id = client.post("/api/sources", json={"path": str(lib)}).json()["id"]
        started = client.post("/api/scan", json={"root_ids": [root_id]})
        assert started.status_code == 200

        deadline = time.time() + 5
        status = {}
        while time.time() < deadline:
            status = client.get("/api/scan/status").json()
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        assert status["status"] == "done"
        assert status["result"]["inserted"] == 1
