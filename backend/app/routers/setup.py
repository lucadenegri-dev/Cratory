"""Configurazione guidata (`/setup`): stato del wizard, rilevamento dei
componenti esterni, installazione di quelli sicuri, verifica delle credenziali.

Router HTTP-only: la logica sta in `services/system_probe.py`,
`services/component_installer.py` e `services/credential_tests.py`. Nessun
testo user-facing nasce qui — solo chiavi, che il frontend traduce.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.app_state import get_state, set_state

router = APIRouter(prefix="/api/setup", tags=["setup"])

SETUP_COMPLETED_KEY = "setup.completed"


class SetupState(BaseModel):
    completed: bool


@router.get("/state", response_model=SetupState)
def read_state(db: Session = Depends(get_db)) -> SetupState:
    return SetupState(completed=get_state(db, SETUP_COMPLETED_KEY) == "1")


@router.put("/state", response_model=SetupState)
def write_state(req: SetupState, db: Session = Depends(get_db)) -> SetupState:
    """Scritto sia al completamento sia allo skip: in entrambi i casi il wizard
    non deve ripresentarsi da solo."""
    set_state(db, SETUP_COMPLETED_KEY, "1" if req.completed else "")
    return SetupState(completed=req.completed)
