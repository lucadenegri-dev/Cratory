"""Endpoint /api/library/fingerprint: guardia di configurazione, avvio job e polling stato."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_409_senza_configurazione(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "acoustid_api_key", "", raising=False)
    r = client.post("/api/library/fingerprint")
    assert r.status_code == 409
    assert "ACOUSTID_API_KEY" in r.json()["detail"]


def test_avvio_e_status(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.config import settings
    from app.db import Base
    from app.services import fingerprint_job

    # Isola il job dal DB reale di sviluppo (vedi test_library_index_router.py).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(fingerprint_job, "SessionLocal",
                        sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(settings, "acoustid_api_key", "k", raising=False)
    monkeypatch.setattr(fingerprint_job, "fpcalc_available", lambda: True)

    class _NoTracksClient:
        def identify(self, path):  # pragma: no cover - nessuna traccia da processare
            raise AssertionError("nessuna chiamata attesa su DB vuoto")

    monkeypatch.setattr(fingerprint_job, "get_acoustid_client", lambda: _NoTracksClient())
    # niente thread reale nel test: il job gira sincrono
    monkeypatch.setattr(fingerprint_job, "_spawn", lambda fn: fn())

    r = client.post("/api/library/fingerprint")
    assert r.status_code == 202
    s = client.get("/api/library/fingerprint/status").json()
    assert s["status"] == "done"
    assert s["result"]["total"] == 0  # DB vuoto: niente possedute da identificare
