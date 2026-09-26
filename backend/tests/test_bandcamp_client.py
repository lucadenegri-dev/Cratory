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


# --- find_band: il nome restituito deve corrispondere a quello cercato ----------
#
# L'autocomplete è approssimativo: per "Music For Nations" restituisce "Music For
# An Alternative Nation", per "PMEDIA" "Red Letter Media". Prendere il primo
# risultato senza guardare il nome farebbe camminare l'arco etichetta sul
# catalogo di un'altra etichetta. Misurato il 2026-09-27.

def _bands(*items):
    return {"auto": {"results": [{"type": "b", **it} for it in items]}}


def test_find_band_rejects_a_fuzzy_neighbour_with_a_different_name():
    payload = _bands({"id": 658797056, "name": "Music For An Alternative Nation"})
    assert _client(lambda r: httpx.Response(200, json=payload)).find_band(
        "Music For Nations") is None


def test_find_band_accepts_the_name_as_a_word_prefix_and_ignores_case_and_punctuation():
    payload = _bands({"id": 959793951, "name": "naff recordings"})
    assert _client(lambda r: httpx.Response(200, json=payload)).find_band(
        "NAFF")["id"] == 959793951
    payload = _bands({"id": 2712813658, "name": "Ak One"})
    assert _client(lambda r: httpx.Response(200, json=payload)).find_band(
        "AK-One")["id"] == 2712813658


def test_find_band_does_not_match_on_a_partial_word():
    # "747" non è un prefisso di parole di "AK-747s": la parola è "747s".
    payload = _bands({"id": 4174645632, "name": "AK-747s"}, {"id": 2505874366, "name": "Being 747"})
    assert _client(lambda r: httpx.Response(200, json=payload)).find_band("747") is None


def test_find_band_for_a_label_prefers_the_result_flagged_as_label():
    payload = _bands(
        {"id": 1352083151, "name": "Naff", "is_label": False},
        {"id": 959793951, "name": "naff recordings", "is_label": True},
        {"id": 2329379424, "name": "NAFF", "is_label": True},
    )
    client = _client(lambda r: httpx.Response(200, json=payload))
    assert client.find_band("NAFF", label=True)["id"] == 959793951
    # Cercando un artista il flag non conta: vince il primo che corrisponde.
    assert client.find_band("NAFF")["id"] == 1352083151


def test_find_band_for_a_label_falls_back_to_a_matching_non_label():
    payload = _bands({"id": 2433457130, "name": "Aquaregia", "is_label": False})
    assert _client(lambda r: httpx.Response(200, json=payload)).find_band(
        "Aquaregia", label=True)["id"] == 2433457130


# --- find_release: "artista album" col filtro album ------------------------------

RELEASE_RESULTS = {"auto": {"results": [
    {"type": "a", "id": 56979295, "name": "Boards of Canada - Inferno",
     "band_name": "Hazbin Hotel/Helluva Boss fan", "band_id": 1349437728},
    {"type": "a", "id": 477965531, "name": "Inferno", "band_name": "Boards of Canada",
     "band_id": 4138854288},
]}}


def test_find_release_sends_the_album_filter_and_checks_artist_and_title():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json=RELEASE_RESULTS)

    found = _client(handler).find_release("Boards of Canada", "Inferno")
    assert seen["body"]["search_text"] == "Boards of Canada Inferno"
    assert seen["body"]["search_filter"] == "a"
    # Il primo risultato è un fan che ha caricato "Boards of Canada - Inferno":
    # il nome band non corrisponde all'artista, si scarta.
    assert found["id"] == 477965531
    assert found["band_id"] == 4138854288


def test_find_release_matches_the_artist_loosely_on_punctuation():
    payload = {"auto": {"results": [
        {"type": "a", "id": 1135524872, "name": "Tilda's Goat Stare",
         "band_name": "Ciel & CCL", "band_id": 959793951},
    ]}}
    found = _client(lambda r: httpx.Response(200, json=payload)).find_release(
        "Ciel, CCL", "Tilda's Goat Stare")
    assert found["id"] == 1135524872


def test_find_release_accepts_a_format_suffix_on_bandcamp_side():
    payload = {"auto": {"results": [
        {"type": "a", "id": 326228031, "name": "Sun Runner EP", "band_name": "AK-One",
         "band_id": 721310265},
    ]}}
    found = _client(lambda r: httpx.Response(200, json=payload)).find_release(
        "AK-One", "Sun Runner")
    assert found["id"] == 326228031


def test_find_release_of_nothing_is_none():
    payload = {"auto": {"results": [{"type": "t", "id": 1, "name": "Inferno", "band_name": "Boards of Canada"}]}}
    assert _client(lambda r: httpx.Response(200, json=payload)).find_release(
        "Boards of Canada", "Inferno") is None
