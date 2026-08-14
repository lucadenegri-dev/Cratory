"""Router SETTINGS: template globali. Sottile."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.organize.schemas import SettingsRead, SettingsUpdate
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
