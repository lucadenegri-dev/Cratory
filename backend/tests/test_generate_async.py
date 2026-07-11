"""Job di generazione asincrona: una richiesta nuova mentre un job e' in corso
NON deve essere inghiottita silenziosamente (il bug: avvii con l'AI, torni sul
form, scegli Algoritmo e Genera -> la richiesta veniva scartata e la UI si
agganciava al vecchio job AI: "il motore resta AI")."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.routers import sets as sets_router
from app.schemas import SetGenerationRequest
from app.services.app_state import set_state


def test_generate_async_rejects_new_request_while_running(monkeypatch):
    # Simula un job AI gia' in corso.
    monkeypatch.setitem(sets_router._gen_state, "status", "running")
    monkeypatch.setitem(sets_router._gen_state, "using_ai", True)

    with pytest.raises(HTTPException) as exc_info:
        sets_router.generate_async(SetGenerationRequest(use_ai=False))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "set_generation_in_progress"


class _FakeSetlist:
    id = 1
    generated_by = "algorithm"


def _run_nonai_capturing_phase(monkeypatch, language: str) -> str:
    """Esegue il runner non-AI con la lingua data e cattura la fase mostrata
    nel momento in cui `generate_set` viene invocato (dopo il runner la resetta a None)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    set_state(session, "language", language)
    session.close()

    monkeypatch.setattr(sets_router, "SessionLocal", factory)
    captured = {}

    def _fake_generate_set(db, req):
        captured["phase"] = sets_router._gen_state["phase"]
        return _FakeSetlist()

    monkeypatch.setattr(sets_router, "generate_set", _fake_generate_set)
    sets_router._run_generation(SetGenerationRequest(use_ai=False), use_ai=False)
    return captured["phase"]


def test_nonai_phase_italiano_default(monkeypatch):
    assert _run_nonai_capturing_phase(monkeypatch, "it") == "Costruisco il set"


def test_nonai_phase_inglese(monkeypatch):
    assert _run_nonai_capturing_phase(monkeypatch, "en") == "Building the set"
