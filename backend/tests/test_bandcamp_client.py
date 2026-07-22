"""Client Bandcamp su trasporto finto: nessuna rete."""

import httpx
import pytest

from app.integrations.bandcamp import BandcampClient, BandcampError


def _client(handler) -> BandcampClient:
    return BandcampClient(http=httpx.Client(transport=httpx.MockTransport(handler)))


DISCOVER_PAYLOAD = {
    "result_count": 434149,
    "batch_result_count": 1,
    "cursor": "AoMIQM2BBnDXhZHEngMrYTIxNzc4MDQ0NDQ=",
    "results": [{"item_id": 503240863, "title": "Dārin"}],
}


def test_discover_sends_the_documented_body_and_unpacks_the_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json=DISCOVER_PAYLOAD)

    results, cursor, total = _client(handler).discover(tag="techno", cursor="*", size=60)
    assert seen["url"] == "https://bandcamp.com/api/discover/1/discover_web"
    assert seen["body"] == {
        "category_id": 0, "tag_norm_names": ["techno"], "geoname_id": 0,
        "slice": "top", "include_result_types": ["a"], "size": 60, "cursor": "*",
    }
    assert results == DISCOVER_PAYLOAD["results"]
    assert cursor == DISCOVER_PAYLOAD["cursor"]
    assert total == 434149


def test_discover_of_an_unknown_tag_is_an_empty_pile_not_an_error():
    handler = lambda r: httpx.Response(200, json={"result_count": 0, "results": [], "cursor": None})
    results, cursor, total = _client(handler).discover(tag="zzzznotatag")
    assert (results, cursor, total) == ([], None, 0)


def test_http_error_becomes_a_typed_bandcamp_error():
    handler = lambda r: httpx.Response(503, text="upstream down")
    with pytest.raises(BandcampError):
        _client(handler).discover(tag="techno")


def test_rate_limit_says_so():
    handler = lambda r: httpx.Response(429, text="slow down")
    with pytest.raises(BandcampError, match="rate limit"):
        _client(handler).discover(tag="techno")


def test_find_band_returns_the_first_band_result():
    payload = {"auto": {"results": [
        {"type": "t", "id": 1, "name": "una traccia"},
        {"type": "b", "id": 2920024821, "name": "Ostgut Ton",
         "item_url_root": "https://ostgut.bandcamp.com"},
    ]}}
    band = _client(lambda r: httpx.Response(200, json=payload)).find_band("Ostgut Ton")
    assert band["id"] == 2920024821


def test_find_band_of_an_unknown_name_is_none():
    payload = {"auto": {"results": [{"type": "t", "id": 1, "name": "x"}]}}
    assert _client(lambda r: httpx.Response(200, json=payload)).find_band("zzz") is None


def test_a_payload_level_error_is_raised_even_with_http_200():
    # Bandcamp risponde 200 con {"error": true}: senza questo controllo un band_id
    # sbagliato sembrerebbe un'etichetta senza dischi.
    handler = lambda r: httpx.Response(200, json={"error": True, "error_message": "bad id"})
    with pytest.raises(BandcampError, match="bad id"):
        _client(handler).band_discography(1)


def test_band_discography_returns_the_items():
    payload = {"discography": [
        {"item_id": 1022287860, "artist_name": "Inox Traxx", "title": "Love Letter"},
    ]}
    items = _client(lambda r: httpx.Response(200, json=payload)).band_discography(2920024821)
    assert items[0]["artist_name"] == "Inox Traxx"


def test_tralbum_returns_the_detail():
    payload = {"title": "Love Letter", "bandcamp_url": "https://ostgut.bandcamp.com/album/love-letter",
               "tracks": [{"track_num": 1, "title": "Love Letter"}]}
    d = _client(lambda r: httpx.Response(200, json=payload)).tralbum(
        band_id=2920024821, tralbum_id=1022287860)
    assert d["bandcamp_url"].endswith("/album/love-letter")
