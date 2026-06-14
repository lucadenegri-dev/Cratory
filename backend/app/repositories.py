"""Query di accesso dati (layer repository)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Playlist, Setlist, SetlistTrack, Track


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
    key: str | None = None,
    duration_min: int | None = None,
    duration_max: int | None = None,
    has_spotify: bool | None = None,
    has_soundcloud: bool | None = None,
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
    if key:
        stmt = stmt.where(Track.camelot_key == key)
    if duration_min is not None:
        stmt = stmt.where(Track.duration_seconds >= duration_min)
    if duration_max is not None:
        stmt = stmt.where(Track.duration_seconds <= duration_max)
    if has_spotify is not None:
        stmt = stmt.where(Track.spotify_id.is_not(None) if has_spotify else Track.spotify_id.is_(None))
    if has_soundcloud is not None:
        stmt = stmt.where(Track.soundcloud_id.is_not(None) if has_soundcloud else Track.soundcloud_id.is_(None))
    if incomplete_metadata:
        stmt = stmt.where((Track.title.is_(None)) | (Track.artist.is_(None)))
    return stmt


def list_tracks(db: Session, *, limit: int = 100, offset: int = 0, **filters):
    stmt = _apply_track_filters(select(Track), **filters)
    total = db.scalar(select(func.count()).select_from(_apply_track_filters(select(Track.id), **filters).subquery()))
    rows = db.scalars(
        stmt.order_by(Track.artist.is_(None), Track.artist, Track.title).limit(limit).offset(offset)
    ).all()
    return total or 0, rows


def get_track(db: Session, track_id: int) -> Track | None:
    return db.scalar(select(Track).where(Track.id == track_id))


def all_playable_tracks(db: Session) -> list[Track]:
    """Tracce utilizzabili in un set: con BPM e durata sensata."""
    return list(db.scalars(select(Track).where(Track.bpm.is_not(None))).all())


def library_stats(db: Session) -> dict:
    tracks = db.scalars(select(Track)).all()
    bpms = [t.bpm for t in tracks if t.bpm]
    by_source: dict[str, int] = {}
    key_distribution: dict[str, int] = {}
    for t in tracks:
        by_source[t.source_type] = by_source.get(t.source_type, 0) + 1
        if t.camelot_key:
            key_distribution[t.camelot_key] = key_distribution.get(t.camelot_key, 0) + 1
    return {
        "total_tracks": len(tracks),
        "playlists": db.scalar(select(func.count()).select_from(Playlist)) or 0,
        "by_source": by_source,
        "with_bpm": len(bpms),
        "with_key": sum(1 for t in tracks if t.camelot_key),
        "with_features": sum(1 for t in tracks if t.mood or t.energy is not None),
        "ready_for_set": sum(1 for t in tracks if t.status == "ready_for_set"),
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
        .where(Track.playlist_id == playlist_id)
        .order_by(Track.added_at.is_(None), Track.added_at)
    ).all())


def delete_playlist(db: Session, playlist_id: int) -> bool:
    """Rimuove una playlist importata e le sue tracce (+ eventuali voci nei set).

    Ritorna False se la playlist non esiste.
    """
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        return False
    track_ids = list(db.scalars(select(Track.id).where(Track.playlist_id == playlist_id)).all())
    if track_ids:
        db.query(SetlistTrack).filter(SetlistTrack.track_id.in_(track_ids)).delete(synchronize_session=False)
        db.query(Track).filter(Track.id.in_(track_ids)).delete(synchronize_session=False)
    db.delete(playlist)
    db.commit()
    return True
