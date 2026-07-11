"""Discovery mode (Fase F): scoperta di musica nuova compatibile.

Endpoint principale:
- POST /api/discovery/expand : espande una playlist importata con tracce affini.

Sincrono (numero di lookup limitato dai cap in services/discovery). La fonte di
similarita' e' Last.fm; Spotify risolve i nomi in tracce reali; l'AI (se configurata)
aggiunge la spiegazione di ogni suggerimento.
"""

import logging
import re

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_errors import api_error
from app.db import get_db
from app.integrations.discogs import DiscogsClient, DiscogsError
from app.integrations.lastfm import (
    LastFMError,
    get_lastfm_client,
    lastfm_configured,
)
from app.integrations.llm import get_llm_client, llm_configured
from app.integrations.spotify import SpotifyWebClient
from app.models import Track
from app.repositories import add_track_to_playlist
from app.schemas import (
    DiscogsReleaseOut,
    DiscogsTrackOut,
    DiscoveryAddRequest,
    DiscoveryAddResponse,
    DiscoveryCandidateOut,
    DiscoveryDigRequest,
    DiscoveryDigResponse,
    DiscoveryExpandRequest,
    DiscoveryGenresOut,
    DiscoveryLeadOut,
    DiscoveryResponse,
    DiscoverySaveForLaterRequest,
    DiscoverySaveForLaterResponse,
    ReasonOut,
)
from app.serializers import track_out
from app.services.discovery import (
    DiscoveryCandidate,
    DiscoveryResult,
    discover_for_playlist,
)
from app.services.discovery_dig import DiscoveryLead, dig
from app.services.labels import _clean_label, album_label, labels_overview
from app.services.playlist_import import get_or_create_discovery_playlist, import_single_track

# Stili Discogs curati per il drill-down "Generi" (oltre ai generi gia' in libreria).
_CURATED_STYLES = [
    "House", "Deep House", "Tech House", "Acid House", "Techno", "Minimal Techno",
    "Detroit Techno", "Dub Techno", "Electro", "Trance", "Progressive House",
    "Drum n Bass", "Jungle", "Breakbeat", "UK Garage", "Disco", "Italo-Disco",
    "Nu-Disco", "Ambient", "Downtempo", "Trip Hop", "IDM", "Dubstep", "Hip Hop",
    "Funk / Soul", "Afrobeat",
]

# Discogs disambigua artisti omonimi con un suffisso numerico ("Aphex Twin (2)"):
# rumore per la UI, va tolto.
_ARTIST_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")


def _clean_artist_name(name: str) -> str:
    return _ARTIST_SUFFIX_RE.sub("", name).strip()


def _parse_duration(value: str | None) -> int | None:
    """'mm:ss' -> secondi. Vuota o non parsabile -> None (il ranking Soulseek
    tratta l'ignoto come neutro, mai penalizzato)."""
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        minutes, seconds = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return minutes * 60 + seconds


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
        label=c.label, label_owned=c.label_owned, explanation=c.explanation,
    )


def _owned_labels(db: Session) -> set[str]:
    """Etichette (pulite, lowercase) gia' in libreria — per il segnale-etichetta su /expand."""
    return {o["label"].lower() for o in labels_overview(db)}


def _response(result: DiscoveryResult) -> DiscoveryResponse:
    return DiscoveryResponse(
        mode=result.mode, scope=result.scope, seed_count=result.seed_count,
        candidates=[_candidate_out(c) for c in result.candidates],
    )


def _require_lastfm() -> None:
    if not lastfm_configured():
        raise api_error(
            409, "lastfm_not_configured",
            "Last.fm not configured: needed for Discovery (free key at last.fm/api).",
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
    # Segnale-etichetta: se Spotify e' configurato, annota i candidati con la loro
    # etichetta e fa salire chi e' su un'etichetta che gia' collezioni.
    album_label_fn = owned = None
    if _spotify_configured():
        client = SpotifyWebClient(db)
        album_label_fn = lambda aid: album_label(client, aid)  # noqa: E731
        owned = _owned_labels(db)
    try:
        result = discover_for_playlist(
            db, req.playlist_id,
            similarity=get_lastfm_client(), resolve=_resolver(db),
            llm=_maybe_llm(req.use_ai),
            album_label_fn=album_label_fn, owned_labels=owned, limit=req.limit,
        )
    except ValueError as exc:
        raise api_error(404, "discovery_not_found", f"Discovery not found: {exc}",
                         reason=str(exc)) from exc
    except LastFMError as exc:
        raise api_error(502, "discovery_provider_error", f"Discovery provider error: {exc}",
                         reason=str(exc)) from exc
    return _response(result)


# --- Discovery v2: dig (crate digging via Discogs) ---------------------------


def _lead_out(lead: DiscoveryLead) -> DiscoveryLeadOut:
    return DiscoveryLeadOut(
        artist=lead.artist, title=lead.title, year=lead.year, label=lead.label,
        style=lead.style, source=lead.source, seed=lead.seed,
        discogs_url=lead.discogs_url, thumb_url=lead.thumb_url,
        have=lead.have, want=lead.want,
        reasons=[ReasonOut(code=r.code, data=r.data) for r in lead.reasons],
        discogs_id=lead.discogs_id, format_badge=lead.format_badge,
    )


@router.get("/genres", response_model=DiscoveryGenresOut)
def discovery_genres(db: Session = Depends(get_db)):
    """Generi gia' in libreria + stili curati, per il seme 'Generi' del dig."""
    rows = db.execute(
        select(Track.genre).where(Track.genre.is_not(None), Track.genre != "").distinct()
    ).all()
    library = sorted({g for (g,) in rows if g})
    return DiscoveryGenresOut(library=library, styles=_CURATED_STYLES)


@router.post("/dig", response_model=DiscoveryDigResponse)
def dig_endpoint(req: DiscoveryDigRequest, db: Session = Depends(get_db)):
    """Lista-dig a volume da Discogs per genere/stile o etichetta (lead non risolti)."""
    from app.repositories import tracks_for_playlist

    taste_tracks = None
    if req.taste_playlist_id is not None:
        taste_tracks = tracks_for_playlist(db, req.taste_playlist_id)
    client = DiscogsClient()
    result = dig(
        db, seed_type=req.seed_type, value=req.value,
        search_releases=lambda **kw: client.search_releases(**kw),
        taste_tracks=taste_tracks,
        adventurousness=req.adventurousness, limit=req.limit,
    )
    return DiscoveryDigResponse(
        seed_type=result.seed_type, value=result.value,
        leads=[_lead_out(lead) for lead in result.leads],
    )


@router.get("/release/{discogs_id}", response_model=DiscogsReleaseOut)
def get_release_detail(discogs_id: int):
    """Dettaglio di un disco del dig: tracklist reale, fetch lazy all'apertura
    del pannello (mai in batch per tutta la griglia)."""
    client = DiscogsClient()
    try:
        payload = client.get_release(discogs_id)
    except DiscogsError as exc:
        raise api_error(502, "discovery_provider_error", f"Discovery provider error: {exc}",
                         reason=str(exc)) from exc

    names = [a.get("name", "") for a in (payload.get("artists") or []) if a.get("name")]
    artist = _clean_artist_name(", ".join(names)) if names else "Sconosciuto"
    labels = payload.get("labels") or []
    images = payload.get("images") or []
    uri = payload.get("uri") or ""

    tracks = [
        DiscogsTrackOut(
            position=item.get("position") or "",
            title=item.get("title") or "",
            duration_seconds=_parse_duration(item.get("duration")),
        )
        for item in (payload.get("tracklist") or [])
        if item.get("type_") == "track"
    ]

    return DiscogsReleaseOut(
        discogs_id=discogs_id,
        title=payload.get("title") or "",
        artist=artist,
        thumb_url=images[0].get("uri") if images else None,
        discogs_url=f"https://www.discogs.com{uri}" if uri.startswith("/") else (uri or None),
        year=payload.get("year"),
        label=labels[0].get("name") if labels else None,
        tracks=tracks,
    )


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


@router.post("/save-for-later", response_model=DiscoverySaveForLaterResponse)
def save_for_later(req: DiscoverySaveForLaterRequest, db: Session = Depends(get_db)):
    """Importa una traccia della tracklist e la mette nella playlist di sistema
    'Scoperte'. Nessun download: solo per-dopo."""
    track, created = import_single_track(
        db, platform="manual", title=req.title, artist=req.artist,
        duration_seconds=req.duration_seconds, url=req.url, artwork_url=req.album_art_url,
    )
    playlist = get_or_create_discovery_playlist(db)
    add_track_to_playlist(db, track, playlist)
    db.commit()
    db.refresh(track)
    return DiscoverySaveForLaterResponse(created=created, track=track_out(track))
