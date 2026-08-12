from app.organize.integrations.integrity import IntegrityResult
from app.organize.models import AudioFile, ScanRoot
from app.organize.services.integrity import run_integrity


def _mkfile(db, path, content_hash, status="present"):
    root = db.query(ScanRoot).first()
    if root is None:
        root = ScanRoot(path="/m")
        db.add(root)
        db.flush()
    f = AudioFile(root_id=root.id, path=path, ext="flac", size_bytes=1,
                  hash_method="file", content_hash=content_hash, status=status)
    db.add(f)
    db.flush()
    return f


def _ok(path):
    return IntegrityResult(ok=True, detail=None)


def _bad(path):
    return IntegrityResult(ok=False, detail="Invalid data found")


def test_marks_corrupt_and_ok(db):
    good = _mkfile(db, "/a.flac", "h1")
    bad = _mkfile(db, "/b.flac", "h2")
    db.commit()
    seen = {"/a.flac": _ok, "/b.flac": _bad}
    res = run_integrity(db, checker=lambda p: seen[p](p))
    db.refresh(good)
    db.refresh(bad)
    assert good.integrity_ok is True
    assert bad.integrity_ok is False
    assert bad.integrity_detail == "Invalid data found"
    assert res["corrupt"] == 1 and res["checked"] == 2


def test_incremental_skips_unchanged(db):
    _mkfile(db, "/a.flac", "h1")
    db.commit()
    run_integrity(db, checker=_ok)  # prima passata -> checked
    calls = {"n": 0}

    def counting(p):
        calls["n"] += 1
        return IntegrityResult(ok=True)

    res = run_integrity(db, checker=counting)  # seconda: hash invariato -> skip
    assert calls["n"] == 0
    assert res["skipped"] == 1 and res["checked"] == 0


def test_force_rechecks(db):
    _mkfile(db, "/a.flac", "h1")
    db.commit()
    run_integrity(db, checker=_ok)
    calls = {"n": 0}

    def counting(p):
        calls["n"] += 1
        return IntegrityResult(ok=True)

    run_integrity(db, checker=counting, force=True)
    assert calls["n"] == 1


def test_only_present_files(db):
    _mkfile(db, "/gone.flac", "h9", status="missing")
    db.commit()
    res = run_integrity(db, checker=_ok)
    assert res["checked"] == 0


def test_corrupt_file_becomes_issue_after_recompute(db):
    # Il job fa: run_integrity (marca) POI analysis.recompute (materializza
    # le issue). Senza il recompute i file corrotti non diventano issue.
    from app.organize.models import Issue
    from app.organize.services import analysis
    _mkfile(db, "/bad.flac", "h1")
    db.commit()
    run_integrity(db, checker=_bad)
    analysis.recompute(db)
    iss = db.query(Issue).filter_by(type="corrupt_file").all()
    assert len(iss) == 1
    assert iss[0].severity == "error"
    assert iss[0].suggested_fix_json == {"action": "quarantine"}
