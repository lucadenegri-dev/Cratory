"""La versione dell'app, da un'unica fonte.

Il file `VERSION` nella radice del repository è quella fonte. La variabile
d'ambiente lo scavalca per lo stesso motivo per cui esiste `CRATORY_BIN_DIR`:
in un bundle Tauri non c'è nessuna radice di repository da cui leggere, e il
packager passa il numero dall'ambiente.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.core.config import BACKEND_DIR

VERSION_ENV = "CRATORY_VERSION"
FALLBACK = "0.0.0-dev"


def _percorso_version() -> Path:
    """Il file sta nella radice del repository, un livello sopra `backend/`."""
    return BACKEND_DIR.parent / "VERSION"


def app_version() -> str:
    """Ambiente → file → default. Non solleva mai: un checkout senza il file
    deve poter avviare l'app, perché la versione è un'informazione e non una
    precondizione per funzionare."""
    dall_ambiente = (os.environ.get(VERSION_ENV) or "").strip()
    if dall_ambiente:
        return dall_ambiente
    try:
        letto = _percorso_version().read_text().strip()
    except OSError:
        return FALLBACK
    return letto or FALLBACK
