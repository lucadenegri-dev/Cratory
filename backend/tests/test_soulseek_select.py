from app.integrations.slskd import SlskdFile
from app.services.soulseek_select import (
    QualityPreference, ScoredCandidate, auto_pick_candidates, best_for_auto,
    query_variants, rank_candidates, search_candidates,
)


def _f(filename, *, bitrate=None, slot=True, length=None, speed=None):
    return SlskdFile(username="u", filename=filename, size=1, bitrate=bitrate,
                     length=length, has_free_slot=slot, queue_length=0,
                     upload_speed=speed)


def test_lossless_outranks_mp3_for_same_name():
    files = [
        _f("Daft Punk - Da Funk.mp3", bitrate=320),
        _f("Daft Punk - Da Funk.flac"),
    ]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked[0].file.extension == "flac"


def test_below_min_bitrate_excluded():
    files = [_f("Daft Punk - Da Funk.mp3", bitrate=128)]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked == []


def test_weak_name_match_excluded():
    files = [_f("Completely Unrelated Song.flac")]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked == []


def test_best_for_auto_returns_none_below_threshold():
    # match parziale: nome plausibile ma non perfetto, solo mp3 a 256
    files = [_f("daft - da funk (live bootleg rip).mp3", bitrate=256)]
    best = best_for_auto(files, artist="Daft Punk", title="Da Funk")
    # confidence sotto 0.7 -> niente auto-pick
    assert best is None


def test_best_for_auto_picks_strong_lossless():
    files = [_f("Daft Punk - Da Funk.flac")]
    best = best_for_auto(files, artist="Daft Punk", title="Da Funk")
    assert best is not None
    assert best.confidence >= 0.7


def test_unknown_bitrate_lossy_not_excluded():
    # Soulseek spesso non riporta il bitrate in ricerca: un mp3 con bitrate ignoto
    # e nome coerente NON deve essere scartato (prima finiva tier 0 -> escluso).
    files = [_f("Daft Punk - Da Funk.mp3", bitrate=None)]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert len(ranked) == 1
    assert ranked[0].quality_tier == 1


def test_available_uploader_outranks_queued_same_track():
    # Stessa traccia/qualita': chi ha lo slot libero deve battere chi non ce l'ha
    # (altrimenti si finisce "Queued, Remotely" e il download non parte mai).
    files = [
        _f("Daft Punk - Da Funk.flac", slot=False),
        _f("Daft Punk - Da Funk.flac", slot=True),
    ]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked[0].file.has_free_slot is True


def test_name_match_uses_basename_not_full_path():
    # Path Soulseek reale e rumoroso: il titolo combacia col nome file anche se il
    # path e' lungo (cartelle/anno/formato). Prima veniva escluso (name_score basso).
    files = [_f("Music\\Arca\\Arca - KiCk i (2020) [FLAC]\\02  Time.flac")]
    ranked = rank_candidates(files, artist="Arca", title="Time")
    assert len(ranked) == 1
    best = best_for_auto(files, artist="Arca", title="Time")
    assert best is not None
    assert best.confidence >= 0.7


# --- Durata attesa nel ranking (disk-first: la versione giusta, non solo il nome) ---


def test_durata_esatta_batte_qualita_superiore():
    # Nome identico: l'mp3 con la durata giusta batte il flac con durata sbagliata
    # (titolo uguale ma versione diversa: il classico radio edit vs extended).
    files = [
        _f("Daft Punk - Da Funk.flac", length=500),
        _f("Daft Punk - Da Funk.mp3", bitrate=320, length=410),
    ]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk",
                             expected_duration=409)
    assert ranked[0].file.extension == "mp3"


def test_durata_ignota_resta_neutra():
    # Soulseek spesso non riporta length: l'ignoto non deve impedire l'auto-pick.
    files = [_f("Daft Punk - Da Funk.flac")]
    best = best_for_auto(files, artist="Daft Punk", title="Da Funk",
                         expected_duration=409)
    assert best is not None


def test_durata_sbagliata_abbassa_confidenza_sotto_auto_pick():
    files = [_f("Daft Punk - Da Funk.flac", length=500)]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk",
                             expected_duration=409)
    assert len(ranked) == 1
    assert ranked[0].confidence < 0.7


# --- Version-matching esplicito -----------------------------------------------


def test_versione_richiesta_premiata_radio_penalizzato():
    files = [
        _f("Artist - Song (Radio Edit).flac"),
        _f("Artist - Song (Extended Mix).flac"),
    ]
    ranked = rank_candidates(files, artist="Artist", title="Song Extended Mix")
    assert "Extended" in ranked[0].file.filename


def test_versione_indesiderata_penalizzata():
    files = [
        _f("Artist - Song (Live).flac"),
        _f("Artist - Song.flac"),
    ]
    ranked = rank_candidates(files, artist="Artist", title="Song")
    assert ranked[0].file.filename == "Artist - Song.flac"


def test_original_mix_equivale_a_nessuna_versione():
    # "Original Mix" e' la versione di default: nessuna penalita' (se venisse
    # penalizzata, questo candidato finirebbe sotto la soglia minima ed escluso).
    files = [_f("Artist - Song (Original Mix).flac")]
    ranked = rank_candidates(files, artist="Artist", title="Song")
    assert len(ranked) == 1


# --- Auto-pick: la confidenza si valuta su OGNI candidato -----------------------


def _sc(score, confidence):
    return ScoredCandidate(file=_f("Artist - Song.flac"), name_score=0.5,
                           quality_tier=3, score=score, confidence=confidence)


def test_auto_pick_candidates_filtra_per_confidenza():
    # Il primo per score e' incerto: non deve oscurare il candidato confidente
    # piu' in basso (prima si guardava solo ranked[0] → needs_review a torto).
    ranked = [_sc(150, 0.5), _sc(120, 0.9), _sc(100, 0.3)]
    eligible = auto_pick_candidates(ranked)
    assert [c.score for c in eligible] == [120]


def test_auto_pick_candidates_vuota_se_tutti_sotto_soglia():
    assert auto_pick_candidates([_sc(150, 0.69), _sc(120, 0.4)]) == []


def test_auto_pick_candidates_preserva_ordine_per_score():
    ranked = [_sc(150, 0.9), _sc(120, 0.8)]
    assert [c.score for c in auto_pick_candidates(ranked)] == [150, 120]


# --- uploadSpeed ---------------------------------------------------------------


def test_uploader_veloce_davanti_a_parita():
    files = [
        _f("Daft Punk - Da Funk.flac", speed=None),
        _f("Daft Punk - Da Funk.flac", speed=2_000_000),
    ]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked[0].file.upload_speed == 2_000_000


# --- Varianti di query ----------------------------------------------------------


def test_query_variants_pulizia_progressiva():
    v = query_variants("Daft Punk", "One More Time (feat. Romanthony) [Radio Edit]")
    assert v[0] == "Daft Punk One More Time (feat. Romanthony) [Radio Edit]"
    assert v[1] == "Daft Punk One More Time"
    assert len(v) == len(set(v))  # dedup


def test_query_variants_suffisso_versione():
    v = query_variants("deadmau5", "Strobe - Extended Mix")
    assert "Extended" not in v[-1]
    assert v[-1].startswith("deadmau5 Strobe")


def test_query_variants_titolo_pulito_resta_unico():
    # Titolo gia' pulito: una sola variante, niente doppioni.
    assert query_variants("Arca", "Time") == ["Arca Time"]


def test_search_candidates_cascata_si_ferma_alla_prima_utile():
    class FakeClient:
        def __init__(self):
            self.queries = []

        def search(self, artist, title, **kw):
            q = f"{artist} {title}".strip()
            self.queries.append(q)
            if "(" in q:  # la query letterale non trova nulla
                return []
            return [_f("Daft Punk - One More Time.flac", length=320)]

    client = FakeClient()
    ranked = search_candidates(
        client, artist="Daft Punk",
        title="One More Time (feat. Romanthony) [Radio Edit]",
        expected_duration=320,
    )
    assert len(ranked) == 1
    assert len(client.queries) == 2  # si ferma alla seconda variante
    # il ranking confronta col titolo ORIGINALE, non con la query pulita
    assert ranked[0].name_score > 0.4


def test_search_candidates_esaurisce_le_varianti_a_vuoto():
    class EmptyClient:
        def search(self, artist, title, **kw):
            return []

    assert search_candidates(EmptyClient(), artist="A", title="B (feat. C) - Dub") == []
