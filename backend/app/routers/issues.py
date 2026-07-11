"""Router ISSUES: lista filtrabile + cambio status (singolo e in blocco) + AI. Sottile."""

import os

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_errors import api_error
from app.db import get_db
from app.integrations import acoustid, cover_art
from app.models import AudioFile, Issue, utcnow
from app.schemas import (IssueBulkBody, IssueFixBody, IssueRead, IssueStatusBody,
                         ProviderRescanBody, ProviderSuggestBody)
from app.services import ai_tags, apply_job, cover_cache, covers as cover_svc, provider_rescan_job, ratings, scan_job, text_providers

router = APIRouter(prefix="/api/issues", tags=["issues"])
_VALID = {"open", "accepted", "dismissed"}

# Campi tag effettivi (= planner._EFFECTIVE_FIELDS): gli unici correggibili a mano.
_RETAGGABLE = {"artist", "title", "album", "album_artist", "genre", "year",
               "label", "track_no", "comment"}


def _to_read(issue: Issue, file: AudioFile) -> IssueRead:
    cur = getattr(file, issue.field, None) if issue.field else None
    return IssueRead(
        id=issue.id, file_id=issue.file_id, root_id=file.root_id, type=issue.type,
        field=issue.field, severity=issue.severity, detail=issue.detail,
        suggested_fix_json=issue.suggested_fix_json, status=issue.status,
        file_path=file.path, artist=file.artist, title=file.title,
        current_value=None if cur is None else str(cur),
        is_new=file.first_seen_at == file.last_scanned_at,
    )


@router.get("", response_model=list[IssueRead])
def list_issues(severity: str | None = None, type: str | None = None,
                status: str | None = None, root_id: int | None = None,
                q: str | None = None, only_new: bool = False,
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
    if only_new:
        # "nuovo" = visto in una sola scansione (first_seen == last_scanned).
        stmt = stmt.where(AudioFile.first_seen_at == AudioFile.last_scanned_at)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(AudioFile.path.ilike(like), AudioFile.artist.ilike(like),
                             AudioFile.title.ilike(like)))
    return [_to_read(i, f) for i, f in db.execute(stmt).all()]


@router.post("/{issue_id}/status", response_model=dict)
def set_status(issue_id: int, body: IssueStatusBody, db: Session = Depends(get_db)):
    if body.status not in _VALID:
        raise api_error(400, "issue_status_invalid", "Invalid status")
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise api_error(404, "issue_not_found", "Issue not found")
    if body.status == "accepted" and issue.suggested_fix_json is None:
        raise api_error(400, "issue_not_autofixable", "Issue is not auto-fixable")
    issue.status = body.status
    issue.updated_at = utcnow()
    db.commit()
    return {"id": issue.id, "status": issue.status}


@router.post("/bulk", response_model=dict)
def bulk(body: IssueBulkBody, db: Session = Depends(get_db)):
    if body.status not in _VALID:
        raise api_error(400, "issue_status_invalid", "Invalid status")
    stmt = select(Issue)
    if body.type:
        stmt = stmt.where(Issue.type == body.type)
    if body.severity:
        stmt = stmt.where(Issue.severity == body.severity)
    updated = 0
    for issue in db.scalars(stmt).all():
        # Le override si toccano in blocco solo se targetizzate per tipo, mai per
        # sola severità (così "ignora tutti gli info" non cancella le proposte).
        if issue.type == "provider_override" and body.type != "provider_override":
            continue
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
        raise api_error(404, "issue_not_found", "Issue not found")
    if issue.field not in _RETAGGABLE:
        raise api_error(400, "issue_field_not_editable", "Field can't be edited by hand")
    value = body.value.strip()
    if not value:
        raise api_error(400, "issue_value_empty", "Empty value")
    fix = {"field": issue.field, "action": "retag", "to": value}
    # Preserva i marcatori (source/confidence) del suggerimento esistente: così
    # accettando per-riga un provider_override non si perde il badge di confidenza.
    prev = issue.suggested_fix_json or {}
    for marker in ("source", "confidence"):
        if prev.get(marker) is not None:
            fix[marker] = prev[marker]
    issue.suggested_fix_json = fix
    issue.status = "accepted"
    issue.updated_at = utcnow()
    db.commit()
    file = db.get(AudioFile, issue.file_id)
    return _to_read(issue, file)


@router.post("/detect-ratings", response_model=dict)
def detect_ratings(db: Session = Depends(get_db)):
    """Rileva i file con un rating (stelline) embeddato e crea le issue
    stray_rating (svuotamento). Sincrono."""
    return ratings.detect_ratings(db)


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
            issue.suggested_fix_json = {"field": issue.field, "action": "retag",
                                        "to": value, "source": "ai"}
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
            issue.suggested_fix_json = {"field": "genre", "action": "retag",
                                        "to": value, "source": "ai"}
            issue.updated_at = utcnow()
            suggested += 1
        else:
            unresolved += 1
    db.commit()
    return {"configured": True, "files": len(todo),
            "suggested": suggested, "unresolved": unresolved}


_PROVIDER_TYPES = ("missing_required_tag", "missing_metadata", "dirty_genre")
_PROVIDER_FIELDS = ("artist", "title", "genre", "year", "label", "album")


@router.post("/provider-suggest", response_model=dict)
def provider_suggest(body: ProviderSuggestBody | None = None, db: Session = Depends(get_db)):
    """Riempie i suggested_fix delle issue aperte dai provider (MusicBrainz→
    Discogs), **fingerprint-first**: se il file non ha mbid e AcoustID è
    configurato, lo fingerprinta prima della lookup → match esatto e confidenza
    'high' invece del testuale (meno errori tipo compilation). Sincrono come
    /api/fingerprint.

    Tocca solo issue open (i tag puliti non hanno issue; i fix manuali sono
    accepted); riempie quando suggested_fix_json è None o non ha source ==
    'provider' (sovrascrive AI/legacy, idempotente sulle sue). Ogni proposta è
    marcata source='provider' + confidence ('high'|'text'). Una lookup per file.

    Se covers=True (default), per i file risolti in questa passata con
    has_cover=False cerca anche una copertina (CAA/Discogs, riusando la
    stessa lookup testuale: nessuna chiamata MB extra) e la mette in cache
    su disco, creando/aggiornando l'issue 'missing_cover'."""
    from app.integrations.discogs_meta import DiscogsMetaClient
    from app.integrations.musicbrainz import MusicBrainzProvider
    from app.services.fingerprint import fingerprint_one

    want_covers = (body or ProviderSuggestBody()).covers
    mb = MusicBrainzProvider(user_agent=settings.musicbrainz_user_agent)
    discogs = DiscogsMetaClient()
    caa = cover_art.CoverArtArchiveClient() if want_covers else None
    ac_client = None
    if acoustid.acoustid_configured() and acoustid.fpcalc_available():
        try:
            ac_client = acoustid.get_acoustid_client()
        except acoustid.AcoustIDError:
            ac_client = None

    rows = db.execute(
        select(Issue, AudioFile).join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.type.in_(_PROVIDER_TYPES),
               Issue.field.in_(_PROVIDER_FIELDS))
    ).all()
    todo = [(i, f) for i, f in rows
            if i.suggested_fix_json is None
            or i.suggested_fix_json.get("source") != "provider"]
    if not todo:
        return {"configured": True, "acoustid_available": ac_client is not None,
                "files": 0, "suggested": 0, "unresolved": 0, "fingerprinted": 0,
                "covers": 0}

    cache: dict[int, "text_providers.ResolvedText"] = {}
    files_by_id: dict[int, AudioFile] = {}
    fingerprinted = 0

    def _lookup(f: AudioFile):
        nonlocal fingerprinted
        files_by_id[f.id] = f
        if f.id not in cache:
            if not f.mbid and ac_client is not None and fingerprint_one(f, ac_client):
                fingerprinted += 1
            cache[f.id] = text_providers.resolve(f, mb=mb, discogs=discogs)
        return cache[f.id]

    suggested = unresolved = 0
    files_seen: set[int] = set()
    for issue, f in todo:
        files_seen.add(f.id)
        res = _lookup(f)
        pair = res.fields.get(issue.field)
        if pair is not None:
            value, conf = pair
            issue.suggested_fix_json = {"field": issue.field, "action": "retag",
                                        "to": str(value), "source": "provider",
                                        "confidence": conf}
            issue.updated_at = utcnow()
            suggested += 1
        else:
            unresolved += 1

    covers = 0
    if want_covers:
        for fid, res in cache.items():
            if cover_svc.fetch_cover(db, files_by_id[fid], res, caa=caa, discogs=discogs):
                covers += 1

    db.commit()
    return {"configured": True, "acoustid_available": ac_client is not None,
            "files": len(files_seen), "suggested": suggested,
            "unresolved": unresolved, "fingerprinted": fingerprinted, "covers": covers}


@router.get("/cover-thumb/{file_id}")
def cover_thumb(file_id: int):
    data = cover_cache.read_thumb(file_id)
    if data is None:
        raise api_error(404, "thumb_missing", "No thumbnail")
    return Response(content=data, media_type="image/jpeg")


@router.post("/provider-rescan", response_model=dict)
def provider_rescan_start(body: ProviderRescanBody | None = None):
    if scan_job.is_running() or apply_job.is_running():
        raise api_error(409, "scan_or_apply_running", "Scan or apply in progress")
    b = body or ProviderRescanBody()
    return provider_rescan_job.start_job(
        folder=b.folder, genre=b.genre, fields=b.fields,
        include_accepted=b.include_accepted, include_dismissed=b.include_dismissed,
        covers=b.covers, only_new=b.only_new)


@router.get("/provider-rescan/status", response_model=dict)
def provider_rescan_status():
    return provider_rescan_job.job_state()


@router.post("/provider-override/accept-high", response_model=dict)
def accept_high_overrides(db: Session = Depends(get_db)):
    rows = db.scalars(select(Issue).where(
        Issue.type == "provider_override", Issue.status == "open")).all()
    updated = 0
    for issue in rows:
        if (issue.suggested_fix_json or {}).get("confidence") == "high":
            issue.status = "accepted"
            issue.updated_at = utcnow()
            updated += 1
    db.commit()
    return {"updated": updated}
