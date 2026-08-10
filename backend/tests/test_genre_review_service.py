"""Test del service di revisione generi (Task 1: colonna; Task 4: logica)."""

from app.models import AudioFile


def _file(db, fid, *, artist=None, title=None, genre=None, album=None,
          label=None, reviewed=None, path=None):
    f = AudioFile(id=fid, root_id=1, path=path or f"/m/{fid}.mp3", ext="mp3",
                  size_bytes=1, hash_method="file", status="present",
                  has_cover=False, artist=artist, title=title, genre=genre,
                  album=album, label=label, genre_reviewed_at=reviewed)
    db.add(f)
    db.commit()
    return f


def test_genre_reviewed_at_column_defaults_none(db):
    f = _file(db, 1, artist="ANNA", title="Hidden Beauties")
    assert f.genre_reviewed_at is None


from sqlalchemy import select

from app.models import Issue
from app.services import genre_review


class _MB:
    """MusicBrainz finto: risponde con candidati fissi (o None)."""
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def lookup(self, **kw):
        self.calls.append(kw)
        return self.result


class _DG:
    def __init__(self, result=None):
        self.result = result

    def lookup(self, **kw):
        return self.result


def _ai_returning(*proposals):
    """ai_fn finto: risponde con le proposte date, allineate all'input."""
    def fn(items):
        assert len(items) == len(proposals)
        return list(proposals)
    return fn


def _issues(db, fid):
    return db.scalars(select(Issue).where(Issue.file_id == fid)).all()


def test_count_candidates_skips_reviewed_unless_redo(db):
    from app.models import utcnow
    _file(db, 1, artist="A", title="T1")
    _file(db, 2, artist="B", title="T2", reviewed=utcnow())
    assert genre_review.count_candidates(db) == 1
    assert genre_review.count_candidates(db, redo=True) == 2


def test_review_proposes_genre_review_issue_when_differs(db):
    f = _file(db, 1, artist="ANNA", title="Hidden Beauties", genre="House")
    res = genre_review.review(
        db, mb=_MB({"genre_candidates": ["Techno"]}), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["proposed"] == 1 and res["confirmed"] == 0
    (issue,) = _issues(db, 1)
    assert issue.type == "genre_review" and issue.field == "genre"
    assert issue.status == "open"
    assert issue.suggested_fix_json == {
        "field": "genre", "action": "retag", "to": "Techno",
        "source": "ai", "confidence": "high"}
    assert f.genre_reviewed_at is not None


def test_review_confirm_same_genre_no_issue_and_closes_stale(db):
    _file(db, 1, artist="A", title="T", genre="tech house")  # casing diverso
    db.add(Issue(file_id=1, type="genre_review", field="genre", severity="info",
                 detail="vecchia proposta", status="open",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "ai"}))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Tech House", "confidence": "high"}))
    assert res["confirmed"] == 1 and res["proposed"] == 0
    assert _issues(db, 1) == []  # la genre_review aperta e ora inutile sparisce


def test_review_fills_open_missing_metadata_issue(db):
    _file(db, 1, artist="A", title="T", genre=None)
    db.add(Issue(file_id=1, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=None, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Dub Techno", "confidence": "low"}))
    assert res["proposed"] == 1
    (issue,) = _issues(db, 1)  # nessuna issue duplicata
    assert issue.type == "missing_metadata"
    assert issue.suggested_fix_json["to"] == "Dub Techno"
    assert issue.suggested_fix_json["source"] == "ai"


def test_review_never_overwrites_provider_suggestion(db):
    _file(db, 1, artist="A", title="T", genre=None)
    provider_fix = {"field": "genre", "action": "retag", "to": "House",
                    "source": "provider", "confidence": "high"}
    db.add(Issue(file_id=1, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=provider_fix, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["skipped"] == 1 and res["proposed"] == 0
    (issue,) = _issues(db, 1)
    assert issue.suggested_fix_json == provider_fix  # intatto


def test_review_skips_when_provider_override_open(db):
    _file(db, 1, artist="A", title="T", genre="House")
    db.add(Issue(file_id=1, type="provider_override", field="genre",
                 severity="info", detail="provider: genre → Techno",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "provider",
                                     "confidence": "strong"}, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Minimal", "confidence": "low"}))
    assert res["skipped"] == 1
    assert len(_issues(db, 1)) == 1  # nessuna seconda issue sul campo genre


def test_review_none_is_unresolved_but_marks_reviewed(db):
    f = _file(db, 1, artist="A", title="T", genre="House")
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": None, "confidence": "low"}))
    assert res["unresolved"] == 1
    assert _issues(db, 1) == []
    assert f.genre_reviewed_at is not None


def test_review_respects_user_decision_on_genre_review(db):
    _file(db, 1, artist="A", title="T", genre="House")
    db.add(Issue(file_id=1, type="genre_review", field="genre", severity="info",
                 detail="AI: genre → Techno", status="dismissed",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "ai"}))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["skipped"] == 1
    (issue,) = _issues(db, 1)
    assert issue.status == "dismissed"  # decisione utente intoccata


def test_review_ai_failure_counts_unresolved_and_continues(db):
    _file(db, 1, artist="A", title="T")
    _file(db, 2, artist="B", title="U")

    def boom(items):
        raise RuntimeError("api down")

    res = genre_review.review(db, mb=_MB(None), discogs=_DG(None), ai_fn=boom)
    assert res["unresolved"] == 2
    assert res["files"] == 2


def test_review_candidates_merged_normalized_deduped(db):
    _file(db, 1, artist="A", title="T")
    captured = {}

    def fn(items):
        captured["items"] = items
        return [{"genre": None, "confidence": "low"}]

    genre_review.review(
        db,
        mb=_MB({"genre_candidates": ["tech house", "techno"],
                "genre_primary": "tech house"}),
        discogs=_DG({"genre_candidates": ["Tech House", "Electronic"]}),
        ai_fn=fn)
    assert captured["items"][0]["candidates"] == \
        ["Tech House", "Techno", "Electronic"]


def test_review_progress_phases(db):
    _file(db, 1, artist="A", title="T")
    seen = []
    genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": None, "confidence": "low"}),
        on_progress=lambda p, t, ph: seen.append((p, t, ph)))
    assert ("looking_up" in {ph for _, _, ph in seen})
    assert seen[-1] == (1, 1, "reviewing")
