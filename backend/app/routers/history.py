"""Router HISTORY: run applicate/annullate + undo. Sottile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Plan, PlanOp
from app.schemas import HistoryItem, UndoResult
from app.services import undo

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistoryItem])
def list_history(db: Session = Depends(get_db)):
    plans = db.scalars(select(Plan).where(Plan.status.in_(("applied", "undone")))
                       .order_by(Plan.id.desc())).all()
    out = []
    for p in plans:
        n = db.scalar(select(func.count()).select_from(PlanOp).where(PlanOp.plan_id == p.id))
        out.append(HistoryItem(id=p.id, status=p.status, created_at=p.created_at, n_ops=n or 0))
    return out


@router.post("/{plan_id}/undo", response_model=UndoResult)
def undo_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="run non trovata")
    if plan.status != "applied":
        raise HTTPException(status_code=400, detail="la run non è in stato 'applied'")
    return undo.undo_run(db, plan)
