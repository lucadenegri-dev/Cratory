"""Router SETTINGS: template globali + target_root per-radice. Sottile."""

import os

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.organize.core.http_errors import api_error
from app.organize.models import ScanRoot
from app.organize.schemas import (
    LanguageSetting, RootTargetRead, RootTargetUpdate, SettingsRead, SettingsUpdate,
)
from app.organize.services import planning

router = APIRouter(prefix="/api/organize/settings", tags=["settings"])


def _read(db: Session) -> SettingsRead:
    s = planning.get_settings(db)
    roots = [RootTargetRead(id=r.id, path=r.path, label=r.label, target_root=r.target_root)
             for r in db.scalars(select(ScanRoot)).all()]
    return SettingsRead(naming_template=s.naming_template,
                        folder_template=s.folder_template, roots=roots)


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


@router.put("/roots/{root_id}/target", response_model=SettingsRead)
def put_root_target(root_id: int, body: RootTargetUpdate, db: Session = Depends(get_db)):
    # F3b (Task 1): la destinazione di un Apply è planning.target_root() (unica,
    # da settings.library_root): questo target per-radice non è più letto da
    # nessun piano. L'endpoint resta finché sources/frontend non vengono rimossi
    # (task successivi), quindi scrive ancora la colonna ScanRoot.target_root.
    if body.target_root is not None and not os.path.isabs(body.target_root):
        raise api_error(400, "target_root_not_absolute", "target_root must be an absolute path")
    root = db.get(ScanRoot, root_id)
    if root is None:
        raise api_error(404, "source_not_found", "Root not found")
    root.target_root = body.target_root
    db.commit()
    return _read(db)
