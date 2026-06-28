"""Router APPLY: avvia/segue il job di applicazione. Sottile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Plan
from app.services import apply_job, scan_job

router = APIRouter(prefix="/api/apply", tags=["apply"])


@router.post("")
def start_apply(db: Session = Depends(get_db)):
    if scan_job.is_running():
        raise HTTPException(status_code=409, detail="scan in corso")
    if db.scalar(select(Plan).where(Plan.status == "draft")) is None:
        raise HTTPException(status_code=400, detail="nessun piano draft da applicare")
    return apply_job.start_job()


@router.get("/status")
def apply_status():
    return apply_job.job_state()
