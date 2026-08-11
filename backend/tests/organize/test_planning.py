from sqlalchemy import select

from app.organize.models import AudioFile, Issue, Plan, PlanOp, ScanRoot, UndoJournal
from app.organize.services import planning


def test_get_settings_seeds_defaults(db):
    s = planning.get_settings(db)
    assert s.naming_template == "{artist} - {title}"
    assert s.folder_template == "{genre}/{artist}"


def test_update_settings(db):
    planning.get_settings(db)
    s = planning.update_settings(db, folder_template="{genre}")
    assert s.folder_template == "{genre}" and s.naming_template == "{artist} - {title}"


def test_set_root_target_and_map(db):
    # Mappa non esclusiva: conftest.SEEDED_SCAN_ROOT_IDS semina 1/2, verifica solo id 3.
    root = ScanRoot(id=3, path="/lib")
    db.add(root)
    db.commit()
    planning.set_root_target(db, 3, "/lib/Library")
    assert planning.root_targets(db)[3] == "/lib/Library"
    planning.set_root_target(db, 3, None)  # in-place → la radice stessa
    assert planning.root_targets(db)[3] == "/lib"


def _file(db, fid, **kw):
    defaults = dict(id=fid, root_id=3, path=f"/lib/varie/{fid}.mp3", ext="mp3", size_bytes=1000,
                    hash_method="file", status="present", has_cover=False,
                    artist="A", title=f"T{fid}", genre="House")
    defaults.update(kw)
    f = AudioFile(**defaults)
    db.add(f)
    db.commit()
    return f


def test_create_plan_persists_and_replaces_draft(db):
    db.add(ScanRoot(id=3, path="/lib"))
    _file(db, 1)
    p1 = planning.create_plan(db)
    assert p1.stats.n_move == 1
    assert db.scalar(select(Plan)) is not None
    p2 = planning.create_plan(db)  # sostituisce il draft
    assert len(db.scalars(select(Plan)).all()) == 1  # un solo draft
    assert len(db.scalars(select(PlanOp)).all()) == p2.stats.n_move


def test_plan_includes_retag_and_delete_and_stats(db):
    db.add(ScanRoot(id=3, path="/lib"))
    _file(db, 1, artist="PINCO")
    _file(db, 2)
    db.add(Issue(file_id=1, type="inconsistent_casing", field="artist", severity="warning",
                 detail="", suggested_fix_json={"field": "artist", "action": "retag",
                 "to": "Pinco"}, status="accepted"))
    from app.organize.models import DupMember, DupGroup
    db.add(DupGroup(id=1, match_kind="exact", keeper_file_id=1, signature="s"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    db.commit()
    p = planning.create_plan(db)
    assert p.stats.n_retag == 1 and p.stats.n_delete == 1
    assert p.stats.space_freed_bytes == 1000
    kinds = [o.kind for o in p.ops]
    assert kinds.index("RETAG") < kinds.index("DELETE")  # ordine


def test_load_plan_none_when_absent(db):
    assert planning.load_plan(db) is None


def test_collision_skips_ops_without_blocking(db):
    # due file → stessa dest (collisione), un terzo si muove pulito:
    # il piano NON è bloccante, gli op in conflitto sono marcati skipped.
    db.add(ScanRoot(id=3, path="/lib"))
    _file(db, 1, title="T")
    _file(db, 2, title="T")     # stesso artist+title+genre → stessa dest
    _file(db, 3, title="Solo")  # pulito
    p = planning.create_plan(db)
    assert p.stats.n_move == 3
    assert p.stats.n_skipped == 2
    assert p.stats.blocking is False
    skipped = {o.file_id for o in p.ops if o.skipped}
    assert skipped == {1, 2}


def test_blocking_only_when_nothing_applicable(db):
    db.add(ScanRoot(id=3, path="/lib"))
    _file(db, 1, title="T")
    _file(db, 2, title="T")  # solo op in collisione → niente da applicare
    p = planning.create_plan(db)
    assert p.stats.n_skipped == 2
    assert p.stats.blocking is True


def test_load_plan_flags_disk_occupied_dest(db, tmp_path):
    # la dest esiste su disco ma non nel DB (Library non scansionata) →
    # conflitto visibile già a livello di piano, op saltato.
    root = tmp_path / "lib"
    (root / "varie").mkdir(parents=True)
    src = root / "varie" / "1.mp3"; src.write_text("a")
    dest = root / "House" / "A" / "A - T1.mp3"
    dest.parent.mkdir(parents=True); dest.write_text("b")
    db.add(ScanRoot(id=3, path=str(root)))
    _file(db, 1, path=str(src))
    p = planning.create_plan(db)
    assert any("su disco" in c.detail for c in p.conflicts)
    assert p.stats.n_skipped == 1 and p.stats.blocking is True


def test_accepted_corrupt_file_enters_removals(db):
    db.add(ScanRoot(id=3, path="/lib"))
    f = _file(db, 1)
    db.add(Issue(file_id=f.id, type="corrupt_file", field=None, severity="error",
                 detail="corrotto", suggested_fix_json={"action": "quarantine"},
                 status="accepted"))
    db.commit()
    _files, _accepted, removals, _snap, _targets = planning._inputs(db)
    assert f.id in removals


def test_draft_con_journal_viene_promosso_non_cancellato(db):
    """Un piano 'draft' con righe di undo journal è un apply morto prima di
    marcarsi 'applied'. Cancellarlo distruggerebbe il journal — cioè la
    reversibilità dei file già spostati su disco — e con foreign_keys=ON
    fallirebbe comunque (UndoJournal.run_id non ha relationship())."""
    db.add(ScanRoot(id=3, path="/lib"))
    f = _file(db, 1)
    morto = Plan(status="draft", rules_json={})
    db.add(morto)
    db.flush()
    db.add(UndoJournal(run_id=morto.id, op_seq=0, kind="MOVE", file_id=f.id,
                       from_path="/lib/a.mp3", to_path="/lib/b.mp3"))
    db.commit()
    morto_id = morto.id

    planning.create_plan(db)

    promosso = db.get(Plan, morto_id)
    assert promosso is not None, "il piano col journal non deve essere cancellato"
    assert promosso.status == "applied"
    assert db.scalar(select(UndoJournal).where(UndoJournal.run_id == morto_id)) is not None


def test_draft_senza_journal_viene_cancellato(db):
    """La bozza normale resta usa-e-getta: senza journal non c'è nulla da salvare."""
    db.add(ScanRoot(id=3, path="/lib"))
    _file(db, 1)
    # Marcatore invece dell'id: SQLite riusa il rowid, quindi il piano nuovo
    # rinascerebbe con lo stesso id di quello appena cancellato.
    db.add(Plan(status="draft", rules_json={"marcatore": "bozza-vecchia"}))
    db.commit()

    planning.create_plan(db)

    superstiti = db.scalars(select(Plan)).all()
    assert len(superstiti) == 1
    assert superstiti[0].rules_json.get("marcatore") is None
