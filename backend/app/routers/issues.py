"""Router ISSUES: lista filtrabile + cambio status (singolo e in blocco). Sottile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, Issue, utcnow
from app.schemas import IssueBulkBody, IssueRead, IssueStatusBody

router = APIRouter(prefix="/api/issues", tags=["issues"])
_VALID = {"open", "accepted", "dismissed"}


def _to_read(issue: Issue, file: AudioFile) -> IssueRead:
    return IssueRead(
        id=issue.id, file_id=issue.file_id, type=issue.type, field=issue.field,
        severity=issue.severity, detail=issue.detail,
        suggested_fix_json=issue.suggested_fix_json, status=issue.status,
        file_path=file.path, artist=file.artist, title=file.title,
    )


@router.get("", response_model=list[IssueRead])
def list_issues(severity: str | None = None, type: str | None = None,
                status: str | None = None, root_id: int | None = None,
                db: Session = Depends(get_db)):
    stmt = select(Issue, AudioFile).join(AudioFile, Issue.file_id == AudioFile.id)
    if severity:
        stmt = stmt.where(Issue.severity == severity)
    if type:
        stmt = stmt.where(Issue.type == type)
    if status:
        stmt = stmt.where(Issue.status == status)
    if root_id:
        stmt = stmt.where(AudioFile.root_id == root_id)
    return [_to_read(i, f) for i, f in db.execute(stmt).all()]


@router.post("/{issue_id}/status", response_model=dict)
def set_status(issue_id: int, body: IssueStatusBody, db: Session = Depends(get_db)):
    if body.status not in _VALID:
        raise HTTPException(status_code=400, detail="status non valido")
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="issue non trovato")
    if body.status == "accepted" and issue.suggested_fix_json is None:
        raise HTTPException(status_code=400, detail="issue non auto-fixabile")
    issue.status = body.status
    issue.updated_at = utcnow()
    db.commit()
    return {"id": issue.id, "status": issue.status}


@router.post("/bulk", response_model=dict)
def bulk(body: IssueBulkBody, db: Session = Depends(get_db)):
    if body.status not in _VALID:
        raise HTTPException(status_code=400, detail="status non valido")
    stmt = select(Issue)
    if body.type:
        stmt = stmt.where(Issue.type == body.type)
    if body.severity:
        stmt = stmt.where(Issue.severity == body.severity)
    updated = 0
    for issue in db.scalars(stmt).all():
        if body.status == "accepted" and issue.suggested_fix_json is None:
            continue
        issue.status = body.status
        issue.updated_at = utcnow()
        updated += 1
    db.commit()
    return {"updated": updated}
