"""Router playlist: punto di partenza del nuovo flusso (playlist streaming -> set).

- elenco playlist Spotify dell'utente (per la selezione),
- import di una playlist o dei liked,
- elenco/dettaglio playlist importate,
- analisi deterministica dei "buchi" di una playlist (o dell'intera libreria).
"""

import csv
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.models import Playlist, PlaylistSyncEvent, Track
from app.models import playlist_tracks as playlist_tracks_table
from app.integrations.spotify import (
    SpotifyError,
    SpotifyNotConfigured,
    SpotifyNotConnected,
    SpotifyWebClient,
)
from app.repositories import (
    FileTags,
    add_track_to_playlist,
    all_playable_tracks,
    delete_playlist,
    delete_playlist_track,
    delete_playlist_tracks,
    file_tags_for_tracks,
    get_playlist,
    list_playlists,
    recount_playlist,
    reorder_playlist_track,
    set_playlist_order,
    tracks_for_playlist,
)
from app.schemas import (
    GapAnalysisResponse,
    GapOut,
    LikedSelectedImportRequest,
    LikedTrackPreview,
    ManualImportRequest,
    PlaylistAddTracksRequest,
    PlaylistAddTracksResult,
    PlaylistBulkRemoveResult,
    PlaylistDeleteResult,
    PlaylistDuplicateRequest,
    PlaylistFromTracksRequest,
    PlaylistImportReport,
    PlaylistImportRequest,
    PlaylistOrderRequest,
    PlaylistOut,
    PlaylistRemoveTracksRequest,
    PlaylistReorderRequest,
    PlaylistSyncEventOut,
    PlaylistUpdateIn,
    SpotifyPlaylistRef,
    StreamingImportJobStatus,
    SyncTrackRef,
    TrackOut,
)
from app.serializers import track_out
from app.services import streaming_import_job
from app.services.export_render import render_m3u8
from app.services.gap_analysis import analyze_gaps
from app.services.manual_import import import_manual_playlist
from app.services.playlist_import import preview_liked_tracks

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
    finally:
        client.close()
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


def _streaming_job_or_409() -> None:
    if streaming_import_job.is_running():
        raise api_error(
            409, "streaming_import_already_running",
            "A streaming import/sync is already running: wait for it to finish and try again.",
        )


@router.post("/import", response_model=StreamingImportJobStatus, status_code=202)
def import_from_spotify(req: PlaylistImportRequest, db: Session = Depends(get_db)):
    """Avvia in background l'import (playlist o liked) da Spotify. Segui lo stato
    con GET /api/playlists/import/status. Il fetch, potenzialmente lento su
    librerie di migliaia di brani, avviene dentro il job."""
    _streaming_job_or_409()
    if req.playlist_id == "liked":
        return streaming_import_job.start_job("spotify_liked")
    return streaming_import_job.start_job("spotify_playlist", playlist_id=req.playlist_id)


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
    finally:
        client.close()
    return [LikedTrackPreview(**p) for p in preview_liked_tracks(db, items)]


@router.post("/import/liked/selected", response_model=StreamingImportJobStatus, status_code=202)
def import_liked_selected(req: LikedSelectedImportRequest, db: Session = Depends(get_db)):
    """Avvia in background l'import nella playlist Liked dei soli brani selezionati
    (additivo, niente prune). Segui lo stato con GET /api/playlists/import/status."""
    _streaming_job_or_409()
    return streaming_import_job.start_job("spotify_liked_selected", spotify_ids=req.spotify_ids)


@router.post("/{playlist_id}/sync", response_model=StreamingImportJobStatus, status_code=202)
def sync_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Avvia in background il riallineamento della playlist con la piattaforma
    d'origine: Spotify con prune, SoundCloud solo additivo. Segui lo stato con
    GET /api/playlists/import/status."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    err = streaming_import_job.sync_error_for(playlist)
    if err:
        raise api_error(409, err[0], err[1])
    _streaming_job_or_409()
    return streaming_import_job.start_job("playlist_sync", playlist_id=playlist_id)


@router.post("/sync-all", response_model=StreamingImportJobStatus, status_code=202)
def sync_all_playlists(db: Session = Depends(get_db)):
    """Avvia in background il riallineamento di TUTTE le playlist Spotify e
    SoundCloud importate; i liked sono esclusi (crescono per selezione manuale).
    Una playlist che fallisce non ferma le altre: l'elenco dei fallimenti è in
    `sync_all.failures` dello stato del job. Segui lo stato con
    GET /api/playlists/import/status."""
    if not streaming_import_job.syncable_playlists(db):
        raise api_error(
            409, "no_syncable_playlists",
            "No syncable playlists: only Spotify/SoundCloud playlists, liked excluded.",
        )
    _streaming_job_or_409()
    return streaming_import_job.start_job("playlists_sync_all")


@router.get("/import/status", response_model=StreamingImportJobStatus)
def import_status():
    return streaming_import_job.job_state()


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


@router.post("/{playlist_id}/duplicate", response_model=PlaylistOut, status_code=201)
def duplicate_playlist(playlist_id: int, req: PlaylistDuplicateRequest, db: Session = Depends(get_db)):
    """Fork: copia la playlist in una manuale (stesso ordine). Una playlist
    sincronizzata non e' riordinabile ne' editabile: la copia manuale si'.
    Le membership sono `added_by="cratory"` (mai toccate da un prune)."""
    src = get_playlist(db, playlist_id)
    if src is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    name = (req.name or f"{src.name} (copia)").strip()
    if not name:
        raise api_error(422, "playlist_name_empty", "Playlist name is empty.")
    copy = Playlist(platform="manual", name=name, kind="manual")
    db.add(copy)
    db.flush()  # serve copy.id per collegare le tracce
    for track in tracks_for_playlist(db, playlist_id):
        add_track_to_playlist(db, track, copy, added_by="cratory")
    recount_playlist(db, copy)
    db.commit()
    db.refresh(copy)
    return PlaylistOut.model_validate(copy)


@router.post("/{playlist_id}/add-tracks", response_model=PlaylistAddTracksResult)
def add_tracks(playlist_id: int, req: PlaylistAddTracksRequest, db: Session = Depends(get_db)):
    """Aggiunge tracce di libreria a una playlist esistente (idempotente).

    Le membership sono marcate `added_by="cratory"`, cosi' il prune del sync non
    le rimuove. Le tracce gia' presenti (o id ripetuti) contano come `skipped`.
    """
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    tracks = db.scalars(select(Track).where(Track.id.in_(req.track_ids))).all()
    by_id = {t.id: t for t in tracks}
    missing = [i for i in req.track_ids if i not in by_id]
    if missing:
        raise api_error(422, "tracks_not_found", f"Nonexistent tracks: {missing}", missing=missing)
    existing = {t.id for t in playlist.tracks}
    added = 0
    for track_id in req.track_ids:
        if track_id in existing:
            continue
        add_track_to_playlist(db, by_id[track_id], playlist, added_by="cratory")
        existing.add(track_id)
        added += 1
    skipped = len(req.track_ids) - added
    recount_playlist(db, playlist)
    db.commit()
    db.refresh(playlist)
    return PlaylistAddTracksResult(
        playlist=PlaylistOut.model_validate(playlist), added=added, skipped=skipped,
    )


# Kind con ordine posseduto dall'utente (nessuna sorgente che lo ridetta).
REORDERABLE_KINDS = {"manual", "shazam"}


def _reorderable_or_409(playlist: Playlist) -> None:
    if playlist.kind not in REORDERABLE_KINDS:
        raise api_error(409, "playlist_not_reorderable",
                        "Reorder is only allowed on manual and shazam playlists")


@router.post("/{playlist_id}/reorder", response_model=list[TrackOut])
def reorder_track(playlist_id: int, req: PlaylistReorderRequest, db: Session = Depends(get_db)):
    """Riordino manuale: sposta una traccia a una posizione (playlist manuali/shazam)."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    _reorderable_or_409(playlist)
    result = reorder_playlist_track(db, playlist_id, req.track_id, req.position)
    if result is None:
        raise api_error(404, "track_not_in_playlist", "Track is not in this playlist")
    db.commit()
    ft_map = file_tags_for_tracks(db, [t.id for t in result])
    return [track_out(t, ft_map.get(t.id)) for t in result]


@router.put("/{playlist_id}/order", response_model=list[TrackOut])
def set_order(playlist_id: int, req: PlaylistOrderRequest, db: Session = Depends(get_db)):
    """Sostituisce l'ordine completo (drag-and-drop): permutazione esatta dei membri."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    _reorderable_or_409(playlist)
    result = set_playlist_order(db, playlist_id, req.track_ids)
    if result is None:
        raise api_error(422, "order_mismatch",
                        "track_ids must be an exact permutation of the playlist members")
    db.commit()
    ft_map = file_tags_for_tracks(db, [t.id for t in result])
    return [track_out(t, ft_map.get(t.id)) for t in result]


@router.patch("/{playlist_id}", response_model=PlaylistOut)
def update_playlist(playlist_id: int, req: PlaylistUpdateIn, db: Session = Depends(get_db)):
    """Rename della playlist. Il nome scelto e' definitivo: `name_locked` impedisce
    al sync di risovrascriverlo dalla piattaforma (no-op sulle playlist manuali,
    che un sync non ce l'hanno)."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    name = req.name.strip()
    if not name:
        raise api_error(422, "playlist_name_empty", "Playlist name is empty.")
    playlist.name = name
    playlist.name_locked = True
    db.commit()
    db.refresh(playlist)
    return PlaylistOut.model_validate(playlist)


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


@router.delete("/{playlist_id}/tracks/{track_id}", response_model=PlaylistDeleteResult)
def remove_playlist_track(playlist_id: int, track_id: int, db: Session = Depends(get_db)):
    """Toglie una singola traccia dalla playlist. Se la traccia diventa un lead orfano
    (non su disco, non in altre playlist, non in alcun set salvato) viene rimossa; il
    conteggio orfani torna nel risultato. 404 se la playlist o la membership non esistono."""
    removed = delete_playlist_track(db, playlist_id, track_id)
    if removed is None:
        raise api_error(404, "playlist_track_not_found", "Track not in playlist")
    return PlaylistDeleteResult(deleted_tracks=removed)


@router.post("/{playlist_id}/tracks/remove", response_model=PlaylistBulkRemoveResult)
def remove_playlist_tracks(playlist_id: int, req: PlaylistRemoveTracksRequest, db: Session = Depends(get_db)):
    """Toglie piu' tracce dalla playlist (bulk). I lead diventati orfani vengono
    cancellati come nella rimozione singola; gli id non-membri sono ignorati."""
    result = delete_playlist_tracks(db, playlist_id, req.track_ids)
    if result is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    removed, deleted = result
    return PlaylistBulkRemoveResult(removed=removed, deleted_tracks=deleted)


@router.post("/{playlist_id}/export", response_class=PlainTextResponse)
def export_playlist(
    playlist_id: int,
    format: str = Query(default="m3u8", pattern="^(m3u8|csv|text|markdown)$"),
    db: Session = Depends(get_db),
):
    """Export della playlist in ordine playlist. M3U8 (importabile in Rekordbox,
    stessa logica dell'export set): punta ai file locali, le tracce senza file su
    disco sono escluse con un commento di conteggio. CSV/testo/Markdown includono
    invece TUTTE le tracce (anche i lead senza file)."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    tracks = tracks_for_playlist(db, playlist_id)  # già in ordine playlist
    # M6: genere effettivo (tag file se la traccia e' posseduta, altrimenti
    # streaming) anche negli export testuali, stessa regola della Library e
    # della vista playlist qui sopra — una sola query in piu' per l'export.
    ft_map = file_tags_for_tracks(db, [t.id for t in tracks])

    def _genre(t: Track) -> str | None:
        ft = ft_map.get(t.id) or FileTags()
        return ft.genre if ft.genre is not None else t.genre

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["position", "title", "artist", "genre", "bpm", "key", "energy",
                         "duration_seconds", "rating", "owned", "local_path", "url"])
        for i, t in enumerate(tracks, start=1):
            writer.writerow([i, t.title or "", t.artist or "", _genre(t) or "", t.bpm or "",
                             t.camelot_key or "", t.energy or "", t.duration_seconds or "",
                             t.rating or "", "1" if t.has_local_file else "0",
                             t.local_path or "", t.url or ""])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    if format == "markdown":
        md = [f"# {playlist.name}", "",
              "| # | Traccia | Genere | BPM | Key | Durata |",
              "|--:|---|---|--:|---|--:|"]
        for i, t in enumerate(tracks, start=1):
            label = f"{t.artist or '?'} — {t.title or '?'}"
            bpm = f"{t.bpm:.0f}" if t.bpm else "—"
            dur = f"{t.duration_seconds // 60}:{t.duration_seconds % 60:02d}" if t.duration_seconds else "—"
            md.append(f"| {i} | {label} | {_genre(t) or '—'} | {bpm} | {t.camelot_key or '—'} | {dur} |")
        return PlainTextResponse("\n".join(md), media_type="text/markdown")

    if format == "text":
        lines = [f"# {playlist.name}", ""]
        for i, t in enumerate(tracks, start=1):
            label = f"{t.artist or '?'} - {t.title or '?'}"
            meta = f" [{t.bpm:.0f} BPM, {t.camelot_key or '?'}]" if t.bpm else (f" [{t.camelot_key}]" if t.camelot_key else "")
            lines.append(f"{i}. {label}{meta}")
        return PlainTextResponse("\n".join(lines))

    # m3u8 (default): solo tracce con file locale
    owned = [t for t in tracks if t.local_path]
    return PlainTextResponse(render_m3u8(owned, len(tracks)), media_type="audio/x-mpegurl")


@router.get("/{playlist_id}/tracks", response_model=list[TrackOut])
def playlist_tracks(playlist_id: int, db: Session = Depends(get_db)):
    if get_playlist(db, playlist_id) is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    added_map = dict(db.execute(
        select(playlist_tracks_table.c.track_id, playlist_tracks_table.c.added_at)
        .where(playlist_tracks_table.c.playlist_id == playlist_id)
    ).all())
    members = tracks_for_playlist(db, playlist_id)
    # I3: senza questo i tag mostrati qui erano quelli streaming mentre
    # TrackEditModal (che precompila da questo stesso payload) salva sul file
    # via /api/organize/files/{primary_file_id}/tags — un utente che "correggeva"
    # il genere che vedeva qui sovrascriveva silenziosamente un tag del file mai
    # mostrato. Una sola query in piu' per l'intera playlist (non per traccia).
    ft_map = file_tags_for_tracks(db, [t.id for t in members])
    out = []
    for i, t in enumerate(members, start=1):
        row = track_out(t, ft_map.get(t.id))
        row.playlist_position = i
        row.playlist_added_at = added_map.get(t.id)
        out.append(row)
    return out


@router.get("/{playlist_id}/sync-log", response_model=list[PlaylistSyncEventOut])
def playlist_sync_log(playlist_id: int, limit: int = Query(default=20, ge=1, le=100),
                      db: Session = Depends(get_db)):
    """Ultimi diff di import/sync (piu' recente prima): cosa e' entrato e uscito."""
    if get_playlist(db, playlist_id) is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    events = db.scalars(
        select(PlaylistSyncEvent).where(PlaylistSyncEvent.playlist_id == playlist_id)
        .order_by(PlaylistSyncEvent.id.desc()).limit(limit)
    ).all()
    return [
        PlaylistSyncEventOut(
            id=e.id, created_at=e.created_at,
            added=[SyncTrackRef(**x) for x in (e.added_tracks or [])],
            removed=[SyncTrackRef(**x) for x in (e.removed_tracks or [])],
        )
        for e in events
    ]


@router.get("/library/gaps", response_model=GapAnalysisResponse)
def library_gaps(db: Session = Depends(get_db)):
    tracks = all_playable_tracks(db)
    gaps = analyze_gaps(tracks, scope="library")
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
