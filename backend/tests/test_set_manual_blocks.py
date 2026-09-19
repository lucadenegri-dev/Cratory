"""Sequenze e banco del set manuale (tappa 3)."""
import pytest

from app.models import Track
from app.services.manual_set import (
    BlockNotFound, ManualSetError, blocks_of, create_manual_set, group_rows, insert_rows,
    load_manual_set, move_block, path_rows, rename_block, split_block,
)


def _set_con_quattro(db):
    tracce = []
    for i in range(4):
        t = Track(source_type="spotify", title=f"T{i}", bpm=124.0, duration_seconds=300,
                  has_local_file=True)
        db.add(t)
        tracce.append(t)
    db.commit()
    s = create_manual_set(db, name="M", playlist_ids=[])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t.id for t in tracce],
                    gap=False, after_row_id=None)
    return s, tracce


def test_raggruppa_due_righe_contigue(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[1].id, righe[2].id],
                   name="Salita")
    main = blocks_of(s, "main")
    assert len(main) == 3                       # prima · nuova · dopo
    assert main[1].name == "Salita"
    assert [r.track_id for r in main[1].rows] == [t[1].id, t[2].id]
    # L'ordine del percorso non cambia: raggruppare non sposta nulla.
    assert [r.track_id for r in path_rows(s)] == [x.id for x in t]


def test_un_raggruppamento_rifiutato_non_lascia_niente_a_meta(db):
    """Verifica dichiarata dalla spec: «un comando fallito non lascia meta'
    spostamento». Il rifiuto arriva prima di toccare qualunque cosa."""
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    blocchi_prima = [(b.id, b.name, b.position) for b in blocks_of(s, "main")]
    with pytest.raises(ManualSetError):
        group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[2].id], name=None)
    db.rollback()
    db.expire_all()
    s = load_manual_set(db, s.id)
    assert [(b.id, b.name, b.position) for b in blocks_of(s, "main")] == blocchi_prima
    assert [r.track_id for r in path_rows(s)] == [x.id for x in t]
    assert s.revision == 1  # nessuna revisione bruciata da un comando rifiutato


def test_non_si_raggruppa_una_riga_sola(db):
    s, t = _set_con_quattro(db)
    with pytest.raises(ManualSetError):
        group_rows(db, s.id, expected_revision=1, row_ids=[path_rows(s)[0].id], name=None)


def test_rinomina_una_sequenza(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[1].id], name="A")
    blocco = blocks_of(s, "main")[0]
    s = rename_block(db, s.id, blocco.id, expected_revision=2, name="  Apertura  ")
    assert blocks_of(s, "main")[0].name == "Apertura"
    s = rename_block(db, s.id, blocco.id, expected_revision=3, name="")
    assert blocks_of(s, "main")[0].name is None  # vuoto = senza nome


def test_sposta_una_sequenza_intera_conservando_l_ordine_interno(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[2].id, righe[3].id], name="Coda")
    coda = next(b for b in blocks_of(s, "main") if b.name == "Coda")
    s = move_block(db, s.id, coda.id, expected_revision=2, position=1)
    assert [r.track_id for r in path_rows(s)] == [t[2].id, t[3].id, t[0].id, t[1].id]


def test_parcheggia_una_sequenza_sul_banco_e_la_riprende(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[1].id], name="Idea")
    idea = next(b for b in blocks_of(s, "main") if b.name == "Idea")

    s = move_block(db, s.id, idea.id, expected_revision=2, position=1, to_bench=True)
    assert [b.name for b in blocks_of(s, "bench")] == ["Idea"]
    assert [r.track_id for r in path_rows(s)] == [t[2].id, t[3].id]  # fuori dal percorso

    s = move_block(db, s.id, idea.id, expected_revision=3, position=1, to_bench=False)
    assert blocks_of(s, "bench") == []
    assert [r.track_id for r in path_rows(s)] == [t[0].id, t[1].id, t[2].id, t[3].id]


def test_separare_una_sequenza_lascia_le_righe_in_ordine(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[1].id, righe[2].id], name="X")
    blocco = next(b for b in blocks_of(s, "main") if b.name == "X")
    s = split_block(db, s.id, blocco.id, expected_revision=2)
    assert all(b.name != "X" for b in blocks_of(s, "main"))
    assert [r.track_id for r in path_rows(s)] == [x.id for x in t]


def test_una_sequenza_di_un_altro_set_non_si_tocca(db):
    s, t = _set_con_quattro(db)
    altro = create_manual_set(db, name="Altro", playlist_ids=[])
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[1].id], name="A")
    blocco = blocks_of(s, "main")[0]
    with pytest.raises(BlockNotFound):
        rename_block(db, altro.id, blocco.id, expected_revision=0, name="Rubato")


# --- Inserire quando le sequenze sono piu' d'una -------------------------------


def test_una_traccia_nuova_finisce_in_fondo_al_percorso_non_in_fondo_alla_prima(db):
    """Con una sequenza sola «in coda» e «in coda al primo blocco» coincidono.
    Con piu' sequenze no: appendere nel primo blocco infilerebbe la traccia in
    mezzo al percorso."""
    s, t = _set_con_quattro(db)
    quinta = Track(source_type="spotify", title="T4", bpm=124.0, duration_seconds=300,
                   has_local_file=True)
    db.add(quinta)
    db.commit()
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[1].id], name="A")

    s = insert_rows(db, s.id, expected_revision=2, track_ids=[quinta.id], gap=False,
                    after_row_id=None)
    assert [r.track_id for r in path_rows(s)] == [t[0].id, t[1].id, t[2].id, t[3].id, quinta.id]


def test_si_inserisce_dopo_una_riga_di_qualunque_sequenza(db):
    s, t = _set_con_quattro(db)
    quinta = Track(source_type="spotify", title="T4", bpm=124.0, duration_seconds=300,
                   has_local_file=True)
    db.add(quinta)
    db.commit()
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[2].id, righe[3].id], name="Coda")

    s = insert_rows(db, s.id, expected_revision=2, track_ids=[quinta.id], gap=False,
                    after_row_id=righe[2].id)
    assert [r.track_id for r in path_rows(s)] == [t[0].id, t[1].id, t[2].id, quinta.id, t[3].id]
    # E' finita dentro la sequenza dell'ancora, non in un blocco tutto suo.
    coda = next(b for b in blocks_of(s, "main") if b.name == "Coda")
    assert [r.track_id for r in coda.rows] == [t[2].id, quinta.id, t[3].id]


def test_la_stessa_traccia_non_rientra_da_un_altra_sequenza(db):
    """Il vincolo «una traccia una volta sola» vale sul percorso intero: se
    guardasse un blocco per volta, raggruppare aprirebbe la porta ai doppioni."""
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[1].id], name="A")
    with pytest.raises(ManualSetError):
        insert_rows(db, s.id, expected_revision=2, track_ids=[t[2].id], gap=False,
                    after_row_id=None)
