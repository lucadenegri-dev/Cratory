from app.services import text_providers
from tests.conftest import make_audio_file


class _MB:
    def __init__(self, res): self.res = res
    def lookup(self, **kw): return self.res


class _Discogs:
    def __init__(self, res): self.res = res
    def lookup(self, **kw): return self.res


def test_musicbrainz_fills_then_discogs_fills_gaps():
    f = make_audio_file(1, artist="SLV", title="Dreamscapes")
    mb = _MB({"canonical_artist": "SLV", "label": "Drumcode",
              "genre_primary": "techno", "release_date": "2019-05-01"})
    dg = _Discogs({"label": "IGNORED", "genre_primary": "Acid Techno"})
    out = text_providers.lookup(f, mb=mb, discogs=dg)
    assert out["label"] == "Drumcode"        # MB vince, Discogs non sovrascrive
    assert out["genre"] == "Techno"          # normalizzato
    assert out["year"] == 2019
    assert out["artist"] == "SLV"


def test_discogs_fills_when_musicbrainz_missing_label():
    f = make_audio_file(2, artist="A", title="B")
    mb = _MB({"genre_primary": "house"})     # niente label
    dg = _Discogs({"label": "Trax", "genre_primary": "Chicago House"})
    out = text_providers.lookup(f, mb=mb, discogs=dg)
    assert out["label"] == "Trax"
    assert out["genre"] == "House"           # MB aveva già il genere → resta MB


def test_no_data_returns_empty():
    f = make_audio_file(3, artist="A", title="B")
    out = text_providers.lookup(f, mb=_MB(None), discogs=_Discogs(None))
    assert out == {}


def test_musicbrainz_album_flows_through():
    f = make_audio_file(4, artist="SLV", title="Dreamscapes")
    mb = _MB({"canonical_artist": "SLV", "canonical_album": "Dreamscapes EP"})
    out = text_providers.lookup(f, mb=mb, discogs=None)
    assert out["album"] == "Dreamscapes EP"


def test_musicbrainz_garbage_genre_does_not_block_discogs_gap_fill():
    # normalize_genre("   ") -> None: se il genere MB normalizza a None non deve
    # finire in out (garbage) né bloccare Discogs come "già presente".
    f = make_audio_file(5, artist="A", title="B")
    mb = _MB({"canonical_artist": "A", "genre_primary": "   "})
    dg = _Discogs({"genre_primary": "Chicago House"})
    out = text_providers.lookup(f, mb=mb, discogs=dg)
    assert out["genre"] == "Chicago House"
