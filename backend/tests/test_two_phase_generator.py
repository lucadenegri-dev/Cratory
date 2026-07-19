"""Fase 2 del generatore: convergenza verso l'anchor, piano di genere, riserva."""

import pytest

from app.models import Playlist, Track
from app.repositories import add_track_to_playlist
from app.schemas import SetGenerationRequest
from app.services.set_generator import (
    _DEFAULT_PROFILE,
    _beam_search_span,
    _candidate_score,
    assign_roles,
    generate_set,
)
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


# --- ruoli col peak esplicito --------------------------------------------------


def test_assign_roles_with_explicit_peak():
    roles = assign_roles(10, peak_at=3)
    assert roles[3] == "peak"
    assert roles.count("peak") == 1
    assert roles[0] == "intro" and roles[-1] == "closing"
    assert all(r == "release" for r in roles[4:-1])


def test_assign_roles_default_unchanged():
    assert assign_roles(10) == assign_roles(10, peak_at=None)
    assert assign_roles(10)[round(9 * 0.7)] == "peak"


def test_assign_roles_peak_clamped_for_tiny_sets():
    # Sotto le 4 tracce il peak esplicito viene ignorato (niente indici assurdi).
    assert assign_roles(3, peak_at=0) == assign_roles(3)


# --- generazione a due fasi (integrazione) -------------------------------------


def _seed_playlist(db, n: int = 16, minutes_each: int = 5):
    pl = Playlist(platform="spotify", name="PL2F")
    db.add(pl)
    db.flush()
    tracks = []
    for i in range(1, n + 1):
        t = Track(source_type="spotify", title=f"T{i}", artist=f"Art{i}",
                  duration_seconds=minutes_each * 60, bpm=120.0 + i,
                  camelot_key="8A", energy=10 + i * 5, genre="Techno",
                  has_local_file=True)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl)
        tracks.append(t)
    db.commit()
    return pl, tracks


def test_two_phase_peak_lands_in_peak_zone(db):
    pl, tracks = _seed_playlist(db)
    setlist = generate_set(db, SetGenerationRequest(
        playlist_id=pl.id, target_duration_minutes=70, max_tracks_per_artist=1))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    n = len(ordered)
    peak_positions = [i for i, st in enumerate(ordered) if st.role == "peak"]
    assert len(peak_positions) == 1
    assert 0.45 <= peak_positions[0] / (n - 1) <= 0.9
    # Il ruolo peak sta sulla traccia eletta dallo scheletro (top impatto).
    peak_track_id = ordered[peak_positions[0]].track_id
    top_impact_ids = {t.id for t in sorted(tracks, key=lambda t: -(t.energy or 0))[:3]}
    assert peak_track_id in top_impact_ids


def test_two_phase_bombs_stay_out_of_the_first_third(db):
    pl, tracks = _seed_playlist(db)
    setlist = generate_set(db, SetGenerationRequest(
        playlist_id=pl.id, target_duration_minutes=70, max_tracks_per_artist=1))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    n = len(ordered)
    reserved = {t.id for t in sorted(tracks, key=lambda t: -(t.energy or 0))[:2]}
    early = {st.track_id for st in ordered[: max(1, n // 3)]}
    assert not (reserved & early), "bomba spesa nel primo terzo del set"


def test_short_sets_keep_single_phase_behavior(db):
    # 13 minuti / 5 a traccia = ~3 tracce attese: niente scheletro, nessun errore.
    pl, _ = _seed_playlist(db, n=10)
    setlist = generate_set(db, SetGenerationRequest(
        playlist_id=pl.id, target_duration_minutes=13, max_tracks_per_artist=1))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    assert len(ordered) >= 3
    assert ordered[0].role == "intro" and ordered[-1].role == "closing"


def test_mood_scores_shift_candidate_ranking():
    prev = make_track(id=1, bpm=126.0, camelot_key="8A")
    cand = make_track(id=2, bpm=126.0, camelot_key="8A")
    base = _score(prev, cand)
    assert _score(prev, cand, mood_scores={2: 100}) == pytest.approx(base + 100 * 0.30)
    assert _score(prev, cand, mood_scores={2: 0}) == pytest.approx(base)
    # id assente dal giudizio -> neutro 50
    assert _score(prev, cand, mood_scores={99: 100}) == pytest.approx(base + 50 * 0.30)
    assert _score(prev, cand, mood_scores=None) == base
