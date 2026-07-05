"""Servizio fingerprint: selezione possedute, soglia, cache (esiti definitivi), errori ritentabili."""
import pytest

from app.integrations.acoustid import AcoustIDError
from app.models import EnrichmentCache, Track
from app.services import fingerprint


class _FakeAcoustID:
    """Client finto: risultati per path, errore sui path indicati."""

    def __init__(self, results=None, error_paths=()):
        self.calls = []
        self.results = results or {}
        self.error_paths = set(error_paths)

    def identify(self, path):
        self.calls.append(path)
        if path in self.error_paths:
            raise AcoustIDError("fingerprint fallito")
        return self.results.get(path, [])


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    monkeypatch.setattr(fingerprint, "_MIN_INTERVAL", 0)


def _owned(db, tmp_path, name, **kw):
    """Traccia posseduta con un file reale su disco."""
    f = tmp_path / f"{name}.mp3"
    f.write_bytes(b"finto audio")
    t = Track(source_type="local_files", title=name, artist="A",
              has_local_file=True, local_path=str(f), audio_hash=f"hash-{name}", **kw)
    db.add(t)
    db.commit()
    return t


def test_seleziona_solo_possedute_senza_mbid(db, tmp_path):
    t1 = _owned(db, tmp_path, "da-identificare")
    _owned(db, tmp_path, "gia-identificata", mbid="mbid-esistente")
    db.add(Track(source_type="spotify", title="Solo streaming", artist="B"))
    db.commit()

    client = _FakeAcoustID({t1.local_path: [{"mbid": "mbid-nuovo", "score": 0.97}]})
    r = fingerprint.fingerprint_tracks(db, client)

    assert client.calls == [t1.local_path]
    assert r["total"] == 1
    assert r["identified"] == 1
    assert t1.mbid == "mbid-nuovo"


def test_sotto_soglia_non_applica_ma_cachea(db, tmp_path):
    t = _owned(db, tmp_path, "incerta")
    client = _FakeAcoustID({t.local_path: [{"mbid": "mbid-x", "score": 0.4}]})
    r = fingerprint.fingerprint_tracks(db, client)

    assert t.mbid is None
    assert r["below_threshold"] == 1 and r["identified"] == 0
    row = db.query(EnrichmentCache).filter_by(provider="acoustid").one()
    assert row.result_json["candidates"] == [{"mbid": "mbid-x", "score": 0.4}]


def test_not_found_cachato_secondo_run_zero_chiamate(db, tmp_path):
    t = _owned(db, tmp_path, "sconosciuta")
    c1 = _FakeAcoustID()  # lista vuota = non nel DB AcoustID (definitivo)
    r1 = fingerprint.fingerprint_tracks(db, c1)
    assert c1.calls == [t.local_path]
    assert r1["not_found"] == 1

    c2 = _FakeAcoustID()
    r2 = fingerprint.fingerprint_tracks(db, c2)
    assert c2.calls == []  # esito definitivo in cache: zero rete
    assert r2["cache_hits"] == 1 and r2["not_found"] == 1


def test_errore_non_cachato_e_ritentato(db, tmp_path):
    t = _owned(db, tmp_path, "instabile")
    c1 = _FakeAcoustID(error_paths=[t.local_path])
    r1 = fingerprint.fingerprint_tracks(db, c1)
    assert r1["errors"] == 1
    assert db.query(EnrichmentCache).filter_by(provider="acoustid").count() == 0

    c2 = _FakeAcoustID({t.local_path: [{"mbid": "mbid-ok", "score": 0.95}]})
    r2 = fingerprint.fingerprint_tracks(db, c2)
    assert c2.calls == [t.local_path]  # ritentata
    assert t.mbid == "mbid-ok" and r2["identified"] == 1


def test_force_riprocessa_e_bypassa_cache(db, tmp_path):
    t = _owned(db, tmp_path, "riverifica", mbid="mbid-vecchio")
    c = _FakeAcoustID({t.local_path: [{"mbid": "mbid-aggiornato", "score": 0.99}]})
    r = fingerprint.fingerprint_tracks(db, c, force=True)
    assert c.calls == [t.local_path]
    assert t.mbid == "mbid-aggiornato"
    assert r["total"] == 1


def test_file_mancante_contato_senza_chiamate(db, tmp_path):
    t = Track(source_type="local_files", title="Sparita", artist="A",
              has_local_file=True, local_path=str(tmp_path / "non-esiste.mp3"))
    db.add(t)
    db.commit()
    c = _FakeAcoustID()
    r = fingerprint.fingerprint_tracks(db, c)
    assert c.calls == []
    assert r["missing_files"] == 1
    assert db.query(EnrichmentCache).count() == 0


def test_progress_fase_fingerprint(db, tmp_path):
    t = _owned(db, tmp_path, "progresso")
    c = _FakeAcoustID({t.local_path: [{"mbid": "m", "score": 0.9}]})
    seen = []
    fingerprint.fingerprint_tracks(db, c, on_progress=lambda i, tot, ph: seen.append((i, tot, ph)))
    assert seen == [(1, 1, "fingerprint")]
