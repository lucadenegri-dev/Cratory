"""Test A22: dopo move/remove i ruoli vengono riassegnati con la stessa logica
deterministica della generazione (assign_roles) e le note AI (ai_reason,
transition_note) delle tracce con vicini cambiati vengono azzerate; le coppie
non toccate conservano le loro. DB in memoria + tracce sintetiche, niente AI/rete.
"""

from app.schemas import SetGenerationRequest
from app.services.set_editor import move_track, remove_track
from app.services.set_generator import assign_roles, generate_set


def _make_set(db, seed_fn, **kw):
    seed_fn(n=40)
    req = SetGenerationRequest(target_duration_minutes=45, start_bpm=128, end_bpm=134, **kw)
    return generate_set(db, req)


def _ordered(setlist):
    return sorted(setlist.tracks, key=lambda st: st.position)


def _seed_ai_notes(db, setlist):
    """Simula l'arricchimento AI: una motivazione e una nota per ogni posizione."""
    for st in _ordered(setlist):
        st.ai_reason = f"reason-{st.position}"
        st.transition_note = f"note-{st.position}"
    db.commit()


def test_remove_peak_reassigns_roles(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    ordered = _ordered(s)
    peak_pos = next(st.position for st in ordered if st.role == "peak")

    out = remove_track(db, s.id, peak_pos)
    roles = [st.role for st in _ordered(out)]
    # stessa logica deterministica della generazione per il nuovo numero di tracce
    assert roles == assign_roles(len(roles))
    # coerenza dell'arco: niente buchi ne' peak duplicati
    assert roles.count("peak") == 1
    assert roles[0] == "intro"
    assert roles[-1] == "closing"


def test_remove_track_clears_adjacent_ai_notes(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    n = len(s.tracks)
    assert n >= 5, "servono abbastanza tracce per avere coppie non toccate"
    _seed_ai_notes(db, s)
    removed_pos = 3

    out = remove_track(db, s.id, removed_pos)
    by_pos = {st.position: st for st in _ordered(out)}
    # i vicini della rimozione (nuove posizioni 2 e 3) hanno note azzerate
    for pos in (removed_pos - 1, removed_pos):
        assert by_pos[pos].ai_reason is None
        assert by_pos[pos].transition_note is None
    # le coppie non toccate conservano le note (attenzione allo shift: la
    # traccia ora in posizione p era in posizione p+1 se p >= removed_pos)
    assert by_pos[1].ai_reason == "reason-1"
    assert by_pos[1].transition_note == "note-1"
    for pos in range(removed_pos + 1, len(by_pos) + 1):
        assert by_pos[pos].ai_reason == f"reason-{pos + 1}"
        assert by_pos[pos].transition_note == f"note-{pos + 1}"


def test_move_track_clears_affected_ai_notes(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    n = len(s.tracks)
    assert n >= 6, "servono abbastanza tracce per avere coppie non toccate"
    _seed_ai_notes(db, s)

    # sposta la posizione 3 in su: swap delle posizioni 2 e 3
    out = move_track(db, s.id, 3, "up")
    by_pos = {st.position: st for st in _ordered(out)}
    # traccia mossa + vicini della vecchia e della nuova posizione: 1..4
    for pos in (1, 2, 3, 4):
        assert by_pos[pos].ai_reason is None, f"ai_reason stantia in posizione {pos}"
        assert by_pos[pos].transition_note is None, f"transition_note stantia in posizione {pos}"
    # le coppie non toccate conservano le note
    for pos in range(5, n + 1):
        assert by_pos[pos].ai_reason == f"reason-{pos}"
        assert by_pos[pos].transition_note == f"note-{pos}"


def test_move_track_reassigns_roles(db, seed_tracks):
    s = _make_set(db, seed_tracks)

    out = move_track(db, s.id, 2, "up")
    roles = [st.role for st in _ordered(out)]
    # i ruoli sono posizionali: dopo lo swap devono combaciare con la generazione
    assert roles == assign_roles(len(roles))


def test_move_track_at_edge_keeps_ai_notes(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    _seed_ai_notes(db, s)

    out = move_track(db, s.id, 1, "up")  # no-op silenzioso
    for st in _ordered(out):
        assert st.ai_reason == f"reason-{st.position}"
        assert st.transition_note == f"note-{st.position}"
