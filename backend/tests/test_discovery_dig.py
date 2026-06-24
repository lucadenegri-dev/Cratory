"""Test Discovery v2 dig (nessuna rete: search Discogs finta)."""

from types import SimpleNamespace

from app.services.discovery_dig import _lead_from_release, dig


def _release(title, *, year=2020, label="Lbl", style="Acid House", have=100, want=10,
             rid=1, uri=None):
    return {
        "id": rid, "title": title, "year": year, "label": [label], "style": [style],
        "community": {"have": have, "want": want},
        "uri": uri or f"/release/{rid}", "cover_image": "http://img",
    }


def _lib(*pairs):
    return [SimpleNamespace(artist=a, title=t) for a, t in pairs]


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
