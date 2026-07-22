"""Contratto con l'API REALE di Bandcamp. ESCLUSO dalla suite: tocca la rete.

Non verifica il nostro codice ma la FORMA della risposta di un provider che puo'
cambiare senza preavviso. Si lancia a mano quando il dig Bandcamp smette di funzionare,
per sapere in due secondi se e' colpa nostra o loro:

    python -m pytest tests/test_bandcamp_contract.py -m network -q
"""

import pytest

from app.integrations.bandcamp import BandcampClient

pytestmark = pytest.mark.network


@pytest.fixture()
def client():
    c = BandcampClient()
    yield c
    c.close()


def test_discover_still_returns_results_cursor_and_count(client):
    results, cursor, total = client.discover(tag="techno", size=5)
    assert total > 1000, "la pila di 'techno' non dovrebbe mai essere piccola"
    assert cursor, "senza cursore non si puo' sfogliare in profondita'"
    item = results[0]
    for key in ("item_id", "title", "band_name", "item_url", "primary_image",
                "release_date", "track_count", "featured_track"):
        assert key in item, f"campo sparito dalla risposta discover: {key}"
    assert "stream_url" in item["featured_track"]


def test_an_unknown_tag_is_still_an_empty_pile(client):
    _, _, total = client.discover(tag="zzzznotatag", size=1)
    assert total == 0


def test_label_search_and_discography_still_work(client):
    band = client.find_band("Ostgut Ton")
    assert band and band.get("id")
    items = client.band_discography(int(band["id"]))
    assert items, "l'etichetta non dovrebbe avere discografia vuota"
    for key in ("item_id", "band_id", "title", "artist_name", "art_id", "release_date"):
        assert key in items[0], f"campo sparito dalla discografia: {key}"


def test_tralbum_still_carries_url_tags_and_streams(client):
    band = client.find_band("Ostgut Ton")
    items = client.band_discography(int(band["id"]))
    detail = client.tralbum(band_id=int(band["id"]), tralbum_id=int(items[0]["item_id"]))
    assert detail.get("bandcamp_url")
    assert isinstance(detail.get("tracks"), list) and detail["tracks"]
    assert "mp3-128" in (detail["tracks"][0].get("streaming_url") or {})
