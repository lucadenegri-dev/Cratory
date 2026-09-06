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


def delete_state(db: Session, key: str) -> None:
    """Rimuove una chiave (no-op se assente). Usato per "azzera override" nei
    settings di config: cancellare la riga = tornare al default `.env`."""
    row = db.get(AppState, key)
    if row is not None:
        db.delete(row)
        db.commit()


def get_states_by_prefix(db: Session, prefix: str) -> dict[str, str]:
    """Tutte le coppie chiave/valore la cui chiave inizia per `prefix`, con il
    prefisso rimosso dalla chiave restituita. Serve a `runtime_settings` per
    caricare in blocco gli override di config (`cfg.*`)."""
    from sqlalchemy import select
    rows = db.execute(
        select(AppState).where(AppState.key.startswith(prefix))
    ).scalars().all()
    return {row.key[len(prefix):]: row.value for row in rows}


LANGUAGE_KEY = "language"
DEFAULT_LANGUAGE = "it"


def get_language(db: Session) -> str:
    """Lingua dell'app ("it" | "en"): valori sconosciuti degradano al default."""
    value = get_state(db, LANGUAGE_KEY)
    return value if value in ("it", "en") else DEFAULT_LANGUAGE


DISCOGS_ENABLED_KEY = "discovery.discogs_enabled"


def get_discogs_enabled(db: Session) -> bool:
    """Discogs come sorgente nella barra del Dig. È una preferenza di
    interfaccia: il backend resta permissivo e `/api/discovery/dig` accetta
    `source=discogs` comunque, così un link salvato torna a funzionare appena
    si riaccende. Default acceso; solo "0" spegne, una riga con un valore
    inatteso non spegne niente in silenzio."""
    return get_state(db, DISCOGS_ENABLED_KEY) != "0"
