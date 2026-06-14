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
    stmt = select(Track).where(Track.title.ilike(title))  # ilike senza % = match esatto case-insensitive
    stmt = stmt.where(Track.artist.ilike(artist)) if artist else stmt.where(Track.artist.is_(None))
    return db.scalar(stmt)


def import_manual_playlist(db: Session, *, name: str, text: str) -> dict:
    """Crea una playlist 'manual' dalle righe di testo. Idempotente sui nomi traccia.

    Ritorna un report {playlist_id, name, created, updated, skipped, total}.
    """
    playlist = Playlist(platform="manual", name=name.strip() or "Playlist manuale", kind="manual")
    db.add(playlist)
    db.flush()  # serve playlist.id

    created = updated = skipped = 0
    seen: set[tuple[str, str]] = set()
    for raw in text.splitlines():
        parsed = parse_line(raw)
        if parsed is None:
            continue
        artist, title = parsed
        if not title:
            skipped += 1
            continue
        key = (_norm(artist), _norm(title))
        if key in seen:
            skipped += 1  # duplicato nello stesso incolla
            continue
        seen.add(key)

        existing = _find_by_name(db, artist, title)
        if existing is not None:
            existing.playlist_id = playlist.id
            existing.playlist_name = playlist.name
            refresh_status(existing)
            updated += 1
        else:
            track = Track(
                source_type="manual", platform="manual",
                playlist_id=playlist.id, playlist_name=playlist.name,
                artist=artist, title=title,
            )
            db.add(track)
            refresh_status(track)
            created += 1

    playlist.track_count = created + updated
    db.commit()
    db.refresh(playlist)
    report = {
        "playlist_id": playlist.id,
        "name": playlist.name,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total": created + updated,
    }
    logger.info("Import manuale '%s': %s", name, report)
    return report
