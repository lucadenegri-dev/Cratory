"""Router LIBRARY: letture read-only per il frontend (statistiche + lista file).
Router sottile: query dirette, nessun servizio nuovo."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, DupGroup, Issue, ScanRoot
from app.schemas import LibraryStatsRead

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
