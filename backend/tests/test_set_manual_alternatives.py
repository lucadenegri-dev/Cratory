"""Alternative del set manuale (tappa 2): aggiunta, scelta con scambio,
rimozione, varco che diventa traccia. DB in memoria, nessuna rete."""
import pytest

from app.models import Track
from app.services.manual_set import (
    AlternativeNotFound,
    ManualSetError,
    RevisionConflict,
    add_alternatives,
    choose_alternative,
    create_manual_set,
    insert_rows,
    path_rows,
    remove_alternative,
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


def _set_con_una_riga(db, track):
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[track.id], gap=False, after_row_id=None)
    return s, path_rows(s)[0]


def test_aggiungi_alternative_in_ordine(db):
    t = _tracks(db, 3)
    s, row = _set_con_una_riga(db, t[0])
    s = add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[t[1].id, t[2].id])
    alts = path_rows(s)[0].alternatives
    assert [a.track_id for a in alts] == [t[1].id, t[2].id]
    assert [a.position for a in alts] == [1, 2]
    assert s.revision == 2


def test_la_traccia_attiva_non_puo_essere_anche_sua_alternativa(db):
    t = _tracks(db, 2)
    s, row = _set_con_una_riga(db, t[0])
    with pytest.raises(ManualSetError):
        add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[t[0].id])


def test_la_stessa_candidata_non_si_aggiunge_due_volte(db):
    t = _tracks(db, 2)
    s, row = _set_con_una_riga(db, t[0])
    s = add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[t[1].id])
    with pytest.raises(ManualSetError):
        add_alternatives(db, s.id, row.id, expected_revision=2, track_ids=[t[1].id])


def test_scegliere_scambia_e_conserva_la_precedente(db):
    t = _tracks(db, 3)
    s, row = _set_con_una_riga(db, t[0])
    s = add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[t[1].id, t[2].id])
    alt = path_rows(s)[0].alternatives[0]
    s = choose_alternative(db, s.id, row.id, alt.id, expected_revision=2)
    riga = path_rows(s)[0]
    assert riga.track_id == t[1].id                            # la candidata e' attiva
    # Anche l'oggetto collegato, non solo la chiave: e' `row.track` che il
    # serializer legge per costruire la risposta, e assegnare la sola foreign
    # key lo lascerebbe puntare alla traccia uscente.
    assert riga.track is not None and riga.track.id == t[1].id
    assert t[0].id in [a.track_id for a in riga.alternatives]  # la precedente e' conservata
    assert t[2].id in [a.track_id for a in riga.alternatives]  # l'altra resta
    assert len(riga.alternatives) == 2
    assert [a.position for a in riga.alternatives] == [1, 2]


def test_scegliere_su_un_varco_lo_trasforma_in_traccia(db):
    t = _tracks(db, 2)
    s, row = _set_con_una_riga(db, t[0])
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=row.id)
    varco = path_rows(s)[1]
    assert varco.slot_kind == "gap"
    s = add_alternatives(db, s.id, varco.id, expected_revision=2, track_ids=[t[1].id])
    alt = path_rows(s)[1].alternatives[0]
    s = choose_alternative(db, s.id, varco.id, alt.id, expected_revision=3)
    riga = path_rows(s)[1]
    assert riga.id == varco.id and riga.slot_kind == "track" and riga.track_id == t[1].id
    assert riga.alternatives == []  # non c'era traccia da conservare


def test_rimuovi_una_alternativa_rinumera(db):
    t = _tracks(db, 4)
    s, row = _set_con_una_riga(db, t[0])
    s = add_alternatives(db, s.id, row.id, expected_revision=1,
                         track_ids=[t[1].id, t[2].id, t[3].id])
    alt = path_rows(s)[0].alternatives[1]
    s = remove_alternative(db, s.id, row.id, alt.id, expected_revision=2)
    alts = path_rows(s)[0].alternatives
    assert [a.track_id for a in alts] == [t[1].id, t[3].id]
    assert [a.position for a in alts] == [1, 2]


def test_alternativa_di_un_altra_riga_non_si_tocca(db):
    t = _tracks(db, 3)
    s, row = _set_con_una_riga(db, t[0])
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[1].id], gap=False, after_row_id=None)
    prima, seconda = path_rows(s)
    s = add_alternatives(db, s.id, prima.id, expected_revision=2, track_ids=[t[2].id])
    alt = path_rows(s)[0].alternatives[0]
    with pytest.raises(AlternativeNotFound):
        remove_alternative(db, s.id, seconda.id, alt.id, expected_revision=3)


def test_traccia_inesistente_fra_le_candidate(db):
    t = _tracks(db, 1)
    s, row = _set_con_una_riga(db, t[0])
    with pytest.raises(ManualSetError):
        add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[999])


def test_conflitto_di_revisione_sulle_alternative(db):
    t = _tracks(db, 2)
    s, row = _set_con_una_riga(db, t[0])
    with pytest.raises(RevisionConflict):
        add_alternatives(db, s.id, row.id, expected_revision=0, track_ids=[t[1].id])
    assert path_rows(s)[0].alternatives == []
