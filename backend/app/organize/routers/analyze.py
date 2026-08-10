"""Router ANALYZE: ricalcola Inspector+Dedup sui dati esistenti (no walk FS)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.organize.db import get_db
from app.organize.services import analysis

router = APIRouter(prefix="/api/analyze", tags=["analyze"])


@router.post("")
def analyze(db: Session = Depends(get_db)):
    return analysis.recompute(db).model_dump(mode="json")
