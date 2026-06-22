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
from app.integrations.getsongbpm import FeatureProviderNotConfigured
from app.integrations.spotify import (
    SpotifyError,
    SpotifyNotConfigured,
    SpotifyNotConnected,
    SpotifyWebClient,
)
from app.repositories import (
    all_playable_tracks,
    delete_playlist,
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
from app.services import enrichment_job
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


def _autoenrich(playlist_id: int | None) -> None:
    """Avvia (best-effort) l'enrichment delle tracce appena importate.

    Non deve mai far fallire l'import: se nessun provider e' configurato o il job
    e' gia' in corso, viene semplicemente ignorato. La UI mostra l'avanzamento via
    /api/enrichment/features/status.
    """
    if playlist_id is None:
        return
    try:
        enrichment_job.start_job(playlist_id=playlist_id)
    except FeatureProviderNotConfigured:
        logger.info("Auto-enrichment saltato: nessun provider di feature configurato.")
    except Exception:  # noqa: BLE001 — l'import non deve fallire per colpa dell'enrichment
        logger.exception("Auto-enrichment non avviato per la playlist %s", playlist_id)


@router.get("/spotify/available", response_model=list[SpotifyPlaylistRef])
def spotify_available(db: Session = Depends(get_db)):
    """Playlist Spotify possedute dall'utente, selezionabili per l'import.

    Solo le proprie: le playlist altrui che l'utente segue non sono importabili
    (in Development Mode Spotify nega l'accesso ai loro item) e vengono escluse.
    """
    client = SpotifyWebClient(db)
    try:
        raw = client.list_user_playlists()
        me_id = client.current_user_id()
    except SpotifyError as exc:
        raise _http_error(exc) from exc
    out: list[SpotifyPlaylistRef] = []
    for p in raw:
        if not p:
            continue
        if (p.get("owner") or {}).get("id") != me_id:
            continue  # playlist seguita ma non posseduta: non importabile
        images = p.get("images") or []
        out.append(SpotifyPlaylistRef(
            platform_playlist_id=p["id"],
            name=p.get("name") or "(senza nome)",
            owner=(p.get("owner") or {}).get("display_name"),
            # in Development Mode /me/playlists puo' restituire tracks=null e spostare
            # il conteggio nel paging object 'items': accettiamo entrambe le forme.
            track_count=((p.get("tracks") or p.get("items") or {}).get("total")) or 0,
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
    _autoenrich(report.get("playlist_id"))
    return PlaylistImportReport(**report)


@router.post("/{playlist_id}/sync", response_model=PlaylistImportReport)
def sync_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Riallinea la playlist con Spotify: importa le nuove tracce e scollega quelle
    rimosse (che restano comunque in libreria). Applica e ritorna un report.
    """
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist non trovata")
    if playlist.platform != "spotify":
        raise HTTPException(status_code=409, detail="Solo le playlist Spotify sono sincronizzabili.")
    if playlist.kind != "liked" and not playlist.platform_playlist_id:
        raise HTTPException(status_code=409, detail="Playlist non sincronizzabile da Spotify.")

    client = SpotifyWebClient(db)
    try:
        if playlist.kind == "liked":
            items = client.get_liked_tracks()
        else:
            items = client.get_playlist_tracks(playlist.platform_playlist_id)
    except SpotifyError as exc:
        raise _http_error(exc) from exc

    report = import_playlist(
        db, platform="spotify", name=playlist.name, items=items,
        platform_playlist_id=playlist.platform_playlist_id,
        owner=playlist.owner, url=playlist.url, artwork_url=playlist.artwork_url,
        kind=playlist.kind, prune=True,
    )
    _autoenrich(report.get("playlist_id"))
    return PlaylistImportReport(**report)


@router.post("/import-manual", response_model=PlaylistImportReport)
def import_manual(req: ManualImportRequest, db: Session = Depends(get_db)):
    """Crea una playlist dalla tracklist incollata ('Artista - Titolo' o CSV)."""
    report = import_manual_playlist(db, name=req.name, text=req.text)
    if report["total"] == 0:
        raise HTTPException(status_code=422, detail="Nessuna traccia riconosciuta nel testo fornito.")
    _autoenrich(report.get("playlist_id"))
    return PlaylistImportReport(**report)


@router.get("", response_model=list[PlaylistOut])
def list_imported(db: Session = Depends(get_db)):
    return [PlaylistOut.model_validate(p) for p in list_playlists(db)]


@router.get("/{playlist_id}", response_model=PlaylistOut)
def playlist_detail(playlist_id: int, db: Session = Depends(get_db)):
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist non trovata")
    return PlaylistOut.model_validate(playlist)


@router.delete("/{playlist_id}", status_code=204)
def remove_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Rimuove una playlist importata e le sue tracce dalla libreria dell'app."""
    if not delete_playlist(db, playlist_id):
        raise HTTPException(status_code=404, detail="Playlist non trovata")


@router.post("/{playlist_id}/enrich")
def enrich_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Riesegue l'enrichment feature sulle tracce di questa playlist.

    force=True: ignora la cache e ri-interroga i provider, cosi' un nuovo tentativo
    recupera anche le tracce rimaste senza dati per un errore di rete precedente.
    """
    if get_playlist(db, playlist_id) is None:
        raise HTTPException(status_code=404, detail="Playlist non trovata")
    try:
        return enrichment_job.start_job(force=True, playlist_id=playlist_id)
    except FeatureProviderNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
