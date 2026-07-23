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


def test_edit_reconcile_clear_branch(db, tmp_path, copy_fixture):
    # svuotare un campo che ha un'issue aperta → issue accepted con action "clear"
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"label": "Old"})
    file = _seed(db, f, label="Old")
    db.add(Issue(file_id=1, type="dirty_label", field="label",
                 severity="info", detail="dirty", status="open"))
    db.commit()
    manual_edit.edit_tags(db, file, {"label": ""})
    iss = db.scalar(select(Issue).where(Issue.field == "label"))
    assert iss.status == "accepted"
    assert iss.suggested_fix_json == {"field": "label", "action": "clear",
                                      "source": "manual"}


def test_edit_write_failure_is_controlled(db, tmp_path, copy_fixture, monkeypatch):
    # una TagWriteError diventa un ManualEditError(500); la voce di journal resta
    # (innocua) e il DB NON viene allineato.
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f, artist="Old")

    def boom(*a, **k):
        raise tagio.TagWriteError("disk on fire")

    monkeypatch.setattr(tagio, "write_tags", boom)
    with pytest.raises(manual_edit.ManualEditError) as e:
        manual_edit.edit_tags(db, file, {"artist": "New"})
    assert e.value.status == 500 and e.value.code == "tag_write_failed"
    assert db.scalar(select(Plan)) is not None        # journal resta
    assert db.get(AudioFile, 1).artist == "Old"       # DB non allineato


def test_edit_mp3_comment_is_honest_noop(db, tmp_path, copy_fixture):
    # comment non si scrive su mp3 (limite EasyID3): l'edit NON deve lasciare il
    # DB divergente né una run fantasma in History.
    f = copy_fixture("mp3", tmp_path / "lib" / "x.mp3")
    file = _seed(db, f, ext="mp3", comment=None)
    manual_edit.edit_tags(db, file, {"comment": "won't land"})
    assert tagio.read_tags(f).comment is None          # disco: invariato
    assert db.get(AudioFile, 1).comment is None         # DB: allineato al disco
    assert db.scalar(select(Plan)) is None              # nessuna run fantasma


def test_edit_mp3_partial_landing(db, tmp_path, copy_fixture):
    # artist atterra, comment no: DB riflette il disco reale; la run registra solo
    # i campi davvero cambiati; l'undo ripristina solo quelli.
    f = copy_fixture("mp3", tmp_path / "lib" / "x.mp3")
    file = _seed(db, f, ext="mp3", artist=None, comment=None)
    manual_edit.edit_tags(db, file, {"artist": "Landed", "comment": "won't land"})
    assert db.get(AudioFile, 1).artist == "Landed"
    assert db.get(AudioFile, 1).comment is None
    plan = db.scalar(select(Plan))
    assert plan is not None and plan.rules_json["fields"] == ["artist"]
    from app.models import UndoJournal
    j = db.scalar(select(UndoJournal).where(UndoJournal.run_id == plan.id))
    assert j.prior_tags_json == {"artist": None}        # solo il campo atterrato


def test_edit_flac_comment_still_works(db, tmp_path, copy_fixture):
    # regressione: su flac il comment si scrive → run creata, DB = disco.
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f, comment=None)
    manual_edit.edit_tags(db, file, {"comment": "kept"})
    assert tagio.read_tags(f).comment == "kept"
    assert db.get(AudioFile, 1).comment == "kept"
    assert db.scalar(select(Plan)) is not None
