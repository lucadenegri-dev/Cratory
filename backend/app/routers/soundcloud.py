"""HTTP only: stato/config SoundCloud, import playlist da URL, like selettivi."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.integrations.soundcloud import (
    DEFAULT_LIKES_LIMIT,
    SoundCloudError,
    SoundCloudInvalidUrl,
    fetch_likes,
    fetch_playlist,
    fetch_track,
    is_likes_url,
    soundcloud_available,
    ytdlp_version,
)
from app.schemas import (
    PlaylistImportReport,
    SoundCloudConfigRequest,
    SoundCloudImportRequest,
    SoundCloudLikedSelectedRequest,
    SoundCloudLikedTrackPreview,
    SoundCloudStatus,
)
from app.services.app_state import get_state, set_state
from app.services.playlist_import import (
    import_playlist,
    import_selected_soundcloud_likes,
    normalize_soundcloud_item,
    preview_soundcloud_likes,
)

router = APIRouter(prefix="/api/soundcloud", tags=["soundcloud"])

USERNAME_KEY = "soundcloud_username"


def _http_error(exc: SoundCloudError) -> HTTPException:
    if isinstance(exc, SoundCloudInvalidUrl):
        return api_error(422, "soundcloud_invalid_url", str(exc), reason=str(exc))
    return api_error(502, "soundcloud_error", str(exc), reason=str(exc))


def _username_or_409(db: Session) -> str:
    username = get_state(db, USERNAME_KEY)
    if not username:
        raise api_error(409, "soundcloud_username_missing", "SoundCloud username not configured (Settings).")
    return username


@router.get("/status", response_model=SoundCloudStatus)
def status(db: Session = Depends(get_db)):
    return SoundCloudStatus(
        available=soundcloud_available(),
        ytdlp_version=ytdlp_version(),
        username=get_state(db, USERNAME_KEY),
    )


@router.put("/config", response_model=SoundCloudStatus)
def set_config(req: SoundCloudConfigRequest, db: Session = Depends(get_db)):
    username = req.username.strip().lstrip("@")
    if not username:
        raise api_error(422, "soundcloud_username_invalid", "Invalid SoundCloud username.")
    set_state(db, USERNAME_KEY, username)
    return status(db)


@router.post("/import", response_model=PlaylistImportReport)
def import_from_url(req: SoundCloudImportRequest, db: Session = Depends(get_db)):
    """Importa una playlist SoundCloud (pubblica o secret link) come lead."""
    if is_likes_url(req.url):
        raise api_error(
            422, "soundcloud_likes_url_not_supported",
            "For likes, use the 'My likes' flow (selective import).",
        )
    try:
        info = fetch_playlist(req.url)
    except SoundCloudError as exc:
        raise _http_error(exc) from exc
    thumbnails = info.get("thumbnails") or []
    report = import_playlist(
        db, platform="soundcloud",
        name=info.get("title") or "Playlist SoundCloud",
        items=info["entries"],
        normalize=normalize_soundcloud_item,
        platform_playlist_id=str(info["id"]) if info.get("id") else None,
        owner=info.get("uploader"),
        url=req.url.strip(),  # conserva il secret link incollato (resta solo nel DB locale)
        artwork_url=thumbnails[-1].get("url") if thumbnails else None,
    )
    return PlaylistImportReport(**report)


@router.get("/likes/preview", response_model=list[SoundCloudLikedTrackPreview])
def likes_preview(limit: int = DEFAULT_LIKES_LIMIT, db: Session = Depends(get_db)):
    """Anteprima dei like recenti, selezionabili. Non importa nulla."""
    username = _username_or_409(db)
    try:
        info = fetch_likes(username, limit=limit)
    except SoundCloudError as exc:
        raise _http_error(exc) from exc
    return [SoundCloudLikedTrackPreview(**p) for p in preview_soundcloud_likes(db, info["entries"])]


@router.post("/import/likes", response_model=PlaylistImportReport)
def import_likes(req: SoundCloudLikedSelectedRequest, db: Session = Depends(get_db)):
    """Importa SOLO i like selezionati. Stateless: rifetcha e filtra per id. Additivo.

    Le entry flat dei like non hanno uploader né durata: ogni selezionata viene
    ri-fetchata in modalità piena (~1s l'una). Se il fetch pieno fallisce si
    ripiega sull'entry flat: meglio un lead povero che un lead perso.
    """
    username = _username_or_409(db)
    try:
        info = fetch_likes(username, limit=req.limit)
    except SoundCloudError as exc:
        raise _http_error(exc) from exc
    wanted = {str(t) for t in req.track_ids}
    selected = [e for e in info["entries"] if e and str(e.get("id")) in wanted]
    full: list[dict] = []
    for entry in selected:
        track_url = entry.get("url") or entry.get("webpage_url")
        try:
            full.append(fetch_track(track_url) if track_url else entry)
        except SoundCloudError:
            full.append(entry)
    report = import_selected_soundcloud_likes(db, full, req.track_ids)
    return PlaylistImportReport(**report)
