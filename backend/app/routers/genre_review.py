"""Router del job 'Revisione generi AI': start/status/preview. Sottile."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.schemas import GenreReviewBody
from app.services import ai_tags, apply_job, genre_review, genre_review_job, scan_job

router = APIRouter(prefix="/api/genre-review", tags=["genre-review"])


@router.post("", response_model=dict)
def genre_review_start(body: GenreReviewBody | None = None):
    if not ai_tags.is_configured():
        # Forma completa dello stato job (come GET /status) + configured: False,
        # cosi' il client riceve sempre la shape dichiarata da GenreReviewJobState.
        return {**genre_review_job.job_state(), "configured": False}
    if scan_job.is_running() or apply_job.is_running():
        raise api_error(409, "scan_or_apply_running", "Scan or apply in progress")
    b = body or GenreReviewBody()
    return genre_review_job.start_job(folder=b.folder, genre=b.genre, redo=b.redo)


@router.get("/status", response_model=dict)
def genre_review_status():
    return genre_review_job.job_state()


@router.get("/preview", response_model=dict)
def genre_review_preview(redo: bool = False, folder: str | None = None,
                         genre: str | None = None,
                         db: Session = Depends(get_db)):
    return {"configured": ai_tags.is_configured(),
            "files": genre_review.count_candidates(
                db, folder=folder, genre=genre, redo=redo)}
