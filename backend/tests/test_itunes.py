import pytest

from app.integrations.itunes import ItunesClient, ItunesError


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, ""

    def json(self):
        return self._p


class _FakeHttp:
    def __init__(self, payload, status=200):
        self.payload, self.status, self.calls = payload, status, []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _Resp(self.payload, self.status)


def test_search_builds_query_and_returns_results():
    http = _FakeHttp({"resultCount": 1, "results": [{"trackName": "X", "previewUrl": "http://a"}]})
    c = ItunesClient(http=http)
    out = c.search("rick astley never gonna", limit=3)
    assert out == [{"trackName": "X", "previewUrl": "http://a"}]
    url, params = http.calls[0]
    assert url.endswith("/search")
    assert params["term"] == "rick astley never gonna"
    assert params["media"] == "music"
    assert params["entity"] == "song"
    assert params["limit"] == 3


def test_search_empty_results():
    http = _FakeHttp({"resultCount": 0, "results": []})
    c = ItunesClient(http=http)
    assert c.search("nothing here") == []


def test_search_http_error_raises_itunes_error():
    http = _FakeHttp({}, status=500)
    c = ItunesClient(http=http)
    with pytest.raises(ItunesError):
        c.search("boom")
