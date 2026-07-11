"""Stato applicativo persistente: mini chiave-valore (niente Alembic, app locale).

Per fatti che devono sopravvivere al riavvio ma non meritano una tabella
dedicata: es. `last_index_at` (ultima indicizzazione libreria completata).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AppState


def get_state(db: Session, key: str) -> str | None:
    row = db.get(AppState, key)
    return row.value if row else None


def set_state(db: Session, key: str, value: str) -> None:
    row = db.get(AppState, key)
    if row is None:
        db.add(AppState(key=key, value=value))
    else:
        row.value = value
    db.commit()


LANGUAGE_KEY = "language"
DEFAULT_LANGUAGE = "it"


def get_language(db: Session) -> str:
    """Lingua dell'app ("it" | "en"): valori sconosciuti degradano al default."""
    value = get_state(db, LANGUAGE_KEY)
    return value if value in ("it", "en") else DEFAULT_LANGUAGE
