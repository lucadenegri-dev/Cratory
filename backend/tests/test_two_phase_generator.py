"""Fase 2 del generatore: convergenza verso l'anchor, piano di genere, riserva."""

import pytest

from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.set_generator import _DEFAULT_PROFILE, _beam_search_span, _candidate_score
from app.services.set_skeleton import strategy_profile


def make_track(**kw) -> Track:
    kw.setdefault("source_type", "spotify")
    kw.setdefault("duration_seconds", 300)
    return Track(**kw)


def _score(prev, cand, **kw) -> float:
    total, _ = _candidate_score(prev, cand, 126.0, SetGenerationRequest(), {},
                                _DEFAULT_PROFILE, 0.5, **kw)
    return total


def test_convergence_rewards_tracks_near_the_incoming_anchor():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    near = make_track(id=2, bpm=130.0, camelot_key="9A")
    far = make_track(id=3, bpm=118.0, camelot_key="3B")
    anchor = make_track(id=9, bpm=132.0, camelot_key="10A")
    gain_near = (_score(prev, near, converge_to=anchor, converge_ramp=1.0)
                 - _score(prev, near))
    gain_far = (_score(prev, far, converge_to=anchor, converge_ramp=1.0)
                - _score(prev, far))
    assert gain_near > gain_far > 0


def test_convergence_ramp_zero_changes_nothing():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    cand = make_track(id=2, bpm=130.0, camelot_key="9A")
    anchor = make_track(id=9, bpm=132.0, camelot_key="10A")
    assert _score(prev, cand, converge_to=anchor, converge_ramp=0.0) == _score(prev, cand)


def test_reserved_track_penalized_outside_peak_window():
    prev = make_track(id=1, bpm=126.0, camelot_key="8A")
    bomb = make_track(id=2, bpm=126.0, camelot_key="8A", energy=95)
    base = _score(prev, bomb)
    # progress=0.5, finestra (0.55, 0.8): fuori -> -25
    outside = _score(prev, bomb, reserved_ids=frozenset({2}), peak_window=(0.55, 0.8))
    assert outside == base - 25.0
    # finestra che copre 0.5: nessuna penalita'
    inside = _score(prev, bomb, reserved_ids=frozenset({2}), peak_window=(0.4, 0.8))
    assert inside == base


def test_plan_family_bonus_orders_match_over_unknown_over_mismatch():
    prev = make_track(id=1, bpm=126.0, camelot_key="8A", genre="Techno")
    match = make_track(id=2, bpm=126.0, camelot_key="8A", genre="Acid")
    unknown = make_track(id=3, bpm=126.0, camelot_key="8A", genre="Weirdcore")
    mismatch = make_track(id=4, bpm=126.0, camelot_key="8A", genre="Acid House")
    s_match = _score(prev, match, plan_family="techno")
    s_unknown = _score(prev, unknown, plan_family="techno")
    # "Acid House" appartiene a techno E house: il mismatch va testato con una
    # famiglia a cui la traccia NON appartiene affatto.
    s_mismatch = _score(prev, mismatch, plan_family="dnb")
    # Il confronto isola il termine di piano: stessi prev, chiavi e BPM.
    assert s_match - _score(prev, match) == pytest.approx(100.0 * 0.20)
    assert s_unknown - _score(prev, unknown) == pytest.approx(50.0 * 0.20)
    assert s_mismatch - _score(prev, mismatch) == 0.0


# --- beam search a span --------------------------------------------------------


def _span_pool(n: int = 10) -> list[Track]:
    return [make_track(id=i, title=f"T{i}", artist=f"Art{i}",
                       bpm=124.0 + i, energy=40 + i * 3, genre="Techno")
            for i in range(1, n + 1)]


def test_span_returns_only_fillers_within_budget():
    pool = _span_pool()
    opener = pool[0]
    fillers = _beam_search_span(
        opener, pool, SetGenerationRequest(), strategy_profile("smooth"),
        125.0, 125.0, 3600,
        elapsed_secs=300, fill_until_secs=1200)  # spazio per ~3 filler da 300s
    assert 0 < len(fillers) <= 3
    ids = [t.id for t, _ in fillers]
    assert opener.id not in ids
    assert fillers[0][1] is not None  # transizione opener -> primo filler
    assert 300 + sum(t.duration_seconds for t, _ in fillers) >= 1200


def test_span_excludes_used_and_respects_artist_counts():
    pool = _span_pool()
    opener = pool[0]
    fillers = _beam_search_span(
        opener, pool, SetGenerationRequest(max_tracks_per_artist=1),
        strategy_profile("smooth"), 125.0, 125.0, 3600,
        elapsed_secs=300, fill_until_secs=1500,
        used={pool[1].id, opener.id}, artist_counts={"art3": 1})
    ids = {t.id for t, _ in fillers}
    assert pool[1].id not in ids   # gia' usato (es. anchor futuro)
    assert pool[2].id not in ids   # artista "Art3" gia' al limite


def test_span_empty_when_budget_already_filled():
    pool = _span_pool()
    fillers = _beam_search_span(
        pool[0], pool, SetGenerationRequest(), strategy_profile("smooth"),
        125.0, 125.0, 3600, elapsed_secs=1200, fill_until_secs=1200)
    assert fillers == []
