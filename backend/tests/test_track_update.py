"""Modifica manuale dei valori di una traccia (PATCH /api/tracks/{id}).

L'utente puo' inserire/correggere a mano BPM, key, energia... e quei valori
sovrascrivono sempre i dati gia' presenti. Test diretti su repository + router
(niente TestClient: stesso stile degli altri test del progetto).
"""

import pytest
from fastapi import HTTPException

from app.models import Track
from app.repositories import update_track
from app.routers import tracks
from app.schemas import TrackUpdateIn


def _track(db, **kw) -> Track:
    t = Track(source_type="spotify", title="X", artist="Y", **kw)
    db.add(t)
    db.commit()
    return t


def test_update_sets_features(db):
    t = _track(db, status="imported")
    update_track(db, t, {"bpm": 128.0, "camelot_key": "8A", "energy": 70})
    assert t.bpm == 128.0
    assert t.camelot_key == "8A"
    assert t.energy == 70
    assert t.status == "ready_for_set"  # bpm + key presenti


def test_manual_overrides_existing_value(db):
    t = _track(db, bpm=120.0, camelot_key="5A")
    update_track(db, t, {"bpm": 124.0})
    assert t.bpm == 124.0  # la modifica manuale sovrascrive il dato precedente


def test_empty_string_clears_field(db):
    t = _track(db, genre="techno")
    update_track(db, t, {"genre": ""})
    assert t.genre is None


def test_editing_only_metadata_leaves_features_untouched(db):
    t = _track(db, bpm=120.0)
    update_track(db, t, {"title": "Nuovo titolo"})
    assert t.title == "Nuovo titolo"
    assert t.bpm == 120.0  # non e' stato toccato


def test_patch_route_rejects_invalid_camelot(db):
    t = _track(db)
    with pytest.raises(HTTPException) as ei:
        tracks.patch_track(t.id, TrackUpdateIn(camelot_key="99Z"), db)
    assert ei.value.status_code == 422


def test_patch_route_normalizes_and_applies(db):
    t = _track(db, status="imported")
    out = tracks.patch_track(t.id, TrackUpdateIn(bpm=130, camelot_key="8a"), db)
    assert out.bpm == 130.0
    assert out.camelot_key == "8A"  # normalizzata in maiuscolo
    assert out.status == "ready_for_set"


def test_patch_route_404_for_missing_track(db):
    with pytest.raises(HTTPException) as ei:
        tracks.patch_track(999999, TrackUpdateIn(bpm=120), db)
    assert ei.value.status_code == 404


def test_patch_partial_leaves_unset_fields_untouched(db):
    t = _track(db, bpm=128.0, camelot_key="8A", genre="Techno")
    tracks.patch_track(t.id, TrackUpdateIn(energy=80), db)
    assert t.energy == 80
    assert t.bpm == 128.0      # non fornito: invariato
    assert t.camelot_key == "8A"
    assert t.genre == "Techno"
