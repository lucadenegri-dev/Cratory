"""Cronologia del set manuale: snapshot della struttura, ripristino, potatura.

Lo snapshot e' la struttura intera con gli id: ripristinarlo significa ricreare
esattamente quelle righe, cosi' gli id che il client ha in mano restano validi.
Cancella-e-ricrea invece di un confronto incrementale: un set manuale ha decine
di righe, non migliaia, e questa forma e' molto piu' facile da verificare.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    Setlist, SetlistAlternative, SetlistBlock, SetlistPairNote, SetlistRevision, SetlistTrack,
)

MAX_REVISIONS = 50
# Solo gli appunti si accorpano. Una nota si scrive un carattere alla volta e il
# client manda una PATCH per volta: senza accorpamento, annullare tornerebbe
# indietro di una lettera. Ogni altro gesto e' un clic solo, e due clic di fila
# devono restare due revisioni — altrimenti un annulla ne cancellerebbe due.
MERGEABLE = ("note:",)


def _accorpabile(kind: str) -> bool:
    return kind.startswith(MERGEABLE)


def snapshot_of(setlist: Setlist) -> dict:
    """Struttura corrente, ordinata per id: due stati uguali danno snapshot uguali."""
    return {
        "blocks": [
            {"id": b.id, "name": b.name, "placement": b.placement, "position": b.position}
            for b in sorted(setlist.blocks, key=lambda b: b.id)
        ],
        "rows": [
            {"id": r.id, "block_id": r.block_id, "position": r.position,
             "slot_kind": r.slot_kind, "track_id": r.track_id, "note": r.note}
            for r in sorted(setlist.tracks, key=lambda r: r.id)
        ],
        "alts": [
            {"id": a.id, "setlist_track_id": a.setlist_track_id, "track_id": a.track_id,
             "position": a.position, "note": a.note}
            for r in sorted(setlist.tracks, key=lambda r: r.id)
            for a in sorted(r.alternatives, key=lambda a: a.id)
        ],
        # Gli appunti di coppia stanno nella struttura come le note di riga: un
        # annulla che li lasciasse fuori riporterebbe indietro mezzo set.
        "pairs": [
            {"id": p.id, "from_track_id": p.from_track_id,
             "to_track_id": p.to_track_id, "note": p.note}
            for p in sorted(setlist.pair_notes, key=lambda p: p.id)
        ],
    }


def restore(db: Session, setlist: Setlist, snapshot: dict) -> None:
    """Riporta la struttura allo snapshot. Non committa, non tocca `revision`."""
    # Figlie prima delle madri: le alternative puntano alle righe, le righe ai
    # blocchi. Il flush dopo la cancellazione rende esplicito l'ordine
    # cancella-poi-ricrea: senza, l'unit of work vede la vecchia riga cancellata
    # e la nuova con lo stesso id e le fonde in una UPDATE, che qui funziona per
    # caso e smette di funzionare appena lo snapshot ha una forma diversa.
    for row in list(setlist.tracks):
        row.alternatives.clear()
    setlist.tracks.clear()
    setlist.blocks.clear()
    setlist.pair_notes.clear()
    db.flush()

    for b in snapshot.get("blocks", []):
        db.add(SetlistBlock(id=b["id"], setlist_id=setlist.id, name=b["name"],
                            placement=b["placement"], position=b["position"]))
    db.flush()
    for r in snapshot.get("rows", []):
        db.add(SetlistTrack(id=r["id"], setlist_id=setlist.id, block_id=r["block_id"],
                            position=r["position"], slot_kind=r["slot_kind"],
                            track_id=r["track_id"], note=r["note"]))
    db.flush()
    for a in snapshot.get("alts", []):
        db.add(SetlistAlternative(id=a["id"], setlist_track_id=a["setlist_track_id"],
                                  track_id=a["track_id"], position=a["position"], note=a["note"]))
    for p in snapshot.get("pairs", []):
        db.add(SetlistPairNote(id=p["id"], setlist_id=setlist.id,
                               from_track_id=p["from_track_id"],
                               to_track_id=p["to_track_id"], note=p["note"]))
    db.flush()
    db.refresh(setlist)


def record(db: Session, setlist: Setlist, kind: str) -> None:
    """Salva lo stato corrente come revisione dopo il cursore. Non committa."""
    # Prima di fotografare: le righe appena aggiunte dal chiamante sono ancora
    # pendenti e il loro id e' None, e uno snapshot senza id non si ripristina.
    db.flush()
    revisioni = sorted(setlist.revisions, key=lambda r: r.seq)
    # Il ramo «ripeti» muore appena si fa qualcosa di nuovo dopo un annulla.
    for vecchia in [r for r in revisioni if r.seq > setlist.undo_seq]:
        setlist.revisions.remove(vecchia)
    revisioni = sorted(setlist.revisions, key=lambda r: r.seq)

    ultima = revisioni[-1] if revisioni else None
    if (ultima is not None and ultima.kind == kind and ultima.seq == setlist.undo_seq
            and _accorpabile(kind)):
        # Stessa nota di fila: una revisione sola.
        ultima.snapshot = snapshot_of(setlist)
        db.flush()
        return

    seq = (ultima.seq + 1) if ultima is not None else 0
    nuova = SetlistRevision(setlist_id=setlist.id, seq=seq, kind=kind,
                            snapshot=snapshot_of(setlist))
    setlist.revisions.append(nuova)
    setlist.undo_seq = seq

    troppe = len(setlist.revisions) - MAX_REVISIONS
    if troppe > 0:
        for vecchia in sorted(setlist.revisions, key=lambda r: r.seq)[:troppe]:
            setlist.revisions.remove(vecchia)
    db.flush()
