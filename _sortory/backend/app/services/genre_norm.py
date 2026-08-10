"""Normalizzazione leggera dei generi: niente vocabolario, solo pulizia.

Trim, spazi multipli, trattini come spazi, Title Case, piccola mappa alias.
Deterministica: nessuna AI, nessun provider.
"""
from __future__ import annotations

import re

# Alias noti (chiave: forma minuscola DOPO la pulizia base).
_ALIASES = {
    "drum'n'bass": "Drum & Bass",
    "drum n bass": "Drum & Bass",
    "drum and bass": "Drum & Bass",
    "dnb": "Drum & Bass",
    "d&b": "Drum & Bass",
    "edm": "EDM",
    "uk garage": "UK Garage",
    "ukg": "UK Garage",
    "idm": "IDM",
    "r&b": "R&B",
    "rnb": "R&B",
}
_SPACES = re.compile(r"\s+")


def normalize_genre(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = _SPACES.sub(" ", raw.replace("-", " ").replace("_", " ")).strip()
    if not s:
        return None
    alias = _ALIASES.get(s.lower())
    if alias:
        return alias
    return " ".join(w if w.isupper() and len(w) <= 3 else w.capitalize()
                    for w in s.split(" "))
