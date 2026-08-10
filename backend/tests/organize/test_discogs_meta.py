import httpx

from app.organize.integrations.discogs_meta import DiscogsMetaClient


def _client(payload):
    def handler(request):
        return httpx.Response(200, json=payload)
    transport = httpx.MockTransport(handler)
    return DiscogsMetaClient(token="t", http=httpx.Client(transport=transport))


def test_lookup_returns_label_genre_year():
    c = _client({"results": [
        {"title": "SLV - Dreamscapes", "label": ["Drumcode"],
         "style": ["Techno"], "genre": ["Electronic"], "year": "2019"},
    ]})
    out = c.lookup(artist="SLV", title="Dreamscapes")
    assert out["label"] == "Drumcode"
    assert out["genre_primary"] == "Techno"   # style batte genre (più specifico)
    assert out["release_date"] == "2019"


def test_lookup_empty_results_returns_none():
    c = _client({"results": []})
    assert c.lookup(artist="X", title="Y") is None


def test_lookup_exposes_genre_candidates_styles_first():
    c = _client({"results": [
        {"style": ["Tech House", "Minimal"], "genre": ["Electronic"],
         "label": ["Drumcode"], "year": 2020},
    ]})
    out = c.lookup(artist="A", title="B")
    assert out["genre_primary"] == "Tech House"
    assert out["genre_candidates"] == ["Tech House", "Minimal", "Electronic"]
