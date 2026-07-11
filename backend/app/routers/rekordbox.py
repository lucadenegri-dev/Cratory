"""Router REKORDBOX: import della collezione XML (BPM/key) e conteggio pending."""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.models import Track
from app.services.rekordbox_import import apply_collection

router = APIRouter(prefix="/api/rekordbox", tags=["rekordbox"])


@router.get("/pending", response_model=dict)
def pending(db: Session = Depends(get_db)):
    count = len(db.scalars(select(Track.id).where(
        Track.has_local_file.is_(True),
        or_(Track.bpm.is_(None), Track.camelot_key.is_(None), Track.camelot_key == ""),
    )).all())
    return {"pending": count}


@router.post("/import", response_model=dict)
def import_collection(file: UploadFile = File(...), overwrite: bool = False,
                      db: Session = Depends(get_db)):
    # Sync `def`: FastAPI la esegue nel threadpool invece che sull'event loop.
    # Un XML grande (parsing) o l'hash audio di fallback (ffmpeg, decine di
    # secondi) bloccherebbero l'intero backend se girassero sull'event loop.
    # ?overwrite=true: la ri-analisi Rekordbox sovrascrive BPM/key esistenti.
    content = file.file.read()
    if not content:
        raise api_error(400, "rekordbox_empty_file", "Empty file.")
    try:
        return apply_collection(db, content, overwrite=overwrite)
    except ValueError as exc:
        raise api_error(400, "rekordbox_import_failed", f"Rekordbox import failed: {exc}",
                         reason=str(exc)) from exc
