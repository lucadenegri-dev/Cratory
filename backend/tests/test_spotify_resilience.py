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
