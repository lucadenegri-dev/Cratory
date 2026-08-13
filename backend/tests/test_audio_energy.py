"""Energia vera dai file audio (PR4): feature deterministiche da PCM + calibrazione
a percentili sulla libreria. I test usano PCM sintetico (numpy) — nessun file, nessuna
dipendenza da ffmpeg, nessuna flakiness.
"""

import numpy as np

SR = 22050


def sine(freq, amp, secs=1.0, sr=SR):
    t = np.arange(int(secs * sr))
    return (amp * np.sin(2 * np.pi * freq * t / sr)).astype(np.int16)


def bursts(freq, amp, secs=1.0, sr=SR):
    # gate on/off a 4 Hz: transitori marcati -> flusso spettrale alto
    t = np.arange(int(secs * sr))
    gate = (np.sin(2 * np.pi * 4 * t / sr) > 0).astype(np.float64)
    return (amp * gate * np.sin(2 * np.pi * freq * t / sr)).astype(np.int16)


# --- F1) feature pure -------------------------------------------------------

def test_rms_tracks_loudness():
    from app.services.audio_energy import pcm_features
    loud = pcm_features(sine(1000, 20000))[0]
    quiet = pcm_features(sine(1000, 2000))[0]
    assert loud > quiet


def test_centroid_tracks_brightness():
    from app.services.audio_energy import pcm_features
    hi = pcm_features(sine(8000, 15000))[1]
    lo = pcm_features(sine(300, 15000))[1]
    assert hi > lo
    assert 6000 < hi < 10000   # ~8 kHz
    assert lo < 1500


def test_flux_tracks_transients():
    from app.services.audio_energy import pcm_features
    bursty = pcm_features(bursts(1000, 15000))[2]
    steady = pcm_features(sine(1000, 15000))[2]
    assert bursty > steady


def test_pcm_features_handles_silence():
    from app.services.audio_energy import pcm_features
    rms, centroid, flux = pcm_features(np.zeros(SR, dtype=np.int16))
    assert rms == 0.0
    assert centroid >= 0.0 and flux >= 0.0  # niente NaN/divisioni per zero


def test_combine_monotonic_and_bounded():
    from app.services.audio_energy import combine_features
    hot = combine_features(0.8, 8000.0, 0.5)
    cold = combine_features(0.1, 400.0, 0.02)
    assert hot > cold
    assert 0.0 <= cold <= hot <= 1.0
    # monotono in ciascun ingresso a parità degli altri
    assert combine_features(0.5, 5000.0, 0.2) > combine_features(0.2, 5000.0, 0.2)
    assert combine_features(0.3, 9000.0, 0.2) > combine_features(0.3, 2000.0, 0.2)


# --- F3) calibrazione a percentili sulla libreria ---------------------------

def test_percentile_ranks_monotonic_and_bounded():
    from app.services.audio_energy import percentile_ranks
    r = percentile_ranks([0.1, 0.5, 0.9, 0.3])
    assert r[2] == max(r)            # 0.9 (indice 2) è il massimo
    assert r[0] == min(r)            # 0.1 (indice 0) è il minimo
    assert all(0 <= x <= 100 for x in r)


def test_percentile_single_track_is_mid():
    from app.services.audio_energy import percentile_ranks
    assert percentile_ranks([0.42]) == [50]


def test_recompute_energy_calibrates_over_library(db):
    from app.services.audio_energy import recompute_energy
    from app.models import Track
    for i, raw in enumerate([0.2, 0.5, 0.8]):
        db.add(Track(source_type="spotify", title=f"T{i}", energy_raw=raw, has_local_file=True))
    # una traccia senza feature calcolate (lead senza file): resta col proxy, non toccata
    db.add(Track(source_type="spotify", title="Lead", energy=71))
    db.commit()

    n = recompute_energy(db)
    assert n == 3
    computed = sorted((t for t in db.query(Track).all() if t.energy_raw is not None),
                      key=lambda t: t.energy_raw)
    assert computed[0].energy < computed[1].energy < computed[2].energy
    assert all(t.energy_source == "computed" for t in computed)
    assert 0 <= computed[0].energy and computed[2].energy <= 100
    lead = db.query(Track).filter_by(title="Lead").one()
    assert lead.energy == 71 and lead.energy_source != "computed"  # proxy intatto


# --- F2) finestre di campionamento (inizio/metà/fine) -----------------------

def test_window_offsets_samples_across_track():
    from app.services.audio_energy import WINDOW_SECONDS, _window_offsets
    offs = _window_offsets(300)  # traccia da 5 minuti
    assert len(offs) == 3
    assert offs[0] < offs[1] < offs[2]
    assert offs[0] >= 0
    assert offs[2] + WINDOW_SECONDS <= 300  # l'ultima finestra resta dentro la traccia


def test_window_offsets_short_track_uses_start():
    from app.services.audio_energy import _window_offsets
    assert _window_offsets(8) == [0.0]      # più corta di una finestra
    assert _window_offsets(None) == [0.0]   # durata sconosciuta
    assert _window_offsets(0) == [0.0]


# --- F4) il proxy non calpesta l'energia calcolata dai file -----------------

def test_proxy_does_not_overwrite_computed_energy():
    from app.models import Track
    from app.services.energy import apply_estimated_energy
    t = Track(source_type="spotify", bpm=128, energy=90, energy_source="computed")
    assert apply_estimated_energy(t) is False
    assert t.energy == 90 and t.energy_source == "computed"


def test_proxy_applies_and_marks_estimated():
    from app.models import Track
    from app.services.energy import apply_estimated_energy
    t = Track(source_type="spotify", bpm=128)
    assert apply_estimated_energy(t) is True
    assert t.energy is not None and t.energy_source == "estimated"
    # senza bpm non fa nulla
    assert apply_estimated_energy(Track(source_type="spotify")) is False

