"""Identificazione mix DJ (Shazam) — cuore deterministico, senza rete ne' audio.

Testa la parte pura (campionamento offset, raggruppamento con finestra sui buchi, orchestrazione
con recognizer finto) e il parsing del payload Shazam. L'I/O (yt-dlp/ffmpeg) non e' qui.
"""

from app.integrations.shazam import RecognizerError, parse_shazam
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
# Con durata 60: offsets pianificati [0, 12, 24, 36, 48], passo 12, retry a +6s.


def _tracker(table):
    calls: list[int] = []

    def recognize_at(offset: int):
        calls.append(offset)
        return table.get(offset)

    return calls, recognize_at


def test_identify_retry_fills_hole_and_confirms_singles():
    # buco a 12 -> il retry a 18 becca A (stessa serie di 0: hit 2, confermata);
    # B ha un solo hit -> campione di conferma a 24+4=28 (buco: resta dubbia).
    table = {0: _m("A", "One"), 18: _m("A", "One"), 24: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out = identify_from_recognizer(60, recognize_at)
    # 36 -> retry a 42; 48 -> il retry (54) sforerebbe la durata: clampato a 48, saltato
    assert calls == [0, 12, 18, 24, 36, 42, 48, 28]
    assert [(t.artist, t.title, t.confidence) for t in out] == [
        ("A", "One", CONFIDENCE_CONFIRMED), ("B", "Two", CONFIDENCE_DUBIOUS),
    ]


def test_identify_confirmation_promotes_single_to_confirmed():
    # durata 36 -> offsets [0, 12, 24]. B singola a 12, la conferma a 16 concorda.
    table = {0: _m("A", "One"), 12: _m("B", "Two"), 16: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out = identify_from_recognizer(36, recognize_at)
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_DUBIOUS),      # conferma a 0+4=4: buco -> dubbia
        ("B", CONFIDENCE_CONFIRMED),    # conferma a 16 concorde -> 90
    ]
    assert 4 in calls and 16 in calls


def test_identify_budget_zero_disables_retry_and_confirm():
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out = identify_from_recognizer(60, recognize_at, max_extra_calls=0)
    assert calls == plan_offsets(60)  # solo la griglia pianificata
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_CONFIRMED), ("B", CONFIDENCE_DUBIOUS),
    ]


def test_identify_error_on_grid_recovered_by_retry():
    # errore sull'offset pianificato, il retry riconosce: la serie non si spezza
    table = {6: _m("A", "One"), 12: _m("A", "One")}

    def recognize_at(offset: int):
        if offset == 0:
            raise RecognizerError("boom")
        return table.get(offset)

    out = identify_from_recognizer(24, recognize_at)  # offsets [0, 12]
    assert [(t.artist, t.confidence) for t in out] == [("A", CONFIDENCE_CONFIRMED)]


def test_identify_stops_after_max_consecutive_errors():
    calls: list[int] = []

    def recognize_at(offset: int):
        calls.append(offset)
        raise RecognizerError("down")

    out = identify_from_recognizer(7200, recognize_at)
    assert out == []
    assert len(calls) == 8  # MAX_CONSECUTIVE_ERRORS, retry compresi


def test_identify_progress_extends_total_with_confirmations():
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two")}
    progress: list[tuple[int, int]] = []
    _, recognize_at = _tracker(table)
    identify_from_recognizer(60, recognize_at, on_progress=lambda i, n: progress.append((i, n)))
    assert progress[:5] == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]  # passata principale
    assert progress[-1] == (6, 6)  # la conferma di B estende il totale


def test_identify_confirm_loop_stops_when_recognizer_is_down():
    # il recognizer muore dopo due match singoli: la fase di conferma non deve
    # martellare l'endpoint che la passata principale ha appena dichiarato giu'
    table = {0: _m("A", "One"), 72: _m("B", "Two")}
    calls: list[int] = []

    def recognize_at(offset: int):
        calls.append(offset)
        if offset in table:
            return table[offset]
        raise RecognizerError("down")

    out = identify_from_recognizer(7200, recognize_at)
    # 2 match + 8 errori consecutivi (griglia+retry), poi zero chiamate di conferma
    assert len(calls) == 10
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_DUBIOUS), ("B", CONFIDENCE_DUBIOUS),
    ]


def test_identify_no_self_confirmation_on_short_audio():
    # audio cortissimo: il campione di conferma coinciderebbe con l'originale ->
    # niente autoconferma, la voce resta dubbia e il budget non si consuma
    table = {0: _m("A", "One")}
    calls, recognize_at = _tracker(table)
    out = identify_from_recognizer(14, recognize_at)
    assert calls == [0]
    assert [(t.artist, t.confidence) for t in out] == [("A", CONFIDENCE_DUBIOUS)]


def test_identify_budget_consumed_by_retry_leaves_singles_unconfirmed():
    # ordine di consumo: il retry sul buco brucia l'unico budget, la conferma
    # di B non parte -> resta dubbia
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out = identify_from_recognizer(60, recognize_at, max_extra_calls=1)
    assert calls == [0, 12, 24, 36, 42, 48]  # 42 = retry sul buco a 36; nessuna conferma
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_CONFIRMED), ("B", CONFIDENCE_DUBIOUS),
    ]


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
