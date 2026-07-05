"""Router SOURCES: gestione delle radici di scan + conteggi. Router sottile."""

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, ScanRoot
from app.schemas import ScanRootCreate, ScanRootRead

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _count(db: Session, root_id: int, status: str) -> int:
    return db.scalar(
        select(func.count()).select_from(AudioFile)
        .where(AudioFile.root_id == root_id, AudioFile.status == status)
    ) or 0


def _to_read(db: Session, root: ScanRoot) -> ScanRootRead:
    return ScanRootRead(
        id=root.id, path=root.path, label=root.label,
        last_scanned_at=root.last_scanned_at,
        file_count=_count(db, root.id, "present"),
        missing_count=_count(db, root.id, "missing"),
    )


@router.get("", response_model=list[ScanRootRead])
def list_sources(db: Session = Depends(get_db)):
    return [_to_read(db, r) for r in db.scalars(select(ScanRoot)).all()]


@router.post("", response_model=ScanRootRead, status_code=201)
def add_source(body: ScanRootCreate, db: Session = Depends(get_db)):
    path = os.path.abspath(os.path.expanduser(body.path))
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Il path non esiste o non è una cartella")
    if db.scalar(select(ScanRoot).where(ScanRoot.path == path)):
        raise HTTPException(status_code=409, detail="Radice già presente")
    root = ScanRoot(path=path, label=body.label)
    db.add(root)
    db.commit()
    db.refresh(root)
    return _to_read(db, root)


@router.delete("/{root_id}", status_code=204)
def delete_source(root_id: int, db: Session = Depends(get_db)):
    root = db.get(ScanRoot, root_id)
    if root is None:
        raise HTTPException(status_code=404, detail="Radice non trovata")
    db.delete(root)
    db.commit()
