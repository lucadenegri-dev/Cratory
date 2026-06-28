"""Import di una cartella locale come playlist (specchio della collezione DJ).

Deterministico: scansiona i file audio, legge i tag (fallback dal nome file),
calcola l'identità via hash dello stream audio e riusa import_playlist. Non
conserva l'audio: tiene solo metadati e il path (riferimento volatile).

Le tracce locali restano SEPARATE da quelle streaming (nessuna fusione per nome):
l'identità è l'hash, non artista+titolo.
"""

import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.integrations.local_files import (
    AUDIO_EXTENSIONS,
    LocalFilesError,
    audio_hash,
    read_tags,
)
from app.services.manual_import import parse_line
from app.services.playlist_import import (
    NormalizedTrack,
    identity_normalize,
    import_playlist,
)

logger = logging.getLogger(__name__)

PLATFORM = "local_files"


def scan_folder(path: str | Path, *, recurse: bool = True) -> list[Path]:
    """Elenco ordinato dei file audio sotto `path` (ricorsivo di default)."""
    root = Path(path)
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            if Path(fn).suffix.lower() in AUDIO_EXTENSIONS:
                files.append(Path(dirpath) / fn)
        if not recurse:
            dirnames.clear()
    return sorted(files)


def build_normalized(path: str | Path) -> NormalizedTrack:
    """Costruisce un NormalizedTrack da un file. Solleva LocalFilesError se l'hash fallisce."""
    p = Path(path)
    tags = read_tags(p)
    artist, title = tags["artist"], tags["title"]
    if not artist or not title:
        # Fallback dal nome file ("Artista - Titolo"), stesso parser dell'import manuale.
        parsed = parse_line(p.stem)
        if parsed is not None:
            fb_artist, fb_title = parsed
            artist = artist or fb_artist
            title = title or fb_title
    digest = audio_hash(p)  # può sollevare LocalFilesError
    return NormalizedTrack(
        platform=PLATFORM,
        platform_track_id=digest,
        title=title,
        artist=artist,
        album=tags["album"],
        duration_seconds=tags["duration_seconds"],
        url=None,
        artwork_url=None,
        isrc=tags["isrc"],
        added_at=None,
        year=tags["year"],
        local_path=str(p.resolve()),
    )


def import_local_folder(
    db: Session,
    *,
    path: str | Path,
    name: str | None = None,
    recurse: bool = True,
    on_progress=None,
) -> dict:
    """Importa una cartella come playlist. Ritorna report con created/updated/failed/errors.

    La fase pesante (tag + hash) è qui: on_progress(processed, total) viene chiamato per
    file. La playlist si crea solo se almeno una traccia è stata normalizzata (total>0).
    """
    root = Path(path)
    playlist_name = name or root.name or "Cartella locale"
    files = scan_folder(root, recurse=recurse)
    total = len(files)

    items: list[NormalizedTrack] = []
    failed = 0
    errors: list[dict] = []
    for i, f in enumerate(files, start=1):
        try:
            items.append(build_normalized(f))
        except LocalFilesError as exc:
            failed += 1
            errors.append({"path": str(f), "error": str(exc)})
            logger.warning("File locale saltato %s: %s", f, exc)
        if on_progress is not None:
            on_progress(i, total)

    if not items:
        return {
            "playlist_id": None, "name": playlist_name, "created": 0, "updated": 0,
            "removed": 0, "skipped": 0, "failed": failed, "total": 0, "errors": errors,
        }

    report = import_playlist(
        db, platform=PLATFORM, name=playlist_name, items=items,
        normalize=identity_normalize, kind="local",
    )
    report["failed"] = failed
    report["errors"] = errors
    return report
