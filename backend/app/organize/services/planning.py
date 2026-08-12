"""Orchestratore Plan/Conflict: settings + costruzione/lettura del piano."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.organize.models import (
    AudioFile, DupMember, Issue, Plan, PlanOp, Settings, UndoJournal, utcnow,
)
from app.organize.schemas import ConflictRead, PlanOpRead, PlanRead, PlanStats
from app.organize.services import conflict
from app.organize.services.planner import PlanOpComputed, build_plan

DEFAULT_NAMING = "{artist} - {title}"
DEFAULT_FOLDER = "{genre}/{artist}"


def get_settings(db: Session) -> Settings:
    s = db.get(Settings, 1)
    if s is None:
        s = Settings(id=1, naming_template=DEFAULT_NAMING, folder_template=DEFAULT_FOLDER)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def update_settings(db: Session, naming_template=None, folder_template=None) -> Settings:
    s = get_settings(db)
    if naming_template is not None:
        s.naming_template = naming_template
    if folder_template is not None:
        s.folder_template = folder_template
    s.updated_at = utcnow()
    db.commit()
    db.refresh(s)
    return s


DEFAULT_LANGUAGE = "en"


def get_language(db: Session) -> str:
    """Lingua dell'app ("it" | "en"): valori sconosciuti degradano al default EN."""
    s = get_settings(db)
    return s.language if s.language in ("it", "en") else DEFAULT_LANGUAGE


def set_language(db: Session, value: str) -> Settings:
    s = get_settings(db)
    s.language = value
    s.updated_at = utcnow()
    db.commit()
    db.refresh(s)
    return s


def target_root() -> str:
    """Destinazione di ogni operazione di Apply: la libreria.

    Fino a F3b esisteva un target per ScanRoot (`root_targets`), ma le due
    radici davano già la stessa destinazione — ed è strutturale: un file
    dell'inbox arriva in libreria, un file della libreria ci resta e si
    riorganizza dentro. Non c'è un secondo posto dove un Apply possa portare
    qualcosa.
    """
    from app.core.config import settings

    return settings.library_root


def _inputs(db):
    files = db.scalars(
        select(AudioFile).where(AudioFile.status == "present", AudioFile.scan_error.is_(None))
    ).all()
    accepted = db.scalars(select(Issue).where(Issue.status == "accepted")).all()
    removals = {m.file_id for m in db.scalars(
        select(DupMember).where(DupMember.action == "remove")).all()}
    # I file corrotti accettati vanno in quarantena come removal (op DELETE).
    removals |= {i.file_id for i in accepted
                 if i.type == "corrupt_file"
                 and (i.suggested_fix_json or {}).get("action") == "quarantine"}
    s = get_settings(db)
    snapshot = {"naming_template": s.naming_template, "folder_template": s.folder_template}
    return files, accepted, removals, snapshot, target_root()


def create_plan(db: Session) -> PlanRead:
    files, accepted, removals, snapshot, target = _inputs(db)
    computed = build_plan(files, accepted, removals, snapshot, target)
    for old in db.scalars(select(Plan).where(Plan.status == "draft")).all():
        # Una bozza con righe di undo journal non è una bozza: è un apply morto
        # prima di potersi marcare 'applied' (apply.py lo fa in fondo, sia sul
        # percorso normale sia su quello d'errore, quindi ci si arriva solo con
        # una terminazione brutale del processo — es. il server fermato durante
        # un apply lungo). Cancellarla distruggerebbe il journal, cioè la
        # reversibilità dei file già spostati su disco; e con foreign_keys=ON
        # fallirebbe comunque, perché UndoJournal.run_id non ha una
        # relationship() che ordini le cancellazioni. La si promuove ad
        # 'applied': è ciò che l'apply avrebbe fatto se fosse arrivato in fondo.
        # Qui una flush() non servirebbe a nulla: le righe figlie esistono
        # davvero, non è un problema di ordinamento.
        if db.scalar(select(UndoJournal.id).where(UndoJournal.run_id == old.id).limit(1)) is not None:
            old.status = "applied"
        else:
            db.delete(old)
    db.flush()
    rules = {**snapshot, "target_root": target}
    plan = Plan(status="draft", rules_json=rules)
    db.add(plan)
    db.flush()
    for seq, op in enumerate(computed):
        db.add(PlanOp(plan_id=plan.id, seq=seq, kind=op.kind, file_id=op.file_id,
                      before_json=op.before, after_json=op.after, status="pending"))
    db.commit()
    return load_plan(db)


def load_plan(db: Session) -> PlanRead | None:
    plan = db.scalar(select(Plan).where(Plan.status == "draft").order_by(Plan.id.desc()))
    if plan is None:
        return None
    ops = db.scalars(select(PlanOp).where(PlanOp.plan_id == plan.id)
                     .order_by(PlanOp.seq)).all()
    files, accepted, removals, snapshot, target = _inputs(db)
    files_by_id = {f.id: f for f in files}
    op_computed = [PlanOpComputed(o.kind, o.file_id, o.before_json, o.after_json) for o in ops]
    conflicts = conflict.check(op_computed, files_by_id, accepted, removals, snapshot, target,
                               disk_occupied=conflict.disk_occupied(op_computed))
    skip_ids = {c.file_id for c in conflicts if c.kind in ("collision", "outside_root")}

    counts = {"RETAG": 0, "COVER": 0, "RENAME": 0, "MOVE": 0, "DELETE": 0}
    space = 0
    n_skipped = 0
    for o in ops:
        counts[o.kind] = counts.get(o.kind, 0) + 1
        if o.kind in ("RENAME", "MOVE") and o.file_id in skip_ids:
            n_skipped += 1
        if o.kind == "DELETE":
            f = files_by_id.get(o.file_id)
            space += (f.size_bytes or 0) if f else 0
    stats = PlanStats(n_retag=counts["RETAG"], n_cover=counts["COVER"],
                      n_rename=counts["RENAME"],
                      n_move=counts["MOVE"], n_delete=counts["DELETE"],
                      space_freed_bytes=space, n_conflicts=len(conflicts),
                      n_skipped=n_skipped,
                      blocking=len(ops) > 0 and n_skipped == len(ops))
    op_reads = [PlanOpRead(id=o.id, seq=o.seq, kind=o.kind, file_id=o.file_id,
                           file_path=files_by_id[o.file_id].path if o.file_id in files_by_id else "",
                           before=o.before_json, after=o.after_json, status=o.status,
                           skipped=o.kind in ("RENAME", "MOVE") and o.file_id in skip_ids)
                for o in ops]
    conflict_reads = [ConflictRead(kind=c.kind, file_id=c.file_id, detail=c.detail)
                      for c in conflicts]
    return PlanRead(id=plan.id, status=plan.status, created_at=plan.created_at,
                    rules=plan.rules_json, ops=op_reads, conflicts=conflict_reads, stats=stats)
