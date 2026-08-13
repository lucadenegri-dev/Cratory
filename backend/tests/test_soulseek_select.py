from app.integrations.slskd import SlskdFile
from app.services.soulseek_select import (
    QualityPreference, ScoredCandidate, auto_pick_candidates,
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
    assert ranked[0].confidence >= 0.7


# --- Path nel punteggio: underscore e artista nella cartella padre --------------


def test_nome_file_con_underscore_riconosciuto():
    # Stile Soulseek classico: "Daft_Punk_-_Digital_Love.flac" e' un match
    # perfetto ma con gli underscore trattati come caratteri di parola veniva
    # scartato del tutto (name_score ~0.38, sotto la soglia 0.45).
    files = [_f("Daft_Punk_-_Digital_Love.flac")]
    ranked = rank_candidates(files, artist="Daft Punk", title="Digital Love")
    assert len(ranked) == 1
    assert ranked[0].confidence >= 0.7


def test_naming_scene_con_underscore_e_trattini():
    # Rip old-school: cartella VA + "B2-daft_punk-digital_love.mp3".
    files = [_f("VA-Ibiza_2001\\B2-daft_punk-digital_love.mp3", bitrate=320)]
    ranked = rank_candidates(files, artist="Daft Punk", title="Digital Love")
    assert len(ranked) == 1


def test_artista_quasi_uguale_nella_cartella_padre():
    # Artista solo nella cartella, e per giunta senza il "The": la similarita'
    # va cercata sul singolo segmento del path (la cartella), non sul path
    # intero appiattito dove il segnale affoga nel rumore.
    files = [_f("Chemical Brothers\\04 - Elektrobank (Album Version).mp3",
                bitrate=320)]
    ranked = rank_candidates(files, artist="The Chemical Brothers",
                             title="Elektrobank")
    assert len(ranked) == 1
    assert ranked[0].confidence >= 0.7


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
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk",
                             expected_duration=409)
    assert len(ranked) == 1
    assert ranked[0].confidence >= 0.7


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
    # L'ultima variante col titolo e' senza suffisso versione; dopo resta solo
    # la ultima-spiaggia solo-artista.
    assert v[-1] == "deadmau5"
    assert "Extended" not in v[-2]
    assert v[-2].startswith("deadmau5 Strobe")


def test_query_variants_titolo_pulito_resta_unico():
    # Titolo gia' pulito: niente doppioni, solo la coppia piena e la
    # ultima-spiaggia solo-artista.
    assert query_variants("Arca", "Time") == ["Arca Time", "Arca"]


def test_query_variants_artisti_multipli_riducono_al_primo():
    # Soulseek fa match AND sui token: con "A, B" in query i file nominati col
    # solo artista principale non matchano MAI. Le ultime varianti devono
    # provare col solo primo artista.
    v = query_variants("FISHER, Chris Lake", "Losing It")
    assert v[0] == "FISHER, Chris Lake Losing It"
    assert "FISHER Losing It" in v
    assert v.index("FISHER Losing It") > v.index("FISHER, Chris Lake Losing It")


def test_query_variants_artista_con_ampersand_e_feat():
    v = query_variants("Dom Dolla & Nelly Furtado", "Dreamin")
    assert "Dom Dolla Dreamin" in v
    v2 = query_variants("Jamie Jones feat. Kelis", "Sunshine")
    assert "Jamie Jones Sunshine" in v2


def test_query_variants_primo_artista_combinato_con_titolo_pulito():
    # La riduzione dell'artista si combina con la pulizia del titolo: e' la
    # variante "come la digiterebbe un umano".
    v = query_variants("Camelphat, Elderbrook", "Cola (Extended Mix)")
    assert "Camelphat Cola" in v


def test_query_variants_solo_artista_come_ultima_spiaggia():
    # Caso reale (NIP Collective — I'm About (Rave Mix)): nei rip da vinile il
    # titolo nei nomi file e' inaffidabile (apostrofi resi come ', ´ o nulla,
    # posizione traccia al posto dell'artista, titolo solo nella cartella della
    # release). Ogni query col titolo torna vuota; "nip collective" da sola
    # trova 80+ file, e il ranking sceglie sul pool. La query solo-artista va
    # provata per ULTIMA: l'ancora resta l'artista, mai il titolo da solo.
    v = query_variants("NIP Collective", "I'm About (Rave Mix)")
    assert v[-1] == "NIP Collective"
    assert v[0] == "NIP Collective I'm About (Rave Mix)"


def test_query_variants_solo_artista_usa_il_primo_artista():
    v = query_variants("FISHER, Chris Lake", "Losing It")
    assert v[-1] == "FISHER"


def test_query_variants_senza_artista_niente_variante_vuota():
    # Artista mancante: nessuna variante solo-artista (sarebbe una query vuota
    # o, peggio, solo-titolo senza ancora).
    v = query_variants("", "Some Title (Remix)")
    assert all(x.strip() for x in v)
    assert "Some Title" in v[-1] or v[-1] == "Some Title"


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


def test_search_candidates_usa_un_budget_di_attesa_ridotto():
    # /api/downloads/candidates attendeva fino a ~45s (3 varianti x 15s di
    # max_wait): il budget per variante deve restare basso cosi' il totale
    # nel caso peggiore si aggira sui 15s.
    from app.services import soulseek_select as select_mod

    class FakeClient:
        def __init__(self):
            self.kwargs = []

        def search(self, artist, title, **kw):
            self.kwargs.append(kw)
            return [_f("Daft Punk - Da Funk.flac")]

    client = FakeClient()
    search_candidates(client, artist="Daft Punk", title="Da Funk")
    assert client.kwargs[0].get("max_wait") == select_mod.CANDIDATE_SEARCH_MAX_WAIT
    assert select_mod.CANDIDATE_SEARCH_MAX_WAIT <= 5.0


def test_search_candidates_timeout_ricerca_sotto_il_budget_di_attesa():
    # slskd popola /responses solo a ricerca COMPLETA: se il searchTimeout del
    # daemon (default 6s) supera il max_wait dell'attesa, per le tracce rare si
    # legge una lista vuota anche quando i file esistono (a mano si trovano, in
    # automatico no). Il timeout passato al daemon deve stare SOTTO l'attesa.
    class FakeClient:
        def __init__(self):
            self.kwargs = []

        def search(self, artist, title, **kw):
            self.kwargs.append(kw)
            return [_f("Daft Punk - Da Funk.flac")]

    client = FakeClient()
    search_candidates(client, artist="Daft Punk", title="Da Funk")
    kw = client.kwargs[0]
    assert kw.get("search_timeout_ms") is not None
    assert kw["search_timeout_ms"] < kw["max_wait"] * 1000


def test_search_candidates_max_wait_personalizzato_mantiene_l_invariante():
    # Il job in background non ha vincoli di latenza HTTP: puo' passare un
    # budget piu' ampio, e il timeout del daemon deve seguirlo restando sotto.
    class FakeClient:
        def __init__(self):
            self.kwargs = []

        def search(self, artist, title, **kw):
            self.kwargs.append(kw)
            return [_f("Daft Punk - Da Funk.flac")]

    client = FakeClient()
    search_candidates(client, artist="Daft Punk", title="Da Funk", max_wait=15.0)
    kw = client.kwargs[0]
    assert kw["max_wait"] == 15.0
    assert kw["search_timeout_ms"] < 15_000


def test_search_candidates_esaurisce_le_varianti_a_vuoto():
    class EmptyClient:
        def search(self, artist, title, **kw):
            return []

    assert search_candidates(EmptyClient(), artist="A", title="B (feat. C) - Dub") == []


# --- Giro finale a filtro ridotto (not_found → needs_review) --------------------


def test_search_candidates_ripescaggio_a_filtro_ridotto():
    # Nome debole ma plausibile (score ~0.40, sotto la soglia 0.45): oggi la
    # cascata torna vuota → not_found secco, mentre a mano il file si trova e
    # si riconosce. Esaurite le varianti, i file raccolti vanno ri-rankati con
    # soglia ridotta: l'esito diventa needs_review coi candidati gia' pronti.
    class WeakClient:
        def search(self, artist, title, **kw):
            return [_f("mix rip\\dafunk daft.flac")]

    ranked = search_candidates(WeakClient(), artist="Daft Punk", title="Da Funk")
    assert len(ranked) == 1  # stesso file da ogni variante: dedup, non doppioni
    # Mai auto-pickabile: il ripescaggio serve alla revisione umana, non al
    # download automatico di un match incerto.
    assert ranked[0].confidence < 0.7


def test_search_candidates_ripescaggio_non_salva_la_spazzatura():
    class GarbageClient:
        def search(self, artist, title, **kw):
            return [_f("Completely Unrelated Song.flac")]

    assert search_candidates(GarbageClient(), artist="Daft Punk", title="Da Funk") == []


def test_search_candidates_ripescaggio_qualita_sotto_soglia():
    # Caso reale (NIP Collective 1993): l'UNICA copia in rete e' un mp3 a
    # 226kbps con nome quasi perfetto (name_score 0.93). Il floor di qualita'
    # la scartava in silenzio → not_found. Un match di nome pieno a bassa
    # qualita' va ripescato per la revisione umana, MAI auto-scaricato: la
    # confidenza resta sotto la soglia di auto-pick per costruzione.
    class LowBitrateClient:
        def search(self, artist, title, **kw):
            return [_f("nip collective - advanced structure ep (1993)\\"
                       "a1   live on mars (original mix).mp3", bitrate=226)]

    ranked = search_candidates(LowBitrateClient(), artist="NIP Collective",
                               title="Live On Mars (Original Mix)")
    assert len(ranked) == 1
    assert ranked[0].confidence < 0.7


def test_search_candidates_bassa_qualita_e_nome_debole_resta_fuori():
    # Il ripescaggio qualita' richiede il nome PIENO (0.45): bassa qualita'
    # E nome debole insieme restano spazzatura.
    class BadClient:
        def search(self, artist, title, **kw):
            return [_f("mix rip\\dafunk daft.mp3", bitrate=128)]

    assert search_candidates(BadClient(), artist="Daft Punk", title="Da Funk") == []
