from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ImportReport
from app.schemas import ImportReportOut
from app.services.import_service import import_rekordbox_xml

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/rekordbox-xml", response_model=ImportReportOut)
async def upload_rekordbox_xml(file: UploadFile, db: Session = Depends(get_db)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File vuoto")
    report = import_rekordbox_xml(db, content, filename=file.filename)
    if not report.stats.get("total_tracks") and report.errors:
        raise HTTPException(status_code=422, detail={"errors": report.errors})
    return report


@router.get("/reports/{report_id}", response_model=ImportReportOut)
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = db.get(ImportReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report non trovato")
    return report
