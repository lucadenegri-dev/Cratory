from unittest.mock import patch

from app.integrations import tagio
from app.models import AudioFile, Plan, PlanOp, ScanRoot, UndoJournal
from app.services import apply as apply_svc
from app.services import undo as undo_svc

_JPG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


def _seed_cover_plan(db, copy_fixture, tmp_path):
    root = ScanRoot(path=str(tmp_path))
    db.add(root)
    db.flush()
    fpath = copy_fixture("flac", tmp_path / "a.flac")
    f = AudioFile(root_id=root.id, path=fpath, ext="flac", size_bytes=1,
                  hash_method="full", artist="A", title="T", has_cover=False,
                  status="present")
    db.add(f)
    db.flush()
    plan = Plan(status="draft", rules_json={
        "naming_template": "{artist} - {title}", "folder_template": "", "targets": {}})
    db.add(plan)
    db.flush()
    db.add(PlanOp(plan_id=plan.id, seq=0, kind="COVER", file_id=f.id,
                  before_json={"has_cover": False},
                  after_json={"full_url": "http://f.jpg", "source": "caa",
                              "confidence": "high"}, status="pending"))
    db.commit()
    return plan, f, fpath


def test_apply_cover_embeds_and_sets_flag(db, copy_fixture, tmp_path):
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    with patch("app.services.apply.cover_art.fetch_image", return_value=_JPG):
        res = apply_svc.apply_plan(db, plan)
    assert res.applied_ops == 1
    assert tagio.read_tags(fpath).has_cover is True
    db.refresh(f)
    assert f.has_cover is True


def test_apply_cover_skips_on_download_failure(db, copy_fixture, tmp_path):
    from app.integrations.cover_art import CoverArtError
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    with patch("app.services.apply.cover_art.fetch_image", side_effect=CoverArtError("dead")):
        res = apply_svc.apply_plan(db, plan)
    assert res.applied_ops == 0
    assert res.skipped_ops == 1
    assert tagio.read_tags(fpath).has_cover is False


def test_apply_cover_skips_when_has_cover_already_true(db, copy_fixture, tmp_path):
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    f.has_cover = True
    db.commit()
    with patch("app.services.apply.cover_art.fetch_image", side_effect=AssertionError(
            "fetch_image non deve essere chiamato se has_cover è già True")) as mock_fetch:
        res = apply_svc.apply_plan(db, plan)
    mock_fetch.assert_not_called()
    assert res.applied_ops == 0
    assert res.skipped_ops == 1


def test_undo_cover_removes_embedded_art(db, copy_fixture, tmp_path):
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    with patch("app.services.apply.cover_art.fetch_image", return_value=_JPG):
        apply_svc.apply_plan(db, plan)
    assert tagio.read_tags(fpath).has_cover is True
    undo_svc.undo_run(db, plan)
    assert tagio.read_tags(fpath).has_cover is False


def test_apply_cover_skips_on_write_failure_without_halting(db, copy_fixture, tmp_path):
    """Una write_cover fallita (es. immagine troppo grande per il blocco FLAC)
    salta l'op per-op senza fermare l'intero apply."""
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    with patch("app.services.apply.cover_art.fetch_image", return_value=_JPG), \
         patch("app.services.apply.tagio.write_cover",
               side_effect=Exception("block is too long to write")):
        res = apply_svc.apply_plan(db, plan)
    assert res.applied_ops == 0
    assert res.skipped_ops == 1
    assert res.partial is False          # NON deve fermare il piano
    assert res.failed_op_seq is None
    assert tagio.read_tags(fpath).has_cover is False
    db.refresh(f)
    assert f.has_cover is False


def _add_cover_issue(db, file_id, status="accepted"):
    from app.models import Issue
    iss = Issue(file_id=file_id, type="missing_cover", field="cover", severity="info",
                detail="copertina mancante", status=status,
                suggested_fix_json={"field": "cover", "source": "caa",
                                    "confidence": "high", "full_url": "http://f.jpg"})
    db.add(iss)
    db.commit()
    return iss


def test_apply_cover_reopens_issue_on_write_failure(db, copy_fixture, tmp_path):
    """Cover non scrivibile → la issue missing_cover torna 'open' (visibile in ISSUES)."""
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    iss = _add_cover_issue(db, f.id)
    with patch("app.services.apply.cover_art.fetch_image", return_value=_JPG), \
         patch("app.services.apply.tagio.write_cover",
               side_effect=Exception("block is too long to write")):
        res = apply_svc.apply_plan(db, plan)
    assert res.skipped_ops == 1
    db.refresh(iss)
    assert iss.status == "open"


def test_apply_cover_reopens_issue_on_download_failure(db, copy_fixture, tmp_path):
    from app.integrations.cover_art import CoverArtError
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    iss = _add_cover_issue(db, f.id)
    with patch("app.services.apply.cover_art.fetch_image", side_effect=CoverArtError("dead")):
        res = apply_svc.apply_plan(db, plan)
    assert res.skipped_ops == 1
    db.refresh(iss)
    assert iss.status == "open"
