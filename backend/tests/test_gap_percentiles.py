"""Soglie opener/peak derivate dai percentili BPM della playlist (A21).

Le soglie fisse (120/126) sono house-centric: una playlist drum&bass a 170+
BPM risultava SEMPRE "senza aperture sotto 120", un falso positivo
sistematico. Con abbastanza tracce con BPM le soglie diventano il 25o/75o
percentile della distribuzione della playlist stessa (il quarto piu' lento
apre, il quarto piu' veloce fa il peak, qualunque sia il genere); sotto
quella dimensione i percentili sono troppo rumorosi e si torna ai default
assoluti. Il formato dei findings (gap_type/severity/description/suggestion)
non cambia.
"""

from app.models import Track
from app.services.gap_analysis import analyze_gaps


def _tracks(bpms: list[float | None]) -> list[Track]:
    return [Track(source_type="spotify", bpm=b) for b in bpms]


def _gap_types(tracks: list[Track]) -> set[str]:
    return {g["gap_type"] for g in analyze_gaps(tracks)}


def test_dnb_playlist_not_flagged_missing_openers():
    # 10 tracce dnb 168-175: la traccia "lenta" a 168 e le low-170 SONO le
    # aperture relative della playlist. La vecchia regola assoluta (<=120)
    # segnalava sempre missing_openers su tutto il repertorio dnb.
    gaps = _gap_types(_tracks([168, 170, 171, 171, 172, 172, 173, 174, 174, 175]))
    assert "missing_openers" not in gaps
    # idem per il peak: 174/174/175 sono il quarto veloce della playlist.
    assert "few_peak_tracks" not in gaps


def test_house_playlist_anchor_same_outcome():
    # Ancoraggio: playlist house ben formata (code lente sotto 120 e code
    # veloci sopra 126 presenti) -> nessun gap opener/peak, ne' con le
    # vecchie soglie assolute ne' con i percentili (P25~120.25, P75~127.75).
    gaps = _gap_types(_tracks([116, 118, 119, 124, 125, 126, 127, 128, 129, 130]))
    assert "missing_openers" not in gaps
    assert "few_peak_tracks" not in gaps


def test_small_playlist_falls_back_to_absolute_defaults():
    # < 8 tracce con BPM: i percentili collasserebbero sul cluster stesso
    # (ogni traccia sposta la soglia) -> valgono i default assoluti, quindi
    # il cluster stretto 122-123 non ha aperture (<=120) ne' peak (>=126).
    gaps = _gap_types(_tracks([122.0, 122.2, 122.4, 122.6, 122.8, 123.0]))
    assert "missing_openers" in gaps
    assert "few_peak_tracks" in gaps


def test_fallback_counts_only_tracks_with_bpm():
    # Le tracce senza BPM non devono contare per la soglia minima delle 8:
    # 6 con BPM + 5 senza = ancora fallback assoluto.
    tracks = _tracks([122.0, 122.2, 122.4, 122.6, 122.8, 123.0])
    tracks += _tracks([None] * 5)
    gaps = _gap_types(tracks)
    assert "missing_openers" in gaps
    assert "few_peak_tracks" in gaps


def test_percentile_interpolation_is_deterministic():
    # Percentile "plain sorted-list" con interpolazione lineare (come il
    # default numpy, ma senza numpy): verifica il calcolo su valori noti.
    from app.services.gap_analysis import _percentile

    vals = [168.0, 170.0, 171.0, 171.0, 172.0, 172.0, 173.0, 174.0, 174.0, 175.0]
    assert _percentile(vals, 0.25) == 171.0          # idx 2.25 tra due 171
    assert _percentile(vals, 0.75) == 173.75         # idx 6.75 tra 173 e 174
    assert _percentile([120.0], 0.25) == 120.0       # singolo valore
    assert _percentile([120.0, 130.0], 0.75) == 127.5
