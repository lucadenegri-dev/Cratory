"""Identificazione mix DJ (Shazam) — cuore deterministico, senza rete ne' audio.

Testa la parte pura (campionamento offset, dedup dei match consecutivi, orchestrazione
con recognizer finto) e il parsing del payload Shazam. L'I/O (yt-dlp/ffmpeg) non e' qui.
"""

from app.integrations.shazam import parse_shazam
from app.services.mix_identify import (
    CONFIDENCE_CONFIRMED,
    CONFIDENCE_DUBIOUS,
    build_tracks,
    group_samples,
    identify_from_recognizer,
    plan_offsets,
)


# --- plan_offsets ------------------------------------------------------------


def test_plan_offsets_short_mix_dense():
    offsets = plan_offsets(120, segment_length=12, max_segments=100)
    assert offsets[0] == 0
    assert offsets == sorted(offsets)
    assert all(b - a == offsets[1] - offsets[0] for a, b in zip(offsets, offsets[1:]))


def test_plan_offsets_caps_long_mix():
    # 2 ore: il passo si allarga per non superare max_segments
    offsets = plan_offsets(7200, segment_length=12, max_segments=100)
    assert len(offsets) <= 100
    assert offsets[1] - offsets[0] >= 72  # ceil(7200/100)


def test_plan_offsets_zero_duration():
    assert plan_offsets(0) == [0]


# --- group_samples / build_tracks -------------------------------------------


def _m(artist, title, isrc=None):
    return {"artist": artist, "title": title, "isrc": isrc}


def test_group_collapses_consecutive_same_track_counting_hits():
    samples = [
        (0, _m("A", "One")),
        (12, _m("A", "One")),       # stesso brano campionato di nuovo -> stessa serie
        (24, _m("B", "Two")),
        (36, None),                  # buco
        (48, _m("C", "Three")),
    ]
    runs = group_samples(samples)
    assert [(r.match["artist"], r.match["title"], r.hits) for r in runs] == [
        ("A", "One", 2), ("B", "Two", 1), ("C", "Three", 1),
    ]
    assert runs[0].offset == 0  # tiene il primo offset della serie


def test_group_merges_same_track_across_small_gaps():
    # 1-2 buchi con la stessa traccia ai due lati: e' la stessa voce, non un doppione
    samples = [(0, _m("A", "One")), (12, None), (24, None), (36, _m("A", "One"))]
    runs = group_samples(samples)
    assert len(runs) == 1
    assert runs[0].hits == 2


def test_group_three_gaps_break_the_window():
    samples = [(0, _m("A", "One")), (12, None), (24, None), (36, None), (48, _m("A", "One"))]
    assert len(group_samples(samples)) == 2  # 3+ buchi: il DJ l'ha rimessa davvero


def test_group_other_track_between_breaks_the_window():
    samples = [(0, _m("A", "One")), (12, _m("B", "Two")), (24, _m("A", "One"))]
    assert len(group_samples(samples)) == 3  # A torna dopo B: voce nuova


def test_group_uses_isrc_when_present():
    # stesso ISRC ma titolo scritto diversamente -> stesso brano
    samples = [(0, _m("A", "One", isrc="X1")), (12, _m("A", "One (Extended)", isrc="X1"))]
    runs = group_samples(samples)
    assert len(runs) == 1 and runs[0].hits == 2


def test_build_tracks_confidence_from_hits():
    runs = group_samples([(0, _m("A", "One")), (12, _m("A", "One")), (24, _m("B", "Two"))])
    out = build_tracks(runs)
    assert [t.position for t in out] == [1, 2]
    assert out[0].confidence == CONFIDENCE_CONFIRMED   # 2 campioni concordi
    assert out[1].confidence == CONFIDENCE_DUBIOUS     # campione singolo
    assert out[0].start_offset_seconds == 0 and out[1].start_offset_seconds == 24


# --- identify_from_recognizer (recognizer finto) -----------------------------


def test_identify_from_recognizer_end_to_end():
    # mappa offset -> match; alcuni offset senza riconoscimento
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two")}
    calls: list[int] = []

    def recognize_at(offset: int):
        calls.append(offset)
        return table.get(offset)

    out = identify_from_recognizer(60, recognize_at)
    assert calls == plan_offsets(60)  # ha campionato tutti gli offset previsti
    assert [(t.artist, t.title) for t in out] == [("A", "One"), ("B", "Two")]


# --- parsing payload Shazam --------------------------------------------------


def test_parse_shazam_extracts_fields():
    raw = {"track": {
        "title": "Strobe", "subtitle": "deadmau5", "isrc": "USXXX1234567",
        "hub": {"actions": [{"type": "applemusicplay", "id": "12345"}]},
    }}
    out = parse_shazam(raw)
    assert out["artist"] == "deadmau5"
    assert out["title"] == "Strobe"
    assert out["isrc"] == "USXXX1234567"
    assert out["apple_id"] == "12345"
    assert "confidence" not in out  # la confidence e' un derivato dei hit, non del parse


def test_parse_shazam_no_match():
    assert parse_shazam(None) is None
    assert parse_shazam({}) is None
    assert parse_shazam({"track": {"title": "x"}}) is None  # manca l'artista
