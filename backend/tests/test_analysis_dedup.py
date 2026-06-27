from sqlalchemy import select

from app.models import AudioFile, DupGroup, DupMember
from app.services.analysis import recompute


def _add(db, id, **kw):
    defaults = dict(id=id, root_id=1, path=f"/m/{id}.mp3", ext="mp3", size_bytes=1,
                    hash_method="file", status="present", has_cover=False,
                    artist="A", title="T", duration_s=200.0, bitrate=320000,
                    content_hash=f"h{id}")
    defaults.update(kw)
    f = AudioFile(**defaults)
    db.add(f)
    db.commit()
    return f


def test_recompute_creates_groups(db):
    _add(db, 1, ext="flac", content_hash="a")
    _add(db, 2, ext="mp3", content_hash="b")
    summary = recompute(db)
    groups = db.scalars(select(DupGroup)).all()
    assert len(groups) == 1
    assert summary.dup_groups == 1 and summary.dup_files == 2
    assert {m.action for m in db.scalars(select(DupMember)).all()} == {"keep", "remove"}


def test_keeper_override_preserved(db):
    _add(db, 1, ext="flac", content_hash="a")  # keeper automatico = flac (id 1)
    _add(db, 2, ext="mp3", content_hash="b")
    recompute(db)
    grp = db.scalar(select(DupGroup))
    grp.keeper_file_id = 2
    grp.keeper_overridden = True
    for m in db.scalars(select(DupMember).where(DupMember.group_id == grp.id)).all():
        m.action = "keep" if m.file_id == 2 else "remove"
    db.commit()
    recompute(db)
    grp2 = db.scalar(select(DupGroup))
    assert grp2.keeper_file_id == 2 and grp2.keeper_overridden is True


def test_dismissed_preserved(db):
    _add(db, 1, ext="flac", content_hash="a")
    _add(db, 2, ext="mp3", content_hash="b")
    recompute(db)
    grp = db.scalar(select(DupGroup))
    grp.dismissed = True
    for m in db.scalars(select(DupMember).where(DupMember.group_id == grp.id)).all():
        m.action = "keep"
    db.commit()
    recompute(db)
    grp2 = db.scalar(select(DupGroup))
    assert grp2.dismissed is True
    assert {m.action for m in db.scalars(select(DupMember)).all()} == {"keep"}


def test_composition_change_new_group(db):
    _add(db, 1, ext="flac", content_hash="a")
    _add(db, 2, ext="mp3", content_hash="b")
    recompute(db)
    db.scalar(select(DupGroup)).keeper_overridden = True
    db.commit()
    _add(db, 3, ext="mp3", content_hash="c")  # entra nel gruppo → signature cambia
    recompute(db)
    grp = db.scalar(select(DupGroup))
    assert grp.keeper_overridden is False  # gruppo nuovo, keeper automatico
    assert len(db.scalars(select(DupMember)).all()) == 3
