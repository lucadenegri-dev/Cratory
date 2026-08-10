from app.integrations.discogs_meta import DiscogsMetaClient


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _Http:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url, params=None):
        return self._resp


def test_cover_extracts_urls():
    resp = _Resp({"results": [
        {"cover_image": "http://img/full.jpg", "thumb": "http://img/thumb.jpg"}]})
    client = DiscogsMetaClient(token=None, http=_Http(resp))
    cov = client.cover(artist="Kai Tracid", title="Tracid Theme")
    assert cov == {"full_url": "http://img/full.jpg", "thumb_url": "http://img/thumb.jpg"}


def test_cover_none_when_no_results():
    client = DiscogsMetaClient(token=None, http=_Http(_Resp({"results": []})))
    assert client.cover(artist="X", title="Y") is None


def test_cover_none_when_no_image():
    resp = _Resp({"results": [{"title": "no image here"}]})
    client = DiscogsMetaClient(token=None, http=_Http(resp))
    assert client.cover(artist="X", title="Y") is None
