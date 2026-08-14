"""Normalizzazione leggera dei generi: alias del modulo core.

Implementazione unica in `app.services.genre_norm` (era byte-identica qui,
duplicata dalla fusione Sortory->Cratory). `organize/` e' il namespace
assorbito: importa dal core, non il contrario.
"""
from __future__ import annotations

from app.services.genre_norm import normalize_genre

__all__ = ["normalize_genre"]
