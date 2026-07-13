"""Ricerca file audio per nome nelle cartelle note (libreria e download slskd).

Modulo deterministico, sola lettura: nessun DB, nessuna scrittura su disco.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.integrations.local_files import AUDIO_EXTENSIONS

MAX_RESULTS = 50
MIN_QUERY_LEN = 2

# TTL della cache della lista file per radice: l'utente digita, ogni tasto
# rifaceva `rglob("*")` sull'intera cartella. App personale, mono-utente: 30s
# di scarto tra un ricerca e la successiva e' invisibile mentre digita, ma
# evita di rimaterializzare l'intero albero ad ogni keystroke. Invalidazione
# SOLO a scadenza TTL (niente invalidazione su scrittura: non serve qui).
CACHE_TTL_SECONDS = 30.0

Clock = Callable[[], float]

# root -> (timestamp letto con `clock`, lista file audio ordinata)
_cache: dict[str, tuple[float, list[Path]]] = {}


def search_roots() -> list[tuple[str, str]]:
    """Coppie (source, radice) configurate ed esistenti. Cartelle mancanti: saltate."""
    roots: list[tuple[str, str]] = []
    if settings.library_root and Path(settings.library_root).is_dir():
        roots.append(("library", settings.library_root))
    if settings.slskd_download_dir and Path(settings.slskd_download_dir).is_dir():
        roots.append(("downloads", settings.slskd_download_dir))
    return roots


def _scan_audio_files(root: str) -> list[Path]:
    return sorted(
        p for p in Path(root).rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )


def _cached_audio_files(root: str, *, ttl: float, clock: Clock) -> list[Path]:
    """Lista file audio sotto `root`, dalla cache se letta entro `ttl` secondi fa."""
    now = clock()
    cached = _cache.get(root)
    if cached is not None and now - cached[0] < ttl:
        return cached[1]
    files = _scan_audio_files(root)
    _cache[root] = (now, files)
    return files


def search_audio_files(query: str, *, roots: list[tuple[str, str]] | None = None,
                       cap: int = MAX_RESULTS, ttl: float = CACHE_TTL_SECONDS,
                       clock: Clock = time.monotonic) -> list[dict]:
    """Match in AND dei termini sul nome file (case-insensitive), max `cap` risultati.

    La lista file per radice viene letta dalla cache TTL (vedi `_cached_audio_files`):
    `clock` e' iniettabile nei test per controllare lo scorrere del tempo senza sleep.
    """
    terms = [t for t in query.strip().lower().split() if t]
    if not terms or len(query.strip()) < MIN_QUERY_LEN:
        return []
    hits: list[dict] = []
    for source, root in roots if roots is not None else search_roots():
        for path in _cached_audio_files(root, ttl=ttl, clock=clock):
            if len(hits) >= cap:
                return hits
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
