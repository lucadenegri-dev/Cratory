"""Job unico di import/sync streaming in background (pattern scan_job:
mono-utente, un job alla volta, stato in memoria con lock).

Copre TUTTE le operazioni che prima erano sincrone nella richiesta HTTP e con
librerie di migliaia di brani (liked Spotify, playlist grosse) rischiavano
timeout/spinner infinito: import playlist/liked Spotify, import selettivo dei
liked (Spotify e SoundCloud), sync playlist (Spotify con prune, SoundCloud
additivo). Il fetch dalla piattaforma (la parte lenta) avviene DENTRO il job;
le validazioni rapide (playlist non trovata, non sincronizzabile, username
mancante...) restano sincrone nei router per un 404/409 immediato.

Nessuna logica di import duplicata: ogni handler richiama le funzioni esistenti
di services/playlist_import.py, passando on_progress per il progresso a grana
fine sul loop principale."""

import logging
import threading
from datetime import datetime, timezone

from app.db import SessionLocal
from app.integrations.soundcloud import (
    SoundCloudError,
    SoundCloudInvalidUrl,
    fetch_likes,
    fetch_playlist as sc_fetch_playlist,
    fetch_track,
)
from app.integrations.spotify import (
    SpotifyError,
    SpotifyNotConfigured,
    SpotifyNotConnected,
    SpotifyWebClient,
)
from app.repositories import get_playlist, list_playlists
from app.services.job_spawn import spawn as _spawn
from app.services.playlist_import import (
    LIKED_PLAYLIST_NAME,
    import_playlist,
    import_selected_liked_tracks,
    import_selected_soundcloud_likes,
    normalize_soundcloud_item,
    _soundcloud_page_url,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "kind": None,
    "phase": None,  # fetching | importing
    "processed": 0, "total": 0,
    "result": None,
    "current_label": None,
    "sync_all": None,
    "error": None, "error_code": None,
    "started_at": None, "finished_at": None,
}


def _state_snapshot() -> dict:
    """Copia di `_state` senza acquisire `_lock`: solo per un chiamante che lo
    tiene gia' (vedi `start_job`) — `threading.Lock` non e' rientrante."""
    return dict(_state)


def job_state() -> dict:
    with _lock:
        return _state_snapshot()


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _progress(done: int, total: int) -> None:
    _state.update(processed=done, total=total)


# --- Sincronizzabilita' di una playlist (condivisa da router e job: la stessa
# validazione, niente logica duplicata) ---------------------------------------

def sync_error_for(playlist) -> tuple[str, str] | None:
    """None se la playlist e' sincronizzabile, altrimenti (code, message) per il 409."""
    if playlist.platform == "soundcloud":
        # I liked SoundCloud crescono solo via flusso selettivo: niente sync totale.
        if playlist.kind == "liked" or not playlist.url:
            return (
                "soundcloud_playlist_not_syncable",
                "SoundCloud playlists can't be synced: use the selective likes flow or re-import the URL.",
            )
        return None
    if playlist.platform != "spotify":
        return ("playlist_platform_not_syncable", "Only Spotify and SoundCloud playlists can be synced.")
    if playlist.kind != "liked" and not playlist.platform_playlist_id:
        return ("playlist_not_syncable", "This playlist can't be synced from Spotify.")
    return None


def syncable_playlists(db) -> list:
    """Le playlist riallineabili in blocco, nell'ordine di `list_playlists`.

    Esclude i liked di entrambe le piattaforme (crescono per selezione manuale,
    non per sync totale) e tutto ciò che `sync_error_for` già rifiuta: playlist
    manuali, Spotify senza `platform_playlist_id`, SoundCloud senza URL."""
    return [
        p for p in list_playlists(db)
        if p.kind != "liked" and sync_error_for(p) is None
    ]


# --- Handler per kind ----------------------------------------------------------

def _run_spotify_playlist(db, params: dict) -> dict:
    playlist_id = params["playlist_id"]
    client = SpotifyWebClient(db)
    try:
        playlist_meta = client.get_playlist_meta(playlist_id)
        items = client.get_playlist_tracks(playlist_id)
        _state["phase"] = "importing"
        images = playlist_meta.get("images") or []
        return import_playlist(
            db, platform="spotify",
            name=playlist_meta.get("name") or "Playlist Spotify",
            items=items,
            platform_playlist_id=playlist_id,
            owner=(playlist_meta.get("owner") or {}).get("display_name"),
            url=(playlist_meta.get("external_urls") or {}).get("spotify"),
            artwork_url=images[0]["url"] if images else None,
            on_progress=_progress,
        )
    finally:
        client.close()


def _run_spotify_liked(db, params: dict) -> dict:
    client = SpotifyWebClient(db)
    try:
        items = client.get_liked_tracks()
        _state["phase"] = "importing"
        return import_playlist(
            db, platform="spotify", name=LIKED_PLAYLIST_NAME,
            items=items, kind="liked", on_progress=_progress,
        )
    finally:
        client.close()


def _run_spotify_liked_selected(db, params: dict) -> dict:
    client = SpotifyWebClient(db)
    try:
        items = client.get_liked_tracks()
    finally:
        client.close()
    _state["phase"] = "importing"
    return import_selected_liked_tracks(db, items, params["spotify_ids"], on_progress=_progress)


def _run_soundcloud_sync(db, playlist, on_progress=_progress) -> dict:
    info = sc_fetch_playlist(playlist.url)
    thumbnails = info.get("thumbnails") or []
    _state["phase"] = "importing"
    # Additivo (prune=False): su SoundCloud un takedown non significa "non mi
    # interessa piu'" — il lead resta collegato. Titolo/uploader/copertina
    # riletti dalla sorgente, con fallback ai valori attuali (A25).
    return import_playlist(
        db, platform="soundcloud",
        name=info.get("title") or playlist.name, items=info["entries"],
        normalize=normalize_soundcloud_item,
        platform_playlist_id=playlist.platform_playlist_id,
        owner=info.get("uploader") or playlist.owner, url=playlist.url,
        artwork_url=(thumbnails[-1].get("url") if thumbnails else playlist.artwork_url),
        kind=playlist.kind, prune=False, on_progress=on_progress,
    )


def _run_spotify_sync(db, playlist, on_progress=_progress) -> dict:
    client = SpotifyWebClient(db)
    # I liked non hanno meta: nome di sistema fisso. Le playlist vere rileggono
    # nome/owner/url/copertina dalla sorgente (A25), con fallback ai valori attuali.
    name, owner, url, artwork = playlist.name, playlist.owner, playlist.url, playlist.artwork_url
    try:
        if playlist.kind == "liked":
            items = client.get_liked_tracks()
        else:
            meta = client.get_playlist_meta(playlist.platform_playlist_id)
            items = client.get_playlist_tracks(playlist.platform_playlist_id)
            images = meta.get("images") or []
            name = meta.get("name") or name
            owner = (meta.get("owner") or {}).get("display_name") or owner
            url = (meta.get("external_urls") or {}).get("spotify") or url
            artwork = images[0]["url"] if images else artwork
    finally:
        client.close()
    _state["phase"] = "importing"
    return import_playlist(
        db, platform="spotify", name=name, items=items,
        platform_playlist_id=playlist.platform_playlist_id,
        owner=owner, url=url, artwork_url=artwork,
        kind=playlist.kind, prune=True, on_progress=on_progress,
    )


def _run_playlist_sync(db, params: dict) -> dict:
    playlist = get_playlist(db, params["playlist_id"])
    if playlist is None:
        # Rete di sicurezza: il router valida gia' prima di avviare il job
        # (finestra di gara praticamente irraggiungibile in un'app locale
        # mono-utente), quindi qui non serve un codice errore dedicato.
        raise RuntimeError("Playlist not found")
    err = sync_error_for(playlist)
    if err:
        raise RuntimeError(err[1])
    if playlist.platform == "soundcloud":
        return _run_soundcloud_sync(db, playlist)
    return _run_spotify_sync(db, playlist)


def _run_playlists_sync_all(db, params: dict) -> dict:
    """Riallinea tutte le playlist sincronizzabili, una alla volta.

    Una playlist che fallisce finisce in `failures` e il giro prosegue: su una
    sync di massa una playlist morta non deve invalidare le altre. La barra
    avanza sulle playlist; il progresso interno vive in `current_label`."""
    playlists = syncable_playlists(db)
    _state.update(total=len(playlists), processed=0)
    report: dict = {
        "synced": 0, "failed": 0,
        "created": 0, "updated": 0, "removed": 0, "skipped": 0,
        "failures": [],
    }
    # Credenziali Spotify assenti/scadute: vale per tutte le sue playlist, non ha
    # senso ripetere la stessa chiamata di rete una volta per playlist.
    spotify_dead: str | None = None

    for done, playlist in enumerate(playlists):
        _state.update(processed=done, phase="fetching", current_label=playlist.name)

        def on_progress(processed: int, total: int, name: str = playlist.name) -> None:
            _state["current_label"] = f"{name} · {processed}/{total}"

        try:
            if playlist.platform == "soundcloud":
                one = _run_soundcloud_sync(db, playlist, on_progress=on_progress)
            elif spotify_dead is not None:
                raise SpotifyNotConnected(spotify_dead)
            else:
                one = _run_spotify_sync(db, playlist, on_progress=on_progress)
        except Exception as exc:  # noqa: BLE001 — l'errore è dato di report, non un crash
            db.rollback()
            if isinstance(exc, (SpotifyNotConnected, SpotifyNotConfigured)) and spotify_dead is None:
                spotify_dead = str(exc)
            report["failed"] += 1
            report["failures"].append({
                "playlist_id": playlist.id, "name": playlist.name,
                "platform": playlist.platform, "error": str(exc),
            })
            logger.warning("Sync di massa: playlist '%s' fallita: %s", playlist.name, exc)
        else:
            report["synced"] += 1
            for key in ("created", "updated", "removed", "skipped"):
                report[key] += one.get(key, 0)

    _state.update(processed=len(playlists), current_label=None)
    return report


def _run_soundcloud_playlist(db, params: dict) -> dict:
    url = params["url"]
    info = sc_fetch_playlist(url)
    thumbnails = info.get("thumbnails") or []
    _state["phase"] = "importing"
    return import_playlist(
        db, platform="soundcloud",
        name=info.get("title") or "Playlist SoundCloud",
        items=info["entries"], normalize=normalize_soundcloud_item,
        platform_playlist_id=str(info["id"]) if info.get("id") else None,
        owner=info.get("uploader"),
        url=url.strip(),  # conserva il secret link incollato (resta solo nel DB locale)
        artwork_url=thumbnails[-1].get("url") if thumbnails else None,
        on_progress=_progress,
    )


def _run_soundcloud_likes_selected(db, params: dict) -> dict:
    """Rifetcha ogni like selezionato in modalita' piena (uploader/durata veri);
    se il fetch pieno fallisce si ripiega sull'entry flat (meglio un lead povero
    che un lead perso)."""
    info = fetch_likes(params["username"], limit=params.get("limit"))
    track_ids = params["track_ids"]
    wanted = {str(t) for t in track_ids}
    selected = [e for e in info["entries"] if e and str(e.get("id")) in wanted]
    full: list[dict] = []
    for entry in selected:
        # In flat mode entry["url"] e' spesso lo stream CDN temporaneo (host
        # media-streaming.soundcloud.cloud): passato a fetch_track verrebbe
        # rifiutato da _validate_url e si ripiegherebbe sull'entry flat. Si
        # preferisce la pagina pubblica (stessa guardia di normalize_soundcloud_item).
        track_url = _soundcloud_page_url(
            entry.get("webpage_url"), entry.get("permalink_url"), entry.get("url"),
        )
        try:
            full.append(fetch_track(track_url) if track_url else entry)
        except SoundCloudError:
            full.append(entry)
    _state["phase"] = "importing"
    return import_selected_soundcloud_likes(db, full, track_ids, on_progress=_progress)


_RUNNERS = {
    "spotify_playlist": _run_spotify_playlist,
    "spotify_liked": _run_spotify_liked,
    "spotify_liked_selected": _run_spotify_liked_selected,
    "playlist_sync": _run_playlist_sync,
    "playlists_sync_all": _run_playlists_sync_all,
    "soundcloud_playlist": _run_soundcloud_playlist,
    "soundcloud_likes_selected": _run_soundcloud_likes_selected,
}


def _spotify_error_code(exc: SpotifyError) -> str:
    if isinstance(exc, SpotifyNotConfigured):
        return "spotify_not_configured"
    if isinstance(exc, SpotifyNotConnected):
        return "spotify_not_connected"
    return "spotify_error"


def _soundcloud_error_code(exc: SoundCloudError) -> str:
    if isinstance(exc, SoundCloudInvalidUrl):
        return "soundcloud_invalid_url"
    return "soundcloud_error"


def _run(kind: str, params: dict) -> None:
    db = SessionLocal()
    try:
        report = _RUNNERS[kind](db, params)
        # Il sync di massa produce un aggregato, non il report di una playlist:
        # vive in un campo suo (`result` resta None per quel kind).
        key = "sync_all" if kind == "playlists_sync_all" else "result"
        _state.update(status="done", phase=None, current_label=None, **{key: report})
        logger.info("Job import/sync streaming completato (%s): %s", kind, report)
    except SpotifyError as exc:
        _state.update(status="error", error=str(exc), error_code=_spotify_error_code(exc))
        logger.warning("Job import/sync streaming fallito (%s, Spotify): %s", kind, exc)
    except SoundCloudError as exc:
        _state.update(status="error", error=str(exc), error_code=_soundcloud_error_code(exc))
        logger.warning("Job import/sync streaming fallito (%s, SoundCloud): %s", kind, exc)
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc), error_code=None)
        logger.exception("Job import/sync streaming fallito (%s, inatteso)", kind)
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


def start_job(kind: str, **params) -> dict:
    """Avvia il job. No-op (stato invariato) se gia' in corso — il chiamante (router)
    e' responsabile del 409 esplicito quando is_running() e' gia' vero."""
    with _lock:
        if _state["status"] == "running":
            return _state_snapshot()
        _state.update(status="running", kind=kind, phase="fetching",
                      processed=0, total=0, result=None, sync_all=None,
                      current_label=None, error=None, error_code=None,
                      started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
    _spawn(lambda: _run(kind, params))
    return job_state()
