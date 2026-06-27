"""Orchestratore dell'analisi: legge audio_file, chiama Inspector/Dedup, fa il merge
preservando le decisioni utente. Impuro (scrive il DB)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AudioFile, Issue, utcnow
from app.schemas import AnalyzeSummary
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


def _summary(db: Session) -> AnalyzeSummary:
    by_sev = dict(db.execute(
        select(Issue.severity, func.count()).group_by(Issue.severity)
    ).all())
    total = sum(by_sev.values())
    return AnalyzeSummary(issues_total=total, issues_by_severity=by_sev)


def recompute(db: Session, on_progress=None) -> AnalyzeSummary:
    started = utcnow()
    files = db.scalars(select(AudioFile).where(AudioFile.status == "present")).all()
    if on_progress is not None:
        on_progress(0, 1, "inspecting")
    _merge_issues(db, inspect(files))
    db.commit()
    summary = _summary(db)
    summary.started_at = started
    summary.finished_at = utcnow()
    return summary
