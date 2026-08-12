"""Motore Scanner deterministico: walk del FS, lettura, upsert in DB."""

import logging
import os
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.config import settings
from app.organize.integrations import content_hash, tagio
from app.organize.models import AudioFile, ScanRoot, utcnow
from app.organize.schemas import ScanSummary
from app.organize.services.file_link import deriva_location, stacca_file
from app.organize.services.roots import root_id_per

logger = logging.getLogger(__name__)

_TAG_FIELDS = (
    "bitrate", "sample_rate", "channels", "duration_s", "artist", "title", "album",
    "album_artist", "genre", "year", "label", "track_no", "comment", "isrc", "has_cover",
)


def _iter_audio_files(root_path: str) -> Iterator[tuple[str, str]]:
    for dirpath, dirs, names in os.walk(root_path):
        # Pota le directory nascoste (es. .quarantine dell'Apply): modificare
        # `dirs` in-place impedisce a os.walk di scenderci.
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext in settings.audio_exts:
                yield os.path.join(dirpath, name), ext


def _scan_file_fields(path: str, ext: str) -> dict:
    """Campi aggiornabili di AudioFile per un file, con errori isolati per-file."""
    h, method = content_hash.compute(path, ext)
    fields = {
        "ext": ext.lstrip("."),
        "size_bytes": 0,
        "content_hash": h,
        "hash_method": method,
        "scan_error": None,
        "has_cover": False,
    }
    for key in _TAG_FIELDS:
        fields.setdefault(key, None)
    try:
        fields["size_bytes"] = os.path.getsize(path)
    except OSError as exc:
        fields["scan_error"] = f"errore lettura file: {exc}"
        return fields
    try:
        info = tagio.read_info(path)
        tags = tagio.read_tags(path)
    except tagio.TagReadError as exc:
        fields["scan_error"] = str(exc)
        return fields
    fields.update(
        bitrate=info.bitrate, sample_rate=info.sample_rate,
        channels=info.channels, duration_s=info.duration_s,
        artist=tags.artist, title=tags.title, album=tags.album,
        album_artist=tags.album_artist, genre=tags.genre, year=tags.year,
        label=tags.label, track_no=tags.track_no, comment=tags.comment,
        isrc=tags.isrc, has_cover=tags.has_cover,
    )
    return fields


def _location_per(path: str) -> str:
    """Collocazione del file rispetto alle due cartelle di Settings.

    Un path fuori da entrambe non è libreria canonica per definizione, quindi
    "inbox" è la risposta conservativa; il warning serve a far emergere la
    configurazione incoerente (una ScanRoot che non sta né in LIBRARY_ROOT né in
    SLSKD_DOWNLOAD_DIR) invece di lasciarla passare muta. Con F3b, tolte le
    ScanRoot, il caso sparisce.
    """
    try:
        return deriva_location(path, library_root=runtime_settings.library_root(),
                               inbox_root=runtime_settings.slskd_download_dir())
    except ValueError:
        logger.warning("Path fuori dalle radici configurate, location=inbox: %s", path)
        return "inbox"


def scan(db: Session, roots: list[ScanRoot], on_progress=None) -> ScanSummary:
    """Scansiona le root date e aggiorna il DB.

    Semantica di idempotenza:
    - Nessuna riga duplicata: ogni file sul disco corrisponde a esattamente una riga.
    - Nessun falso missing/moved: i file invariati restano "present".
    - ``summary.updated`` conta le righe *ri-toccate* (``last_scanned_at`` aggiornato),
      NON le righe il cui contenuto è cambiato.  Anche una re-scansione su disco
      immutato produce ``updated == N`` (dove N è il numero di file già noti).
      Chunk 2 non deve interpretare ``updated`` come "contenuto modificato".
    """
    summary = ScanSummary(roots=[r.id for r in roots], started_at=utcnow())
    work = [(root, p, e) for root in roots for p, e in _iter_audio_files(root.path)]
    summary.found = len(work)
    seen_by_root: dict[int, set[str]] = {r.id: set() for r in roots}
    new_inserts: list[AudioFile] = []
    for index, (root, path, ext) in enumerate(work):
        seen_by_root[root.id].add(path)
        fields = _scan_file_fields(path, ext)
        existing = db.scalar(
            select(AudioFile).where(AudioFile.root_id == root.id, AudioFile.path == path)
        )
        if existing is None:
            # Stesso timestamp per entrambi: un file "nuovo" ha
            # first_seen_at == last_scanned_at finché non lo si ri-scansiona
            # (base del filtro "solo file nuovi").
            now = utcnow()
            row = AudioFile(
                root_id=root_id_per(db, _location_per(path)), path=path, status="present",
                location=_location_per(path),
                first_seen_at=now, last_scanned_at=now, **fields,
            )
            db.add(row)
            new_inserts.append(row)
            summary.inserted += 1
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.status = "present"
            existing.last_scanned_at = utcnow()
            summary.updated += 1
        if fields["scan_error"]:
            summary.errors += 1
        if on_progress is not None:
            on_progress(index + 1, summary.found, "scanning")
    db.flush()  # assegna gli id ai nuovi insert
    _reconcile(db, roots, seen_by_root, new_inserts, summary)
    for root in roots:
        root.last_scanned_at = utcnow()
    db.commit()
    summary.finished_at = utcnow()
    return summary


def _reconcile(db, roots, seen_by_root, new_inserts, summary) -> None:
    """Marca i file spariti come missing; se l'hash combacia con un nuovo insert,
    li tratta come spostamento (aggiorna il path della riga esistente)."""
    inserts_by_key: dict[tuple[int, str], AudioFile] = {}
    for row in new_inserts:
        if row.content_hash:
            inserts_by_key.setdefault((row.root_id, row.content_hash), row)
    for root in roots:
        seen = seen_by_root[root.id]
        all_rows = db.scalars(select(AudioFile).where(AudioFile.root_id == root.id)).all()
        gone = [r for r in all_rows if r.path not in seen and r.status != "missing"]
        for row in gone:
            key = (root.id, row.content_hash) if row.content_hash else None
            cand = inserts_by_key.get(key) if key else None
            if cand is not None and cand.id != row.id:
                moved_path = cand.path
                # Il file esce dall'indice: nessuna Track deve restare a
                # puntarlo. `cand` nasce in questo stesso scan, quindi di norma
                # non è ancora agganciato — ma se è già stato flushato può
                # esserlo, e la FK non ha chi la ordini. Costa una UPDATE.
                if cand.id is not None:
                    stacca_file(db, cand.id)
                db.delete(cand)
                db.flush()
                row.path = moved_path
                # Il file si è spostato: può aver attraversato il confine
                # inbox↔library (è esattamente ciò che fa un Apply).
                row.location = _location_per(moved_path)
                row.root_id = root_id_per(db, row.location)
                row.status = "present"
                row.last_scanned_at = utcnow()
                summary.moved += 1
                summary.inserted -= 1
                del inserts_by_key[key]
            else:
                row.status = "missing"
                summary.missing += 1
