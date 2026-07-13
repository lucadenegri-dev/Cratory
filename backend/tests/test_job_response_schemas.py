"""response_model tipati per gli endpoint job che finora ritornavano dict grezzi:
generate-async/generate-status (sets.py) e identify/identify-status (dj_sets.py).
Il contratto deve restare wire-identico: qui verifichiamo le chiavi esatte."""

import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import app
from app.routers import sets as sets_router

# Snapshot preso all'import (fase di collection, prima che qualunque test giri):
# `sets_router._gen_state` e' un dict globale di modulo non coperto dal reset
# automatico dei job in conftest.py (quello copre solo i 4 job in
# app/services/*_job.py). Alcuni test in test_generate_async.py lo mutano
# direttamente (non via monkeypatch), quindi puo' arrivare "sporco" qui a
# seconda dell'ordine di esecuzione dei file: va ripristinato PRIMA e dopo.
_PRISTINE_GEN_STATE = copy.deepcopy(sets_router._gen_state)


@pytest.fixture(autouse=True)
def _reset_gen_state():
    def _reset():
        sets_router._gen_state.clear()
        sets_router._gen_state.update(copy.deepcopy(_PRISTINE_GEN_STATE))

    _reset()
    yield
    _reset()


class _FakeThread:
    """Intercetta l'avvio del thread reale: la richiesta HTTP deve solo verificare
    la forma della risposta immediata, non far girare la generazione per davvero."""

    def __init__(self, target=None, args=(), daemon=None):
        pass

    def start(self):
        pass


# --- POST /api/sets/generate-async -------------------------------------------


def test_generate_async_response_shape(monkeypatch):
    monkeypatch.setattr(sets_router.threading, "Thread", _FakeThread)
    client = TestClient(app)
    r = client.post("/api/sets/generate-async", json={"use_ai": False})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"status", "phase", "using_ai"}
    assert body == {"status": "running", "phase": None, "using_ai": False}


# --- GET /api/sets/generate-status -------------------------------------------


def test_generate_status_response_shape_idle():
    client = TestClient(app)
    r = client.get("/api/sets/generate-status")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "status", "phase", "using_ai", "setlist_id", "error", "started_at", "finished_at",
    }
    assert body["status"] == "idle"


def test_generate_status_response_shape_done(monkeypatch):
    monkeypatch.setitem(sets_router._gen_state, "status", "done")
    monkeypatch.setitem(sets_router._gen_state, "setlist_id", 42)
    client = TestClient(app)
    r = client.get("/api/sets/generate-status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["setlist_id"] == 42


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


def test_generate_async_response_model_is_wired():
    assert _response_schema_ref("/api/sets/generate-async", "post").endswith("GenerateAsyncStartOut")


def test_generate_status_response_model_is_wired():
    assert _response_schema_ref("/api/sets/generate-status", "get").endswith("GenerateStatusOut")


def test_identify_response_model_is_wired():
    assert _response_schema_ref("/api/shazam/identify", "post").endswith("MixIdentifyStartOut")


def test_identify_status_response_model_is_wired():
    assert _response_schema_ref("/api/shazam/identify-status", "get").endswith("MixIdentifyStatusOut")
