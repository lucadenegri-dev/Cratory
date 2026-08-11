"""Router APPLY: avvia/segue il job di applicazione. Sottile."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.organize.core.http_errors import api_error
from app.organize.models import Plan
from app.organize.services import apply_job, scan_job

router = APIRouter(prefix="/api/organize/apply", tags=["apply"])


@router.post("")
def start_apply(db: Session = Depends(get_db)):
    if scan_job.is_running():
        raise api_error(409, "scan_running", "Scan in progress")
    if db.scalar(select(Plan).where(Plan.status == "draft")) is None:
        raise api_error(400, "plan_draft_missing", "No draft plan to apply")
    return apply_job.start_job()


@router.get("/status")
def apply_status():
    return apply_job.job_state()
