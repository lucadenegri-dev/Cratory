from mutagen.flac import FLAC

from app.organize.integrations import tagio
from app.organize.models import AudioFile, Issue, Plan, PlanOp, ScanRoot
from app.organize.services import apply as apply_svc
from app.organize.services import planner, ratings
from app.organize.services import undo as undo_svc


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
    f.has_rating = True   # il file ha davvero un rating (detect l'ha rilevato)
    db.commit()
    iss = Issue(file_id=f.id, type="stray_rating", field="rating", severity="info",
                detail="x", status="accepted",
                suggested_fix_json={"field": "rating", "action": "clear"})
    db.add(iss); db.commit()
    ops = planner.build_plan([f], [iss], set(),
                             {"naming_template": "{artist}", "folder_template": ""}, {})
    rating_ops = [o for o in ops if o.kind == "RATING"]
    assert len(rating_ops) == 1 and rating_ops[0].file_id == f.id


def test_build_plan_skips_rating_when_already_cleared(db, copy_fixture, tmp_path):
    # Il file è già stato ripulito (has_rating=False) ma la issue stray_rating
    # resta 'accepted' per sempre: il planner NON deve rigenerare un op RATING
    # fantasma a ogni piano.
    f, p = _rated_flac(db, copy_fixture, tmp_path)
    f.has_rating = False
    db.commit()
    iss = Issue(file_id=f.id, type="stray_rating", field="rating", severity="info",
                detail="x", status="accepted",
                suggested_fix_json={"field": "rating", "action": "clear"})
    db.add(iss); db.commit()
    ops = planner.build_plan([f], [iss], set(),
                             {"naming_template": "{artist}", "folder_template": ""}, {})
    assert [o for o in ops if o.kind == "RATING"] == []


def test_detect_sets_has_rating_flag(db, copy_fixture, tmp_path):
    f, p = _rated_flac(db, copy_fixture, tmp_path)
    root = db.query(ScanRoot).one()
    p2 = copy_fixture("flac", tmp_path / "b.flac")   # nessun rating
    g = AudioFile(root_id=root.id, path=p2, ext="flac", size_bytes=1,
                  hash_method="full", status="present")
    db.add(g); db.commit()
    ratings.detect_ratings(db)
    db.refresh(f); db.refresh(g)
    assert f.has_rating is True
    assert g.has_rating is False


def test_apply_rating_clears_has_rating_flag(db, copy_fixture, tmp_path):
    f, p = _rated_flac(db, copy_fixture, tmp_path)
    f.has_rating = True
    plan = Plan(status="draft", rules_json={
        "naming_template": "{artist}", "folder_template": "", "targets": {}})
    db.add(plan); db.flush()
    db.add(PlanOp(plan_id=plan.id, seq=0, kind="RATING", file_id=f.id,
                  before_json={"rating": "present"}, after_json={"action": "clear"},
                  status="pending"))
    db.commit()
    apply_svc.apply_plan(db, plan)
    db.refresh(f)
    assert f.has_rating is False


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
