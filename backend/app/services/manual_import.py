"""Import manuale di una playlist da testo libero o CSV (backlog -> attivo 14/06/2026).

Caso d'uso: l'utente incolla una tracklist ("Artista - Titolo" per riga, oppure
CSV "artista,titolo") e ne ricava una playlist nella libreria, pronta per
l'enrichment (BPM/key/...) e per il Set Builder. Nessuna rete: solo parsing + DB.

Le tracce manuali non hanno identita' di streaming: il match/dedup e' su
artista+titolo normalizzati (case-insensitive).
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Playlist, Track
from app.repositories import add_track_to_playlist, ci_equals, recount_playlist
from app.services.track_status import refresh_status

logger = logging.getLogger(__name__)

# Separatori "Artista - Titolo" (trattino semplice, en dash, em dash).
_DASH_SEPARATORS = (" - ", " – ", " — ")


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def parse_line(line: str) -> tuple[str | None, str | None] | None:
    """Una riga -> (artista, titolo). None se la riga e' vuota.

    Formati riconosciuti, in ordine: 'Artista - Titolo', TSV, CSV 'artista,titolo'.
    Se non c'e' separatore, l'intera riga e' il titolo (artista sconosciuto).
    """
    s = line.strip()
    if not s:
        return None
    for sep in _DASH_SEPARATORS:
        if sep in s:
            artist, title = s.split(sep, 1)
            return artist.strip() or None, title.strip() or None
    for sep in ("\t", ","):
        if sep in s:
            artist, title = s.split(sep, 1)
            return artist.strip() or None, title.strip() or None
    return None, s


def _find_by_name(db: Session, artist: str | None, title: str) -> Track | None:
    stmt = select(Track).where(ci_equals(Track.title, title))  # match esatto case-insensitive (%/_ escapati)
    stmt = stmt.where(ci_equals(Track.artist, artist)) if artist else stmt.where(Track.artist.is_(None))
    return db.scalar(stmt)


def _import_pairs(db: Session, *, name: str, items, default_name: str, source: str = "manual") -> dict:
    """Crea una playlist da coppie ``(artista, titolo, isrc)``, marcata con `source`
    (es. 'manual' o 'shazam'). Idempotente sui nomi traccia (dedup case-insensitive).
    Ritorna il report d'import."""
    playlist = Playlist(platform=source, name=name.strip() or default_name, kind=source)
    db.add(playlist)
    db.flush()  # serve playlist.id

    created = updated = skipped = 0
    seen: set[tuple[str, str]] = set()
    for artist, title, isrc in items:
        if not title:
            skipped += 1
            continue
        key = (_norm(artist), _norm(title))
        if key in seen:
            skipped += 1  # duplicato nello stesso lotto
            continue
        seen.add(key)

        existing = _find_by_name(db, artist, title)
        if existing is not None:
            refresh_status(existing)
            db.flush()
            add_track_to_playlist(db, existing, playlist)
            updated += 1
        else:
            track = Track(source_type=source, platform=source, artist=artist, title=title, isrc=isrc or None)
            db.add(track)
            refresh_status(track)
            db.flush()
            add_track_to_playlist(db, track, playlist)
            created += 1

    recount_playlist(db, playlist)
    db.commit()
    db.refresh(playlist)
    return {
        "playlist_id": playlist.id,
        "name": playlist.name,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total": created + updated,
    }


def import_manual_playlist(db: Session, *, name: str, text: str) -> dict:
    """Crea una playlist 'manual' dalle righe di testo ('Artista - Titolo'/CSV/TSV).
    Idempotente sui nomi traccia. Ritorna {playlist_id, name, created, updated, skipped, total}."""
    items = []
    for raw in text.splitlines():
        parsed = parse_line(raw)
        if parsed is None:
            continue
        items.append((parsed[0], parsed[1], None))
    report = _import_pairs(db, name=name, items=items, default_name="Playlist manuale")
    logger.info("Import manuale '%s': %s", name, report)
    return report


def import_track_pairs(db: Session, *, name: str, items, source: str = "manual") -> dict:
    """Crea una playlist da coppie ``(artista, titolo, isrc)`` gia' separate, marcata
    con `source` (usato per importare un set Shazam come playlist di lead)."""
    report = _import_pairs(db, name=name, items=items, default_name="Playlist", source=source)
    logger.info("Import coppie '%s' (%s): %s", name, source, report)
    return report
