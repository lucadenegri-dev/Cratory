"""Router SCAN: avvio e stato del job di scansione. Router sottile."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.organize.services import apply_job, scan_job
from app.organize.core.http_errors import api_error

router = APIRouter(prefix="/api/organize/scan", tags=["scan"])


class ScanStart(BaseModel):
    root_ids: list[int] | None = None


@router.post("")
def start_scan(body: ScanStart | None = None):
    if apply_job.is_running():
        raise api_error(409, "apply_running", "Apply in progress")
    root_ids = body.root_ids if body else None
    return scan_job.start_job(root_ids)


@router.get("/status")
def scan_status():
    return scan_job.job_state()
