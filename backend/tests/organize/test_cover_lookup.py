from app.organize.integrations import cover_art


class _Caa:
    def __init__(self, thumb):
        self._thumb = thumb
        self.seen = []

    def front_thumb(self, mbid):
        self.seen.append(mbid)
        return self._thumb

    def front_url(self, mbid):
        return f"https://caa/release/{mbid}/front"


class _Discogs:
    def __init__(self, cov):
        self._cov = cov

    def cover(self, *, artist, title):
        return self._cov


def test_caa_used_on_high():
    caa = _Caa(b"CAAJPG")
    res = cover_art.lookup_cover(release_mbids=["R1"], confidence="high",
                                 artist="A", title="T", caa=caa, discogs=_Discogs(None))
    assert res.source == "caa" and res.confidence == "high"
    assert res.thumb_bytes == b"CAAJPG"
    assert res.full_url.endswith("/release/R1/front")


def test_discogs_fallback_on_text():
    caa = _Caa(None)  # non consultato su text comunque
    discogs = _Discogs({"full_url": "http://f.jpg", "thumb_url": "http://t.jpg"})
    res = cover_art.lookup_cover(release_mbids=[], confidence="text",
                                 artist="A", title="T", caa=caa, discogs=discogs,
                                 fetch=lambda url, http=None: b"DGJPG")
    assert res.source == "discogs" and res.confidence == "text"
    assert res.thumb_bytes == b"DGJPG" and res.full_url == "http://f.jpg"


def test_caa_miss_then_discogs_on_high():
    caa = _Caa(None)  # CAA non trova nulla
    discogs = _Discogs({"full_url": "http://f.jpg", "thumb_url": "http://t.jpg"})
    res = cover_art.lookup_cover(release_mbids=["R1"], confidence="high",
                                 artist="A", title="T", caa=caa, discogs=discogs,
                                 fetch=lambda url, http=None: b"DGJPG")
    assert res.source == "discogs"


def test_none_when_nothing_found():
    res = cover_art.lookup_cover(release_mbids=[], confidence="text",
                                 artist="A", title="T", caa=_Caa(None),
                                 discogs=_Discogs(None))
    assert res is None


def test_discogs_download_failure_is_none():
    def _boom(url, http=None):
        raise cover_art.CoverArtError("dead")
    discogs = _Discogs({"full_url": "http://f.jpg", "thumb_url": "http://t.jpg"})
    res = cover_art.lookup_cover(release_mbids=[], confidence="text",
                                 artist="A", title="T", caa=_Caa(None),
                                 discogs=discogs, fetch=_boom)
    assert res is None
