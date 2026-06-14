"""Query di accesso dati (layer repository)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import CuePoint, Playlist, Setlist, SetlistTrack, Track


def _apply_track_filters(  # noqa: PLR0913
    stmt,
    *,
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    source: str | None = None,
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
):
    if artist:
        stmt = stmt.where(Track.artist.ilike(f"%{artist}%"))
    if title:
        stmt = stmt.where(Track.title.ilike(f"%{title}%"))
    if album:
        stmt = stmt.where(Track.album.ilike(f"%{album}%"))
    if genre:
        stmt = stmt.where(Track.genre.ilike(f"%{genre}%"))
    if source:
        stmt = stmt.where(Track.source_type == source)
    if bpm_min is not None:
        stmt = stmt.where(Track.bpm >= bpm_min)
    if bpm_max is not None:
        stmt = stmt.where(Track.bpm <= bpm_max)
    if tonality:
        stmt = stmt.where(Track.tonality == tonality)
    if duration_min is not None:
        stmt = stmt.where(Track.duration_seconds >= duration_min)
    if duration_max is not None:
        stmt = stmt.where(Track.duration_seconds <= duration_max)
    if play_count_min is not None:
        stmt = stmt.where(Track.play_count >= play_count_min)
    if play_count_max is not None:
        stmt = stmt.where(Track.play_count <= play_count_max)
    if has_spotify is not None:
        stmt = stmt.where(Track.spotify_id.is_not(None) if has_spotify else Track.spotify_id.is_(None))
    if has_soundcloud is not None:
        stmt = stmt.where(Track.soundcloud_id.is_not(None) if has_soundcloud else Track.soundcloud_id.is_(None))
    if has_cues is not None:
        cue_exists = select(CuePoint.id).where(CuePoint.track_id == Track.id).exists()
        stmt = stmt.where(cue_exists if has_cues else ~cue_exists)
    if incomplete_metadata:
        stmt = stmt.where((Track.title.is_(None)) | (Track.artist.is_(None)))
    return stmt


def list_tracks(db: Session, *, limit: int = 100, offset: int = 0, **filters):
    base = select(Track).options(
        selectinload(Track.cue_points), selectinload(Track.beatgrid_points)
    )
    stmt = _apply_track_filters(base, **filters)
    total = db.scalar(select(func.count()).select_from(_apply_track_filters(select(Track.id), **filters).subquery()))
    rows = db.scalars(
        stmt.order_by(Track.artist.is_(None), Track.artist, Track.title).limit(limit).offset(offset)
    ).all()
    return total or 0, rows


def get_track(db: Session, track_id: int) -> Track | None:
    return db.scalar(
        select(Track)
        .options(selectinload(Track.cue_points), selectinload(Track.beatgrid_points))
        .where(Track.id == track_id)
    )


def all_playable_tracks(db: Session) -> list[Track]:
    """Tracce utilizzabili in un set: con BPM e durata sensata."""
    return list(db.scalars(
        select(Track)
        .options(selectinload(Track.cue_points), selectinload(Track.beatgrid_points))
        .where(Track.bpm.is_not(None))
    ).all())


def library_stats(db: Session) -> dict:
    tracks = db.scalars(select(Track).options(selectinload(Track.cue_points))).all()
    bpms = [t.bpm for t in tracks if t.bpm]
    by_source: dict[str, int] = {}
    key_distribution: dict[str, int] = {}
    for t in tracks:
        by_source[t.source_type] = by_source.get(t.source_type, 0) + 1
        if t.tonality:
            key_distribution[t.tonality] = key_distribution.get(t.tonality, 0) + 1
    return {
        "total_tracks": len(tracks),
        "by_source": by_source,
        "with_bpm": len(bpms),
        "with_tonality": sum(1 for t in tracks if t.tonality),
        "with_cues": sum(1 for t in tracks if t.cue_points),
        "missing_metadata": sum(1 for t in tracks if not t.title or not t.artist),
        "bpm_min": min(bpms) if bpms else None,
        "bpm_max": max(bpms) if bpms else None,
        "key_distribution": dict(sorted(key_distribution.items())),
    }


_SETLIST_TRACKS = selectinload(Setlist.tracks).selectinload(SetlistTrack.track)


def get_setlist(db: Session, setlist_id: int) -> Setlist | None:
    return db.scalar(
        select(Setlist).options(_SETLIST_TRACKS).where(Setlist.id == setlist_id)
    )


def list_setlists(db: Session) -> list[Setlist]:
    return list(db.scalars(
        select(Setlist).options(_SETLIST_TRACKS).order_by(Setlist.created_at.desc())
    ).all())


# --- Playlist importate (nuovo flusso) ---------------------------------------


def list_playlists(db: Session) -> list[Playlist]:
    return list(db.scalars(select(Playlist).order_by(Playlist.imported_at.desc())).all())


def get_playlist(db: Session, playlist_id: int) -> Playlist | None:
    return db.scalar(select(Playlist).where(Playlist.id == playlist_id))


def tracks_for_playlist(db: Session, playlist_id: int) -> list[Track]:
    return list(db.scalars(
        select(Track)
        .options(selectinload(Track.cue_points), selectinload(Track.beatgrid_points))
        .where(Track.playlist_id == playlist_id)
        .order_by(Track.added_at.is_(None), Track.added_at)
    ).all())
