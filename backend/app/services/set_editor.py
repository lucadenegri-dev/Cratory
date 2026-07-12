"""Editing deterministico della scaletta (MVP 3).

Rinomina, elimina, rimuove/sposta/sostituisce tracce. Dopo ogni modifica alla
sequenza ricalcola gli score di transizione con il motore deterministico
(scoring.py): l'ordine cambia, quindi prev/next cambiano e gli score vanno
ricomputati. Quando le posizioni cambiano (rimozione/spostamento) i ruoli
vengono riassegnati con la stessa logica della generazione (assign_roles) e
le note AI (ai_reason/transition_note) delle tracce con vicini cambiati
vengono azzerate: una nota azzerata e' onesta, una stantia mente. Le coppie
non toccate conservano le loro.
"""

import logging

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistTrack
from app.repositories import get_setlist, get_track
from app.services.scoring import risk_from_score, score_transition
from app.services.set_generator import assign_roles

logger = logging.getLogger(__name__)


class SetEditError(Exception):
    pass


def _ordered(setlist: Setlist) -> list[SetlistTrack]:
    return sorted(setlist.tracks, key=lambda st: st.position)


def _renumber(tracks: list[SetlistTrack]) -> None:
    for i, st in enumerate(sorted(tracks, key=lambda s: s.position), start=1):
        st.position = i


def _reassign_roles(setlist: Setlist) -> None:
    """Riassegna i ruoli posizionali con la stessa logica della generazione."""
    ordered = _ordered(setlist)
    for st, role in zip(ordered, assign_roles(len(ordered))):
        st.role = role


def _clear_ai_notes(setlist: Setlist, positions: set[int]) -> None:
    """Azzera ai_reason/transition_note delle tracce nelle posizioni indicate."""
    for st in setlist.tracks:
        if st.position in positions:
            st.ai_reason = None
            st.transition_note = None


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
    n = len(setlist.tracks)
    # i vicini della rimozione (nelle nuove posizioni) hanno il contesto cambiato
    _clear_ai_notes(setlist, {p for p in (position - 1, position) if 1 <= p <= n})
    _reassign_roles(setlist)
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
        # traccia mossa + vicini della vecchia e della nuova posizione (1-based)
        lo, hi = min(i, j) + 1, max(i, j) + 1
        _clear_ai_notes(setlist, {p for p in (lo - 1, lo, hi, hi + 1) if 1 <= p <= n})
        _reassign_roles(setlist)
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
    if setlist.owned_only and not new_track.has_local_file:
        raise SetEditError(
            "Il set e' nato \"solo brani posseduti\": la traccia sostitutiva "
            "non ha un file locale. Scarica il brano o scegline uno posseduto."
        )
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
