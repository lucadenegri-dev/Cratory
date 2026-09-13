"""HTTP per backup e ripristino. Solo trasporto: le regole stanno in
services/backup.py, qui si mappano le eccezioni a codici stabili."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.services import backup, native_picker
from app.services.app_state import get_state, set_state

router = APIRouter(prefix="/api/backup", tags=["backup"])


class VoceOut(BaseModel):
    nome: str
    byte: int
    presente: bool


class EstimateOut(BaseModel):
    byte: int
    voci: list[VoceOut]
    last_backup_at: str | None
    nome_di_default: str
    picker_disponibile: bool


class BackupIn(BaseModel):
    # Nullo = ripiego senza picker: ~/Downloads/<nome_di_default>.
    path: str | None = None


class BackupOut(BaseModel):
    percorso: str
    byte: int
    creato_il: str


class RestoreIn(BaseModel):
    path: str


class RiepilogoOut(BaseModel):
    creato_il: str | None
    app_version: str | None
    tracce: int
    playlist: int
    membri: list[str]
    ha_credenziali: bool


class ConfirmOut(BaseModel):
    riavvio_necessario: bool


@router.get("/estimate", response_model=EstimateOut)
def estimate(db: Session = Depends(get_db)):
    voci = backup.contenuto()
    return EstimateOut(
        byte=sum(v.byte for v in voci),
        voci=[VoceOut(nome=v.nome, byte=v.byte, presente=v.presente) for v in voci],
        last_backup_at=get_state(db, "last_backup_at"),
        nome_di_default=backup.nome_di_default(),
        picker_disponibile=native_picker.picker_available(),
    )


@router.post("", response_model=BackupOut)
def crea(body: BackupIn, db: Session = Depends(get_db)):
    destinazione = Path(body.path) if body.path else Path.home() / "Downloads" / backup.nome_di_default()
    try:
        esito = backup.crea(destinazione)
    except backup.BackupInCorso:
        raise api_error(409, "backup_in_corso", "A backup is already being written")
    set_state(db, "last_backup_at", esito.creato_il)
    return BackupOut(percorso=esito.percorso, byte=esito.byte, creato_il=esito.creato_il)


def _job_error(exc: backup.JobInCorso):
    return api_error(409, "job_in_corso", f"A job is running: {exc.job}", job=exc.job)


@router.post("/restore/prepare", response_model=RiepilogoOut)
def prepare(body: RestoreIn, db: Session = Depends(get_db)):
    try:
        r = backup.prepara(Path(body.path), db)
    except FileNotFoundError:
        raise api_error(404, "file_non_trovato", "Backup file not found")
    except backup.BackupNonValido as exc:
        raise api_error(400, exc.codice, f"Invalid backup: {exc.codice}", detail=exc.dettaglio)
    except backup.JobInCorso as exc:
        raise _job_error(exc)
    return RiepilogoOut(**r.__dict__)


@router.post("/restore/confirm", response_model=ConfirmOut)
def confirm(db: Session = Depends(get_db)):
    try:
        backup.conferma(db)
    except backup.NienteDaRipristinare:
        raise api_error(409, "niente_da_ripristinare", "No restore has been prepared")
    except backup.JobInCorso as exc:
        raise _job_error(exc)
    return ConfirmOut(riavvio_necessario=True)


@router.delete("/restore", status_code=204)
def annulla():
    backup.annulla()
    return Response(status_code=204)


@router.get("/restore/last")
def last(db: Session = Depends(get_db)) -> dict | None:
    raw = get_state(db, "last_restore")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None
