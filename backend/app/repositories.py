"""Query di accesso dati (layer repository)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import DjSet, DjSetTrack, Playlist, Setlist, SetlistTrack, Track, playlist_tracks

# Colonne ordinabili dalla libreria (header cliccabili nel frontend).
_SORT_COLUMNS = {
    "title": Track.title,
    "artist": Track.artist,
    "source": Track.source_type,
    "bpm": Track.bpm,
    "key": Track.camelot_key,
    "energy": Track.energy,
    "genre": Track.genre,
    "duration": Track.duration_seconds,
    "year": Track.year,
    "status": Track.status,
}


def _apply_track_filters(  # noqa: PLR0913
    stmt,
    *,
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    label: str | None = None,
    source: str | None = None,
    status: str | None = None,
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
    if label:
        stmt = stmt.where(Track.label == label)  # match esatto: drill-down dall'etichetta
    if source:
        stmt = stmt.where(Track.source_type == source)
    if status:
        stmt = stmt.where(Track.status == status)
    if bpm_min is not None:
        stmt = stmt.where(Track.bpm >= bpm_min)
    if bpm_max is not None:
        stmt = stmt.where(Track.bpm <= bpm_max)
    if key:
        stmt = stmt.where(Track.camelot_key.ilike(key))  # case-insensitive: "7a" -> "7A"
    if duration_min is not None:
        stmt = stmt.where(Track.duration_seconds >= duration_min)
    if duration_max is not None:
        stmt = stmt.where(Track.duration_seconds <= duration_max)
    if has_spotify is not None:
        stmt = stmt.where(Track.spotify_id.is_not(None) if has_spotify else Track.spotify_id.is_(None))
    if has_soundcloud is not None:
        stmt = stmt.where(Track.soundcloud_id.is_not(None) if has_soundcloud else Track.soundcloud_id.is_(None))
    if incomplete_metadata:
        # "dati incompleti" utile al DJ: manca un metadato chiave o una feature di mixing.
        stmt = stmt.where(
            Track.title.is_(None) | Track.artist.is_(None)
            | Track.bpm.is_(None) | Track.camelot_key.is_(None)
        )
    return stmt


def list_tracks(
    db: Session, *, limit: int = 100, offset: int = 0,
    sort: str | None = None, order: str = "asc", **filters,
):
    stmt = _apply_track_filters(select(Track), **filters)
    total = db.scalar(select(func.count()).select_from(_apply_track_filters(select(Track.id), **filters).subquery()))

    column = _SORT_COLUMNS.get(sort or "")
    if column is not None:
        direction = column.desc() if order == "desc" else column.asc()
        # NULL sempre in fondo, poi id come tie-breaker (paginazione deterministica).
        order_by = (column.is_(None), direction, Track.id.asc())
    else:
        order_by = (Track.artist.is_(None), Track.artist, Track.title)

    rows = db.scalars(
        stmt.options(selectinload(Track.playlists)).order_by(*order_by).limit(limit).offset(offset)
    ).all()
    return total or 0, rows


def get_track(db: Session, track_id: int) -> Track | None:
    return db.scalar(
        select(Track).options(selectinload(Track.playlists)).where(Track.id == track_id)
    )


# Campi feature musicali: se l'utente ne modifica uno a mano, la fonte diventa "manual".
_MANUAL_FEATURE_FIELDS = {"bpm", "camelot_key", "mood", "energy", "danceability", "vocalness", "label"}


def update_track(db: Session, track: Track, data: dict) -> Track:
    """Applica una modifica manuale parziale a una traccia.

    `data` contiene solo i campi forniti (PATCH): le stringhe vuote diventano None
    (azzeramento), gli altri valori sovrascrivono anche dati gia' presenti — la
    modifica manuale ha sempre la precedenza sull'enrichment. Aggiorna lo stato.
    """
    from datetime import datetime, timezone

    from app.services.track_status import refresh_status

    touched_feature = False
    for field, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(track, field, value)
        if field in _MANUAL_FEATURE_FIELDS:
            touched_feature = True
    if touched_feature:
        track.enrichment_source = "manual"
        track.enrichment_confidence = 100  # inserito dall'utente: massima fiducia
        track.enriched_at = datetime.now(timezone.utc)
    refresh_status(track)
    db.commit()
    db.refresh(track)
    return track


def all_playable_tracks(db: Session) -> list[Track]:
    """Tracce utilizzabili in un set: con BPM e durata sensata."""
    return list(db.scalars(select(Track).where(Track.bpm.is_not(None))).all())


_BPM_HISTOGRAM_BINS = 8


def _bpm_histogram(bpms: list[float], bins: int = _BPM_HISTOGRAM_BINS) -> list[dict]:
    """Istogramma dei BPM su ``bins`` intervalli a larghezza uguale tra min e max.

    Ogni voce: ``{"from": float, "to": float, "count": int}``. Lista vuota se non
    ci sono BPM; un solo bin se i BPM hanno un unico valore distinto. Il valore
    massimo cade nell'ultimo bin (chiuso a destra).
    """
    if not bpms:
        return []
    lo, hi = min(bpms), max(bpms)
    if lo == hi:
        return [{"from": lo, "to": hi, "count": len(bpms)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in bpms:
        idx = int((v - lo) / width)
        if idx >= bins:  # il massimo cade nell'ultimo bin
            idx = bins - 1
        counts[idx] += 1
    return [
        {"from": lo + i * width, "to": lo + (i + 1) * width, "count": counts[i]}
        for i in range(bins)
    ]


def _energy_distribution(energies: list[int]) -> list[dict]:
    """Distribuzione dell'energia su 5 bucket fissi di ampiezza 20 (0-100).

    Sempre 5 voci ``{"from": int, "to": int, "count": int}`` (anche con count 0).
    Il valore 100 cade nell'ultimo bucket ``[80, 100]``.
    """
    counts = [0] * 5
    for e in energies:
        idx = min(int(e // 20), 4)
        counts[idx] += 1
    return [
        {"from": i * 20, "to": (i + 1) * 20, "count": counts[i]}
        for i in range(5)
    ]


def library_stats(db: Session) -> dict:
    # Aggregati in SQL (colonne/indici esistenti) invece di caricare l'intera
    # tabella in oggetti ORM: bpm/energy come sole colonne per i bin in Python.
    bpms = [b for b in db.scalars(select(Track.bpm).where(Track.bpm.is_not(None))) if b]
    energies = list(db.scalars(select(Track.energy).where(Track.energy.is_not(None))))

    by_source = dict(
        db.execute(select(Track.source_type, func.count()).group_by(Track.source_type)).all()
    )
    key_distribution = dict(
        db.execute(
            select(Track.camelot_key, func.count())
            .where(Track.camelot_key.is_not(None), Track.camelot_key != "")
            .group_by(Track.camelot_key)
        ).all()
    )

    def count_where(*conds) -> int:
        return db.scalar(select(func.count()).select_from(Track).where(*conds)) or 0

    with_features = count_where(
        ((Track.mood.is_not(None)) & (Track.mood != "")) | (Track.energy.is_not(None))
    )
    ready_for_set = count_where(Track.status == "ready_for_set")
    missing_metadata = count_where(
        (Track.title.is_(None)) | (Track.title == "") | (Track.artist.is_(None)) | (Track.artist == "")
    )

    return {
        "total_tracks": db.scalar(select(func.count()).select_from(Track)) or 0,
        "playlists": db.scalar(select(func.count()).select_from(Playlist)) or 0,
        "by_source": by_source,
        "with_bpm": len(bpms),
        "with_key": sum(key_distribution.values()),
        "with_features": with_features,
        "ready_for_set": ready_for_set,
        "missing_metadata": missing_metadata,
        "bpm_min": min(bpms) if bpms else None,
        "bpm_max": max(bpms) if bpms else None,
        "key_distribution": dict(sorted(key_distribution.items())),
        "bpm_histogram": _bpm_histogram(bpms),
        "energy_distribution": _energy_distribution(energies),
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


def add_track_to_playlist(db: Session, track: Track, playlist: Playlist, *, added_at=None) -> None:
    """Crea la membership brano<->playlist se non esiste (idempotente). Non committa."""
    exists = db.execute(
        select(playlist_tracks.c.track_id).where(
            playlist_tracks.c.playlist_id == playlist.id,
            playlist_tracks.c.track_id == track.id,
        )
    ).first()
    if exists:
        return
    db.execute(playlist_tracks.insert().values(
        playlist_id=playlist.id, track_id=track.id, added_at=added_at,
    ))


def remove_track_from_playlist(db: Session, playlist_id: int, track_id: int) -> None:
    db.execute(playlist_tracks.delete().where(
        playlist_tracks.c.playlist_id == playlist_id,
        playlist_tracks.c.track_id == track_id,
    ))


def recount_playlist(db: Session, playlist: Playlist) -> None:
    n = db.scalar(
        select(func.count()).select_from(playlist_tracks)
        .where(playlist_tracks.c.playlist_id == playlist.id)
    )
    playlist.track_count = n or 0


def tracks_for_playlist(db: Session, playlist_id: int) -> list[Track]:
    return list(db.scalars(
        select(Track)
        .options(selectinload(Track.playlists))
        .join(playlist_tracks, playlist_tracks.c.track_id == Track.id)
        .where(playlist_tracks.c.playlist_id == playlist_id)
        .order_by(playlist_tracks.c.added_at.is_(None), playlist_tracks.c.added_at)
    ).all())


def delete_playlist(db: Session, playlist_id: int) -> bool:
    """Rimuove una playlist: cancella le sue membership; le tracce restano in libreria
    (e nelle altre playlist). Ritorna False se la playlist non esiste."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        return False
    db.execute(playlist_tracks.delete().where(playlist_tracks.c.playlist_id == playlist_id))
    db.delete(playlist)
    db.commit()
    return True


# --- DJ set identificati via Shazam (corpus per i suggerimenti) ---------------

_DJSET_TRACKS = selectinload(DjSet.tracks)


def list_dj_sets(db: Session) -> list[DjSet]:
    return list(db.scalars(
        select(DjSet).options(_DJSET_TRACKS).order_by(DjSet.created_at.desc())
    ).all())


def get_dj_set(db: Session, dj_set_id: int) -> DjSet | None:
    return db.scalar(select(DjSet).options(_DJSET_TRACKS).where(DjSet.id == dj_set_id))


def get_dj_set_by_url(db: Session, url: str) -> DjSet | None:
    return db.scalar(select(DjSet).options(_DJSET_TRACKS).where(DjSet.source_url == url))


def delete_dj_set(db: Session, dj_set_id: int) -> bool:
    dj_set = db.scalar(select(DjSet).where(DjSet.id == dj_set_id))
    if dj_set is None:
        return False
    db.delete(dj_set)  # cascade elimina le DjSetTrack
    db.commit()
    return True


def all_dj_set_tracks(db: Session) -> list[DjSetTrack]:
    """Tutte le tracce identificate (corpus per la co-occorrenza, Fase 2)."""
    return list(db.scalars(select(DjSetTrack)).all())
