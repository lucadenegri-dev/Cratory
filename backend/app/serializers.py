"""Conversione modelli ORM -> schemi Pydantic con campi derivati."""

from app.models import Setlist, Track
from app.schemas import (
    CuePointOut,
    SetlistOut,
    SetlistSummaryOut,
    SetlistTrackOut,
    TrackDetailOut,
    TrackOut,
)


def _spotify_url(track: Track) -> str | None:
    return f"https://open.spotify.com/track/{track.spotify_id}" if track.spotify_id else None


def track_out(track: Track) -> TrackOut:
    return TrackOut(
        id=track.id,
        rekordbox_track_id=track.rekordbox_track_id,
        spotify_id=track.spotify_id,
        soundcloud_id=track.soundcloud_id,
        source_type=track.source_type,
        title=track.title,
        artist=track.artist,
        album=track.album,
        genre=track.genre,
        year=track.year,
        duration_seconds=track.duration_seconds,
        bpm=track.bpm,
        tonality=track.tonality,
        play_count=track.play_count,
        rating=track.rating,
        date_added=track.date_added,
        cue_count=len(track.cue_points),
        has_beatgrid=bool(track.beatgrid_points),
        spotify_url=_spotify_url(track),
    )


def track_detail_out(track: Track) -> TrackDetailOut:
    base = track_out(track).model_dump()
    return TrackDetailOut(
        **base,
        comments=track.comments,
        location=track.location,
        cue_points=[CuePointOut.model_validate(c) for c in track.cue_points],
        beatgrid_bpms=sorted({p.bpm for p in track.beatgrid_points}),
    )


def setlist_out(setlist: Setlist) -> SetlistOut:
    items = [
        SetlistTrackOut(
            position=st.position,
            track=track_out(st.track),
            transition_score=st.transition_score,
            transition_reason=st.transition_reason,
            ai_reason=st.ai_reason,
            risk_level=st.risk_level,
        )
        for st in setlist.tracks
    ]
    total = sum(st.track.duration_seconds or 0 for st in setlist.tracks)
    return SetlistOut(
        id=setlist.id,
        name=setlist.name,
        target_duration_minutes=setlist.target_duration_minutes,
        start_bpm=setlist.start_bpm,
        end_bpm=setlist.end_bpm,
        strategy=setlist.strategy,
        prompt=setlist.prompt,
        global_explanation=setlist.global_explanation,
        total_duration_seconds=total,
        created_at=setlist.created_at,
        tracks=items,
    )


def setlist_summary_out(setlist: Setlist) -> SetlistSummaryOut:
    return SetlistSummaryOut(
        id=setlist.id,
        name=setlist.name,
        strategy=setlist.strategy,
        target_duration_minutes=setlist.target_duration_minutes,
        track_count=len(setlist.tracks),
        created_at=setlist.created_at,
    )
