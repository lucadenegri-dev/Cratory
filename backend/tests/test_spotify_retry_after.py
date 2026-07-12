"""E5: l'header Retry-After puo' essere secondi O una data HTTP (RFC 7231).
`int()` secco su una data (o spazzatura) crashava la chiamata invece di riprovare."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from app.integrations import spotify as spotify_mod
from app.integrations.spotify import SpotifyWebClient, _retry_after_seconds


def test_retry_after_plain_seconds():
    assert _retry_after_seconds("5") == 5


def test_retry_after_http_date():
    future = datetime.now(timezone.utc) + timedelta(seconds=30)
    wait = _retry_after_seconds(format_datetime(future, usegmt=True))
    assert 25 <= wait <= 31  # tolleranza sull'orologio


def test_retry_after_garbage_falls_back_to_default():
    assert _retry_after_seconds("soon™") == 2


def test_retry_after_missing_falls_back_to_default():
    assert _retry_after_seconds(None) == 2


def test_retry_after_past_http_date_is_not_negative():
    past = datetime.now(timezone.utc) - timedelta(seconds=60)
    assert _retry_after_seconds(format_datetime(past, usegmt=True)) >= 0


def test_429_with_http_date_retries_instead_of_crashing(db, monkeypatch):
    client = SpotifyWebClient(db)
    monkeypatch.setattr(client, "_access_token", lambda *, user: "token")
    monkeypatch.setattr(spotify_mod.time, "sleep", lambda s: None)

    class _FakeResp:
        def __init__(self, status_code, headers=None, json_body=None):
            self.status_code = status_code
            self.headers = headers or {}
            self._json = json_body or {}
            self.text = ""

        def json(self):
            return self._json

    date_header = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=1), usegmt=True)
    calls = {"n": 0}

    class _FakeHttp:
        def request(self, *_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return _FakeResp(429, headers={"Retry-After": date_header})
            return _FakeResp(200, json_body={"ok": True})

    client.http = _FakeHttp()
    assert client._call("GET", "/me", user=True) == {"ok": True}
    assert calls["n"] == 2  # 429 assorbito con retry, nessun ValueError
