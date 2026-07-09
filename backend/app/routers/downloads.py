"""HTTP per l'acquisizione file via slskd. Nessuna logica di business qui."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import SessionLocal, get_db
from app.integrations.slskd import (
    SlskdError, SlskdFile, get_slskd_client, slskd_configured,
)
from app.repositories import get_track, tracks_download_pending
from app.services import soulseek_download_job as job
from app.schemas import TrackOut
from app.serializers import track_out
from app.services.soulseek_select import rank_candidates, search_candidates
from app.services.download_review import (
    NoReviewFileError, discard_downloaded, keep_downloaded, review_detail,
)
from app.services.auto_link import auto_link_preview
from sqlalchemy.orm import Session

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
    # Durata attesa (dalla Track): premia la versione giusta nel ranking.
    duration_seconds: int | None = None


class TrackDownloadIn(BaseModel):
    track_id: int
    candidate: CandidateOut


class TrackAutopickIn(BaseModel):
    track_id: int


class SearchIn(BaseModel):
    query: str


class ManualDownloadIn(BaseModel):
    candidate: CandidateOut


class ReviewActionIn(BaseModel):
    track_id: int


class AutoLinkHit(BaseModel):
    path: str
    name: str
    format: str | None = None
    size: int | None = None
    source: str


class AutoLinkProposal(BaseModel):
    track_id: int
    label: str
    artist: str | None = None
    title: str | None = None
    hit: AutoLinkHit | None = None


def _candidate_out(c) -> CandidateOut:
    return CandidateOut(
        username=c.file.username, filename=c.file.filename, size=c.file.size,
        bitrate=c.file.bitrate, length=c.file.length, format=c.file.extension or None,
        name_score=c.name_score, quality_tier=c.quality_tier, confidence=c.confidence,
    )


def _slskd_file(c: CandidateOut) -> SlskdFile:
    return SlskdFile(username=c.username, filename=c.filename, size=c.size,
                     bitrate=c.bitrate, length=c.length, has_free_slot=True,
                     queue_length=None)


@router.get("/pending", response_model=list[TrackOut])
def download_pending(db: Session = Depends(get_db)):
    """Le "da sistemare": wishlist con esito download da rivedere/non trovata/fallita.

    Persistite sulla Track: sopravvivono a job, sessioni e riavvii.
    """
    return [track_out(t) for t in tracks_download_pending(db)]


@router.delete("/pending/{track_id}", response_model=TrackOut)
def ignore_pending(track_id: int, db: Session = Depends(get_db)):
    """Ignora una "da sistemare": azzera l'esito e la traccia esce dall'archivio."""
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata.")
    track.last_download_outcome = None
    track.last_download_reason = None
    db.commit()
    db.refresh(track)
    return track_out(track)


@router.post("/retry-pending", status_code=202)
def retry_pending():
    """Ritenta l'auto-pick su tutte le "da sistemare". 409 se un job e' in corso."""
    if not slskd_configured():
        raise HTTPException(status_code=409, detail="slskd non configurato.")
    if job.is_running():
        raise HTTPException(status_code=409, detail="Un download e' gia' in corso.")
    return job.start_retry_job()


@router.get("/status")
def status():
    return {"available": slskd_configured(), **job.job_state()}


@router.post("/candidates", response_model=list[CandidateOut])
def candidates(req: CandidatesIn):
    if not slskd_configured():
        raise HTTPException(status_code=409, detail="slskd non configurato (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    try:
        # Cascata di varianti di query: la letterale spesso esclude file validi.
        ranked = search_candidates(get_slskd_client(), artist=req.artist,
                                   title=req.title,
                                   expected_duration=req.duration_seconds)
    except SlskdError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [_candidate_out(c) for c in ranked]


@router.post("/playlist/{playlist_id}", status_code=202)
def download_playlist(playlist_id: int):
    if not slskd_configured():
        raise HTTPException(status_code=409, detail="slskd non configurato.")
    if job.is_running():
        raise HTTPException(status_code=409, detail="Un download e' gia' in corso.")
    return {"available": True, **job.start_playlist_job(playlist_id)}


@router.post("/track", status_code=202)
def download_track(req: TrackDownloadIn):
    if not slskd_configured():
        raise HTTPException(status_code=409, detail="slskd non configurato.")
    if job.is_running():
        raise HTTPException(status_code=409, detail="Un download e' gia' in corso.")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise HTTPException(status_code=404, detail="Traccia non trovata.")
    finally:
        db.close()
    return {"available": True, **job.start_track_job(req.track_id, _slskd_file(req.candidate))}


@router.post("/track/auto", status_code=202)
def download_track_auto(req: TrackAutopickIn):
    """Download immediato in auto-pick di una singola traccia (es. 'Scarica
    ora' dalla tracklist di un lead Discovery): nessun candidato scelto
    dall'utente, stessa cascata di ricerca del job playlist."""
    if not slskd_configured():
        raise HTTPException(status_code=409, detail="slskd non configurato.")
    if job.is_running():
        raise HTTPException(status_code=409, detail="Un download e' gia' in corso.")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise HTTPException(status_code=404, detail="Traccia non trovata.")
    finally:
        db.close()
    return {"available": True, **job.start_track_autopick_job(req.track_id)}


@router.post("/search", response_model=list[CandidateOut])
def search(req: SearchIn):
    if not slskd_configured():
        raise HTTPException(status_code=409, detail="slskd non configurato (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    query = req.query.strip()
    if not query:
        return []
    try:
        files = get_slskd_client().search(query, "")
    except SlskdError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # Ricerca libera: slskd ha gia' filtrato per query, l'utente sceglie a vista.
    ranked = rank_candidates(files, artist="", title=query, min_name_score=0.0)
    return [_candidate_out(c) for c in ranked]


@router.post("/manual", status_code=202)
def download_manual(req: ManualDownloadIn):
    if not slskd_configured():
        raise HTTPException(status_code=409, detail="slskd non configurato.")
    if job.is_running():
        raise HTTPException(status_code=409, detail="Un download e' gia' in corso.")
    return {"available": True, **job.start_manual_job(_slskd_file(req.candidate))}


@router.get("/review/{track_id}")
def review(track_id: int, db: Session = Depends(get_db)):
    """Confronto atteso-vs-scaricato per un needs_review-per-durata."""
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata.")
    return review_detail(db, track)


@router.post("/keep-review", response_model=TrackOut)
def keep_review(req: ReviewActionIn, db: Session = Depends(get_db)):
    """Tieni il file dubbio già scaricato: lo aggancia e svuota l'esito."""
    track = get_track(db, req.track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata.")
    try:
        track = keep_downloaded(db, track)
    except NoReviewFileError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return track_out(track)


@router.post("/discard-review", response_model=TrackOut)
def discard_review(req: ReviewActionIn, db: Session = Depends(get_db)):
    """Scarta il file dubbio: lo elimina dall'inbox e sgancia la traccia."""
    track = get_track(db, req.track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata.")
    return track_out(discard_downloaded(db, track))


@router.get("/auto-link", response_model=list[AutoLinkProposal])
def auto_link(db: Session = Depends(get_db)):
    """Proposte di collegamento file-locale per tutte le tracce da sistemare.

    Sola lettura: non collega nulla, restituisce (traccia, miglior match locale).
    Il collegamento vero passa per POST /api/tracks/{id}/link-file dopo la conferma.
    """
    return auto_link_preview(db)
