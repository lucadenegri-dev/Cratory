"""Rinomina ed elimina un set.

Era l'editor della scaletta generata: rimuoveva, spostava e sostituiva tracce
per posizione, riassegnando ruoli e ricalcolando gli score di transizione. Con
la rimozione del generatore (2026-09-19) quella superficie e' sparita — un set
si prepara a mano, e le sue mutazioni stanno in `manual_set.py`, che ragiona per
id e non per posizione. Restano le due operazioni che valgono per qualunque set.
"""

import logging

from sqlalchemy.orm import Session

from app.models import Setlist
from app.repositories import get_setlist

logger = logging.getLogger(__name__)


class SetEditError(Exception):
    pass


def _require(db: Session, setlist_id: int) -> Setlist:
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise SetEditError("Set non trovato")
    return setlist


def rename_set(db: Session, setlist_id: int, name: str) -> Setlist:
    setlist = _require(db, setlist_id)
    setlist.name = name.strip()
    db.commit()
    db.refresh(setlist)
    return setlist


def delete_set(db: Session, setlist_id: int) -> None:
    setlist = _require(db, setlist_id)
    db.delete(setlist)
    db.commit()
    logger.info("Set %s eliminato", setlist_id)
