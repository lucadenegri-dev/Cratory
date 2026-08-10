"""Router PLAN: costruisce e legge il piano draft. Sottile."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.organize.db import get_db
from app.organize.core.http_errors import api_error
from app.organize.schemas import PlanRead
from app.organize.services import planning

router = APIRouter(prefix="/api/plan", tags=["plan"])


@router.post("", response_model=PlanRead)
def post_plan(db: Session = Depends(get_db)):
    return planning.create_plan(db)


@router.get("", response_model=PlanRead)
def get_plan(db: Session = Depends(get_db)):
    plan = planning.load_plan(db)
    if plan is None:
        raise api_error(404, "plan_draft_missing", "No draft plan")
    return plan
