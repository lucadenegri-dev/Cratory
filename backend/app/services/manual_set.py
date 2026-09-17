"""Set manuale (banco di preparazione, tappa 1): le mutazioni del percorso.

Deterministico, senza AI. Ogni funzione che muta controlla `expected_revision`,
applica la modifica, incrementa `Setlist.revision` e committa nella stessa
transazione. Le righe si identificano per id, mai per posizione. I set manual
non passano mai da assign_roles / recompute_transitions (spec 2026-09-15).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistBlock, SetlistTrack
from app.repositories import get_playlist, get_setlist, get_track


class ManualSetError(Exception):
    """Errore di dominio (422 dal router, salvo le sottoclassi)."""


class ManualSetNotFound(ManualSetError):
    pass


class ManualSetNotManual(ManualSetError):
    pass


class RowNotFound(ManualSetError):
    pass


class RevisionConflict(ManualSetError):
    def __init__(self, current: int):
        super().__init__(f"Revision mismatch: current is {current}")
        self.current = current


def create_manual_set(db: Session, *, name: str | None, playlist_id: int | None) -> Setlist:
    playlist = None
    if playlist_id is not None:
        playlist = get_playlist(db, playlist_id)
        if playlist is None:
            raise ManualSetError("Playlist not found")
    clean = (name or "").strip() or (playlist.name if playlist is not None else "Set")
    setlist = Setlist(name=clean, kind="manual", source_playlist_id=playlist_id, generated_by="manual")
    db.add(setlist)
    db.commit()
    return get_setlist(db, setlist.id)


def load_manual_set(db: Session, setlist_id: int) -> Setlist:
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise ManualSetNotFound("Set not found")
    if setlist.kind != "manual":
        raise ManualSetNotManual("Set is not a manual set")
    return setlist


def _check_revision(setlist: Setlist, expected: int) -> None:
    if setlist.revision != expected:
        raise RevisionConflict(setlist.revision)


def main_block(db: Session, setlist: Setlist) -> SetlistBlock:
    """Il blocco `main` del set (tappa 1: uno solo), creato al primo inserimento."""
    for block in setlist.blocks:
        if block.placement == "main":
            return block
    block = SetlistBlock(setlist_id=setlist.id, placement="main", position=1)
    db.add(block)
    db.flush()
    setlist.blocks.append(block)
    return block


def path_rows(setlist: Setlist) -> list[SetlistTrack]:
    """Righe del percorso in ordine: blocchi main per posizione, righe per posizione."""
    rows: list[SetlistTrack] = []
    for block in sorted(setlist.blocks, key=lambda b: b.position):
        if block.placement != "main":
            continue
        rows.extend(sorted((r for r in setlist.tracks if r.block_id == block.id),
                           key=lambda r: r.position))
    return rows


def _renumber(rows: list[SetlistTrack]) -> None:
    for i, row in enumerate(rows, start=1):
        row.position = i


def _row_of(setlist: Setlist, row_id: int) -> SetlistTrack:
    for row in setlist.tracks:
        if row.id == row_id:
            return row
    raise RowNotFound("Row not found")


def _commit_bumped(db: Session, setlist: Setlist) -> Setlist:
    setlist.revision += 1
    db.commit()
    return get_setlist(db, setlist.id)


def insert_rows(db: Session, setlist_id: int, *, expected_revision: int,
                track_ids: list[int], gap: bool, after_row_id: int | None) -> Setlist:
    """Inserisce tracce (nell'ordine dato) oppure un varco, dopo `after_row_id`
    (None = in coda). Una traccia compare al piu' una volta nel percorso."""
    if gap == bool(track_ids):
        raise ManualSetError("Give either track_ids or gap")
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    block = main_block(db, setlist)
    rows = [r for r in path_rows(setlist) if r.block_id == block.id]
    at = len(rows)
    if after_row_id is not None:
        anchor = _row_of(setlist, after_row_id)
        if anchor not in rows:
            raise ManualSetError(f"Row {after_row_id} is not in the main block")
        at = rows.index(anchor) + 1
    present = {r.track_id for r in rows if r.track_id is not None}
    new_rows: list[SetlistTrack] = []
    if gap:
        new_rows.append(SetlistTrack(setlist_id=setlist.id, block_id=block.id, position=0, slot_kind="gap"))
    else:
        for tid in track_ids:
            if get_track(db, tid) is None:
                raise ManualSetError(f"Track {tid} not found")
            if tid in present:
                raise ManualSetError(f"Track {tid} is already in the path")
            present.add(tid)
            new_rows.append(SetlistTrack(setlist_id=setlist.id, block_id=block.id, position=0,
                                         slot_kind="track", track_id=tid))
    rows[at:at] = new_rows
    for row in new_rows:
        db.add(row)
        setlist.tracks.append(row)
    _renumber(rows)
    return _commit_bumped(db, setlist)


def move_row(db: Session, setlist_id: int, row_id: int, *, expected_revision: int, position: int) -> Setlist:
    """Sposta la riga alla posizione 1-based dentro il blocco main."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    rows = [r for r in path_rows(setlist) if r.block_id == row.block_id]
    if not 1 <= position <= len(rows):
        raise ManualSetError(f"Position {position} out of range 1..{len(rows)}")
    rows.remove(row)
    rows.insert(position - 1, row)
    _renumber(rows)
    return _commit_bumped(db, setlist)


def remove_row(db: Session, setlist_id: int, row_id: int, *, expected_revision: int) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    rows = [r for r in path_rows(setlist) if r.block_id == row.block_id and r.id != row.id]
    setlist.tracks.remove(row)  # delete-orphan sulla relazione: la riga sparisce
    _renumber(rows)
    return _commit_bumped(db, setlist)


def update_row_note(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
                    note: str | None) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    row.note = (note or "").strip() or None
    return _commit_bumped(db, setlist)
