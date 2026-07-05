"""Ricerca file audio per nome nelle cartelle note (libreria e download slskd).

Modulo deterministico, sola lettura: nessun DB, nessuna scrittura su disco.
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.integrations.local_files import AUDIO_EXTENSIONS

MAX_RESULTS = 50
MIN_QUERY_LEN = 2


def search_roots() -> list[tuple[str, str]]:
    """Coppie (source, radice) configurate ed esistenti. Cartelle mancanti: saltate."""
    roots: list[tuple[str, str]] = []
    if settings.library_root and Path(settings.library_root).is_dir():
        roots.append(("library", settings.library_root))
    if settings.slskd_download_dir and Path(settings.slskd_download_dir).is_dir():
        roots.append(("downloads", settings.slskd_download_dir))
    return roots


def search_audio_files(query: str, *, roots: list[tuple[str, str]] | None = None,
                       cap: int = MAX_RESULTS) -> list[dict]:
    """Match in AND dei termini sul nome file (case-insensitive), max `cap` risultati."""
    terms = [t for t in query.strip().lower().split() if t]
    if not terms or len(query.strip()) < MIN_QUERY_LEN:
        return []
    hits: list[dict] = []
    for source, root in roots if roots is not None else search_roots():
        for path in sorted(Path(root).rglob("*")):
            if len(hits) >= cap:
                return hits
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            name = path.name.lower()
            if not all(t in name for t in terms):
                continue
            hits.append({
                "path": str(path),
                "name": path.name,
                "format": path.suffix.lower().lstrip(".") or None,
                "size": path.stat().st_size,
                "source": source,
            })
    return hits
