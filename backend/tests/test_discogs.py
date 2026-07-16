"""Test integrazione Discogs (nessuna rete: http finto)."""

import httpx
import pytest

from app.integrations.discogs import DiscogsClient, DiscogsError, SORT_DESC, SORT_WANT


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, ""

    def json(self):
        return self._p


def _resp(payload, status=200):
    """Scorciatoia per costruire una `_Resp` dentro un handler di `_FakeHttp`."""
    return _Resp(payload, status)


class _FakeHttp:
    """Http finto: payload statico (uso storico) oppure un handler dinamico
    `handler(url, params=None, **kw) -> _Resp` (una risposta diversa per pagina,
    errori selettivi) quando l'argomento passato e' una funzione."""

    def __init__(self, payload_or_handler, status=200):
        self.calls = []
        if callable(payload_or_handler):
            self._handler = payload_or_handler
            self.payload = None
        else:
            self._handler = None
            self.payload, self.status = payload_or_handler, status

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        if self._handler is not None:
            return self._handler(url, params=params, **kw)
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
    """Contratto cambiato: non piu' auto-paginazione 1->3, il chiamante passa le
    pagine esplicite e il client le concatena nell'ordine richiesto."""
    http = _PagedHttp([
        _Resp(_page(100, pages=3)),
        _Resp(_page(100, pages=3, start=100)),
        _Resp(_page(30, pages=3, start=200)),
    ])
    c = DiscogsClient(token=None, http=http)
    out = c.search_releases(style="Techno", pages=[1, 2, 3])
    assert len(out) == 230
    assert out[0]["id"] == 0 and out[-1]["id"] == 229  # concatenazione in ordine
    assert [p["page"] for (_, p) in http.calls] == [1, 2, 3]


def test_search_releases_no_internal_cap_fetches_all_requested_pages():
    """SEARCH_MAX_PAGES (tetto interno a 3) e' sparito: il client scarica
    esattamente le pagine richieste dal chiamante, anche oltre il vecchio tetto."""
    http = _PagedHttp([_Resp(_page(100, pages=10, start=i * 100)) for i in range(5)])
    c = DiscogsClient(token=None, http=http)
    out = c.search_releases(style="Techno", pages=[1, 2, 3, 4, 5])
    assert len(http.calls) == 5
    assert len(out) == 500


def test_search_releases_short_page_does_not_stop_early():
    """Contratto cambiato: le pagine sono esplicite, quindi una pagina corta non
    interrompe piu' il giro (il chiamante ha gia' deciso quali pagine vuole)."""
    http = _PagedHttp([_Resp(_page(40, pages=1)), _Resp(_page(40, pages=1, start=40))])
    c = DiscogsClient(token=None, http=http)
    out = c.search_releases(label="Warp", pages=[1, 2])
    assert len(out) == 80
    assert len(http.calls) == 2


def test_search_releases_later_page_error_returns_partial():
    """Prima pagina ok, seconda in errore -> best-effort: si ritorna il raccolto,
    nessuna eccezione (solo il fallimento della PRIMA pagina e' un errore duro).
    Ci si ferma alla pagina fallita: la 3 non viene tentata (rate limit)."""
    http = _PagedHttp([
        _Resp(_page(100, pages=3)),
        _Resp({"error": "boom"}, status=500),
        _Resp(_page(50, pages=3, start=200)),
    ])
    c = DiscogsClient(token=None, http=http)
    out = c.search_releases(style="Techno", pages=[1, 2, 3])
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


# --- sonda count_releases + ordinamento per domanda ----------------------------


def test_count_releases_reads_pagination_items():
    calls = []

    def handler(url, params=None, **kw):
        calls.append(params)
        return _resp({"pagination": {"items": 43345, "pages": 100}, "results": []})

    client = DiscogsClient(token=None, http=_FakeHttp(handler))
    assert client.count_releases(style="Acid House") == 43345
    # la sonda deve essere ECONOMICA: una riga, non cento
    assert calls[0]["per_page"] == 1
    assert calls[0]["style"] == "Acid House"


def test_search_releases_fetches_requested_pages_sorted():
    seen_pages = []

    def handler(url, params=None, **kw):
        seen_pages.append(params["page"])
        return _resp({
            "pagination": {"items": 1000, "pages": 10},
            "results": [{"id": params["page"], "title": f"A - P{params['page']}"}],
        })

    client = DiscogsClient(token=None, http=_FakeHttp(handler))
    out = client.search_releases(style="Acid House", pages=[8, 9, 10],
                                 sort=SORT_WANT, sort_order=SORT_DESC)
    assert seen_pages == [8, 9, 10]
    assert [r["id"] for r in out] == [8, 9, 10]


def test_search_releases_sends_sort_params():
    captured = {}

    def handler(url, params=None, **kw):
        captured.update(params)
        return _resp({"pagination": {"items": 10, "pages": 1}, "results": []})

    client = DiscogsClient(token=None, http=_FakeHttp(handler))
    client.search_releases(label="Trax Records", pages=[1], sort=SORT_WANT, sort_order=SORT_DESC)
    assert captured["sort"] == "want"
    assert captured["sort_order"] == "desc"


def test_search_releases_later_page_error_stops_and_keeps_collected():
    calls = []

    def handler(url, params=None, **kw):
        calls.append(params["page"])
        if params["page"] == 2:
            raise httpx.HTTPError("boom")
        return _resp({"pagination": {"items": 500, "pages": 5},
                      "results": [{"id": params["page"], "title": "A - B"}]})

    client = DiscogsClient(token=None, http=_FakeHttp(handler))
    # Pagina successiva in errore: best-effort, tiene cio' che ha e SI FERMA — non salta
    # alla 3. Il fallimento dominante e' il rate limit: se la 2 e' andata in errore la
    # quota e' esaurita e la 3 fallirebbe comunque, quindi non la si tenta nemmeno.
    # Solo la pagina 1 e' stata raccolta -> 1 risultato, e la 3 non viene mai chiamata.
    assert len(client.search_releases(style="x", pages=[1, 2, 3])) == 1
    # la 3 non viene mai tentata (la 2 compare piu' volte: retry di trasporto)
    assert 3 not in calls
