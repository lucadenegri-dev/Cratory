"""Router etichette discografiche.

- panoramica delle etichette presenti in libreria (aggregati deterministici).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import LabelStatsOut
from app.services.labels import labels_overview

router = APIRouter(prefix="/api/labels", tags=["labels"])


@router.get("", response_model=list[LabelStatsOut])
def list_labels(db: Session = Depends(get_db)):
    return [LabelStatsOut(**row) for row in labels_overview(db)]
