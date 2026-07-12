"""Router playlist: punto di partenza del nuovo flusso (playlist streaming -> set).

- elenco playlist Spotify dell'utente (per la selezione),
- import di una playlist o dei liked,
- elenco/dettaglio playlist importate,
- analisi deterministica dei "buchi" di una playlist (o dell'intera libreria).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.models import Playlist, Track
from app.integrations.soundcloud import (
    SoundCloudError,
    SoundCloudInvalidUrl,
    fetch_playlist as sc_fetch_playlist,
)
from app.integrations.spotify import (
    SpotifyError,
    SpotifyNotConfigured,
    SpotifyNotConnected,
    SpotifyWebClient,
)
from app.repositories import (
    add_track_to_playlist,
    all_playable_tracks,
    delete_playlist,
    get_playlist,
    list_playlists,
    recount_playlist,
    tracks_for_playlist,
)
from app.schemas import (
    GapAnalysisResponse,
    GapOut,
    LikedSelectedImportRequest,
    LikedTrackPreview,
    ManualImportRequest,
    PlaylistAddTrackRequest,
    PlaylistAddTrackResponse,
    PlaylistDeleteResult,
    PlaylistFromTracksRequest,
    PlaylistImportReport,
    PlaylistImportRequest,
    PlaylistOut,
    SpotifyPlaylistRef,
    TrackOut,
)
from app.serializers import track_out
from app.services.gap_analysis import analyze_gaps
from app.services.manual_import import import_manual_playlist
from app.services.playlist_import import (
    LIKED_PLAYLIST_NAME,
    import_playlist,
    import_selected_liked_tracks,
    import_single_track,
    normalize_soundcloud_item,
    preview_liked_tracks,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/playlists", tags=["playlists"])


def _http_error(exc: SpotifyError) -> HTTPException:
    if isinstance(exc, SpotifyNotConfigured):
        return api_error(409, "spotify_not_configured", str(exc), reason=str(exc))
    if isinstance(exc, SpotifyNotConnected):
        return api_error(401, "spotify_not_connected", str(exc), reason=str(exc))
    return api_error(502, "spotify_error", str(exc), reason=str(exc))


# L'auto-enrichment delle tracce appena importate non e' piu' responsabilita' di
# Cratory: il motore di enrichment (feature/genere) vive ora in Sortory.


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
                db, platform="spotify", name=LIKED_PLAYLIST_NAME,
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
    # Enrichment non piu' avviato qui: e' ora responsabilita' di Sortory.
    return PlaylistImportReport(**report)


@router.get("/spotify/liked/preview", response_model=list[LikedTrackPreview])
def liked_preview(db: Session = Depends(get_db)):
    """Anteprima dei brani salvati (liked) di Spotify, selezionabili per l'import.

    Non importa nulla: marca quali sono già nella playlist Liked locale.
    """
    client = SpotifyWebClient(db)
    try:
        items = client.get_liked_tracks()
    except SpotifyError as exc:
        raise _http_error(exc) from exc
    return [LikedTrackPreview(**p) for p in preview_liked_tracks(db, items)]


@router.post("/import/liked/selected", response_model=PlaylistImportReport)
def import_liked_selected(req: LikedSelectedImportRequest, db: Session = Depends(get_db)):
    """Importa nella playlist Liked solo i brani selezionati. Additivo (niente prune)."""
    client = SpotifyWebClient(db)
    try:
        items = client.get_liked_tracks()
    except SpotifyError as exc:
        raise _http_error(exc) from exc
    report = import_selected_liked_tracks(db, items, req.spotify_ids)
    return PlaylistImportReport(**report)


@router.post("/{playlist_id}/sync", response_model=PlaylistImportReport)
def sync_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Riallinea la playlist con la piattaforma d'origine: Spotify con prune,
    SoundCloud solo additivo.
    """
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")

    if playlist.platform == "soundcloud":
        # I liked SoundCloud crescono solo via flusso selettivo: niente sync totale.
        if playlist.kind == "liked" or not playlist.url:
            raise api_error(
                409, "soundcloud_playlist_not_syncable",
                "SoundCloud playlists can't be synced: use the selective likes flow or re-import the URL.",
            )
        try:
            info = sc_fetch_playlist(playlist.url)
        except SoundCloudError as exc:
            if isinstance(exc, SoundCloudInvalidUrl):
                raise api_error(422, "soundcloud_invalid_url", str(exc), reason=str(exc)) from exc
            raise api_error(502, "soundcloud_error", str(exc), reason=str(exc)) from exc
        # Additivo (prune=False): su SoundCloud un takedown non significa
        # "non mi interessa più" — il lead resta collegato.
        report = import_playlist(
            db, platform="soundcloud", name=playlist.name, items=info["entries"],
            normalize=normalize_soundcloud_item,
            platform_playlist_id=playlist.platform_playlist_id,
            owner=playlist.owner, url=playlist.url, artwork_url=playlist.artwork_url,
            kind=playlist.kind, prune=False,
        )
        return PlaylistImportReport(**report)

    if playlist.platform != "spotify":
        raise api_error(
            409, "playlist_platform_not_syncable",
            "Only Spotify and SoundCloud playlists can be synced.",
        )
    if playlist.kind != "liked" and not playlist.platform_playlist_id:
        raise api_error(409, "playlist_not_syncable", "This playlist can't be synced from Spotify.")

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
    # Enrichment non piu' avviato qui: e' ora responsabilita' di Sortory.
    return PlaylistImportReport(**report)


@router.post("/import-manual", response_model=PlaylistImportReport)
def import_manual(req: ManualImportRequest, db: Session = Depends(get_db)):
    """Crea una playlist dalla tracklist incollata ('Artista - Titolo' o CSV)."""
    report = import_manual_playlist(db, name=req.name, text=req.text)
    if report["total"] == 0:
        raise api_error(422, "no_tracks_recognized", "No tracks recognized in the given text.")
    # Enrichment non piu' avviato qui: e' ora responsabilita' di Sortory.
    return PlaylistImportReport(**report)


@router.post("/create-from-tracks", response_model=PlaylistOut, status_code=201)
def create_from_tracks(req: PlaylistFromTracksRequest, db: Session = Depends(get_db)):
    """Crea una playlist componendo tracce gia' in libreria (disk-first)."""
    tracks = db.scalars(select(Track).where(Track.id.in_(req.track_ids))).all()
    by_id = {t.id: t for t in tracks}
    missing = [i for i in req.track_ids if i not in by_id]
    if missing:
        raise api_error(422, "tracks_not_found", f"Nonexistent tracks: {missing}", missing=missing)
    if not req.name.strip():
        raise api_error(422, "playlist_name_empty", "Playlist name is empty.")
    # Stessa costruzione delle playlist manuali (services/manual_import.py).
    playlist = Playlist(platform="manual", name=req.name.strip(), kind="manual")
    db.add(playlist)
    db.flush()  # serve playlist.id
    for track_id in req.track_ids:  # nell'ordine scelto dall'utente
        add_track_to_playlist(db, by_id[track_id], playlist)
    recount_playlist(db, playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


@router.get("", response_model=list[PlaylistOut])
def list_imported(db: Session = Depends(get_db)):
    return [PlaylistOut.model_validate(p) for p in list_playlists(db)]


@router.get("/{playlist_id}", response_model=PlaylistOut)
def playlist_detail(playlist_id: int, db: Session = Depends(get_db)):
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    return PlaylistOut.model_validate(playlist)


@router.delete("/{playlist_id}", response_model=PlaylistDeleteResult)
def remove_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Rimuove una playlist importata e i lead diventati orfani (non su disco, non in
    altre playlist, non in alcun set salvato). Ritorna quante tracce sono state rimosse."""
    removed = delete_playlist(db, playlist_id)
    if removed is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    return PlaylistDeleteResult(deleted_tracks=removed)


@router.get("/{playlist_id}/tracks", response_model=list[TrackOut])
def playlist_tracks(playlist_id: int, db: Session = Depends(get_db)):
    if get_playlist(db, playlist_id) is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    return [track_out(t) for t in tracks_for_playlist(db, playlist_id)]


@router.post("/{playlist_id}/discovered-tracks", response_model=PlaylistAddTrackResponse)
def add_discovered_track(playlist_id: int, req: PlaylistAddTrackRequest, db: Session = Depends(get_db)):
    """Aggiunge una traccia scoperta a questa playlist; write-back Spotify best-effort."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")

    platform = "spotify" if req.spotify_id else "manual"
    track, created = import_single_track(
        db, platform=platform, platform_track_id=req.spotify_id,
        title=req.title, artist=req.artist, isrc=req.isrc,
        duration_seconds=req.duration_seconds, url=req.url, artwork_url=req.album_art_url,
    )
    add_track_to_playlist(db, track, playlist)
    recount_playlist(db, playlist)
    db.commit()

    spotify_added = False
    spotify_error: str | None = None
    if req.spotify_id and playlist.platform == "spotify" and playlist.platform_playlist_id:
        try:
            SpotifyWebClient(db).add_tracks(playlist.platform_playlist_id, [req.spotify_id])
            spotify_added = True
        except SpotifyError as exc:
            spotify_error = str(exc)
            logger.warning("Write-back Spotify fallito per playlist %s: %s", playlist_id, exc)

    return PlaylistAddTrackResponse(
        created=created, track=track_out(track),
        spotify_added=spotify_added, spotify_error=spotify_error,
    )


@router.get("/library/gaps", response_model=GapAnalysisResponse)
def library_gaps(db: Session = Depends(get_db)):
    tracks = all_playable_tracks(db)
    gaps = analyze_gaps(tracks)
    return GapAnalysisResponse(
        scope="library", track_count=len(tracks),
        gaps=[GapOut(**g) for g in gaps],
    )


@router.get("/{playlist_id}/gaps", response_model=GapAnalysisResponse)
def playlist_gaps(playlist_id: int, db: Session = Depends(get_db)):
    if get_playlist(db, playlist_id) is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    tracks = tracks_for_playlist(db, playlist_id)
    gaps = analyze_gaps(tracks)
    return GapAnalysisResponse(
        scope="playlist", track_count=len(tracks),
        gaps=[GapOut(**g) for g in gaps],
    )
