from fastapi.testclient import TestClient

from app.organize.integrations import tagio
from app.main import app
from app.organize.models import AudioFile, Plan, PlanOp, ScanRoot
from app.organize.services import manual_edit

client = TestClient(app)


def test_history_marks_manual_edit_runs(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old"})
    db.add(ScanRoot(id=1, path=str(tmp_path / "lib")))
    db.add(AudioFile(id=1, root_id=1, path=f, ext="flac", size_bytes=10,
                     hash_method="file", status="present", artist="Old"))
    # una run "normale" applicata, senza kind
    normal = Plan(id=99, status="applied", rules_json={"naming_template": "{artist}"})
    db.add(normal)
    db.add(PlanOp(plan_id=99, seq=0, kind="RETAG", file_id=1,
                  before_json={}, after_json={}, status="applied"))
    db.commit()
    manual_edit.edit_tags(db, db.get(AudioFile, 1), {"artist": "New"})

    rows = client.get("/api/history").json()
    by_kind = {r["kind"]: r for r in rows}
    assert by_kind["manual_edit"]["n_ops"] == 0        # nessun PlanOp per l'edit manuale
    assert None in by_kind                             # la run normale non ha kind
