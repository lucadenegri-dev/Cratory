from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.http_errors import api_error
from app.services.file_search import path_within_roots, search_roots
from app.db import get_db
from app.integrations.local_files import read_cover
from app.repositories import genres_overview, get_track, library_stats, list_tracks, update_track
from app.organize.services import apply_job, scan_job
from app.schemas import (
    GenreCountOut,
    LibraryStatsOut,
    TrackDetailOut,
    TrackLinkFileIn,
    TrackListOut,
    TrackUpdateIn,
)
from app.serializers import track_detail_out, track_out
from app.services.acquisition import LinkFileError, link_local_file
from app.services.camelot import parse_camelot
from app.services.genre_norm import normalize_genre

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
    rating: int | None = Query(default=None, ge=1, le=3),
    duration_min: int | None = None,
    duration_max: int | None = None,
    has_spotify: bool | None = None,
    has_soundcloud: bool | None = None,
    has_local_file: bool | None = None,
    archived: bool = False,
    in_playlist: list[int] | None = Query(default=None),
    incomplete_metadata: bool | None = None,
    sort: str | None = Query(
        default=None,
        pattern="^(title|artist|source|bpm|key|energy|genre|duration|year|status|rating|added_at)$",
    ),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=0, le=500),  # 0 = tutte (nessuna paginazione)
    offset: int = Query(default=0, ge=0),
):
    total, rows = list_tracks(
        db,
        limit=limit, offset=offset, sort=sort, order=order,
        artist=artist, title=title, album=album, genre=genre, label=label, source=source, status=status,
        bpm_min=bpm_min, bpm_max=bpm_max, key=key, rating=rating,
        duration_min=duration_min, duration_max=duration_max,
        has_spotify=has_spotify, has_soundcloud=has_soundcloud,
        has_local_file=has_local_file,
        archived=archived,
        in_playlist=in_playlist,
        incomplete_metadata=incomplete_metadata,
    )
    return TrackListOut(total=total, items=[track_out(t) for t in rows])


@router.get("/tracks/{track_id}", response_model=TrackDetailOut)
def get_track_detail(track_id: int, db: Session = Depends(get_db)):
    track = get_track(db, track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found")
    return track_detail_out(track)


@router.get("/tracks/{track_id}/cover")
def get_track_cover(track_id: int, db: Session = Depends(get_db)):
    """Artwork incorporato nel file della traccia posseduta (on-demand, non salvato in
    DB). 404 se la traccia non esiste, non è posseduta, il file manca o non ha cover.
    Il frontend usa `album_art_url` (Spotify) se presente e ripiega qui altrimenti."""
    track = get_track(db, track_id)
    if track is None or not track.has_local_file or not track.local_path:
        raise api_error(404, "track_cover_unavailable", "Cover not available")
    if not Path(track.local_path).exists():
        raise api_error(404, "track_file_not_found", "File not found")
    cover = read_cover(track.local_path)
    if cover is None:
        raise api_error(404, "track_no_embedded_cover", "No cover embedded in the file")
    data, mime = cover
    return Response(content=data, media_type=mime, headers={"Cache-Control": "max-age=3600"})


# Content-Type per estensione: `mimetypes` non conosce bene .flac/.aiff, quindi
# mappiamo esplicitamente i formati audio comuni; fallback binario generico.
_AUDIO_MIME = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".aac": "audio/aac",
    ".flac": "audio/flac", ".wav": "audio/wav", ".aif": "audio/aiff", ".aiff": "audio/aiff",
    ".ogg": "audio/ogg", ".opus": "audio/ogg",
}


@router.get("/tracks/{track_id}/audio")
def get_track_audio(track_id: int, db: Session = Depends(get_db)):
    """Streaming del file locale di una traccia posseduta, per audizione rapida.
    Sola lettura: il file non viene MAI modificato. `FileResponse` gestisce le
    Range request (seek) e risponde 206 al `Range`. 404 se la traccia non esiste,
    non è posseduta, il file risolve fuori dalle cartelle consentite o è mancante."""
    track = get_track(db, track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found")
    if not track.has_local_file or not track.local_path:
        raise api_error(404, "track_no_local_file", "Track has no local file")
    path = Path(track.local_path)
    roots = [root for _, root in search_roots()]
    if not path_within_roots(path, roots):
        raise api_error(404, "track_file_not_allowed", "File outside allowed roots")
    if not path.exists():
        raise api_error(404, "track_file_missing", "File not found")
    media_type = _AUDIO_MIME.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.patch("/tracks/{track_id}", response_model=TrackDetailOut)
def patch_track(track_id: int, payload: TrackUpdateIn, db: Session = Depends(get_db)):
    """Modifica manuale dei valori di una traccia (BPM, key, energia...).

    Inserimento a mano: i valori forniti hanno la precedenza su quelli esistenti. Solo
    i campi presenti nel body vengono toccati; `null` azzera, assente resta com'e'.
    """
    track = get_track(db, track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found")
    data = payload.model_dump(exclude_unset=True)
    # `archived` e' un bool NOT NULL: un null esplicito non puo' azzerare,
    # vale come "invariato" (a differenza degli altri campi PATCH).
    if data.get("archived") is None:
        data.pop("archived", None)
    # La tonalita' non si inventa: se fornita, deve essere un valore Camelot valido.
    if data.get("camelot_key"):
        camelot = str(data["camelot_key"]).strip().upper()
        if not parse_camelot(camelot):
            raise api_error(422, "invalid_camelot_key",
                             "Invalid key: use Camelot notation (e.g. 8A, 12B).")
        data["camelot_key"] = camelot
    # Il genere corretto a mano e' la massima autorita' della catena.
    if "genre" in data:
        data["genre"] = normalize_genre(data.get("genre"))
    track = update_track(db, track, data)
    return track_detail_out(track)


@router.post("/tracks/{track_id}/link-file", response_model=TrackDetailOut)
def link_file(track_id: int, payload: TrackLinkFileIn, db: Session = Depends(get_db)):
    """Collega manualmente un file su disco alla traccia (possesso senza download)."""
    track = get_track(db, track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found")
    try:
        track = link_local_file(db, track, path=payload.path)
    except LinkFileError as exc:
        raise api_error(400, "track_link_failed", f"Track link failed: {exc}",
                         reason=str(exc)) from exc
    return track_detail_out(track)


@router.post("/library/index", status_code=202)
def start_library_index():
    """Alias del job unico di scansione (`scan_job`), sull'intera libreria
    canonica (LIBRARY_ROOT): il disco È la libreria. Endpoint invariato per il
    frontend (`startLibraryIndex` in frontend/lib/api.ts); da F4 il motore
    dietro non è più un job dedicato ma lo stesso scan+link di
    POST /api/organize/scan — stessa guardia di quella rotta canonica: uno
    scan concorrente a un Apply in corso cammina un albero mezzo spostato e
    `_reconcile` puo' fondere 1:1 attraverso il confine inbox/libreria
    (mis-merge, vedi il docstring di `_reconcile` in scanner.py)."""
    if apply_job.is_running():
        raise api_error(409, "apply_running", "Apply in progress")
    if not runtime_settings.library_root():
        raise api_error(
            409, "library_root_not_configured",
            "LIBRARY_ROOT not configured: set the canonical library folder in .env.",
        )
    return scan_job.start_job()


@router.get("/library/index/status")
def library_index_status():
    return scan_job.job_state()


@router.get("/stats", response_model=LibraryStatsOut)
def get_stats(db: Session = Depends(get_db)):
    return library_stats(db)


@router.get("/library/genres", response_model=list[GenreCountOut])
def library_genres(db: Session = Depends(get_db)):
    """Generi della libreria col conteggio, per il filtro del Set Builder."""
    return genres_overview(db)
