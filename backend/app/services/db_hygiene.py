"""Pulizia una-tantum disk-first: allinea il DB alle regole attuali.

Due operazioni, entrambe con `apply` (False = dry-run: conta ciò che cambierebbe
senza scrivere):

- `purge_lead_residue`: sui lead (senza file su disco) azzera i campi che nessun
  flusso attuale scrive più (residui della vecchia catena di enrichment).
- `realign_owned_from_disk`: sulle possedute rilegge i tag dal file e rende il disco
  autorevole sui campi disco-derivabili (mai tocca i file: solo lettura).

Non altera BPM/tonalità (Rekordbox), né la cover (Spotify): la cover da disco è
servita on-demand dall'endpoint, non scritta qui.
"""
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.local_files import read_tags
from app.models import Track
from app.repositories import merge_tracks
from app.services.energy import apply_estimated_energy
from app.services.genre_norm import normalize_genre
from app.services.manual_import import parse_line

# Campi senza writer attuale per un lead puro (streaming, no file, no Rekordbox):
# ogni valore presente è residuo legacy.
LEAD_RESIDUE_FIELDS = ("genre", "bpm", "camelot_key", "energy")

# Campi che, su una posseduta, devono rispecchiare il disco.
DISK_FIELDS = ("title", "artist", "album", "genre", "year", "isrc", "duration_seconds", "label")


def _dedupe_keeper(group: list[Track]) -> Track:
    """Nella dedup, tiene la traccia con identità streaming (spotify_id/isrc); a
    parità, quella con l'id minore."""
    return max(group, key=lambda t: (1 if (t.spotify_id or t.isrc) else 0, -t.id))


def dedupe_by_audio_hash(db: Session, *, apply: bool) -> int:
    """Fonde le tracce che condividono lo stesso `audio_hash` (stesso file su disco):
    tiene la 'migliore' e fonde le altre dentro. Ritorna quante ne (verrebbero) fuse."""
    groups = db.execute(
        select(Track.audio_hash, func.count())
        .where(Track.audio_hash.is_not(None), Track.audio_hash != "")
        .group_by(Track.audio_hash)
        .having(func.count() > 1)
    ).all()
    merged = 0
    for digest, _n in groups:
        rows = list(db.scalars(select(Track).where(Track.audio_hash == digest)))
        keep = _dedupe_keeper(rows)
        for t in rows:
            if t.id != keep.id:
                merged += 1
                if apply:
                    merge_tracks(db, keep, t)
    if apply:
        db.commit()
    return merged


def purge_lead_residue(db: Session, *, apply: bool) -> dict[str, int]:
    """Azzera sui lead (`has_local_file` non True) i campi in LEAD_RESIDUE_FIELDS.
    Ritorna, per campo, quanti valori sono (o sarebbero, in dry-run) azzerati."""
    counts = {f: 0 for f in LEAD_RESIDUE_FIELDS}
    leads = db.scalars(select(Track).where(Track.has_local_file.is_not(True))).all()
    for t in leads:
        for f in LEAD_RESIDUE_FIELDS:
            if getattr(t, f) is not None:
                counts[f] += 1
                if apply:
                    setattr(t, f, None)
    if apply:
        db.commit()
    return counts


def _disk_values(local_path: str) -> dict:
    """Valori disco-derivabili da un file (con fallback nome file per artist/title)."""
    tags = read_tags(local_path)
    artist, title = tags.get("artist"), tags.get("title")
    if not artist or not title:
        parsed = parse_line(Path(local_path).stem)
        if parsed is not None:
            artist = artist or parsed[0]
            title = title or parsed[1]
    genre = tags.get("genre")
    return {
        "title": title,
        "artist": artist,
        "album": tags.get("album"),
        "genre": normalize_genre(genre) if genre else None,
        "year": tags.get("year"),
        "isrc": tags.get("isrc"),
        "duration_seconds": tags.get("duration_seconds"),
        "label": tags.get("label"),
    }


def realign_owned_from_disk(db: Session, *, apply: bool) -> dict:
    """Sulle possedute (`has_local_file` True) con file esistente, sovrascrive i campi
    disco-derivabili con i valori del file (svuota se assenti) e ricalcola l'energia.
    Non tocca bpm/camelot_key (Rekordbox) né album_art_url (Spotify). Ritorna
    `{changed_tracks, changed_fields, missing_file}`."""
    changed_tracks = 0
    changed_fields = 0
    missing_file = 0
    owned = db.scalars(select(Track).where(Track.has_local_file.is_(True))).all()
    for t in owned:
        if not t.local_path or not Path(t.local_path).exists():
            missing_file += 1
            continue
        new = _disk_values(t.local_path)
        track_changed = False
        for f in DISK_FIELDS:
            if getattr(t, f) != new[f]:
                track_changed = True
                changed_fields += 1
                if apply:
                    setattr(t, f, new[f])
        if track_changed:
            changed_tracks += 1
            if apply:
                apply_estimated_energy(t)
    if apply:
        db.commit()
    return {"changed_tracks": changed_tracks, "changed_fields": changed_fields, "missing_file": missing_file}
