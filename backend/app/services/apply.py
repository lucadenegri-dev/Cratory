"""Motore Apply: pre-volo (conflitti snapshot + stale) e — nel Task 5 — esecuzione."""

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import tagio
from app.models import AudioFile, DupMember, Issue, Plan, PlanOp, ScanRoot, utcnow
from app.schemas import ApplyResult
from app.services import conflict
from app.services.planner import PlanOpComputed


def _root_path(db: Session, root_id: int) -> str:
    root = db.get(ScanRoot, root_id)
    return root.path if root else ""


def _tag_value(tags, field):
    return getattr(tags, field, None)


def _stale_op(ops, files_by_id) -> int | None:
    for o in ops:
        f = files_by_id.get(o.file_id)
        if f is None or not os.path.exists(f.path):
            return o.seq
        if o.kind in ("RENAME", "MOVE", "DELETE"):
            if o.before_json.get("path") != f.path:
                return o.seq
        elif o.kind == "RETAG":
            tags = tagio.read_tags(f.path)
            for field, old in o.before_json.items():
                if _tag_value(tags, field) != old:
                    return o.seq
    return None


def _inputs(db: Session, plan: Plan):
    ops = db.scalars(select(PlanOp).where(PlanOp.plan_id == plan.id)
                     .order_by(PlanOp.seq)).all()
    files = {f.id: f for f in db.scalars(
        select(AudioFile).where(AudioFile.status == "present",
                                AudioFile.scan_error.is_(None))).all()}
    snapshot = {"naming_template": plan.rules_json["naming_template"],
                "folder_template": plan.rules_json["folder_template"]}
    targets = {int(k): v for k, v in plan.rules_json.get("targets", {}).items()}
    accepted = db.scalars(select(Issue).where(Issue.status == "accepted")).all()
    removals = {m.file_id for m in db.scalars(
        select(DupMember).where(DupMember.action == "remove")).all()}
    return ops, files, snapshot, targets, accepted, removals


def apply_plan(db: Session, plan: Plan, on_progress=None) -> ApplyResult:
    started = utcnow()
    ops, files, snapshot, targets, accepted, removals = _inputs(db, plan)
    op_computed = [PlanOpComputed(o.kind, o.file_id, o.before_json, o.after_json) for o in ops]
    if conflict.check(op_computed, files, accepted, removals, snapshot, targets):
        return ApplyResult(refused=True, reason="conflitti bloccanti",
                           started_at=started, finished_at=utcnow())
    stale = _stale_op(ops, files)
    if stale is not None:
        return ApplyResult(stale=True, failed_op_seq=stale, reason="piano stale",
                           started_at=started, finished_at=utcnow())
    # Task 5 inserisce qui l'esecuzione; per ora ritorna un risultato "nessuna op".
    return ApplyResult(run_id=plan.id, applied_ops=0,
                       started_at=started, finished_at=utcnow())
