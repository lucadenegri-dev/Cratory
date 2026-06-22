import httpx
import pytest

from app.integrations.spotify import SpotifyError, SpotifyWebClient


class _FailingHttp:
    def request(self, *_, **__):
        raise httpx.ConnectError("network blocked")


def test_spotify_transport_error_is_wrapped(db, monkeypatch):
    client = SpotifyWebClient(db)
    client.http = _FailingHttp()
    monkeypatch.setattr(client, "_access_token", lambda *, user: "token")

    with pytest.raises(SpotifyError, match="Spotify non raggiungibile"):
        client._call("GET", "/me/playlists", user=True)


def test_search_by_label_builds_query_and_returns_items(db, monkeypatch):
    client = SpotifyWebClient(db)
    captured = {}

    def fake_get(path, *, params=None, **__):
        captured["path"], captured["params"] = path, params
        return {"tracks": {"items": [{"id": "t1", "name": "X"}]}}

    monkeypatch.setattr(client, "_get", fake_get)
    items = client.search_by_label("Warp Records", limit=5)

    assert items == [{"id": "t1", "name": "X"}]
    assert captured["path"] == "/search"
    assert captured["params"]["q"] == 'label:"Warp Records"'
    assert captured["params"]["type"] == "track"
    assert captured["params"]["limit"] == 5

    # dev mode: limit>10 viene clampato a 10 (Spotify rifiuta "Invalid limit")
    client.search_by_label("Warp Records", limit=20)
    assert captured["params"]["limit"] == 10


def test_search_by_label_handles_error_and_empty(db, monkeypatch):
    client = SpotifyWebClient(db)

    def boom(*_, **__):
        raise SpotifyError("403")

    monkeypatch.setattr(client, "_get", boom)
    assert client.search_by_label("Warp") == []   # SpotifyError -> []
    assert client.search_by_label("") == []        # label vuota -> []
