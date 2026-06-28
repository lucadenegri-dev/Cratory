"""Motore Undo: inverte l'undo_journal di una run in ordine inverso."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import fsops, tagio
from app.models import Plan, UndoJournal
from app.schemas import UndoResult


def undo_run(db: Session, plan: Plan) -> UndoResult:
    rows = db.scalars(
        select(UndoJournal).where(UndoJournal.run_id == plan.id,
                                  UndoJournal.reversed.is_(False))
        .order_by(UndoJournal.op_seq.desc())
    ).all()
    reversed_ops = 0
    try:
        for r in rows:
            if r.kind == "RETAG":
                tagio.write_tags(r.from_path, r.prior_tags_json or {})
            elif r.kind in ("RENAME", "MOVE"):
                fsops.safe_move(r.to_path, r.from_path)
            elif r.kind == "DELETE":
                fsops.safe_move(r.quarantine_path, r.from_path)
            r.reversed = True
            db.commit()
            reversed_ops += 1
    except Exception as exc:  # noqa: BLE001
        return UndoResult(run_id=plan.id, reversed_ops=reversed_ops, error=str(exc))
    plan.status = "undone"
    db.commit()
    return UndoResult(run_id=plan.id, reversed_ops=reversed_ops)
