"""Motore Apply: pre-volo (conflitti snapshot + stale) e — nel Task 5 — esecuzione."""

import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import cover_art, fsops, tagio
from app.models import AudioFile, DupMember, Issue, Plan, PlanOp, ScanRoot, UndoJournal, utcnow
from app.schemas import ApplyResult
from app.services import conflict
from app.services.planner import PlanOpComputed

logger = logging.getLogger(__name__)


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
    # Gli op in conflitto (collisione DB o dest già esistente su disco) vengono
    # saltati, non bloccano più l'intero piano: il resto si applica.
    conflicts = conflict.check(op_computed, files, accepted, removals, snapshot, targets,
                               disk_occupied=conflict.disk_occupied(op_computed))
    skip_ids = {c.file_id for c in conflicts if c.kind in ("collision", "outside_root")}
    skipped = [o for o in ops if o.kind in ("RENAME", "MOVE") and o.file_id in skip_ids]
    for o in skipped:
        o.status = "skipped"
    db.commit()
    ops = [o for o in ops if o.status != "skipped"]
    soft_skipped = 0
    stale = _stale_op(ops, files)
    if stale is not None:
        return ApplyResult(stale=True, failed_op_seq=stale, reason="piano stale",
                           skipped_ops=len(skipped) + soft_skipped,
                           started_at=started, finished_at=utcnow())
    retag_ops = [o for o in ops if o.kind == "RETAG"]
    cover_ops = [o for o in ops if o.kind == "COVER"]
    rating_ops = [o for o in ops if o.kind == "RATING"]
    move_ops = [o for o in ops if o.kind in ("RENAME", "MOVE")]
    del_ops = [o for o in ops if o.kind == "DELETE"]
    del_by_path = {o.before_json["path"]: o for o in del_ops}
    done: set = set()
    state = {"seq": 0, "applied": 0}
    current = {"seq": None}   # Fix 4: traccia il seq del PlanOp corrente
    total = len(ops)
    src_dirs: set = set()     # cartelle sorgente svuotabili, pulite a fine run

    def _cleanup_dirs():
        roots = {r.path for r in db.scalars(select(ScanRoot)).all()} | set(targets.values())
        fsops.cleanup_empty_dirs(src_dirs, roots)

    def _journal(kind, file_id, from_path=None, to_path=None, prior_tags=None, quarantine_path=None):
        db.add(UndoJournal(run_id=plan.id, op_seq=state["seq"], kind=kind, file_id=file_id,
                           from_path=from_path, to_path=to_path, prior_tags_json=prior_tags,
                           quarantine_path=quarantine_path))
        db.commit()
        state["seq"] += 1

    def _reopen_cover_issue(file_id):
        # Cover skippata per errore (download/scrittura): rimetti la issue
        # missing_cover a 'open' così torna visibile in ISSUES per una decisione,
        # invece di restare 'accepted' e ritentare in silenzio al prossimo piano.
        iss = db.scalar(select(Issue).where(
            Issue.file_id == file_id, Issue.type == "missing_cover"))
        if iss is not None and iss.status != "open":
            iss.status = "open"
            iss.updated_at = utcnow()

    def _progress():
        state["applied"] += 1
        if on_progress is not None:
            on_progress(state["applied"], total, "applying")

    def _do_delete(o):
        f = files[o.file_id]
        q = fsops.quarantine_path_for(f.path, _root_path(db, f.root_id))
        _journal("DELETE", o.file_id, from_path=f.path, quarantine_path=q)  # journal PRIMA
        fsops.safe_move(f.path, q)                              # poi muta
        src_dirs.add(os.path.dirname(f.path))
        o.status = "applied"
        db.commit()
        done.add(o.file_id)
        _progress()

    try:
        for o in retag_ops:
            current["seq"] = o.seq   # Fix 4
            f = files[o.file_id]
            prior = {field: _tag_value(tagio.read_tags(f.path), field) for field in o.after_json}
            _journal("RETAG", o.file_id, from_path=f.path, prior_tags=prior)  # journal PRIMA
            tagio.write_tags(f.path, o.after_json)              # poi muta
            for field, value in o.after_json.items():           # DB allineato al disco:
                setattr(f, field, value)                        # niente RETAG fantasma pre-scan
            o.status = "applied"
            db.commit()
            _progress()
        for o in cover_ops:
            current["seq"] = o.seq
            f = files[o.file_id]
            if f.has_cover:
                o.status = "skipped"
                db.commit()
                soft_skipped += 1
                continue
            try:
                data = cover_art.fetch_image(cover_art.bounded_cover_url(o.after_json["full_url"]))
            except cover_art.CoverArtError:
                o.status = "skipped"
                _reopen_cover_issue(o.file_id)
                db.commit()
                soft_skipped += 1
                continue
            _journal("COVER", o.file_id, from_path=f.path)   # prior = nessuna cover
            try:
                tagio.write_cover(f.path, data)
            except Exception as exc:  # noqa: BLE001
                # Scrittura cover fallita (es. immagine troppo grande per il
                # blocco metadati FLAC): salta QUESTA cover per-op, il resto del
                # piano continua. L'entry di journal resta ma è innocua (undo →
                # remove_cover idempotente su un file senza cover).
                logger.warning("write_cover fallita su %s: %s", f.path, exc)
                o.status = "skipped"
                _reopen_cover_issue(o.file_id)
                db.commit()
                soft_skipped += 1
                continue
            f.has_cover = True
            o.status = "applied"
            db.commit()
            _progress()
        for o in rating_ops:
            current["seq"] = o.seq
            f = files[o.file_id]
            prior = tagio.read_rating(f.path)
            if not prior:
                o.status = "skipped"   # niente rating da togliere (già pulito)
                db.commit()
                soft_skipped += 1
                continue
            # journal PRIMA: prior_tags conserva il rating nativo per l'undo.
            _journal("RATING", o.file_id, from_path=f.path, prior_tags={"rating": prior})
            try:
                tagio.clear_rating(f.path)
            except tagio.TagWriteError as exc:
                logger.warning("clear_rating fallita su %s: %s", f.path, exc)
                o.status = "skipped"
                db.commit()
                soft_skipped += 1
                continue
            f.has_rating = False   # allinea il flag al disco: niente op fantasma
            o.status = "applied"
            db.commit()
            _progress()
        for o in move_ops:
            current["seq"] = o.seq   # Fix 4
            f = files[o.file_id]
            dest = o.after_json["path"]
            blocker = del_by_path.get(dest)
            if blocker is not None and blocker.file_id not in done:
                _do_delete(blocker)                            # delete-prima-di-move
            _journal(o.kind, o.file_id, from_path=f.path, to_path=dest)  # journal PRIMA
            fsops.safe_move(f.path, dest)                      # poi muta
            src_dirs.add(os.path.dirname(f.path))
            o.status = "applied"
            db.commit()
            _progress()
        for o in del_ops:
            current["seq"] = o.seq   # Fix 4
            if o.file_id not in done:
                _do_delete(o)
    except Exception as exc:  # noqa: BLE001 — stop pulito, journal intatto
        plan.status = "applied"
        db.commit()
        _cleanup_dirs()
        return ApplyResult(run_id=plan.id, applied_ops=state["applied"], partial=True,
                           failed_op_seq=current["seq"], error=str(exc),  # Fix 4: seq del PlanOp
                           skipped_ops=len(skipped) + soft_skipped,
                           started_at=started, finished_at=utcnow())

    plan.status = "applied"
    db.commit()
    _cleanup_dirs()
    return ApplyResult(run_id=plan.id, applied_ops=state["applied"],
                       skipped_ops=len(skipped) + soft_skipped,
                       started_at=started, finished_at=utcnow())
