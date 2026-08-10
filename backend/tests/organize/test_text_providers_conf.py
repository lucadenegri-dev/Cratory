from app.organize.services import text_providers
from tests.organize.conftest import make_audio_file


class FakeMB:
    def __init__(self, res):
        self.res = res

    def lookup(self, **kw):
        return self.res


class FakeDiscogs:
    def __init__(self, res):
        self.res = res

    def lookup(self, **kw):
        return self.res


def test_strong_confidence_from_exact_mb_match():
    f = make_audio_file(1, artist="SLV", title="Dreamscapes", mbid="mb-1")
    mb = FakeMB({"canonical_artist": "SLV", "genre_primary": "Tech House",
                 "confidence": 95})
    out = text_providers.lookup_with_conf(f, mb=mb, discogs=None)
    assert out["genre"] == ("Tech House", "strong")
    assert out["artist"] == ("SLV", "strong")


def test_weak_confidence_from_fuzzy_mb_match_without_identity():
    # match fuzzy che torna solo il genere: nessun campo identita' da
    # confrontare -> non verificabile -> weak
    f = make_audio_file(2, artist="SLV", title="Dreamscapes")
    mb = FakeMB({"genre_primary": "House", "confidence": 70})
    out = text_providers.lookup_with_conf(f, mb=mb, discogs=None)
    assert out["genre"] == ("House", "weak")


def test_discogs_gap_fill_is_weak_even_with_strong_mb():
    f = make_audio_file(3, artist="SLV", title="Dreamscapes", mbid="mb-3")
    mb = FakeMB({"canonical_title": "Dreamscapes", "confidence": 95})  # no genre/label
    discogs = FakeDiscogs({"label": "Drumcode", "genre_primary": "Techno"})
    out = text_providers.lookup_with_conf(f, mb=mb, discogs=discogs)
    assert out["title"] == ("Dreamscapes", "strong")
    assert out["label"] == ("Drumcode", "weak")
    assert out["genre"] == ("Techno", "weak")


def test_lookup_still_returns_flat_values():
    f = make_audio_file(4, artist="SLV", title="Dreamscapes", mbid="mb-4")
    mb = FakeMB({"genre_primary": "House", "confidence": 95})
    assert text_providers.lookup(f, mb=mb, discogs=None) == {"genre": "House"}
