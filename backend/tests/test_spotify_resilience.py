from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.integrations.spotify import SpotifyError, SpotifyWebClient
from app.models import SpotifyToken


class _FailingHttp:
    def request(self, *_, **__):
        raise httpx.ConnectError("network blocked")


def test_spotify_transport_error_is_wrapped(db, monkeypatch):
    client = SpotifyWebClient(db)
    client.http = _FailingHttp()
    monkeypatch.setattr(client, "_access_token", lambda *, user: "token")

    with pytest.raises(SpotifyError, match="Spotify non raggiungibile"):
        client._call("GET", "/me/playlists", user=True)


def test_spotify_401_preserves_refresh_token(db, monkeypatch):
    token = SpotifyToken(
        kind="user", access_token="stale-token", refresh_token="refresh-abc",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(token)
    db.commit()

    client = SpotifyWebClient(db)

    class _FakeResp:
        def __init__(self, status_code, json_body=None, text=""):
            self.status_code = status_code
            self._json = json_body or {}
            self.text = text
            self.headers = {}

        def json(self):
            return self._json

    calls = {"n": 0}

    class _FakeHttp:
        def request(self, *_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return _FakeResp(401, text="expired")
            return _FakeResp(200, {"ok": True})

    client.http = _FakeHttp()
    refreshed = {}

    def fake_token_request(data):
        refreshed.update(data)
        return {"access_token": "fresh-token", "expires_in": 3600}

    monkeypatch.setattr(client, "_token_request", fake_token_request)

    result = client._call("GET", "/me", user=True)

    assert result == {"ok": True}
    # Il refresh_token originale e' stato usato: nessun re-login forzato.
    assert refreshed == {"grant_type": "refresh_token", "refresh_token": "refresh-abc"}
