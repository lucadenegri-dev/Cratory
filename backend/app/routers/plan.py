"""Router PLAN: costruisce e legge il piano draft. Sottile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import PlanRead
from app.services import planning

router = APIRouter(prefix="/api/plan", tags=["plan"])


@router.post("", response_model=PlanRead)
def post_plan(db: Session = Depends(get_db)):
    return planning.create_plan(db)


@router.get("", response_model=PlanRead)
def get_plan(db: Session = Depends(get_db)):
    plan = planning.load_plan(db)
    if plan is None:
        raise HTTPException(status_code=404, detail="nessun piano draft")
    return plan
