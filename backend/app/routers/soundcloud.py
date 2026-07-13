"""HTTP only: stato/config SoundCloud, import playlist da URL, like selettivi."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.integrations.soundcloud import (
    SoundCloudError,
    SoundCloudInvalidUrl,
    fetch_likes,
    is_likes_url,
    soundcloud_available,
    ytdlp_version,
)
from app.schemas import (
    SoundCloudConfigRequest,
    SoundCloudImportRequest,
    SoundCloudLikedSelectedRequest,
    SoundCloudLikedTrackPreview,
    SoundCloudStatus,
    StreamingImportJobStatus,
)
from app.services import streaming_import_job
from app.services.app_state import get_state, set_state
from app.services.playlist_import import preview_soundcloud_likes

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


@router.post("/import", response_model=StreamingImportJobStatus, status_code=202)
def import_from_url(req: SoundCloudImportRequest, db: Session = Depends(get_db)):
    """Avvia in background l'import di una playlist SoundCloud (pubblica o secret
    link) come lead. Segui lo stato con GET /api/playlists/import/status."""
    if is_likes_url(req.url):
        raise api_error(
            422, "soundcloud_likes_url_not_supported",
            "For likes, use the 'My likes' flow (selective import).",
        )
    if streaming_import_job.is_running():
        raise api_error(
            409, "streaming_import_already_running",
            "A streaming import/sync is already running: wait for it to finish and try again.",
        )
    return streaming_import_job.start_job("soundcloud_playlist", url=req.url)


@router.get("/likes/preview", response_model=list[SoundCloudLikedTrackPreview])
def likes_preview(limit: int | None = None, db: Session = Depends(get_db)):
    """Anteprima dei like, selezionabili. Non importa nulla. Senza `limit`: tutti."""
    username = _username_or_409(db)
    try:
        info = fetch_likes(username, limit=limit)
    except SoundCloudError as exc:
        raise _http_error(exc) from exc
    return [SoundCloudLikedTrackPreview(**p) for p in preview_soundcloud_likes(db, info["entries"])]


@router.post("/import/likes", response_model=StreamingImportJobStatus, status_code=202)
def import_likes(req: SoundCloudLikedSelectedRequest, db: Session = Depends(get_db)):
    """Avvia in background l'import dei SOLI like selezionati (additivo). Segui lo
    stato con GET /api/playlists/import/status.

    Stateless: il job rifetcha e filtra per id. Le entry flat dei like non hanno
    uploader né durata: ogni selezionata viene ri-fetchata in modalità piena
    (~1s l'una, da cui lo spostamento in background). Se il fetch pieno fallisce
    si ripiega sull'entry flat: meglio un lead povero che un lead perso.
    """
    username = _username_or_409(db)
    if streaming_import_job.is_running():
        raise api_error(
            409, "streaming_import_already_running",
            "A streaming import/sync is already running: wait for it to finish and try again.",
        )
    return streaming_import_job.start_job(
        "soundcloud_likes_selected", username=username, track_ids=req.track_ids, limit=req.limit,
    )
