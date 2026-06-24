"""Test integrazione Discogs (nessuna rete: http finto)."""

from app.integrations.discogs import DiscogsClient


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


def test_search_releases_builds_query_and_returns_results():
    http = _FakeHttp({"results": [{"id": 1, "title": "A - B"}]})
    c = DiscogsClient(token=None, http=http)
    out = c.search_releases(style="Acid House", per_page=50)
    assert out == [{"id": 1, "title": "A - B"}]
    url, params = http.calls[0]
    assert url.endswith("/database/search")
    assert params["type"] == "release"
    assert params["style"] == "Acid House"
    assert params["per_page"] == 50


def test_search_releases_label_filter_and_no_filters():
    http = _FakeHttp({"results": []})
    c = DiscogsClient(token=None, http=http)
    assert c.search_releases(label="Warp") == []
    assert http.calls[-1][1]["label"] == "Warp"
    # senza alcun filtro non interroga la rete
    http.calls.clear()
    assert c.search_releases() == []
    assert http.calls == []


def test_search_releases_error_returns_empty():
    http = _FakeHttp({"error": "boom"}, status=500)
    c = DiscogsClient(token=None, http=http)
    assert c.search_releases(genre="Electronic") == []


def test_token_sets_auth_header():
    c = DiscogsClient(token="abc")
    assert c.http.headers.get("Authorization") == "Discogs token=abc"
    assert "Cratory" in c.http.headers.get("User-Agent", "")
