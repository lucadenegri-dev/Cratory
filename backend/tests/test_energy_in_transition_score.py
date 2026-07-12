"""L'energia entra nel composito score_transition (audit A23).

Il termine energia esiste SOLO quando entrambe le tracce hanno `energy`:
per le librerie senza energia lo score deve restare IDENTICO a prima
(nessuna deriva, compat all'indietro totale).
"""

from app.models import Track
from app.services.scoring import risk_from_score, score_transition


def make_track(bpm=None, key=None, duration=300, energy=None, genre=None) -> Track:
    return Track(source_type="spotify", bpm=bpm, camelot_key=key, duration_seconds=duration,
                 energy=energy, genre=genre)


def test_close_energy_beats_far_energy():
    # Stesso BPM/key/durata: energie vicine devono battere un crollo di energia.
    # BPM 128->131 (non perfetto) per non saturare a 100 e vedere l'ordinamento.
    base = make_track(bpm=128, key="8A", energy=60)
    close = score_transition(base, make_track(bpm=131, key="9A", energy=62)).score
    far = score_transition(base, make_track(bpm=131, key="9A", energy=20)).score
    assert close > far


def test_missing_energy_keeps_score_identical():
    # Compat all'indietro: se anche UNA sola energia manca, lo score e'
    # identico a quello di una coppia del tutto priva di energia.
    no_energy = score_transition(
        make_track(bpm=128, key="8A"), make_track(bpm=130, key="9A")).score
    only_from = score_transition(
        make_track(bpm=128, key="8A", energy=70), make_track(bpm=130, key="9A")).score
    only_to = score_transition(
        make_track(bpm=128, key="8A"), make_track(bpm=130, key="9A", energy=70)).score
    assert only_from == no_energy
    assert only_to == no_energy


def test_energy_influence_is_bounded():
    # Un match BPM/key perfetto con energia pessima NON crolla di fascia:
    # il rischio resta "low" (l'energia corregge, BPM+key restano dominanti).
    base = make_track(bpm=128, key="8A", energy=100)
    crash = score_transition(base, make_track(bpm=128, key="8A", energy=10)).score
    assert crash >= 70
    assert risk_from_score(crash) == "low"


def test_energy_term_never_flips_bad_pair_above_sharp_threshold():
    # Guardia sul generatore: un salto brusco (BPM+key pessimi, score ~19) con
    # energia coerente non deve superare la soglia sharp (<30) di set_generator.
    prev = make_track(bpm=128, key="8A", energy=70)
    sharp = make_track(bpm=150, key="2B", energy=68)
    assert score_transition(prev, sharp).score < 30
