"""Fase 1 del set generator: scheletro (impatto, piano di genere, anchor)."""

from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.set_skeleton import build_skeleton, impact_scores, plan_genre_families, strategy_profile


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


# --- scheletro: anchor, riserva, segmenti --------------------------------------


def _pool(n: int = 16, genre: str = "Techno") -> list[Track]:
    """Pool sintetico: energie e BPM crescenti, artisti tutti diversi."""
    return [make_track(id=i, title=f"T{i}", artist=f"Art{i}",
                       bpm=120.0 + i, energy=10 + i * 5, genre=genre)
            for i in range(1, n + 1)]


def _build(pool, strategy: str = "smooth", minutes: int = 70, **req_kw):
    req = SetGenerationRequest(target_duration_minutes=minutes,
                               strategy=strategy, **req_kw)
    return build_skeleton(pool, req, strategy_profile(strategy),
                          start_bpm=125.0, end_bpm=125.0,
                          target_seconds=minutes * 60)


def test_skeleton_none_for_short_sets():
    # 20 min / ~300s a traccia = 4 tracce attese: sotto la soglia di 6.
    assert _build(_pool(), minutes=20) is None


def test_skeleton_none_for_tiny_pool():
    assert _build(_pool(n=7)) is None  # pool < 8


def test_skeleton_has_opening_peak_closing_in_order():
    sk = _build(_pool())
    roles = [a.role for a in sk.anchors]
    assert roles[0] == "opening" and roles[-1] == "closing" and "peak" in roles
    positions = [a.position for a in sk.anchors]
    assert positions == sorted(positions)
    assert len(sk.segments) == len(sk.anchors) - 1


def test_peak_anchor_is_top_impact_and_reserved():
    pool = _pool()
    sk = _build(pool)
    imp = impact_scores(pool)
    peak = next(a for a in sk.anchors if a.role == "peak")
    top3 = sorted(imp, key=lambda tid: (-imp[tid], tid))[:3]
    assert peak.track.id in top3
    assert peak.track.id in sk.reserved_ids
    # Riserva = top 15% del pool (16 -> 2 tracce), tie-break per id.
    assert sk.reserved_ids == frozenset(sorted(imp, key=lambda t: (-imp[t], t))[:2])


def test_anchors_are_distinct_and_respect_artist_cap():
    # Stesso artista su tutte le tracce + cap 1: lo scheletro non puo' eleggere
    # due anchor dello stesso artista, quindi degrada a None.
    pool = [make_track(id=i, artist="Solo", bpm=120.0 + i, energy=10 + i * 5,
                       genre="Techno") for i in range(1, 17)]
    assert _build(pool, max_tracks_per_artist=1) is None


def test_peak_position_for_descending_arc():
    # Strategia closing (arco 75->40): il momento piu' alto sta all'inizio.
    sk = _build(_pool(), strategy="closing")
    peak = next(a for a in sk.anchors if a.role == "peak")
    assert peak.position <= 0.3


def test_reset_anchors_come_from_strategy_points():
    # contrast ha reset_points (0.34, 0.67): il primo diventa anchor, il secondo
    # viene scartato perche' dista meno di _MIN_ANCHOR_GAP dal peak (0.7).
    sk = _build(_pool(), strategy="contrast")
    resets = [a for a in sk.anchors if a.role == "reset"]
    assert {round(a.position, 2) for a in resets} == {0.34}


def test_segment_families_follow_plan():
    pool = ([make_track(id=i, title=f"T{i}", artist=f"A{i}", bpm=130.0 + i % 5,
                        energy=60 + i, genre="Techno") for i in range(1, 9)]
            + [make_track(id=20 + i, title=f"H{i}", artist=f"B{i}", bpm=124.0 + i % 5,
                          energy=30 + i, genre="House") for i in range(1, 7)])
    sk = _build(pool)
    peak_segments = [s for s in sk.segments if s.end_anchor.role == "peak"]
    other_segments = [s for s in sk.segments if s.end_anchor.role != "peak"]
    assert all(s.family == "techno" for s in peak_segments)
    assert all(s.family == "house" for s in other_segments)


def test_segment_families_none_for_single_family_pool():
    sk = _build(_pool())  # tutto techno: piano degenerato
    assert all(s.family is None for s in sk.segments)
    assert sk.peak_window is not None
