"""Router SOURCES: gestione delle radici di scan + conteggi. Router sottile."""

import os

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.organize.core.http_errors import api_error
from app.organize.models import AudioFile, ScanRoot
from app.organize.schemas import ScanRootCreate, ScanRootRead
from app.organize.services import cover_cache, thumbs

router = APIRouter(prefix="/api/organize/sources", tags=["sources"])


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
        raise api_error(400, "source_path_invalid", "Path does not exist or is not a folder")
    if db.scalar(select(ScanRoot).where(ScanRoot.path == path)):
        raise api_error(409, "source_already_present", "Root already present")
    root = ScanRoot(path=path, label=body.label)
    db.add(root)
    db.commit()
    db.refresh(root)
    return _to_read(db, root)


@router.delete("/{root_id}", status_code=204)
def delete_source(root_id: int, db: Session = Depends(get_db)):
    root = db.get(ScanRoot, root_id)
    if root is None:
        raise api_error(404, "source_not_found", "Root not found")
    # id raccolti PRIMA del cascade: dopo la delete i rowid sono liberi e uno
    # scan successivo può riassegnarli, quindi la cache thumbnail va purgata
    # per ognuno o resterebbe a servire la cover del file vecchio.
    file_ids = list(db.scalars(select(AudioFile.id).where(AudioFile.root_id == root_id)))
    db.delete(root)
    db.commit()
    for file_id in file_ids:
        thumbs.drop_thumb(file_id)
        cover_cache.drop_thumb(file_id)
