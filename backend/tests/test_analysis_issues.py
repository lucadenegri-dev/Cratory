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


def test_recompute_preserves_bridge_mismatch(db):
    # bridge_mismatch non è calcolata dall'Inspector (viene da Cratory):
    # il merge non deve cancellarla, la riconcilia /api/issues/bridge-suggest.
    _add_file(db, path="/m/a.mp3", artist="Sconosciuto", title="Acid Face",
              genre="Techno", year=2020, label="X",
              duration_s=200.0, bitrate=320000, content_hash="a", isrc="DEAB12300123")
    f = db.scalar(select(AudioFile))
    db.add(Issue(file_id=f.id, type="bridge_mismatch", field="artist",
                 severity="warning", detail="Cratory (ISRC): artist diverso",
                 suggested_fix_json={"field": "artist", "action": "retag", "to": "Rataxes"},
                 status="open"))
    db.commit()
    recompute(db)
    kept = db.scalars(select(Issue).where(Issue.type == "bridge_mismatch")).all()
    assert len(kept) == 1
    assert kept[0].suggested_fix_json == {"field": "artist", "action": "retag",
                                          "to": "Rataxes"}
    assert kept[0].status == "open"
