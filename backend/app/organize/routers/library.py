"""Router LIBRARY: letture read-only per il frontend (statistiche + lista file).
Router sottile: query dirette, nessun servizio nuovo."""

import os
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.organize.core.http_errors import api_error
from app.db import get_db
from app.organize.models import AudioFile, DupGroup, DupMember, Issue
from app.organize.schemas import FileRow, LibraryFacets, LibraryStatsRead
from app.organize.services import cover_cache, thumbs
from app.organize.services.roots import radici

router = APIRouter(prefix="/api/organize", tags=["library"])


@router.get("/library/stats", response_model=LibraryStatsRead)
def library_stats(db: Session = Depends(get_db)):
    files_total = db.scalar(
        select(func.count()).select_from(AudioFile).where(AudioFile.status == "present")
    ) or 0
    by_ext = {
        ext: n
        for ext, n in db.execute(
            select(AudioFile.ext, func.count())
            .where(AudioFile.status == "present")
            .group_by(AudioFile.ext)
        ).all()
    }
    issues_by_severity = {
        sev: n
        for sev, n in db.execute(
            select(Issue.severity, func.count())
            .where(Issue.status == "open")
            .group_by(Issue.severity)
        ).all()
    }
    dup_groups = db.scalar(
        select(func.count()).select_from(DupGroup).where(DupGroup.dismissed.is_(False))
    ) or 0
    # Le "sorgenti" non sono più righe di tabella: sono le cartelle configurate.
    sources = len(radici(db))
    return LibraryStatsRead(
        files_total=files_total,
        by_ext=by_ext,
        issues_by_severity=issues_by_severity,
        dup_groups=dup_groups,
        sources=sources,
    )


_SEV_RANK = {"error": 3, "warning": 2, "info": 1}
_RANK_SEV = {3: "error", 2: "warning", 1: "info"}
_SORT_COLS = {
    "path": AudioFile.path,
    "artist": AudioFile.artist,
    "title": AudioFile.title,
    "ext": AudioFile.ext,
    "bitrate": AudioFile.bitrate,
    "duration": AudioFile.duration_s,
}


def _file_row(f: AudioFile, n_issues: int, rank: int, dup_n: int, cover_n: int) -> FileRow:
    return FileRow(
        id=f.id, location=f.location, path=f.path, ext=f.ext,
        artist=f.artist, title=f.title, album=f.album, album_artist=f.album_artist,
        genre=f.genre, year=f.year, label=f.label, track_no=f.track_no,
        comment=f.comment, bitrate=f.bitrate, duration_s=f.duration_s,
        status=f.status, issue_count=n_issues,
        worst_severity=_RANK_SEV.get(rank), in_dup_group=bool(dup_n),
        cover_source="embedded" if f.has_cover else ("provider" if cover_n else None),
    )


def build_file_row(db: Session, f: AudioFile) -> FileRow:
    """FileRow di un singolo file (per l'endpoint di modifica manuale): stesse
    quattro metriche di `list_files`, ma calcolate per un solo `f`."""
    n_issues = db.scalar(select(func.count()).select_from(Issue).where(
        Issue.file_id == f.id, Issue.status == "open")) or 0
    rank = db.scalar(select(func.max(case(_SEV_RANK, value=Issue.severity, else_=0)))
                     .select_from(Issue).where(Issue.file_id == f.id,
                                               Issue.status == "open")) or 0
    dup_n = db.scalar(select(func.count()).select_from(DupMember)
                      .join(DupGroup, DupGroup.id == DupMember.group_id)
                      .where(DupMember.file_id == f.id,
                             DupGroup.dismissed.is_(False))) or 0
    cover_n = db.scalar(select(func.count()).select_from(Issue).where(
        Issue.file_id == f.id, Issue.type == "missing_cover",
        Issue.status == "open")) or 0
    return _file_row(f, n_issues, rank, dup_n, cover_n)


@router.get("/library/facets", response_model=LibraryFacets)
def library_facets(db: Session = Depends(get_db)):
    """Valori distinti (solo file `present`) per i filtri per-tag di FILES."""
    def distinct(col):
        return [
            v for (v,) in db.execute(
                select(col)
                .where(AudioFile.status == "present", col.is_not(None), col != "")
                .distinct().order_by(col)
            ).all()
        ]

    return LibraryFacets(
        genre=distinct(AudioFile.genre),
        artist=distinct(AudioFile.artist),
        album=distinct(AudioFile.album),
        label=distinct(AudioFile.label),
        ext=distinct(AudioFile.ext),
        year=distinct(AudioFile.year),
    )


@router.get("/files", response_model=list[FileRow])
def list_files(
    db: Session = Depends(get_db),
    location: Literal["inbox", "library"] | None = None,
    status: str = "present",
    has_issues: bool | None = None,
    q: str | None = None,
    genre: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    label: str | None = None,
    ext: str | None = None,
    year: int | None = None,
    sort: str = "path",
    dir: str = "asc",
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    issue_count = (
        select(func.count())
        .select_from(Issue)
        .where(Issue.file_id == AudioFile.id, Issue.status == "open")
        .scalar_subquery()
    )
    worst_rank = (
        select(func.max(case(_SEV_RANK, value=Issue.severity, else_=0)))
        .select_from(Issue)
        .where(Issue.file_id == AudioFile.id, Issue.status == "open")
        .scalar_subquery()
    )
    in_dup = (
        select(func.count())
        .select_from(DupMember)
        .join(DupGroup, DupGroup.id == DupMember.group_id)
        .where(DupMember.file_id == AudioFile.id, DupGroup.dismissed.is_(False))
        .scalar_subquery()
    )
    cover_proposal = (
        select(func.count())
        .select_from(Issue)
        .where(Issue.file_id == AudioFile.id, Issue.type == "missing_cover",
               Issue.status == "open")
        .scalar_subquery()
    )

    stmt = select(AudioFile, issue_count, worst_rank, in_dup, cover_proposal).where(
        AudioFile.status == status
    )
    if location is not None:
        stmt = stmt.where(AudioFile.location == location)
    if has_issues is True:
        stmt = stmt.where(issue_count > 0)
    elif has_issues is False:
        stmt = stmt.where(issue_count == 0)
    for col, val in ((AudioFile.genre, genre), (AudioFile.artist, artist),
                     (AudioFile.album, album), (AudioFile.label, label),
                     (AudioFile.ext, ext), (AudioFile.year, year)):
        if val is not None and val != "":
            stmt = stmt.where(col == val)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(AudioFile.path.ilike(like), AudioFile.artist.ilike(like),
                AudioFile.title.ilike(like))
        )
    col = _SORT_COLS.get(sort, AudioFile.path)
    ordering = col.desc() if dir == "desc" else col.asc()
    # id come tiebreaker: ordinamento deterministico e paginazione stabile
    stmt = stmt.order_by(ordering, AudioFile.id).limit(limit).offset(offset)

    rows = []
    for f, n_issues, rank, dup_n, cover_n in db.execute(stmt).all():
        rows.append(_file_row(f, n_issues or 0, rank or 0, dup_n, cover_n))
    return rows


@router.get("/files/{file_id}/thumb")
def file_thumb(file_id: int, request: Request, db: Session = Depends(get_db)):
    """Miniatura della traccia: l'artwork embeddato se c'è, altrimenti la
    copertina proposta dai provider già in cache. 404 se non c'è nulla — il
    frontend disegna il placeholder e non ritenta."""
    f = db.get(AudioFile, file_id)
    if f is None:
        raise api_error(404, "file_not_found", "File not found")

    # ETag sull'mtime del *file audio*: un apply che riscrive i tag invalida
    # anche la copia nel browser, non solo quella su disco.
    try:
        stamp = str(os.path.getmtime(f.path))
    except OSError:
        stamp = "0"
    if not f.has_cover:
        # Fallback = cover_cache/{id}.jpg: "importa metadati dal provider" può
        # sovrascrivere la proposta senza toccare l'audio, quindi il suo mtime
        # deve entrare nello stamp o un client con l'ETag vecchio riceve un
        # 304 e resta con l'immagine superata.
        try:
            stamp += f"-{os.path.getmtime(cover_cache.thumb_path(file_id))}"
        except OSError:
            pass
    etag = f'W/"{file_id}-{stamp}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})

    data = thumbs.get_thumb(file_id, f.path) if f.has_cover else None
    if data is None:
        data = cover_cache.read_thumb(file_id)
    if data is None:
        # Niente ETag da validare qui: ISSUES/DUPLICATES/PLAN non passano
        # cover_source, quindi ogni riga senza copertina rifà questa richiesta
        # a ogni mount. Un max-age corto la smorza senza rischiare di
        # nascondere per troppo tempo una copertina appena importata.
        raise api_error(404, "thumb_missing", "No thumbnail",
                        headers={"Cache-Control": "max-age=60"})
    return Response(content=data, media_type="image/jpeg",
                    headers={"ETag": etag, "Cache-Control": "no-cache"})
