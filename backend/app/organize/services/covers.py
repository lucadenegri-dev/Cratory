# backend/app/services/covers.py
"""Copertine: ricerca (CAA/Discogs) e issue sintetica 'missing_cover'.

Estratto dal router così che *sia* provider-suggest *sia* il rescan possano
riusare la stessa logica (che vive nei services, non nei router)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.organize.integrations import cover_art
from app.organize.models import AudioFile, Issue, utcnow
from app.organize.services import cover_cache


def upsert_cover_issue(db: Session, file_id: int, cover, thumb_bytes: bytes) -> bool:
    """Crea/aggiorna l'issue missing_cover. Non tocca (né ri-cacha) le proposte
    già accettate o ignorate. Ritorna True se ha agito."""
    issue = db.scalar(select(Issue).where(
        Issue.file_id == file_id, Issue.type == "missing_cover", Issue.field == "cover"))
    if issue is not None and issue.status != "open":
        return False  # non resuscitare (né ri-cacha la thumb di) proposte accettate/ignorate
    ref = cover_cache.save_thumb(file_id, thumb_bytes)
    if issue is None:
        issue = Issue(file_id=file_id, type="missing_cover", field="cover",
                      severity="info", detail="copertina mancante", status="open")
        db.add(issue)
    issue.suggested_fix_json = {"field": "cover", "source": cover.source,
                                "confidence": cover.confidence,
                                "full_url": cover.full_url, "thumb_ref": ref}
    issue.updated_at = utcnow()
    return True


def fetch_cover(db: Session, file: AudioFile, resolved, *, caa=None, discogs=None,
                fetch=None) -> bool:
    """Per un file **senza** copertina cerca l'arte dai provider (CAA su match
    'high', Discogs come fallback) usando i release-MBID già risolti; se la trova
    crea/aggiorna l'issue missing_cover. Ritorna True se ha proposto una cover."""
    if file.has_cover:
        return False
    cover = cover_art.lookup_cover(
        release_mbids=resolved.release_mbids, confidence=resolved.confidence,
        artist=file.artist, title=file.title, caa=caa, discogs=discogs, fetch=fetch)
    if cover is None:
        return False
    return upsert_cover_issue(db, file.id, cover, cover.thumb_bytes)
