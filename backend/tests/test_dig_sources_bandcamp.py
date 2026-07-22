"""La sorgente Bandcamp: normalizzazione dei tag, sfogliata col cursore, mapping."""

import pytest

from app.integrations.bandcamp import BandcampError
from app.services.dig_sources import Pile, Seed
from app.services.dig_sources.bandcamp import BANDCAMP_REACH, BandcampSource, _tag_norm


# Un risultato di `discover_web`, ridotto ai campi che il mapping usa.
# Catturato dall'API reale il 2026-07-22.
DISCOVER_ITEM = {
    "item_id": 503240863,
    "item_type": "a",
    "title": "Dārin",
    "item_url": "https://mutual-rytm.bandcamp.com/album/d-rin?from=discover_page",
    "primary_image": {"image_id": 68920540, "is_art": True},
    "band_id": 2554223401,
    "album_artist": "Phil Berg",
    "band_name": "Mutual Rytm",
    "price": {"amount": 800, "currency": "EUR"},
    "featured_track": {
        "id": 1185648549, "title": "Mephisto", "duration": 298.365,
        "stream_url": "https://t4.bcbits.com/stream/xxx/mp3-128/1185648549?p=0",
    },
    "release_date": "2026-07-17 00:00:00 UTC",
    "track_count": 7,
}


class _FakeBandcamp:
    """Client Bandcamp finto: serve batch prefissate, registra le chiamate."""

    def __init__(self, batches=None, total=434149):
        self.batches = list(batches or [])
        self.total = total
        self.calls: list[dict] = []

    def discover(self, *, tag, cursor="*", size=500):
        self.calls.append({"tag": tag, "cursor": cursor, "size": size})
        if not self.batches:
            return [], None, self.total
        batch = self.batches.pop(0)
        return batch, (f"cur{len(self.calls)}" if self.batches else None), self.total


def _item(n: int) -> dict:
    return {**DISCOVER_ITEM, "item_id": n, "title": f"Release {n}"}


# --- normalizzazione dei tag -------------------------------------------------

def test_tag_norm_lowercases_and_hyphenates():
    assert _tag_norm("Deep House") == "deep-house"
    assert _tag_norm("UK Garage") == "uk-garage"
    assert _tag_norm("IDM") == "idm"
    assert _tag_norm("Italo-Disco") == "italo-disco"


def test_tag_norm_collapses_punctuation_runs():
    # 'Funk / Soul' -> 'funk-soul' (1.630 release). Sostituire solo gli spazi darebbe
    # 'funk-/-soul', che su Bandcamp non esiste: zero risultati.
    assert _tag_norm("Funk / Soul") == "funk-soul"


def test_tag_norm_uses_an_alias_where_the_naive_form_finds_the_wrong_pile():
    # 'drum-n-bass' esiste (9.745) ma il tag vero e' 'drum-and-bass' (37.264):
    # senza alias si scava nella pila sbagliata, non in una pila vuota.
    assert _tag_norm("Drum n Bass") == "drum-and-bass"


def test_tag_norm_of_an_empty_seed_is_empty():
    assert _tag_norm("   ") == ""


# --- probe -------------------------------------------------------------------

def test_probe_measures_the_pile_and_declares_the_reach():
    fake = _FakeBandcamp(total=434149)
    pile = BandcampSource(fake).probe(Seed("genre", "Techno"))
    assert pile.height == 434149
    assert pile.reach == BANDCAMP_REACH
    assert pile.resolution == "tag"
    assert pile.handle == "techno"
    assert fake.calls[0]["size"] == 1      # la sonda deve costare il minimo


def test_probe_of_a_seed_bandcamp_does_not_know_is_an_empty_pile():
    fake = _FakeBandcamp(total=0)
    pile = BandcampSource(fake).probe(Seed("genre", "zzzznotatag"))
    assert pile.height == 0 and pile.resolution is None


def test_probe_of_an_unknown_seed_type_costs_nothing():
    fake = _FakeBandcamp()
    pile = BandcampSource(fake).probe(Seed("playlist", "x"))
    assert (pile.height, pile.reach) == (0, 0)
    assert fake.calls == []


# --- sfogliata col cursore ---------------------------------------------------

def _tag_pile() -> Pile:
    return Pile(height=434149, reach=BANDCAMP_REACH, resolution="tag", handle="techno")


def test_fetch_at_the_surface_takes_the_first_items():
    fake = _FakeBandcamp(batches=[[_item(i) for i in range(500)]])
    got = BandcampSource(fake).fetch(Seed("genre", "Techno"), _tag_pile(), 0, 300)
    assert len(got) == 300
    assert got[0]["item_id"] == 0


def test_fetch_consumes_the_offset_before_collecting():
    # L'offset e' in ITEM: la sfogliata deve scartarne 600 (due batch da 500 meno il
    # resto) e cominciare a raccogliere esattamente da li'.
    fake = _FakeBandcamp(batches=[[_item(i) for i in range(500)],
                                  [_item(i) for i in range(500, 1000)]])
    got = BandcampSource(fake).fetch(Seed("genre", "Techno"), _tag_pile(), 600, 300)
    assert [g["item_id"] for g in got[:3]] == [600, 601, 602]
    assert len(got) == 300


def test_fetch_follows_the_cursor_instead_of_restarting():
    fake = _FakeBandcamp(batches=[[_item(i) for i in range(500)],
                                  [_item(i) for i in range(500, 1000)]])
    BandcampSource(fake).fetch(Seed("genre", "Techno"), _tag_pile(), 600, 300)
    assert fake.calls[0]["cursor"] == "*"
    assert fake.calls[1]["cursor"] == "cur1"


def test_fetch_stops_when_the_pile_runs_out():
    fake = _FakeBandcamp(batches=[[_item(i) for i in range(40)]])
    got = BandcampSource(fake).fetch(Seed("genre", "Techno"), _tag_pile(), 0, 300)
    assert len(got) == 40


def test_an_error_during_the_skip_is_raised_not_swallowed():
    # Degradare qui restituirebbe lead da una profondita' DIVERSA da quella chiesta:
    # la lista sembrerebbe un dig profondo ed e' la cima della pila.
    class _Failing(_FakeBandcamp):
        def discover(self, **kw):
            raise BandcampError("rate limit")

    with pytest.raises(BandcampError):
        BandcampSource(_Failing()).fetch(Seed("genre", "Techno"), _tag_pile(), 600, 300)


def test_an_error_after_the_window_started_degrades_to_what_was_collected():
    class _FailsLater(_FakeBandcamp):
        def discover(self, **kw):
            self.calls.append(kw)
            if len(self.calls) == 1:
                return [_item(i) for i in range(500)], "cur1", self.total
            raise BandcampError("rate limit")

    got = BandcampSource(_FailsLater()).fetch(Seed("genre", "Techno"), _tag_pile(), 400, 300)
    assert 0 < len(got) < 300      # i 100 raccolti prima del guasto, non un errore


# --- mapping -----------------------------------------------------------------

def test_lead_from_discover_maps_the_documented_fields():
    lead = BandcampSource(_FakeBandcamp()).to_lead(DISCOVER_ITEM, Seed("genre", "Techno"))
    assert lead.artist == "Phil Berg"
    # band_name e' l'ETICHETTA quando differisce dall'artista: su Bandcamp
    # l'etichetta e' la band che ospita.
    assert lead.label == "Mutual Rytm"
    assert lead.title == "Dārin"
    assert lead.year == 2026
    assert lead.source == "bandcamp"
    assert lead.source_id == "2554223401:503240863"   # band_id:item_id, serve al dettaglio
    assert lead.source_url == "https://mutual-rytm.bandcamp.com/album/d-rin"
    assert lead.thumb_url == "https://f4.bcbits.com/img/a68920540_9.jpg"
    assert lead.stream_url.startswith("https://t4.bcbits.com/stream/")
    assert lead.styles == []          # i tag stanno solo nel dettaglio release
    assert (lead.have, lead.want) == (0, 0)


def test_a_self_released_album_has_no_label():
    raw = {**DISCOVER_ITEM, "album_artist": "Phil Berg", "band_name": "Phil Berg"}
    lead = BandcampSource(_FakeBandcamp()).to_lead(raw, Seed("genre", "Techno"))
    assert lead.label is None


def test_the_artist_falls_back_to_the_band_when_there_is_no_album_artist():
    raw = {**DISCOVER_ITEM, "album_artist": ""}
    lead = BandcampSource(_FakeBandcamp()).to_lead(raw, Seed("genre", "Techno"))
    assert lead.artist == "Mutual Rytm"


@pytest.mark.parametrize("count,badge", [(1, "Single"), (2, "EP"), (5, "EP"), (6, "Album"), (12, "Album")])
def test_the_format_badge_is_derived_from_the_track_count(count, badge):
    # DERIVATO, non dichiarato: Bandcamp non ha un campo formato. Serve perche' i
    # chip di filtro della griglia esistono gia' e senza badge nasconderebbero tutto.
    raw = {**DISCOVER_ITEM, "track_count": count}
    assert BandcampSource(_FakeBandcamp()).to_lead(raw, Seed("genre", "T")).format_badge == badge


@pytest.mark.parametrize("broken", [
    {"title": ""},
    {"album_artist": "", "band_name": ""},
    {"album_artist": "Various Artists", "band_name": "Various Artists"},
    {"track_count": 0},
    {"featured_track": {}},
])
def test_structurally_broken_items_are_dropped_not_crashed(broken):
    # Il de-noise vero (have/want, formati off-target) su Bandcamp non esiste: restano
    # solo gli scarti strutturali. Un campo mancante scarta il lead, non solleva.
    assert BandcampSource(_FakeBandcamp()).to_lead({**DISCOVER_ITEM, **broken},
                                                   Seed("genre", "T")) is None


# --- seme etichetta ----------------------------------------------------------

# Un item di `band_details`, catturato dall'API reale il 2026-07-22. Forma DIVERSA
# dai risultati di discover: artist_name, nessuno stream, nessun track_count,
# nessun URL, e una data in un altro formato.
DISCOGRAPHY_ITEM = {
    "item_id": 1022287860,
    "item_type": "album",
    "artist_name": "Inox Traxx",
    "band_name": "Ostgut Ton",
    "title": "Love Letter",
    "art_id": 2027095290,
    "release_date": "26 Jun 2026 00:00:00 GMT",
    "is_purchasable": True,
    "band_id": 2920024821,
}


_DEFAULT_BAND = {"id": 2920024821, "name": "Ostgut Ton"}


class _FakeLabelBandcamp(_FakeBandcamp):
    def __init__(self, band=_DEFAULT_BAND, discography=None):
        # NB: il default e' il dict stesso, non None-come-sentinella — altrimenti
        # `band=None` esplicito (il seme morto) collasserebbe sullo stesso default.
        super().__init__()
        self.band = band
        self.discography = discography if discography is not None else [DISCOGRAPHY_ITEM]

    def find_band(self, name):
        self.calls.append({"op": "find_band", "name": name})
        return self.band

    def band_discography(self, band_id):
        self.calls.append({"op": "discography", "band_id": band_id})
        return self.discography


def test_label_probe_resolves_the_band_and_keeps_the_discography():
    fake = _FakeLabelBandcamp(discography=[DISCOGRAPHY_ITEM] * 153)
    pile = BandcampSource(fake).probe(Seed("label", "Ostgut Ton"))
    assert pile.height == 153
    # La pila E' la discografia: non c'e' un fondo oltre cui andare.
    assert pile.reach == 153
    assert pile.resolution == "discography"
    assert len(pile.handle) == 153
    assert [c["op"] for c in fake.calls] == ["find_band", "discography"]


def test_a_label_bandcamp_does_not_host_is_a_dead_seed():
    fake = _FakeLabelBandcamp(band=None)
    pile = BandcampSource(fake).probe(Seed("label", "Etichetta Inesistente"))
    assert (pile.height, pile.reach) == (0, 0)
    assert pile.resolution is None


def test_label_fetch_slices_the_discography_without_any_request():
    fake = _FakeLabelBandcamp()
    items = [{**DISCOGRAPHY_ITEM, "item_id": i} for i in range(100)]
    pile = Pile(height=100, reach=100, resolution="discography", handle=items)
    got = BandcampSource(fake).fetch(Seed("label", "Ostgut Ton"), pile, 0, 300)
    assert len(got) == 100
    assert fake.calls == []      # probe aveva gia' pagato


def test_lead_from_discography_reads_artist_name_not_artist():
    lead = BandcampSource(_FakeLabelBandcamp()).to_lead(
        DISCOGRAPHY_ITEM, Seed("label", "Ostgut Ton"))
    assert lead.artist == "Inox Traxx"
    assert lead.label == "Ostgut Ton"
    assert lead.title == "Love Letter"
    assert lead.source_id == "2920024821:1022287860"
    assert lead.thumb_url == "https://f4.bcbits.com/img/a2027095290_9.jpg"


def test_lead_from_discography_parses_the_other_date_format():
    # '26 Jun 2026 ...' non e' ancorabile all'inizio: l'anno va cercato nella stringa.
    lead = BandcampSource(_FakeLabelBandcamp()).to_lead(
        DISCOGRAPHY_ITEM, Seed("label", "Ostgut Ton"))
    assert lead.year == 2026


def test_lead_from_discography_has_no_stream_badge_or_url():
    # Nessuna delle tre e' visibile in griglia: la card non rende link esterni, e il
    # play ricade sulla risoluzione iTunes che non ha bisogno di un id di sorgente.
    # Il pannello, che apre tralbum_details, ha comunque URL, tag e stream veri.
    lead = BandcampSource(_FakeLabelBandcamp()).to_lead(
        DISCOGRAPHY_ITEM, Seed("label", "Ostgut Ton"))
    assert lead.stream_url is None
    assert lead.format_badge is None
    assert lead.source_url is None


@pytest.mark.parametrize("broken", [{"title": ""}, {"artist_name": ""},
                                    {"artist_name": "Various Artists"}])
def test_broken_discography_items_are_dropped(broken):
    assert BandcampSource(_FakeLabelBandcamp()).to_lead(
        {**DISCOGRAPHY_ITEM, **broken}, Seed("label", "Ostgut Ton")) is None
