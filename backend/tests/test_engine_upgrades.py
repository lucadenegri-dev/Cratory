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


def test_progressive_orders_tracks_by_rising_energy(db):
    from app.services.set_generator import generate_set
    # stesso BPM/key, energia varia: progressive deve costruire un arco crescente
    for i, e in enumerate([20, 40, 60, 80]):
        _lib_track(db, i, bpm=128.0, camelot_key="8A", energy=e)
    db.commit()
    sl = generate_set(db, _req(strategy="progressive", start_bpm=128, end_bpm=128,
                               target_duration_minutes=15, max_tracks_per_artist=5))
    energies = [st.track.energy for st in sorted(sl.tracks, key=lambda s: s.position)]
    assert energies[-1] > energies[0]  # il set finisce più in alto di dove parte


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


def test_beam_beats_greedy_on_hard_case(db):
    # Caso reale trovato per forza bruta: il greedy segue la traiettoria BPM e finisce
    # in un vicolo armonico (totale 378), mentre l'ordine ottimo vale 434. Il beam,
    # guardando avanti, deve avvicinarsi molto all'ottimo — ben oltre il greedy.
    specs = [(130.0, "7A"), (128.0, "8A"), (126.0, "11A"),
             (124.0, "11A"), (130.0, "11A"), (124.0, "7A")]
    for i, (bpm, key) in enumerate(specs):
        _lib_track(db, i, bpm=bpm, camelot_key=key)
    db.commit()
    from app.services.set_generator import generate_set
    setlist = generate_set(db, _req(start_bpm=130, end_bpm=124, target_duration_minutes=20))
    assert _set_total_score(setlist) >= 420  # greedy si ferma a 378, ottimo 434


def test_generate_set_is_deterministic(db):
    from app.services.set_generator import generate_set
    for i in range(10):
        _lib_track(db, i, bpm=124.0 + i * 1.3, camelot_key="8A")
    db.commit()
    a = generate_set(db, _req(start_bpm=124, end_bpm=134, target_duration_minutes=25))
    b = generate_set(db, _req(start_bpm=124, end_bpm=134, target_duration_minutes=25))
    order_a = [st.track_id for st in sorted(a.tracks, key=lambda st: st.position)]
    order_b = [st.track_id for st in sorted(b.tracks, key=lambda st: st.position)]
    assert order_a == order_b


def test_beam_respects_invariants(db):
    from app.services.set_generator import generate_set
    for i in range(12):
        _lib_track(db, i, bpm=124.0 + i * 1.2, camelot_key="8A",
                   artist="Solo" if i % 2 == 0 else f"Art{i}")
    db.commit()
    setlist = generate_set(db, _req(start_bpm=124, end_bpm=138, target_duration_minutes=30,
                                    max_tracks_per_artist=2))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    ids = [st.track_id for st in ordered]
    assert len(ids) == len(set(ids))                       # nessun duplicato
    assert [st.position for st in ordered] == list(range(1, len(ids) + 1))  # posizioni contigue
    assert sum(1 for st in ordered if st.track.artist == "Solo") <= 2       # cap per artista


# --- E) Corridoio BPM per le candidate passate all'AI ------------------------

def _mk(i, bpm, artist=None):
    from app.models import Track
    t = Track(source_type="spotify", title=f"T{i}", artist=artist or f"Art{i}",
              duration_seconds=200, bpm=bpm, camelot_key="8A")
    t.id = i
    return t


def test_ai_candidates_cover_the_whole_corridor():
    # 80 tracce ammassate a 120 (start) + 20 verso 129 (end). Il vecchio ranking per
    # sola vicinanza allo start affamava il finale dell'arco: le 60 candidate erano
    # tutte a ~120. Il corridoio stratificato copre anche il fondo.
    from app.services.ai_agent import _rank_candidates
    cands = [_mk(i, 120.0 + (i % 3) * 0.2) for i in range(80)]
    cands += [_mk(100 + i, 129.0 + (i % 3) * 0.2) for i in range(20)]
    ranked = _rank_candidates(cands, _req(start_bpm=120, end_bpm=130))
    assert len(ranked) <= 60
    assert any(t.bpm >= 128 for t in ranked)   # il finale dell'arco è rappresentato
    assert any(t.bpm <= 121 for t in ranked)   # e anche la partenza


def test_ai_candidates_guarantee_seeds():
    from app.services.ai_agent import _rank_candidates
    cands = [_mk(i, 120.0) for i in range(80)]
    seed = _mk(999, 150.0, artist="Rare Seed")  # fuori corridoio
    cands.append(seed)
    ranked = _rank_candidates(cands, _req(start_bpm=120, end_bpm=125, seed_artists=["Rare Seed"]))
    assert seed in ranked  # il seed è sempre garantito
