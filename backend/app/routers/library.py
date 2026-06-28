"""Router LIBRARY: letture read-only per il frontend (statistiche + lista file).
Router sottile: query dirette, nessun servizio nuovo."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, DupGroup, DupMember, Issue, ScanRoot
from app.schemas import FileRow, LibraryStatsRead

router = APIRouter(prefix="/api", tags=["library"])


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
    sources = db.scalar(select(func.count()).select_from(ScanRoot)) or 0
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
    "bitrate": AudioFile.bitrate,
    "duration": AudioFile.duration_s,
}


@router.get("/files", response_model=list[FileRow])
def list_files(
    db: Session = Depends(get_db),
    root_id: int | None = None,
    status: str = "present",
    has_issues: bool | None = None,
    q: str | None = None,
    sort: str = "path",
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

    stmt = select(AudioFile, issue_count, worst_rank, in_dup).where(
        AudioFile.status == status
    )
    if root_id is not None:
        stmt = stmt.where(AudioFile.root_id == root_id)
    if has_issues is True:
        stmt = stmt.where(issue_count > 0)
    elif has_issues is False:
        stmt = stmt.where(issue_count == 0)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(AudioFile.path.ilike(like), AudioFile.artist.ilike(like),
                AudioFile.title.ilike(like))
        )
    stmt = stmt.order_by(_SORT_COLS.get(sort, AudioFile.path)).limit(limit).offset(offset)

    rows = []
    for f, n_issues, rank, dup_n in db.execute(stmt).all():
        rows.append(FileRow(
            id=f.id, root_id=f.root_id, path=f.path, ext=f.ext,
            artist=f.artist, title=f.title, bitrate=f.bitrate, duration_s=f.duration_s,
            status=f.status, issue_count=n_issues or 0,
            worst_severity=_RANK_SEV.get(rank or 0), in_dup_group=bool(dup_n),
        ))
    return rows
