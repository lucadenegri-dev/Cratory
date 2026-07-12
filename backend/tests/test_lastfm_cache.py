"""Test client Last.fm: User-Agent identificativo e cache in-memory con TTL.

Nessuna rete: http finto con contatore di chiamate, clock iniettabile
(`lastfm._now`) monkeypatchato per simulare lo scadere del TTL.
"""

import pytest

from app.integrations import lastfm
from app.integrations.lastfm import LastFMClient


# --- doppioni HTTP (stessa convenzione di test_discovery.py) ------------------


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.text = payload, status, ""

    def json(self):
        return self._payload


class _FakeHttp:
    """Http finto: risposte consumate in ordine, l'ultima si ripete."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


_PAYLOAD = {"similarartists": {"artist": [
    {"name": "Boards of Canada", "match": "1.0"},
]}}
_EXPECTED = [{"name": "Boards of Canada", "match": 1.0}]


@pytest.fixture(autouse=True)
def _cache_pulita():
    """Cache di modulo: va svuotata prima e dopo ogni test per l'isolamento."""
    lastfm.clear_cache()
    yield
    lastfm.clear_cache()


# --- User-Agent ---------------------------------------------------------------


def test_client_httpx_ha_user_agent_identificativo():
    """Le ToS Last.fm richiedono uno UA identificativo (come Discogs/MusicBrainz)."""
    client = LastFMClient("KEY")
    try:
        assert "cratory" in client.http.headers["user-agent"].lower()
    finally:
        client.http.close()


# --- cache: hit entro il TTL ---------------------------------------------------


def test_seconda_chiamata_identica_non_tocca_la_rete():
    http = _FakeHttp(_FakeResp(_PAYLOAD))
    client = LastFMClient("KEY", http=http)

    first = client.similar_artists("Cache Artist")
    second = client.similar_artists("Cache Artist")

    assert first == second == _EXPECTED
    assert len(http.calls) == 1  # la seconda arriva dalla cache


def test_parametri_diversi_non_condividono_la_cache():
    http = _FakeHttp(_FakeResp(_PAYLOAD))
    client = LastFMClient("KEY", http=http)

    client.similar_artists("Cache Artist")
    client.similar_artists("Cache Artist", limit=5)  # limit diverso -> chiave diversa

    assert len(http.calls) == 2


# --- cache: scadenza TTL -------------------------------------------------------


def test_dopo_il_ttl_si_rifetcha(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(lastfm, "_now", lambda: clock["t"])
    http = _FakeHttp(_FakeResp(_PAYLOAD))
    client = LastFMClient("KEY", http=http)

    client.similar_artists("Cache Artist")
    clock["t"] += lastfm.CACHE_TTL_SECONDS + 1  # oltre la scadenza
    out = client.similar_artists("Cache Artist")

    assert out == _EXPECTED
    assert len(http.calls) == 2  # la voce scaduta forza il refetch


# --- cache: gli errori non si cachano ------------------------------------------


def test_gli_errori_non_finiscono_in_cache():
    http = _FakeHttp(_FakeResp({}, status=500), _FakeResp(_PAYLOAD))
    client = LastFMClient("KEY", http=http)

    first = client.similar_artists("Cache Artist")   # 500 -> LastFMError -> []
    second = client.similar_artists("Cache Artist")  # deve ritentare la rete

    assert first == []
    assert second == _EXPECTED
    assert len(http.calls) == 2
