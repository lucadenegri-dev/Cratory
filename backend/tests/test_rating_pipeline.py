from mutagen.flac import FLAC

from app.integrations import tagio
from app.models import AudioFile, Issue, Plan, PlanOp, ScanRoot
from app.services import apply as apply_svc
from app.services import planner, ratings
from app.services import undo as undo_svc


def _rated_flac(db, copy_fixture, tmp_path, value="204"):
    root = ScanRoot(path=str(tmp_path)); db.add(root); db.flush()
    p = copy_fixture("flac", tmp_path / "a.flac")
    a = FLAC(p); a["artist"] = ["Keep"]; a["rating"] = [value]; a.save()
    f = AudioFile(root_id=root.id, path=p, ext="flac", size_bytes=1,
                  hash_method="full", status="present", artist="Keep")
    db.add(f); db.flush()
    return f, p


def test_detect_creates_stray_rating_issue(db, copy_fixture, tmp_path):
    f, p = _rated_flac(db, copy_fixture, tmp_path)
    db.commit()
    res = ratings.detect_ratings(db)
    assert res["found"] == 1 and res["created"] == 1
    iss = db.query(Issue).filter_by(type="stray_rating").one()
    assert iss.field == "rating"
    assert iss.suggested_fix_json == {"field": "rating", "action": "clear"}
    # idempotente: una seconda passata non duplica
    ratings.detect_ratings(db)
    assert db.query(Issue).filter_by(type="stray_rating").count() == 1


def test_build_plan_emits_rating_op(db, copy_fixture, tmp_path):
    f, p = _rated_flac(db, copy_fixture, tmp_path)
    db.commit()
    iss = Issue(file_id=f.id, type="stray_rating", field="rating", severity="info",
                detail="x", status="accepted",
                suggested_fix_json={"field": "rating", "action": "clear"})
    db.add(iss); db.commit()
    ops = planner.build_plan([f], [iss], set(),
                             {"naming_template": "{artist}", "folder_template": ""}, {})
    rating_ops = [o for o in ops if o.kind == "RATING"]
    assert len(rating_ops) == 1 and rating_ops[0].file_id == f.id


def test_rating_op_clears_and_undo_restores(db, copy_fixture, tmp_path):
    f, p = _rated_flac(db, copy_fixture, tmp_path)
    plan = Plan(status="draft", rules_json={
        "naming_template": "{artist} - {title}", "folder_template": "", "targets": {}})
    db.add(plan); db.flush()
    db.add(PlanOp(plan_id=plan.id, seq=0, kind="RATING", file_id=f.id,
                  before_json={"rating": "present"}, after_json={"action": "clear"},
                  status="pending"))
    db.commit()
    res = apply_svc.apply_plan(db, plan)
    assert res.applied_ops == 1
    assert tagio.read_rating(p) is None
    assert tagio.read_tags(p).artist == "Keep"      # altri tag intatti
    undo_svc.undo_run(db, plan)
    assert tagio.read_rating(p) == "204"


def test_rating_op_skipped_when_no_rating(db, copy_fixture, tmp_path):
    root = ScanRoot(path=str(tmp_path)); db.add(root); db.flush()
    p = copy_fixture("flac", tmp_path / "b.flac")   # nessun rating
    f = AudioFile(root_id=root.id, path=p, ext="flac", size_bytes=1,
                  hash_method="full", status="present")
    db.add(f); db.flush()
    plan = Plan(status="draft", rules_json={
        "naming_template": "{artist}", "folder_template": "", "targets": {}})
    db.add(plan); db.flush()
    db.add(PlanOp(plan_id=plan.id, seq=0, kind="RATING", file_id=f.id,
                  before_json={"rating": "present"}, after_json={"action": "clear"},
                  status="pending"))
    db.commit()
    res = apply_svc.apply_plan(db, plan)
    assert res.applied_ops == 0 and res.skipped_ops == 1
