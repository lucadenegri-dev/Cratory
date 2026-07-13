"""Ogni Gap porta `params` (i numeri usati nelle f-string di description/suggestion),
per permettere al frontend di tradurre il testo (i18n) invece di ricevere solo
l'italiano hardcoded dal backend. description/suggestion restano per compatibilita'
(vedi CLAUDE.md item 5: wire shape ADD params, non si rimuove nulla)."""

from app.models import Track
from app.services.gap_analysis import analyze_gaps


def _track(**kw):
    kw.setdefault("source_type", "manual")
    return Track(**kw)


def test_missing_openers_params():
    tracks = [_track(bpm=128.0, camelot_key="8A") for _ in range(5)]
    gaps = {g["gap_type"]: g for g in analyze_gaps(tracks)}
    g = gaps["missing_openers"]
    assert g["params"]["count"] == 0
    assert g["params"]["opener_max"] == 120.0
    # backward compat: description/suggestion restano stringhe pronte
    assert "0" in g["description"]


def test_few_peak_tracks_params():
    tracks = [_track(bpm=110.0, camelot_key="8A") for _ in range(5)]
    gaps = {g["gap_type"]: g for g in analyze_gaps(tracks)}
    g = gaps["few_peak_tracks"]
    assert g["params"]["count"] == 0
    assert g["params"]["peak_min"] == 126.0


def test_missing_bpm_bridge_params():
    tracks = [_track(bpm=b, camelot_key="8A") for b in [100.0, 102.0, 104.0, 130.0]]
    gaps = {g["gap_type"]: g for g in analyze_gaps(tracks)}
    g = gaps["missing_bpm_bridge"]
    assert g["params"]["lo"] == 104.0
    assert g["params"]["hi"] == 130.0
    assert g["params"]["gap"] == 26.0


def test_missing_harmonic_data_params():
    tracks = [_track(bpm=128.0, camelot_key="8A")] + [_track(bpm=128.0) for _ in range(3)]
    gaps = {g["gap_type"]: g for g in analyze_gaps(tracks)}
    g = gaps["missing_harmonic_data"]
    assert g["params"]["with_key"] == 1
    assert g["params"]["total"] == 4


def test_uniform_energy_params_is_empty_dict():
    tracks = [_track(bpm=128.0, camelot_key="8A", energy=50) for _ in range(6)]
    gaps = {g["gap_type"]: g for g in analyze_gaps(tracks)}
    g = gaps["uniform_energy"]
    assert g["params"] == {}


def test_low_genre_variety_params():
    tracks = (
        [_track(bpm=128.0, camelot_key="8A", genre="techno") for _ in range(8)]
        + [_track(bpm=128.0, camelot_key="8A", genre="house") for _ in range(1)]
    )
    gaps = {g["gap_type"]: g for g in analyze_gaps(tracks)}
    g = gaps["low_genre_variety"]
    assert g["params"]["pct"] == 89  # round(8/9*100)


def test_scattered_genres_params():
    tracks = [
        _track(bpm=128.0, camelot_key="8A", genre=f"genre-{i}")
        for i in range(10)
    ]
    gaps = {g["gap_type"]: g for g in analyze_gaps(tracks)}
    g = gaps["scattered_genres"]
    assert g["params"]["count"] == 10


def test_every_gap_has_params_key():
    """Nessun finding deve mancare di `params` (anche se vuoto): il frontend
    lo usa per tradurre, deve poterlo sempre leggere senza controlli extra."""
    tracks = [_track(bpm=128.0, camelot_key="8A", genre=f"genre-{i}") for i in range(10)]
    gaps = analyze_gaps(tracks)
    assert gaps  # sanity: la fixture produce almeno un gap
    for g in gaps:
        assert "params" in g
        assert isinstance(g["params"], dict)
        # backward compat: i campi originali restano tutti
        assert {"gap_type", "severity", "description", "suggestion"} <= g.keys()
