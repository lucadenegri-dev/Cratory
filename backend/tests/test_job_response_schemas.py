"""response_model tipati per gli endpoint job che ritornavano dict grezzi.

Copriva anche generate-async/generate-status di `sets.py`: quei due endpoint
sono spariti con il generatore (2026-09-19), e con loro i test e lo snapshot di
`_gen_state`. Qui restano identify/identify-status di `dj_sets.py`, il cui
contratto deve restare wire-identico: verifichiamo le chiavi esatte.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import app


class _FakeThread:
    """Intercetta l'avvio del thread reale: la richiesta HTTP deve solo verificare
    la forma della risposta immediata, non far girare il job per davvero."""

    def __init__(self, target=None, args=(), daemon=None):
        pass

    def start(self):
        pass


# --- POST /api/shazam/identify + GET /api/shazam/identify-status -------------


def test_identify_status_response_shape_idle():
    client = TestClient(app)
    r = client.get("/api/shazam/identify-status")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "status", "phase", "processed", "total", "dj_set_id", "error", "started_at", "finished_at",
    }
    assert body["status"] == "idle"


def test_identify_response_shape_starts_job(monkeypatch):
    from app.services import mix_identify_job as job

    # mix_identify_job usa SessionLocal direttamente (non Depends(get_db)):
    # senza questo monkeypatch start_job() scriverebbe sul DB reale del progetto
    # (backend/data/djassistant.db), non su uno isolato per il test.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(job, "SessionLocal", TestSession)

    monkeypatch.setattr(job.threading, "Thread", lambda *a, **kw: _FakeThread())
    monkeypatch.setattr("app.routers.dj_sets._deps_available", lambda: True)
    client = TestClient(app)
    r = client.post("/api/shazam/identify", json={"url": "https://soundcloud.com/x/mix"})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "status", "phase", "processed", "total", "dj_set_id", "error", "started_at",
        "finished_at", "cached",
    }
    assert body["status"] == "running"
    assert body["cached"] is False


# --- response_model effettivamente cablato (non solo dict che "sembra" giusto) ---
# I test sopra passerebbero anche senza response_model (l'endpoint ritorna gia'
# quelle chiavi): qui verifichiamo che lo schema OpenAPI referenzi il modello
# Pydantic dedicato, cioe' che `response_model=` sia davvero impostato sulla route.


def _response_schema_ref(path: str, method: str) -> str:
    schema = app.openapi()["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
    return schema.get("$ref", "")


def test_identify_response_model_is_wired():
    assert _response_schema_ref("/api/shazam/identify", "post").endswith("MixIdentifyStartOut")


def test_identify_status_response_model_is_wired():
    assert _response_schema_ref("/api/shazam/identify-status", "get").endswith("MixIdentifyStatusOut")
