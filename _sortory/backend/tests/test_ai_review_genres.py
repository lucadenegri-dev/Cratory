"""review_genres: formato del prompt, tool web_search, abbinamento per indice
(non più posizionale) con guardia sul titolo riecheggiato."""

import sys
import types

import pytest

from app.services import ai_tags


class _FakeParsed:
    def __init__(self, items):
        self.items = items


class _FakeResp:
    def __init__(self, items):
        self.parsed_output = _FakeParsed(items) if items is not None else None


def _install_fake_anthropic(monkeypatch, captured, items_out):
    class _FakeMessages:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return _FakeResp(items_out)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = _FakeMessages()

    mod = types.ModuleType("anthropic")
    mod.Anthropic = _FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def _install_fake_anthropic_sequence(monkeypatch, captured_calls, items_out_sequence):
    """Variante di _install_fake_anthropic che ritorna una risposta DIVERSA a
    ogni chiamata successiva (una per elemento di `items_out_sequence`, nello
    stesso ordine) — serve a testare il ritentativo di review_genres, dove il
    primo e il secondo tentativo devono poter avere esiti diversi.
    `captured_calls` è una lista: vi si accumulano i kwargs di OGNI chiamata,
    così il test può verificare sia il contenuto sia il NUMERO di chiamate
    effettuate."""
    state = {"n": 0}

    class _FakeMessages:
        def parse(self, **kwargs):
            captured_calls.append(kwargs)
            i = state["n"]
            state["n"] += 1
            return _FakeResp(items_out_sequence[i])

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = _FakeMessages()

    mod = types.ModuleType("anthropic")
    mod.Anthropic = _FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def test_review_genres_empty_input_no_call():
    assert ai_tags.review_genres([]) == []


def test_review_genres_prompt_tools_and_alignment(monkeypatch):
    captured = {}
    # Solo la prima traccia riceve risposta (indice e titolo corretti); la
    # seconda resta senza risposta -> unresolved (copre ancora il "padding").
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="Hidden Beauties",
                         genre="Tech House", confidence="high")])
    items = [{"artist": "ANNA", "title": "Hidden Beauties", "album": "EP1",
              "label": "Drumcode", "current_genre": "House",
              "candidates": ["Tech House", "Techno"]},
             {"artist": None, "title": None, "album": None, "label": None,
              "current_genre": None, "candidates": []}]
    out = ai_tags.review_genres(items)
    # tool web_search presente con max_uses limitato
    assert captured["tools"] == [{"type": "web_search_20250305",
                                  "name": "web_search", "max_uses": 3}]
    assert captured["model"] == "claude-haiku-4-5"
    # il listato contiene i metadati e i candidati
    text = captured["messages"][0]["content"]
    assert "ANNA - Hidden Beauties" in text
    assert "genere attuale: House" in text
    assert "Tech House; Techno" in text
    # output allineato per indice: la seconda traccia (nessuna risposta) è
    # None/low, non la risposta della prima
    assert out == [{"genre": "Tech House", "confidence": "high", "level": None},
                   {"genre": None, "confidence": "low", "level": None}]


def test_review_genres_no_parsed_output_raises(monkeypatch):
    # Fix: se il modello non produce alcun output strutturato (parsing
    # fallito, o turno consumato interamente dalla ricerca web) la funzione
    # deve sollevare invece di restituire dei _Review() di default per ogni
    # item — altrimenti il batch tornerebbe tutto genre=None e verrebbe
    # marcato "revisionato" per errore (bug di resumabilità).
    captured = {}
    _install_fake_anthropic(monkeypatch, captured, None)
    with pytest.raises(ai_tags.AiReviewError):
        ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                "label": None, "current_genre": None,
                                "candidates": []}])


def test_review_genres_weird_confidence_becomes_low(monkeypatch):
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="boh")])
    out = ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                  "label": None, "current_genre": None,
                                  "candidates": []}])
    assert out == [{"genre": "Acid", "confidence": "low", "level": None}]


def test_review_genres_shifted_titles_are_discarded_and_raise(monkeypatch):
    """Riproduce dal vivo lo slittamento osservato: il modello risponde con
    indici corretti (0,1,2) ma ognuno riecheggia la testa 'Artista - Titolo'
    della traccia SUCCESSIVA (a rotazione) invece della propria — nel formato
    reale osservato in produzione, non il solo titolo. Anche con la guardia
    per contenimento nessuna risposta è compatibile con l'item al proprio
    indice (gli artisti/titoli non si sovrappongono affatto) -> tutte
    scartate -> sotto soglia (metà) -> deve sollevare AiReviewError invece di
    restituire silenziosamente 3 unresolved (che il chiamante marcherebbe
    come "revisionati", perdendo la traccia)."""
    captured = {}
    items = [
        {"artist": "Oneohtrix Point Never", "title": "Boring Angel",
         "album": None, "label": None, "current_genre": "Ambient",
         "candidates": ["Ambient", "Electronic", "IDM"]},
        {"artist": "Artist B", "title": "Track Two",
         "album": None, "label": None, "current_genre": None,
         "candidates": []},
        {"artist": "Artist C", "title": "Track Three",
         "album": None, "label": None, "current_genre": None,
         "candidates": []},
    ]
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="Artist B - Track Two", genre="Electro",
                         confidence="high"),
         ai_tags._Review(index=1, title="Artist C - Track Three", genre="Techno",
                         confidence="high"),
         ai_tags._Review(index=2,
                         title="Oneohtrix Point Never - Boring Angel",
                         genre="Ambient", confidence="high")])
    with pytest.raises(ai_tags.AiReviewError):
        ai_tags.review_genres(items)


def test_review_genres_real_observed_echo_includes_artist_prefix(monkeypatch):
    """Caso reale osservato dal vivo: il modello riecheggia 'Artista -
    Titolo' invece del solo titolo (nonostante il prompt lo chieda), pur
    essendo perfettamente allineato per indice — compreso un apostrofo
    tipografico nell'item ('I Don’t Love Me Anymore') riecheggiato con
    apostrofo dritto dal modello. Con il confronto per contenimento tutte le
    risposte devono passare (nessuna eccezione, generi abbinati
    correttamente) invece di essere scartate in blocco come nel bug
    osservato (0 risposte su N superavano il vecchio controllo per
    uguaglianza -> AiReviewError su ogni batch)."""
    captured = {}
    items = [
        {"artist": "Oneohtrix Point Never", "title": "Replica",
         "album": None, "label": None, "current_genre": "Ambient",
         "candidates": ["Ambient", "Electronic"]},
        {"artist": "Oneohtrix Point Never",
         "title": "I Don’t Love Me Anymore", "album": None, "label": None,
         "current_genre": "Synthpop", "candidates": ["Synthpop"]},
    ]
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="Oneohtrix Point Never - Replica",
                         genre="Ambient", confidence="high"),
         ai_tags._Review(
             index=1,
             title="Oneohtrix Point Never - I Don't Love Me Anymore",
             genre="Synthpop", confidence="high")])
    out = ai_tags.review_genres(items)
    assert out == [{"genre": "Ambient", "confidence": "high", "level": None},
                   {"genre": "Synthpop", "confidence": "high", "level": None}]


def test_review_genres_short_title_below_threshold_skips_containment_guard(
        monkeypatch):
    """Un titolo molto corto (es. 'Acid', 4 caratteri normalizzati) è sotto
    la soglia minima per un confronto per contenimento affidabile: rischia di
    essere contenuto per puro caso nella riga riecheggiata di una traccia
    diversa (es. 'rataxes - Acid Face'). Sotto soglia la guardia testuale
    viene saltata e ci si affida al solo index, quindi la risposta passa
    comunque invece di essere scartata per un falso negativo di lunghezza."""
    captured = {}
    items = [{"artist": "Some Artist", "title": "Acid", "album": None,
              "label": None, "current_genre": None, "candidates": []}]
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="rataxes - Acid Face",
                         genre="Acid Techno", confidence="high")])
    out = ai_tags.review_genres(items)
    assert out == [{"genre": "Acid Techno", "confidence": "high", "level": None}]


def test_review_genres_out_of_order_indices_match_correct_track(monkeypatch):
    """Il modello risponde fuori ordine (2, 0, 1) ma con indice e titolo
    corretti: ogni traccia deve ricevere la SUA risposta, non quella nella
    posizione in cui è arrivata."""
    captured = {}
    items = [
        {"artist": "A", "title": "First", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "B", "title": "Second", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "C", "title": "Third", "album": None, "label": None,
         "current_genre": None, "candidates": []},
    ]
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=2, title="Third", genre="Techno",
                         confidence="high"),
         ai_tags._Review(index=0, title="First", genre="House",
                         confidence="high"),
         ai_tags._Review(index=1, title="Second", genre="Trance",
                         confidence="low")])
    out = ai_tags.review_genres(items)
    assert out == [{"genre": "House", "confidence": "high", "level": None},
                   {"genre": "Trance", "confidence": "low", "level": None},
                   {"genre": "Techno", "confidence": "high", "level": None}]


def test_review_genres_missing_response_for_one_item_stays_unresolved(monkeypatch):
    """Una traccia senza risposta corrispondente diventa unresolved; le altre
    restano corrette (non prendono la risposta di un'altra per riempire il
    buco)."""
    captured = {}
    items = [
        {"artist": "A", "title": "First", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "B", "title": "Second", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "C", "title": "Third", "album": None, "label": None,
         "current_genre": None, "candidates": []},
    ]
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="First", genre="House",
                         confidence="high"),
         ai_tags._Review(index=2, title="Third", genre="Techno",
                         confidence="high")])
    out = ai_tags.review_genres(items)
    assert out == [{"genre": "House", "confidence": "high", "level": None},
                   {"genre": None, "confidence": "low", "level": None},
                   {"genre": "Techno", "confidence": "high", "level": None}]


def test_review_genres_typographic_apostrophe_and_case_do_not_false_reject(monkeypatch):
    """Il confronto del titolo dev'essere tollerante a maiuscole/minuscole,
    spazi, punteggiatura e apostrofi tipografici (dati reali: 'I Don't Love Me
    Anymore' con apostrofo curvo ’)."""
    captured = {}
    items = [{"artist": "A", "title": "I Don’t Love Me Anymore",
              "album": None, "label": None, "current_genre": None,
              "candidates": []}]
    # Il modello riecheggia un titolo con apostrofo dritto, minuscolo e
    # spaziatura leggermente diversa: deve comunque passare la guardia.
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="i don't love me  anymore",
                         genre="Downtempo", confidence="high")])
    out = ai_tags.review_genres(items)
    assert out == [{"genre": "Downtempo", "confidence": "high", "level": None}]


def test_review_genres_out_of_range_index_ignored(monkeypatch):
    """Un indice fuori intervallo nella risposta viene ignorato senza
    corrompere l'abbinamento delle altre tracce."""
    captured = {}
    items = [
        {"artist": "A", "title": "First", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "B", "title": "Second", "album": None, "label": None,
         "current_genre": None, "candidates": []},
    ]
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=5, title="Ghost", genre="Junk",
                         confidence="high"),
         ai_tags._Review(index=0, title="First", genre="House",
                         confidence="high")])
    out = ai_tags.review_genres(items)
    assert out == [{"genre": "House", "confidence": "high", "level": None},
                   {"genre": None, "confidence": "low", "level": None}]


def test_review_genres_duplicate_index_keeps_first_occurrence(monkeypatch):
    """Se il modello risponde due volte allo stesso indice, tiene la prima
    occorrenza e non lascia che la seconda la sovrascriva silenziosamente."""
    captured = {}
    items = [{"artist": "A", "title": "First", "album": None, "label": None,
              "current_genre": None, "candidates": []}]
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="First", genre="House",
                         confidence="high"),
         ai_tags._Review(index=0, title="First", genre="Techno",
                         confidence="low")])
    out = ai_tags.review_genres(items)
    assert out == [{"genre": "House", "confidence": "high", "level": None}]


def test_review_genres_level_is_returned(monkeypatch):
    """Il livello di evidenza dichiarato dal modello (track/release/artist)
    arriva nel dict di output, allineato per indice come genre/confidence."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="Boring Angel", genre="Progressive Electronic",
                         confidence="high", level="release")])
    out = ai_tags.review_genres(
        [{"artist": "Oneohtrix Point Never", "title": "Boring Angel",
          "album": "R Plus Seven", "label": None, "current_genre": "Ambient",
          "candidates": []}])
    assert out == [{"genre": "Progressive Electronic", "confidence": "high",
                    "level": "release"}]


def test_review_genres_level_out_of_vocabulary_becomes_none(monkeypatch):
    """Un valore di level fuori dai tre ammessi (track/release/artist) viene
    normalizzato a None invece di propagarsi com'è o far sollevare eccezioni."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="low",
                         level="boh")])
    out = ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                  "label": None, "current_genre": None,
                                  "candidates": []}])
    assert out == [{"genre": "Acid", "confidence": "low", "level": None}]


def test_review_genres_level_absent_becomes_none(monkeypatch):
    """Se il modello non valorizza level (default del BaseModel), l'output
    riporta None e non solleva eccezioni."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    out = ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                  "label": None, "current_genre": None,
                                  "candidates": []}])
    assert out == [{"genre": "Acid", "confidence": "high", "level": None}]


def test_review_genres_artist_level_forces_confidence_low(monkeypatch):
    """Regola deterministica: level == 'artist' forza confidence a 'low' anche
    se il modello dichiara 'high' — è esattamente dove si concentra l'effetto
    alone dell'artista (vedi Oneohtrix Point Never / Boring Angel nel report)."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="Boring Angel", genre="Ambient",
                         confidence="high", level="artist")])
    out = ai_tags.review_genres(
        [{"artist": "Oneohtrix Point Never", "title": "Boring Angel",
          "album": "R Plus Seven", "label": None, "current_genre": None,
          "candidates": []}])
    assert out == [{"genre": "Ambient", "confidence": "low", "level": "artist"}]


def test_review_genres_budget_becomes_max_uses(monkeypatch):
    """Il tetto passato in max_web_searches finisce nel max_uses del tool
    web_search (non un valore fisso hardcoded)."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    ai_tags.review_genres(
        [{"artist": "A", "title": "B", "album": None, "label": None,
          "current_genre": None, "candidates": []}],
        max_web_searches=5)
    assert captured["tools"] == [{"type": "web_search_20250305",
                                  "name": "web_search", "max_uses": 5}]


def test_review_genres_zero_budget_omits_tool(monkeypatch):
    """Con budget 0 il tool web_search non va passato affatto (non con
    max_uses=0)."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    ai_tags.review_genres(
        [{"artist": "A", "title": "B", "album": None, "label": None,
          "current_genre": None, "candidates": []}],
        max_web_searches=0)
    assert "tools" not in captured


def test_review_genres_always_search_adds_instruction_to_prompt(monkeypatch):
    """In modalità 'cerca sempre' il prompt contiene l'istruzione aggiuntiva
    che spinge a cercare sul web invece di rispondere a memoria."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    ai_tags.review_genres(
        [{"artist": "A", "title": "B", "album": None, "label": None,
          "current_genre": None, "candidates": []}],
        always_search=True)
    text = captured["messages"][0]["content"]
    assert "DEVI cercare" in text


def test_review_genres_default_mode_has_no_always_search_instruction(monkeypatch):
    """Senza always_search (default) l'istruzione aggiuntiva non compare nel
    prompt — comportamento preesistente preservato."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    ai_tags.review_genres(
        [{"artist": "A", "title": "B", "album": None, "label": None,
          "current_genre": None, "candidates": []}])
    text = captured["messages"][0]["content"]
    assert "DEVI cercare" not in text


def test_review_genres_retries_once_on_empty_items_then_succeeds(monkeypatch):
    """Giro 3 osservato dal vivo: al primo tentativo parsed_output.items è
    una lista VUOTA (zero risposte su 3 tracce, zero ricerche eseguite) —
    ben sotto la soglia della guardia esistente. review_genres deve
    ritentare la STESSA richiesta una volta sola; se il secondo tentativo è
    valido, il batch va a buon fine (nessuna eccezione) e le tracce non
    tornano indietro senza motivo."""
    calls = []
    items = [
        {"artist": "Djrum", "title": "Waxcap", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "B", "title": "Second", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "C", "title": "Third", "album": None, "label": None,
         "current_genre": None, "candidates": []},
    ]
    _install_fake_anthropic_sequence(monkeypatch, calls, [
        [],  # tentativo 1: lista vuota, il caso osservato dal vivo
        [ai_tags._Review(index=0, title="Djrum - Waxcap", genre="Breaks",
                         confidence="high", level="track"),
         ai_tags._Review(index=1, title="Second", genre="House",
                         confidence="high"),
         ai_tags._Review(index=2, title="Third", genre="Techno",
                         confidence="high")],
    ])
    out = ai_tags.review_genres(items)
    assert len(calls) == 2
    assert out == [{"genre": "Breaks", "confidence": "high", "level": "track"},
                   {"genre": "House", "confidence": "high", "level": None},
                   {"genre": "Techno", "confidence": "high", "level": None}]


def test_review_genres_retries_once_then_raises_if_still_empty(monkeypatch):
    """Se anche il secondo tentativo è vuoto/troppo corto, review_genres
    solleva AiReviewError come oggi — ma con ESATTAMENTE due chiamate
    all'API: un solo ritentativo, non un ciclo."""
    calls = []
    items = [
        {"artist": "A", "title": "First", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "B", "title": "Second", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "C", "title": "Third", "album": None, "label": None,
         "current_genre": None, "candidates": []},
    ]
    _install_fake_anthropic_sequence(monkeypatch, calls, [[], []])
    with pytest.raises(ai_tags.AiReviewError):
        ai_tags.review_genres(items)
    assert len(calls) == 2


def test_review_genres_all_null_genre_is_valid_no_retry(monkeypatch):
    """Giro 2 osservato dal vivo: tutti gli elementi presenti e allineati
    per indice/titolo (passano la guardia), ma con genre=None su tutti —
    un'astensione motivata ('non so'), non un fallimento. Non deve scattare
    alcun ritentativo: una sola chiamata, output con tutti i generi a
    null."""
    calls = []
    items = [
        {"artist": "Djrum", "title": "Waxcap", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "B", "title": "Second", "album": None, "label": None,
         "current_genre": None, "candidates": []},
        {"artist": "C", "title": "Third", "album": None, "label": None,
         "current_genre": None, "candidates": []},
    ]
    _install_fake_anthropic_sequence(monkeypatch, calls, [
        [ai_tags._Review(index=0, title="Djrum - Waxcap", genre=None,
                         confidence="low"),
         ai_tags._Review(index=1, title="Second", genre=None,
                         confidence="low"),
         ai_tags._Review(index=2, title="Third", genre=None,
                         confidence="low")],
    ])
    out = ai_tags.review_genres(items)
    assert len(calls) == 1
    assert out == [{"genre": None, "confidence": "low", "level": None},
                   {"genre": None, "confidence": "low", "level": None},
                   {"genre": None, "confidence": "low", "level": None}]


def test_review_genres_prompt_requires_one_item_per_track_default_mode(monkeypatch):
    """Il prompt deve pretendere esplicitamente un elemento per traccia
    (anche in modalità non always_search), altrimenti una lista vuota o
    incompleta non viene riconosciuta dal modello come risposta invalida."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    ai_tags.review_genres(
        [{"artist": "A", "title": "B", "album": None, "label": None,
          "current_genre": None, "candidates": []}])
    text = captured["messages"][0]["content"].lower()
    assert "un elemento per" in text


def test_review_genres_prompt_requires_one_item_per_track_always_search_mode(
        monkeypatch):
    """Stesso requisito, ma in modalità always_search: qui il prompt include
    anche 'preferisci null se la ricerca non basta', che potrebbe essere
    letto come autorizzazione a omettere l'elemento — il requisito di un
    elemento per traccia deve valere comunque."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    ai_tags.review_genres(
        [{"artist": "A", "title": "B", "album": None, "label": None,
          "current_genre": None, "candidates": []}],
        always_search=True)
    text = captured["messages"][0]["content"].lower()
    assert "un elemento per" in text


def test_review_genres_compound_genre_reduced_to_first_component(monkeypatch):
    """Caso reale osservato dal vivo (Djrum - Waxcap): il modello restituisce
    la stringa composita di Beatport copiata pari pari invece di scegliere un
    solo genere, nonostante il prompt lo richieda esplicitamente. Il primo
    componente ('Breaks') va tenuto: è la scelta più specifica secondo la
    convenzione già in uso in DiscogsMetaClient.lookup (styles[0])."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="Djrum - Waxcap",
                         genre="Breaks / Breakbeat / UK Bass",
                         confidence="high", level="track")])
    out = ai_tags.review_genres(
        [{"artist": "Djrum", "title": "Waxcap", "album": None, "label": None,
          "current_genre": None, "candidates": []}])
    assert out == [{"genre": "Breaks", "confidence": "high", "level": "track"}]


def test_review_genres_comma_separated_list_reduced_to_first_component(monkeypatch):
    """Stesso difetto ma con separatore virgola (es. genere Discogs multi-style
    incollato pari pari): tenuto il primo componente."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Techno, House, Acid",
                         confidence="high")])
    out = ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                  "label": None, "current_genre": None,
                                  "candidates": []}])
    assert out == [{"genre": "Techno", "confidence": "high", "level": None}]


def test_review_genres_legitimate_ampersand_and_hyphen_genres_untouched(
        monkeypatch):
    """La rete di sicurezza deve intervenire SOLO sui separatori di elenco
    (virgola, barra, punto e virgola, trattino verticale), non su qualunque
    punteggiatura: generi legittimi come 'Drum & Bass', 'Tech House' e
    'Hi-NRG' non contengono liste e devono passare identici, senza essere
    troncati alla prima parola/componente per errore."""
    captured = {}
    genres = ["Drum & Bass", "Tech House", "Hi-NRG"]
    for g in genres:
        captured.clear()
        _install_fake_anthropic(
            monkeypatch, captured,
            [ai_tags._Review(index=0, title="B", genre=g, confidence="high")])
        out = ai_tags.review_genres(
            [{"artist": "A", "title": "B", "album": None, "label": None,
              "current_genre": None, "candidates": []}])
        assert out == [{"genre": g, "confidence": "high", "level": None}], g


def test_review_genres_prompt_forbids_list_separators(monkeypatch):
    """Il prompt deve prevenire il difetto a monte, non solo la rete di
    sicurezza nel codice: istruzione esplicita a scegliere il genere singolo
    più specifico quando la fonte riporta una lista/tag composto, con
    l'esempio reale osservato ('Breaks / Breakbeat / UK Bass')."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    ai_tags.review_genres(
        [{"artist": "A", "title": "B", "album": None, "label": None,
          "current_genre": None, "candidates": []}])
    text = captured["messages"][0]["content"]
    assert "Breaks / Breakbeat / UK Bass" in text
    assert "separator" in text.lower()


def test_review_genres_retries_once_when_parsed_output_is_none_then_succeeds(
        monkeypatch):
    """Fix 1: quando il primo tentativo non produce alcun output strutturato
    (parsed_output None — parsing fallito o turno consumato dalla ricerca
    web), review_genres deve ritentare la STESSA richiesta una volta invece
    di sollevare subito: è precisamente il fallimento che il budget di
    ricerca più alto (fino a 10 ricerche in una singola chiamata per i
    sotto-batch bisognosi) rende più probabile, e la composizione dei
    sotto-batch è deterministica — un batch che fallisce così rifallirebbe
    identico alla passata successiva, senza mai marcare i suoi file."""
    calls = []
    items = [{"artist": "A", "title": "First", "album": None, "label": None,
              "current_genre": None, "candidates": []}]
    _install_fake_anthropic_sequence(monkeypatch, calls, [
        None,  # tentativo 1: nessun output strutturato
        [ai_tags._Review(index=0, title="First", genre="House",
                         confidence="high")],
    ])
    out = ai_tags.review_genres(items)
    assert len(calls) == 2
    assert out == [{"genre": "House", "confidence": "high", "level": None}]


def test_review_genres_raises_after_retry_when_parsed_output_still_none(
        monkeypatch):
    """Se anche il secondo tentativo non produce output strutturato,
    review_genres solleva come prima — ma con ESATTAMENTE due chiamate
    all'API: un solo ritentativo complessivo, non uno per tipo di
    fallimento, e nessuna possibilità di catena."""
    calls = []
    items = [{"artist": "A", "title": "First", "album": None, "label": None,
              "current_genre": None, "candidates": []}]
    _install_fake_anthropic_sequence(monkeypatch, calls, [None, None])
    with pytest.raises(ai_tags.AiReviewError):
        ai_tags.review_genres(items)
    assert len(calls) == 2


def test_review_genres_max_tokens_regression_stays_below_sdk_streaming_ceiling(
        monkeypatch):
    """Regressione (non un test di comportamento: un vincolo dell'ambiente,
    va spiegato o fra sei mesi sembra arbitrario). Il commit 97727b0 aveva
    alzato max_tokens 4096->32000 per dare margine ai sotto-batch bisognosi
    (fino a 10 ricerche web in una chiamata), sul presupposto — sbagliato —
    che i risultati delle ricerche pesassero sull'output: sono invece token
    di INPUT, misurato dal vivo su un batch da 10 con 3 ricerche:
    input=25065, output=382. L'output reale di questa funzione è una lista
    strutturata di poche decine di token per traccia (poche centinaia in
    totale per un batch da 10): l'aumento non serviva a nulla, e ha rotto la
    feature. L'SDK Python di Anthropic rifiuta le chiamate non-streaming la
    cui durata stimata (funzione di max_tokens) supera 10 minuti:
    'Streaming is required for operations that may take longer than 10
    minutes. See https://github.com/anthropics/anthropic-sdk-python#long-requests'
    — con max_tokens=32000 OGNI chiamata falliva con questo ValueError,
    azzerando la feature (misurato dal vivo su 10 tracce:
    proposed=0, confirmed=0, unresolved=10, web_searches=0). Fissiamo qui un
    tetto ben sotto la soglia dell'SDK (~21333 token per claude-haiku-4-5,
    dalla formula in anthropic._base_client._calculate_nonstreaming_timeout)
    così che un futuro "diamo più margine" non ripeta lo stesso errore senza
    che un test lo segnali."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                            "label": None, "current_genre": None,
                            "candidates": []}])
    # Tetto documentato: ampio margine sopra il fabbisogno reale (~400 token
    # per un batch da 10) ma ben sotto la soglia di rifiuto non-streaming
    # dell'SDK.
    assert captured["max_tokens"] <= 8192


def test_review_genres_reports_web_search_count_on_success(monkeypatch):
    """Fix 4: il numero di ricerche web effettivamente eseguite (da
    response.usage.server_tool_use.web_search_requests) viene comunicato al
    chiamante come attributo `web_searches` sul valore di ritorno — senza
    cambiare la forma per-traccia (resta una list di dict allineata per
    indice, confrontabile con == a una list semplice)."""
    calls = []

    class _RespWithUsage(_FakeResp):
        def __init__(self, items, web_search_requests):
            super().__init__(items)
            self.usage = types.SimpleNamespace(
                server_tool_use=types.SimpleNamespace(
                    web_search_requests=web_search_requests))

    class _FakeMessages:
        def parse(self, **kwargs):
            calls.append(kwargs)
            return _RespWithUsage(
                [ai_tags._Review(index=0, title="B", genre="Acid",
                                 confidence="high")], 4)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = _FakeMessages()

    mod = types.ModuleType("anthropic")
    mod.Anthropic = _FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", mod)

    out = ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                  "label": None, "current_genre": None,
                                  "candidates": []}])
    assert out == [{"genre": "Acid", "confidence": "high", "level": None}]
    assert getattr(out, "web_searches", None) == 4


def test_review_genres_web_search_count_defaults_to_zero_without_usage(
        monkeypatch):
    """Una risposta (reale o fake) priva di `usage.server_tool_use` non deve
    far sollevare l'estrazione del conteggio: default a zero."""
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="B", genre="Acid", confidence="high")])
    out = ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                  "label": None, "current_genre": None,
                                  "candidates": []}])
    assert getattr(out, "web_searches", None) == 0


def test_review_genres_raises_with_accumulated_web_search_count(monkeypatch):
    """L'eccezione sollevata dopo il ritentativo esaurito porta con sé il
    totale delle ricerche web consumate nei DUE tentativi (Fix 4): il
    chiamante non deve perdere il costo di un batch fallito solo perché non
    ha prodotto un esito utilizzabile."""
    calls = []
    items = [{"artist": "A", "title": "First", "album": None, "label": None,
              "current_genre": None, "candidates": []}]

    class _RespEmptyWithUsage(_FakeResp):
        def __init__(self, items, web_search_requests):
            super().__init__(items)
            self.usage = types.SimpleNamespace(
                server_tool_use=types.SimpleNamespace(
                    web_search_requests=web_search_requests))

    responses = [_RespEmptyWithUsage([], 2), _RespEmptyWithUsage([], 3)]
    state = {"n": 0}

    class _FakeMessages:
        def parse(self, **kwargs):
            calls.append(kwargs)
            i = state["n"]
            state["n"] += 1
            return responses[i]

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = _FakeMessages()

    mod = types.ModuleType("anthropic")
    mod.Anthropic = _FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", mod)

    with pytest.raises(ai_tags.AiReviewError) as exc_info:
        ai_tags.review_genres(items)
    assert len(calls) == 2
    assert exc_info.value.web_searches == 5


def test_review_genres_no_title_on_item_skips_guard(monkeypatch):
    """Se la traccia non ha titolo (None), la guardia viene saltata e ci si
    affida solo all'indice."""
    captured = {}
    items = [{"artist": "A", "title": None, "album": None, "label": None,
              "current_genre": None, "candidates": []}]
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(index=0, title="Qualunque Cosa", genre="House",
                         confidence="high")])
    out = ai_tags.review_genres(items)
    assert out == [{"genre": "House", "confidence": "high", "level": None}]
