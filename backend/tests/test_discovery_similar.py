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
    # Artisti diversi: qui si misura il conteggio per arco, non il cap (che ha i suoi test sotto).
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


def test_an_origin_without_a_band_has_no_artist_edge_but_walks_the_others(db):
    # Release trovata per "artista + album" ma artista senza pagina Bandcamp:
    # l'arco artista non esiste (dichiarato, non "0 dischi"), gli altri sì.
    source = _FakeSource(origin=_origin(band_id=None, discography=[]),
                         edges=[("same_label", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.origin is not None
    assert result.edges["same_artist"] == EdgeReport(count=None, absent_reason="no_band")
    assert result.edges["same_label"].count == 1
    assert len(result.leads) == 1


def test_the_artist_edge_is_not_capped(db):
    # La sonda della diagnosi, come test permanente. `_MAX_PER_ARTIST` del dig
    # tagliava a 2 un arco che è per costruzione un artista solo: "i simili
    # danno due risultati" veniva da qui, non dall'interruttore stile/periodo.
    edges = [("same_artist", _lead(artist="Jasmín", title=f"Disco {i}")) for i in range(10)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 10
    assert result.edges["same_artist"].count == 10


def test_the_label_edge_is_still_capped(db):
    # Sull'etichetta il monopolio è un rischio vero: un artista prolifico del
    # catalogo non deve mangiarsi la griglia. Il cap resta lì.
    edges = [("same_label", _lead(artist="Prolific", title=f"Disco {i}")) for i in range(5)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 2


def test_edge_counts_describe_the_leads_shown_not_the_candidates(db):
    # Il chip "ETICHETTA 5" con due card a schermo mentiva: contava prima del cap.
    edges = [("same_label", _lead(artist="Prolific", title=f"Disco {i}")) for i in range(5)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_label"].count == len(result.leads) == 2


def test_a_lead_reached_by_artist_and_label_is_exempt(db):
    # La parentela più forte vince: raggiunto anche dall'artista, non si taglia.
    edges = [("same_artist", _lead(artist="Jasmín", title=f"Disco {i}")) for i in range(3)]
    edges += [("same_label", _lead(artist="Jasmín", title=f"Disco {i}")) for i in range(3)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 3
    assert result.edges["same_artist"].count == 3
    assert result.edges["same_label"].count == 3


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

    def __init__(self, band=None, discographies=None, tralbum=None, releases=None):
        self.band = band
        self.discographies = discographies or {}
        self._tralbum = tralbum or {}
        # Titolo cercato -> risultato dell'autocomplete album. Assente = non trovato.
        self.releases = releases or {}
        self.calls: list[tuple] = []

    def find_band(self, name, *, label=False):
        self.calls.append(("find_band", name, label))
        return self.band

    def find_release(self, artist, title):
        self.calls.append(("find_release", artist, title))
        return self.releases.get(title)

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
    # Riconosciuta in discografia: nessuna ricerca release, che costerebbe una richiesta.
    assert not any(c[0] == "find_release" for c in client.calls)


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
    # Ma la ricerca release è stata tentata, per album e poi per titolo.
    assert [c for c in client.calls if c[0] == "find_release"] == [
        ("find_release", "Jasmín", "Un disco che non esiste"),
        ("find_release", "Jasmín", "Nemmeno questo"),
    ]


def test_a_band_bandcamp_does_not_know_and_a_release_it_does_not_have_resolve_to_nothing():
    client = _FakeClient(band=None)
    src = BandcampSimilar(client)
    assert src.resolve(_track()) is None
    # Senza band non c'è discografia da scaricare.
    assert not any(c[0] == "band_discography" for c in client.calls)


# --- fallback: la release cercata per "artista + album" ---------------------------
#
# Misurato il 2026-09-27 su dieci tracce della libreria: la discografia della band
# dell'artista NON elenca le release pubblicate da un'etichetta (stanno sulla pagina
# dell'etichetta), e per quelle l'autocomplete album con "artista album" le trova
# 8 volte su 10. Payload ridotti ai campi usati.

LABEL_HOSTED_RELEASE = {
    "type": "a", "id": 3507238487, "name": "Pacific Spirit", "band_name": "747",
    "band_id": 2433457130,
}

# Il dettaglio di una release ospitata dall'etichetta: `label`/`label_id` vuoti,
# l'etichetta è la band che ospita.
LABEL_HOSTED_TRALBUM = {
    "label": None, "label_id": None,
    "band": {"band_id": 2433457130, "name": "Aquaregia"},
    "tralbum_artist": "747",
    "tags": [{"name": "acid", "norm_name": "acid", "isloc": False}],
    "release_date": 1750000000,
    "bandcamp_url": "https://aquaregiarec.bandcamp.com/album/pacific-spirit",
}


def test_a_release_the_discography_does_not_list_is_searched_by_artist_and_album():
    client = _FakeClient(
        band={"id": 111, "name": "747"},
        discographies={111: [{**DISCOGRAPHY_ITEM, "band_id": 111, "title": "Altro"}]},
        tralbum=LABEL_HOSTED_TRALBUM,
        releases={"Pacific Spirit": LABEL_HOSTED_RELEASE},
    )
    origin = BandcampSimilar(client).resolve(
        _track(artist="747", title="Second Narrows", album="Pacific Spirit"))
    assert origin.resolution == "release"
    assert origin.title == "Pacific Spirit"
    assert origin.tralbum_id == 3507238487
    assert origin.tralbum_type == "a"
    # La band resta quella dell'artista: l'arco artista cammina la SUA discografia.
    assert origin.band_id == 111
    assert len(origin.discography) == 1
    # Il dettaglio si chiede alla pagina che ospita, non alla band dell'artista.
    assert ("tralbum", 2433457130, 3507238487, "a") in client.calls
    assert origin.year == 2025
    assert origin.tag == "acid"
    assert origin.source_url == LABEL_HOSTED_TRALBUM["bandcamp_url"]


def test_a_release_hosted_by_another_band_takes_that_band_as_its_label():
    client = _FakeClient(
        band={"id": 111, "name": "747"}, discographies={111: []},
        tralbum=LABEL_HOSTED_TRALBUM, releases={"Pacific Spirit": LABEL_HOSTED_RELEASE},
    )
    origin = BandcampSimilar(client).resolve(_track(artist="747", album="Pacific Spirit"))
    assert origin.label == "Aquaregia"
    assert origin.label_id == 2433457130


def test_a_release_hosted_by_the_artist_keeps_the_label_the_detail_declares():
    # Blawan pubblica "Woke Up Right Handed" sulla propria pagina, con XL come
    # etichetta dichiarata nel dettaglio: l'etichetta è quella, non la pagina.
    client = _FakeClient(
        band={"id": 632918856, "name": "Blawan"}, discographies={632918856: []},
        tralbum={**TRALBUM, "label": "XL Recordings", "label_id": 3802567032,
                 "band": {"band_id": 632918856, "name": "Blawan"}},
        releases={"Woke Up Right Handed": {"type": "a", "id": 1613389736,
                                           "name": "Woke Up Right Handed",
                                           "band_name": "Blawan", "band_id": 632918856}},
    )
    origin = BandcampSimilar(client).resolve(
        _track(artist="Blawan", album="Woke Up Right Handed EP"))
    assert origin.label == "XL Recordings"
    assert origin.label_id == 3802567032


def test_the_release_search_strips_the_format_suffix():
    # "Blawan Woke Up Right Handed EP" dà zero risultati, senza "EP" trova la
    # release. Misurato il 2026-09-27.
    client = _FakeClient(band={"id": 632918856, "name": "Blawan"},
                         discographies={632918856: []})
    BandcampSimilar(client).resolve(_track(artist="Blawan", title="Gosk",
                                           album="Woke Up Right Handed EP"))
    assert ("find_release", "Blawan", "Woke Up Right Handed") in client.calls


def test_a_release_hosted_by_a_page_named_after_the_artist_is_self_released():
    # La pagina che ospita si chiama come l'artista e il dettaglio non dichiara
    # un'etichetta: è autoprodotto, non "etichetta = l'artista stesso".
    client = _FakeClient(
        band={"id": 111, "name": "747"}, discographies={111: []},
        tralbum={**LABEL_HOSTED_TRALBUM, "band": {"band_id": 999, "name": "747"}},
        releases={"Pacific Spirit": LABEL_HOSTED_RELEASE},
    )
    origin = BandcampSimilar(client).resolve(_track(artist="747", album="Pacific Spirit"))
    assert origin.label is None
    assert origin.label_id is None


def test_an_artist_without_a_band_still_resolves_through_the_release():
    # "Ciel, CCL" non ha una band su Bandcamp, ma "Tilda's Goat Stare" sta sulla
    # pagina di naff recordings e la ricerca album la trova.
    client = _FakeClient(
        band=None, tralbum=LABEL_HOSTED_TRALBUM,
        releases={"Pacific Spirit": LABEL_HOSTED_RELEASE},
    )
    origin = BandcampSimilar(client).resolve(_track(artist="747", album="Pacific Spirit"))
    assert origin is not None
    assert origin.resolution == "release"
    assert origin.band_id is None
    assert origin.discography == []
    assert origin.label_id == 2433457130
    assert not any(c[0] == "band_discography" for c in client.calls)


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


def test_the_label_edge_walks_the_hosting_label_when_the_artist_has_no_band():
    client = _FakeClientWithDiscover(
        band=None, tralbum=LABEL_HOSTED_TRALBUM,
        discographies={2433457130: [LABEL_ITEM]},
        releases={"Pacific Spirit": LABEL_HOSTED_RELEASE},
    )
    src = BandcampSimilar(client)
    origin = src.resolve(_track(artist="747", album="Pacific Spirit"))
    edges = src.expand(origin, style_period=False)
    assert [e for e, _ in edges if e == "same_artist"] == []
    assert [raw["title"] for e, raw in edges if e == "same_label"] == \
        ["Un disco dell'etichetta"]


def test_the_label_edge_by_name_asks_for_a_label_not_any_band():
    # artist_only: l'etichetta viene dal tag del file e si cerca per nome. Deve
    # chiedere un'etichetta, o "NAFF" prenderebbe la band omonima.
    client = _FakeClientWithDiscover(
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [], },
        tralbum=TRALBUM,
    )
    src = BandcampSimilar(client)
    origin = src.resolve(_track(album="Sconosciuto", title="Sconosciuto"))
    assert origin.resolution == "artist_only"
    src.expand(origin, style_period=False)
    assert ("find_band", "Hessle Audio", True) in client.calls


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
    # I due archi di discografia devono passare dal mapper della discografia: la
    # forma discover non ha `artist_name` e uscirebbe `None`.
    for edge in ("same_artist", "same_label"):
        from_discography = src.to_lead(edge, DISCOGRAPHY_ITEM)
        assert from_discography is not None, edge
        assert from_discography.artist == "Jasmín"
        assert from_discography.source_id == "637178087:4024735967"
    from_discover = src.to_lead("same_period_style", DISCOVER_ITEM_2026)
    assert from_discover.artist == "Altro Artista"
    assert from_discover.stream_url == "https://t4.bcbits.com/stream/x"


def test_a_similar_lead_carries_no_seed_let_alone_the_name_of_an_edge():
    # `seed` dice cosa ha cercato chi scava: nei simili non si è cercato niente, e
    # metterci il nome dell'arco lo farebbe uscire dall'API come se fosse un seme.
    src, _ = _resolver()
    for edge, raw in (("same_artist", DISCOGRAPHY_ITEM),
                      ("same_label", DISCOGRAPHY_ITEM),
                      ("same_period_style", DISCOVER_ITEM_2026)):
        assert src.to_lead(edge, raw).seed is None, edge
