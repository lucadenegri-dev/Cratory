"""GET /api/pipeline: snapshot unico per la striscia di orientamento in dashboard."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import PipelineOut
from app.services.pipeline import pipeline_snapshot

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.get("", response_model=PipelineOut)
def get_pipeline(db: Session = Depends(get_db)):
    return pipeline_snapshot(db)
