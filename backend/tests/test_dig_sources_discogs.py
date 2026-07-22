"""La sorgente Discogs: traduzione della finestra in pagine e mapping dei record."""

from app.services.dig_sources import Pile, Seed
from app.services.dig_sources.discogs import DiscogsSource


class _FakeDiscogs:
    """Client Discogs finto: registra le chiamate, non tocca la rete."""

    def __init__(self, items=None, total=43345):
        self.items = items if items is not None else []
        self.total = total
        self.calls: list[dict] = []

    def count_releases(self, **kw):
        self.calls.append({"op": "count", **kw})
        return self.total

    def search_releases(self, **kw):
        self.calls.append({"op": "search", **kw})
        return self.items


def _release(title, *, rid=1, style="Acid House"):
    return {
        "id": rid, "title": title, "year": 2020, "label": ["Lbl"], "style": [style],
        "community": {"have": 100, "want": 10}, "format": [],
        "uri": f"/release/{rid}", "cover_image": "http://img",
    }


def test_probe_resolves_style_first():
    fake = _FakeDiscogs()
    pile = DiscogsSource(fake).probe(Seed("genre", "Acid House"))
    assert fake.calls[0] == {"op": "count", "style": "Acid House"}
    assert pile.height == 43345 and pile.reach == 10_000
    assert pile.resolution == "style"


def test_probe_falls_back_to_the_discogs_shelf_when_the_style_is_unknown():
    # 'Electronic' non e' uno style ma un genre: la sonda ripiega e lo dichiara.
    class _Fake(_FakeDiscogs):
        def count_releases(self, **kw):
            self.calls.append({"op": "count", **kw})
            return 0 if "style" in kw else 4_960_093

    fake = _Fake()
    pile = DiscogsSource(fake).probe(Seed("genre", "Electronic"))
    assert pile.resolution == "genre" and pile.height == 4_960_093


def test_probe_of_an_unknown_seed_type_is_an_empty_pile_and_costs_nothing():
    fake = _FakeDiscogs()
    pile = DiscogsSource(fake).probe(Seed("playlist", "x"))
    assert (pile.height, pile.reach) == (0, 0)
    assert fake.calls == []


def test_fetch_asks_for_exactly_three_pages_whatever_the_offset():
    # 3 pagine da 100 = i 300 item della finestra. Una quarta sarebbe una richiesta
    # sprecata a ogni dig.
    fake = _FakeDiscogs()
    src = DiscogsSource(fake)
    pile = Pile(height=43345, reach=10_000, resolution="style", handle={"style": "Acid House"})
    for offset, expected in [(0, [1, 2, 3]), (4850, [49, 50, 51]), (9700, [98, 99, 100])]:
        fake.calls.clear()
        src.fetch(Seed("genre", "Acid House"), pile, offset, 300)
        assert fake.calls[-1]["pages"] == expected


def test_fetch_reuses_the_filters_probe_already_resolved():
    fake = _FakeDiscogs()
    pile = Pile(height=300, reach=10_000, resolution="label", handle={"label": "Warp"})
    DiscogsSource(fake).fetch(Seed("label", "Warp"), pile, 0, 300)
    assert fake.calls[-1]["label"] == "Warp"
    assert not any(c["op"] == "count" for c in fake.calls)   # nessuna ri-sonda


def test_to_lead_carries_the_neutral_identity_fields():
    lead = DiscogsSource(_FakeDiscogs()).to_lead(
        _release("Aphex Twin - Xtal", rid=7), Seed("genre", "Acid House"))
    assert lead.source == "discogs"
    assert lead.source_id == "7"
    assert lead.source_url == "https://www.discogs.com/release/7"
    assert lead.stream_url is None
