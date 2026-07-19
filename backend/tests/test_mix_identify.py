"""Identificazione mix DJ (Shazam) — cuore deterministico, senza rete ne' audio.

Testa la parte pura (campionamento offset, raggruppamento e fusione temporale,
orchestrazione con recognizer finto) e il parsing del payload Shazam. L'I/O
(yt-dlp/ffmpeg) non e' qui.
"""

from app.integrations.shazam import RecognizerError, parse_shazam
from app.services.mix_identify import (
    CONFIDENCE_CONFIRMED,
    CONFIDENCE_DUBIOUS,
    PITCH_PROBE_HOLES,
    PITCH_RATES,
    _pitch_filter,
    build_tracks,
    group_samples,
    identify_from_recognizer,
    merge_same_key_runs,
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


def test_plan_offsets_default_cap_keeps_tracks_visible_on_long_mixes():
    # tetto di default 200: su 2h08m il passo scende a ~39s, cosi' una traccia
    # da 2-3 minuti viene campionata piu' volte e puo' essere confermata
    offsets = plan_offsets(7720)
    assert len(offsets) <= 200
    assert offsets[1] - offsets[0] == 39  # ceil(7720/200)


# --- group_samples / merge_same_key_runs / build_tracks ----------------------


def _m(artist, title, isrc=None):
    return {"artist": artist, "title": title, "isrc": isrc}


def test_group_collapses_consecutive_same_track_counting_hits():
    samples = [
        (0, _m("A", "One")),
        (12, _m("A", "One")),       # stesso brano campionato di nuovo -> stessa serie
        (24, _m("B", "Two")),
        (36, None),                  # buco: spezza la serie
        (48, _m("C", "Three")),
    ]
    runs = group_samples(samples)
    assert [(r.match["artist"], r.match["title"], r.hits) for r in runs] == [
        ("A", "One", 2), ("B", "Two", 1), ("C", "Three", 1),
    ]
    assert runs[0].offset == 0 and runs[0].last_offset == 12


def test_group_uses_isrc_when_present():
    # stesso ISRC ma titolo scritto diversamente -> stesso brano
    samples = [(0, _m("A", "One", isrc="X1")), (12, _m("A", "One (Extended)", isrc="X1"))]
    runs = group_samples(samples)
    assert len(runs) == 1 and runs[0].hits == 2


def test_merge_rejoins_same_track_across_holes():
    # buchi con la stessa traccia ai due lati, entro la finestra: stessa voce
    runs = group_samples([(0, _m("A", "One")), (12, None), (24, None), (36, _m("A", "One"))])
    merged = merge_same_key_runs(runs)
    assert len(merged) == 1
    assert merged[0].hits == 2 and merged[0].last_offset == 36


def test_merge_rejoins_same_track_over_an_interloper():
    # il caso Total Eclipse: la stessa traccia ai due lati di un match diverso
    # (falso positivo o overlap) si ricuce; il match in mezzo resta una voce sua
    runs = group_samples([(975, _m("Diva", "Total Eclipse")), (1014, _m("Guetta", "Titanium")),
                          (1131, _m("Diva", "Total Eclipse"))])
    merged = merge_same_key_runs(runs)
    assert [(r.match["artist"], r.hits) for r in merged] == [("Diva", 2), ("Guetta", 1)]
    assert merged[0].offset == 975 and merged[0].last_offset == 1131


def test_merge_far_reappearance_is_a_new_entry():
    # oltre la finestra temporale il DJ l'ha rimessa davvero: voce nuova
    runs = group_samples([(0, _m("A", "One")), (150, None), (300, _m("A", "One"))])
    assert len(merge_same_key_runs(runs)) == 2


def test_build_tracks_confidence_from_hits():
    runs = group_samples([(0, _m("A", "One")), (12, _m("A", "One")), (24, _m("B", "Two"))])
    out = build_tracks(runs)
    assert [t.position for t in out] == [1, 2]
    assert out[0].confidence == CONFIDENCE_CONFIRMED   # 2 campioni concordi
    assert out[1].confidence == CONFIDENCE_DUBIOUS     # campione singolo
    assert out[0].start_offset_seconds == 0 and out[1].start_offset_seconds == 24


# --- identify_from_recognizer (recognizer finto) -----------------------------
# Con durata 60: offsets pianificati [0, 12, 24, 36, 48], passo 12,
# retry sui buchi a +6s, conferma a due lati a +-6s.


def _tracker(table):
    """Fake di recognize_at(offset, rate): registra `offset` per le chiamate a
    rate naturale e `(offset, rate)` per quelle pitch-compensate; la table usa
    le stesse chiavi (int per rate 1.0, tupla per i match solo-compensati)."""
    calls: list = []

    def recognize_at(offset: int, rate: float = 1.0):
        key = offset if rate == 1.0 else (offset, rate)
        calls.append(key)
        return table.get(key)

    return calls, recognize_at


def test_identify_retry_fills_hole_and_drops_refuted_single():
    # buco a 12 -> il retry a 18 becca A (stessa serie di 0: hit 2, confermata);
    # B ha un solo hit -> conferme a 30 (buco) e 18 (traccia diversa): smentita, fuori.
    table = {0: _m("A", "One"), 18: _m("A", "One"), 24: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out, aborted = identify_from_recognizer(60, recognize_at)
    # 36 -> retry a 42; 48 -> il retry (54) sforerebbe la durata: clampato a 48, saltato.
    # I buchi rimasti tali dopo il retry ricevono la scala pitch-compensata completa
    # (nessun rate scoperto: sonda tutta PITCH_RATES, qui sempre a vuoto).
    assert calls == [0, 12, 18, 24,
                     36, 42, (36, 0.96), (36, 1.04), (36, 0.92), (36, 1.08),
                     48, (48, 0.96), (48, 1.04), (48, 0.92), (48, 1.08),
                     30, 18]
    assert [(t.artist, t.title, t.confidence) for t in out] == [("A", "One", CONFIDENCE_CONFIRMED)]
    assert aborted is None


def test_identify_confirmation_promotes_single_and_drops_refuted():
    # durata 36 -> offsets [0, 12, 24]. B singola a 12: la conferma a 18 concorda -> 90.
    # A singola a 0: conferma a 6 muta, -6 fuori range -> smentita, fuori.
    table = {0: _m("A", "One"), 12: _m("B", "Two"), 18: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out, aborted = identify_from_recognizer(36, recognize_at)
    assert [(t.artist, t.confidence) for t in out] == [("B", CONFIDENCE_CONFIRMED)]
    assert 6 in calls and 18 in calls
    assert aborted is None


def test_identify_two_sided_confirmation_rescues_track_near_its_end():
    # la conferma a +6 cade sulla traccia successiva (C), quella a -6 concorda:
    # B e' vera, viene promossa; il match C della conferma non crea voci
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two"),
             30: _m("C", "Three"), 18: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out, _ = identify_from_recognizer(60, recognize_at)
    assert calls == [0, 12, 24,
                     36, 42, (36, 0.96), (36, 1.04), (36, 0.92), (36, 1.08),
                     48, (48, 0.96), (48, 1.04), (48, 0.92), (48, 1.08),
                     30, 18]
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_CONFIRMED), ("B", CONFIDENCE_CONFIRMED),
    ]


def test_identify_merges_over_refuted_interloper_end_to_end():
    # Total Eclipse in miniatura: D ai due lati di T. Le due D si fondono in una
    # confermata senza spendere conferme; T smentita (18 e 6 muti) sparisce.
    table = {0: _m("D", "Eclipse"), 12: _m("T", "Titanium"), 24: _m("D", "Eclipse")}
    calls, recognize_at = _tracker(table)
    out, _ = identify_from_recognizer(60, recognize_at)
    assert calls == [0, 12, 24,
                     36, 42, (36, 0.96), (36, 1.04), (36, 0.92), (36, 1.08),
                     48, (48, 0.96), (48, 1.04), (48, 0.92), (48, 1.08),
                     18, 6]
    assert [(t.artist, t.confidence, t.start_offset_seconds) for t in out] == [
        ("D", CONFIDENCE_CONFIRMED, 0),
    ]


def test_identify_budget_zero_disables_retry_and_confirm():
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out, aborted = identify_from_recognizer(60, recognize_at, max_extra_calls=0)
    assert calls == plan_offsets(60)  # solo la griglia pianificata
    # B non e' mai stata verificata: resta dubbia (assenza di prove, non smentita)
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_CONFIRMED), ("B", CONFIDENCE_DUBIOUS),
    ]
    assert aborted is None


def test_identify_error_on_grid_gets_no_hole_retry_but_confirmation_can_rescue():
    # un errore sull'offset pianificato NON scatena il retry sul buco (il
    # recognizer ha gia' fatto backoff internamente); la traccia adiacente
    # rimasta singola puo' comunque essere confermata
    table = {6: _m("A", "One"), 12: _m("A", "One")}
    calls: list[int] = []

    def recognize_at(offset: int, rate: float = 1.0):
        calls.append(offset)
        if offset == 0:
            raise RecognizerError("boom")
        return table.get(offset)

    out, aborted = identify_from_recognizer(24, recognize_at)  # offsets [0, 12]
    # 0 -> errore (nessun retry a 6); 12 -> A singola; conferma a 12-6=6 -> A
    assert calls == [0, 12, 6]
    assert [(t.artist, t.confidence) for t in out] == [("A", CONFIDENCE_CONFIRMED)]
    assert aborted is None


def test_identify_stops_after_max_consecutive_errors_and_reports_abort():
    calls: list[int] = []

    def recognize_at(offset: int, rate: float = 1.0):
        calls.append(offset)
        raise RecognizerError("down")

    out, aborted = identify_from_recognizer(7200, recognize_at)
    assert out == []
    # ogni errore ha gia' assorbito il backoff del recognizer: bastano 3 di fila
    assert len(calls) == 3  # MAX_CONSECUTIVE_ERRORS, senza retry sui buchi
    assert aborted == 72  # passo 36: terzo offset di griglia, dove ci si e' fermati


def test_identify_errored_confirmation_is_not_a_verification():
    # il tentativo di conferma che va in ERRORE non conta come verifica:
    # il singolo resta dubbio (recognizer giu' = assenza di prove)
    table = {0: _m("A", "One"), 12: _m("B", "Two")}
    calls: list[int] = []

    def recognize_at(offset: int, rate: float = 1.0):
        calls.append(offset)
        if offset not in table:
            raise RecognizerError("down")
        return table[offset]

    out, aborted = identify_from_recognizer(36, recognize_at)  # offsets [0, 12, 24]
    # griglia: 0->A, 12->B, 24->errore (niente retry). Conferme: A a 6 -> errore
    # (non conta), -6 invalido; B a 18 -> errore, poi il contatore ferma tutto.
    assert calls == [0, 12, 24, 6, 18]
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_DUBIOUS), ("B", CONFIDENCE_DUBIOUS),
    ]
    assert aborted is None  # la griglia era completa: parziale no, dubbie si'


def test_identify_progress_extends_total_with_confirmations():
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two")}
    progress: list[tuple[int, int]] = []
    _, recognize_at = _tracker(table)
    identify_from_recognizer(60, recognize_at, on_progress=lambda i, n: progress.append((i, n)))
    assert progress[:5] == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]  # passata principale
    assert progress[-1] == (6, 6)  # la conferma di B estende il totale


def test_identify_confirm_loop_stops_when_recognizer_is_down():
    # il recognizer muore dopo due match singoli: la fase di conferma non deve
    # martellare l'endpoint; i singoli MAI verificati restano dubbi, non scartati
    table = {0: _m("A", "One"), 72: _m("B", "Two")}
    calls: list[int] = []

    def recognize_at(offset: int, rate: float = 1.0):
        calls.append(offset)
        if offset in table:
            return table[offset]
        raise RecognizerError("down")

    out, aborted = identify_from_recognizer(7200, recognize_at)
    # passo 36s: A@0, errore@36 (nessun retry sul buco: e' un errore), B@72,
    # poi 3 errori consecutivi (108/144/180) -> abort, zero conferme
    assert calls == [0, 36, 72, 108, 144, 180]
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_DUBIOUS), ("B", CONFIDENCE_DUBIOUS),
    ]
    assert aborted == 180


def test_identify_no_self_confirmation_on_short_audio():
    # audio cortissimo: nessun campione di conferma indipendente possibile ->
    # mai verificata, resta dubbia e il budget non si consuma
    table = {0: _m("A", "One")}
    calls, recognize_at = _tracker(table)
    out, _ = identify_from_recognizer(14, recognize_at)
    assert calls == [0]
    assert [(t.artist, t.confidence) for t in out] == [("A", CONFIDENCE_DUBIOUS)]


def test_identify_budget_consumed_by_retry_leaves_singles_unconfirmed():
    # ordine di consumo: il retry sul buco brucia l'unico budget, la conferma
    # di B non parte -> mai verificata, resta dubbia
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out, _ = identify_from_recognizer(60, recognize_at, max_extra_calls=1)
    assert calls == [0, 12, 24, 36, 42, 48]  # 42 = retry sul buco a 36; nessuna conferma
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_CONFIRMED), ("B", CONFIDENCE_DUBIOUS),
    ]


# --- retry pitch-compensato ---------------------------------------------------
# Un DJ che pitcha oltre ~2% rende la traccia invisibile a Shazam: i buchi
# rimasti tali dopo il retry spostato vengono ritentati con il segmento
# ricampionato (scala PITCH_RATES). Il primo rate che matcha diventa quello
# preferito: i buchi successivi lo provano da solo (il pitch di un set e'
# perlopiu' globale), le conferme del run lo riusano (altrimenti la conferma
# tornerebbe muta e scarterebbe una traccia vera).


def test_identify_pitch_retry_resolves_hole_and_remembers_rate():
    # C suona pitchata a +8%: matcha solo col segmento compensato a 0.92.
    # Primo buco: scala completa fino a 0.92; buchi successivi: subito 0.92.
    table = {0: _m("A", "One"), 12: _m("A", "One"),
             (24, 0.92): _m("C", "Pitched"), (36, 0.92): _m("C", "Pitched"),
             (48, 0.92): _m("C", "Pitched")}
    calls, recognize_at = _tracker(table)
    out, aborted = identify_from_recognizer(60, recognize_at)
    assert calls == [0, 12,
                     24, 30, (24, 0.96), (24, 1.04), (24, 0.92),
                     36, 42, (36, 0.92),
                     48, (48, 0.92)]
    assert [(t.artist, t.title, t.confidence) for t in out] == [
        ("A", "One", CONFIDENCE_CONFIRMED), ("C", "Pitched", CONFIDENCE_CONFIRMED),
    ]
    assert out[1].start_offset_seconds == 24  # registrata all'offset pianificato
    assert aborted is None


def test_identify_pitch_confirmation_uses_discovered_rate():
    # B matcha solo compensata (1.04): la conferma del singolo DEVE usare lo
    # stesso rate, altrimenti tornerebbe muta e scarterebbe una traccia vera.
    table = {0: _m("A", "One"), 12: _m("A", "One"),
             (24, 1.04): _m("B", "Two"), (18, 1.04): _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out, _ = identify_from_recognizer(36, recognize_at)
    assert (18, 1.04) in calls  # conferma pitch-compensata, non a rate naturale
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_CONFIRMED), ("B", CONFIDENCE_CONFIRMED),
    ]


def test_identify_pitch_probes_stop_after_first_holes():
    # Mix non pitchato con molti brani fuori catalogo: la scala completa si
    # sonda solo sui primi PITCH_PROBE_HOLES buchi, poi l'ipotesi pitch decade
    # e i buchi restanti non spendono piu' chiamate compensate.
    table = {0: _m("A", "One"), 18: _m("A", "One")}
    calls, recognize_at = _tracker(table)
    out, _ = identify_from_recognizer(72, recognize_at)  # offsets [0..60], buchi 24/36/48/60
    pitched = [c for c in calls if isinstance(c, tuple)]
    assert len(pitched) == PITCH_PROBE_HOLES * len(PITCH_RATES)
    assert not [c for c in pitched if c[0] == 60]  # il quarto buco non sonda piu'
    assert [(t.artist, t.confidence) for t in out] == [("A", CONFIDENCE_CONFIRMED)]


def test_identify_pitch_stops_at_budget():
    # il budget si esaurisce a meta' scala: i tentativi compensati si fermano li'
    table = {0: _m("A", "One"), 12: _m("A", "One")}
    calls, recognize_at = _tracker(table)
    out, _ = identify_from_recognizer(36, recognize_at, max_extra_calls=2)
    assert calls == [0, 12, 24, (24, 0.96), (24, 1.04)]
    assert [(t.artist, t.confidence) for t in out] == [("A", CONFIDENCE_CONFIRMED)]


def test_pitch_filter_args():
    # rate naturale: nessun filtro; compensato: resample->asetrate->resample
    # (il segmento va prima normalizzato a 16k, poi "rietichettato" per lo shift)
    assert _pitch_filter(1.0) == []
    assert _pitch_filter(0.96) == ["-af", "aresample=16000,asetrate=15360,aresample=16000"]
    assert _pitch_filter(1.08) == ["-af", "aresample=16000,asetrate=17280,aresample=16000"]


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
