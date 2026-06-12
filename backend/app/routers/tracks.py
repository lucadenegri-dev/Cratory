from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories import get_track, library_stats, list_tracks
from app.schemas import LibraryStatsOut, TrackDetailOut, TrackListOut
from app.serializers import track_detail_out, track_out

router = APIRouter(prefix="/api", tags=["tracks"])


@router.get("/tracks", response_model=TrackListOut)
def get_tracks(  # noqa: PLR0913
    db: Session = Depends(get_db),
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    source: str | None = Query(default=None, pattern="^(spotify|soundcloud|local)$"),
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    tonality: str | None = None,
    duration_min: int | None = None,
    duration_max: int | None = None,
    play_count_min: int | None = None,
    play_count_max: int | None = None,
    has_spotify: bool | None = None,
    has_soundcloud: bool | None = None,
    has_cues: bool | None = None,
    incomplete_metadata: bool | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    total, rows = list_tracks(
        db,
        limit=limit, offset=offset,
        artist=artist, title=title, album=album, genre=genre, source=source,
        bpm_min=bpm_min, bpm_max=bpm_max, tonality=tonality,
        duration_min=duration_min, duration_max=duration_max,
        play_count_min=play_count_min, play_count_max=play_count_max,
        has_spotify=has_spotify, has_soundcloud=has_soundcloud,
        has_cues=has_cues, incomplete_metadata=incomplete_metadata,
    )
    return TrackListOut(total=total, items=[track_out(t) for t in rows])


@router.get("/tracks/{track_id}", response_model=TrackDetailOut)
def get_track_detail(track_id: int, db: Session = Depends(get_db)):
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata")
    return track_detail_out(track)


@router.get("/stats", response_model=LibraryStatsOut)
def get_stats(db: Session = Depends(get_db)):
    return library_stats(db)
