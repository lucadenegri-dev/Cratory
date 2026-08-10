from sqlalchemy import select

from app.models import AudioFile, Issue
from app.services.analysis import recompute


def _add_file(db, **kw):
    defaults = dict(root_id=1, path="/m/x.mp3", ext="mp3", size_bytes=1, hash_method="file",
                    status="present", has_cover=False)
    defaults.update(kw)
    f = AudioFile(**defaults)
    db.add(f)
    db.commit()
    return f


def test_recompute_creates_issues(db):
    _add_file(db, path="/m/a.mp3", artist="", title="", content_hash="a")
    summary = recompute(db)
    issues = db.scalars(select(Issue)).all()
    assert any(i.type == "missing_required_tag" for i in issues)
    assert summary.issues_total == len(issues)


def test_dismissed_survives_recompute(db):
    _add_file(db, path="/m/a.mp3", artist="A", title="T", genre=None, year=2020, label="X",
              duration_s=200.0, bitrate=320000, content_hash="a")
    recompute(db)
    genre_issue = db.scalar(select(Issue).where(Issue.type == "missing_metadata",
                                                Issue.field == "genre"))
    genre_issue.status = "dismissed"
    db.commit()
    recompute(db)
    again = db.scalar(select(Issue).where(Issue.type == "missing_metadata",
                                          Issue.field == "genre"))
    assert again.status == "dismissed"


def test_accepted_suggested_fix_survives_recompute(db):
    # Issue ancora valida (genere mancante) ma con una decisione utente:
    # l'AI/utente ha impostato un valore e l'ha accettata → non deve essere azzerata.
    _add_file(db, path="/m/a.mp3", artist="A", title="T", genre=None, year=2020, label="X",
              duration_s=200.0, bitrate=320000, content_hash="a")
    recompute(db)
    issue = db.scalar(select(Issue).where(Issue.type == "missing_metadata",
                                          Issue.field == "genre"))
    issue.status = "accepted"
    issue.suggested_fix_json = {"field": "genre", "action": "retag", "to": "Techno"}
    db.commit()
    recompute(db)
    again = db.scalar(select(Issue).where(Issue.type == "missing_metadata",
                                          Issue.field == "genre"))
    assert again.status == "accepted"
    assert again.suggested_fix_json == {"field": "genre", "action": "retag", "to": "Techno"}


def test_open_ai_suggestion_not_wiped_to_none(db):
    # Anche su issue 'open': un suggerimento già presente (es. AI) non va azzerato
    # quando l'Inspector non ne calcola uno (missing_* → None).
    _add_file(db, path="/m/b.mp3", artist="", title="", content_hash="b")
    recompute(db)
    issue = db.scalar(select(Issue).where(Issue.type == "missing_required_tag",
                                          Issue.field == "artist"))
    issue.suggested_fix_json = {"field": "artist", "action": "retag", "to": "Kai Tracid"}
    db.commit()
    recompute(db)
    again = db.scalar(select(Issue).where(Issue.type == "missing_required_tag",
                                          Issue.field == "artist"))
    assert again.suggested_fix_json == {"field": "artist", "action": "retag", "to": "Kai Tracid"}


def test_stale_issue_deleted(db):
    f = _add_file(db, path="/m/a.mp3", artist="A", title="T", genre=None, year=2020,
                  label="X", duration_s=200.0, bitrate=320000, content_hash="a")
    recompute(db)
    assert db.scalar(select(Issue).where(Issue.field == "genre")) is not None
    f.genre = "House"  # buco riempito
    db.commit()
    recompute(db)
    assert db.scalar(select(Issue).where(Issue.field == "genre")) is None


def test_genre_review_survives_recompute_in_every_status(db):
    # genre_review è synthetic (creata dal job di revisione generi, non
    # dall'Inspector): un recompute() non deve mai cancellarla, in nessuno
    # stato — altrimenti ogni scan (anche automatico, dopo un apply) azzera
    # l'intero output del job.
    f1 = _add_file(db, path="/m/open.mp3", artist="A", title="T1", genre="House",
                   content_hash="o")
    f2 = _add_file(db, path="/m/accepted.mp3", artist="B", title="T2", genre="House",
                   content_hash="acc")
    f3 = _add_file(db, path="/m/dismissed.mp3", artist="C", title="T3", genre="House",
                   content_hash="dis")
    fix = {"field": "genre", "action": "retag", "to": "Techno",
           "source": "ai", "confidence": "high"}
    db.add(Issue(file_id=f1.id, type="genre_review", field="genre", severity="info",
                 detail="AI: genre → Techno", suggested_fix_json=fix, status="open"))
    db.add(Issue(file_id=f2.id, type="genre_review", field="genre", severity="info",
                 detail="AI: genre → Techno", suggested_fix_json=fix, status="accepted"))
    db.add(Issue(file_id=f3.id, type="genre_review", field="genre", severity="info",
                 detail="AI: genre → Techno", suggested_fix_json=fix, status="dismissed"))
    db.commit()

    recompute(db)

    rows = db.scalars(select(Issue).where(Issue.type == "genre_review")).all()
    statuses = {r.file_id: r.status for r in rows}
    assert statuses == {f1.id: "open", f2.id: "accepted", f3.id: "dismissed"}


def test_recompute_deletes_orphaned_bridge_mismatch(db):
    # bridge_mismatch era un tipo di issue legacy (bridge Cratory) che l'Inspector
    # non ricalcola più: T9 ha rimosso l'esenzione _EXTERNAL_TYPES, quindi il
    # recompute deve cancellarle a prescindere dallo status, come qualsiasi altra
    # issue orfana non più prodotta.
    f = _add_file(db, path="/m/a.mp3", artist="A", title="T", genre="House", year=2020,
                  label="X", duration_s=200.0, bitrate=320000, content_hash="a")
    db.add(Issue(file_id=f.id, type="bridge_mismatch", field="bpm", severity="warning",
                 detail="bpm diverso dal bridge", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=f.id, type="bridge_mismatch", field="key", severity="warning",
                 detail="key diversa dal bridge", suggested_fix_json=None, status="dismissed"))
    db.add(Issue(file_id=f.id, type="bridge_mismatch", field="energy", severity="warning",
                 detail="energy diversa dal bridge", suggested_fix_json=None, status="accepted"))
    db.commit()
    assert db.scalars(select(Issue).where(Issue.type == "bridge_mismatch")).all()

    recompute(db)

    assert db.scalars(select(Issue).where(Issue.type == "bridge_mismatch")).all() == []
