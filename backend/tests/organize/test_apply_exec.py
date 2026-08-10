import os

from sqlalchemy import select

from app.organize.models import AudioFile, DupGroup, DupMember, Issue, Plan, PlanOp, ScanRoot, UndoJournal
from app.organize.services.apply import apply_plan


def _af(db, fid, path, **kw):
    d = dict(id=fid, root_id=1, path=path, ext="flac", size_bytes=10, hash_method="file",
             status="present", has_cover=False, artist="A", title=f"T{fid}", genre="House")
    d.update(kw)
    db.add(AudioFile(**d))


def test_apply_move_and_delete_with_reorder(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    keeper = copy_fixture("flac", root / "varie" / "k.flac")
    dup = copy_fixture("flac", root / "House" / "A" / "A - T1.flac")  # occupa lo slot del keeper
    db.add(ScanRoot(id=1, path=str(root)))
    _af(db, 1, keeper, title="T1")   # keeper → House/A/A - T1.flac
    _af(db, 2, dup, title="T1")      # dup rimosso, è nello slot destinazione
    db.add(DupGroup(id=1, match_kind="fuzzy", keeper_file_id=1, signature="s"))
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    dest = str(root / "House" / "A" / "A - T1.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": keeper}, after_json={"path": dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="DELETE", file_id=2,
                  before_json={"path": dup}, after_json={}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.partial is False and res.applied_ops == 2
    assert os.path.exists(dest)                      # keeper spostato nello slot
    assert not os.path.exists(keeper)
    q = str(root / ".quarantine" / "House" / "A" / "A - T1.flac")
    assert os.path.exists(q)                         # dup in quarantena (delete avvenuto prima del move)
    assert plan.status == "applied"
    rows = db.scalars(select(UndoJournal).where(UndoJournal.run_id == 1)).all()
    assert {r.kind for r in rows} == {"MOVE", "DELETE"} and len(rows) == 2


def test_apply_cleans_emptied_source_dirs(db, tmp_path, copy_fixture):
    # dopo lo spostamento la vecchia cartella genere resta vuota → va rimossa
    root = tmp_path / "lib"
    src = copy_fixture("flac", root / "Hous" / "A" / "A - T1.flac")  # genere sporco
    db.add(ScanRoot(id=1, path=str(root)))
    _af(db, 1, src, title="T1", genre="House")
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    dest = str(root / "House" / "A" / "A - T1.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": src}, after_json={"path": dest}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.applied_ops == 1
    assert os.path.exists(dest)
    assert not (root / "Hous").exists()  # catena svuotata rimossa
    assert root.exists()


def test_apply_retag(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    f = copy_fixture("flac", root / "x.flac")
    from app.organize.integrations import tagio
    tagio.write_tags(f, {"artist": "PINCO", "title": "T"})
    db.add(ScanRoot(id=1, path=str(root)))
    _af(db, 1, f, artist="PINCO", title="T")
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "", "targets": {"1": str(root)}})  # folder vuoto → niente move
    db.add(plan)
    db.add(PlanOp(plan_id=1, seq=0, kind="RETAG", file_id=1,
                  before_json={"artist": "PINCO"}, after_json={"artist": "Pinco"}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.applied_ops == 1
    assert tagio.read_tags(f).artist == "Pinco"
    row = db.scalar(select(UndoJournal).where(UndoJournal.kind == "RETAG"))
    assert row.prior_tags_json == {"artist": "PINCO"}  # prior letto dal file vivo


def test_apply_retag_updates_db_row(db, tmp_path, copy_fixture):
    # Dopo un RETAG la riga AudioFile deve riflettere i nuovi tag, così una
    # ricostruzione del piano SENZA re-scan non rigenera un RETAG fantasma.
    root = tmp_path / "lib"
    f = copy_fixture("flac", root / "x.flac")
    db.add(ScanRoot(id=1, path=str(root)))
    _af(db, 1, f, artist=None, title=None, genre="House")
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    db.add(PlanOp(plan_id=1, seq=0, kind="RETAG", file_id=1,
                  before_json={"artist": None, "title": None},
                  after_json={"artist": "Pinco", "title": "Bel Titolo"}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.applied_ops == 1
    row = db.get(AudioFile, 1)
    assert row.artist == "Pinco" and row.title == "Bel Titolo"
