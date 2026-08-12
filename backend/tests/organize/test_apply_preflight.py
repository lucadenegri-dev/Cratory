from sqlalchemy import select

from app.organize.models import AudioFile, Plan, PlanOp, ScanRoot
from app.organize.services.apply import apply_plan


def _setup(db, tmp_path, *, before_path):
    root = tmp_path / "lib"
    root.mkdir(exist_ok=True)
    db.add(ScanRoot(id=3, path=str(root)))
    db.add(AudioFile(id=1, root_id=3, path=str(root / "x.flac"), ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    plan = Plan(id=1, status="draft",
                rules_json={"naming_template": "{artist} - {title}",
                            "folder_template": "{genre}/{artist}", "target_root": str(root)})
    db.add(plan)
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": before_path},
                  after_json={"path": str(root / "House" / "A" / "A - T.flac")}, status="pending"))
    db.commit()
    return plan


def _seed_two_colliding(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"; root.mkdir()
    for i in (1, 2):
        copy_fixture("flac", root / f"{i}.flac")
    db.add(ScanRoot(id=3, path=str(root)))
    db.add(AudioFile(id=1, root_id=3, path=str(root / "1.flac"), ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    db.add(AudioFile(id=2, root_id=3, path=str(root / "2.flac"), ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    plan = Plan(id=1, status="draft",
                rules_json={"naming_template": "{artist} - {title}",
                            "folder_template": "{genre}/{artist}", "target_root": str(root)})
    db.add(plan)
    dest = str(root / "House" / "A" / "A - T.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": str(root / "1.flac")}, after_json={"path": dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="MOVE", file_id=2,
                  before_json={"path": str(root / "2.flac")}, after_json={"path": dest}, status="pending"))
    db.commit()
    return plan, root


def test_colliding_ops_are_skipped_not_refused(db, tmp_path, copy_fixture):
    # due file che renderizzano alla stessa destinazione: entrambi saltati,
    # l'apply non viene più rifiutato in blocco
    plan, root = _seed_two_colliding(db, tmp_path, copy_fixture)
    res = apply_plan(db, plan)
    assert res.refused is False
    assert res.applied_ops == 0 and res.skipped_ops == 2
    assert (root / "1.flac").exists() and (root / "2.flac").exists()  # nessuno spostato
    ops = db.scalars(select(PlanOp)).all()
    assert {o.status for o in ops} == {"skipped"}
    assert plan.status == "applied"


def test_disk_occupied_op_skipped_others_applied(db, tmp_path, copy_fixture):
    # la dest del file 1 è occupata su disco da un file NON nel DB → op saltato;
    # il file 2 si sposta regolarmente
    root = tmp_path / "lib"; root.mkdir()
    copy_fixture("flac", root / "1.flac")
    copy_fixture("flac", root / "2.flac")
    dest1 = root / "House" / "A" / "A - T1.flac"
    copy_fixture("flac", dest1)  # intruso su disco, sconosciuto al DB
    db.add(ScanRoot(id=3, path=str(root)))
    for i in (1, 2):
        db.add(AudioFile(id=i, root_id=3, path=str(root / f"{i}.flac"), ext="flac", size_bytes=1,
                         hash_method="file", status="present", has_cover=False,
                         artist="A", title=f"T{i}", genre="House"))
    plan = Plan(id=1, status="draft",
                rules_json={"naming_template": "{artist} - {title}",
                            "folder_template": "{genre}/{artist}", "target_root": str(root)})
    db.add(plan)
    dest2 = root / "House" / "A" / "A - T2.flac"
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": str(root / "1.flac")}, after_json={"path": str(dest1)}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="MOVE", file_id=2,
                  before_json={"path": str(root / "2.flac")}, after_json={"path": str(dest2)}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.applied_ops == 1 and res.skipped_ops == 1
    assert (root / "1.flac").exists()      # saltato: resta dov'era
    assert dest2.exists() and not (root / "2.flac").exists()  # applicato
    by_id = {o.file_id: o for o in db.scalars(select(PlanOp)).all()}
    assert by_id[1].status == "skipped" and by_id[2].status == "applied"


def test_stale_when_before_path_mismatch(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    plan = _setup(db, tmp_path, before_path=str(tmp_path / "lib" / "ALTRO.flac"))  # before ≠ path reale
    res = apply_plan(db, plan)
    assert res.stale is True and res.failed_op_seq == 0
