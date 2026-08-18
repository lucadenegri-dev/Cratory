"""Configurazione guidata (`/setup`): stato del wizard, rilevamento dei
componenti esterni, installazione di quelli sicuri, verifica delle credenziali.

Router HTTP-only: la logica sta in `services/system_probe.py`,
`services/component_installer.py` e `services/credential_tests.py`. Nessun
testo user-facing nasce qui — solo chiavi, che il frontend traduce.
"""
import sys

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.services import component_installer, credential_tests, system_probe
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


@router.get("/probe")
def probe(force: bool = False) -> dict:
    """Stato dei componenti esterni. `force=true` bypassa la cache: lo usa il
    bottone "Ricontrolla" dopo un'installazione."""
    return {"platform": sys.platform, "components": system_probe.probe_all(force=force)}


@router.post("/install/{key}", status_code=202)
def install(key: str) -> dict:
    try:
        return component_installer.start(key)
    except component_installer.UnknownComponent as exc:
        raise api_error(400, "unknown_component", f"componente sconosciuto: {key}",
                        component=key) from exc
    except component_installer.NotAutoInstallable as exc:
        raise api_error(400, "not_auto_installable",
                        f"{key} va installato a mano", component=key) from exc
    except component_installer.AlreadyRunning as exc:
        raise api_error(409, "install_already_running",
                        "un'installazione è già in corso") from exc


@router.get("/install/status")
def install_status() -> dict:
    return component_installer.status()


@router.post("/test/{service}")
def test_credential(service: str) -> dict:
    """Prova reale della credenziale. slskd non è qui: il suo stato vivo lo dà
    già `GET /api/slskd/status`."""
    try:
        return credential_tests.check(service)
    except KeyError as exc:
        raise api_error(400, "unknown_service", f"servizio sconosciuto: {service}",
                        service=service) from exc
