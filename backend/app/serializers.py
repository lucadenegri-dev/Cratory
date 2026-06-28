"""Conversione modelli ORM -> schemi Pydantic con campi derivati."""

from app.models import Setlist, Track
from app.schemas import (
    AlternativeOut,
    SetlistOut,
    SetlistSummaryOut,
    SetlistTrackOut,
    TrackDetailOut,
    TrackOut,
    TrackPlaylistRef,
)
from app.services.scoring import classify_transition, mixing_overview, mixing_tip


def _spotify_url(track: Track) -> str | None:
    return f"https://open.spotify.com/track/{track.spotify_id}" if track.spotify_id else None


def track_out(track: Track) -> TrackOut:
    return TrackOut(
        id=track.id,
        spotify_id=track.spotify_id,
        soundcloud_id=track.soundcloud_id,
        source_type=track.source_type,
        platform=track.platform,
        title=track.title,
        artist=track.artist,
        album=track.album,
        genre=track.genre,
        genre_secondary=track.genre_secondary,
        year=track.year,
        duration_seconds=track.duration_seconds,
        bpm=track.bpm,
        camelot_key=track.camelot_key,
        mood=track.mood,
        energy=track.energy,
        danceability=track.danceability,
        vocalness=track.vocalness,
        label=track.label,
        status=track.status or "imported",
        url=track.url,
        isrc=track.isrc,
        playlists=[TrackPlaylistRef(id=p.id, name=p.name) for p in track.playlists],
        added_at=track.added_at,
        spotify_url=_spotify_url(track),
        album_art_url=track.album_art_url,
        enriched=track.enriched_at is not None,
        enrichment_source=track.enrichment_source,
        enrichment_confidence=track.enrichment_confidence,
    )


def track_detail_out(track: Track) -> TrackDetailOut:
    return TrackDetailOut(**track_out(track).model_dump())


def setlist_out(setlist: Setlist) -> SetlistOut:
    # F10: classifichiamo ogni transizione dal brano precedente (deterministico,
    # ricalcolato in lettura dai dati delle due tracce: nessuna colonna in DB).
    items = []
    prev = None
    for st in setlist.tracks:
        cls = classify_transition(prev, st.track) if prev is not None else None
        items.append(SetlistTrackOut(
            position=st.position,
            role=st.role,
            track=track_out(st.track),
            transition_score=st.transition_score,
            transition_reason=st.transition_reason,
            transition_note=st.transition_note,
            ai_reason=st.ai_reason,
            risk_level=st.risk_level,
            transition_class=cls.label if cls else None,
            transition_class_label=cls.label_it if cls else None,
            transition_class_reason=cls.reason if cls else None,
            mix_tip=mixing_tip(prev, st.track) if prev is not None else None,
        ))
        prev = st.track
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
        generated_by=setlist.generated_by or "algorithmic",
        validation=setlist.validation or {},
        mixing_overview=mixing_overview([st.track for st in setlist.tracks]),
        total_duration_seconds=total,
        created_at=setlist.created_at,
        tracks=items,
    )


def alternative_out(alt) -> AlternativeOut:
    return AlternativeOut(
        track=track_out(alt.track),
        score_prev=alt.score_prev,
        score_next=alt.score_next,
        reason=alt.reason,
        risk_level=alt.risk_level,
    )


def setlist_summary_out(setlist: Setlist) -> SetlistSummaryOut:
    return SetlistSummaryOut(
        id=setlist.id,
        name=setlist.name,
        strategy=setlist.strategy,
        target_duration_minutes=setlist.target_duration_minutes,
        track_count=len(setlist.tracks),
        total_duration_seconds=sum(st.track.duration_seconds or 0 for st in setlist.tracks),
        generated_by=setlist.generated_by or "algorithmic",
        created_at=setlist.created_at,
    )
