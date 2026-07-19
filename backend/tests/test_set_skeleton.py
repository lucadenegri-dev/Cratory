"""Fase 1 del set generator: scheletro (impatto, piano di genere, anchor)."""

from app.models import Track
from app.services.set_skeleton import impact_scores


def make_track(**kw) -> Track:
    kw.setdefault("source_type", "spotify")
    kw.setdefault("duration_seconds", 300)
    return Track(**kw)


# --- punteggio di impatto ------------------------------------------------------


def test_impact_ordering_follows_energy_then_bpm():
    lo = make_track(id=1, bpm=120.0, energy=30)
    mid = make_track(id=2, bpm=125.0, energy=60)
    hi = make_track(id=3, bpm=130.0, energy=95)
    imp = impact_scores([lo, mid, hi])
    assert imp[3] > imp[2] > imp[1]
    assert imp[3] == 1.0 and imp[1] == 0.0  # percentili estremi


def test_impact_without_energy_falls_back_to_bpm():
    # Nessuna traccia ha energia: conta solo il percentile BPM.
    a = make_track(id=1, bpm=120.0)
    b = make_track(id=2, bpm=128.0)
    c = make_track(id=3, bpm=140.0)
    imp = impact_scores([a, b, c])
    assert imp[3] > imp[2] > imp[1]


def test_impact_mixed_pool_track_without_energy_uses_bpm_only():
    with_e = make_track(id=1, bpm=120.0, energy=90)
    without_e = make_track(id=2, bpm=140.0)
    other = make_track(id=3, bpm=125.0, energy=50)
    imp = impact_scores([with_e, without_e, other])
    assert imp[2] == 1.0  # solo BPM per lei, ed e' il BPM piu' alto


def test_impact_single_track_is_neutral():
    only = make_track(id=1, bpm=128.0, energy=70)
    assert impact_scores([only]) == {1: 0.5}
