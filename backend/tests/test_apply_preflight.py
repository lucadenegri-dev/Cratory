from app.models import AudioFile, Plan, PlanOp, ScanRoot
from app.services.apply import apply_plan


def _setup(db, tmp_path, *, before_path):
    root = tmp_path / "lib"
    root.mkdir(exist_ok=True)
    db.add(ScanRoot(id=1, path=str(root)))
    db.add(AudioFile(id=1, root_id=1, path=str(root / "x.flac"), ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    plan = Plan(id=1, status="draft",
                rules_json={"naming_template": "{artist} - {title}",
                            "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": before_path},
                  after_json={"path": str(root / "House" / "A" / "A - T.flac")}, status="pending"))
    db.commit()
    return plan


def test_refused_on_blocking_conflict(db, tmp_path, copy_fixture):
    # due file che renderizzano alla stessa destinazione → collisione bloccante
    root = tmp_path / "lib"; root.mkdir()
    for i in (1, 2):
        copy_fixture("flac", root / f"{i}.flac")
    db.add(ScanRoot(id=1, path=str(root)))
    db.add(AudioFile(id=1, root_id=1, path=str(root / "1.flac"), ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    db.add(AudioFile(id=2, root_id=1, path=str(root / "2.flac"), ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    plan = Plan(id=1, status="draft",
                rules_json={"naming_template": "{artist} - {title}",
                            "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    dest = str(root / "House" / "A" / "A - T.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": str(root / "1.flac")}, after_json={"path": dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="MOVE", file_id=2,
                  before_json={"path": str(root / "2.flac")}, after_json={"path": dest}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.refused is True


def test_stale_when_before_path_mismatch(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    plan = _setup(db, tmp_path, before_path=str(tmp_path / "lib" / "ALTRO.flac"))  # before ≠ path reale
    res = apply_plan(db, plan)
    assert res.stale is True and res.failed_op_seq == 0
