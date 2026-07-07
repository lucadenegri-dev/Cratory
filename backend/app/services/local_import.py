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
    """Elenco ordinato dei file audio sotto `path` (ricorsivo di default).

    Ignora cartelle e file nascosti (nome che inizia con '.', es. `.quarantine`,
    `.DS_Store`, `.git`): non sono contenuto di libreria/inbox da conteggiare o
    indicizzare."""
    root = Path(path)
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
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
