"""Discovery mode: crate digging ("Scava").

Endpoint dig: genera lead dall'unione di uno o piu' semi genere/etichetta, ne apre
la tracklist, offre una preview audio effimera e importa/salva-per-dopo i lead
scelti. La sorgente e' Discogs o Bandcamp (`req.source`,
`app/services/dig_sources/`); iTunes/YouTube servono solo alla preview del
fallback Discogs.
"""

import re
import time
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.integrations.bandcamp import BandcampClient, BandcampError
from app.integrations.discogs import DiscogsClient, DiscogsError
from app.integrations.itunes import ItunesClient
from app.models import Track
from app.repositories import add_track_to_playlist, file_tags_for_tracks
from app.schemas import (
    DiscogsVideoOut,
    DiscoveryAddRequest,
    DiscoveryAddResponse,
    DiscoveryDigRequest,
    DiscoveryDigResponse,
    DiscoveryGenresOut,
    DiscoveryLeadOut,
    DiscoveryPileOut,
    DiscoveryPreviewOut,
    DiscoveryReleaseOut,
    DiscoverySaveForLaterRequest,
    DiscoverySaveForLaterResponse,
    DiscoverySimilarResponse,
    DiscoveryTrackOut,
    EdgeReportOut,
    GenreCountOut,
    OriginOut,
    ReasonOut,
)
from app.serializers import track_out
from app.services.dig_sources.bandcamp import BandcampSimilar, BandcampSource, _art_url, _bc_year_from_epoch
from app.services.dig_sources import Seed
from app.services.dig_sources.discogs import DiscogsSource
from app.services.discovery_dig import DiscoveryLead, dig
from app.services.discovery_similar import similar
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
# senza pila lo dice (`piles[].total == 0`), invece di far credere che il problema sia la
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


def _bc_duration(value: Any) -> int | None:
    """Durata Bandcamp -> secondi interi. E' un float ("212.012"), non 'mm:ss' come
    Discogs, quindi il parsing passa da `float` e non da `int` diretto.

    Endpoint non documentato: un valore non numerico (o assente) non deve far cadere
    la release in un 500, la traccia resta solo senza durata (il ranking la tratta
    come neutra, mai penalizzata)."""
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


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
    """Generi gia' in libreria + stili curati, per il seme 'Generi' del dig.

    Un'unica query raggruppata alimenta sia `library` che `library_counts`: stessa
    colonna (`Track.genre`), stesso filtro, cosi' i due non possono divergere come
    accadeva confrontando questo endpoint con /api/library/genres (tag effettivo,
    solo tracce con BPM)."""
    rows = db.execute(
        select(Track.genre, func.count())
        .where(Track.genre.is_not(None), Track.genre != "")
        .group_by(Track.genre)
    ).all()
    counts = {genre: count for genre, count in rows if genre}
    library = sorted(counts)
    return DiscoveryGenresOut(
        library=library,
        styles=_CURATED_STYLES,
        library_counts=[GenreCountOut(genre=g, count=counts[g]) for g in library],
    )


@router.post("/dig", response_model=DiscoveryDigResponse)
def dig_endpoint(req: DiscoveryDigRequest, db: Session = Depends(get_db)):
    """Lista-dig a volume dall'unione dei semi (generi/etichette): lead non risolti."""
    client = BandcampClient() if req.source == "bandcamp" else DiscogsClient()
    source = BandcampSource(client) if req.source == "bandcamp" else DiscogsSource(client)
    seeds = [Seed(type=s.type, value=s.value) for s in req.seeds]
    try:
        result = dig(db, seeds=seeds, source=source, depth=req.depth)
    except (DiscogsError, BandcampError) as exc:
        # Rate limit / token mancante / endpoint cambiato: 502 esplicito, mai uno
        # "zero risultati" muto — l'utente deve poter distinguere "non c'e' niente"
        # da "il provider non ha risposto".
        raise api_error(502, "discovery_provider_error", f"Discovery provider error: {exc}",
                        reason=str(exc)) from exc
    finally:
        client.close()
    return DiscoveryDigResponse(
        seeds=req.seeds, source=req.source,
        leads=[_lead_out(lead) for lead in result.leads],
        piles=[DiscoveryPileOut(seed_type=p.seed.type, value=p.seed.value,
                                total=p.total, reach=p.reach, resolution=p.resolution)
               for p in result.piles],
    )


@router.get("/similar", response_model=DiscoverySimilarResponse)
def similar_endpoint(
    track_id: int,
    source: str = "bandcamp",
    style_period: bool = False,
    db: Session = Depends(get_db),
):
    """I lead Bandcamp imparentati con una traccia posseduta."""
    if source != "bandcamp":
        raise api_error(400, "discovery_bad_source",
                        f"Sorgente non supportata dai simili: {source}")
    track = db.get(Track, track_id)
    if track is None:
        raise api_error(404, "track_not_found", f"Traccia {track_id} inesistente")

    client = BandcampClient()
    try:
        result = similar(db, track, source=BandcampSimilar(client),
                         style_period=style_period)
    except BandcampError as exc:
        # Come nel dig: "non c'è niente" e "il provider non ha risposto" devono
        # restare distinguibili dal chiamante.
        raise api_error(502, "discovery_provider_error", f"Discovery provider error: {exc}",
                        reason=str(exc)) from exc
    finally:
        client.close()

    origin = result.origin
    return DiscoverySimilarResponse(
        track_id=track_id, source=source,
        origin=OriginOut(
            artist=origin.artist, title=origin.title, label=origin.label,
            year=origin.year, tag=origin.tag, source_url=origin.source_url,
            resolution=origin.resolution,
        ) if origin else None,
        edges={k: EdgeReportOut(count=v.count, absent_reason=v.absent_reason)
               for k, v in result.edges.items()},
        leads=[_lead_out(lead) for lead in result.leads],
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
            duration_seconds=_bc_duration(item.get("duration")),
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


# Gli id di YouTube sono undici caratteri di un alfabeto ristretto. Il
# controllo non e' cosmetico: l'id finisce dentro l'HTML della pagina qui
# sotto, e senza vincolo sarebbe il chiamante a decidere cosa ci scriviamo.
_ID_YOUTUBE = re.compile(r"[A-Za-z0-9_-]{11}")

# Nessuna prosa, nessuno stile, nessuno script: solo il player, a tutta
# pagina, dentro un documento che esiste per il suo indirizzo e non per il suo
# contenuto.
_PAGINA_YOUTUBE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>preview</title>
<style>html,body{{margin:0;height:100%;background:#000}}iframe{{border:0;width:100%;height:100%}}</style>
</head><body>
<iframe src="https://www.youtube-nocookie.com/embed/{video_id}?autoplay=1"
        allow="autoplay; encrypted-media" allowfullscreen></iframe>
</body></html>"""


@router.get("/preview/youtube/{video_id}", response_class=HTMLResponse)
def preview_youtube(video_id: str) -> HTMLResponse:
    """Una pagina che contiene soltanto il player YouTube.

    Serve per il referrer, e per nient'altro. Dal 2025 YouTube risponde
    "Errore 153 - configurazione del video player" agli embed che arrivano
    senza un `Referer` utilizzabile, e nel guscio desktop la pagina sta su
    `tauri://localhost`: uno schema che un referrer valido non lo produce, per
    quanti attributi gli si mettano addosso. Servendo l'iframe da qui, la
    richiesta a YouTube parte da `http://127.0.0.1:8000` — un indirizzo che un
    referrer ce l'ha.

    E' l'unico endpoint dell'app che risponde HTML invece di JSON: non e' una
    pagina dell'interfaccia (quella e' tutta nel frontend), e' un contenitore
    tecnico il cui unico contenuto e' un iframe di terzi. Niente qui viene
    scaricato o conservato: la preview resta effimera com'era.
    """
    if not _ID_YOUTUBE.fullmatch(video_id):
        raise api_error(
            400, "invalid_youtube_id",
            "id YouTube non valido: undici caratteri fra lettere, cifre, `-` e `_`",
            video_id=video_id,
        )
    return HTMLResponse(_PAGINA_YOUTUBE.format(video_id=video_id))


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
    # M6: import_single_track puo' ripiegare su una traccia GIA' posseduta
    # (match artista+titolo): senza i tag file mostrava il genere streaming
    # anche per una traccia con un genere curato sul file.
    ft = file_tags_for_tracks(db, [track.id]).get(track.id)
    return DiscoveryAddResponse(created=created, track=track_out(track, ft))


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
    ft = file_tags_for_tracks(db, [track.id]).get(track.id)
    return DiscoverySaveForLaterResponse(created=created, track=track_out(track, ft))
