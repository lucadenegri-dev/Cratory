"""Versione dell'app e controllo degli aggiornamenti.

Router senza prefisso: `/api/version` e `/api/updates/*` non condividono una
radice, e scrivere i percorsi per intero è più chiaro di due router separati
per un endpoint ciascuno.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.http_errors import api_error
from app.core.version import app_version
from app.services import update_check

router = APIRouter(tags=["updates"])


class Version(BaseModel):
    version: str


@router.get("/api/version", response_model=Version)
def read_version() -> Version:
    return Version(version=app_version())


class UpdateCheck(BaseModel):
    current: str
    latest: str | None = None
    update_available: bool = False
    url: str | None = None
    # Testo scritto su GitHub, non nostro: è l'unica prosa che il backend
    # trasmette, ed è contenuto di terzi (come la coda del log di slskd).
    notes: str | None = None


@router.get("/api/updates/check", response_model=UpdateCheck)
def check_updates() -> UpdateCheck:
    """`NoReleasePublished` va intercettata PRIMA della sua superclasse:
    eredita da `UpdateCheckFailed`, quindi invertendo i due `except` il 404
    perderebbe il suo codice e diventerebbe indistinguibile da un errore
    di rete."""
    try:
        return UpdateCheck(**update_check.check())
    except update_check.NoReleasePublished as exc:
        raise api_error(502, "update_no_release", str(exc)) from exc
    except update_check.UpdateCheckFailed as exc:
        raise api_error(502, "update_check_failed", str(exc), reason=str(exc)) from exc
