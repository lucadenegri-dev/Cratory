# backend/app/services/provider_rescan.py
"""Core della ricerca provider 'per traccia' (riclassificazione). Sincrono e
testabile: i provider (mb/discogs/ac_client) sono iniettati. Produce/aggiorna
issue sintetiche 'provider_override' che confluiscono nel flusso accept/PLAN/apply."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AudioFile, Issue, utcnow
from app.services import covers as cover_svc
from app.services import text_providers
from app.services.fingerprint import fingerprint_one

RESCAN_FIELDS = ("genre", "album", "label", "year", "artist", "title")
_OVERRIDE_TYPE = "provider_override"


def has_open_inspector_issue(db: Session, file_id: int, field: str) -> bool:
    """True se c'è già una issue APERTA non-override su quel (file, campo):
    in quel caso il flusso normale la gestisce, l'override non deve duplicare."""
    row = db.scalar(
        select(Issue.id).where(Issue.file_id == file_id, Issue.field == field,
                               Issue.type != _OVERRIDE_TYPE, Issue.status == "open")
    )
    return row is not None


def _get_override(db: Session, file_id: int, field: str) -> Issue | None:
    return db.scalar(select(Issue).where(
        Issue.file_id == file_id, Issue.type == _OVERRIDE_TYPE, Issue.field == field))


def upsert_override(db: Session, file_id: int, field: str, value: Any, confidence: str,
                    *, include_accepted: bool = False, include_dismissed: bool = False) -> bool:
    """Crea/aggiorna la proposta override. Ritorna True se ha effettivamente
    proposto (creata o (ri)aperta), False se ha lasciato intatta una decisione
    utente. Di default accepted/dismissed NON si toccano; con i flag si
    'riaprono' (ri-proposte) — ma solo perché il chiamante arriva qui già solo
    quando il valore differisce dal file (vedi rescan)."""
    fix = {"field": field, "action": "retag", "to": str(value),
           "source": "provider", "confidence": confidence}
    detail = f"provider: {field} → {value}"
    row = _get_override(db, file_id, field)
    if row is None:
        db.add(Issue(file_id=file_id, type=_OVERRIDE_TYPE, field=field,
                     severity="info", detail=detail, suggested_fix_json=fix, status="open"))
        return True
    if row.status == "open":
        row.suggested_fix_json = fix
        row.detail = detail
        row.updated_at = utcnow()
        return True
    if (row.status == "accepted" and include_accepted) or \
            (row.status == "dismissed" and include_dismissed):
        row.suggested_fix_json = fix
        row.detail = detail
        row.status = "open"
        row.updated_at = utcnow()
        return True
    return False


def delete_stale_override(db: Session, file_id: int, field: str) -> None:
    row = _get_override(db, file_id, field)
    if row is not None and row.status == "open":
        db.delete(row)


def _differs(current: Any, value: Any) -> bool:
    if current is None:
        return True
    if isinstance(value, int):
        return current != value
    return str(current).strip() != str(value).strip()


def rescan(db: Session, *, folder: str | None = None, genre: str | None = None,
           fields: list[str] | None = None, mb, discogs, ac_client=None, caa=None,
           covers: bool = False, only_new: bool = False, on_progress=None,
           include_accepted: bool = False, include_dismissed: bool = False) -> dict:
    # I campi override sono opzionali quando si cercano solo le copertine; se non
    # si chiede né campi né cover, si ricade sul default 'genre' (comportamento
    # storico). Un file è "nuovo" se visto in una sola scansione: first_seen == last_scanned.
    fields = [f for f in (fields or []) if f in RESCAN_FIELDS]
    if not fields and not covers:
        fields = ["genre"]
    stmt = select(AudioFile).where(AudioFile.status == "present")
    if folder:
        stmt = stmt.where(AudioFile.path.ilike(f"%{folder}%"))
    if genre:
        stmt = stmt.where(AudioFile.genre == genre)
    if only_new:
        stmt = stmt.where(AudioFile.first_seen_at == AudioFile.last_scanned_at)
    files = db.scalars(stmt).all()
    total = len(files)
    res = {"configured": True, "acoustid_available": ac_client is not None,
           "scanned": total, "fingerprinted": 0, "matched": 0, "no_match": 0,
           "proposed_high": 0, "proposed_text": 0, "covers": 0}

    for idx, f in enumerate(files):
        if on_progress is not None:
            on_progress(idx, total, "looking_up")
        if not f.mbid and ac_client is not None and fingerprint_one(f, ac_client):
            res["fingerprinted"] += 1
        # resolve() dà i campi (come lookup_with_conf) *e* i release-MBID, che
        # servono alla ricerca cover.
        resolved = text_providers.resolve(f, mb=mb, discogs=discogs)
        found = resolved.fields
        res["matched" if found else "no_match"] += 1
        for field in fields:
            if field not in found:
                delete_stale_override(db, f.id, field)
                continue
            value, conf = found[field]
            if not _differs(getattr(f, field), value):
                delete_stale_override(db, f.id, field)
                continue
            if has_open_inspector_issue(db, f.id, field):
                continue
            if upsert_override(db, f.id, field, value, conf,
                               include_accepted=include_accepted,
                               include_dismissed=include_dismissed):
                res["proposed_high" if conf == "high" else "proposed_text"] += 1
        if covers and cover_svc.fetch_cover(db, f, resolved, caa=caa, discogs=discogs):
            res["covers"] += 1
        db.commit()

    if on_progress is not None:
        on_progress(total, total, "looking_up")
    return res
