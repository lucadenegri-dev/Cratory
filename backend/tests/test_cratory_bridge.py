import httpx
import pytest

from app.services import cratory_bridge

BODY = {"found": True, "match": "isrc", "track_id": 7, "artist": "Rataxes",
        "title": "Acid Face", "genre": "Acid Techno", "genre_secondary": None,
        "label": "Bunker", "year": 2024, "confidence": 100}


def _resp(json_body, url="http://localhost:8000/api/tracks/lookup"):
    return httpx.Response(200, json=json_body, request=httpx.Request("GET", url))


def test_lookup_by_isrc(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(url=url, params=params, timeout=timeout)
        return _resp(BODY)

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    body = cratory_bridge.lookup("http://localhost:8000/", isrc="DEAB12300123")
    assert body["found"] is True and body["genre"] == "Acid Techno"
    assert captured["url"] == "http://localhost:8000/api/tracks/lookup"  # niente //
    assert captured["params"] == {"isrc": "DEAB12300123"}
    assert captured["timeout"] == 3.0


def test_lookup_by_artist_title(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(url=url, params=params, timeout=timeout)
        return _resp(dict(BODY, match="fuzzy", confidence=70))

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    body = cratory_bridge.lookup("http://localhost:8000",
                                 artist="Rataxes", title="Acid Face")
    assert body["match"] == "fuzzy"
    assert captured["params"] == {"artist": "Rataxes", "title": "Acid Face"}


def test_lookup_unreachable_raises(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectError("connessione rifiutata")

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    with pytest.raises(cratory_bridge.CratoryUnreachable):
        cratory_bridge.lookup("http://localhost:8000", isrc="X")


def test_lookup_http_error_raises(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return httpx.Response(500, json={"detail": "boom"},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    with pytest.raises(cratory_bridge.CratoryUnreachable):
        cratory_bridge.lookup("http://localhost:8000", isrc="X")
