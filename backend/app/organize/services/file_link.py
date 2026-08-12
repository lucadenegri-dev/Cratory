"""Aggancio fra la traccia e il suo file, e derivazione della collocazione.

`Track.primary_file_id` e `AudioFile.track_id` sono le due facce della stessa
relazione. La prima è la cache che dice da quale file arrivano i `local_*`; la
seconda è la proprietà del file. Vanno mantenute insieme: qui stanno le uniche
funzioni autorizzate a scriverle.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Track
from app.organize.models import AudioFile


def _dentro(path: str, radice: str) -> bool:
    """True se `path` sta sotto `radice`. Confronto per componenti, non per
    prefisso di stringa: altrimenti `/Music/LibraryVecchia` risulterebbe dentro
    `/Music/Library`."""
    if not radice:
        return False
    try:
        Path(path).relative_to(Path(radice))
    except ValueError:
        return False
    return True


def deriva_location(path: str, *, library_root: str, inbox_root: str) -> str:
    """"library" o "inbox". Sollevare è voluto: un file fuori dalle due radici
    non dovrebbe esistere nell'indice, e inventargli una collocazione
    nasconderebbe una configurazione sbagliata."""
    if _dentro(path, library_root):
        return "library"
    if _dentro(path, inbox_root):
        return "inbox"
    raise ValueError(f"path fuori da entrambe le radici configurate: {path}")


def aggiorna_primary(db: Session, track: Track) -> None:
    """Allinea `track.primary_file_id` (e il `track_id` del file) al file che
    corrisponde a `track.local_path`. Se quel file non è indicizzato, azzera.

    Non fa commit: il chiamante decide la transazione."""
    if not track.local_path:
        track.primary_file_id = None
        return
    file = db.scalar(select(AudioFile).where(AudioFile.path == track.local_path))
    if file is None:
        track.primary_file_id = None
        return
    track.primary_file_id = file.id
    file.track_id = track.id


def stacca_file(db: Session, file_id: int) -> int:
    """Azzera `primary_file_id` sulle tracce che puntano a questo file.

    Da chiamare PRIMA di cancellare un AudioFile: la FK non ha una
    relationship() da quel lato, quindi nessuno azzera i figli al posto nostro —
    ed è la stessa classe di difetto delle sei coppie senza relationship trovate
    nell'audit di F2.

    NON tocca `has_local_file`: stabilire se la traccia è posseduta è compito
    dell'indicizzazione libreria."""
    esito = db.execute(
        update(Track).where(Track.primary_file_id == file_id).values(primary_file_id=None)
    )
    return esito.rowcount or 0
