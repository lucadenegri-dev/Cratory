"""Shazam — identificazione delle tracce dei set DJ (Fase 1).

Un mix (URL SoundCloud/Mixcloud/YouTube) viene scaricato e le sue tracce identificate
via fingerprinting (services/mix_identify). Le tracce identificate (DjSetTrack) NON
entrano in libreria: restano legate al DjSet e serviranno come corpus per i
suggerimenti per co-occorrenza (Fase 2). L'analisi e' un job in background con polling.
"""

import importlib.util
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.models import DjSetTrack, Track
from app.repositories import ci_equals, delete_dj_set, get_dj_set, list_dj_sets
from app.schemas import DjSetCreateIn, DjSetOut, DjSetSummaryOut, PlaylistImportReport
from app.services import mix_identify_job
from app.services.manual_import import import_track_pairs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/shazam", tags=["shazam"])


def _match_library_tracks(db: Session, tracks: list[DjSetTrack]) -> dict[int, Track]:
    """Cross-match deterministico delle tracce Shazam con la libreria: ISRC
    anzitutto, poi artista+titolo esatto (case-insensitive). Una traccia senza
    ISRC ne' artista/titolo non puo' matchare nulla."""
    isrcs = {t.isrc for t in tracks if t.isrc}
    by_isrc: dict[str, Track] = {}
    if isrcs:
        for tr in db.scalars(select(Track).where(Track.isrc.in_(isrcs))).all():
            if tr.isrc and tr.isrc not in by_isrc:
                by_isrc[tr.isrc] = tr

    matches: dict[int, Track] = {}
    for dst in tracks:
        track = by_isrc.get(dst.isrc) if dst.isrc else None
        if track is None and dst.artist and dst.title:
            track = db.scalar(
                select(Track).where(ci_equals(Track.artist, dst.artist), ci_equals(Track.title, dst.title))
            )
        if track is not None:
            matches[dst.id] = track
    return matches


def _dj_set_detail_out(db: Session, dj_set) -> dict:
    """Serializza un DjSet includendo, per ogni traccia, il cross-match libreria."""
    out = DjSetSummaryOut.model_validate(dj_set).model_dump()
    matches = _match_library_tracks(db, dj_set.tracks)
    track_rows = []
    for t in dj_set.tracks:
        row = {
            "position": t.position,
            "start_offset_seconds": t.start_offset_seconds,
            "artist": t.artist,
            "title": t.title,
            "isrc": t.isrc,
            "confidence": t.confidence,
            "library_track_id": None,
            "library_status": None,
        }
        match = matches.get(t.id)
        if match is not None:
            row["library_track_id"] = match.id
            row["library_status"] = "owned" if match.has_local_file else "in_library"
        track_rows.append(row)
    out["tracks"] = track_rows
    return out


def _deps_available() -> bool:
    """ffmpeg + yt-dlp + shazamio presenti? Senza non si puo' identificare."""
    import shutil

    return bool(
        shutil.which("ffmpeg")
        and importlib.util.find_spec("yt_dlp")
        and importlib.util.find_spec("shazamio")
    )


@router.get("/status")
def status():
    return {"available": _deps_available()}


@router.post("/identify")
def identify(req: DjSetCreateIn):
    """Avvia l'identificazione di un mix (o riusa un set gia' analizzato)."""
    if not _deps_available():
        raise api_error(
            409, "shazam_deps_missing",
            "Identification unavailable: ffmpeg, yt-dlp and shazamio are required on the backend.",
        )
    return mix_identify_job.start_job(req.url)


@router.get("/identify-status")
def identify_status():
    return mix_identify_job.job_state()


@router.get("/sets", response_model=list[DjSetSummaryOut])
def list_sets(db: Session = Depends(get_db)):
    return list_dj_sets(db)


@router.get("/sets/{dj_set_id}", response_model=DjSetOut)
def get_set(dj_set_id: int, db: Session = Depends(get_db)):
    dj_set = get_dj_set(db, dj_set_id)
    if dj_set is None:
        raise api_error(404, "set_not_found", "Set not found")
    return _dj_set_detail_out(db, dj_set)


@router.post("/sets/{dj_set_id}/import-playlist", response_model=PlaylistImportReport, status_code=201)
def import_as_playlist(dj_set_id: int, db: Session = Depends(get_db)):
    """Importa le tracce identificate di un set come playlist di lead (manual).

    Le tracce Shazam non entrano automaticamente in libreria: qui l'utente le
    promuove a lead (dedup su artista+titolo, ISRC conservato per il riaggancio)."""
    dj_set = get_dj_set(db, dj_set_id)
    if dj_set is None:
        raise api_error(404, "set_not_found", "Set not found")
    if dj_set.imported_playlist_id is not None:
        raise api_error(409, "dj_set_already_imported", "Set already imported as playlist")
    items = [(t.artist, t.title, t.isrc) for t in dj_set.tracks]
    report = import_track_pairs(db, name=dj_set.title or "Set Shazam", items=items, source="shazam")
    dj_set.imported_playlist_id = report["playlist_id"]
    db.commit()
    return PlaylistImportReport(**report)


@router.delete("/sets/{dj_set_id}", status_code=204)
def remove_set(dj_set_id: int, db: Session = Depends(get_db)):
    if not delete_dj_set(db, dj_set_id):
        raise api_error(404, "set_not_found", "Set not found")
