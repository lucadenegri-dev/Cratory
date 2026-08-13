"""Collega un file audio acquisito a una Track esistente (ownership).

Non tocca lo status di enrichment ne' le feature musicali. Calcola l'audio-hash
(best-effort): e' la chiave di riaggancio quando Sortory rinomina/sposta il
file nella libreria canonica.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.integrations.local_files import (
    AUDIO_EXTENSIONS, LocalFilesError, audio_hash, read_audio_quality,
)
from app.models import Track
from app.organize.services.file_link import aggiorna_primary
from app.repositories import get_primary_file, merge_tracks
from app.services.genre_align import align_track_genre

logger = logging.getLogger(__name__)


def attach_local_file(db: Session, track: Track, *, path: str,
                      fmt: str | None = None, bitrate: int | None = None) -> Track:
    track.has_local_file = True
    track.local_path = path
    track.local_format = fmt
    track.local_bitrate = bitrate
    try:
        track.audio_hash = audio_hash(path)
    except LocalFilesError as exc:
        # L'hash e' il riaggancio futuro, non un requisito del possesso: non bloccare.
        logger.warning("Audio-hash non calcolabile per %s: %s", path, exc)
    try:
        # Firma incrementale (stessa che scrive l'indice): senza, il prossimo
        # index_library non puo' skippare il file e lo ri-hasha (decodifica ffmpeg).
        stat = Path(path).stat()
        track.local_mtime = stat.st_mtime
        track.local_size = stat.st_size
    except OSError as exc:
        logger.warning("stat() non riuscita per %s: %s", path, exc)
    db.flush()  # rende visibili hash/path per la ricerca dei doppioni
    # Se un'altra traccia possiede gia' lo stesso file (es. gia' indicizzata come
    # local_files), la fonde qui dentro: niente doppione dopo il collegamento.
    conds = [Track.local_path == path]
    if track.audio_hash:
        conds.append(Track.audio_hash == track.audio_hash)
    dupes = db.scalars(
        select(Track).where(and_(Track.id != track.id, or_(*conds)))
    ).all()
    for dup in dupes:
        merge_tracks(db, track, dup)
    # Dopo la fusione dei doppioni: la traccia superstite è quella che deve
    # portare l'aggancio al file, se Organize l'ha già indicizzato.
    aggiorna_primary(db, track)
    # Stessa classe di difetto di D8 (collega_tracce), sul percorso
    # dell'acquisizione: un lead che arriva con un genere streaming e ora
    # possiede un file lo terrebbe per sempre, anche se il tag dice altro. Lo
    # scan non ripara: quella riga AudioFile è stata INSERITA, non aggiornata,
    # quindi la sua guardia sul tag cambiato non scatta mai per questo file.
    # Se Organize non ha ancora scansionato il path, `aggiorna_primary` non
    # trova nulla e qui non c'è niente da allineare: ci penserà lo scan.
    primary = get_primary_file(db, track)
    if primary is not None:
        align_track_genre(track, primary.genre, apply=True)
    db.commit()
    db.refresh(track)
    return track


class LinkFileError(ValueError):
    """Percorso non valido per il collegamento manuale (inesistente o non audio)."""


def link_local_file(db: Session, track: Track, *, path: str) -> Track:
    """Collegamento manuale di un file su disco: valida e azzera l'esito download.

    L'uscita dall'archivio "da sistemare" avviene qui, qualunque sia la pagina
    da cui si collega (dettaglio traccia o archivio).
    """
    p = Path(path).expanduser()
    if not p.is_file():
        raise LinkFileError(f"File non trovato: {p}")
    if p.suffix.lower() not in AUDIO_EXTENSIONS:
        raise LinkFileError(f"Estensione non audio: {p.suffix or '(nessuna)'}")
    quality = read_audio_quality(p)
    track = attach_local_file(db, track, path=str(p), fmt=quality["format"],
                              bitrate=quality["bitrate"])
    track.last_download_outcome = None
    track.last_download_reason = None
    db.commit()
    db.refresh(track)
    return track
