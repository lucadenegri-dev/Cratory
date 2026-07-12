"""E9: il match case-insensitive ESATTO non deve trattare %/_ del valore come
wildcard LIKE. Helper condiviso `ci_equals`."""
from sqlalchemy import select

from app.models import Track
from app.repositories import ci_equals


def _add(db, title):
    db.add(Track(source_type="manual", title=title, artist="A"))
    db.commit()


def _titles(db, value):
    return [t.title for t in db.scalars(select(Track).where(ci_equals(Track.title, value))).all()]


def test_underscore_is_not_a_wildcard(db):
    _add(db, "Track_01")
    _add(db, "TrackX01")  # con ilike grezzo "_" matcherebbe anche questo
    assert _titles(db, "Track_01") == ["Track_01"]


def test_percent_is_not_a_wildcard(db):
    _add(db, "50%")
    _add(db, "5099")  # con ilike grezzo "%" matcherebbe anche questo
    assert _titles(db, "50%") == ["50%"]


def test_case_insensitive_match_still_works(db):
    _add(db, "Track_01")
    assert _titles(db, "track_01") == ["Track_01"]
