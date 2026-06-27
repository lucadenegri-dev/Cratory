from sqlalchemy import select

from app.models import AudioFile, Issue, Plan, PlanOp, ScanRoot
from app.services import planning


def test_get_settings_seeds_defaults(db):
    s = planning.get_settings(db)
    assert s.naming_template == "{artist} - {title}"
    assert s.folder_template == "{genre}/{artist}"


def test_update_settings(db):
    planning.get_settings(db)
    s = planning.update_settings(db, folder_template="{genre}")
    assert s.folder_template == "{genre}" and s.naming_template == "{artist} - {title}"


def test_set_root_target_and_map(db):
    root = ScanRoot(id=1, path="/lib")
    db.add(root)
    db.commit()
    planning.set_root_target(db, 1, "/lib/Library")
    assert planning.root_targets(db) == {1: "/lib/Library"}
    planning.set_root_target(db, 1, None)  # in-place → la radice stessa
    assert planning.root_targets(db) == {1: "/lib"}


def _file(db, fid, **kw):
    defaults = dict(id=fid, root_id=1, path=f"/lib/varie/{fid}.mp3", ext="mp3", size_bytes=1000,
                    hash_method="file", status="present", has_cover=False,
                    artist="A", title=f"T{fid}", genre="House")
    defaults.update(kw)
    f = AudioFile(**defaults)
    db.add(f)
    db.commit()
    return f


def test_create_plan_persists_and_replaces_draft(db):
    db.add(ScanRoot(id=1, path="/lib"))
    _file(db, 1)
    p1 = planning.create_plan(db)
    assert p1.stats.n_move == 1
    assert db.scalar(select(Plan)) is not None
    p2 = planning.create_plan(db)  # sostituisce il draft
    assert len(db.scalars(select(Plan)).all()) == 1  # un solo draft
    assert len(db.scalars(select(PlanOp)).all()) == p2.stats.n_move


def test_plan_includes_retag_and_delete_and_stats(db):
    db.add(ScanRoot(id=1, path="/lib"))
    _file(db, 1, artist="PINCO")
    _file(db, 2)
    db.add(Issue(file_id=1, type="inconsistent_casing", field="artist", severity="warning",
                 detail="", suggested_fix_json={"field": "artist", "action": "retag",
                 "to": "Pinco"}, status="accepted"))
    from app.models import DupMember, DupGroup
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
