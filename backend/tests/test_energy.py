from app.services.energy import estimate_energy


def test_energy_none_without_bpm():
    assert estimate_energy(None, None, None) is None


def test_energy_scales_with_bpm_and_genre_bias():
    base = estimate_energy(125.0, None, None)
    assert 0 <= base <= 100
    hi = estimate_energy(125.0, None, "techno")
    lo = estimate_energy(125.0, None, "ambient")
    assert hi > base > lo
