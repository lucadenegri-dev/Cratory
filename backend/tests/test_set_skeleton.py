"""Fase 1 del set generator: scheletro (impatto, piano di genere, anchor)."""

from app.models import Track
from app.services.set_skeleton import impact_scores, plan_genre_families


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


# --- piano di genere -----------------------------------------------------------


def test_plan_none_when_pool_is_dominated_by_one_family():
    pool = ([make_track(id=i, genre="Techno") for i in range(1, 10)]
            + [make_track(id=99, genre="House")])
    assert plan_genre_families(pool) is None  # 90% techno: degenera


def test_plan_none_without_a_second_qualified_family():
    # 75% techno (sotto l'80%) ma nessun'altra famiglia raggiunge il 15%.
    pool = ([make_track(id=i, genre="Techno") for i in range(1, 7)]
            + [make_track(id=7, genre="Weirdcore"), make_track(id=8)])
    assert plan_genre_families(pool) is None


def test_plan_picks_principal_by_count_and_calm_by_energy():
    pool = ([make_track(id=i, genre="Techno", energy=80) for i in range(1, 6)]
            + [make_track(id=10 + i, genre="House", energy=40) for i in range(3)]
            + [make_track(id=20 + i, genre="Ambient", energy=20) for i in range(2)])
    plan = plan_genre_families(pool)
    assert plan is not None
    assert plan.principal == "techno"   # famiglia piu' numerosa
    assert plan.calm == "chill"         # tra le qualificate, energia media piu' bassa


def test_plan_calm_falls_back_to_bpm_when_energy_missing():
    pool = ([make_track(id=i, genre="Techno", bpm=140.0) for i in range(1, 6)]
            + [make_track(id=10 + i, genre="House", bpm=124.0) for i in range(3)]
            + [make_track(id=20 + i, genre="Trance", bpm=138.0) for i in range(2)])
    plan = plan_genre_families(pool)
    assert plan is not None and plan.calm == "house"  # BPM medio piu' basso
