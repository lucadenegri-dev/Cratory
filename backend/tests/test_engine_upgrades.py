"""Test degli upgrade al motore di generazione:
A) scoring Camelot graduato, B) BPM mezzo/doppio tempo,
C) profili di strategia, D) beam search, E) corridoio candidate AI.
"""

from app.models import Track


def make_track(bpm=None, key=None, duration=300, energy=None, genre=None) -> Track:
    return Track(source_type="spotify", bpm=bpm, camelot_key=key, duration_seconds=duration,
                 energy=energy, genre=genre)


# --- A) Camelot graduato -----------------------------------------------------

def test_camelot_score_graded_ordering():
    from app.services.camelot import camelot_score
    # stessa key = massimo; unknown = neutro
    assert camelot_score("8A", "8A") == 100
    assert camelot_score("8A", None) == 50
    assert camelot_score(None, None) == 50
    # relativa (8A<->8B) e adiacente (8A->9A) sono forti
    assert camelot_score("8A", "8B") >= 85
    assert camelot_score("8A", "9A") >= 80
    # "weak" non è più piatto: +2 stessa lettera (energy boost) > 3-4 passi > tritono
    assert camelot_score("8A", "9A") > camelot_score("8A", "10A") > camelot_score("8A", "2A")
    # diagonale (8A->9B) usabile, meglio di un salto lontano
    assert camelot_score("8A", "9B") > camelot_score("8A", "3A")
    # tritono è il fondo
    assert camelot_score("8A", "2A") <= 15


# --- B) BPM mezzo/doppio tempo ----------------------------------------------

def test_halftime_transition_is_mixable():
    from app.services.scoring import score_transition
    base = make_track(bpm=140, key="7A")
    half = score_transition(base, make_track(bpm=70, key="7A")).score       # 70 = 140/2
    unrelated = score_transition(base, make_track(bpm=110, key="7A")).score  # diff 30, nessun fold
    assert half > unrelated


def test_doubletime_transition_is_mixable():
    from app.services.scoring import score_transition
    base = make_track(bpm=87, key="7A")
    double = score_transition(base, make_track(bpm=174, key="7A")).score     # 174 = 87*2
    assert double >= 40  # non è un salto "difficile" da 5 punti


def test_mixing_tip_mentions_halftime():
    from app.services.scoring import mixing_tip
    tip = mixing_tip(make_track(bpm=140, key="7A"), make_track(bpm=70, key="7A"))
    assert "tempo" in tip.lower()


# --- C) Profili di strategia -------------------------------------------------

def _req(**kw):
    from app.schemas import SetGenerationRequest
    return SetGenerationRequest(**kw)


def test_strategy_profiles_differ():
    from app.services.set_generator import strategy_profile
    # le 7 strategie non sono più lo stesso algoritmo: contrast/experimental
    # ammettono salti bruschi, le altre no.
    assert strategy_profile("smooth").allow_sharp is False
    assert strategy_profile("contrast").allow_sharp is True
    assert strategy_profile("experimental").allow_sharp is True
    assert strategy_profile("peak_time").bpm_curve < 1.0   # sale in fretta
    assert strategy_profile("warm_up").bpm_curve > 1.0     # sale piano
    # contrast piazza reset deliberati, smooth no
    assert strategy_profile("contrast").reset_points
    assert not strategy_profile("smooth").reset_points


def test_contrast_allows_sharp_change():
    from app.services.set_generator import _candidate_score, strategy_profile
    prev = make_track(bpm=128, key="8A", energy=70)
    sharp = make_track(bpm=150, key="2B", energy=68)  # salto BPM + key debole = score basso
    req = _req()
    smooth_total, _ = _candidate_score(prev, sharp, 128, req, {}, strategy_profile("smooth"), 0.5)
    contrast_total, _ = _candidate_score(prev, sharp, 128, req, {}, strategy_profile("contrast"), 0.5)
    assert contrast_total > smooth_total  # smooth applica la penalità -40, contrast no


def test_contrast_rewards_reset_at_reset_point():
    from app.services.set_generator import _candidate_score, strategy_profile
    prev = make_track(bpm=128, key="8A", energy=82, genre="techno")
    reset_cand = make_track(bpm=126, key="8A", energy=55, genre="techno")  # -27 energia = reset
    req = _req()
    p = strategy_profile("contrast")
    at_reset, _ = _candidate_score(prev, reset_cand, 128, req, {}, p, p.reset_points[0])
    off_reset, _ = _candidate_score(prev, reset_cand, 128, req, {}, p, 0.05)
    assert at_reset > off_reset  # il bonus reset scatta solo vicino ai reset point


def test_experimental_rewards_novelty():
    from app.services.set_generator import _candidate_score, strategy_profile
    prev = make_track(bpm=128, key="8A", energy=70, genre="techno")
    same = make_track(bpm=128, key="8A", energy=70, genre="techno")
    novel = make_track(bpm=128, key="8A", energy=70, genre="electro")  # cambio di genere
    req = _req()
    exp = strategy_profile("experimental")
    s_same, _ = _candidate_score(prev, same, 128, req, {}, exp, 0.5)
    s_novel, _ = _candidate_score(prev, novel, 128, req, {}, exp, 0.5)
    assert s_novel > s_same
    # smooth invece preferisce la coerenza
    sm = strategy_profile("smooth")
    assert _candidate_score(prev, novel, 128, req, {}, sm, 0.5)[0] < _candidate_score(prev, same, 128, req, {}, sm, 0.5)[0]


def test_progressive_has_energy_arc_smooth_does_not():
    from app.services.set_generator import _desired_energy, strategy_profile
    req = _req()  # nessuna energia richiesta dall'utente
    prog = strategy_profile("progressive")
    smooth = strategy_profile("smooth")
    assert prog.energy_arc is not None
    assert smooth.energy_arc is None
    # progressive impone un arco di energia crescente; smooth non impone nulla
    assert _desired_energy(req, 1.0, prog) > _desired_energy(req, 0.0, prog)
    assert _desired_energy(req, 0.5, smooth) is None
    # l'energia esplicita dell'utente vince sempre sul profilo
    assert _desired_energy(_req(start_energy=90, end_energy=90), 0.5, prog) == 90


# --- C2) Copertura dei generi richiesti (presence-only) ----------------------

def test_requested_absent_genre_gets_presence_boost():
    # Un genere RICHIESTO ma ancora assente dal set batte un techno equivalente,
    # nonostante la coerenza favorisca il techno (stesso genere del prev).
    from app.services.set_generator import _candidate_score, strategy_profile
    prev = make_track(bpm=128, key="8A", energy=70, genre="techno")
    breakbeat = make_track(bpm=128, key="8A", energy=70, genre="breakbeat")
    techno = make_track(bpm=128, key="8A", energy=70, genre="techno")
    req = _req(genres=["dub", "breakbeat", "techno"])
    sm = strategy_profile("smooth")
    bb, _ = _candidate_score(prev, breakbeat, 128, req, {}, sm, 0.5, genre_counts={"techno": 3})
    tk, _ = _candidate_score(prev, techno, 128, req, {}, sm, 0.5, genre_counts={"techno": 3})
    assert bb > tk


def test_presence_boost_tapers_once_genre_present():
    # Il boost cala man mano che il genere richiesto compare: presence-only, non quota.
    from app.services.set_generator import _candidate_score, strategy_profile
    prev = make_track(bpm=128, key="8A", energy=70, genre="techno")
    breakbeat = make_track(bpm=128, key="8A", energy=70, genre="breakbeat")
    req = _req(genres=["breakbeat", "techno"])
    sm = strategy_profile("smooth")
    absent, _ = _candidate_score(prev, breakbeat, 128, req, {}, sm, 0.5, genre_counts={})
    present, _ = _candidate_score(prev, breakbeat, 128, req, {}, sm, 0.5, genre_counts={"breakbeat": 2})
    assert absent > present


def test_no_requested_genres_leaves_score_unchanged():
    # Senza req.genres il termine e' inerte: passare genre_counts non cambia nulla.
    from app.services.set_generator import _candidate_score, strategy_profile
    prev = make_track(bpm=128, key="8A", energy=70, genre="techno")
    cand = make_track(bpm=128, key="8A", energy=70, genre="breakbeat")
    sm = strategy_profile("smooth")
    with_counts, _ = _candidate_score(prev, cand, 128, _req(), {}, sm, 0.5, genre_counts={"techno": 5})
    without, _ = _candidate_score(prev, cand, 128, _req(), {}, sm, 0.5)
    assert with_counts == without


# --- D) Beam search ----------------------------------------------------------

def _lib_track(db, i, **kw):
    from app.models import Track
    kw.setdefault("has_local_file", True)
    t = Track(source_type="spotify", title=f"T{i}", artist=kw.pop("artist", f"Art{i}"),
              duration_seconds=200, **kw)
    db.add(t)
    db.flush()
    return t


def _set_total_score(setlist):
    from app.services.scoring import score_transition
    ordered = [st.track for st in sorted(setlist.tracks, key=lambda st: st.position)]
    return sum(score_transition(a, b).score for a, b in zip(ordered, ordered[1:]))


# --- E) Corridoio BPM per le candidate passate all'AI ------------------------

def _mk(i, bpm, artist=None):
    from app.models import Track
    t = Track(source_type="spotify", title=f"T{i}", artist=artist or f"Art{i}",
              duration_seconds=200, bpm=bpm, camelot_key="8A")
    t.id = i
    return t


