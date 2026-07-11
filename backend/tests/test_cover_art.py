import httpx

from app.integrations import cover_art


class _FakeResp:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class _FakeHttp:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def get(self, url, params=None):
        self.calls.append(url)
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def test_front_thumb_returns_bytes_on_200():
    http = _FakeHttp(_FakeResp(200, b"\xff\xd8jpgbytes"))
    client = cover_art.CoverArtArchiveClient(http=http)
    assert client.front_thumb("REL-MBID") == b"\xff\xd8jpgbytes"
    assert "release/REL-MBID/front-250" in http.calls[0]


def test_front_thumb_none_on_404():
    http = _FakeHttp(_FakeResp(404))
    client = cover_art.CoverArtArchiveClient(http=http)
    assert client.front_thumb("REL-MBID") is None


def test_front_thumb_none_on_transport_error():
    http = _FakeHttp(httpx.ConnectError("boom"))
    client = cover_art.CoverArtArchiveClient(http=http)
    assert client.front_thumb("REL-MBID") is None


def test_front_url_is_bounded_size():
    # La cover EMBEDDATA usa una dimensione limitata lato CAA (non l'originale
    # full-res, che può sforare il blocco metadati FLAC da 16 MB).
    client = cover_art.CoverArtArchiveClient(http=_FakeHttp(_FakeResp(200)))
    assert client.front_url("REL-MBID").endswith("/release/REL-MBID/front-500")


def test_fetch_image_returns_bytes():
    http = _FakeHttp(_FakeResp(200, b"IMG"))
    assert cover_art.fetch_image("http://x/y.jpg", http=http) == b"IMG"


def test_fetch_image_raises_on_error():
    http = _FakeHttp(_FakeResp(500))
    try:
        cover_art.fetch_image("http://x/y.jpg", http=http)
        assert False, "attesa CoverArtError"
    except cover_art.CoverArtError:
        pass


def test_bounded_cover_url_caps_caa_full():
    # URL CAA full-res → variante 500px (retroattivo sui full_url già salvati).
    assert cover_art.bounded_cover_url(
        "https://coverartarchive.org/release/R1/front"
    ) == "https://coverartarchive.org/release/R1/front-500"


def test_bounded_cover_url_leaves_sized_and_others_untouched():
    assert cover_art.bounded_cover_url(
        "https://coverartarchive.org/release/R1/front-500"
    ) == "https://coverartarchive.org/release/R1/front-500"
    assert cover_art.bounded_cover_url(
        "https://i.discogs.com/abc.jpeg"
    ) == "https://i.discogs.com/abc.jpeg"
