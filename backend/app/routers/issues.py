"""Router ISSUES: lista filtrabile + cambio status (singolo e in blocco) + AI. Sottile."""

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, Issue, utcnow
from app.schemas import IssueBulkBody, IssueFixBody, IssueRead, IssueStatusBody
from app.services import ai_tags

router = APIRouter(prefix="/api/issues", tags=["issues"])
_VALID = {"open", "accepted", "dismissed"}

# Campi tag effettivi (= planner._EFFECTIVE_FIELDS): gli unici correggibili a mano.
_RETAGGABLE = {"artist", "title", "album", "album_artist", "genre", "year",
               "label", "track_no", "comment"}


def _to_read(issue: Issue, file: AudioFile) -> IssueRead:
    return IssueRead(
        id=issue.id, file_id=issue.file_id, root_id=file.root_id, type=issue.type,
        field=issue.field, severity=issue.severity, detail=issue.detail,
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
    if root_id is not None:
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


@router.post("/{issue_id}/fix", response_model=IssueRead)
def fix_issue(issue_id: int, body: IssueFixBody, db: Session = Depends(get_db)):
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="issue non trovato")
    if issue.field not in _RETAGGABLE:
        raise HTTPException(status_code=400, detail="campo non correggibile a mano")
    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="valore vuoto")
    issue.suggested_fix_json = {"field": issue.field, "action": "retag", "to": value}
    issue.status = "accepted"
    issue.updated_at = utcnow()
    db.commit()
    file = db.get(AudioFile, issue.file_id)
    return _to_read(issue, file)


@router.post("/ai-suggest", response_model=dict)
def ai_suggest(db: Session = Depends(get_db)):
    if not ai_tags.is_configured():
        return {"configured": False, "files": 0, "suggested": 0, "unresolved": 0}
    rows = db.execute(
        select(Issue, AudioFile)
        .join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.type == "missing_required_tag",
               Issue.field.in_(("artist", "title")))
    ).all()
    # JSON null si filtra in Python: la colonna JSON serializza None come 'null'
    # (convenzione del codebase, vedi bulk()/set_status()).
    todo = [(issue, f) for issue, f in rows if issue.suggested_fix_json is None]
    if not todo:
        return {"configured": True, "files": 0, "suggested": 0, "unresolved": 0}

    by_file: dict[int, str] = {}
    for issue, f in todo:
        by_file.setdefault(issue.file_id,
                           os.path.splitext(os.path.basename(f.path))[0])
    file_ids = list(by_file.keys())
    guesses = ai_tags.suggest([by_file[fid] for fid in file_ids])
    guess_by_file = {fid: guesses[k] for k, fid in enumerate(file_ids)
                     if k < len(guesses)}

    suggested = 0
    unresolved = 0
    for issue, f in todo:
        g = guess_by_file.get(issue.file_id) or {}
        value = (g.get(issue.field) or "").strip()
        if value:
            issue.suggested_fix_json = {"field": issue.field, "action": "retag", "to": value}
            issue.updated_at = utcnow()
            suggested += 1
        else:
            unresolved += 1
    db.commit()
    return {"configured": True, "files": len(file_ids),
            "suggested": suggested, "unresolved": unresolved}


@router.post("/ai-suggest-genre", response_model=dict)
def ai_suggest_genre(db: Session = Depends(get_db)):
    if not ai_tags.is_configured():
        return {"configured": False, "files": 0, "suggested": 0, "unresolved": 0}
    rows = db.execute(
        select(Issue, AudioFile)
        .join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.field == "genre",
               Issue.type.in_(("missing_metadata", "dirty_genre")))
    ).all()
    todo = [(issue, f) for issue, f in rows if issue.suggested_fix_json is None]
    if not todo:
        return {"configured": True, "files": 0, "suggested": 0, "unresolved": 0}

    file_ids = [f.id for _, f in todo]
    # artista/titolo "effettivi" dai suggested_fix delle issue artist/title
    at_issues = db.scalars(
        select(Issue).where(Issue.file_id.in_(file_ids),
                            Issue.field.in_(("artist", "title")))
    ).all()
    sugg: dict[int, dict[str, str]] = {}
    for iss in at_issues:
        fix = iss.suggested_fix_json
        if fix and fix.get("to"):
            sugg.setdefault(iss.file_id, {})[iss.field] = fix["to"]

    def _describe(f) -> str:
        artist = f.artist or sugg.get(f.id, {}).get("artist")
        title = f.title or sugg.get(f.id, {}).get("title")
        if artist and title:
            base = f"{artist} - {title}"
        elif artist or title:
            base = artist or title
        else:
            base = os.path.splitext(os.path.basename(f.path))[0]
        # Per i 'dirty_genre' il file ha già un genere (sporco): passalo come
        # contesto perché l'AI ne estragga il primario pulito.
        if f.genre and f.genre.strip():
            base = f"{base} [genere attuale: {f.genre.strip()}]"
        return base

    genres = ai_tags.suggest_genres([_describe(f) for _, f in todo])

    suggested = 0
    unresolved = 0
    for (issue, _f), genre in zip(todo, genres):
        value = (genre or "").strip()
        if value:
            issue.suggested_fix_json = {"field": "genre", "action": "retag", "to": value}
            issue.updated_at = utcnow()
            suggested += 1
        else:
            unresolved += 1
    db.commit()
    return {"configured": True, "files": len(todo),
            "suggested": suggested, "unresolved": unresolved}
