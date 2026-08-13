"""Conversione modelli ORM -> schemi Pydantic con campi derivati."""

from sqlalchemy.orm import Session

from app.models import Setlist, Track
from app.repositories import FileTags, file_tags_for_tracks
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


def track_out(track: Track, file_tags: FileTags | None = None) -> TrackOut:
    ft = file_tags or FileTags()
    return TrackOut(
        id=track.id,
        spotify_id=track.spotify_id,
        soundcloud_id=track.soundcloud_id,
        source_type=track.source_type,
        platform=track.platform,
        title=track.title,
        artist=track.artist,
        album=ft.album if ft.album is not None else track.album,
        genre=ft.genre if ft.genre is not None else track.genre,
        year=ft.year if ft.year is not None else track.year,
        duration_seconds=track.duration_seconds,
        bpm=track.bpm,
        camelot_key=track.camelot_key,
        energy=track.energy,
        label=ft.label if ft.label is not None else track.label,
        status=track.status or "imported",
        url=track.url,
        isrc=track.isrc,
        playlists=[TrackPlaylistRef(id=p.id, name=p.name) for p in track.playlists],
        added_at=track.added_at,
        spotify_url=_spotify_url(track),
        album_art_url=track.album_art_url,
        has_local_file=bool(track.has_local_file),
        local_path=track.local_path,
        local_format=track.local_format,
        local_bitrate=track.local_bitrate,
        archived=bool(track.archived),
        rating=track.rating,
        last_download_outcome=track.last_download_outcome,
        last_download_reason=track.last_download_reason,
        last_download_path=track.last_download_path,
        primary_file_id=track.primary_file_id,
        genre_from_file=ft.genre is not None,
        album_from_file=ft.album is not None,
        label_from_file=ft.label is not None,
        year_from_file=ft.year is not None,
    )


def track_detail_out(track: Track, file_tags: FileTags | None = None) -> TrackDetailOut:
    ft = file_tags or FileTags()
    return TrackDetailOut(**track_out(track, file_tags).model_dump(),
                          file_artist=ft.artist, file_title=ft.title)


def setlist_out(setlist: Setlist, lang: str = "it", db: Session | None = None) -> SetlistOut:
    # F10: classifichiamo ogni transizione dal brano precedente (deterministico,
    # ricalcolato in lettura dai dati delle due tracce: nessuna colonna in DB).
    # M6: genere/album/label/anno effettivi (tag file) anche nel dettaglio set,
    # non solo in Library — una sola query in piu' per l'intero set (`db` e'
    # opzionale: i chiamanti che non lo passano restano col fallback streaming,
    # com'era prima).
    ft_map = file_tags_for_tracks(db, [st.track_id for st in setlist.tracks]) if db is not None else {}
    # I4: la classificazione del reset (classify_transition) deve leggere lo
    # STESSO genere effettivo mostrato in `track` qui sotto, non lo streaming
    # grezzo: altrimenti un set con quel brano "Progressive House" solo sul file
    # può etichettare come reset una transizione che non lo è (o viceversa).
    # D4: derivata da `ft_map` (già una query in blocco, riga sopra) invece di
    # un secondo giro di query — stessa espressione di `_EFFECTIVE_TAGS["genre"]`
    # (tag file se presente, altrimenti lo streaming), calcolata qui in Python.
    genre_map = ({st.track_id: ft_map.get(st.track_id, FileTags()).genre or st.track.genre
                 for st in setlist.tracks} if db is not None else None)
    items = []
    prev = None
    for st in setlist.tracks:
        # score=transition_score persistito: evita di ricomputare score_transition
        # per ogni riga del set (None su set storici -> fallback interno).
        cls = (classify_transition(prev, st.track, lang, score=st.transition_score, genre_map=genre_map)
               if prev is not None else None)
        items.append(SetlistTrackOut(
            position=st.position,
            role=st.role,
            track=track_out(st.track, ft_map.get(st.track_id)),
            transition_score=st.transition_score,
            transition_reason=st.transition_reason,
            transition_note=st.transition_note,
            ai_reason=st.ai_reason,
            risk_level=st.risk_level,
            mood_tags=st.mood_tags or [],
            transition_class=cls.label if cls else None,
            transition_class_reason=cls.reason if cls else None,
            mix_tip=mixing_tip(prev, st.track, lang) if prev is not None else None,
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
        owned_only=bool(setlist.owned_only),
        validation=setlist.validation or {},
        curation=setlist.curation or {},
        mixing_overview=mixing_overview([st.track for st in setlist.tracks], lang),
        total_duration_seconds=total,
        created_at=setlist.created_at,
        tracks=items,
    )


def alternative_out(alt, file_tags: FileTags | None = None) -> AlternativeOut:
    return AlternativeOut(
        track=track_out(alt.track, file_tags),
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
