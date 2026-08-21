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


def parse_version(raw: str) -> tuple[int, int, int] | None:
    """`v0.10.0` e `0.10.0` danno lo stesso risultato. `None` se non è una
    versione su cui si possa ragionare: un tag lo scrive una persona a mano,
    e non deve poter far esplodere il controllo aggiornamenti."""
    testo = (raw or "").strip().lstrip("vV")
    numeri = testo.split("+", 1)[0].split("-", 1)[0].split(".")
    if len(numeri) != 3:
        return None
    try:
        maggiore, minore, patch = (int(n) for n in numeri)
    except ValueError:
        return None
    return maggiore, minore, patch


def is_newer(candidate: str, current: str) -> bool:
    """True se `candidate` è più recente di `current`.

    Confronto fra numeri, non fra stringhe: "0.10.0" < "0.9.0" in ordine
    testuale, e chi lo confrontasse così non mostrerebbe mai un aggiornamento
    dopo la nona minor. Se una delle due non è leggibile la risposta è False:
    meglio non annunciare un aggiornamento che annunciarne uno inventato.
    """
    a = parse_version(candidate)
    b = parse_version(current)
    if a is None or b is None:
        return False
    return a > b
