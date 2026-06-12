from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Track
from app.repositories import all_playable_tracks, get_track
from app.schemas import TransitionCandidateOut, TransitionScoreOut, TransitionScoreRequest
from app.serializers import track_out
from app.services.scoring import score_transition

router = APIRouter(prefix="/api/transitions", tags=["transitions"])


def _ranked(db: Session, track_id: int, *, incoming: bool, limit: int) -> list[TransitionCandidateOut]:
    anchor = get_track(db, track_id)
    if anchor is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata")
    results: list[tuple[int, Track, TransitionScoreOut]] = []
    for other in all_playable_tracks(db):
        if other.id == anchor.id:
            continue
        ts = (
            score_transition(other, anchor) if incoming
            else score_transition(anchor, other)
        )
        results.append((
            ts.score, other,
            TransitionScoreOut(score=ts.score, technical_reasons=ts.technical_reasons, warnings=ts.warnings),
        ))
    results.sort(key=lambda item: item[0], reverse=True)
    return [TransitionCandidateOut(track=track_out(t), score=s) for _, t, s in results[:limit]]


@router.get("/after/{track_id}", response_model=list[TransitionCandidateOut])
def transitions_after(track_id: int, limit: int = Query(default=20, le=100), db: Session = Depends(get_db)):
    """Cosa posso mettere dopo questa traccia."""
    return _ranked(db, track_id, incoming=False, limit=limit)


@router.get("/before/{track_id}", response_model=list[TransitionCandidateOut])
def transitions_before(track_id: int, limit: int = Query(default=20, le=100), db: Session = Depends(get_db)):
    """Cosa posso mettere prima di questa traccia."""
    return _ranked(db, track_id, incoming=True, limit=limit)


@router.post("/score", response_model=TransitionScoreOut)
def score(req: TransitionScoreRequest, db: Session = Depends(get_db)):
    from_track = get_track(db, req.from_track_id)
    to_track = get_track(db, req.to_track_id)
    if from_track is None or to_track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata")
    ts = score_transition(from_track, to_track)
    return TransitionScoreOut(score=ts.score, technical_reasons=ts.technical_reasons, warnings=ts.warnings)
