"""Configurazione guidata (`/setup`): stato del wizard, rilevamento dei
componenti esterni, installazione di quelli sicuri, verifica delle credenziali.

Router HTTP-only: la logica sta in `services/system_probe.py`,
`services/binary_installer.py` e `services/credential_tests.py`. Nessun
testo user-facing nasce qui — solo chiavi, che il frontend traduce.
"""
import sys

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.services import binary_installer, credential_tests, slskd_daemon, system_probe
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


def _richiedi_slskd_non_in_esecuzione() -> None:
    """`binary_installer` non sa nulla del demone (sarebbe un import
    circolare: `slskd_daemon` importa già `binary_installer` per trovare
    l'eseguibile da lanciare) — la verifica sta quindi qui, nel router che
    già coordina entrambi i servizi, non nell'installer.

    Sostituire il binario mentre il demone lo sta eseguendo lo rende
    irraggiungibile a `stop()`: su Linux l'eseguibile del processo vivo
    legge come cancellato, la prova di proprietà (`owned_pid`, che confronta
    il percorso lanciato con quello vivo) non incrocia più, il pid file
    viene scartato come stantio e il demone resta vivo, non tracciato e non
    più fermabile dall'app — lo stesso orfano di `AlreadyOwned`, stavolta
    causato dall'installazione anziché da un secondo avvio."""
    try:
        pid = slskd_daemon.owned_pid()
    except slskd_daemon.UnsupportedPlatform:
        # Su questa piattaforma Cratory non può comunque avviare/possedere
        # un demone (vedi UnsupportedPlatform in slskd_daemon): nessun
        # rischio di sostituire il binario sotto un processo che non
        # potremmo mai aver lanciato noi.
        return
    if pid is not None:
        raise api_error(409, "slskd_running_cannot_install",
                        "slskd è in esecuzione: fermalo prima di reinstallarlo",
                        pid=pid)


@router.post("/install/{key}", status_code=202)
def install(key: str) -> dict:
    if key == "slskd":
        _richiedi_slskd_non_in_esecuzione()
    try:
        return binary_installer.start(key)
    except binary_installer.UnknownComponent as exc:
        raise api_error(400, "unknown_component", f"componente sconosciuto: {key}",
                        component=key) from exc
    except binary_installer.AlreadyRunning as exc:
        raise api_error(409, "install_already_running",
                        "un'installazione è già in corso") from exc


@router.get("/install/status")
def install_status() -> dict:
    return binary_installer.status()


@router.post("/test/{service}")
def test_credential(service: str) -> dict:
    """Prova reale della credenziale. slskd non è qui: il suo stato vivo lo dà
    già `GET /api/slskd/status`."""
    try:
        return credential_tests.check(service)
    except KeyError as exc:
        raise api_error(400, "unknown_service", f"servizio sconosciuto: {service}",
                        service=service) from exc
