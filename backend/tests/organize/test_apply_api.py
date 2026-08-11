import time

from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, Plan, PlanOp, ScanRoot
from app.organize.services import apply_job, scan_job
from app.organize.services.undo import undo_run  # noqa: E402 (top del file)


def _seed_plan(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    f = copy_fixture("flac", root / "varie" / "x.flac")
    # id 3: 1 e 2 sono le ScanRoot canoniche seminate da _fresh_db (F2).
    db.add(ScanRoot(id=3, path=str(root)))
    db.add(AudioFile(id=1, root_id=3, path=f, ext="flac", size_bytes=10, hash_method="file",
                     status="present", has_cover=False, artist="A", title="T", genre="House"))
    db.add(Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "targets": {"3": str(root)}}))
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1, before_json={"path": f},
                  after_json={"path": str(root / "House" / "A" / "A - T.flac")}, status="pending"))
    db.commit()
    return f


def _wait(client, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get("/api/organize/apply/status").json()
        if st["status"] in ("done", "error"):
            return st
        time.sleep(0.02)
    raise AssertionError("apply non terminato")


def test_apply_no_draft_400(db):
    with TestClient(app) as client:
        assert client.post("/api/organize/apply").status_code == 400


def test_apply_job_runs(db, tmp_path, copy_fixture):
    _seed_plan(db, tmp_path, copy_fixture)
    with TestClient(app) as client:
        assert client.post("/api/organize/apply").status_code == 200
        st = _wait(client)
        assert st["status"] == "done"
        assert st["result"]["applied_ops"] == 1


def test_history_and_undo(db, tmp_path, copy_fixture):
    f = _seed_plan(db, tmp_path, copy_fixture)
    with TestClient(app) as client:
        client.post("/api/organize/apply")
        _wait(client)
        hist = client.get("/api/organize/history").json()
        assert len(hist) == 1 and hist[0]["status"] == "applied"
        undo = client.post(f"/api/organize/history/{hist[0]['id']}/undo")
        assert undo.status_code == 200 and undo.json()["reversed_ops"] == 1
        assert client.get("/api/organize/history").json()[0]["status"] == "undone"


def test_undo_non_applied_400(db, tmp_path, copy_fixture):
    _seed_plan(db, tmp_path, copy_fixture)  # piano draft, non applied
    with TestClient(app) as client:
        assert client.post("/api/organize/history/1/undo").status_code == 400


def test_scan_blocked_while_apply_running(db):
    """POST /api/scan deve restituire 409 se apply_job è in esecuzione."""
    with TestClient(app) as client:
        apply_job._state.update(status="running")
        try:
            assert client.post("/api/organize/scan").status_code == 409
        finally:
            apply_job._state.update(status="idle")


def test_apply_blocked_while_scan_running(db):
    """POST /api/apply deve restituire 409 se scan_job è in esecuzione."""
    with TestClient(app) as client:
        scan_job._state.update(status="running")
        try:
            assert client.post("/api/organize/apply").status_code == 409
        finally:
            scan_job._state.update(status="idle")
