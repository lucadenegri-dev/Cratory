import os

import pytest
from sqlalchemy import select

from app.integrations import tagio
from app.models import AudioFile, Issue, Plan, ScanRoot, UndoJournal
from app.services import manual_edit
from app.services.planner import build_plan
from app.services.undo import undo_run


def _seed(db, path, **kw):
    """ScanRoot(id=1) + un AudioFile 'present' su un file reale."""
    if db.get(ScanRoot, 1) is None:
        db.add(ScanRoot(id=1, path=os.path.dirname(path)))
    d = dict(id=1, root_id=1, path=path, ext="flac", size_bytes=10, hash_method="file",
             status="present", has_cover=False, artist="Old", title="T", genre="House")
    d.update(kw)
    db.add(AudioFile(**d))
    db.commit()
    return db.get(AudioFile, 1)


def test_edit_writes_disk_and_db(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old", "title": "T"})
    file = _seed(db, f, artist="Old", title="T")
    manual_edit.edit_tags(db, file, {"artist": "New Artist", "genre": "Techno"})
    assert tagio.read_tags(f).artist == "New Artist"      # disco
    assert tagio.read_tags(f).genre == "Techno"
    assert db.get(AudioFile, 1).artist == "New Artist"    # DB allineato
    assert db.get(AudioFile, 1).genre == "Techno"


def test_edit_creates_undoable_manual_run(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old"})
    file = _seed(db, f, artist="Old")
    manual_edit.edit_tags(db, file, {"artist": "New"})
    plan = db.scalar(select(Plan))
    assert plan.status == "applied"
    assert plan.rules_json["kind"] == "manual_edit"
    j = db.scalar(select(UndoJournal).where(UndoJournal.run_id == plan.id))
    assert j.kind == "RETAG" and j.prior_tags_json == {"artist": "Old"}  # prior dal disco


def test_undo_restores_manual_edit(db, tmp_path, copy_fixture):
    # reversibilità end-to-end: l'undo della run manuale riporta il tag sul file.
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old"})
    file = _seed(db, f, artist="Old")
    manual_edit.edit_tags(db, file, {"artist": "New"})
    assert tagio.read_tags(f).artist == "New"
    plan = db.scalar(select(Plan))
    undo_run(db, plan)
    assert tagio.read_tags(f).artist == "Old"     # tag ripristinato sul disco
    assert plan.status == "undone"


def test_edit_empty_string_clears_tag(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old", "label": "ClearMe"})
    file = _seed(db, f, artist="Old", label="ClearMe")
    manual_edit.edit_tags(db, file, {"label": ""})
    assert tagio.read_tags(f).label is None
    assert db.get(AudioFile, 1).label is None


def test_edit_coerces_year_and_track(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f)
    manual_edit.edit_tags(db, file, {"year": "2003", "track_no": "5"})
    assert db.get(AudioFile, 1).year == 2003
    assert db.get(AudioFile, 1).track_no == 5


def test_edit_rejects_bad_year(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f)
    with pytest.raises(manual_edit.ManualEditError) as e:
        manual_edit.edit_tags(db, file, {"year": "notayear"})
    assert e.value.status == 400 and e.value.code == "value_invalid"


def test_edit_rejects_unknown_field(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f)
    with pytest.raises(manual_edit.ManualEditError) as e:
        manual_edit.edit_tags(db, file, {"bpm": "128"})
    assert e.value.status == 400 and e.value.code == "field_not_editable"


def test_edit_rejects_missing_file(db, tmp_path):
    file = _seed(db, str(tmp_path / "gone.flac"), status="present")
    with pytest.raises(manual_edit.ManualEditError) as e:
        manual_edit.edit_tags(db, file, {"artist": "X"})
    assert e.value.status == 409 and e.value.code == "file_not_writable"


def test_edit_noop_when_unchanged(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f, artist="Same")
    manual_edit.edit_tags(db, file, {"artist": "Same"})
    assert db.scalar(select(Plan)) is None            # nessuna run creata


def test_edit_closes_open_issue_on_field(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f, artist=None, genre="House")
    db.add(Issue(file_id=1, type="missing_required_tag", field="artist",
                 severity="error", detail="no artist", status="open"))
    db.add(Issue(file_id=1, type="dirty_genre", field="genre",
                 severity="info", detail="dirty", status="open"))
    db.commit()
    manual_edit.edit_tags(db, file, {"artist": "Fixed"})
    art = db.scalar(select(Issue).where(Issue.field == "artist"))
    gen = db.scalar(select(Issue).where(Issue.field == "genre"))
    assert art.status == "accepted"
    assert art.suggested_fix_json == {"field": "artist", "action": "retag",
                                      "to": "Fixed", "source": "manual"}
    assert gen.status == "open"                        # campo non toccato: invariato


def test_edit_leaves_no_phantom_retag(db, tmp_path, copy_fixture):
    # dopo l'edit, il DB è allineato: build_plan non deve rigenerare un RETAG.
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f, artist=None)
    db.add(Issue(file_id=1, type="missing_required_tag", field="artist",
                 severity="error", detail="no artist", status="open"))
    db.commit()
    manual_edit.edit_tags(db, file, {"artist": "Fixed"})
    accepted = db.scalars(select(Issue).where(Issue.status == "accepted")).all()
    ops = build_plan([db.get(AudioFile, 1)], accepted, removals=[],
                     settings_snapshot={"naming_template": "{artist} - {title}",
                                        "folder_template": ""},
                     root_targets={})
    assert not any(o.kind == "RETAG" for o in ops)
