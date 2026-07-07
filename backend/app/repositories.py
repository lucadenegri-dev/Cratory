"""Query di accesso dati (layer repository)."""

from collections.abc import Iterable

from sqlalchemy import delete, func, select
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
    has_local_file: bool | None = None,
    incomplete_metadata: bool | None = None,
    archived: bool = False,
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
    if has_local_file is not None:
        # Possesso disk-first: True = in libreria (file su disco), False = wishlist.
        stmt = (
            stmt.where(Track.has_local_file.is_(True))
            if has_local_file
            else stmt.where((Track.has_local_file.is_(False)) | (Track.has_local_file.is_(None)))
        )
    if incomplete_metadata:
        # "dati incompleti" utile al DJ: manca un metadato chiave o una feature di mixing.
        stmt = stmt.where(
            Track.title.is_(None) | Track.artist.is_(None)
            | Track.bpm.is_(None) | Track.camelot_key.is_(None)
        )
    # Scartate: fuori da ogni vista di default; archived=True le mostra da sole.
    stmt = (stmt.where(Track.archived.is_(True)) if archived
            else stmt.where(Track.archived.is_not(True)))
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


def update_track(db: Session, track: Track, data: dict) -> Track:
    """Applica una modifica manuale parziale a una traccia.

    `data` contiene solo i campi forniti (PATCH): le stringhe vuote diventano None
    (azzeramento), gli altri valori sovrascrivono anche dati gia' presenti — la
    modifica manuale ha sempre la precedenza. Vale per tutti i campi TRANNE
    `energy`, che non e' modificabile a mano: e' sempre derivata da bpm/genere
    (services/energy) e viene ricalcolata qui quando il patch tocca bpm o
    genere e la traccia ha un bpm. Aggiorna lo stato.
    """
    from app.services.energy import estimate_energy
    from app.services.track_status import refresh_status

    for field, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(track, field, value)
    if ("bpm" in data or "genre" in data) and track.bpm is not None:
        track.energy = estimate_energy(track.bpm, None, track.genre)
    refresh_status(track)
    db.commit()
    db.refresh(track)
    return track


def all_playable_tracks(db: Session, *, owned_only: bool = False) -> list[Track]:
    """Tracce utilizzabili in un set: con BPM e durata sensata.

    Con ``owned_only`` restringe alle tracce possedute (file su disco): e' il
    pool dell'editor quando il set e' nato "solo brani posseduti".
    """
    stmt = select(Track).where(Track.bpm.is_not(None))
    if owned_only:
        stmt = stmt.where(Track.has_local_file.is_(True))
    return list(db.scalars(stmt).all())


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
    # Distribuzione generi per la stat di dashboard. I tag su disco hanno grafie
    # incoerenti ("Ambient"/"ambient"): li fondiamo case-insensitive tenendo come
    # etichetta la grafia più frequente. È solo presentazione — il valore
    # autorevole resta il tag sul file (scritto da DjOrganizer), non lo tocchiamo.
    _genre_variants: dict[str, dict[str, int]] = {}
    for label, n in db.execute(
        select(Track.genre, func.count())
        .where(Track.genre.is_not(None), Track.genre != "")
        .group_by(Track.genre)
    ):
        _genre_variants.setdefault(label.casefold(), {})[label] = n
    genre_distribution = {
        max(variants, key=variants.__getitem__): sum(variants.values())
        for variants in _genre_variants.values()
    }

    def count_where(*conds) -> int:
        return db.scalar(select(func.count()).select_from(Track).where(*conds)) or 0

    with_features = count_where(Track.energy.is_not(None))
    ready_for_set = count_where(Track.status == "ready_for_set")
    with_local_file = count_where(Track.has_local_file.is_(True))
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
        "with_local_file": with_local_file,
        "missing_metadata": missing_metadata,
        "bpm_min": min(bpms) if bpms else None,
        "bpm_max": max(bpms) if bpms else None,
        "key_distribution": dict(sorted(key_distribution.items())),
        "genre_distribution": dict(
            sorted(genre_distribution.items(), key=lambda kv: kv[1], reverse=True)
        ),
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


def tracks_download_pending(db: Session) -> list[Track]:
    """Wishlist con esito download da sistemare (da rivedere/non trovata/fallita)."""
    return list(db.scalars(
        select(Track)
        .where((Track.has_local_file.is_(False)) | (Track.has_local_file.is_(None)))
        .where(Track.archived.is_not(True))
        .where(Track.last_download_outcome.in_(["needs_review", "not_found", "failed"]))
        .order_by(Track.artist, Track.title)
    ))


def tracks_without_local_file(db: Session, playlist_id: int) -> list[Track]:
    """Tracce della playlist senza file locale (coda della sezione Download)."""
    return list(db.scalars(
        select(Track)
        .join(playlist_tracks, playlist_tracks.c.track_id == Track.id)
        .where(playlist_tracks.c.playlist_id == playlist_id)
        .where((Track.has_local_file.is_(False)) | (Track.has_local_file.is_(None)))
        .where(Track.archived.is_not(True))  # le scartate non si riscaricano
        .order_by(Track.artist, Track.title)
    ))


def orphan_lead_ids(db: Session, candidate_ids: Iterable[int] | None = None) -> list[int]:
    """Id dei lead orfani: non su disco (`has_local_file` non True), non in nessuna
    playlist e non in alcun set salvato. Se `candidate_ids` è dato, si restringe a
    quelli (utile a valle di una eliminazione playlist); altrimenti scandisce tutto
    il DB (usato dalla pulizia una-tantum)."""
    stmt = select(Track.id).where(
        Track.has_local_file.is_not(True),
        Track.id.not_in(select(playlist_tracks.c.track_id)),
        Track.id.not_in(select(SetlistTrack.track_id)),
    )
    if candidate_ids is not None:
        ids = list(candidate_ids)
        if not ids:
            return []
        stmt = stmt.where(Track.id.in_(ids))
    return list(db.scalars(stmt))


def unreferenced_track_ids(db: Session, candidate_ids: Iterable[int] | None = None) -> list[int]:
    """Tra i candidati (o tutte le tracce), quelle non in nessuna playlist né set
    salvato — a prescindere dal possesso su disco. Usato dall'indicizzazione per
    decidere se una traccia sganciata va rimossa o tenuta come lead."""
    stmt = select(Track.id).where(
        Track.id.not_in(select(playlist_tracks.c.track_id)),
        Track.id.not_in(select(SetlistTrack.track_id)),
    )
    if candidate_ids is not None:
        ids = list(candidate_ids)
        if not ids:
            return []
        stmt = stmt.where(Track.id.in_(ids))
    return list(db.scalars(stmt))


def delete_orphan_leads(db: Session, candidate_ids: Iterable[int] | None = None) -> int:
    """Cancella i lead orfani (vedi `orphan_lead_ids`) e ritorna quanti. Non committa
    (lo fa il chiamante)."""
    ids = orphan_lead_ids(db, candidate_ids)
    if not ids:
        return 0
    db.execute(
        delete(Track).where(Track.id.in_(ids)),
        execution_options={"synchronize_session": False},
    )
    return len(ids)


def delete_playlist(db: Session, playlist_id: int) -> int | None:
    """Rimuove una playlist e i lead diventati orfani (non su disco, non in altre
    playlist, non in alcun set salvato). Ritorna il numero di tracce orfane
    cancellate, o None se la playlist non esiste."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        return None
    candidate_ids = [
        r[0] for r in db.execute(
            select(playlist_tracks.c.track_id).where(playlist_tracks.c.playlist_id == playlist_id)
        )
    ]
    db.execute(playlist_tracks.delete().where(playlist_tracks.c.playlist_id == playlist_id))
    db.delete(playlist)
    db.flush()  # le membership rimosse devono essere visibili al check orfani
    removed = delete_orphan_leads(db, candidate_ids)
    db.commit()
    return removed


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
