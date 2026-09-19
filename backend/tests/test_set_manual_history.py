"""Cronologia del set manuale (tappa 3): snapshot, ripristino, annulla e ripeti."""
import pytest
from sqlalchemy import select

from app.models import Setlist, SetlistBlock, SetlistRevision, SetlistTrack, Track


def test_una_revisione_appartiene_al_suo_set_e_porta_lo_snapshot(db):
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistRevision(setlist_id=s.id, seq=0, kind="create", snapshot={"blocks": [], "rows": []}))
    db.commit()
    db.refresh(s)
    assert s.undo_seq == 0
    assert [r.seq for r in s.revisions] == [0]
    assert s.revisions[0].snapshot == {"blocks": [], "rows": []}


def test_cancellare_il_set_cancella_la_sua_cronologia(db):
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistRevision(setlist_id=s.id, seq=0, kind="create", snapshot={}))
    db.commit()
    db.delete(s)
    db.commit()
    assert db.scalars(select(SetlistRevision)).all() == []


# --- Task 2: snapshot, ripristino, registrazione ---------------------------

from app.services.manual_history import MAX_REVISIONS, record, restore, snapshot_of  # noqa: E402


def _set_con_struttura(db):
    """Un set con due blocchi, tre righe (una varco) e una alternativa."""
    from app.models import SetlistAlternative
    t1 = Track(source_type="spotify", title="T1", has_local_file=True)
    t2 = Track(source_type="spotify", title="T2", has_local_file=True)
    db.add_all([t1, t2])
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    b1 = SetlistBlock(setlist_id=s.id, placement="main", position=1, name="Apertura")
    b2 = SetlistBlock(setlist_id=s.id, placement="bench", position=1)
    db.add_all([b1, b2])
    db.flush()
    r1 = SetlistTrack(setlist_id=s.id, block_id=b1.id, position=1, track_id=t1.id, note="ciao")
    r2 = SetlistTrack(setlist_id=s.id, block_id=b1.id, position=2, slot_kind="gap")
    r3 = SetlistTrack(setlist_id=s.id, block_id=b2.id, position=1, track_id=t2.id)
    db.add_all([r1, r2, r3])
    db.flush()
    db.add(SetlistAlternative(setlist_track_id=r1.id, track_id=t2.id, position=1))
    db.commit()
    db.refresh(s)
    return s, (t1, t2), (b1, b2), (r1, r2, r3)


def test_lo_snapshot_descrive_tutta_la_struttura(db):
    s, _, (b1, b2), (r1, r2, r3) = _set_con_struttura(db)
    snap = snapshot_of(s)
    assert [b["id"] for b in snap["blocks"]] == sorted([b1.id, b2.id])
    assert {b["placement"] for b in snap["blocks"]} == {"main", "bench"}
    assert [r["id"] for r in snap["rows"]] == sorted([r1.id, r2.id, r3.id])
    assert any(r["slot_kind"] == "gap" and r["track_id"] is None for r in snap["rows"])
    assert any(r["note"] == "ciao" for r in snap["rows"])
    assert len(snap["alts"]) == 1


def test_ripristinare_riporta_la_struttura_con_gli_stessi_id(db):
    s, (t1, t2), (b1, b2), (r1, r2, r3) = _set_con_struttura(db)
    prima = snapshot_of(s)
    ids_prima = {"blocks": sorted(b.id for b in s.blocks), "rows": sorted(r.id for r in s.tracks)}

    # Sfascia: togli una riga, rinomina un blocco.
    s.tracks.remove(next(r for r in s.tracks if r.id == r2.id))
    next(b for b in s.blocks if b.id == b1.id).name = "Altro"
    db.commit()
    db.refresh(s)
    assert sorted(r.id for r in s.tracks) != ids_prima["rows"]

    restore(db, s, prima)
    db.commit()
    db.refresh(s)
    assert sorted(r.id for r in s.tracks) == ids_prima["rows"]
    assert sorted(b.id for b in s.blocks) == ids_prima["blocks"]
    assert next(b for b in s.blocks if b.id == b1.id).name == "Apertura"
    assert next(r for r in s.tracks if r.id == r1.id).note == "ciao"
    assert len(next(r for r in s.tracks if r.id == r1.id).alternatives) == 1


def test_lo_snapshot_di_uno_stato_ripristinato_e_identico(db):
    """Se ripristinare non fosse fedele, i due snapshot divergerebbero."""
    s, *_ = _set_con_struttura(db)
    prima = snapshot_of(s)
    restore(db, s, prima)
    db.commit()
    db.refresh(s)
    assert snapshot_of(s) == prima


def test_record_scarta_il_ramo_ripeti(db):
    s, *_ = _set_con_struttura(db)
    for i in range(3):
        record(db, s, kind=f"g{i}")
        db.commit()
    assert [r.seq for r in s.revisions] == [0, 1, 2]

    s.undo_seq = 0  # come dopo due annulla
    db.commit()
    record(db, s, kind="nuovo")
    db.commit()
    db.refresh(s)
    assert [r.seq for r in s.revisions] == [0, 1]
    assert s.revisions[-1].kind == "nuovo"


def test_record_accorpa_due_gesti_dello_stesso_tipo(db):
    s, *_ = _set_con_struttura(db)
    record(db, s, kind="note:7")
    db.commit()
    quante = len(s.revisions)
    record(db, s, kind="note:7")
    db.commit()
    db.refresh(s)
    assert len(s.revisions) == quante  # sovrascritta, non aggiunta
    record(db, s, kind="note:8")
    db.commit()
    db.refresh(s)
    assert len(s.revisions) == quante + 1  # riga diversa: revisione nuova


def test_record_pota_oltre_il_limite(db):
    s, *_ = _set_con_struttura(db)
    for i in range(MAX_REVISIONS + 10):
        record(db, s, kind=f"g{i}")
        db.commit()
    db.refresh(s)
    assert len(s.revisions) == MAX_REVISIONS
    # Le piu' vecchie sono quelle cadute.
    assert s.revisions[0].seq == s.revisions[-1].seq - (MAX_REVISIONS - 1)
