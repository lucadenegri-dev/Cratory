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
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
    local_path: str | None = None


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
    )


SC_TITLE_SEPARATOR = " - "

# Posizione di tracklist/vinile usata come prefisso del titolo ("a1 - ...",
# "B2 - ...", "01 - ..."): non è un artista.
_SC_POSITION_RE = re.compile(r"^(?:[a-d]\d{1,2}|\d{1,2}\.?)$", re.IGNORECASE)


def _norm_name(value: str | None) -> str:
    """Normalizza un nome per il confronto con l'uploader: via il contenuto tra
    parentesi/quadre (numeri di catalogo, note remix), poi casefold alfanumerico."""
    value = re.sub(r"[(\[].*?[)\]]", "", value or "")
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def split_artist_title(raw_title: str | None, uploader: str | None) -> tuple[str | None, str | None]:
    """Split deterministico "Artist - Title" alla PRIMA occorrenza del separatore.

    Regole (in ordine), tutte deterministiche — normalizzazione da import
    (competenza Cratory), non enrichment (Sortory):
    - un prefisso di posizione tracklist/vinile ("a1", "B2", "01") a sinistra
      del primo separatore si scarta e si ri-splitta il resto;
    - se la parte destra coincide con l'uploader (e la sinistra no) il titolo
      segue la convenzione "Titolo - Artista": si inverte;
    - senza separatore l'artista è l'uploader (il fetch pieno dà il nome vero).
    """
    raw_title = (raw_title or "").strip()
    uploader = (uploader or "").strip() or None
    if SC_TITLE_SEPARATOR in raw_title:
        left, _, right = raw_title.partition(SC_TITLE_SEPARATOR)
        left, right = left.strip(), right.strip()
        if _SC_POSITION_RE.match(left):
            # "a1 - Pariah - Caterpillar" -> ri-splitta "Pariah - Caterpillar";
            # "B2 - Some Track" -> solo titolo, artista dall'uploader.
            if SC_TITLE_SEPARATOR not in right:
                return uploader, (right or raw_title)
            left, _, right = right.partition(SC_TITLE_SEPARATOR)
            left, right = left.strip(), right.strip()
        norm_up = _norm_name(uploader)
        if len(norm_up) >= 3:  # nomi troppo corti ("DJ") matchano per caso
            norm_left, norm_right = _norm_name(left), _norm_name(right)
            right_matches = norm_right and (norm_up in norm_right or norm_right in norm_up)
            left_matches = norm_left and (norm_up in norm_left or norm_left in norm_up)
            if right_matches and not left_matches:
                return (right or uploader), (left or raw_title)
        return (left or uploader), (right or raw_title)
    return uploader, (raw_title or None)


def normalize_soundcloud_item(entry: dict | None) -> NormalizedTrack | None:
    """Entry flat yt-dlp -> NormalizedTrack. Niente ISRC: SoundCloud non lo espone."""
    if not entry:
        return None
    tid = entry.get("id")
    if not tid:
        return None
    artist, title = split_artist_title(entry.get("title"), entry.get("uploader"))
    duration = entry.get("duration")
    thumbnails = entry.get("thumbnails") or []
    return NormalizedTrack(
        platform="soundcloud",
        platform_track_id=str(tid),
        title=title,
        artist=artist,
        album=None,
        duration_seconds=int(duration) if duration else None,
        url=entry.get("url") or entry.get("webpage_url"),
        artwork_url=(thumbnails[-1].get("url") if thumbnails else None),
        isrc=None,
        added_at=None,  # non disponibile in flat mode
    )


def identity_normalize(item: NormalizedTrack) -> NormalizedTrack:
    """Passthrough per chi fornisce già NormalizedTrack (es. import locale)."""
    return item


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
    elif norm.platform == "soundcloud":
        # Popola la colonna dedicata (come spotify_id): abilita il filtro
        # has_soundcloud su /api/tracks e l'esposizione di soundcloud_id.
        track.soundcloud_id = track.soundcloud_id or norm.platform_track_id
    track.source_type = track.source_type or norm.platform
    track.title = track.title or norm.title
    track.artist = track.artist or norm.artist
    track.album = track.album or norm.album
    track.year = track.year or norm.year
    track.duration_seconds = track.duration_seconds or norm.duration_seconds
    track.url = track.url or norm.url
    track.album_art_url = track.album_art_url or norm.artwork_url
    track.isrc = track.isrc or norm.isrc
    track.added_at = track.added_at or norm.added_at
    # local_path: overwrite-quando-presente (solo i NormalizedTrack locali lo valorizzano),
    # così un file spostato/rinominato aggiorna il path pur mantenendo l'identità via hash.
    if norm.local_path:
        track.local_path = norm.local_path


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
    items: list,
    normalize: Callable[[Any], "NormalizedTrack | None"] = normalize_spotify_item,
    platform_playlist_id: str | None = None,
    owner: str | None = None,
    url: str | None = None,
    artwork_url: str | None = None,
    kind: str = "playlist",
    prune: bool = False,
) -> dict:
    """Importa/aggiorna una playlist e le sue tracce. Idempotente. Ritorna un report.

    Con ``prune=True`` (sync da Spotify) le tracce ancora collegate a questa playlist
    ma non piu' presenti nel set importato vengono SCOLLEGATE: la membership su
    playlist_tracks viene rimossa; la traccia resta in libreria e in ogni altra playlist.
    """
    playlist = None
    if platform_playlist_id:
        playlist = db.scalar(
            select(Playlist).where(
                Playlist.platform == platform,
                Playlist.platform_playlist_id == platform_playlist_id,
            )
        )
    elif kind == "liked":
        # I liked non hanno platform_playlist_id: la playlist va ritrovata per `kind`,
        # altrimenti ogni import ne creerebbe una duplicata.
        playlist = _liked_playlist(db, platform)
    elif url:
        # Fallback per playlist URL-based senza platform_playlist_id (es. alcuni
        # link SoundCloud la cui estrazione flat non espone un id di set): senza
        # questo ramo ogni re-import/sync dello stesso URL creerebbe un duplicato.
        # Non tocca Spotify: le playlist reali hanno sempre platform_playlist_id
        # (primo ramo) e i liked passano da `kind=="liked"` (secondo ramo).
        playlist = db.scalar(
            select(Playlist).where(Playlist.platform == platform, Playlist.url == url)
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
        norm = normalize(item)
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


# --- Liked selettivi ---------------------------------------------------------

LIKED_PLAYLIST_NAME = "Liked Spotify"


def _liked_playlist(db: Session, platform: str = "spotify") -> Playlist | None:
    """La playlist dei brani salvati (kind="liked"). Ne esiste al più una per piattaforma."""
    return db.scalar(
        select(Playlist).where(Playlist.platform == platform, Playlist.kind == "liked")
    )


DISCOVERY_PLAYLIST_NAME = "Scoperte"


def get_or_create_discovery_playlist(db: Session) -> Playlist:
    """La playlist di sistema per le tracce 'per dopo' del dig Discovery.

    Ne esiste al più una (kind='discovery'), creata al primo uso — stesso
    pattern di _liked_playlist, ma qui va anche creata se assente (i liked
    nascono dall'import Spotify, 'Scoperte' nasce dal primo 'per dopo').
    """
    playlist = db.scalar(
        select(Playlist).where(Playlist.platform == "manual", Playlist.kind == "discovery")
    )
    if playlist is None:
        playlist = Playlist(platform="manual", name=DISCOVERY_PLAYLIST_NAME, kind="discovery")
        db.add(playlist)
        db.flush()
    return playlist


def preview_liked_tracks(db: Session, items: list) -> list[dict]:
    """Item liked di Spotify -> anteprima selezionabile, senza importare nulla.

    Ogni voce è marcata ``already_imported`` se la traccia è già collegata alla
    playlist Liked locale (match ISRC / platform_track_id / spotify_id, coerente
    con la dedup di ``_find_existing``).
    """
    playlist = _liked_playlist(db)
    isrcs: set[str] = set()
    platform_ids: set[str] = set()
    if playlist is not None:
        for t in tracks_for_playlist(db, playlist.id):
            if t.isrc:
                isrcs.add(t.isrc)
            if t.platform_track_id:
                platform_ids.add(t.platform_track_id)
            if t.spotify_id:
                platform_ids.add(t.spotify_id)

    out: list[dict] = []
    for item in items:
        norm = normalize_spotify_item(item)
        if norm is None or not norm.platform_track_id:
            continue
        already = (
            (norm.isrc is not None and norm.isrc in isrcs)
            or norm.platform_track_id in platform_ids
        )
        out.append({
            "spotify_id": norm.platform_track_id,
            "isrc": norm.isrc,
            "title": norm.title,
            "artist": norm.artist,
            "duration_seconds": norm.duration_seconds,
            "artwork_url": norm.artwork_url,
            "already_imported": already,
        })
    return out


def import_selected_liked_tracks(db: Session, items: list, spotify_ids: list[str]) -> dict:
    """Importa nella playlist Liked SOLO gli item selezionati. Additivo (niente prune)."""
    wanted = set(spotify_ids)
    selected = [
        item for item in items
        if (item.get("track") or item.get("item") or {}).get("id") in wanted
    ]
    return import_playlist(
        db, platform="spotify", name=LIKED_PLAYLIST_NAME,
        items=selected, kind="liked", prune=False,
    )


SC_LIKED_PLAYLIST_NAME = "SoundCloud Likes"


def preview_soundcloud_likes(db: Session, entries: list) -> list[dict]:
    """Entry like yt-dlp -> anteprima selezionabile, senza importare nulla.

    ``already_imported`` = la traccia è già collegata alla playlist liked
    SoundCloud locale (match per platform_track_id: l'ISRC qui non esiste).
    """
    playlist = _liked_playlist(db, "soundcloud")
    platform_ids: set[str] = set()
    if playlist is not None:
        for t in tracks_for_playlist(db, playlist.id):
            if t.platform_track_id:
                platform_ids.add(t.platform_track_id)

    from app.integrations.soundcloud import uploader_from_url

    out: list[dict] = []
    for entry in entries:
        norm = normalize_soundcloud_item(entry)
        if norm is None or not norm.platform_track_id:
            continue
        out.append({
            "track_id": norm.platform_track_id,
            # Come su SoundCloud: titolo grezzo + utente (slug URL). Nessun
            # parsing artista/titolo qui: avviene all'import col fetch pieno.
            "title": (entry.get("title") or "").strip() or None,
            "uploader": uploader_from_url(norm.url),
            "duration_seconds": norm.duration_seconds,
            "artwork_url": norm.artwork_url,
            "url": norm.url,
            "already_imported": norm.platform_track_id in platform_ids,
        })
    return out


def import_selected_soundcloud_likes(db: Session, entries: list, track_ids: list[str]) -> dict:
    """Importa nella playlist liked SoundCloud SOLO le entry selezionate. Additivo."""
    wanted = {str(t) for t in track_ids}
    selected = [e for e in entries if e and str(e.get("id")) in wanted]
    return import_playlist(
        db, platform="soundcloud", name=SC_LIKED_PLAYLIST_NAME,
        items=selected, normalize=normalize_soundcloud_item,
        kind="liked", prune=False,
    )
