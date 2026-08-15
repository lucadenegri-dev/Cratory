"""HTTP per l'acquisizione file via slskd. Nessuna logica di business qui."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core import runtime_settings
from app.core.http_errors import api_error
from app.db import SessionLocal, get_db
from app.integrations.slskd import (
    SlskdError, SlskdFile, get_slskd_client, slskd_configured,
)
from app.integrations.soundcloud import soundcloud_available
from app.repositories import file_tags_for_tracks, get_track, tracks_download_pending
from app.services import soulseek_download_job as job
from app.schemas import TrackOut
from app.serializers import track_out
from app.services.soulseek_select import (
    AUTO_PICK_MIN_CONFIDENCE, QualityPreference, query_variants, rank_candidates,
    search_candidates,
)
from app.services.download_review import (
    NoReviewFileError, discard_downloaded, keep_downloaded, review_detail,
)
from app.services.auto_link import auto_link_preview
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


class CandidateOut(BaseModel):
    username: str
    filename: str
    size: int | None = None
    bitrate: int | None = None
    length: int | None = None
    format: str | None = None
    name_score: float = 0.0
    quality_tier: int = 0
    confidence: float = 0.0


class CandidatesIn(BaseModel):
    artist: str
    title: str
    # Durata attesa (dalla Track): premia la versione giusta nel ranking.
    duration_seconds: int | None = None


class TrackDownloadIn(BaseModel):
    track_id: int
    candidate: CandidateOut


class TrackAutopickIn(BaseModel):
    track_id: int


class TrackSoundcloudIn(BaseModel):
    track_id: int


class ReviewActionIn(BaseModel):
    track_id: int


class AutoLinkHit(BaseModel):
    path: str
    name: str
    format: str | None = None
    size: int | None = None
    source: str


class AutoLinkProposal(BaseModel):
    track_id: int
    label: str
    artist: str | None = None
    title: str | None = None
    hit: AutoLinkHit | None = None


# Ricerca manuale: budget pieno come il job in background (l'utente sta
# guardando uno spinner e preferisce risultati completi ai 5s di /candidates).
MANUAL_SEARCH_MAX_WAIT = 15.0


class SearchIn(BaseModel):
    query: str
    # Con track_id i risultati vengono arricchiti con score/confidenza
    # (artista/titolo/durata attesa della Track) e la risposta include le
    # varianti di query dell'auto-pick come suggerimenti.
    track_id: int | None = None


class SearchFileOut(BaseModel):
    username: str
    filename: str
    size: int | None = None
    bitrate: int | None = None
    length: int | None = None
    format: str | None = None
    has_free_slot: bool = True
    queue_length: int | None = None
    upload_speed: int | None = None
    # Presenti solo con contesto traccia: guidano ordinamento e badge, MAI esclusioni.
    score: float | None = None
    confidence: float | None = None
    auto_ok: bool = False


class SearchOut(BaseModel):
    variants: list[str]
    results: list[SearchFileOut]


def _search_file_out(f: SlskdFile, *, score: float | None = None,
                     confidence: float | None = None) -> SearchFileOut:
    return SearchFileOut(
        username=f.username, filename=f.filename, size=f.size, bitrate=f.bitrate,
        length=f.length, format=f.extension or None, has_free_slot=f.has_free_slot,
        queue_length=f.queue_length, upload_speed=f.upload_speed,
        score=score, confidence=confidence,
        auto_ok=confidence is not None and confidence >= AUTO_PICK_MIN_CONFIDENCE,
    )


def _candidate_out(c) -> CandidateOut:
    return CandidateOut(
        username=c.file.username, filename=c.file.filename, size=c.file.size,
        bitrate=c.file.bitrate, length=c.file.length, format=c.file.extension or None,
        name_score=c.name_score, quality_tier=c.quality_tier, confidence=c.confidence,
    )


def _slskd_file(c: CandidateOut) -> SlskdFile:
    return SlskdFile(username=c.username, filename=c.filename, size=c.size,
                     bitrate=c.bitrate, length=c.length, has_free_slot=True,
                     queue_length=None)


def _ffmpeg_available() -> bool:
    """ffmpeg presente? Serve al postprocessor MP3 di yt-dlp."""
    import shutil

    return shutil.which("ffmpeg") is not None


@router.get("/pending", response_model=list[TrackOut])
def download_pending(db: Session = Depends(get_db)):
    """Le "da sistemare": wishlist con esito download da rivedere/non trovata/fallita.

    Persistite sulla Track: sopravvivono a job, sessioni e riavvii.
    """
    tracks = tracks_download_pending(db)
    ft_map = file_tags_for_tracks(db, [t.id for t in tracks])
    return [track_out(t, ft_map.get(t.id)) for t in tracks]


@router.delete("/pending/{track_id}", response_model=TrackOut)
def ignore_pending(track_id: int, db: Session = Depends(get_db)):
    """Ignora una "da sistemare": azzera l'esito e la traccia esce dall'archivio."""
    track = get_track(db, track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found.")
    track.last_download_outcome = None
    track.last_download_reason = None
    db.commit()
    db.refresh(track)
    return track_out(track, file_tags_for_tracks(db, [track.id]).get(track.id))


@router.post("/retry-pending", status_code=202)
def retry_pending():
    """Ritenta l'auto-pick su tutte le "da sistemare". 409 se un job e' in corso."""
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    if job.is_running():
        raise api_error(409, "download_already_running", "A download is already running.")
    return job.start_retry_job()


@router.get("/status")
def status():
    return {"available": slskd_configured(), **job.job_state()}


@router.post("/candidates", response_model=list[CandidateOut])
def candidates(req: CandidatesIn):
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    client = get_slskd_client()
    try:
        # Cascata di varianti di query: la letterale spesso esclude file validi.
        ranked = search_candidates(client, artist=req.artist,
                                   title=req.title,
                                   expected_duration=req.duration_seconds)
    except SlskdError as exc:
        raise api_error(502, "slskd_error", f"slskd error: {exc}", reason=str(exc)) from exc
    finally:
        client.close()
    return [_candidate_out(c) for c in ranked]


@router.post("/search", response_model=SearchOut)
def search(req: SearchIn, db: Session = Depends(get_db)):
    """Ricerca manuale Soulseek: UNA ricerca con la query letterale dell'utente.

    Niente cascata di varianti (resta esclusiva dell'auto-pick) e niente filtro
    a soglia: comanda l'utente, il ranking e' solo una guida. Restano fuori i
    soli file non-audio (estensione sconosciuta).
    """
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    track = None
    if req.track_id is not None:
        track = get_track(db, req.track_id)
        if track is None:
            raise api_error(404, "track_not_found", "Track not found.")
    client = get_slskd_client()
    try:
        files = client.search(req.query, "", max_wait=MANUAL_SEARCH_MAX_WAIT,
                              search_timeout_ms=int((MANUAL_SEARCH_MAX_WAIT - 1.0) * 1000))
    except SlskdError as exc:
        raise api_error(502, "slskd_error", f"slskd error: {exc}", reason=str(exc)) from exc
    finally:
        client.close()
    if track is None:
        return SearchOut(variants=[], results=[_search_file_out(f) for f in files])
    # min_bitrate=1: anche la bassa qualita' deve comparire (tier>0);
    # min_name_score=0.0: anche i nomi pessimi. Il ranking ordina, non esclude.
    ranked = rank_candidates(files, artist=track.artist or "", title=track.title or "",
                             pref=QualityPreference(min_bitrate=1), min_name_score=0.0,
                             expected_duration=track.duration_seconds)
    return SearchOut(
        variants=query_variants(track.artist or "", track.title or ""),
        results=[_search_file_out(c.file, score=c.score, confidence=c.confidence)
                 for c in ranked],
    )


@router.post("/playlist/{playlist_id}", status_code=202)
def download_playlist(playlist_id: int):
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    if job.is_running():
        raise api_error(409, "download_already_running", "A download is already running.")
    return {"available": True, **job.start_playlist_job(playlist_id)}


@router.post("/track", status_code=202)
def download_track(req: TrackDownloadIn):
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    if job.is_running():
        raise api_error(409, "download_already_running", "A download is already running.")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise api_error(404, "track_not_found", "Track not found.")
    finally:
        db.close()
    return {"available": True, **job.start_track_job(req.track_id, _slskd_file(req.candidate))}


@router.post("/track/auto", status_code=202)
def download_track_auto(req: TrackAutopickIn):
    """Download immediato in auto-pick di una singola traccia (es. 'Scarica
    ora' dalla tracklist di un lead Discovery): nessun candidato scelto
    dall'utente, stessa cascata di ricerca del job playlist."""
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    if job.is_running():
        raise api_error(409, "download_already_running", "A download is already running.")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise api_error(404, "track_not_found", "Track not found.")
    finally:
        db.close()
    return {"available": True, **job.start_track_autopick_job(req.track_id)}


@router.post("/track/soundcloud", status_code=202)
def download_track_soundcloud(req: TrackSoundcloudIn):
    """Scarica via yt-dlp l'audio di una singola traccia SoundCloud (dal dettaglio
    traccia) e la collega come file posseduto. Stessa barra/job del download
    Soulseek: un solo download alla volta."""
    if not soundcloud_available():
        raise api_error(409, "ytdlp_unavailable", "yt-dlp not available on the backend.")
    if not _ffmpeg_available():
        raise api_error(409, "ffmpeg_unavailable", "ffmpeg not available on the backend.")
    if not runtime_settings.slskd_download_dir():
        raise api_error(409, "download_dir_not_configured",
                        "Download dir not configured (SLSKD_DOWNLOAD_DIR).")
    if job.is_running():
        raise api_error(409, "download_already_running", "A download is already running.")
    db = SessionLocal()
    try:
        track = get_track(db, req.track_id)
        if track is None:
            raise api_error(404, "track_not_found", "Track not found.")
        if track.platform != "soundcloud" or not track.url:
            raise api_error(422, "not_a_soundcloud_track", "Track has no SoundCloud URL.")
        return {"available": True, **job.start_soundcloud_track_job(track.id)}
    finally:
        db.close()


@router.get("/review/{track_id}")
def review(track_id: int, db: Session = Depends(get_db)):
    """Confronto atteso-vs-scaricato per un needs_review-per-durata."""
    track = get_track(db, track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found.")
    return review_detail(db, track)


@router.post("/keep-review", response_model=TrackOut)
def keep_review(req: ReviewActionIn, db: Session = Depends(get_db)):
    """Tieni il file dubbio già scaricato: lo aggancia e svuota l'esito."""
    track = get_track(db, req.track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found.")
    try:
        track = keep_downloaded(db, track)
    except NoReviewFileError as exc:
        raise api_error(409, "download_review_error", f"Download review error: {exc}",
                         reason=str(exc)) from exc
    return track_out(track, file_tags_for_tracks(db, [track.id]).get(track.id))


@router.post("/discard-review", response_model=TrackOut)
def discard_review(req: ReviewActionIn, db: Session = Depends(get_db)):
    """Scarta il file dubbio: lo elimina dall'inbox e sgancia la traccia."""
    track = get_track(db, req.track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found.")
    discarded = discard_downloaded(db, track)
    return track_out(discarded, file_tags_for_tracks(db, [discarded.id]).get(discarded.id))


@router.get("/auto-link", response_model=list[AutoLinkProposal])
def auto_link(db: Session = Depends(get_db)):
    """Proposte di collegamento file-locale per tutte le tracce da sistemare.

    Sola lettura: non collega nulla, restituisce (traccia, miglior match locale).
    Il collegamento vero passa per POST /api/tracks/{id}/link-file dopo la conferma.
    """
    return auto_link_preview(db)
