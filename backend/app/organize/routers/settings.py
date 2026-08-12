"""Router SETTINGS: template globali. Sottile."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.organize.schemas import LanguageSetting, SettingsRead, SettingsUpdate
from app.organize.services import planning

router = APIRouter(prefix="/api/organize/settings", tags=["settings"])


def _read(db: Session) -> SettingsRead:
    s = planning.get_settings(db)
    return SettingsRead(naming_template=s.naming_template,
                        folder_template=s.folder_template)


@router.get("", response_model=SettingsRead)
def get_settings(db: Session = Depends(get_db)):
    return _read(db)


@router.put("", response_model=SettingsRead)
def put_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    planning.update_settings(db, naming_template=body.naming_template,
                             folder_template=body.folder_template)
    return _read(db)


@router.get("/language", response_model=LanguageSetting)
def get_language_route(db: Session = Depends(get_db)):
    return LanguageSetting(language=planning.get_language(db))


@router.put("/language", response_model=LanguageSetting)
def put_language_route(body: LanguageSetting, db: Session = Depends(get_db)):
    planning.set_language(db, body.language)
    return body
