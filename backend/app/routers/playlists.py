"""Router playlist: punto di partenza del nuovo flusso (playlist streaming -> set).

- elenco playlist Spotify dell'utente (per la selezione),
- import di una playlist o dei liked,
- elenco/dettaglio playlist importate,
- analisi deterministica dei "buchi" di una playlist (o dell'intera libreria).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.spotify import (
    SpotifyError,
    SpotifyNotConfigured,
    SpotifyNotConnected,
    SpotifyWebClient,
)
from app.repositories import (
    all_playable_tracks,
    get_playlist,
    list_playlists,
    tracks_for_playlist,
)
from app.schemas import (
    GapAnalysisResponse,
    GapOut,
    ManualImportRequest,
    PlaylistImportReport,
    PlaylistImportRequest,
    PlaylistOut,
    SpotifyPlaylistRef,
    TrackOut,
)
from app.serializers import track_out
from app.services.gap_analysis import analyze_gaps
from app.services.manual_import import import_manual_playlist
from app.services.playlist_import import import_playlist

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/playlists", tags=["playlists"])


def _http_error(exc: SpotifyError) -> HTTPException:
    if isinstance(exc, SpotifyNotConfigured):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, SpotifyNotConnected):
        return HTTPException(status_code=401, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/spotify/available", response_model=list[SpotifyPlaylistRef])
def spotify_available(db: Session = Depends(get_db)):
    """Playlist Spotify dell'utente autenticato, selezionabili per l'import."""
    try:
        raw = SpotifyWebClient(db).list_user_playlists()
    except SpotifyError as exc:
        raise _http_error(exc) from exc
    out: list[SpotifyPlaylistRef] = []
    for p in raw:
        if not p:
            continue
        images = p.get("images") or []
        out.append(SpotifyPlaylistRef(
            platform_playlist_id=p["id"],
            name=p.get("name") or "(senza nome)",
            owner=(p.get("owner") or {}).get("display_name"),
            track_count=(p.get("tracks") or {}).get("total", 0),
            url=(p.get("external_urls") or {}).get("spotify"),
            artwork_url=images[0]["url"] if images else None,
        ))
    return out


@router.post("/import", response_model=PlaylistImportReport)
def import_from_spotify(req: PlaylistImportRequest, db: Session = Depends(get_db)):
    client = SpotifyWebClient(db)
    try:
        if req.playlist_id == "liked":
            items = client.get_liked_tracks()
            report = import_playlist(
                db, platform="spotify", name="Brani che ti piacciono",
                items=items, kind="liked",
            )
        else:
            playlist_meta = client.get_playlist_meta(req.playlist_id)
            items = client.get_playlist_tracks(req.playlist_id)
            images = playlist_meta.get("images") or []
            report = import_playlist(
                db, platform="spotify",
                name=playlist_meta.get("name") or "Playlist Spotify",
                items=items,
                platform_playlist_id=req.playlist_id,
                owner=(playlist_meta.get("owner") or {}).get("display_name"),
                url=(playlist_meta.get("external_urls") or {}).get("spotify"),
                artwork_url=images[0]["url"] if images else None,
            )
    except SpotifyError as exc:
        raise _http_error(exc) from exc
    return PlaylistImportReport(**report)


@router.post("/import-manual", response_model=PlaylistImportReport)
def import_manual(req: ManualImportRequest, db: Session = Depends(get_db)):
    """Crea una playlist dalla tracklist incollata ('Artista - Titolo' o CSV)."""
    report = import_manual_playlist(db, name=req.name, text=req.text)
    if report["total"] == 0:
        raise HTTPException(status_code=422, detail="Nessuna traccia riconosciuta nel testo fornito.")
    return PlaylistImportReport(**report)


@router.get("", response_model=list[PlaylistOut])
def list_imported(db: Session = Depends(get_db)):
    return [PlaylistOut.model_validate(p) for p in list_playlists(db)]


@router.get("/{playlist_id}/tracks", response_model=list[TrackOut])
def playlist_tracks(playlist_id: int, db: Session = Depends(get_db)):
    if get_playlist(db, playlist_id) is None:
        raise HTTPException(status_code=404, detail="Playlist non trovata")
    return [track_out(t) for t in tracks_for_playlist(db, playlist_id)]


@router.get("/{playlist_id}/gaps", response_model=GapAnalysisResponse)
def playlist_gaps(playlist_id: int, db: Session = Depends(get_db)):
    if get_playlist(db, playlist_id) is None:
        raise HTTPException(status_code=404, detail="Playlist non trovata")
    tracks = tracks_for_playlist(db, playlist_id)
    gaps = analyze_gaps(tracks)
    return GapAnalysisResponse(
        scope="playlist", track_count=len(tracks),
        gaps=[GapOut(**g) for g in gaps],
    )


@router.get("/library/gaps", response_model=GapAnalysisResponse)
def library_gaps(db: Session = Depends(get_db)):
    tracks = all_playable_tracks(db)
    gaps = analyze_gaps(tracks)
    return GapAnalysisResponse(
        scope="library", track_count=len(tracks),
        gaps=[GapOut(**g) for g in gaps],
    )
