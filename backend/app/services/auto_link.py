"""Proposta di collegamento automatico file-locale per le tracce da sistemare.

Sola lettura: per ogni traccia "da sistemare" cerca sul disco (LIBRARY_ROOT +
download slskd) il primo file il cui nome contiene tutti i termini di
"artista titolo". NON collega nulla: restituisce solo proposte da confermare
lato UI (il collegamento vero passa poi per link_local_file, che valida ed
esegue il possesso). Il disco viene scandito una sola volta per tutte le tracce.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.integrations.local_files import AUDIO_EXTENSIONS
from app.repositories import tracks_download_pending
from app.services.file_search import search_roots
from app.services.track_label import track_label


def _all_audio_files() -> list[tuple[str, Path]]:
    """(source, path) di ogni file audio nelle radici configurate, scansione unica."""
    files: list[tuple[str, Path]] = []
    for source, root in search_roots():
        for path in sorted(Path(root).rglob("*")):
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                files.append((source, path))
    return files


def auto_link_preview(db: Session) -> list[dict]:
    """Per ogni traccia da sistemare, il primo file locale che combacia (o None)."""
    files = _all_audio_files()
    out: list[dict] = []
    for t in tracks_download_pending(db):
        query = f"{(t.artist or '').strip()} {(t.title or '').strip()}".strip()
        terms = [x for x in query.lower().split() if x]
        hit = None
        if terms and len(query) >= 2:
            for source, path in files:
                name = path.name.lower()
                if all(term in name for term in terms):
                    hit = {
                        "path": str(path),
                        "name": path.name,
                        "format": path.suffix.lower().lstrip(".") or None,
                        "size": path.stat().st_size,
                        "source": source,
                    }
                    break
        out.append({
            "track_id": t.id,
            "label": track_label(t),
            "artist": t.artist,
            "title": t.title,
            "hit": hit,
        })
    return out
