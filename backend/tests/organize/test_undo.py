import os

from app.organize.models import AudioFile, Plan, PlanOp, ScanRoot
from app.organize.services.apply import apply_plan
from app.organize.services.undo import undo_run


def test_undo_restores_move_and_delete(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    keeper = copy_fixture("flac", root / "varie" / "k.flac")
    dup = copy_fixture("flac", root / "House" / "A" / "A - T1.flac")
    # ScanRoot id >= 3: 1 e 2 sono le canoniche (conftest.SEEDED_SCAN_ROOT_IDS).
    db.add(ScanRoot(id=3, path=str(root)))
    for fid, p in ((1, keeper), (2, dup)):
        db.add(AudioFile(id=fid, root_id=3, path=p, ext="flac", size_bytes=10,
                         hash_method="file", status="present", has_cover=False,
                         artist="A", title="T1", genre="House"))
    from app.organize.models import DupGroup, DupMember
    # flush prima di DupGroup/DupMember: ordine FK-safe, vedi test_apply_undo_invariant.py.
    db.flush()
    db.add(DupGroup(id=1, match_kind="fuzzy", keeper_file_id=1, signature="s"))
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "target_root": str(root)})
    db.add(plan)
    dest = str(root / "House" / "A" / "A - T1.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": keeper}, after_json={"path": dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="DELETE", file_id=2,
                  before_json={"path": dup}, after_json={}, status="pending"))
    db.commit()
    apply_plan(db, plan)
    res = undo_run(db, plan)
    assert res.reversed_ops == 2
    assert os.path.exists(keeper) and os.path.exists(dup)  # tutto al suo posto
    assert plan.status == "undone"
