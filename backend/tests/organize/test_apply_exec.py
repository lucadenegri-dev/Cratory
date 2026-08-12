import os
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.organize.models import AudioFile, DupGroup, DupMember, Issue, Plan, PlanOp, ScanRoot, UndoJournal
from app.organize.services.apply import apply_plan


def _af(db, fid, path, **kw):
    d = dict(id=fid, root_id=3, path=path, ext="flac", size_bytes=10, hash_method="file",
             status="present", has_cover=False, artist="A", title=f"T{fid}", genre="House")
    d.update(kw)
    db.add(AudioFile(**d))


def test_apply_move_and_delete_with_reorder(db, tmp_path, copy_fixture, monkeypatch):
    root = tmp_path / "lib"
    # location di default degli AudioFile è "inbox": la quarantena del DELETE
    # deriva la base da SLSKD_DOWNLOAD_DIR per quella location, non più da
    # root_id — deve combaciare con `root` per restare dentro di essa.
    monkeypatch.setattr(settings, "slskd_download_dir", str(root))
    keeper = copy_fixture("flac", root / "varie" / "k.flac")
    dup = copy_fixture("flac", root / "House" / "A" / "A - T1.flac")  # occupa lo slot del keeper
    db.add(ScanRoot(id=3, path=str(root)))
    _af(db, 1, keeper, title="T1")   # keeper → House/A/A - T1.flac
    _af(db, 2, dup, title="T1")      # dup rimosso, è nello slot destinazione
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
    db.add(ScanRoot(id=3, path=str(root)))
    _af(db, 1, src, title="T1", genre="House")
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "target_root": str(root)})
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
    db.add(ScanRoot(id=3, path=str(root)))
    _af(db, 1, f, artist="PINCO", title="T")
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "", "target_root": str(root)})  # folder vuoto → niente move
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
    db.add(ScanRoot(id=3, path=str(root)))
    _af(db, 1, f, artist=None, title=None, genre="House")
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "target_root": str(root)})
    db.add(plan)
    db.add(PlanOp(plan_id=1, seq=0, kind="RETAG", file_id=1,
                  before_json={"artist": None, "title": None},
                  after_json={"artist": "Pinco", "title": "Bel Titolo"}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.applied_ops == 1
    row = db.get(AudioFile, 1)
    assert row.artist == "Pinco" and row.title == "Bel Titolo"


def _piano_di_solo_delete(db, root, src, **kw):
    db.add(ScanRoot(id=3, path=str(root)))
    _af(db, 1, src, **kw)
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "", "target_root": str(root)})
    db.add(plan)
    db.add(PlanOp(plan_id=1, seq=0, kind="DELETE", file_id=1,
                  before_json={"path": src}, after_json={}, status="pending"))
    db.commit()
    return plan


def _dove_e_finito(db):
    """Il path REALE del file quarantenato: `quarantine_path_for` non normalizza,
    e una base sbagliata ci infila dentro una catena di ".." che porta altrove."""
    row = db.scalar(select(UndoJournal).where(UndoJournal.kind == "DELETE"))
    return Path(os.path.realpath(row.quarantine_path))


def test_delete_resta_in_quarantena_con_cartella_non_configurata(db, tmp_path, copy_fixture,
                                                                 monkeypatch):
    """Cartella non configurata = base vuota: `os.path.relpath(path, "")` la
    risolve contro la cwd del server e il join produce un path relativo pieno di
    "..", che riporta il file fuori da qualsiasi .quarantine."""
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    root = tmp_path / "lib"
    src = copy_fixture("flac", root / "House" / "x.flac")   # location default: "inbox"
    plan = _piano_di_solo_delete(db, root, src)
    res = apply_plan(db, plan)
    assert res.applied_ops == 1 and res.partial is False
    assert not os.path.exists(src)
    finale = _dove_e_finito(db)
    assert ".quarantine" in finale.parts, f"file uscito dalla quarantena: {finale}"
    assert finale.exists()


def test_delete_resta_in_quarantena_se_il_file_non_sta_sotto_la_base(db, tmp_path, copy_fixture,
                                                                     monkeypatch):
    """LIBRARY_ROOT cambiata e non ancora ri-scansionata: la riga dice
    location="library" ma il path punta alla cartella vecchia. La base derivata
    non contiene il file, e senza guardia il join lo sposta fuori."""
    monkeypatch.setattr(settings, "library_root", str(tmp_path / "nuova" / "sotto"))
    monkeypatch.setattr(settings, "slskd_download_dir", str(tmp_path / "inbox"))
    vecchia = tmp_path / "vecchia"
    src = copy_fixture("flac", vecchia / "House" / "x.flac")
    plan = _piano_di_solo_delete(db, vecchia, src, location="library")
    res = apply_plan(db, plan)
    assert res.applied_ops == 1 and res.partial is False
    assert not os.path.exists(src)
    finale = _dove_e_finito(db)
    assert ".quarantine" in finale.parts, f"file uscito dalla quarantena: {finale}"
    assert finale.exists()
