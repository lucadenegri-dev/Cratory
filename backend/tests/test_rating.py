"""Voto a 3 livelli: colonna Track.rating e serializzazione."""

from app.models import Track
from app.serializers import track_out


def test_rating_default_none(db):
    t = Track(source_type="manual", title="T", artist="A")
    db.add(t); db.commit(); db.refresh(t)
    assert t.rating is None


def test_rating_persistito_e_serializzato(db):
    t = Track(source_type="manual", title="T", artist="A", rating=3)
    db.add(t); db.commit(); db.refresh(t)
    assert track_out(t).rating == 3


def test_rating_assente_serializzato_none(db):
    t = Track(source_type="manual", title="T", artist="A")
    db.add(t); db.commit(); db.refresh(t)
    assert track_out(t).rating is None
