"""Il motore dei simili: orchestrazione, archi, ranking. Nessuna rete."""

import pytest

from app.models import Track
from app.services.dig_sources import DiscoveryLead
from app.services.discovery_similar import (
    EdgeReport,
    Origin,
    SimilarResult,
    similar,
)


def _track(**kw) -> Track:
    """Una Track non persistita: il motore legge solo gli attributi."""
    base = dict(id=1, artist="Jasmín", title="Bite The Hand", album="Bite The Hand",
                label="Hessle Audio", genre="Bass", year=2025, has_local_file=True)
    base.update(kw)
    return Track(**base)


def _lead(artist="Pearson Sound", title="Which Way Is Up", **kw) -> DiscoveryLead:
    return DiscoveryLead(artist=artist, artist_keys=[artist.lower()], title=title,
                         source="bandcamp", **kw)


class _FakeSource:
    """Sorgente finta: restituisce origine e archi prefissati, registra le chiamate."""

    name = "bandcamp"

    def __init__(self, origin=None, edges=None):
        self._origin = origin
        self._edges = edges or []
        self.expand_calls: list[dict] = []

    def resolve(self, track):
        return self._origin

    def expand(self, origin, *, style_period):
        self.expand_calls.append({"style_period": style_period})
        return list(self._edges)

    def to_lead(self, edge, raw):
        return raw


def _origin(**kw) -> Origin:
    base = dict(artist="Jasmín", band_id=637178087, title="Bite The Hand",
                tralbum_id=4024735967, tralbum_type="a", label="Hessle Audio",
                label_id=2788766970, tag="bass", year=2025,
                source_url="https://x.bandcamp.com/album/y", resolution="release",
                discography=[])
    base.update(kw)
    return Origin(**base)


def test_artist_absent_from_bandcamp_gives_no_origin_and_no_leads(db):
    source = _FakeSource(origin=None)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.origin is None
    assert result.leads == []
    assert result.edges["same_artist"] == EdgeReport(count=None, absent_reason="no_band")
    assert result.edges["same_label"].absent_reason == "no_band"
    assert result.edges["same_period_style"].absent_reason == "no_band"
    # Nessuna espansione: senza band non c'è nulla da espandere.
    assert source.expand_calls == []


def test_leads_carry_one_reason_per_edge_that_reached_them(db):
    lead = _lead()
    source = _FakeSource(origin=_origin(), edges=[("same_artist", lead),
                                                  ("same_label", lead)])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 1
    codes = sorted(r.code for r in result.leads[0].reasons)
    assert codes == ["same_artist", "same_label"]


def test_edge_counts_report_leads_produced_after_dedup(db):
    # Artisti DIVERSI di proposito: con tre lead dello stesso artista il tetto
    # `_MAX_PER_ARTIST` (2) ne taglierebbe uno e il test misurerebbe il tetto
    # invece del conteggio degli archi. Il tetto ha il suo test, più sotto.
    source = _FakeSource(origin=_origin(), edges=[
        ("same_artist", _lead(artist="Artista A", title="A")),
        ("same_label", _lead(artist="Artista B", title="B")),
        ("same_label", _lead(artist="Artista C", title="C")),
    ])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_artist"].count == 1
    assert result.edges["same_label"].count == 2
    assert len(result.leads) == 3


def test_style_period_off_is_an_absent_edge_not_a_zero_count(db):
    source = _FakeSource(origin=_origin(), edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_period_style"] == EdgeReport(count=None, absent_reason="off")
    assert source.expand_calls == [{"style_period": False}]


def test_a_label_the_source_cannot_walk_is_absent_not_a_zero_count(db):
    # `label_id` uguale alla band: autoprodotto. L'arco non è percorribile, e dire
    # "0 dischi" affermerebbe di aver guardato.
    source = _FakeSource(origin=_origin(label_id=637178087, label="Jasmín"),
                         edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_label"] == EdgeReport(count=None,
                                                    absent_reason="self_released")


def test_a_missing_label_in_artist_only_is_absent_for_its_own_reason(db):
    source = _FakeSource(origin=_origin(resolution="artist_only", label=None,
                                        label_id=None, title=None, tralbum_id=None),
                         edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_label"].absent_reason == "no_label"


def test_one_artist_cannot_monopolise_the_grid(db):
    # La discografia dell'artista di partenza mangerebbe la griglia senza il tetto
    # che il dig applica già (_MAX_PER_ARTIST).
    edges = [("same_artist", _lead(title=f"Disco {i}")) for i in range(5)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 2
    # L'arco però ha davvero prodotto 5 lead: il tetto taglia la vista, non il conto.
    assert result.edges["same_artist"].count == 5


def test_owned_leads_are_dropped(db):
    owned = _track(id=2, artist="Pearson Sound", title="Which Way Is Up",
                   album="Which Way Is Up")
    source = _FakeSource(origin=_origin(), edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False,
                     library=[owned])
    assert result.leads == []
    assert result.edges["same_artist"].count == 0


from app.services.dig_sources.bandcamp import BandcampSimilar


# Payload catturati dall'API reale il 2026-09-06, ridotti ai campi usati.
DISCOGRAPHY_ITEM = {
    "item_id": 4024735967, "item_type": "album", "band_id": 637178087,
    "title": "Bite The Hand That Feeds You", "artist_name": "Jasmín",
    "band_name": "Jasmín", "art_id": 111, "release_date": "26 Jun 2026 00:00:00 GMT",
}

TRALBUM = {
    "label": "Hessle Audio", "label_id": 2788766970,
    "tags": [
        {"name": "Electronic", "norm_name": "electronic", "isloc": False},
        {"name": "Bristol", "norm_name": "bristol", "isloc": True},
        {"name": "bass", "norm_name": "bass", "isloc": False},
    ],
    "release_date": 1761091200,
    "bandcamp_url": "https://jasminhoek.bandcamp.com/album/bite-the-hand-that-feeds-you",
}


class _FakeClient:
    """Client Bandcamp finto: risposte prefissate, chiamate registrate."""

    def __init__(self, band=None, discographies=None, tralbum=None):
        self.band = band
        self.discographies = discographies or {}
        self._tralbum = tralbum or {}
        self.calls: list[tuple] = []

    def find_band(self, name):
        self.calls.append(("find_band", name))
        return self.band

    def band_discography(self, band_id):
        self.calls.append(("band_discography", band_id))
        return list(self.discographies.get(band_id, []))

    def tralbum(self, *, band_id, tralbum_id, tralbum_type="a"):
        self.calls.append(("tralbum", band_id, tralbum_id, tralbum_type))
        return dict(self._tralbum)


def _resolver(**kw) -> tuple[BandcampSimilar, _FakeClient]:
    client = _FakeClient(
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM]},
        tralbum=TRALBUM,
        **kw,
    )
    return BandcampSimilar(client), client


def test_resolve_matches_the_release_by_album_and_reads_its_details():
    src, client = _resolver()
    # Titolo completo: la discografia elenca release, e il match è esatto per
    # scelta di design (niente prefisso, per non risolvere sulla release sbagliata).
    origin = src.resolve(_track(album="Bite The Hand That Feeds You"))
    assert origin.resolution == "release"
    assert origin.band_id == 637178087
    assert origin.tralbum_id == 4024735967
    assert origin.tralbum_type == "a"   # "album" -> "a", non "album"
    assert origin.label == "Hessle Audio"
    assert origin.label_id == 2788766970
    assert origin.year == 2025          # da release_date epoch
    assert origin.source_url == TRALBUM["bandcamp_url"]


def test_resolve_skips_generic_and_location_tags_when_choosing_the_style_tag():
    src, _ = _resolver()
    assert src.resolve(_track(album="Bite The Hand That Feeds You")).tag == "bass"


def test_resolve_matches_by_title_when_the_album_tag_is_missing():
    src, _ = _resolver()
    origin = src.resolve(_track(album=None, title="Bite The Hand That Feeds You"))
    assert origin.resolution == "release"


def test_unresolved_release_falls_back_to_the_file_tags():
    src, client = _resolver()
    origin = src.resolve(_track(album="Un disco che non esiste", title="Nemmeno questo"))
    assert origin.resolution == "artist_only"
    assert origin.label == "Hessle Audio"   # dal tag del file
    assert origin.tag == "bass"             # da track.genre "Bass", normalizzato
    assert origin.year == 2025              # da track.year
    # Nessun dettaglio release chiesto: non c'è release da dettagliare.
    assert not any(c[0] == "tralbum" for c in client.calls)


def test_a_band_bandcamp_does_not_know_resolves_to_nothing():
    src = BandcampSimilar(_FakeClient(band=None))
    assert src.resolve(_track()) is None


DISCOVER_ITEM_2026 = {
    "item_id": 900001, "item_type": "a", "title": "Vicino nel tempo",
    "item_url": "https://x.bandcamp.com/album/vicino", "band_id": 42,
    "album_artist": "Altro Artista", "band_name": "Una Label",
    "primary_image": {"image_id": 5}, "track_count": 4,
    "featured_track": {"stream_url": "https://t4.bcbits.com/stream/x"},
    "release_date": "2026-01-01 00:00:00 UTC",
}
DISCOVER_ITEM_2010 = {**DISCOVER_ITEM_2026, "item_id": 900002, "title": "Lontano",
                      "release_date": "2010-01-01 00:00:00 UTC"}

LABEL_ITEM = {**DISCOGRAPHY_ITEM, "item_id": 777, "title": "Un disco dell'etichetta",
              "artist_name": "Pearson Sound", "band_name": "Hessle Audio"}


class _FakeClientWithDiscover(_FakeClient):
    def __init__(self, discover_batch=None, **kw):
        super().__init__(**kw)
        self.discover_batch = discover_batch or []

    def discover(self, *, tag, cursor="*", size=500):
        self.calls.append(("discover", tag, cursor, size))
        return list(self.discover_batch), None, len(self.discover_batch)


def test_the_artist_edge_reuses_the_discography_and_excludes_the_origin_release():
    other = {**DISCOGRAPHY_ITEM, "item_id": 555, "title": "Un altro disco"}
    client = _FakeClientWithDiscover(
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM, other], 2788766970: []},
        tralbum=TRALBUM,
    )
    src = BandcampSimilar(client)
    origin = src.resolve(_track(album="Bite The Hand That Feeds You"))
    before = len(client.calls)
    edges = src.expand(origin, style_period=False)
    titles = [raw["title"] for edge, raw in edges if edge == "same_artist"]
    assert titles == ["Un altro disco"]
    # L'arco artista non ricompra la discografia: solo la chiamata dell'etichetta.
    assert [c[0] for c in client.calls[before:]] == ["band_discography"]


def test_the_label_edge_walks_the_label_discography():
    client = _FakeClientWithDiscover(
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM], 2788766970: [LABEL_ITEM]},
        tralbum=TRALBUM,
    )
    src = BandcampSimilar(client)
    edges = src.expand(src.resolve(_track(album="Bite The Hand That Feeds You")),
                       style_period=False)
    assert [raw["title"] for edge, raw in edges if edge == "same_label"] == \
        ["Un disco dell'etichetta"]


def test_a_self_released_origin_has_no_label_edge_and_costs_no_request():
    client = _FakeClientWithDiscover(
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM]},
        tralbum={**TRALBUM, "label_id": 637178087, "label": "Jasmín"},
    )
    src = BandcampSimilar(client)
    origin = src.resolve(_track(album="Bite The Hand That Feeds You"))
    before = len(client.calls)
    edges = src.expand(origin, style_period=False)
    assert [e for e, _ in edges if e == "same_label"] == []
    assert client.calls[before:] == []


def test_the_style_edge_keeps_only_releases_inside_the_period_window():
    client = _FakeClientWithDiscover(
        discover_batch=[DISCOVER_ITEM_2026, DISCOVER_ITEM_2010],
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM], 2788766970: []},
        tralbum=TRALBUM,
    )
    src = BandcampSimilar(client)
    edges = src.expand(src.resolve(_track()), style_period=True)
    # origin.year = 2025, PERIOD_YEARS = 3 -> 2026 dentro, 2010 fuori.
    assert [raw["title"] for edge, raw in edges if edge == "same_period_style"] == \
        ["Vicino nel tempo"]
    assert any(c[0] == "discover" and c[1] == "bass" for c in client.calls)


def test_the_style_edge_costs_no_request_when_switched_off():
    client = _FakeClientWithDiscover(
        discover_batch=[DISCOVER_ITEM_2026],
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM], 2788766970: []},
        tralbum=TRALBUM,
    )
    src = BandcampSimilar(client)
    src.expand(src.resolve(_track()), style_period=False)
    assert not any(c[0] == "discover" for c in client.calls)


def test_each_edge_maps_with_the_shape_its_endpoint_returns():
    src, _ = _resolver()
    from_discography = src.to_lead("same_artist", DISCOGRAPHY_ITEM)
    assert from_discography.artist == "Jasmín"
    assert from_discography.source_id == "637178087:4024735967"
    from_discover = src.to_lead("same_period_style", DISCOVER_ITEM_2026)
    assert from_discover.artist == "Altro Artista"
    assert from_discover.stream_url == "https://t4.bcbits.com/stream/x"
