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
from app.repositories import (
    file_tags_for_tracks, get_track, tracks_download_pending, tracks_without_local_file,
)
from app.schemas import TrackOut
from app.serializers import track_out
from app.services import download_queue as dlqueue
from app.services.download_dispatcher import fill
from app.services.soulseek_select import (
    AUTO_PICK_MIN_CONFIDENCE, QualityPreference, auto_pick_quality_ok, query_variants,
    rank_candidates,
)
from app.services.download_review import (
    NoReviewFileError, discard_downloaded, keep_downloaded, review_detail,
)
from app.services.auto_link import auto_link_preview
from app.services.track_label import track_label
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


# Ricerca manuale: budget pieno come il job in background, non quello ridotto
# della cascata (l'utente sta guardando uno spinner e preferisce risultati
# completi a una risposta rapida e mezza vuota).
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
        # Il badge promette «l'auto-pick l'avrebbe accettato»: entrambe le sue
        # barriere, confidenza E qualita' (qui la confidenza arriva da un
        # ranking con soglia bitrate rilassata, che da sola mentirebbe).
        auto_ok=(confidence is not None and confidence >= AUTO_PICK_MIN_CONFIDENCE
                 and auto_pick_quality_ok(f)),
    )


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


@router.post("/retry-pending")
def retry_pending():
    """Ritenta l'auto-pick su tutte le "da sistemare": le accoda tutte.

    Nessun 409 da "download gia' in corso": la coda assorbe il lotto e la
    deduplica di `enqueue` salta quelle gia' in attesa o in lavorazione, quindi
    ripremere il pulsante non raddoppia il lavoro.
    """
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    db = SessionLocal()
    try:
        added, skipped = dlqueue.enqueue(
            db, [t.id for t in tracks_download_pending(db)])
    finally:
        db.close()
    if added:
        fill()
    return {"enqueued": added, "skipped": skipped}


@router.get("/status")
def status():
    """Forma invariata: la barra globale del frontend legge queste chiavi.

    `total`/`processed` raccontano solo il "giro" corrente (le tracce
    accodate da quando la coda, l'ultima volta, non aveva nulla di attivo),
    non l'intero storico mai accodato — vedi `download_queue.current_round_items`.
    A coda ferma restano quelli dell'ultimo giro concluso, non zero. Gli item
    annullati non contano mai.
    """
    db = SessionLocal()
    try:
        items = dlqueue.current_round_items(db)
        by_outcome = {"downloaded": 0, "needs_review": 0, "not_found": 0, "failed": 0}
        for i in items:
            if i.outcome in by_outcome:
                by_outcome[i.outcome] += 1
        running = [i for i in items if i.state == "running"]
        done = [i for i in items if i.state == "done"]
        label = None
        if running:
            track = get_track(db, running[0].track_id)
            label = track_label(track) if track is not None else None
        return {
            "available": slskd_configured(),
            "status": "running" if running or any(i.state == "queued" for i in items)
                      else ("done" if items else "idle"),
            "processed": len(done),
            "total": len(items),
            **by_outcome,
            # Non piu' significativo: la coda mescola item di provenienze
            # diverse, non c'e' piu' "la playlist del job in corso".
            "playlist_id": None,
            "items": [{"track_id": i.track_id, "artist": None, "title": None,
                       "outcome": i.outcome, "reason": i.error} for i in done],
            # Non c'e' piu' un errore di job: un fallimento e' dell'item, e
            # viaggia nel suo `reason`.
            "error": None,
            "current_label": label,
        }
    finally:
        db.close()


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


@router.post("/playlist/{playlist_id}")
def download_playlist(playlist_id: int):
    """Accoda in auto-pick tutte le tracce della playlist senza file locale."""
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    db = SessionLocal()
    try:
        added, skipped = dlqueue.enqueue(
            db, [t.id for t in tracks_without_local_file(db, playlist_id)])
    finally:
        db.close()
    if added:
        fill()
    return {"enqueued": added, "skipped": skipped}


@router.post("/track")
def download_track(req: TrackDownloadIn):
    """Accoda una traccia col candidato che l'utente ha scelto lui.

    Il candidato viaggia nel `payload` dell'item: e' cosi' che il runner sa di
    non dover rifare l'auto-pick (e di dover saltare il guard sulla durata,
    che protegge la scelta automatica, non quella umana).
    """
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise api_error(404, "track_not_found", "Track not found.")
        added, skipped = dlqueue.enqueue(db, [req.track_id], kind="soulseek_chosen",
                                         payload=req.candidate.model_dump())
    finally:
        db.close()
    if added:
        fill()
    return {"enqueued": added, "skipped": skipped}


@router.post("/track/auto")
def download_track_auto(req: TrackAutopickIn):
    """Accoda una traccia in auto-pick (es. 'Scarica ora' dalla tracklist di un
    lead Discovery): nessun candidato scelto dall'utente, la cascata di ricerca
    la fa il runner. Nessun vincolo di concorrenza: ci pensa la coda."""
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise api_error(404, "track_not_found", "Track not found.")
        added, skipped = dlqueue.enqueue(db, [req.track_id], kind="soulseek_auto")
    finally:
        db.close()
    if added:
        fill()
    return {"enqueued": added, "skipped": skipped}


@router.post("/track/soundcloud")
def download_track_soundcloud(req: TrackSoundcloudIn):
    """Accoda il download via yt-dlp dell'audio di una traccia SoundCloud (dal
    dettaglio traccia), che il runner collega poi come file posseduto.

    Stessa coda del download Soulseek — non piu' "uno alla volta": cambia solo
    il `kind` dell'item, che dice al runner di passare da yt-dlp e non da slskd.
    """
    if not soundcloud_available():
        raise api_error(409, "ytdlp_unavailable", "yt-dlp not available on the backend.")
    if not _ffmpeg_available():
        raise api_error(409, "ffmpeg_unavailable", "ffmpeg not available on the backend.")
    if not runtime_settings.slskd_download_dir():
        raise api_error(409, "download_dir_not_configured",
                        "Download dir not configured (SLSKD_DOWNLOAD_DIR).")
    db = SessionLocal()
    try:
        track = get_track(db, req.track_id)
        if track is None:
            raise api_error(404, "track_not_found", "Track not found.")
        if track.platform != "soundcloud" or not track.url:
            raise api_error(422, "not_a_soundcloud_track", "Track has no SoundCloud URL.")
        added, skipped = dlqueue.enqueue(db, [track.id], kind="soundcloud")
    finally:
        db.close()
    if added:
        fill()
    return {"enqueued": added, "skipped": skipped}


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
