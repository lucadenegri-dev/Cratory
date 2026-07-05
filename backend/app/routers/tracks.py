from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.integrations.getsongbpm import (
    FeatureProviderNotConfigured,
    feature_provider_configured,
    get_feature_provider,
)
from app.models import Track
from app.repositories import get_track, library_stats, list_tracks, update_track
from app.integrations.acoustid import AcoustIDNotConfigured
from app.schemas import (
    FingerprintJobStatus,
    LibraryIndexJobStatus,
    LibraryStatsOut,
    TrackDetailOut,
    TrackLinkFileIn,
    TrackListOut,
    TrackLookupOut,
    TrackUpdateIn,
)
from app.serializers import track_detail_out, track_out
from app.services.acquisition import LinkFileError, link_local_file
from app.services.camelot import parse_camelot
from app.services.genre_norm import normalize_genre
from app.services.feature_enrichment import enrich_features
from app.services import fingerprint_job, library_index_job

router = APIRouter(prefix="/api", tags=["tracks"])


@router.get("/tracks", response_model=TrackListOut)
def get_tracks(  # noqa: PLR0913
    db: Session = Depends(get_db),
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    label: str | None = None,
    source: str | None = Query(default=None, pattern="^(spotify|soundcloud|manual|local_files)$"),
    status: str | None = Query(
        default=None,
        pattern="^(imported|ready_for_set)$",
    ),
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    key: str | None = None,
    duration_min: int | None = None,
    duration_max: int | None = None,
    has_spotify: bool | None = None,
    has_soundcloud: bool | None = None,
    has_local_file: bool | None = None,
    archived: bool = False,
    incomplete_metadata: bool | None = None,
    sort: str | None = Query(
        default=None,
        pattern="^(title|artist|source|bpm|key|energy|genre|duration|year|status)$",
    ),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    total, rows = list_tracks(
        db,
        limit=limit, offset=offset, sort=sort, order=order,
        artist=artist, title=title, album=album, genre=genre, label=label, source=source, status=status,
        bpm_min=bpm_min, bpm_max=bpm_max, key=key,
        duration_min=duration_min, duration_max=duration_max,
        has_spotify=has_spotify, has_soundcloud=has_soundcloud,
        has_local_file=has_local_file,
        archived=archived,
        incomplete_metadata=incomplete_metadata,
    )
    return TrackListOut(total=total, items=[track_out(t) for t in rows])


@router.get("/tracks/lookup", response_model=TrackLookupOut)
def lookup_track(
    db: Session = Depends(get_db),
    isrc: str | None = None,
    artist: str | None = None,
    title: str | None = None,
):
    """Lookup read-only per il bridge DjOrganizer: ISRC → fuzzy artist+title.

    Sola lettura: nessuna scrittura, nessun side-effect. Mai 404: `found=false`.
    """
    if not isrc and not (artist and title):
        raise HTTPException(
            status_code=422,
            detail="Servono isrc oppure artist+title.",
        )
    # limit(1): eventuali duplicati (stesso ISRC / stesso artist+title) non devono
    # far fallire il lookup con MultipleResultsFound — si risponde col primo match.
    hit, how, conf = None, None, 0
    if isrc:
        hit = db.scalars(select(Track).where(Track.isrc == isrc).limit(1)).first()
        if hit:
            how, conf = "isrc", 100
    if hit is None and artist and title:
        hit = db.scalars(select(Track).where(
            Track.artist.ilike(artist), Track.title.ilike(title)).limit(1)).first()
        if hit:
            how, conf = "fuzzy", 70
    if hit is None:
        return TrackLookupOut(found=False)
    return TrackLookupOut(
        found=True, match=how, track_id=hit.id,
        artist=hit.artist, title=hit.title,
        genre=hit.genre, genre_secondary=hit.genre_secondary,
        genre_source=hit.genre_source, album=hit.album,
        label=hit.label, year=hit.year, confidence=conf,
    )


@router.get("/tracks/{track_id}", response_model=TrackDetailOut)
def get_track_detail(track_id: int, db: Session = Depends(get_db)):
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata")
    return track_detail_out(track)


@router.patch("/tracks/{track_id}", response_model=TrackDetailOut)
def patch_track(track_id: int, payload: TrackUpdateIn, db: Session = Depends(get_db)):
    """Modifica manuale dei valori di una traccia (BPM, key, mood, energia...).

    Inserimento a mano: i valori forniti hanno la precedenza sull'enrichment. Solo
    i campi presenti nel body vengono toccati; `null` azzera, assente resta com'e'.
    """
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata")
    data = payload.model_dump(exclude_unset=True)
    # La tonalita' non si inventa: se fornita, deve essere un valore Camelot valido.
    if data.get("camelot_key"):
        camelot = str(data["camelot_key"]).strip().upper()
        if not parse_camelot(camelot):
            raise HTTPException(status_code=422, detail="Tonalità non valida: usa la notazione Camelot (es. 8A, 12B).")
        data["camelot_key"] = camelot
    # Il genere corretto a mano e' la massima autorita' della catena.
    if "genre" in data:
        data["genre"] = normalize_genre(data.get("genre"))
        data["genre_source"] = "manual" if data["genre"] else None
    track = update_track(db, track, data)
    return track_detail_out(track)


@router.post("/tracks/{track_id}/link-file", response_model=TrackDetailOut)
def link_file(track_id: int, payload: TrackLinkFileIn, db: Session = Depends(get_db)):
    """Collega manualmente un file su disco alla traccia (possesso senza download)."""
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata")
    try:
        track = link_local_file(db, track, path=payload.path)
    except LinkFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return track_detail_out(track)


@router.post("/tracks/{track_id}/enrich", response_model=TrackDetailOut)
def enrich_one(track_id: int, db: Session = Depends(get_db)):
    """Arricchisce le feature musicali di UNA traccia (sincrono). Non sovrascrive BPM/key esistenti."""
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata")
    if not feature_provider_configured():
        raise HTTPException(
            status_code=409,
            detail=str(FeatureProviderNotConfigured(
                "Nessun provider di feature configurato: abilita Deezer e/o imposta "
                "GETSONGBPM_API_KEY / LASTFM_API_KEY (vedi Impostazioni)."
            )),
        )
    # force=True: elabora la traccia anche se ha gia' BPM (completa i campi mancanti).
    enrich_features(db, get_feature_provider(), force=True, track_ids=[track_id])
    db.refresh(track)
    return track_detail_out(track)


@router.post("/library/index", response_model=LibraryIndexJobStatus, status_code=202)
def start_library_index():
    """Indicizza la libreria canonica (LIBRARY_ROOT): il disco È la libreria."""
    if not settings.library_root:
        raise HTTPException(
            status_code=409,
            detail="LIBRARY_ROOT non configurata: imposta nel .env la cartella della libreria canonica.",
        )
    return library_index_job.start_job()


@router.get("/library/index/status", response_model=LibraryIndexJobStatus)
def library_index_status():
    return library_index_job.job_state()


@router.post("/library/fingerprint", response_model=FingerprintJobStatus, status_code=202)
def start_fingerprint(force: bool = Query(default=False)):
    """Fingerprinting AcoustID delle tracce possedute: audio -> mbid (identita' certa)."""
    try:
        return fingerprint_job.start_job(force=force)
    except AcoustIDNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/library/fingerprint/status", response_model=FingerprintJobStatus)
def fingerprint_status():
    return fingerprint_job.job_state()


@router.get("/stats", response_model=LibraryStatsOut)
def get_stats(db: Session = Depends(get_db)):
    return library_stats(db)
