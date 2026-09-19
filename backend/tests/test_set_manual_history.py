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
