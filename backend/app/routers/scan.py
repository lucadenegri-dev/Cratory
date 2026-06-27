"""Router SCAN: avvio e stato del job di scansione. Router sottile."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import scan_job

router = APIRouter(prefix="/api/scan", tags=["scan"])


class ScanStart(BaseModel):
    root_ids: list[int] | None = None


@router.post("")
def start_scan(body: ScanStart | None = None):
    root_ids = body.root_ids if body else None
    return scan_job.start_job(root_ids)


@router.get("/status")
def scan_status():
    return scan_job.job_state()
