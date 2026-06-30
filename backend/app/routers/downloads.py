"""HTTP per l'acquisizione file via slskd. Nessuna logica di business qui."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import SessionLocal
from app.integrations.slskd import (
    SlskdError, SlskdFile, get_slskd_client, slskd_configured,
)
from app.repositories import get_track
from app.services import soulseek_download_job as job
from app.services.soulseek_select import rank_candidates

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


class CandidateOut(BaseModel):
    username: str
    filename: str
    size: int | None = None
    bitrate: int | None = None
    length: int | None = None
    format: str | None = None
    name_score: float = 0.0
    quality_tier: int = 0
    confidence: float = 0.0


class CandidatesIn(BaseModel):
    artist: str
    title: str


class TrackDownloadIn(BaseModel):
    track_id: int
    candidate: CandidateOut


def _candidate_out(c) -> CandidateOut:
    return CandidateOut(
        username=c.file.username, filename=c.file.filename, size=c.file.size,
        bitrate=c.file.bitrate, length=c.file.length, format=c.file.extension or None,
        name_score=c.name_score, quality_tier=c.quality_tier, confidence=c.confidence,
    )


@router.get("/status")
def status():
    return {"available": slskd_configured(), **job.job_state()}


@router.post("/candidates", response_model=list[CandidateOut])
def candidates(req: CandidatesIn):
    if not slskd_configured():
        raise HTTPException(409, "slskd non configurato (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    try:
        files = get_slskd_client().search(req.artist, req.title)
    except SlskdError as exc:
        raise HTTPException(502, str(exc)) from exc
    ranked = rank_candidates(files, artist=req.artist, title=req.title)
    return [_candidate_out(c) for c in ranked]


@router.post("/playlist/{playlist_id}", status_code=202)
def download_playlist(playlist_id: int):
    if not slskd_configured():
        raise HTTPException(409, "slskd non configurato.")
    if job.is_running():
        raise HTTPException(409, "Un download e' gia' in corso.")
    return job.start_playlist_job(playlist_id)


@router.post("/track", status_code=202)
def download_track(req: TrackDownloadIn):
    if not slskd_configured():
        raise HTTPException(409, "slskd non configurato.")
    if job.is_running():
        raise HTTPException(409, "Un download e' gia' in corso.")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise HTTPException(404, "Traccia non trovata.")
    finally:
        db.close()
    c = req.candidate
    file = SlskdFile(username=c.username, filename=c.filename, size=c.size,
                     bitrate=c.bitrate, length=c.length, has_free_slot=True,
                     queue_length=None)
    return job.start_track_job(req.track_id, file)
