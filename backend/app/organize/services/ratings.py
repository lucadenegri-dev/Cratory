# backend/app/services/ratings.py
"""Rating (stelline) come issue sintetica 'stray_rating': rileva i file che
hanno un rating embeddato e propone di svuotarlo (action=clear), che poi
confluisce nel flusso accept → PLAN → apply → undo come un op RATING dedicato."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.organize.models import AudioFile, Issue, utcnow
from app.organize.integrations import tagio

_TYPE = "stray_rating"


def _stars(token: str | None) -> int | None:
    """Stima 1-5 stelle dal token nativo (solo per il testo della issue)."""
    try:
        n = int(str(token).strip())
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n <= 5:
        stars = n                      # già in scala 0-5
    elif n <= 100:
        stars = round(n / 20)          # scala 0-100
    else:
        stars = round(n / 51)          # POPM 0-255
    return max(1, min(5, stars))


def upsert_rating_issue(db: Session, file_id: int, token: str) -> bool:
    """Crea/aggiorna la issue stray_rating (una per file). Non tocca proposte
    già accettate/ignorate. Ritorna True se ha agito."""
    iss = db.scalar(select(Issue).where(
        Issue.file_id == file_id, Issue.type == _TYPE))
    if iss is not None and iss.status != "open":
        return False
    stars = _stars(token)
    detail = f"rating {stars}★ presente" if stars else "rating presente"
    fix = {"field": "rating", "action": "clear"}
    if iss is None:
        db.add(Issue(file_id=file_id, type=_TYPE, field="rating", severity="info",
                     detail=detail, suggested_fix_json=fix, status="open"))
        return True
    iss.detail = detail
    iss.suggested_fix_json = fix
    iss.updated_at = utcnow()
    return True


def detect_ratings(db: Session) -> dict:
    """Scorre i file presenti, legge il rating e crea/aggiorna una issue
    stray_rating per quelli che ne hanno uno. Sincrono (come provider-suggest)."""
    files = db.scalars(select(AudioFile).where(AudioFile.status == "present")).all()
    found = created = 0
    for f in files:
        try:
            token = tagio.read_rating(f.path)
        except tagio.TagReadError:
            continue
        # has_rating riflette lo stato reale sul disco: consente al planner di
        # non rigenerare op RATING fantasma sui file già ripuliti (simmetrico a
        # has_cover). Va mantenuto anche quando il rating è assente.
        f.has_rating = bool(token)
        if not token:
            continue
        found += 1
        if upsert_rating_issue(db, f.id, token):
            created += 1
    db.commit()
    return {"files": len(files), "found": found, "created": created}
