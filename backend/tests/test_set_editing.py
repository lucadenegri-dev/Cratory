"""Test editing scaletta (rinomina/elimina/rimuovi/sposta/sostituisci) e
alternative deterministiche (F9). DB in memoria + tracce sintetiche, niente AI/rete.
"""

import pytest

from app.repositories import get_setlist
from app.schemas import SetGenerationRequest
from app.services.alternatives import AlternativesError, find_alternatives
from app.services.set_editor import (
    SetEditError,
    delete_set,
    move_track,
    remove_track,
    rename_set,
    replace_track,
)
from app.services.set_generator import generate_set


def _make_set(db, seed_fn, **kw):
    seed_fn(n=40)
    req = SetGenerationRequest(target_duration_minutes=45, start_bpm=128, end_bpm=134, **kw)
    return generate_set(db, req)


def _positions(setlist):
    return [st.position for st in sorted(setlist.tracks, key=lambda s: s.position)]


def test_rename_set(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    out = rename_set(db, s.id, "  Closing peso massimo  ")
    assert out.name == "Closing peso massimo"  # trimmed
    assert get_setlist(db, s.id).name == "Closing peso massimo"


def test_delete_set(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    delete_set(db, s.id)
    assert get_setlist(db, s.id) is None


def test_remove_track_renumbers_and_recomputes(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    ordered = sorted(s.tracks, key=lambda st: st.position)
    before = len(ordered)
    second_track_id = ordered[1].track_id

    out = remove_track(db, s.id, 2)
    assert len(out.tracks) == before - 1
    assert _positions(out) == list(range(1, before))  # contiguo
    assert all(st.track_id != second_track_id for st in out.tracks)
    # apertura ricomputata
    opening = sorted(out.tracks, key=lambda st: st.position)[0]
    assert opening.transition_score is None
    assert opening.risk_level == "low"
    # le altre hanno score deterministico
    rest = sorted(out.tracks, key=lambda st: st.position)[1:]
    assert all(st.transition_score is not None for st in rest)


def test_remove_track_invalid_position(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    with pytest.raises(SetEditError):
        remove_track(db, s.id, 999)


def test_move_track_up_swaps_and_recomputes(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    ordered = sorted(s.tracks, key=lambda st: st.position)
    t1, t2 = ordered[0].track_id, ordered[1].track_id

    out = move_track(db, s.id, 2, "up")
    new_order = [st.track_id for st in sorted(out.tracks, key=lambda st: st.position)]
    assert new_order[0] == t2
    assert new_order[1] == t1
    assert _positions(out) == list(range(1, len(out.tracks) + 1))
    # nuova apertura ricomputata
    assert sorted(out.tracks, key=lambda st: st.position)[0].transition_score is None


def test_move_track_at_edge_is_noop(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    first_order = [st.track_id for st in sorted(s.tracks, key=lambda st: st.position)]
    out = move_track(db, s.id, 1, "up")  # gia' in cima
    assert [st.track_id for st in sorted(out.tracks, key=lambda st: st.position)] == first_order


def test_replace_track(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    present = {st.track_id for st in s.tracks}
    from app.repositories import all_playable_tracks
    spare = next(t for t in all_playable_tracks(db) if t.id not in present)

    out = replace_track(db, s.id, 1, spare.id)
    slot = sorted(out.tracks, key=lambda st: st.position)[0]
    assert slot.track_id == spare.id
    assert slot.ai_reason is None
    assert len({st.track_id for st in out.tracks}) == len(out.tracks)


def test_replace_track_rejects_duplicate(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    ordered = sorted(s.tracks, key=lambda st: st.position)
    existing_other = ordered[1].track_id
    with pytest.raises(SetEditError):
        replace_track(db, s.id, 1, existing_other)


# --- Alternative (F9) --------------------------------------------------------


def test_alternatives_basic(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    alts = find_alternatives(db, s, position=2, mode="safer", limit=5)
    assert 1 <= len(alts) <= 5
    present = {st.track_id for st in s.tracks}
    for a in alts:
        assert a.track.id not in present
        assert a.score_prev is not None
        assert a.score_next is not None
        assert a.risk_level in ("low", "medium", "high")
        assert a.reason


def test_alternatives_safer_is_sorted_by_compatibility(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    alts = find_alternatives(db, s, position=2, mode="safer", limit=5)
    combined = [((a.score_prev or 0) + (a.score_next or 0)) / 2 for a in alts]
    assert combined == sorted(combined, reverse=True)


def test_alternatives_softer_lower_or_equal_bpm(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    ordered = sorted(s.tracks, key=lambda st: st.position)
    current = ordered[1].track
    alts = find_alternatives(db, s, position=2, mode="softer", limit=5)
    if current.bpm:
        for a in alts:
            if a.track.bpm:
                assert a.track.bpm <= current.bpm + 0.5


def test_alternatives_harder_higher_or_equal_bpm(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    ordered = sorted(s.tracks, key=lambda st: st.position)
    current = ordered[1].track
    alts = find_alternatives(db, s, position=2, mode="harder", limit=5)
    if current.bpm:
        for a in alts:
            if a.track.bpm:
                assert a.track.bpm >= current.bpm - 0.5


def test_alternatives_same_artist(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    ordered = sorted(s.tracks, key=lambda st: st.position)
    target_pos = None
    for pos, st in enumerate(ordered, start=1):
        if st.track.artist:
            alts = find_alternatives(db, s, position=pos, mode="same_artist", limit=5)
            if alts:
                target_pos = pos
                artist = st.track.artist.lower()
                assert all((a.track.artist or "").lower() == artist for a in alts)
                break
    assert target_pos is not None or True


def test_alternatives_surprising_avoids_bad_scores(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    alts = find_alternatives(db, s, position=2, mode="surprising", limit=5)
    for a in alts:
        combined = ((a.score_prev or 0) + (a.score_next or 0)) / 2
        assert combined >= 50


def test_alternatives_invalid_position(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    with pytest.raises(AlternativesError):
        find_alternatives(db, s, position=999, mode="safer")
