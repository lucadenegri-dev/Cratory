"""Integrazione AcoustID: parsing puro, client con fingerprinter/http finti, retry POST.

Nessuna rete, nessun fpcalc: il fingerprinter e' iniettabile e l'HTTP e' finto,
come per gli altri provider (pattern GetSongBPM/Deezer).
"""
import httpx
import pytest

from app.core import config
from app.integrations.acoustid import (
    AcoustIDClient,
    AcoustIDError,
    acoustid_configured,
    parse_lookup,
)


# --- parse_lookup (puro) -------------------------------------------------------


def test_parse_lookup_ordina_per_score_e_deduplica():
    payload = {"status": "ok", "results": [
        {"id": "r1", "score": 0.71, "recordings": [{"id": "mbid-b"}, {"id": "mbid-c"}]},
        {"id": "r2", "score": 0.98, "recordings": [{"id": "mbid-a"}, {"id": "mbid-b"}]},
    ]}
    out = parse_lookup(payload)
    assert [c["mbid"] for c in out[:2]] == ["mbid-a", "mbid-b"]
    assert out[0]["score"] == 0.98
    # mbid-b compare in entrambi i result: vince lo score piu' alto, niente doppioni
    assert [c["mbid"] for c in out].count("mbid-b") == 1
    assert next(c for c in out if c["mbid"] == "mbid-b")["score"] == 0.98


def test_parse_lookup_payload_vuoto_o_malformato():
    assert parse_lookup({"status": "ok", "results": []}) == []
    assert parse_lookup({"status": "ok"}) == []
    # result senza recordings o senza id: ignorati senza crash
    assert parse_lookup({"status": "ok", "results": [
        {"score": 0.9},
        {"score": 0.9, "recordings": [{}]},
        {"recordings": [{"id": "mbid-x"}]},  # senza score -> 0.0
    ]}) == [{"mbid": "mbid-x", "score": 0.0}]


# --- client (fingerprinter + http finti) ----------------------------------------


class _FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, ""

    def json(self):
        return self._p


class _FakeHttp:
    def __init__(self, payload, status=200):
        self.payload, self.status, self.calls = payload, status, []

    def post(self, url, data=None):
        self.calls.append((url, data))
        return _FakeResp(self.payload, self.status)


def _fp(path):
    return 247, b"FAKE_FINGERPRINT"


def test_identify_parametri_e_parsing():
    http = _FakeHttp({"status": "ok", "results": [
        {"score": 0.95, "recordings": [{"id": "mbid-1"}]},
    ]})
    client = AcoustIDClient("KEY", fingerprinter=_fp, http=http)
    out = client.identify("/x/track.mp3")
    assert out == [{"mbid": "mbid-1", "score": 0.95}]
    url, data = http.calls[0]
    assert "acoustid.org" in url
    assert data["client"] == "KEY"
    assert data["duration"] == 247
    assert data["fingerprint"] == "FAKE_FINGERPRINT"  # bytes -> str
    assert data["meta"] == "recordings"


def test_identify_errore_api_solleva():
    http = _FakeHttp({"status": "error", "error": {"message": "invalid API key"}})
    client = AcoustIDClient("BAD", fingerprinter=_fp, http=http)
    with pytest.raises(AcoustIDError, match="invalid API key"):
        client.identify("/x/track.mp3")


def test_identify_fingerprint_fallito_solleva():
    def boom(path):
        raise RuntimeError("decodifica fallita")

    client = AcoustIDClient("KEY", fingerprinter=boom, http=_FakeHttp({}))
    with pytest.raises(AcoustIDError, match="decodifica"):
        client.identify("/x/rotto.mp3")


def test_identify_ritenta_su_errore_di_trasporto(monkeypatch):
    from app.integrations import _http as http_mod

    monkeypatch.setattr(http_mod.time, "sleep", lambda s: None)

    class _FlakyHttp:
        def __init__(self):
            self.calls = 0

        def post(self, url, data=None):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("reset")
            return _FakeResp({"status": "ok", "results": []})

    http = _FlakyHttp()
    client = AcoustIDClient("KEY", fingerprinter=_fp, http=http)
    assert client.identify("/x/track.mp3") == []
    assert http.calls == 2


# --- configurazione -------------------------------------------------------------


def test_acoustid_configured(monkeypatch):
    monkeypatch.setattr(config.settings, "acoustid_api_key", "", raising=False)
    assert acoustid_configured() is False
    monkeypatch.setattr(config.settings, "acoustid_api_key", "k", raising=False)
    assert acoustid_configured() is True
