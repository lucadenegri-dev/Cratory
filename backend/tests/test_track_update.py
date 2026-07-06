"""Modifica manuale dei valori di una traccia (PATCH /api/tracks/{id}).

L'utente puo' inserire/correggere a mano BPM, key, genere... e quei valori
sovrascrivono sempre i dati gia' presenti. L'energia invece e' sempre derivata
(services/energy): non e' un campo modificabile a mano, si ricalcola quando
cambiano bpm/genere. Test diretti su repository + router (niente TestClient:
stesso stile degli altri test del progetto).
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import Track
from app.repositories import update_track
from app.routers import tracks
from app.schemas import TrackUpdateIn
from app.services.energy import estimate_energy


def _track(db, **kw) -> Track:
    t = Track(source_type="spotify", title="X", artist="Y", **kw)
    db.add(t)
    db.commit()
    return t


def test_update_sets_features(db):
    t = _track(db, status="imported")
    update_track(db, t, {"bpm": 128.0, "camelot_key": "8A"})
    assert t.bpm == 128.0
    assert t.camelot_key == "8A"
    assert t.energy == estimate_energy(128.0, None, None)  # derivata dal bpm
    assert t.status == "ready_for_set"  # bpm + key presenti


def test_energy_field_rejected_by_schema(db):
    """L'energia non e' piu' un campo modificabile a mano: extra="forbid" deve
    rifiutare qualunque payload che la contenga (422 a monte, mai in repository)."""
    with pytest.raises(ValidationError):
        TrackUpdateIn(energy=70)


def test_patching_bpm_recomputes_energy(db):
    """Un patch che cambia il bpm deve ricalcolare l'energia derivata, cosi'
    non resta stantia dopo una modifica manuale."""
    t = _track(db, bpm=100.0, genre="ambient")
    update_track(db, t, {"bpm": 100.0})  # ricalcolo esplicito: stesso bpm, forziamo il path
    old_energy = t.energy
    update_track(db, t, {"bpm": 150.0})
    assert t.energy == estimate_energy(150.0, None, "ambient")
    assert t.energy != old_energy


def test_patching_genre_recomputes_energy(db):
    """Un patch che cambia il genere deve ricalcolare l'energia derivata (il
    genere modula lo score in services/energy)."""
    t = _track(db, bpm=140.0, genre="ambient")
    update_track(db, t, {"bpm": 140.0})
    ambient_energy = t.energy
    update_track(db, t, {"genre": "techno"})
    assert t.energy == estimate_energy(140.0, None, "techno")
    assert t.energy != ambient_energy


def test_patching_without_bpm_or_genre_leaves_energy_untouched(db):
    t = _track(db, bpm=128.0, genre="techno")
    update_track(db, t, {"bpm": 128.0})
    energy_before = t.energy
    update_track(db, t, {"title": "Nuovo titolo"})
    assert t.energy == energy_before


def test_patching_bpm_without_existing_bpm_before_leaves_no_energy_if_no_bpm(db):
    """Se la traccia non ha bpm (ne' prima ne' nel patch), l'energia resta None:
    non si inventa un valore senza bpm."""
    t = _track(db, genre="techno")
    update_track(db, t, {"genre": "house"})
    assert t.bpm is None
    assert t.energy is None


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
    tracks.patch_track(t.id, TrackUpdateIn(label="Kompakt"), db)
    assert t.label == "Kompakt"
    assert t.bpm == 128.0      # non fornito: invariato
    assert t.camelot_key == "8A"
    assert t.genre == "Techno"


def test_patch_route_rejects_energy_field(db):
    """Il router valida il body con TrackUpdateIn (extra="forbid"): un payload
    con 'energy' deve fallire la validazione Pydantic prima ancora di arrivare
    al repository. FastAPI la traduce in 422 a runtime; qui verifichiamo il
    contratto dello schema direttamente."""
    with pytest.raises(ValidationError):
        TrackUpdateIn(bpm=128, energy=80)
