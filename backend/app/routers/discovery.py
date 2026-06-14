"""Discovery mode (Fase F): scoperta di musica nuova compatibile.

Due endpoint:
- POST /api/discovery/expand : espande una playlist importata con tracce affini.
- POST /api/discovery/gap    : cerca tracce che colmino un gap (da gap_analysis).

Sincrono (numero di lookup limitato dai cap in services/discovery). La fonte di
similarita' e' Last.fm; Spotify risolve i nomi in tracce reali; l'AI (se configurata)
aggiunge la spiegazione di ogni suggerimento.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.integrations.lastfm import (
    LastFMError,
    LastFMNotConfigured,
    get_lastfm_client,
    lastfm_configured,
)
from app.integrations.llm import get_llm_client, llm_configured
from app.integrations.spotify import SpotifyWebClient
from app.schemas import (
    DiscoveryAddRequest,
    DiscoveryAddResponse,
    DiscoveryCandidateOut,
    DiscoveryExpandRequest,
    DiscoveryGapRequest,
    DiscoveryResponse,
)
from app.serializers import track_out
from app.services.discovery import (
    DiscoveryCandidate,
    DiscoveryResult,
    discover_for_gap,
    discover_for_playlist,
)
from app.services.playlist_import import import_single_track

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/discovery", tags=["discovery"])


def _spotify_configured() -> bool:
    return bool(settings.spotify_client_id and settings.spotify_client_secret)


def _resolver(db: Session):
    """Resolver Spotify (solo metadata, client_credentials): None se Spotify non configurato."""
    if not _spotify_configured():
        return None
    client = SpotifyWebClient(db)
    return lambda artist, title: client.search_track(artist, title)


def _maybe_llm(use_ai: bool | None):
    if use_ai is False or not llm_configured():
        return None
    try:
        return get_llm_client()
    except Exception as exc:  # noqa: BLE001 - l'AI e' opzionale, non deve bloccare il discovery
        logger.warning("Discovery: LLM non disponibile: %s", exc)
        return None


def _candidate_out(c: DiscoveryCandidate) -> DiscoveryCandidateOut:
    return DiscoveryCandidateOut(
        artist=c.artist, title=c.title, match=c.match, source=c.source, seed=c.seed,
        spotify_id=c.spotify_id, spotify_url=c.spotify_url, album_art_url=c.album_art_url,
        isrc=c.isrc, duration_seconds=c.duration_seconds,
        compatibility=c.compatibility, explanation=c.explanation,
    )


def _response(result: DiscoveryResult) -> DiscoveryResponse:
    return DiscoveryResponse(
        mode=result.mode, scope=result.scope, seed_count=result.seed_count,
        candidates=[_candidate_out(c) for c in result.candidates],
    )


def _require_lastfm() -> None:
    if not lastfm_configured():
        raise HTTPException(
            status_code=409,
            detail=str(LastFMNotConfigured(
                "LASTFM_API_KEY mancante in backend/.env: serve per il Discovery "
                "(chiave gratuita su last.fm/api)."
            )),
        )


@router.get("/status")
def status():
    return {
        "configured": lastfm_configured(),
        "spotify_resolver": _spotify_configured(),
        "ai_explanations": llm_configured(),
    }


@router.post("/expand", response_model=DiscoveryResponse)
def expand(req: DiscoveryExpandRequest, db: Session = Depends(get_db)):
    _require_lastfm()
    try:
        result = discover_for_playlist(
            db, req.playlist_id,
            similarity=get_lastfm_client(), resolve=_resolver(db),
            llm=_maybe_llm(req.use_ai), limit=req.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LastFMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _response(result)


@router.post("/gap", response_model=DiscoveryResponse)
def gap(req: DiscoveryGapRequest, db: Session = Depends(get_db)):
    _require_lastfm()
    gap_dict = {
        "gap_type": req.gap_type,
        "description": req.description,
        "suggestion": req.suggestion,
    }
    try:
        result = discover_for_gap(
            db, gap_dict,
            similarity=get_lastfm_client(), resolve=_resolver(db),
            llm=_maybe_llm(req.use_ai), playlist_id=req.playlist_id, limit=req.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LastFMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _response(result)


@router.post("/add", response_model=DiscoveryAddResponse)
def add_to_library(req: DiscoveryAddRequest, db: Session = Depends(get_db)):
    """Importa nella libreria dell'app una traccia scoperta (idempotente)."""
    platform = "spotify" if req.spotify_id else "manual"
    track, created = import_single_track(
        db, platform=platform, platform_track_id=req.spotify_id,
        title=req.title, artist=req.artist, isrc=req.isrc,
        duration_seconds=req.duration_seconds, url=req.url, artwork_url=req.album_art_url,
    )
    return DiscoveryAddResponse(created=created, track=track_out(track))
