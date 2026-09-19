"""Passaggi del set manuale (tappa 4): appunti per coppia e «la suono a»."""
import pytest
from sqlalchemy import select

from app.models import Setlist, SetlistPairNote, SetlistTrack, Track


def _due_tracce(db):
    a = Track(source_type="spotify", title="A", bpm=124.0, camelot_key="8A",
              duration_seconds=300, has_local_file=True)
    b = Track(source_type="spotify", title="B", bpm=126.0, camelot_key="9A",
              duration_seconds=300, has_local_file=True)
    db.add_all([a, b])
    db.commit()
    return a, b


def test_un_appunto_di_coppia_appartiene_al_suo_set(db):
    a, b = _due_tracce(db)
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=b.id,
                           note="entra sul break"))
    db.commit()
    db.refresh(s)
    assert [p.note for p in s.pair_notes] == ["entra sul break"]


def test_cancellare_il_set_cancella_i_suoi_appunti_di_coppia(db):
    a, b = _due_tracce(db)
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=b.id, note="x"))
    db.commit()
    db.delete(s)
    db.commit()
    assert db.scalars(select(SetlistPairNote)).all() == []


def test_la_riga_porta_il_tempo_a_cui_la_suono(db):
    a, _ = _due_tracce(db)
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    riga = SetlistTrack(setlist_id=s.id, position=1, track_id=a.id, play_bpm=126.5)
    db.add(riga)
    db.commit()
    db.refresh(riga)
    assert riga.play_bpm == 126.5
    # Il tempo della traccia non si tocca: `play_bpm` vale in questo set e basta.
    assert a.bpm == 124.0
