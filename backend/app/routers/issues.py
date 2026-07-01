"""Router ISSUES: lista filtrabile + cambio status (singolo e in blocco) + AI. Sottile."""

import os
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, Issue, utcnow
from app.schemas import IssueBulkBody, IssueFixBody, IssueRead, IssueStatusBody
from app.services import ai_tags, cratory_bridge, planning

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


# --- Bridge Cratory ----------------------------------------------------------
# Precedenza valori (spec ecosistema): fix manuale > tag pulito nel file >
# suggerimento Cratory > AI-da-filename. Il bridge tocca SOLO issue aperte:
# un tag pulito non ha issue (mai toccato), un fix manuale/accettato ha
# status != "open" (mai toccato). Sovrascrive invece un suggerimento AI non
# ancora accettato (Cratory > AI); gli endpoint AI, che saltano le issue già
# suggerite, non sovrascrivono mai il bridge.

_BRIDGE_TYPES = ("missing_required_tag", "missing_metadata", "dirty_genre")
_BRIDGE_FIELDS = ("artist", "title", "genre", "year", "label")
_NOT_CONFIGURED = {"configured": False, "files": 0, "suggested": 0,
                   "unresolved": 0, "mismatches": 0}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


@router.post("/bridge-suggest", response_model=dict)
def bridge_suggest(db: Session = Depends(get_db)):
    base_url = (planning.get_settings(db).cratory_base_url or "").strip()
    if not base_url:
        return dict(_NOT_CONFIGURED)

    rows = db.execute(
        select(Issue, AudioFile)
        .join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.type.in_(_BRIDGE_TYPES),
               Issue.field.in_(_BRIDGE_FIELDS))
    ).all()
    isrc_files = [f for f in db.scalars(
        select(AudioFile).where(AudioFile.status == "present",
                                AudioFile.isrc.is_not(None))
    ).all() if (f.isrc or "").strip()]

    cache: dict[int, dict | None] = {}

    def _lookup(f: AudioFile) -> dict | None:
        """Una sola lookup HTTP per file (cache). None = nessuna chiave usabile."""
        if f.id not in cache:
            if (f.isrc or "").strip():
                cache[f.id] = cratory_bridge.lookup(base_url, isrc=f.isrc.strip())
            elif (f.artist or "").strip() and (f.title or "").strip():
                cache[f.id] = cratory_bridge.lookup(
                    base_url, artist=f.artist.strip(), title=f.title.strip())
            else:
                cache[f.id] = None
        return cache[f.id]

    suggested = unresolved = mismatches = 0
    files_seen: set[int] = set()
    try:
        # 1) Riempi suggested_fix sulle issue aperte esistenti (mai su tag puliti:
        #    un tag pulito non ha issue). Mai auto-accettare: status resta open.
        for issue, f in rows:
            files_seen.add(f.id)
            res = _lookup(f)
            value = res.get(issue.field) if res and res.get("found") else None
            if isinstance(value, str):
                value = value.strip() or None
            if value is not None:
                issue.suggested_fix_json = {"field": issue.field,
                                            "action": "retag", "to": value}
                issue.updated_at = utcnow()
                suggested += 1
            else:
                unresolved += 1

        # 2) Pulisci le bridge_mismatch orfane (file non più presente o senza
        #    più ISRC): il merge dell'analisi le esenta dalla cancellazione,
        #    quindi la riconciliazione avviene qui.
        for issue, f in db.execute(
            select(Issue, AudioFile).join(AudioFile, Issue.file_id == AudioFile.id)
            .where(Issue.type == "bridge_mismatch")
        ).all():
            if f.status != "present" or not (f.isrc or "").strip():
                db.delete(issue)

        # 3) Check discrepanze: solo match ISRC (confidence 100), mai fuzzy.
        #    Senza ISRC nel file il check si salta.
        for f in isrc_files:
            res = _lookup(f)
            if res is None or not res.get("found") or res.get("match") != "isrc":
                continue  # nessuna informazione certa: non toccare nulla
            expected: dict[str, str] = {}
            for field in ("artist", "title"):
                c_val = (res.get(field) or "").strip()
                if c_val and _norm(getattr(f, field)) \
                        and _norm(c_val) != _norm(getattr(f, field)):
                    expected[field] = c_val
            existing = {i.field: i for i in db.scalars(
                select(Issue).where(Issue.file_id == f.id,
                                    Issue.type == "bridge_mismatch")).all()}
            for field, c_val in expected.items():
                detail = (f"Cratory (ISRC {f.isrc.strip()}): {field} = '{c_val}', "
                          f"nel file = '{getattr(f, field)}'")
                row = existing.get(field)
                if row is None:
                    db.add(Issue(file_id=f.id, type="bridge_mismatch", field=field,
                                 severity="warning", detail=detail,
                                 suggested_fix_json={"field": field,
                                                     "action": "retag", "to": c_val},
                                 status="open"))
                    mismatches += 1
                else:
                    row.detail = detail
                    if row.status == "open":  # le decisioni utente sono intoccabili
                        row.suggested_fix_json = {"field": field,
                                                  "action": "retag", "to": c_val}
                        mismatches += 1
                    row.updated_at = utcnow()
            for field, row in existing.items():
                if field not in expected:
                    db.delete(row)  # discrepanza risolta (o non più confermata)
    except cratory_bridge.CratoryUnreachable:
        # Degradazione pulita: niente modifiche parziali, stessa UX del
        # non-configurato (come ai-suggest senza ANTHROPIC_API_KEY).
        db.rollback()
        return dict(_NOT_CONFIGURED)

    db.commit()
    return {"configured": True, "files": len(files_seen), "suggested": suggested,
            "unresolved": unresolved, "mismatches": mismatches}
