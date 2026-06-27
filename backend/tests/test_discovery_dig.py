"""Test Discovery v2 dig (nessuna rete: search Discogs finta)."""

from types import SimpleNamespace

from app.services.discovery_dig import _lead_from_release, dig


def _release(title, *, year=2020, label="Lbl", style="Acid House", have=100, want=10,
             rid=1, uri=None, fmt=None):
    return {
        "id": rid, "title": title, "year": year, "label": [label], "style": [style],
        "community": {"have": have, "want": want}, "format": fmt or [],
        "uri": uri or f"/release/{rid}", "cover_image": "http://img",
    }


def _lib(*items):
    """Track finte. Ogni item: (artist, title) o (artist, title, {"label":..., "genre":...})."""
    out = []
    for it in items:
        extra = it[2] if len(it) > 2 else {}
        out.append(SimpleNamespace(
            artist=it[0], title=it[1],
            label=extra.get("label"), genre=extra.get("genre"),
        ))
    return out


def test_lead_parsing_and_various_skipped():
    lead = _lead_from_release(_release("Aphex Twin - Xtal", year=1992, rid=1), "Acid House")
    assert lead.artist == "Aphex Twin" and lead.title == "Xtal"
    assert lead.year == 1992 and lead.label == "Lbl" and lead.style == "Acid House"
    assert lead.discogs_url == "https://www.discogs.com/release/1"
    assert _lead_from_release(_release("Various - Comp"), "x") is None
    assert _lead_from_release({"title": "no separator"}, "x") is None


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


def test_dig_adventurous_surfaces_deep_cuts():
    def search(**kw):
        return [
            _release("Pop Star - Hit", rid=1, have=9000),         # mainstream (molto posseduto)
            _release("Obscure One - Deep Cut", rid=2, have=20),   # raro
        ]

    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=[], adventurousness=0.9)
    assert (res.leads[0].artist, res.leads[0].title) == ("Obscure One", "Deep Cut")


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


def test_dig_demand_beats_anonymous_rarity():
    def search(**kw):
        return [
            _release("Anon - Untraded", rid=1, have=1, want=0),    # raro ma nessuno lo cerca
            _release("Wanted - Grail", rid=2, have=1, want=80),    # raro E molto cercato
        ]

    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=[], adventurousness=0.9)
    assert res.leads[0].artist == "Wanted"  # la gemma richiesta in cima


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
    assert p.artist_count("aphex twin") == 2
    assert p.owned_labels == {"warp"}
    assert {"idm", "downtempo"} <= p.genre_tokens


def test_taste_profile_familiarity_is_graduated():
    p = TasteProfile.from_tracks(_lib(
        ("Solo", "A"),
        ("Trio", "A"), ("Trio", "B"), ("Trio", "C"),
    ))
    assert p.familiarity("Solo") == 1 / FAMILIARITY_FULL_AT
    assert p.familiarity("Trio") == 1.0          # 3 release: piena
    assert p.familiarity("Unknown") == 0.0


def test_taste_profile_affinities():
    p = TasteProfile.from_tracks(_lib(("A", "B", {"label": "Warp", "genre": "Acid House"})))
    assert p.label_affinity("Warp") == 1.0
    assert p.label_affinity("warp") == 1.0
    assert p.label_affinity("Other") == 0.0
    assert p.label_affinity(None) == 0.0
    assert p.style_affinity("Acid House") == 1.0     # token in comune
    assert p.style_affinity("Techno") == 0.0
    assert p.style_affinity(None) == 0.0


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
    assert res.leads[0].style == "Acid House"


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
