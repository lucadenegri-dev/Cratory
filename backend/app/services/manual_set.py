"""Set manuale (banco di preparazione): le mutazioni del percorso e della riserva.

Deterministico, senza AI. Ogni funzione che muta controlla `expected_revision`,
applica la modifica, incrementa `Setlist.revision` e committa nella stessa
transazione. Le righe si identificano per id, mai per posizione. I set manual
non passano mai da assign_roles / recompute_transitions (spec 2026-09-15).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistAlternative, SetlistBlock, SetlistTrack
from app.repositories import get_playlist, get_setlist, get_track
from app.services.manual_history import record, restore


class ManualSetError(Exception):
    """Errore di dominio (422 dal router, salvo le sottoclassi)."""


class ManualSetNotFound(ManualSetError):
    pass


class ManualSetNotManual(ManualSetError):
    pass


class RowNotFound(ManualSetError):
    pass


class AlternativeNotFound(ManualSetError):
    pass


class NothingToUndo(ManualSetError):
    pass


class NothingToRedo(ManualSetError):
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
    db.flush()
    record(db, setlist, "create")  # la revisione 0 e' il set vuoto: la prima mutazione e' annullabile
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
    """L'ULTIMA sequenza del percorso, quella in cui finisce cio' che si appende;
    creata al primo inserimento se il set non ne ha ancora. Dalla tappa 3 le
    sequenze possono essere piu' d'una, e «in coda» vuol dire in coda all'ultima,
    non in coda alla prima."""
    esistenti = [b for b in setlist.blocks if b.placement == "main"]
    if esistenti:
        return max(esistenti, key=lambda b: b.position)
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


def reserve_rows(setlist: Setlist) -> list[SetlistTrack]:
    """Le tracce messe da parte per la serata: righe senza blocco, in ordine."""
    return sorted((r for r in setlist.tracks if r.block_id is None),
                  key=lambda r: r.position)


def _renumber(rows: list[SetlistTrack]) -> None:
    for i, row in enumerate(rows, start=1):
        row.position = i


def _row_of(setlist: Setlist, row_id: int) -> SetlistTrack:
    for row in setlist.tracks:
        if row.id == row_id:
            return row
    raise RowNotFound("Row not found")


def _commit_bumped(db: Session, setlist: Setlist, kind: str) -> Setlist:
    """Incrementa la revisione, salva lo snapshot e committa, in una transazione.

    `kind` etichetta il gesto: due gesti uguali di fila si accorpano in una
    revisione sola (vedi manual_history.record)."""
    setlist.revision += 1
    record(db, setlist, kind)
    db.commit()
    return get_setlist(db, setlist.id)


def insert_rows(db: Session, setlist_id: int, *, expected_revision: int,
                track_ids: list[int], gap: bool, after_row_id: int | None,
                reserve: bool = False) -> Setlist:
    """Inserisce tracce (nell'ordine dato) oppure un varco, dopo `after_row_id`
    (None = in coda). `reserve=True` le mette in coda alla riserva invece che
    nel percorso; il vincolo «una traccia una volta sola» vale dentro il
    percorso, non fra percorso e riserva."""
    if gap == bool(track_ids):
        raise ManualSetError("Give either track_ids or gap")
    if gap and reserve:
        raise ManualSetError("A gap belongs to the path, not to the reserve")
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    if reserve:
        rows = reserve_rows(setlist)
        at = len(rows)
        block_id = None
        present: set[int] = set()  # in riserva una traccia puo' ripetersi dal percorso
    else:
        percorso = path_rows(setlist)
        if after_row_id is not None:
            # Si entra nella sequenza dell'ancora, non in una fissa: il DJ ha
            # indicato un punto preciso del percorso.
            anchor = _row_of(setlist, after_row_id)
            if anchor not in percorso:
                raise ManualSetError(f"Row {after_row_id} is not in the path")
            block_id = anchor.block_id
            rows = [r for r in percorso if r.block_id == block_id]
            at = rows.index(anchor) + 1
        else:
            block = main_block(db, setlist)
            block_id = block.id
            rows = [r for r in percorso if r.block_id == block.id]
            at = len(rows)
        # Il vincolo «una traccia una volta sola» vale sul percorso intero, non
        # sulla sequenza in cui si sta inserendo.
        present = {r.track_id for r in percorso if r.track_id is not None}
    new_rows: list[SetlistTrack] = []
    if gap:
        new_rows.append(SetlistTrack(setlist_id=setlist.id, block_id=block_id, position=0, slot_kind="gap"))
    else:
        for tid in track_ids:
            if get_track(db, tid) is None:
                raise ManualSetError(f"Track {tid} not found")
            if tid in present:
                raise ManualSetError(f"Track {tid} is already in the path")
            present.add(tid)
            new_rows.append(SetlistTrack(setlist_id=setlist.id, block_id=block_id, position=0,
                                         slot_kind="track", track_id=tid))
    rows[at:at] = new_rows
    for row in new_rows:
        db.add(row)
        setlist.tracks.append(row)
    _renumber(rows)
    return _commit_bumped(db, setlist, "rows")


def move_row(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
             position: int, to_reserve: bool | None = None) -> Setlist:
    """Sposta la riga alla posizione 1-based. `to_reserve` la cambia di
    destinazione: True la porta in riserva, False la riporta nel percorso,
    None la lascia dov'e'."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    era_in_riserva = row.block_id is None
    va_in_riserva = era_in_riserva if to_reserve is None else to_reserve
    if va_in_riserva and row.slot_kind == "gap":
        raise ManualSetError("A gap belongs to the path, not to the reserve")

    if va_in_riserva == era_in_riserva:
        destinazione = [r for r in (reserve_rows(setlist) if era_in_riserva
                                    else path_rows(setlist))
                        if r.block_id == row.block_id]
    else:
        origine = [r for r in (reserve_rows(setlist) if era_in_riserva
                               else path_rows(setlist))
                   if r.block_id == row.block_id and r.id != row.id]
        if va_in_riserva:
            destinazione = reserve_rows(setlist)
            row.block_id = None
        else:
            block = main_block(db, setlist)
            presenti = {r.track_id for r in path_rows(setlist)
                        if r.block_id == block.id and r.track_id is not None}
            if row.track_id in presenti:
                raise ManualSetError(f"Track {row.track_id} is already in the path")
            destinazione = [r for r in path_rows(setlist) if r.block_id == block.id]
            row.block_id = block.id
        _renumber(origine)
        destinazione = [r for r in destinazione if r.id != row.id]

    massimo = len(destinazione) if row in destinazione else len(destinazione) + 1
    if not 1 <= position <= massimo:
        raise ManualSetError(f"Position {position} out of range 1..{massimo}")
    if row in destinazione:
        destinazione.remove(row)
    destinazione.insert(position - 1, row)
    _renumber(destinazione)
    return _commit_bumped(db, setlist, "move")


def remove_row(db: Session, setlist_id: int, row_id: int, *, expected_revision: int) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    vicine = reserve_rows(setlist) if row.block_id is None else path_rows(setlist)
    rows = [r for r in vicine if r.block_id == row.block_id and r.id != row.id]
    setlist.tracks.remove(row)  # delete-orphan sulla relazione: la riga sparisce
    _renumber(rows)
    return _commit_bumped(db, setlist, "remove")


def update_row_note(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
                    note: str | None) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    row.note = (note or "").strip() or None
    return _commit_bumped(db, setlist, f"note:{row.id}")


# --- Alternative (tappa 2) -----------------------------------------------------


def _alt_of(row: SetlistTrack, alt_id: int) -> SetlistAlternative:
    for alt in row.alternatives:
        if alt.id == alt_id:
            return alt
    raise AlternativeNotFound("Alternative not found")


def _renumber_alts(alts: list[SetlistAlternative]) -> None:
    for i, alt in enumerate(alts, start=1):
        alt.position = i


def add_alternatives(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
                     track_ids: list[int]) -> Setlist:
    """Candidate in coda alla riga. La traccia attiva non puo' essere candidata
    di se' stessa, e la stessa candidata non si ripete sulla stessa riga."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    presenti = {a.track_id for a in row.alternatives}
    alts = list(row.alternatives)
    for tid in track_ids:
        if get_track(db, tid) is None:
            raise ManualSetError(f"Track {tid} not found")
        if tid == row.track_id:
            raise ManualSetError(f"Track {tid} is already the active one on this row")
        if tid in presenti:
            raise ManualSetError(f"Track {tid} is already an alternative on this row")
        presenti.add(tid)
        alt = SetlistAlternative(setlist_track_id=row.id, track_id=tid, position=0)
        db.add(alt)
        row.alternatives.append(alt)
        alts.append(alt)
    _renumber_alts(alts)
    return _commit_bumped(db, setlist, "alts")


def remove_alternative(db: Session, setlist_id: int, row_id: int, alt_id: int, *,
                       expected_revision: int) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    alt = _alt_of(row, alt_id)
    row.alternatives.remove(alt)  # delete-orphan: la candidata sparisce
    _renumber_alts(list(row.alternatives))
    return _commit_bumped(db, setlist, "alts")


def choose_alternative(db: Session, setlist_id: int, row_id: int, alt_id: int, *,
                       expected_revision: int) -> Setlist:
    """La candidata prende il posto dell'attiva, e l'attiva prende il suo posto
    fra le candidate. Su un varco non c'e' nulla da conservare: lo slot diventa
    `track` mantenendo id e appunto (spec, sezione 3)."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    alt = _alt_of(row, alt_id)
    uscente = row.track_id
    # La relationship va assegnata insieme alla foreign key: `row.track` e'
    # gia' caricata, e al flush SQLAlchemy la fa vincere sul solo `track_id`
    # riscrivendolo com'era. Stesso accorgimento di set_editor.add_track.
    row.track_id = alt.track_id
    row.track = alt.track
    row.slot_kind = "track"
    row.alternatives.remove(alt)
    if uscente is not None:
        row.alternatives.append(
            SetlistAlternative(setlist_track_id=row.id, track_id=uscente, position=0)
        )
    _renumber_alts(list(row.alternatives))
    return _commit_bumped(db, setlist, "choose")


# --- Cronologia: annulla e ripeti (tappa 3) ------------------------------------


def can_undo(setlist: Setlist) -> bool:
    return any(r.seq < setlist.undo_seq for r in setlist.revisions)


def can_redo(setlist: Setlist) -> bool:
    return any(r.seq > setlist.undo_seq for r in setlist.revisions)


def _muovi_cursore(db: Session, setlist_id: int, expected_revision: int, avanti: bool) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    candidate = [r for r in setlist.revisions
                 if (r.seq > setlist.undo_seq if avanti else r.seq < setlist.undo_seq)]
    if not candidate:
        raise NothingToRedo("Nothing to redo") if avanti else NothingToUndo("Nothing to undo")
    bersaglio = min(candidate, key=lambda r: r.seq) if avanti else max(candidate, key=lambda r: r.seq)
    restore(db, setlist, bersaglio.snapshot)
    setlist.undo_seq = bersaglio.seq
    # La revisione cresce anche qui: annullare E' una modifica, e un client
    # fermo alla precedente deve vedersi rifiutare la sua mutazione.
    setlist.revision += 1
    db.commit()
    return get_setlist(db, setlist.id)


def undo(db: Session, setlist_id: int, *, expected_revision: int) -> Setlist:
    return _muovi_cursore(db, setlist_id, expected_revision, avanti=False)


def redo(db: Session, setlist_id: int, *, expected_revision: int) -> Setlist:
    return _muovi_cursore(db, setlist_id, expected_revision, avanti=True)


# --- Sequenze e banco (tappa 3) ------------------------------------------------


class BlockNotFound(ManualSetError):
    pass


def blocks_of(setlist: Setlist, placement: str) -> list[SetlistBlock]:
    return sorted((b for b in setlist.blocks if b.placement == placement),
                  key=lambda b: b.position)


def _block_of(setlist: Setlist, block_id: int) -> SetlistBlock:
    for block in setlist.blocks:
        if block.id == block_id:
            return block
    raise BlockNotFound("Block not found")


def _renumber_blocks(blocks: list[SetlistBlock]) -> None:
    for i, block in enumerate(blocks, start=1):
        block.position = i


def group_rows(db: Session, setlist_id: int, *, expected_revision: int,
               row_ids: list[int], name: str | None) -> Setlist:
    """Raggruppa righe contigue dello stesso blocco in una sequenza nuova, al
    loro posto: l'ordine del percorso non cambia, cambia come e' diviso."""
    if len(row_ids) < 2:
        raise ManualSetError("A sequence needs at least two rows")
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    righe = [_row_of(setlist, rid) for rid in row_ids]
    blocchi = {r.block_id for r in righe}
    if len(blocchi) != 1 or None in blocchi:
        raise ManualSetError("Rows must belong to one and the same block")
    origine = _block_of(setlist, righe[0].block_id)
    tutte = sorted((r for r in setlist.tracks if r.block_id == origine.id),
                   key=lambda r: r.position)
    indici = sorted(tutte.index(r) for r in righe)
    if indici != list(range(indici[0], indici[0] + len(indici))):
        raise ManualSetError("Rows must be contiguous")

    prima = tutte[:indici[0]]
    gruppo = [tutte[i] for i in indici]
    dopo = tutte[indici[-1] + 1:]

    fratelli = blocks_of(setlist, origine.placement)
    at = fratelli.index(origine)

    def nuovo_blocco(sue_righe: list[SetlistTrack], nome: str | None) -> SetlistBlock:
        blocco = SetlistBlock(setlist_id=setlist.id, placement=origine.placement,
                              name=nome, position=0)
        db.add(blocco)
        setlist.blocks.append(blocco)
        db.flush()
        for r in sue_righe:
            # La relationship, non solo la foreign key: `blocco_di_origine.rows`
            # e' caricata, e se le righe restassero sue il suo scioglimento le
            # sgancerebbe (block_id a NULL) buttandole nella riserva.
            r.block = blocco
        _renumber(sue_righe)
        return blocco

    # Il blocco di origine si spezza in tre: cio' che precede (resta suo), il
    # gruppo (blocco nuovo, col nome), cio' che segue (blocco nuovo senza nome).
    # Ricostruito come lista, non a colpi di slice annidati: qui un indice
    # sbagliato riordinerebbe il percorso in silenzio.
    sostituzione: list[SetlistBlock] = []
    if prima:
        _renumber(prima)
        sostituzione.append(origine)
    sostituzione.append(nuovo_blocco(gruppo, (name or "").strip() or None))
    if dopo:
        sostituzione.append(nuovo_blocco(dopo, None))
    if not prima:
        # Il blocco di origine e' rimasto vuoto: sciolto, non lasciato in giro.
        setlist.blocks.remove(origine)

    _renumber_blocks(fratelli[:at] + sostituzione + fratelli[at + 1:])
    return _commit_bumped(db, setlist, "block")


def rename_block(db: Session, setlist_id: int, block_id: int, *, expected_revision: int,
                 name: str | None) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    block = _block_of(setlist, block_id)
    block.name = (name or "").strip() or None
    return _commit_bumped(db, setlist, "block")


def move_block(db: Session, setlist_id: int, block_id: int, *, expected_revision: int,
               position: int, to_bench: bool | None = None) -> Setlist:
    """Sposta la sequenza intera: l'ordine interno non si tocca mai."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    block = _block_of(setlist, block_id)
    destinazione = block.placement if to_bench is None else ("bench" if to_bench else "main")
    # Tutto cio' che si legge si legge prima di toccare qualunque cosa: una
    # posizione fuori range deve lasciare il set com'era, banco compreso.
    if destinazione == block.placement:
        rimasti: list[SetlistBlock] = []
        fratelli = [b for b in blocks_of(setlist, block.placement) if b.id != block.id]
    else:
        rimasti = [b for b in blocks_of(setlist, block.placement) if b.id != block.id]
        fratelli = blocks_of(setlist, destinazione)
    if not 1 <= position <= len(fratelli) + 1:
        raise ManualSetError(f"Position {position} out of range 1..{len(fratelli) + 1}")

    block.placement = destinazione
    fratelli.insert(position - 1, block)
    _renumber_blocks(rimasti)
    _renumber_blocks(fratelli)
    return _commit_bumped(db, setlist, "block")


def split_block(db: Session, setlist_id: int, block_id: int, *, expected_revision: int) -> Setlist:
    """Scioglie la sequenza: le righe passano al blocco che la precede, in coda,
    nell'ordine che avevano. Se era la prima, vanno in testa a quella dopo."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    block = _block_of(setlist, block_id)
    fratelli = blocks_of(setlist, block.placement)
    if len(fratelli) == 1:
        raise ManualSetError("The only sequence cannot be split")
    at = fratelli.index(block)
    ospite = fratelli[at - 1] if at > 0 else fratelli[1]
    mie = sorted((r for r in setlist.tracks if r.block_id == block.id), key=lambda r: r.position)
    sue = sorted((r for r in setlist.tracks if r.block_id == ospite.id), key=lambda r: r.position)
    unite = (sue + mie) if at > 0 else (mie + sue)
    for r in mie:
        r.block = ospite  # la relationship, non solo la foreign key: vedi group_rows
    _renumber(unite)
    setlist.blocks.remove(block)
    _renumber_blocks([b for b in fratelli if b.id != block.id])
    return _commit_bumped(db, setlist, "block")
