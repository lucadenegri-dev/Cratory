"""Aggregatori deterministici per la dashboard: istogramma BPM e distribuzione energia."""

from app.repositories import _bpm_histogram, _energy_distribution


def test_bpm_histogram_empty():
    assert _bpm_histogram([]) == []


def test_bpm_histogram_single_value():
    bins = _bpm_histogram([128.0, 128.0, 128.0])
    assert bins == [{"from": 128.0, "to": 128.0, "count": 3}]


def test_bpm_histogram_eight_equal_bins():
    bpms = [100.0, 105.0, 120.0, 135.0, 150.0, 165.0, 179.0, 180.0]
    bins = _bpm_histogram(bpms)
    assert len(bins) == 8
    # estremi ai bordi della libreria
    assert bins[0]["from"] == 100.0
    assert bins[-1]["to"] == 180.0
    # ogni traccia conteggiata una sola volta
    assert sum(b["count"] for b in bins) == len(bpms)
    # il valore massimo cade nell'ultimo bin (chiuso a destra)
    assert bins[-1]["count"] >= 1


def test_bpm_histogram_bin_width_consistent():
    bins = _bpm_histogram([60.0, 140.0])  # range 80 / 8 = width 10
    widths = [round(b["to"] - b["from"], 6) for b in bins]
    assert widths == [10.0] * 8


def test_energy_distribution_five_fixed_buckets_when_empty():
    buckets = _energy_distribution([])
    assert [b["from"] for b in buckets] == [0, 20, 40, 60, 80]
    assert [b["to"] for b in buckets] == [20, 40, 60, 80, 100]
    assert all(b["count"] == 0 for b in buckets)


def test_energy_distribution_boundaries():
    # 0 -> [0,20]; 20 -> [20,40]; 100 -> [80,100]
    buckets = _energy_distribution([0, 20, 40, 60, 80, 100, 100])
    counts = [b["count"] for b in buckets]
    assert counts == [1, 1, 1, 1, 3]
