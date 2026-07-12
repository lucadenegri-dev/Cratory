"""Test integrazione Discogs (nessuna rete: http finto)."""

import pytest

from app.integrations.discogs import DiscogsClient, DiscogsError


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


def test_search_releases_error_raises():
    """Un errore Discogs sulla prima pagina NON degrada a lista vuota: il router
    deve poterlo distinguere da 'zero risultati' e mostrarlo all'utente (502)."""
    http = _FakeHttp({"error": "boom"}, status=500)
    c = DiscogsClient(token=None, http=http)
    with pytest.raises(DiscogsError):
        c.search_releases(genre="Electronic")


def test_search_releases_rate_limit_raises():
    http = _FakeHttp({"message": "rate limited"}, status=429)
    c = DiscogsClient(token=None, http=http)
    with pytest.raises(DiscogsError):
        c.search_releases(style="Acid House")


# --- paginazione limitata di search_releases ----------------------------------


class _PagedHttp:
    """Http finto che risponde con un payload diverso per ogni chiamata."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None):
        # copia dei params: il client puo' riusare/mutare il dict tra le pagine
        self.calls.append((url, dict(params or {})))
        return self.responses[len(self.calls) - 1]


def _page(n_items, *, pages=None, start=0):
    payload = {"results": [
        {"id": start + i, "title": f"A - T{start + i}"} for i in range(n_items)
    ]}
    if pages is not None:
        payload["pagination"] = {"pages": pages}
    return payload


def test_search_releases_paginates_and_concatenates():
    http = _PagedHttp([
        _Resp(_page(100, pages=3)),
        _Resp(_page(100, pages=3, start=100)),
        _Resp(_page(30, pages=3, start=200)),
    ])
    c = DiscogsClient(token=None, http=http)
    out = c.search_releases(style="Techno")
    assert len(out) == 230
    assert out[0]["id"] == 0 and out[-1]["id"] == 229  # concatenazione in ordine
    assert [p["page"] for (_, p) in http.calls] == [1, 2, 3]


def test_search_releases_stops_at_max_pages():
    from app.integrations.discogs import SEARCH_MAX_PAGES

    http = _PagedHttp([_Resp(_page(100, pages=10, start=i * 100)) for i in range(10)])
    c = DiscogsClient(token=None, http=http)
    out = c.search_releases(style="Techno")
    assert SEARCH_MAX_PAGES == 3
    assert len(http.calls) == SEARCH_MAX_PAGES
    assert len(out) == 300


def test_search_releases_short_page_stops_early():
    """Una pagina con meno di per_page risultati e' l'ultima: niente chiamate extra."""
    http = _PagedHttp([_Resp(_page(40, pages=1))])
    c = DiscogsClient(token=None, http=http)
    out = c.search_releases(label="Warp")
    assert len(out) == 40
    assert len(http.calls) == 1


def test_search_releases_later_page_error_returns_partial():
    """Prima pagina ok, seconda in errore -> best-effort: si ritorna il raccolto,
    nessuna eccezione (solo il fallimento della PRIMA pagina e' un errore duro)."""
    http = _PagedHttp([
        _Resp(_page(100, pages=3)),
        _Resp({"error": "boom"}, status=500),
    ])
    c = DiscogsClient(token=None, http=http)
    out = c.search_releases(style="Techno")
    assert len(out) == 100
    assert len(http.calls) == 2


def test_token_sets_auth_header():
    c = DiscogsClient(token="abc")
    assert c.http.headers.get("Authorization") == "Discogs token=abc"
    assert "Cratory" in c.http.headers.get("User-Agent", "")


def test_get_release_returns_payload():
    payload = {"id": 1, "title": "Selected Ambient Works 85-92"}
    http = _FakeHttp(payload)
    c = DiscogsClient(token=None, http=http)
    out = c.get_release(1)
    assert out == payload
    url, params = http.calls[0]
    assert url.endswith("/releases/1")


def test_get_release_error_raises():
    http = _FakeHttp({"error": "boom"}, status=500)
    c = DiscogsClient(token=None, http=http)
    with pytest.raises(DiscogsError):
        c.get_release(1)
