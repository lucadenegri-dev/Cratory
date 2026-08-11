"""Router FINGERPRINT: identità acustica AcoustID → AudioFile.mbid."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.organize.db import get_db
from app.organize.integrations import acoustid
from app.organize.services.fingerprint import fingerprint_files

router = APIRouter(prefix="/api/organize/fingerprint", tags=["fingerprint"])


@router.get("/status", response_model=dict)
def status():
    return {"configured": acoustid.acoustid_configured(),
            "fpcalc": acoustid.fpcalc_available()}


@router.post("", response_model=dict)
def run(db: Session = Depends(get_db)):
    if not acoustid.acoustid_configured() or not acoustid.fpcalc_available():
        return {"configured": False, "identified": 0, "below_threshold": 0,
                "not_found": 0, "errors": 0, "total": 0}
    return {"configured": True, **fingerprint_files(db, acoustid.get_acoustid_client())}
