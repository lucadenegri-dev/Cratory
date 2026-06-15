"""Resilienza dell'enrichment agli errori di rete (es. SSL EOF) e scoping per playlist.

Regressione per l'errore osservato in produzione:
  [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
che prima faceva crashare l'intero job. Nessuna chiamata HTTP reale.
"""

import httpx
import pytest

from app.integrations._http import get_with_retries
from app.integrations.getsongbpm import (
    ChainedFeatureProvider,
    FeatureProviderError,
    GetSongBPMProvider,
)


class _FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, ""

    def json(self):
        return self._p


class _RaisingHttp:
    """Client finto che solleva un errore di trasporto sulle prime `fail_times` GET."""

    def __init__(self, exc, fail_times=None):
        self.exc, self.fail_times, self.calls = exc, fail_times, 0

    def get(self, url, params=None):
        self.calls += 1
        if self.fail_times is None or self.calls <= self.fail_times:
            raise self.exc
        return _FakeResp({"search": []})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Azzera il backoff: i test non devono dormire davvero tra i retry."""
    monkeypatch.setattr("app.integrations._http.time.sleep", lambda *_: None)


# --- get_with_retries --------------------------------------------------------


def test_get_with_retries_raises_provider_error_after_attempts():
    http = _RaisingHttp(httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF"))
    with pytest.raises(FeatureProviderError):
        get_with_retries(http, "https://x", error_cls=FeatureProviderError, retries=2)
    assert http.calls == 3  # primo tentativo + 2 retry


def test_get_with_retries_recovers_on_later_attempt():
    http = _RaisingHttp(httpx.ReadError("connection reset"), fail_times=1)
    resp = get_with_retries(http, "https://x", error_cls=FeatureProviderError, retries=2)
    assert resp.status_code == 200
    assert http.calls == 2  # fallisce una volta, poi riesce


# --- il provider non crasha, la traccia diventa "non trovata" ----------------


def test_getsongbpm_lookup_returns_none_on_ssl_error():
    p = GetSongBPMProvider("KEY", http=_RaisingHttp(
        httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred")
    ))
    assert p.lookup(title="Da Funk", artist="Daft Punk") is None


def test_chain_continues_when_one_provider_has_ssl_error():
    """Un provider che cade per SSL non deve azzerare i dati degli altri."""
    failing = GetSongBPMProvider("KEY", http=_RaisingHttp(httpx.ConnectError("EOF")))

    class _Working:
        name = "working"

        def lookup(self, **_):
            return {"bpm": 120.0, "confidence": 70}

    out = ChainedFeatureProvider([failing, _Working()]).lookup(title="X", artist="Y")
    assert out and out["bpm"] == 120.0


# --- scoping per playlist (auto-enrichment + ri-arricchimento) ---------------


class _ConstProvider:
    name = "const"

    def lookup(self, **_):
        return {"bpm": 128.0, "confidence": 90}


def test_enrich_features_scoped_to_single_playlist(db):
    from app.models import Playlist, Track
    from app.services.feature_enrichment import enrich_features

    pa = Playlist(platform="spotify", name="A")
    pb = Playlist(platform="spotify", name="B")
    db.add_all([pa, pb])
    db.flush()
    for i in range(3):
        db.add(Track(source_type="spotify", playlist_id=pa.id, title=f"A{i}", artist="X"))
    for i in range(2):
        db.add(Track(source_type="spotify", playlist_id=pb.id, title=f"B{i}", artist="Y"))
    db.commit()

    report = enrich_features(db, _ConstProvider(), playlist_id=pa.id)

    assert report["total"] == 3  # solo le tracce della playlist A
    a_tracks = db.query(Track).filter(Track.playlist_id == pa.id).all()
    b_tracks = db.query(Track).filter(Track.playlist_id == pb.id).all()
    assert all(t.bpm == 128.0 for t in a_tracks)
    assert all(t.bpm is None for t in b_tracks)  # playlist B intatta
