"""Shazam — identificazione delle tracce dei set DJ (Fase 1).

Un mix (URL SoundCloud/Mixcloud/YouTube) viene scaricato e le sue tracce identificate
via fingerprinting (services/mix_identify). Le tracce identificate (DjSetTrack) NON
entrano in libreria: restano legate al DjSet e serviranno come corpus per i
suggerimenti per co-occorrenza (Fase 2). L'analisi e' un job in background con polling.
"""

import importlib.util
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories import delete_dj_set, get_dj_set, list_dj_sets
from app.schemas import DjSetCreateIn, DjSetOut, DjSetSummaryOut
from app.services import mix_identify_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/shazam", tags=["shazam"])


def _deps_available() -> bool:
    """ffmpeg + yt-dlp + shazamio presenti? Senza non si puo' identificare."""
    import shutil

    return bool(
        shutil.which("ffmpeg")
        and importlib.util.find_spec("yt_dlp")
        and importlib.util.find_spec("shazamio")
    )


@router.get("/status")
def status():
    return {"available": _deps_available()}


@router.post("/identify")
def identify(req: DjSetCreateIn):
    """Avvia l'identificazione di un mix (o riusa un set gia' analizzato)."""
    if not _deps_available():
        raise HTTPException(
            status_code=409,
            detail="Identificazione non disponibile: servono ffmpeg, yt-dlp e shazamio nel backend.",
        )
    return mix_identify_job.start_job(req.url)


@router.get("/identify-status")
def identify_status():
    return mix_identify_job.job_state()


@router.get("/sets", response_model=list[DjSetSummaryOut])
def list_sets(db: Session = Depends(get_db)):
    return list_dj_sets(db)


@router.get("/sets/{dj_set_id}", response_model=DjSetOut)
def get_set(dj_set_id: int, db: Session = Depends(get_db)):
    dj_set = get_dj_set(db, dj_set_id)
    if dj_set is None:
        raise HTTPException(status_code=404, detail="Set non trovato")
    return dj_set


@router.delete("/sets/{dj_set_id}", status_code=204)
def remove_set(dj_set_id: int, db: Session = Depends(get_db)):
    if not delete_dj_set(db, dj_set_id):
        raise HTTPException(status_code=404, detail="Set non trovato")
