import os

import pytest

from app.organize.integrations import tagio
from app.organize.models import AudioFile, DupGroup, DupMember, Issue, Plan, PlanOp, ScanRoot
from app.organize.services.apply import apply_plan
from app.organize.services.undo import undo_run


def _snapshot(paths):
    """Mappa path → (esiste, artist, title) per confronto."""
    out = {}
    for p in paths:
        if os.path.exists(p):
            t = tagio.read_tags(p)
            out[p] = (True, t.artist, t.title)
        else:
            out[p] = (False, None, None)
    return out


def _build(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    keep = copy_fixture("flac", root / "varie" / "keep.flac")
    rem = copy_fixture("flac", root / "House" / "A" / "A - T.flac")
    plain = copy_fixture("flac", root / "varie" / "plain.flac")
    tagio.write_tags(keep, {"artist": "PINCO", "title": "T"})   # casing da correggere
    tagio.write_tags(rem, {"artist": "A", "title": "T"})
    tagio.write_tags(plain, {"artist": "B", "title": "U"})
    # id 3: 1 e 2 sono le ScanRoot canoniche seminate da _fresh_db (F2).
    db.add(ScanRoot(id=3, path=str(root)))
    db.add(AudioFile(id=1, root_id=3, path=keep, ext="flac", size_bytes=10, hash_method="file",
                     status="present", has_cover=False, artist="PINCO", title="T", genre="House"))
    db.add(AudioFile(id=2, root_id=3, path=rem, ext="flac", size_bytes=10, hash_method="file",
                     status="present", has_cover=False, artist="A", title="T", genre="House"))
    db.add(AudioFile(id=3, root_id=3, path=plain, ext="flac", size_bytes=10, hash_method="file",
                     status="present", has_cover=False, artist="B", title="U", genre="House"))
    # DupGroup/DupMember non hanno una relationship() verso AudioFile: senza un
    # flush qui, l'ordine di flush degli INSERT non è garantito e con
    # foreign_keys=ON (engine unificato F2) può tentare l'INSERT di dup_group
    # prima di audio_file, violando la FK su keeper_file_id.
    db.flush()
    db.add(DupGroup(id=1, match_kind="fuzzy", keeper_file_id=1, signature="s"))
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "targets": {"3": str(root)}})
    db.add(plan)
    # ops: RETAG keep (PINCO→Pinco), MOVE keep nello slot del rimosso, MOVE plain, DELETE rem
    keep_dest = str(root / "House" / "Pinco" / "Pinco - T.flac")
    plain_dest = str(root / "House" / "B" / "B - U.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="RETAG", file_id=1,
                  before_json={"artist": "PINCO"}, after_json={"artist": "Pinco"}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="MOVE", file_id=1,
                  before_json={"path": keep}, after_json={"path": keep_dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=2, kind="MOVE", file_id=3,
                  before_json={"path": plain}, after_json={"path": plain_dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=3, kind="DELETE", file_id=2,
                  before_json={"path": rem}, after_json={}, status="pending"))
    db.commit()
    quarantine_rem = str(root / ".quarantine" / os.path.relpath(rem, str(root)))
    return plan, [keep, rem, plain, keep_dest, plain_dest, quarantine_rem]


def test_apply_then_undo_equals_initial(db, tmp_path, copy_fixture):
    plan, paths = _build(db, tmp_path, copy_fixture)
    initial = _snapshot(paths)
    apply_plan(db, plan)
    assert _snapshot(paths) != initial            # apply ha cambiato qualcosa
    undo_run(db, plan)
    assert _snapshot(paths) == initial            # INVARIANTE: tutto com'era


def test_partial_failure_then_undo_restores(db, tmp_path, copy_fixture, monkeypatch):
    plan, paths = _build(db, tmp_path, copy_fixture)
    initial = _snapshot(paths)
    from app.organize.integrations import fsops
    real = fsops.safe_move
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:                       # fa fallire la 2ª mutazione FS
            raise fsops.FsOpError("boom")
        return real(src, dst)
    monkeypatch.setattr("app.organize.services.apply.fsops.safe_move", flaky)
    res = apply_plan(db, plan)
    monkeypatch.setattr("app.organize.services.apply.fsops.safe_move", real)
    assert res.partial is True
    undo_run(db, plan)
    assert _snapshot(paths) == initial            # anche dopo un parziale, l'undo ripristina
