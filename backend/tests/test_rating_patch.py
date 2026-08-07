"""Voto via PATCH /api/tracks/{id}: assegna, cambia, toglie, valida 1..3."""

import pytest
from pydantic import ValidationError

from app.models import Track
from app.routers import tracks
from app.schemas import TrackUpdateIn


def _track(db, **kw) -> Track:
    t = Track(source_type="spotify", title="X", artist="Y", **kw)
    db.add(t)
    db.commit()
    return t


def test_patch_assegna_cambia_toglie(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=2), db)
    db.refresh(t)
    assert t.rating == 2
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    db.refresh(t)
    assert t.rating == 3
    tracks.patch_track(t.id, TrackUpdateIn(rating=None), db)  # null esplicito = toglie
    db.refresh(t)
    assert t.rating is None


def test_patch_senza_rating_non_tocca(db):
    t = _track(db, rating=3)
    tracks.patch_track(t.id, TrackUpdateIn(title="Nuovo"), db)
    db.refresh(t)
    assert t.rating == 3


@pytest.mark.parametrize("bad", [0, 4, -1])
def test_rating_fuori_range_rifiutato(bad):
    with pytest.raises(ValidationError):
        TrackUpdateIn(rating=bad)
