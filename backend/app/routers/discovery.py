"""Discovery mode: crate digging via Discogs ("Scava").

Endpoint dig: genera lead per genere/etichetta, ne apre la tracklist, offre una
preview audio effimera e importa/salva-per-dopo i lead scelti. La sorgente e'
Discogs (integrations/discogs); iTunes/YouTube servono solo la preview.
"""

import re
import time

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.integrations.bandcamp import BandcampClient, BandcampError
from app.integrations.discogs import DiscogsClient, DiscogsError
from app.integrations.itunes import ItunesClient
from app.models import Track
from app.repositories import add_track_to_playlist
from app.schemas import (
    DiscogsVideoOut,
    DiscoveryAddRequest,
    DiscoveryAddResponse,
    DiscoveryDigRequest,
    DiscoveryDigResponse,
    DiscoveryGenresOut,
    DiscoveryLeadOut,
    DiscoveryPreviewOut,
    DiscoveryReleaseOut,
    DiscoverySaveForLaterRequest,
    DiscoverySaveForLaterResponse,
    DiscoveryTrackOut,
    ReasonOut,
)
from app.serializers import track_out
from app.services.dig_sources.bandcamp import _art_url, _bc_year_from_epoch
from app.services.dig_sources.discogs import DiscogsSource
from app.services.discovery_dig import DiscoveryLead, dig
from app.services.playlist_import import get_or_create_discovery_playlist, import_single_track
from app.services.preview import extract_youtube_videos, resolve_preview

# Stili Discogs curati per il drill-down "Generi" (oltre ai generi gia' in libreria).
#
# Ogni voce deve essere uno `style` ESISTENTE nel vocabolario Discogs: il dig interroga
# `search_releases(style=...)`, quindi un nome che Discogs non conosce e' un seme morto
# (zero lead, per sempre). Collaudate una per una contro l'API reale il 2026-07-16.
#
# Rimossa "Detroit Techno": non esiste ne' come `style` ne' come `genre` (entrambi 0
# release; come testo libero `q=` ne trova 6.079, ma il dig non usa `q`). Il Detroit
# techno su Discogs sta sotto lo style "Techno" — che e' gia' qui, come Minimal Techno
# e Dub Techno: non serve un sostituto.
#
# La lista e' scritta a mano e Discogs non espone un endpoint per enumerare gli style,
# quindi non e' derivabile dai dati: marcira' ancora. La difesa non e' un test (girerebbe
# in rete, andrebbe escluso dalla suite e non lo eseguirebbe nessuno) ma la UI: un seme
# senza pila lo dice (`pile_total == 0`), invece di far credere che il problema sia la
# libreria dell'utente.
_CURATED_STYLES = [
    "House", "Deep House", "Tech House", "Acid House", "Techno", "Minimal Techno",
    "Dub Techno", "Electro", "Trance", "Progressive House",
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


router = APIRouter(prefix="/api/discovery", tags=["discovery"])

# Cache TTL in-memory del get_release: lo stesso disco viene interrogato più volte
# (preview della card + di più tracce). Evita chiamate Discogs ripetute.
_RELEASE_TTL_S = 600
_release_cache: dict[int, tuple[float, dict]] = {}


def _cached_get_release(client: DiscogsClient, discogs_id: int) -> dict:
    now = time.monotonic()
    cached = _release_cache.get(discogs_id)
    if cached and now - cached[0] < _RELEASE_TTL_S:
        return cached[1]
    payload = client.get_release(discogs_id)
    _release_cache[discogs_id] = (now, payload)
    return payload


def _lead_out(lead: DiscoveryLead) -> DiscoveryLeadOut:
    return DiscoveryLeadOut(
        artist=lead.artist, title=lead.title, year=lead.year, label=lead.label,
        style=lead.styles[0] if lead.styles else None, source=lead.source, seed=lead.seed,
        source_id=lead.source_id, source_url=lead.source_url, stream_url=lead.stream_url,
        thumb_url=lead.thumb_url, have=lead.have, want=lead.want,
        reasons=[ReasonOut(code=r.code, data=r.data) for r in lead.reasons],
        format_badge=lead.format_badge,
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
    client = DiscogsClient()
    try:
        result = dig(db, seed_type=req.seed_type, value=req.value,
                     source=DiscogsSource(client), depth=req.depth)
    except DiscogsError as exc:
        # Rate limit / token mancante: 502 esplicito, mai uno "zero risultati" muto.
        raise api_error(502, "discovery_provider_error", f"Discovery provider error: {exc}",
                         reason=str(exc)) from exc
    finally:
        client.close()
    return DiscoveryDigResponse(
        seed_type=result.seed_type, value=result.value, source=req.source,
        leads=[_lead_out(lead) for lead in result.leads],
        pile_total=result.pile_total, pile_reach=result.pile_reach,
        seed_resolution=result.seed_resolution,
    )


def _bandcamp_ids(raw: str) -> tuple[int, int]:
    """"band_id:item_id" -> (band_id, item_id).

    Solo interi: nessun URL attraversa il confine, quindi non c'e' niente da far
    seguire al backend e nessun allowlist di host da tenere corretto per sempre.
    """
    parts = (raw or "").split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise api_error(400, "discovery_bad_id",
                        "Id Bandcamp non valido: atteso 'band_id:item_id'.")
    return int(parts[0]), int(parts[1])


def _discogs_release(discogs_id: int) -> DiscoveryReleaseOut:
    client = DiscogsClient()
    try:
        payload = client.get_release(discogs_id)
    except DiscogsError as exc:
        raise api_error(502, "discovery_provider_error", f"Discovery provider error: {exc}",
                         reason=str(exc)) from exc
    finally:
        client.close()

    names = [a.get("name", "") for a in (payload.get("artists") or []) if a.get("name")]
    artist = _clean_artist_name(", ".join(names)) if names else "Sconosciuto"
    labels = payload.get("labels") or []
    images = payload.get("images") or []
    uri = payload.get("uri") or ""

    tracks = [
        DiscoveryTrackOut(
            position=item.get("position") or "",
            title=item.get("title") or "",
            duration_seconds=_parse_duration(item.get("duration")),
        )
        for item in (payload.get("tracklist") or [])
        if item.get("type_") == "track"
    ]

    return DiscoveryReleaseOut(
        source="discogs", source_id=str(discogs_id),
        source_url=f"https://www.discogs.com{uri}" if uri.startswith("/") else (uri or None),
        title=payload.get("title") or "", artist=artist,
        thumb_url=images[0].get("uri") if images else None,
        year=payload.get("year"), label=labels[0].get("name") if labels else None,
        tracks=tracks, videos=[DiscogsVideoOut(**v) for v in extract_youtube_videos(payload)],
    )


def _bandcamp_release(band_id: int, item_id: int) -> DiscoveryReleaseOut:
    client = BandcampClient()
    try:
        payload = client.tralbum(band_id=band_id, tralbum_id=item_id)
    except BandcampError as exc:
        raise api_error(502, "discovery_provider_error",
                        f"Discovery provider error: {exc}", reason=str(exc)) from exc
    finally:
        client.close()

    tracks = [
        DiscoveryTrackOut(
            position=str(item.get("track_num") or ""),
            title=item.get("title") or "",
            duration_seconds=(int(item["duration"]) if item.get("duration") else None),
            stream_url=(item.get("streaming_url") or {}).get("mp3-128"),
        )
        for item in (payload.get("tracks") or [])
        if item.get("title")
    ]
    return DiscoveryReleaseOut(
        source="bandcamp", source_id=f"{band_id}:{item_id}",
        source_url=payload.get("bandcamp_url"),
        title=payload.get("title") or "",
        artist=payload.get("tralbum_artist") or "Sconosciuto",
        thumb_url=_art_url(payload.get("art_id"), size="16"),
        year=_bc_year_from_epoch(payload.get("release_date")),
        label=payload.get("label"),
        tracks=tracks,
        videos=[],
    )


@router.get("/release", response_model=DiscoveryReleaseOut)
def get_release_detail(source: str = "discogs", id: str = ""):
    """Dettaglio di un disco del dig: tracklist reale, fetch lazy all'apertura del
    pannello (mai in batch per tutta la griglia)."""
    if source == "bandcamp":
        return _bandcamp_release(*_bandcamp_ids(id))
    if not id.isdigit():
        raise api_error(400, "discovery_bad_id", "Id Discogs non valido.")
    return _discogs_release(int(id))


@router.get("/preview", response_model=DiscoveryPreviewOut)
def get_preview(
    artist: str,
    title: str,
    discogs_id: int | None = None,
    level: str = "track",
):
    """Preview audio di un lead: iTunes (30s pulita) o fallback video YouTube della
    release Discogs. Risoluzione lazy, effimera: nessuna persistenza. Gli errori dei
    provider degradano a kind="none" (una preview mancante non è un errore)."""
    itunes = ItunesClient()
    discogs = DiscogsClient() if discogs_id is not None else None
    try:
        get_release = None
        if discogs is not None:
            get_release = lambda rid: _cached_get_release(discogs, rid)  # noqa: E731
        result = resolve_preview(
            artist, title,
            itunes_search=lambda term: itunes.search(term),
            get_release=get_release,
            discogs_id=discogs_id,
            level=level,
        )
    finally:
        itunes.close()
        if discogs is not None:
            discogs.close()
    return DiscoveryPreviewOut(
        kind=result.kind,
        audio_url=result.audio_url,
        youtube_video_id=result.youtube_video_id,
        source_url=result.source_url,
        matched_title=result.matched_title,
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
    'Discovery'. Nessun download: solo per-dopo."""
    track, created = import_single_track(
        db, platform="manual", title=req.title, artist=req.artist,
        duration_seconds=req.duration_seconds, url=req.url, artwork_url=req.album_art_url,
    )
    playlist = get_or_create_discovery_playlist(db)
    # 'Discovery' non si sincronizza mai, ma la provenienza Cratory resta coerente.
    add_track_to_playlist(db, track, playlist, added_by="cratory")
    db.commit()
    db.refresh(track)
    return DiscoverySaveForLaterResponse(created=created, track=track_out(track))
