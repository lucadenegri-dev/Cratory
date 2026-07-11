"""Impostazioni utente persistite in AppState (mono-utente, niente tabella dedicata)."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.app_state import LANGUAGE_KEY, get_language, set_state

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LanguageSetting(BaseModel):
    language: Literal["it", "en"]


@router.get("/language", response_model=LanguageSetting)
def read_language(db: Session = Depends(get_db)):
    return LanguageSetting(language=get_language(db))


@router.put("/language", response_model=LanguageSetting)
def write_language(req: LanguageSetting, db: Session = Depends(get_db)):
    set_state(db, LANGUAGE_KEY, req.language)
    return req
