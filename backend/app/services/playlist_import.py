"""Import di una playlist streaming come punto di partenza del set (nuovo flusso).

Responsabilita' DETERMINISTICHE:
- normalizzare gli item della playlist nel modello Track interno,
- deduplicare (per ISRC, poi per platform_track_id),
- collegare le tracce alla Playlist importata,
- impostare lo stato iniziale.

Nessuna chiamata AI qui. L'enrichment musicale (BPM/key/mood/...) e' un passo
successivo e separato (services/enrichment + integrations/).
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Playlist, Track
from app.repositories import add_track_to_playlist, recount_playlist, remove_track_from_playlist, tracks_for_playlist
from app.services.track_status import refresh_status

logger = logging.getLogger(__name__)


@dataclass
class NormalizedTrack:
    platform: str
    platform_track_id: str | None
    title: str | None
    artist: str | None
    album: str | None
    duration_seconds: int | None
    url: str | None
    artwork_url: str | None
    isrc: str | None
    added_at: datetime | None
    year: int | None = None
    album_id: str | None = None


def _release_year(album: dict) -> int | None:
    date = album.get("release_date") or ""
    return int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None


def _parse_added_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_spotify_item(item: dict) -> NormalizedTrack | None:
    """Item di playlist/liked -> NormalizedTrack.

    L'oggetto traccia sta sotto chiavi diverse a seconda dell'endpoint:
    - /me/tracks (liked): item["track"]
    - /playlists/{id}/items: item["item"]  (/tracks ora da' 403 in Development Mode)
    """
    track = item.get("track") or item.get("item") or {}
    if not track or track.get("type") == "episode" or item.get("is_local") or track.get("is_local"):
        return None
    tid = track.get("id")
    if not tid:
        return None
    album = track.get("album") or {}
    images = album.get("images") or []
    artists = track.get("artists") or []
    external = track.get("external_ids") or {}
    return NormalizedTrack(
        platform="spotify",
        platform_track_id=tid,
        title=track.get("name") or None,
        artist=", ".join(a["name"] for a in artists if a.get("name")) or None,
        album=album.get("name") or None,
        duration_seconds=round(track["duration_ms"] / 1000) if track.get("duration_ms") else None,
        url=(track.get("external_urls") or {}).get("spotify"),
        artwork_url=images[0]["url"] if images else None,
        isrc=external.get("isrc"),
        added_at=_parse_added_at(item.get("added_at")),
        year=_release_year(album),
        album_id=album.get("id"),
    )


def _find_existing(db: Session, norm: NormalizedTrack) -> Track | None:
    # Priorita' matching: ISRC -> platform_track_id (vedi nuovo_progetto.md sez. 3)
    if norm.isrc:
        hit = db.scalar(select(Track).where(Track.isrc == norm.isrc))
        if hit:
            return hit
    if norm.platform_track_id:
        hit = db.scalar(
            select(Track).where(
                Track.platform == norm.platform,
                Track.platform_track_id == norm.platform_track_id,
            )
        )
        if hit:
            return hit
        if norm.platform == "spotify":
            return db.scalar(select(Track).where(Track.spotify_id == norm.platform_track_id))
    return None


def _apply_fields(track: Track, norm: NormalizedTrack) -> None:
    """Completa SOLO i campi vuoti (non sovrascrive enrichment/dati DJ esistenti)."""
    track.platform = track.platform or norm.platform
    track.platform_track_id = track.platform_track_id or norm.platform_track_id
    if norm.platform == "spotify":
        track.spotify_id = track.spotify_id or norm.platform_track_id
    track.source_type = track.source_type or norm.platform
    track.title = track.title or norm.title
    track.artist = track.artist or norm.artist
    track.album = track.album or norm.album
    track.album_id = track.album_id or norm.album_id
    track.year = track.year or norm.year
    track.duration_seconds = track.duration_seconds or norm.duration_seconds
    track.url = track.url or norm.url
    track.album_art_url = track.album_art_url or norm.artwork_url
    track.isrc = track.isrc or norm.isrc
    track.added_at = track.added_at or norm.added_at


def _apply(db: Session, track: Track, norm: NormalizedTrack, playlist: Playlist) -> None:
    _apply_fields(track, norm)
    refresh_status(track)
    db.flush()  # garantisce track.id per la membership
    add_track_to_playlist(db, track, playlist, added_at=norm.added_at)


def import_single_track(
    db: Session,
    *,
    platform: str = "spotify",
    platform_track_id: str | None = None,
    title: str | None = None,
    artist: str | None = None,
    isrc: str | None = None,
    duration_seconds: int | None = None,
    url: str | None = None,
    artwork_url: str | None = None,
) -> tuple[Track, bool]:
    """Importa una singola traccia nella libreria (es. da Discovery). Idempotente.

    Ritorna (track, created). Non la collega a nessuna playlist: entra in libreria
    come traccia indipendente, pronta per l'enrichment e l'uso nei set.
    """
    norm = NormalizedTrack(
        platform=platform, platform_track_id=platform_track_id, title=title, artist=artist,
        album=None, duration_seconds=duration_seconds, url=url, artwork_url=artwork_url,
        isrc=isrc, added_at=None,
    )
    existing = _find_existing(db, norm)
    # Candidato non risolto (niente ISRC/platform_track_id): ripiega sul match per nome
    # cosi' un secondo "Aggiungi" non duplica la traccia.
    if existing is None and not isrc and not platform_track_id and title:
        stmt = select(Track).where(Track.title.ilike(title))
        stmt = stmt.where(Track.artist.ilike(artist)) if artist else stmt.where(Track.artist.is_(None))
        existing = db.scalar(stmt)
    target = existing if existing is not None else Track(source_type=platform)
    if existing is None:
        db.add(target)
    _apply_fields(target, norm)
    refresh_status(target)
    db.commit()
    db.refresh(target)
    return target, existing is None


def import_playlist(
    db: Session,
    *,
    platform: str,
    name: str,
    items: list[dict],
    platform_playlist_id: str | None = None,
    owner: str | None = None,
    url: str | None = None,
    artwork_url: str | None = None,
    kind: str = "playlist",
    prune: bool = False,
) -> dict:
    """Importa/aggiorna una playlist e le sue tracce. Idempotente. Ritorna un report.

    Con ``prune=True`` (sync da Spotify) le tracce ancora collegate a questa playlist
    ma non piu' presenti nel set importato vengono SCOLLEGATE (playlist_id/name=None):
    restano in libreria, escono solo dalla playlist.
    """
    if platform != "spotify":
        raise ValueError(f"Piattaforma non supportata per l'import: {platform}")

    playlist = None
    if platform_playlist_id:
        playlist = db.scalar(
            select(Playlist).where(
                Playlist.platform == platform,
                Playlist.platform_playlist_id == platform_playlist_id,
            )
        )
    if playlist is None:
        playlist = Playlist(platform=platform, name=name, kind=kind)
        db.add(playlist)
    playlist.name = name
    playlist.platform_playlist_id = platform_playlist_id
    playlist.owner = owner
    playlist.url = url
    playlist.artwork_url = artwork_url
    playlist.kind = kind
    db.flush()  # serve playlist.id per collegare le tracce

    created = updated = skipped = 0
    present_isrcs: set[str] = set()
    present_platform_ids: set[str] = set()
    for item in items:
        norm = normalize_spotify_item(item) if platform == "spotify" else None
        if norm is None:
            skipped += 1
            continue
        if norm.isrc:
            present_isrcs.add(norm.isrc)
        if norm.platform_track_id:
            present_platform_ids.add(norm.platform_track_id)
        existing = _find_existing(db, norm)
        if existing is None:
            track = Track(source_type=platform)
            db.add(track)
            _apply(db, track, norm, playlist)
            created += 1
        else:
            _apply(db, existing, norm, playlist)
            updated += 1

    removed = 0
    if prune:
        for track in tracks_for_playlist(db, playlist.id):
            still_present = (
                (track.isrc is not None and track.isrc in present_isrcs)
                or (track.platform_track_id is not None
                    and track.platform_track_id in present_platform_ids)
            )
            if not still_present:
                remove_track_from_playlist(db, playlist.id, track.id)
                removed += 1

    recount_playlist(db, playlist)
    db.commit()
    db.refresh(playlist)
    report = {
        "playlist_id": playlist.id,
        "name": playlist.name,
        "created": created,
        "updated": updated,
        "removed": removed,
        "skipped": skipped,
        "total": created + updated,
    }
    logger.info("Import playlist '%s': %s", name, report)
    return report
