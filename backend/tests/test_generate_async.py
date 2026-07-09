"""Job di generazione asincrona: una richiesta nuova mentre un job e' in corso
NON deve essere inghiottita silenziosamente (il bug: avvii con l'AI, torni sul
form, scegli Algoritmo e Genera -> la richiesta veniva scartata e la UI si
agganciava al vecchio job AI: "il motore resta AI")."""

import pytest
from fastapi import HTTPException

from app.routers import sets as sets_router
from app.schemas import SetGenerationRequest


def test_generate_async_rejects_new_request_while_running(monkeypatch):
    # Simula un job AI gia' in corso.
    monkeypatch.setitem(sets_router._gen_state, "status", "running")
    monkeypatch.setitem(sets_router._gen_state, "using_ai", True)

    with pytest.raises(HTTPException) as exc_info:
        sets_router.generate_async(SetGenerationRequest(use_ai=False))
    assert exc_info.value.status_code == 409
    assert "in corso" in exc_info.value.detail
