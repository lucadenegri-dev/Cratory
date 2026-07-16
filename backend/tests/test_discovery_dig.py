"""Test Discovery v2 dig (nessuna rete: search Discogs finta)."""

from types import SimpleNamespace

import pytest

from app.services.discovery_dig import (
    _clean_artist,
    _is_owned,
    _lead_from_release,
    _owned_index,
    _reasons,
    _title_candidates,
    _window,
    dig,
)


def _release(title, *, year=2020, label="Lbl", style="Acid House", have=100, want=10,
             rid=1, uri=None, fmt=None):
    return {
        "id": rid, "title": title, "year": year, "label": [label], "style": [style],
        "community": {"have": have, "want": want}, "format": fmt or [],
        "uri": uri or f"/release/{rid}", "cover_image": "http://img",
    }


def _lib(*items):
    """Track finte. Ogni item: (artist, title) o (artist, title, {"label":..., "genre":..., "album":...})."""
    out = []
    for it in items:
        extra = it[2] if len(it) > 2 else {}
        out.append(SimpleNamespace(
            artist=it[0], title=it[1],
            label=extra.get("label"), genre=extra.get("genre"),
            album=extra.get("album"),
        ))
    return out


def test_lead_parsing_and_various_skipped():
    lead = _lead_from_release(_release("Aphex Twin - Xtal", year=1992, rid=1), "Acid House")
    assert lead.artist == "Aphex Twin" and lead.title == "Xtal"
    assert lead.year == 1992 and lead.label == "Lbl" and lead.styles == ["Acid House"]
    assert lead.discogs_url == "https://www.discogs.com/release/1"
    assert _lead_from_release(_release("Various - Comp"), "x") is None
    assert _lead_from_release({"title": "no separator"}, "x") is None


# --- Task 3: grammatica Discogs — normalizzazione artisti ---------------------


def test_clean_artist_strips_discogs_disambiguation():
    # Discogs marca gli omonimi: Tyree* non e' un artista diverso da Tyree
    assert _clean_artist("Tyree*") == ("Tyree", ["tyree"])
    assert _clean_artist("Gravity Zero (4)") == ("Gravity Zero", ["gravity zero"])


def test_clean_artist_splits_multi_artist_fields():
    display, keys = _clean_artist("Nail* / Einzelkind")
    assert display == "Nail / Einzelkind"          # niente cruft nella UI
    assert keys == ["nail / einzelkind", "nail", "einzelkind"]


def test_clean_artist_keeps_ampersand_names_matchable_whole():
    # 'Above & Beyond' e' UN artista: la chiave intera deve esserci per prima
    display, keys = _clean_artist("Above & Beyond")
    assert display == "Above & Beyond"
    assert keys[0] == "above & beyond"


def test_clean_artist_does_not_split_on_comma_and_ampersand():
    # '&' e ',' non sono separatori affidabili: si accetta di PERDERE il credito sullo
    # split vero ('OPTML, Gravity Zero & RADD' e' davvero tre artisti) pur di non
    # rischiare l'aggancio falso su un nome di band. Resta la chiave intera, coi
    # suffissi Discogs comunque ripuliti.
    display, keys = _clean_artist("OPTML, Gravity Zero (4) & RADD (3)")
    assert display == "OPTML, Gravity Zero & RADD"
    assert keys == ["optml, gravity zero & radd"]


def test_clean_artist_does_not_split_band_names_with_ampersand_or_comma():
    # 'Earth, Wind & Fire' e' UN artista: spezzarlo darebbe chiavi generiche
    # ('fire', 'wind') che agganciano la libreria per sbaglio.
    assert _clean_artist("Earth, Wind & Fire")[1] == ["earth, wind & fire"]
    assert _clean_artist("Above & Beyond")[1] == ["above & beyond"]


def test_lead_carries_clean_artist_and_all_styles():
    item = _release("Tyree* - Acid Crash", rid=7)
    item["style"] = ["Acid House", "Chicago House"]
    lead = _lead_from_release(item, "Acid House")
    assert lead.artist == "Tyree"
    assert lead.artist_keys == ["tyree"]
    assert lead.styles == ["Acid House", "Chicago House"]


# --- Task 5: il possesso — release contro tracce -----------------------------


def test_title_candidates_covers_format_suffix_and_splits():
    assert "Piercing Love" in _title_candidates("Piercing Love EP")
    assert "Sentipede" in _title_candidates("Sentipede / 808 Rhythm Traxx 3")
    assert "Acid Trax" in _title_candidates("Acid Trax (Original Mix)")


def test_owned_via_discogs_cruft_artist():
    # regressione: possiedi Tyree, Discogs lo chiama Tyree* -> te lo riproponeva
    tracks, albums = _owned_index(_lib(("Tyree", "Acid Crash")))
    lead = _lead_from_release(_release("Tyree* - Acid Crash", rid=1), "x")
    assert _is_owned(lead, tracks, albums) is True


def test_owned_via_album_when_release_is_an_ep():
    tracks, albums = _owned_index(_lib(("Fabien D'Estival", "Some Track",
                                        {"album": "Piercing Love EP"})))
    lead = _lead_from_release(_release("Fabien D'Estival - Piercing Love EP", rid=1), "x")
    assert _is_owned(lead, tracks, albums) is True


def test_owned_via_track_when_release_title_carries_the_format_suffix():
    # Lo scenario cardine: possiedi la traccia 'Piercing Love', Discogs chiama la
    # release 'Piercing Love EP'. Passa da owned_tracks + strip del suffisso.
    tracks, albums = _owned_index(_lib(("Fabien D'Estival", "Piercing Love")))
    lead = _lead_from_release(_release("Fabien D'Estival - Piercing Love EP", rid=1), "x")
    assert _is_owned(lead, tracks, albums) is True


def test_owned_via_one_side_of_a_split_title():
    tracks, albums = _owned_index(_lib(("Nail", "Sentipede")))
    lead = _lead_from_release(_release("Nail* / Einzelkind - Sentipede / 808 Rhythm Traxx 3", rid=1), "x")
    assert _is_owned(lead, tracks, albums) is True


def test_not_owned_stays_not_owned():
    tracks, albums = _owned_index(_lib(("Tyree", "Acid Crash")))
    lead = _lead_from_release(_release("Armando - Land Of Confusion", rid=1), "x")
    assert _is_owned(lead, tracks, albums) is False


def test_not_owned_requires_both_artist_and_title_to_match():
    # Il possesso e' la COPPIA (artista, titolo): un match su un solo lato non basta.
    # Senza questo, una semantica 'OR' rotta passerebbe il test qui sopra (che cambia
    # entrambi i lati) e scarterebbe lead buoni per un'omonimia di titolo.
    tracks, albums = _owned_index(_lib(("Tyree", "Acid Crash")))
    # stesso artista, altro titolo -> non posseduto
    same_artist = _lead_from_release(_release("Tyree* - Other Track", rid=1), "x")
    assert _is_owned(same_artist, tracks, albums) is False
    # stesso titolo, altro artista -> non posseduto
    same_title = _lead_from_release(_release("Armando - Acid Crash", rid=2), "x")
    assert _is_owned(same_title, tracks, albums) is False


def test_dig_dedup_vs_library_and_pressings():
    def search(**kw):
        return [
            _release("Owned Artist - Owned Track", rid=1),                 # gia' in libreria
            _release("New Artist - New Track", rid=2),
            _release("New Artist - New Track", rid=3),                     # altra pressatura: dedup
        ]

    res = dig(None, seed_type="genre", value="Acid House", search_releases=search,
              library=_lib(("Owned Artist", "Owned Track")), limit=50)
    pairs = [(l.artist, l.title) for l in res.leads]
    assert ("Owned Artist", "Owned Track") not in pairs       # gia' posseduto
    assert pairs.count(("New Artist", "New Track")) == 1       # pressature collassate
    assert res.seed_type == "genre" and res.value == "Acid House"


def test_dig_label_seed_uses_label_filter():
    seen: dict = {}

    def search(**kw):
        seen.update(kw)
        return [_release("A - B", rid=9)]

    dig(None, seed_type="label", value="Warp", search_releases=search, library=[], limit=10)
    assert seen.get("label") == "Warp"


# NB: `test_dig_adventurous_surfaces_deep_cuts` stava qui. Il Task 6 lo ha reso falso per
# progetto (la rarita' non entra piu' nel punteggio): riscritto semanticamente in fondo,
# nella sezione Task 6, come `test_flat_taste_keeps_the_pile_order`.


def test_dig_familiar_first_when_safe():
    def search(**kw):
        return [
            _release("Stranger - Tune", rid=1, have=20),
            _release("Known - Other", rid=2, have=20),
        ]

    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=_lib(("Known", "Something Else")), adventurousness=0.1)
    assert res.leads[0].artist == "Known"


def test_dig_truncates_to_limit():
    def search(**kw):
        return [_release(f"A{i} - T{i}", rid=i) for i in range(50)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[], limit=10)
    assert len(res.leads) == 10


# --- de-noise: filtri, dedup varianti, cap artista, domanda ------------------


def test_dig_filters_offtarget_formats():
    def search(**kw):
        return [
            _release("Comp Maker - Big Box", rid=1, fmt=["CD", "Compilation"]),
            _release("Mix DJ - Continuous", rid=2, fmt=["DJ Mix"]),
            _release("Real Artist - Real Track", rid=3, fmt=["Vinyl", '12"']),
        ]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[], limit=50)
    pairs = [(l.artist, l.title) for l in res.leads]
    assert pairs == [("Real Artist", "Real Track")]  # comp e DJ mix scartati


def test_dig_filters_dead_self_released_but_keeps_wanted():
    def search(**kw):
        return [
            _release("Nobody - Bedroom Demo", rid=1, have=0, want=0,
                     label="Not On Label (Nobody Self-released)"),
            _release("Cult Hero - Sought Gem", rid=2, have=2, want=40,
                     label="Not On Label (Cult Hero Self-released)"),
        ]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[], limit=50)
    pairs = [(l.artist, l.title) for l in res.leads]
    assert ("Nobody", "Bedroom Demo") not in pairs        # self-released morto: scartato
    assert ("Cult Hero", "Sought Gem") in pairs           # self-released ma RICHIESTO: tenuto


def test_dig_dedup_variant_titles():
    def search(**kw):
        return [
            _release("A - Track", rid=1),
            _release("A - Track (Original Mix)", rid=2),
            _release("A - Track [Radio Edit]", rid=3),
        ]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[], limit=50)
    assert len(res.leads) == 1  # varianti collassate


def test_dig_caps_per_artist():
    def search(**kw):
        return [_release(f"Prolific - Track {i}", rid=i) for i in range(6)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[], limit=50)
    assert len(res.leads) == 2  # max 2 per artista


# NB: `test_dig_demand_beats_anonymous_rarity` stava qui. La domanda non ordina piu' i lead
# nel punteggio (la codifica la finestra): riscritto semanticamente in fondo, nella sezione
# Task 6, come `test_score_ignores_demand_which_the_window_already_encodes`. La domanda come
# FILTRO resta comunque coperta qui sopra da `test_dig_filters_dead_self_released_but_keeps_wanted`.


# --- Task 1: TasteProfile + tokenizzazione stile -----------------------------

from app.services.discovery_dig import TasteProfile, _style_tokens, FAMILIARITY_FULL_AT


def test_style_tokens_normalizes_and_splits():
    assert _style_tokens("Deep House") == {"deep", "house"}
    assert _style_tokens("Tech-House / Minimal") == {"tech", "house", "minimal"}
    assert _style_tokens(None) == set()
    assert _style_tokens("") == set()


def test_taste_profile_from_tracks_aggregates():
    p = TasteProfile.from_tracks(_lib(
        ("Aphex Twin", "Xtal", {"label": "Warp", "genre": "IDM"}),
        ("Aphex Twin", "Ageispolis", {"label": "Warp", "genre": "IDM"}),
        ("Boards Of Canada", "Roygbiv", {"label": "Warp", "genre": "Downtempo"}),
    ))
    assert p.artist_count(["aphex twin"]) == 2
    assert p.owned_labels == {"warp"}
    assert {"idm"} in p.genre_sets
    assert {"downtempo"} in p.genre_sets


def test_taste_profile_familiarity_is_graduated():
    p = TasteProfile.from_tracks(_lib(
        ("Solo", "A"),
        ("Trio", "A"), ("Trio", "B"), ("Trio", "C"),
    ))
    assert p.familiarity(["solo"]) == 1 / FAMILIARITY_FULL_AT
    assert p.familiarity(["trio"]) == 1.0          # 3 release: piena
    assert p.familiarity(["unknown"]) == 0.0


def test_taste_profile_affinities():
    p = TasteProfile.from_tracks(_lib(("A", "B", {"label": "Warp", "genre": "Acid House"})))
    assert p.label_affinity("Warp") == 1.0
    assert p.label_affinity("warp") == 1.0
    assert p.label_affinity("Other") == 0.0
    assert p.label_affinity(None) == 0.0
    assert p.style_affinity(["Acid House"]) == 1.0     # match esatto: {acid,house} su se stesso
    assert p.style_affinity(["Techno"]) == 0.0
    assert p.style_affinity(None) == 0.0


# --- Task 4: affinita' di stile graduata (Jaccard per genere) ----------------


def test_style_affinity_is_graduated_not_binary():
    p = TasteProfile.from_tracks(_lib(("A", "T", {"genre": "Deep House"})))
    assert p.style_affinity(["Deep House"]) == 1.0
    # {house} / {deep, house, acid} — un token condiviso NON vale 1.0
    assert p.style_affinity(["Acid House"]) == pytest.approx(1 / 3)
    assert p.style_affinity(["Drum n Bass"]) == 0.0


def test_style_affinity_uses_all_release_styles():
    p = TasteProfile.from_tracks(_lib(("A", "T", {"genre": "Chicago House"})))
    assert p.style_affinity(["Acid House", "Chicago House"]) == 1.0


def test_style_affinity_compares_per_genre_not_against_a_single_bag():
    # Regressione, e il valore puntuale e' il punto: la Jaccard va calcolata contro
    # OGNI genere separatamente, non contro l'unione dei token della libreria.
    # Per-genere: max({house}/{acid,deep,house}, 0) = 1/3 <- atteso.
    # Sacco unico: {house}/{acid,deep,house,drum,n,bass} = 1/6. Un '< 1.0' non
    # distinguerebbe i due (1/6 lo soddisfa): morderebbe solo il ritorno al match
    # binario, non il ritorno all'unione.
    p = TasteProfile.from_tracks(_lib(
        ("A", "T1", {"genre": "Deep House"}),
        ("B", "T2", {"genre": "Drum n Bass"}),
    ))
    assert p.style_affinity(["Acid House"]) == pytest.approx(1 / 3)


def test_familiarity_is_max_across_split_artists():
    p = TasteProfile.from_tracks(_lib(("Einzelkind", "T1"), ("Einzelkind", "T2"),
                                      ("Einzelkind", "T3")))
    _, keys = _clean_artist("Nail* / Einzelkind")
    assert p.familiarity(keys) == 1.0        # 3 tracce = familiarita' piena
    assert p.familiarity(["sconosciuto"]) == 0.0


def test_familiarity_is_graduated():
    p = TasteProfile.from_tracks(_lib(("Tyree", "T1")))
    assert p.familiarity(["tyree"]) == pytest.approx(1 / 3)


# --- Task 2: scoring esteso con i segnali di gusto ---------------------------


def test_dig_label_boost_changes_order():
    def search(**kw):
        return [
            _release("No Label Match - Track", rid=1, label="Unknown Lbl", have=20),
            _release("Followed - Track", rid=2, label="Warp", have=20),
        ]

    # Riferimento di gusto: possiedo qualcosa su Warp. adv basso => conta il gusto.
    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=[], taste_tracks=_lib(("Whoever", "Whatever", {"label": "Warp"})),
              adventurousness=0.1)
    assert res.leads[0].label == "Warp"


def test_dig_style_affinity_changes_order():
    def search(**kw):
        return [
            _release("Off Style - Track", rid=1, style="Trance", have=20),
            _release("On Style - Track", rid=2, style="Acid House", have=20),
        ]

    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=[], taste_tracks=_lib(("Whoever", "Whatever", {"genre": "Acid House"})),
              adventurousness=0.1)
    # `DiscoveryLead.style` (singolare) e' diventato `.styles` (Task 3): il test era
    # rimasto mascherato dal crash di `_reasons`, non aggiornato al rename.
    assert res.leads[0].styles == ["Acid House"]


def test_dig_graduated_familiarity_prefers_more_collected():
    def search(**kw):
        return [
            _release("Once - Track", rid=1, have=20),
            _release("Thrice - Track", rid=2, have=20),
        ]

    # 'Thrice' lo possiedo 3 volte (familiarita' piena), 'Once' una volta sola.
    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=[],
              taste_tracks=_lib(
                  ("Once", "a"),
                  ("Thrice", "a"), ("Thrice", "b"), ("Thrice", "c"),
              ),
              adventurousness=0.1)
    assert res.leads[0].artist == "Thrice"


def test_dig_dedup_is_library_wide_even_with_playlist_taste():
    def search(**kw):
        return [_release("Owned Elsewhere - Track", rid=1)]

    # Il riferimento di gusto e' una playlist che NON contiene il brano,
    # ma il brano e' gia' in libreria: deve restare scartato (dedup library-wide).
    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=_lib(("Owned Elsewhere", "Track")),
              taste_tracks=_lib(("Other", "Thing")), limit=50)
    assert res.leads == []


# --- Task 3: reason codes (spiegazioni deterministiche) ----------------------

from datetime import datetime, timezone


def _codes(lead):
    return {r.code for r in lead.reasons}


def test_dig_emits_rare_wanted_and_deep_cut():
    def search(**kw):
        return [_release("Cult - Grail", rid=1, have=3, want=120)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[])
    lead = res.leads[0]
    assert "rare_wanted" in _codes(lead)
    assert "deep_cut" in _codes(lead)
    rare = next(r for r in lead.reasons if r.code == "rare_wanted")
    assert rare.data == {"have": 3, "want": 120}


def test_dig_no_rare_wanted_when_not_demanded():
    def search(**kw):
        return [_release("Common - Tune", rid=1, have=4000, want=2)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[])
    codes = _codes(res.leads[0])
    assert "rare_wanted" not in codes
    assert "deep_cut" not in codes        # have=4000 > soglia


def test_dig_emits_taste_reason_codes():
    def search(**kw):
        return [_release("Followed - Track", rid=1, label="Warp", style="Acid House", have=20)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[],
              taste_tracks=_lib(("Followed", "Older", {"label": "Warp", "genre": "Acid House"})))
    lead = res.leads[0]
    codes = _codes(lead)
    assert {"label_followed", "artist_collected", "style_match"} <= codes
    art = next(r for r in lead.reasons if r.code == "artist_collected")
    assert art.data == {"artist": "Followed", "count": 1}


def test_dig_emits_recent_reason():
    cur = datetime.now(timezone.utc).year

    def search(**kw):
        return [_release("New - Drop", rid=1, year=cur, have=20)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[])
    assert "recent" in _codes(res.leads[0])


# --- Task 7: i reason diventano selettivi (non scattano su tutto) ------------
#
# NB: helper rinominato `_reason_codes` (nel piano era `_codes`) perche' nel modulo
# esiste gia' un `_codes(lead)` (sopra) che legge `lead.reasons` dal risultato di
# `dig()`. Un secondo `def _codes` con arita' diversa avrebbe sovrascritto il primo
# nel namespace del modulo e rotto in silenzio i quattro test precedenti (TypeError
# per argomento mancante) — non e' una libera scelta di stile, e' per non spezzare
# i test esistenti che chiamano `_codes(lead)` con un solo argomento.


def _reason_codes(lead, profile, seed_type="genre", year=2026):
    return {r.code for r in _reasons(lead, profile, seed_type, year)}


def test_deep_cut_requires_demand():
    p = TasteProfile.from_tracks([])
    # nessuno lo ha E nessuno lo cerca: non e' una gemma, e' rumore
    assert "deep_cut" not in _reason_codes(_lead_from_release(_release("A - T", have=10, want=0, rid=1), "x"), p)
    assert "deep_cut" in _reason_codes(_lead_from_release(_release("A - T", have=10, want=5, rid=2), "x"), p)
    assert "deep_cut" not in _reason_codes(_lead_from_release(_release("A - T", have=200, want=50, rid=3), "x"), p)


def test_label_followed_not_emitted_on_a_label_dig():
    p = TasteProfile.from_tracks(_lib(("X", "Y", {"label": "Lbl"})))
    lead = _lead_from_release(_release("A - T", label="Lbl", rid=1), "Lbl")
    assert "label_followed" in _reason_codes(lead, p, seed_type="genre")
    # su un dig per etichetta ce l'hanno TUTTI: informa zero
    assert "label_followed" not in _reason_codes(lead, p, seed_type="label")


def test_style_match_needs_more_than_one_shared_token():
    p = TasteProfile.from_tracks(_lib(("A", "T", {"genre": "Deep House"})))
    exact = _lead_from_release(_release("A - T", style="Deep House", rid=1), "x")
    loose = _lead_from_release(_release("A - T", style="Acid House", rid=2), "x")
    assert "style_match" in _reason_codes(exact, p)
    assert "style_match" not in _reason_codes(loose, p)   # 0.33 < soglia 0.5


def test_recent_badge_survives_even_though_year_left_the_score():
    p = TasteProfile.from_tracks([])
    assert "recent" in _reason_codes(_lead_from_release(_release("A - T", year=2025, rid=1), "x"), p, year=2026)
    assert "recent" not in _reason_codes(_lead_from_release(_release("A - T", year=1988, rid=2), "x"), p, year=2026)


# --- Task 2: _window — profondita' della pila ordinata per domanda -----------


def test_window_depth_zero_is_the_canon():
    assert _window(0.0, 43345) == [1, 2, 3]


def test_window_depth_one_is_the_bottom_of_the_pile():
    # 43345 release -> 434 pagine, ma Discogs si ferma a 100 (pagina 101 -> 404)
    assert _window(1.0, 43345) == [98, 99, 100]


def test_window_is_always_three_pages():
    # regressione: una finestra di 4 pagine costa una richiesta di troppo a ogni dig
    for depth in (0.0, 0.15, 0.5, 0.85, 1.0):
        assert len(_window(depth, 43345)) == 3


def test_window_is_monotonic_in_depth():
    starts = [_window(d, 43345)[0] for d in (0.0, 0.15, 0.5, 0.85, 1.0)]
    assert starts == sorted(starts)
    assert starts == [1, 16, 49, 83, 98]


def test_window_short_pile_ignores_depth():
    # 150 release = 2 pagine: non c'e' profondita' da scegliere
    assert _window(0.0, 150) == [1, 2]
    assert _window(1.0, 150) == [1, 2]


def test_window_tiny_pile():
    assert _window(0.5, 40) == [1]


def test_window_empty_pile():
    assert _window(0.5, 0) == []


# --- Task 6: il punteggio e' solo gusto ---------------------------------------

from app.services.discovery_dig import _score, _select, _weights


def test_weights_drop_the_label_signal_on_a_label_dig():
    # su un dig per etichetta TUTTI i lead hanno l'etichetta del seme: costante, non ordina
    w = _weights("label")
    assert w.label == 0.0
    assert w.artist + w.style == pytest.approx(1.0)   # il peso si redistribuisce
    g = _weights("genre")
    assert (g.artist, g.label, g.style) == (0.5, 0.3, 0.2)


def test_score_is_taste_only():
    profile = TasteProfile.from_tracks(_lib(("Tyree", "T1"), ("Tyree", "T2"), ("Tyree", "T3")))
    mine = _lead_from_release(_release("Tyree - New One", have=9999, want=0, year=1990, rid=1), "x")
    other = _lead_from_release(_release("Sconosciuto - Rare One", have=1, want=999, year=2026, rid=2), "x")
    w = _weights("genre")
    # have/want/anno non entrano piu' nel punteggio: solo il gusto ordina
    assert _score(mine, profile, w) > _score(other, profile, w)


def test_score_ignores_year():
    profile = TasteProfile.from_tracks(_lib(("Tyree", "T1")))
    old = _lead_from_release(_release("Tyree - A", year=1988, rid=1), "x")
    new = _lead_from_release(_release("Tyree - B", year=2026, rid=2), "x")
    assert _score(old, profile, _weights("genre")) == _score(new, profile, _weights("genre"))


def test_flat_taste_keeps_the_pile_order():
    """Sostituisce `test_dig_adventurous_surfaces_deep_cuts`.

    Quel test asseriva che con `adventurousness` alta il deep cut (have basso)
    scavalcasse il mainstream (have=9000). Col Task 6 e' FALSO PER PROGETTO, non per
    svista: la rarita' (`novelty`) e' uscita dal punteggio, e `adventurousness` non
    ordina piu' nulla. Far emergere i deep cut e' compito della FINESTRA (`_window`):
    la profondita' sceglie il bacino, il gusto ordina dentro il bacino.

    Il comportamento vero, che qui si fissa: a gusto piatto i lead pareggiano e lo
    stable sort di `_select` conserva l'ordine della pila (l'ordine per domanda con cui
    Discogs risponde). E' il fallback VOLUTO quando il gusto non discrimina.
    """
    profile = TasteProfile.from_tracks([])          # riferimento vuoto: nessun segnale aggancia
    w = _weights("genre")
    mainstream = _lead_from_release(_release("Pop Star - Hit", rid=1, have=9000), "x")
    deep_cut = _lead_from_release(_release("Obscure One - Deep Cut", rid=2, have=20), "x")
    # have 9000 vs 20: prima ribaltava l'ordine, ora non entra proprio nel punteggio
    assert _score(mainstream, profile, w) == _score(deep_cut, profile, w) == 0.0
    for lead in (mainstream, deep_cut):
        lead.score = _score(lead, profile, w)
    assert [l.artist for l in _select([mainstream, deep_cut], 50)] == ["Pop Star", "Obscure One"]


def test_score_ignores_demand_which_the_window_already_encodes():
    """Sostituisce `test_dig_demand_beats_anonymous_rarity`.

    La domanda non batte piu' niente NEL PUNTEGGIO: ordina il BACINO, non i lead dentro
    il bacino. Dentro una finestra il `want` e' ~costante (pagina 30: mediana 287,
    minimo 284) — non ha potere discriminante. Quale finestra si guardi lo decide `depth`
    (`_window`), non lo score.

    `_demand` resta viva e usata: la legge `_reasons` per il codice `rare_wanted`, e resta
    un FILTRO anti-rumore in `_lead_from_release` (self-released morti). Non e' scomparsa
    dal motore, e' scomparsa dall'ORDINAMENTO.
    """
    # stesso gusto per entrambi (una release a testa nel riferimento) -> pari merito
    profile = TasteProfile.from_tracks(_lib(("Anon", "Older"), ("Wanted", "Older")))
    w = _weights("genre")
    untraded = _lead_from_release(_release("Anon - Untraded", rid=1, have=1, want=0), "x")
    grail = _lead_from_release(_release("Wanted - Grail", rid=2, have=1, want=80), "x")
    # want 0 vs 80: prima decideva l'ordine, ora i due pareggiano (gusto identico)
    assert _score(untraded, profile, w) == _score(grail, profile, w) == pytest.approx(0.5 / 3)
