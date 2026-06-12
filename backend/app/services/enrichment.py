"""Enrichment metadata da Spotify (MVP 2).

Regole (da docs/05-functional-spec.md F2):
- MAI sovrascrivere BPM e tonalita' di Rekordbox.
- title/artist/album/anno: completati solo se vuoti.
- cover, spotify_artist_id, generi artista: sempre aggiornati da Spotify.
- enriched_at funge da cache: le tracce gia' arricchite vengono saltate (force=True per rifare).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artist, Track

logger = logging.getLogger(__name__)


class TrackMetadataSource(Protocol):
    """Sottoinsieme del client Spotify usato dall'enrichment (testabile con un fake)."""

    def get_tracks_batch(self, ids: list[str]) -> list[dict[str, Any]]: ...
    def get_artists_batch(self, ids: list[str]) -> list[dict[str, Any]]: ...


def _release_year(album: dict[str, Any]) -> int | None:
    date = album.get("release_date") or ""
    return int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None


def _apply_track_metadata(track: Track, meta: dict[str, Any]) -> None:
    artists = meta.get("artists") or []
    artist_names = ", ".join(a["name"] for a in artists if a.get("name"))
    album = meta.get("album") or {}
    images = album.get("images") or []

    if not track.title:
        track.title = meta.get("name") or None
    if not track.artist:
        track.artist = artist_names or None
    if not track.album:
        track.album = album.get("name") or None
    if not track.year:
        track.year = _release_year(album)
    track.album_art_url = images[0]["url"] if images else track.album_art_url
    track.spotify_artist_id = artists[0]["id"] if artists else None
    track.enriched_at = datetime.now(timezone.utc)


def _upsert_artists(db: Session, artist_meta: list[dict[str, Any]]) -> dict[str, Artist]:
    by_id: dict[str, Artist] = {}
    for meta in artist_meta:
        if not meta:
            continue
        sid = meta["id"]
        artist = db.scalar(select(Artist).where(Artist.spotify_artist_id == sid))
        if artist is None:
            artist = Artist(name=meta.get("name") or "?", spotify_artist_id=sid)
            db.add(artist)
        artist.name = meta.get("name") or artist.name
        artist.genres = meta.get("genres") or []
        artist.popularity = meta.get("popularity")
        by_id[sid] = artist
    return by_id


def enrich_library(db: Session, source: TrackMetadataSource, *, force: bool = False) -> dict:
    """Arricchisce tutte le tracce Spotify non ancora arricchite. Ritorna un report."""
    stmt = select(Track).where(Track.spotify_id.is_not(None))
    if not force:
        stmt = stmt.where(Track.enriched_at.is_(None))
    tracks = list(db.scalars(stmt).all())
    if not tracks:
        return {"enriched": 0, "skipped_already_enriched": True, "not_found": 0, "artists_updated": 0}

    by_spotify_id = {t.spotify_id: t for t in tracks}
    metas = source.get_tracks_batch(list(by_spotify_id.keys()))

    not_found = 0
    for meta in metas:
        if not meta:  # id inesistente/rimosso da Spotify
            not_found += 1
            continue
        track = by_spotify_id.get(meta["id"])
        if track is not None:
            _apply_track_metadata(track, meta)

    artist_ids = sorted({t.spotify_artist_id for t in tracks if t.spotify_artist_id})
    artists = _upsert_artists(db, source.get_artists_batch(artist_ids)) if artist_ids else {}

    # genere traccia: se vuoto, usa i generi dell'artista (dato Spotify a livello artista)
    for t in tracks:
        if not t.genre and t.spotify_artist_id in artists:
            genres = artists[t.spotify_artist_id].genres
            if genres:
                t.genre = ", ".join(genres[:3])

    db.commit()
    enriched = sum(1 for t in tracks if t.enriched_at is not None)
    logger.info("Enrichment: %s tracce, %s artisti, %s id non trovati",
                enriched, len(artists), not_found)
    return {
        "enriched": enriched,
        "not_found": not_found,
        "artists_updated": len(artists),
        "skipped_already_enriched": False,
    }
