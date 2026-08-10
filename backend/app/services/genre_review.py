"""Revisione generi su tutta la libreria: candidati dai provider come evidenza,
AI (con web search) per decidere, proposte come issue 'genre_review' oppure
riempimento delle issue genre già aperte. Sincrono e testabile: mb/discogs/ai_fn
sono iniettati (il job li costruisce). Mai due proposte aperte sullo stesso
campo di uno stesso file; i fix di origine provider e le decisioni utente
(accepted/dismissed) non si toccano."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AudioFile, Issue, utcnow
from app.services.genre_norm import normalize_genre

GENRE_REVIEW_TYPE = "genre_review"
# Issue "da inspector" che il job può riempire invece di crearne una nuova.
_FILLABLE_TYPES = ("missing_metadata", "dirty_genre")
_BATCH = 10


def _candidates_stmt(folder: str | None, genre: str | None, redo: bool):
    stmt = select(AudioFile).where(AudioFile.status == "present")
    if folder:
        stmt = stmt.where(AudioFile.path.ilike(f"%{folder}%"))
    if genre:
        stmt = stmt.where(AudioFile.genre == genre)
    if not redo:
        stmt = stmt.where(AudioFile.genre_reviewed_at.is_(None))
    return stmt


def count_candidates(db: Session, *, folder: str | None = None,
                     genre: str | None = None, redo: bool = False) -> int:
    stmt = _candidates_stmt(folder, genre, redo)
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def _provider_candidates(f: AudioFile, *, mb, discogs) -> list[str]:
    """Candidati genere dai provider, normalizzati e deduplicati (ordine: MB
    per popolarità, poi Discogs). Gli errori/None dei provider sono tollerati."""
    raw: list[str] = []
    mb_res = mb.lookup(title=f.title, artist=f.artist,
                       isrc=(f.isrc.strip() or None) if f.isrc else None,
                       mbid=f.mbid) if mb is not None else None
    if mb_res:
        raw += mb_res.get("genre_candidates") or []
        if mb_res.get("genre_primary"):
            raw.append(mb_res["genre_primary"])
    dg_res = discogs.lookup(artist=f.artist, title=f.title) \
        if discogs is not None else None
    if dg_res:
        raw += dg_res.get("genre_candidates") or []
    out: list[str] = []
    for g in raw:
        n = normalize_genre(g)
        if n and n not in out:
            out.append(n)
    return out


def _apply_proposal(db: Session, f: AudioFile, proposal: dict) -> str:
    """Applica l'esito AI a un file. Ritorna la categoria per i contatori:
    'proposed' | 'confirmed' | 'unresolved' | 'skipped'."""
    value = normalize_genre(proposal.get("genre"))
    review_row = db.scalar(select(Issue).where(
        Issue.file_id == f.id, Issue.type == GENRE_REVIEW_TYPE,
        Issue.field == "genre"))
    if value is None:
        return "unresolved"
    current = normalize_genre(f.genre)
    if current is not None and value.lower() == current.lower():
        # Genere confermato: una genre_review aperta non ha più ragione d'essere.
        if review_row is not None and review_row.status == "open":
            db.delete(review_row)
        return "confirmed"

    fix = {"field": "genre", "action": "retag", "to": value,
           "source": "ai", "confidence": proposal.get("confidence", "low")}
    detail = f"AI: genre → {value}"
    open_rows = db.scalars(select(Issue).where(
        Issue.file_id == f.id, Issue.field == "genre",
        Issue.status == "open")).all()
    by_type = {r.type: r for r in open_rows}

    fillable = next((by_type[t] for t in _FILLABLE_TYPES if t in by_type), None)
    if fillable is not None:
        if (fillable.suggested_fix_json or {}).get("source") == "provider":
            return "skipped"  # provider > AI, mai sovrascrivere
        fillable.suggested_fix_json = fix
        fillable.updated_at = utcnow()
        return "proposed"
    if any(r.type != GENRE_REVIEW_TYPE for r in open_rows):
        return "skipped"  # es. provider_override aperto: niente doppioni
    if review_row is None:
        db.add(Issue(file_id=f.id, type=GENRE_REVIEW_TYPE, field="genre",
                     severity="info", detail=detail, suggested_fix_json=fix,
                     status="open"))
        return "proposed"
    if review_row.status == "open":
        review_row.suggested_fix_json = fix
        review_row.detail = detail
        review_row.updated_at = utcnow()
        return "proposed"
    return "skipped"  # accepted/dismissed: decisione utente


def review(db: Session, *, mb, discogs, ai_fn, folder: str | None = None,
           genre: str | None = None, redo: bool = False,
           batch_size: int = _BATCH, on_progress=None) -> dict:
    """Loop principale: batch di file → lookup provider → una chiamata AI →
    applicazione esiti + commit. Un batch AI fallito conta come unresolved e il
    job prosegue col successivo."""
    files = db.scalars(_candidates_stmt(folder, genre, redo)).all()
    total = len(files)
    res = {"configured": True, "files": total, "proposed": 0, "confirmed": 0,
           "unresolved": 0, "skipped": 0}
    done = 0
    for start in range(0, total, batch_size):
        batch = files[start:start + batch_size]
        items = []
        for f in batch:
            if on_progress is not None:
                on_progress(done + len(items), total, "looking_up")
            items.append({
                "artist": f.artist, "title": f.title, "album": f.album,
                "label": f.label, "current_genre": f.genre,
                "candidates": _provider_candidates(f, mb=mb, discogs=discogs),
            })
        if on_progress is not None:
            on_progress(done, total, "reviewing")
        try:
            results = ai_fn(items)
        except Exception:  # noqa: BLE001 — un batch fallito non ferma il job
            results = [None] * len(batch)
        for f, proposal in zip(batch, results):
            res[_apply_proposal(db, f, proposal or {})] += 1
            f.genre_reviewed_at = utcnow()
        done += len(batch)
        db.commit()
        if on_progress is not None:
            on_progress(done, total, "reviewing")
    return res
