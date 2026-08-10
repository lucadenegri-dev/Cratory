"""Router FILES (scrittura): modifica manuale dei metadati. Sottile."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.organize.core.http_errors import api_error
from app.organize.db import get_db
from app.organize.models import AudioFile
from app.organize.routers.library import build_file_row
from app.organize.schemas import FileRow, FileTagsUpdate
from app.organize.services import manual_edit

router = APIRouter(prefix="/api", tags=["files"])


@router.post("/files/{file_id}/tags", response_model=FileRow)
def update_file_tags(file_id: int, body: FileTagsUpdate,
                     db: Session = Depends(get_db)):
    file = db.get(AudioFile, file_id)
    if file is None:
        raise api_error(404, "file_not_found", "File not found")
    try:
        manual_edit.edit_tags(db, file, body.model_dump(exclude_unset=True))
    except manual_edit.ManualEditError as exc:
        raise api_error(exc.status, exc.code, exc.message, **exc.params)
    return build_file_row(db, file)
