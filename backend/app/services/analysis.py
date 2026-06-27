"""Orchestratore dell'analisi: legge audio_file, chiama Inspector/Dedup, fa il merge
preservando le decisioni utente. Impuro (scrive il DB)."""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AudioFile, DupGroup, DupMember, Issue, utcnow
from app.schemas import AnalyzeSummary
from app.services.dedup import find_duplicates
from app.services.inspector import inspect


def _merge_issues(db: Session, computed) -> None:
    existing = {(i.file_id, i.type, i.field): i for i in db.scalars(select(Issue)).all()}
    seen: set = set()
    for c in computed:
        key = (c.file_id, c.type, c.field)
        seen.add(key)
        row = existing.get(key)
        if row is None:
            db.add(Issue(file_id=c.file_id, type=c.type, field=c.field, severity=c.severity,
                         detail=c.detail, suggested_fix_json=c.suggested_fix, status="open"))
        else:
            row.severity = c.severity
            row.detail = c.detail
            row.suggested_fix_json = c.suggested_fix
            row.updated_at = utcnow()
    for key, row in existing.items():
        if key not in seen:
            db.delete(row)


def _signature(member_ids) -> str:
    joined = ",".join(str(i) for i in sorted(member_ids))
    return hashlib.blake2b(joined.encode()).hexdigest()


def _merge_dups(db: Session, computed) -> None:
    old_groups = db.scalars(select(DupGroup)).all()
    decisions = {g.signature: (g.dismissed, g.keeper_overridden, g.keeper_file_id)
                 for g in old_groups}
    for g in old_groups:
        db.delete(g)  # la cascade all/delete-orphan rimuove anche i membri
    db.flush()
    for c in computed:
        sig = _signature(c.member_ids)
        dismissed, overridden, keeper = False, False, c.keeper_id
        if sig in decisions:
            d_dismissed, d_overridden, d_keeper = decisions[sig]
            if d_dismissed:
                dismissed = True
            elif d_overridden and d_keeper in c.member_ids:
                overridden, keeper = True, d_keeper
        grp = DupGroup(match_kind=c.match_kind, keeper_file_id=keeper,
                       keeper_overridden=overridden, dismissed=dismissed, signature=sig)
        db.add(grp)
        db.flush()
        for fid in c.member_ids:
            action = "keep" if (dismissed or fid == keeper) else "remove"
            db.add(DupMember(group_id=grp.id, file_id=fid, action=action))


def _summary(db: Session) -> AnalyzeSummary:
    by_sev = dict(db.execute(
        select(Issue.severity, func.count()).group_by(Issue.severity)
    ).all())
    dup_groups = db.scalar(select(func.count()).select_from(DupGroup)) or 0
    dup_files = db.scalar(select(func.count()).select_from(DupMember)) or 0
    return AnalyzeSummary(issues_total=sum(by_sev.values()), issues_by_severity=by_sev,
                          dup_groups=dup_groups, dup_files=dup_files)


def recompute(db: Session, on_progress=None) -> AnalyzeSummary:
    started = utcnow()
    files = db.scalars(select(AudioFile).where(AudioFile.status == "present")).all()
    if on_progress is not None:
        on_progress(0, 2, "inspecting")
    _merge_issues(db, inspect(files))
    if on_progress is not None:
        on_progress(1, 2, "deduping")
    _merge_dups(db, find_duplicates(files))
    db.commit()
    summary = _summary(db)
    summary.started_at = started
    summary.finished_at = utcnow()
    return summary
