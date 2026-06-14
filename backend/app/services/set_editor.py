"""Editing deterministico della scaletta (MVP 3).

Rinomina, elimina, rimuove/sposta/sostituisce tracce. Dopo ogni modifica alla
sequenza ricalcola gli score di transizione con il motore deterministico
(scoring.py): l'ordine cambia, quindi prev/next cambiano e gli score vanno
ricomputati. Le motivazioni AI (ai_reason) restano invariate, tranne sulla
traccia sostituita (che non ha piu' senso conservare).
"""

import logging

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistTrack
from app.repositories import get_setlist, get_track
from app.services.scoring import risk_from_score, score_transition

logger = logging.getLogger(__name__)


class SetEditError(Exception):
    pass


def _ordered(setlist: Setlist) -> list[SetlistTrack]:
    return sorted(setlist.tracks, key=lambda st: st.position)


def _renumber(tracks: list[SetlistTrack]) -> None:
    for i, st in enumerate(sorted(tracks, key=lambda s: s.position), start=1):
        st.position = i


def recompute_transitions(setlist: Setlist) -> None:
    """Ricalcola transition_score/reason/risk per ogni traccia nell'ordine corrente."""
    ordered = _ordered(setlist)
    for i, st in enumerate(ordered):
        if i == 0:
            st.transition_score = None
            st.transition_reason = "traccia di apertura"
            st.risk_level = "low"
            continue
        ts = score_transition(ordered[i - 1].track, st.track)
        st.transition_score = float(ts.score)
        st.transition_reason = "; ".join(ts.technical_reasons)
        st.risk_level = risk_from_score(ts.score)


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


def remove_track(db: Session, setlist_id: int, position: int) -> Setlist:
    setlist = _require(db, setlist_id)
    ordered = _ordered(setlist)
    if not 1 <= position <= len(ordered):
        raise SetEditError("Posizione non valida")
    if len(ordered) <= 1:
        raise SetEditError("Il set deve contenere almeno una traccia")
    setlist.tracks.remove(ordered[position - 1])  # cascade delete-orphan
    _renumber(setlist.tracks)
    recompute_transitions(setlist)
    db.commit()
    db.refresh(setlist)
    return setlist


def move_track(db: Session, setlist_id: int, position: int, direction: str) -> Setlist:
    setlist = _require(db, setlist_id)
    ordered = _ordered(setlist)
    n = len(ordered)
    if not 1 <= position <= n:
        raise SetEditError("Posizione non valida")
    i = position - 1
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < n:  # ai bordi e' un no-op silenzioso
        ordered[i].position, ordered[j].position = ordered[j].position, ordered[i].position
        recompute_transitions(setlist)
        db.commit()
        db.refresh(setlist)
    return setlist


def replace_track(db: Session, setlist_id: int, position: int, new_track_id: int) -> Setlist:
    setlist = _require(db, setlist_id)
    ordered = _ordered(setlist)
    if not 1 <= position <= len(ordered):
        raise SetEditError("Posizione non valida")
    new_track = get_track(db, new_track_id)
    if new_track is None:
        raise SetEditError("Traccia sostitutiva inesistente")
    if any(st.track_id == new_track_id for k, st in enumerate(ordered) if k != position - 1):
        raise SetEditError("La traccia e' gia' presente nel set")
    slot = ordered[position - 1]
    slot.track_id = new_track.id
    slot.track = new_track
    slot.ai_reason = None  # la motivazione AI riguardava la traccia precedente
    recompute_transitions(setlist)
    db.commit()
    db.refresh(setlist)
    return setlist
