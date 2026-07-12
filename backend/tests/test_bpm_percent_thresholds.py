"""Fasce BPM percentuali in `_bpm_points` (audit A4, residuo).

Le vecchie fasce assolute (±2/±5/±8 BPM) non scalano con il tempo: 5 BPM a
85 BPM e' un salto del 5.9%, a 170 solo del 2.9%. Le fasce diventano
percentuali (1.6% / 4% / 6.5% del tempo medio), tarate per replicare il
comportamento storico intorno al "club sweet spot" ~128 BPM
(2/128 ~= 1.56%, 5/128 ~= 3.9%, 8/128 ~= 6.25%; la fascia ottima e'
arrotondata per eccesso cosi' il salto di esattamente 2 BPM resta ottimo).
I punti per fascia (50/38/20/5, e 40/30 sul fold half/double) restano
invariati.
"""

from app.models import Track
from app.services.scoring import _bpm_points, score_transition


def make_track(bpm=None, key=None, duration=300) -> Track:
    return Track(source_type="spotify", bpm=bpm, camelot_key=key,
                 duration_seconds=duration)


def test_same_absolute_diff_scores_lower_at_slow_tempo():
    # Il caso RED: 5 BPM di differenza pesano diversamente a tempi diversi.
    # 85->90 e' un salto del 5.9% (fascia rischiosa), 170->175 solo del 2.9%
    # (fascia buona). Con le vecchie soglie assolute finivano ENTRAMBI in ±5.
    slow_pts = _bpm_points(85, 90)[0]
    fast_pts = _bpm_points(170, 175)[0]
    assert slow_pts < fast_pts


def test_anchor_128_bands_match_old_absolute_behavior():
    # Ancora sul club sweet spot: intorno a 128 BPM le fasce percentuali
    # devono riprodurre le vecchie assolute. Valori scelti BEN dentro/fuori
    # le fasce per essere robusti all'arrotondamento delle percentuali.
    assert _bpm_points(128, 129.5)[0] == 50.0   # Δ1.5 (1.17%): fascia ottima
    assert _bpm_points(128, 130)[0] == 50.0     # Δ2 (1.55%): il bordo storico resta ottimo
    assert _bpm_points(128, 132.5)[0] == 38.0   # Δ4.5 (3.45%): fascia buona
    assert _bpm_points(128, 135.5)[0] == 20.0   # Δ7.5 (5.69%): fascia rischiosa
    assert _bpm_points(128, 138)[0] == 5.0      # Δ10 (7.52%): fuori fascia


def test_bands_are_symmetric():
    # Il riferimento percentuale (media dei tempi) e' simmetrico: l'ordine
    # delle tracce non cambia la fascia.
    assert _bpm_points(85, 90)[0] == _bpm_points(90, 85)[0]
    assert _bpm_points(170, 175)[0] == _bpm_points(175, 170)[0]


def test_half_double_folding_applies_before_percent_check():
    # Il fold half/double resta prioritario: 85->170 e' un mezzo/doppio tempo
    # perfetto (Δ effettivo 0), non un salto dell'era glaciale.
    pts, reason, _ = _bpm_points(85, 170)
    assert pts == 40.0
    assert "tempo" in reason  # reason "mezzo/doppio tempo"
    # E nel composito: il fold batte nettamente un salto vero della stessa entita'.
    folded = score_transition(make_track(bpm=85, key="7A"),
                              make_track(bpm=170, key="7A")).score
    unrelated = score_transition(make_track(bpm=85, key="7A"),
                                 make_track(bpm=130, key="7A")).score
    assert folded > unrelated


def test_folded_near_match_stays_in_halftime_band():
    # Fold quasi perfetto (85->172: Δ effettivo 2 sulla griglia ~171): resta
    # nella fascia half/double alta, il riferimento percentuale va calcolato
    # sulla griglia raddoppiata, non sulla media dei BPM grezzi.
    assert _bpm_points(85, 172)[0] == 40.0
