"""Riserva del set manuale (tappa 2): righe con block_id NULL, spostamenti
fra riserva e percorso. DB in memoria, nessuna rete."""
import pytest

from app.models import Track
from app.services.manual_set import (
    ManualSetError,
    create_manual_set,
    insert_rows,
    move_row,
    path_rows,
    remove_row,
    reserve_rows,
)


def _tracks(db, n=4):
    out = []
    for i in range(n):
        t = Track(source_type="spotify", title=f"T{i}", artist="A", duration_seconds=300,
                  bpm=124.0, has_local_file=True)
        db.add(t)
        out.append(t)
    db.commit()
    return out


def test_inserisci_in_riserva(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_ids=[])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id, t[1].id],
                    gap=False, after_row_id=None, reserve=True)
    assert path_rows(s) == []
    ris = reserve_rows(s)
    assert [r.track_id for r in ris] == [t[0].id, t[1].id]
    assert [r.position for r in ris] == [1, 2]
    assert all(r.block_id is None for r in ris)


def test_un_varco_in_riserva_non_ha_senso(db):
    s = create_manual_set(db, name="M", playlist_ids=[])
    with pytest.raises(ManualSetError):
        insert_rows(db, s.id, expected_revision=0, track_ids=[], gap=True,
                    after_row_id=None, reserve=True)


def test_la_stessa_traccia_puo_stare_in_riserva_e_nel_percorso(db):
    """Spec: il vincolo di unicita' vale dentro il percorso, non fra percorso e riserva."""
    t = _tracks(db, 1)
    s = create_manual_set(db, name="M", playlist_ids=[])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[0].id], gap=False,
                    after_row_id=None, reserve=True)
    assert [r.track_id for r in path_rows(s)] == [t[0].id]
    assert [r.track_id for r in reserve_rows(s)] == [t[0].id]


def test_porta_una_riga_dal_percorso_alla_riserva(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_ids=[])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t],
                    gap=False, after_row_id=None)
    seconda = path_rows(s)[1]
    s = move_row(db, s.id, seconda.id, expected_revision=1, position=1, to_reserve=True)
    assert [r.track_id for r in path_rows(s)] == [t[0].id, t[2].id]
    assert [r.position for r in path_rows(s)] == [1, 2]      # il percorso si rinumera
    assert [r.track_id for r in reserve_rows(s)] == [t[1].id]


def test_riporta_una_riga_dalla_riserva_al_percorso(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_ids=[])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[1].id], gap=False,
                    after_row_id=None, reserve=True)
    in_riserva = reserve_rows(s)[0]
    s = move_row(db, s.id, in_riserva.id, expected_revision=2, position=1, to_reserve=False)
    assert [r.track_id for r in path_rows(s)] == [t[1].id, t[0].id]
    assert reserve_rows(s) == []


def test_riportare_nel_percorso_una_traccia_gia_presente_e_un_conflitto(db):
    t = _tracks(db, 1)
    s = create_manual_set(db, name="M", playlist_ids=[])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[0].id], gap=False,
                    after_row_id=None, reserve=True)
    in_riserva = reserve_rows(s)[0]
    with pytest.raises(ManualSetError):
        move_row(db, s.id, in_riserva.id, expected_revision=2, position=1, to_reserve=False)


def test_togliere_una_riga_di_riserva_rinumera_la_riserva(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_ids=[])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t],
                    gap=False, after_row_id=None, reserve=True)
    s = remove_row(db, s.id, reserve_rows(s)[0].id, expected_revision=1)
    ris = reserve_rows(s)
    assert [r.track_id for r in ris] == [t[1].id, t[2].id]
    assert [r.position for r in ris] == [1, 2]
