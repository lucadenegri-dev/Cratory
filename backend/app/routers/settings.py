"""Router SETTINGS: template globali + target_root per-radice. Sottile."""

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ScanRoot
from app.schemas import RootTargetRead, RootTargetUpdate, SettingsRead, SettingsUpdate
from app.services import planning

router = APIRouter(prefix="/api/settings", tags=["settings"])


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


@router.put("/roots/{root_id}/target", response_model=SettingsRead)
def put_root_target(root_id: int, body: RootTargetUpdate, db: Session = Depends(get_db)):
    if body.target_root is not None and not os.path.isabs(body.target_root):
        raise HTTPException(status_code=400, detail="target_root deve essere un path assoluto")
    if planning.set_root_target(db, root_id, body.target_root) is None:
        raise HTTPException(status_code=404, detail="radice non trovata")
    return _read(db)
