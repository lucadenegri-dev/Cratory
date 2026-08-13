"""Elenco dei file audio in una cartella locale.

Deterministico: scansiona ricorsivamente, ignorando cartelle e file nascosti.
Usato dal conteggio inbox della pipeline (`pipeline.py`) e dall'indicizzazione
libreria (`library_index.py`), che a valle legge tag e calcola l'identità.
"""

import os
from pathlib import Path

from app.integrations.local_files import AUDIO_EXTENSIONS


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
