import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import app
from app.routers import downloads as downloads_router
from app.integrations.slskd import SlskdError, SlskdFile

client = TestClient(app)


def _engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return e, sessionmaker(bind=e, expire_on_commit=False)


def _override_db(factory):
    """get_db della app -> sessione sul DB in-memory del test."""
    from app.db import get_db

    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _db


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app.dependency_overrides.clear()


class _Client:
    """slskd finto: registra le query e restituisce file predefiniti."""

    def __init__(self, files):
        self.files = files
        self.queries = []
        self.closed = False

    def search(self, artist, title, **kwargs):
        self.queries.append(f"{artist} {title}".strip())
        return self.files

    def close(self):
        self.closed = True


def test_409_quando_slskd_non_configurato(monkeypatch):
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.post("/api/downloads/search", json={"query": "aphex twin"})
    assert r.status_code == 409


def test_query_letterale_una_sola_ricerca(monkeypatch):
    # La query dell'utente passa tal quale: UNA chiamata, nessuna cascata di varianti.
    fake = _Client([SlskdFile(username="u", filename="Aphex Twin - Xtal.flac", size=1,
                              bitrate=None, length=None, has_free_slot=True, queue_length=0)])
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: fake)
    r = client.post("/api/downloads/search", json={"query": "aphex twin xtal"})
    assert r.status_code == 200
    assert fake.queries == ["aphex twin xtal"]
    assert fake.closed is True
    body = r.json()
    assert body["variants"] == []
    assert body["results"][0]["username"] == "u"
    assert body["results"][0]["score"] is None
    assert body["results"][0]["auto_ok"] is False


def test_con_track_id_arricchisce_senza_escludere(monkeypatch):
    # Nome pessimo E bitrate sotto la soglia auto-pick: nei risultati manuali
    # devono comparire ENTRAMBI (nessun filtro a soglia), ordinati per score.
    from app.models import Track

    _, factory = _engine()
    db = factory()
    t = Track(source_type="manual", artist="Aphex Twin", title="Xtal", duration_seconds=294)
    db.add(t)
    db.commit()
    _override_db(factory)

    files = [
        SlskdFile(username="good", filename="Aphex Twin - Xtal.flac", size=1,
                  bitrate=None, length=294, has_free_slot=True, queue_length=0),
        SlskdFile(username="bad-name", filename="b1 untitled rip.mp3", size=1,
                  bitrate=320, length=None, has_free_slot=True, queue_length=0),
        SlskdFile(username="low-q", filename="Aphex Twin - Xtal.mp3", size=1,
                  bitrate=128, length=294, has_free_slot=True, queue_length=0),
    ]
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _Client(files))
    r = client.post("/api/downloads/search", json={"query": "aphex twin xtal", "track_id": t.id})
    assert r.status_code == 200
    body = r.json()
    users = [f["username"] for f in body["results"]]
    assert set(users) == {"good", "bad-name", "low-q"}      # nessuno escluso
    assert users[0] == "good"                                # score desc
    top = body["results"][0]
    assert top["score"] is not None and top["confidence"] is not None
    assert top["auto_ok"] is True                            # flac nome+durata giusti
    bad = next(f for f in body["results"] if f["username"] == "bad-name")
    assert bad["auto_ok"] is False


def test_con_track_id_include_le_varianti(monkeypatch):
    from app.models import Track
    from app.services.soulseek_select import query_variants

    _, factory = _engine()
    db = factory()
    t = Track(source_type="manual", artist="Marco Faraone, UTO",
              title="Real Freak (Extended Mix)")
    db.add(t)
    db.commit()
    _override_db(factory)

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _Client([]))
    r = client.post("/api/downloads/search", json={"query": "x", "track_id": t.id})
    assert r.status_code == 200
    assert r.json()["variants"] == query_variants("Marco Faraone, UTO",
                                                  "Real Freak (Extended Mix)")


def test_404_track_inesistente(monkeypatch):
    _, factory = _engine()
    _override_db(factory)
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    r = client.post("/api/downloads/search", json={"query": "x", "track_id": 999})
    assert r.status_code == 404


def test_502_su_errore_slskd(monkeypatch):
    class _Boom:
        def search(self, a, t, **k):
            raise SlskdError("daemon irraggiungibile")

        def close(self):
            pass

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _Boom())
    r = client.post("/api/downloads/search", json={"query": "x"})
    assert r.status_code == 502
