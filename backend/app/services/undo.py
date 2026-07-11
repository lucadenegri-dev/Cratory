"""Motore Undo: inverte l'undo_journal di una run in ordine inverso."""

import os

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
                if os.path.exists(r.from_path):
                    tagio.write_tags(r.from_path, r.prior_tags_json or {})
                # else: la mutazione non era atterrata → niente da invertire
            elif r.kind in ("RENAME", "MOVE"):
                if os.path.exists(r.to_path):
                    fsops.safe_move(r.to_path, r.from_path)
                # else: la mutazione non era atterrata → niente da invertire
            elif r.kind == "DELETE":
                if os.path.exists(r.quarantine_path):
                    fsops.safe_move(r.quarantine_path, r.from_path)
            elif r.kind == "COVER":
                if os.path.exists(r.from_path):
                    tagio.remove_cover(r.from_path)
            elif r.kind == "RATING":
                prior = (r.prior_tags_json or {}).get("rating")
                if prior and os.path.exists(r.from_path):
                    tagio.set_rating(r.from_path, prior)
            else:
                raise ValueError(f"kind sconosciuto nell'undo: {r.kind}")  # Fix 3
            r.reversed = True
            db.commit()
            reversed_ops += 1
    except Exception as exc:  # noqa: BLE001
        return UndoResult(run_id=plan.id, reversed_ops=reversed_ops, error=str(exc))
    plan.status = "undone"
    db.commit()
    return UndoResult(run_id=plan.id, reversed_ops=reversed_ops)
