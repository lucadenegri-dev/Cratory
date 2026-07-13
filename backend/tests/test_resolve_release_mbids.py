from types import SimpleNamespace

from app.services import text_providers


class _MB:
    def __init__(self, res):
        self._res = res

    def lookup(self, *, title, artist, isrc=None, mbid=None):
        return self._res


def _file(**kw):
    base = dict(title="T", artist="A", isrc=None, mbid=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_resolve_exposes_release_mbids_and_strong_confidence():
    mb = _MB({"canonical_title": "T", "confidence": 95,
              "release_mbids": ["REL-1", "REL-2"]})
    r = text_providers.resolve(_file(), mb=mb, discogs=None)
    assert r.confidence == "strong"
    assert r.release_mbids == ["REL-1", "REL-2"]
    assert r.fields["title"][0] == "T"


def test_resolve_weak_confidence_when_tags_diverge():
    # match non-esatto i cui canonici divergono dai tag del file -> weak
    mb = _MB({"canonical_title": "Completely Different Song",
              "canonical_artist": "Another Artist",
              "confidence": 70, "release_mbids": ["REL-1"]})
    r = text_providers.resolve(_file(title="T", artist="A"), mb=mb, discogs=None)
    assert r.confidence == "weak"


def test_resolve_none_confidence_without_mb_match():
    r = text_providers.resolve(_file(), mb=_MB(None), discogs=None)
    assert r.confidence is None and r.release_mbids == []


def test_lookup_with_conf_still_returns_fields_only():
    mb = _MB({"canonical_title": "T", "confidence": 95, "release_mbids": ["R"]})
    fields = text_providers.lookup_with_conf(_file(), mb=mb, discogs=None)
    assert fields["title"] == ("T", "strong")
    assert "release_mbids" not in fields
