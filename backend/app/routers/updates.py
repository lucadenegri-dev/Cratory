"""Versione dell'app e controllo degli aggiornamenti.

Router senza prefisso: `/api/version` e `/api/updates/*` non condividono una
radice, e scrivere i percorsi per intero è più chiaro di due router separati
per un endpoint ciascuno.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.version import app_version

router = APIRouter(tags=["updates"])


class Version(BaseModel):
    version: str


@router.get("/api/version", response_model=Version)
def read_version() -> Version:
    return Version(version=app_version())
