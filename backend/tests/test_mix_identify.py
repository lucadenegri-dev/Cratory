"""Identificazione mix DJ (Shazam) — cuore deterministico, senza rete ne' audio.

Testa la parte pura (campionamento offset, dedup dei match consecutivi, orchestrazione
con recognizer finto) e il parsing del payload Shazam. L'I/O (yt-dlp/ffmpeg) non e' qui.
"""

from app.integrations.shazam import parse_shazam
from app.services.mix_identify import (
    dedup_consecutive,
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


# --- dedup_consecutive -------------------------------------------------------


def _m(artist, title, isrc=None):
    return {"artist": artist, "title": title, "isrc": isrc, "confidence": 80}


def test_dedup_collapses_consecutive_same_track():
    samples = [
        (0, _m("A", "One")),
        (12, _m("A", "One")),       # stesso brano campionato di nuovo -> collassa
        (24, _m("B", "Two")),
        (36, None),                  # buco
        (48, _m("C", "Three")),
    ]
    out = dedup_consecutive(samples)
    assert [(t.artist, t.title) for t in out] == [("A", "One"), ("B", "Two"), ("C", "Three")]
    assert [t.position for t in out] == [1, 2, 3]
    assert out[0].start_offset_seconds == 0  # tiene il primo offset del blocco


def test_dedup_same_track_replayed_later_is_new_entry():
    samples = [(0, _m("A", "One")), (12, _m("B", "Two")), (24, _m("A", "One"))]
    out = dedup_consecutive(samples)
    assert len(out) == 3  # A torna dopo B: il DJ l'ha rimesso


def test_dedup_uses_isrc_when_present():
    # stesso ISRC ma titolo scritto diversamente -> stesso brano
    samples = [(0, _m("A", "One", isrc="X1")), (12, _m("A", "One (Extended)", isrc="X1"))]
    assert len(dedup_consecutive(samples)) == 1


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
    assert out["confidence"] == 80


def test_parse_shazam_no_match():
    assert parse_shazam(None) is None
    assert parse_shazam({}) is None
    assert parse_shazam({"track": {"title": "x"}}) is None  # manca l'artista
