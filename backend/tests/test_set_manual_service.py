"""Servizio del set manuale (tappa 1): creazione, righe, varco, spostamento,
rimozione, appunto, revisione. DB in memoria, nessuna rete."""
import pytest

from app.models import Playlist, SetlistTrack, Track
from app.repositories import add_track_to_playlist, get_setlist
from app.services.manual_set import (
    ManualSetNotFound,
    ManualSetNotManual,
    RevisionConflict,
    RowNotFound,
    ManualSetError,
    create_manual_set,
    insert_rows,
    move_row,
    path_rows,
    remove_row,
    update_row_note,
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


def _playlist(db, tracks):
    pl = Playlist(platform="spotify", name="Deep")
    db.add(pl)
    db.flush()
    for t in tracks:
        add_track_to_playlist(db, t, pl, added_by="test")
    db.commit()
    return pl


def _ids(setlist):
    return [r.track_id for r in path_rows(setlist)]


def test_crea_vuoto_da_playlist(db):
    pl = _playlist(db, _tracks(db, 2))
    s = create_manual_set(db, name=None, playlist_id=pl.id)
    assert s.kind == "manual" and s.source_playlist_id == pl.id
    assert s.name == "Deep"  # default: il nome della playlist
    assert s.revision == 0 and s.tracks == [] and s.blocks == []


def test_crea_senza_playlist_con_nome(db):
    s = create_manual_set(db, name="  Sabato  ", playlist_id=None)
    assert s.name == "Sabato" and s.source_playlist_id is None


def test_crea_con_playlist_inesistente(db):
    with pytest.raises(ManualSetError):
        create_manual_set(db, name=None, playlist_id=999)


def test_inserisci_crea_il_blocco_main_e_incrementa_la_revisione(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id, t[1].id], gap=False, after_row_id=None)
    assert s.revision == 1
    assert [b.placement for b in s.blocks] == ["main"]
    assert _ids(s) == [t[0].id, t[1].id]
    assert [r.position for r in path_rows(s)] == [1, 2]


def test_inserisci_dopo_una_riga(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id, t[1].id], gap=False, after_row_id=None)
    first = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[2].id], gap=False, after_row_id=first.id)
    assert _ids(s) == [t[0].id, t[2].id, t[1].id]
    assert [r.position for r in path_rows(s)] == [1, 2, 3]


def test_inserisci_un_varco(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id, t[1].id], gap=False, after_row_id=None)
    first = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=first.id)
    rows = path_rows(s)
    assert [r.slot_kind for r in rows] == ["track", "gap", "track"]
    assert rows[1].track_id is None and rows[1].track is None


def test_inserisci_rifiuta_la_stessa_traccia_due_volte_nel_percorso(db):
    t = _tracks(db, 1)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    with pytest.raises(ManualSetError):
        insert_rows(db, s.id, expected_revision=1, track_ids=[t[0].id], gap=False, after_row_id=None)


def test_inserisci_traccia_senza_bpm_ne_tonalita(db):
    """Spec: nel percorso entra anche chi non ha dati tecnici (file locale basta)."""
    t = Track(source_type="spotify", title="Grezza", has_local_file=True)
    db.add(t)
    db.commit()
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t.id], gap=False, after_row_id=None)
    assert _ids(s) == [t.id]


def test_inserisci_traccia_inesistente(db):
    s = create_manual_set(db, name="M", playlist_id=None)
    with pytest.raises(ManualSetError):
        insert_rows(db, s.id, expected_revision=0, track_ids=[999], gap=False, after_row_id=None)


def test_inserisci_dopo_una_riga_fuori_dal_blocco_principale(db):
    """`after_row_id` che nomina una riga fuori dal blocco main (es. una riserva,
    block_id NULL: non ancora raggiungibile in tappa 1 ma gia' nel modello) deve
    dare un errore di dominio, non un ValueError non gestito da rows.index()."""
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_id=None)
    # Aggiunta via relationship (non solo la colonna FK): cosi' la riga entra
    # subito in `s.tracks` in memoria, come farebbe il caricamento eager reale
    # di un set con piu' blocchi (tappa 2/3) — senza questo la riga resterebbe
    # invisibile alla collezione gia' caricata e il test proverebbe solo
    # RowNotFound invece del vero bug (rows.index() fuori dal blocco main).
    reserve = SetlistTrack(block_id=None, position=1, slot_kind="track", track_id=t[0].id)
    s.tracks.append(reserve)
    db.commit()
    with pytest.raises(ManualSetError):
        insert_rows(db, s.id, expected_revision=0, track_ids=[t[1].id], gap=False,
                   after_row_id=reserve.id)


def test_sposta_a_posizione(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t], gap=False, after_row_id=None)
    last = path_rows(s)[2]
    s = move_row(db, s.id, last.id, expected_revision=1, position=1)
    assert _ids(s) == [t[2].id, t[0].id, t[1].id]
    assert [r.position for r in path_rows(s)] == [1, 2, 3]
    assert s.revision == 2


def test_sposta_posizione_fuori_range(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t], gap=False, after_row_id=None)
    with pytest.raises(ManualSetError):
        move_row(db, s.id, path_rows(s)[0].id, expected_revision=1, position=5)


def test_togli_rinumera(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t], gap=False, after_row_id=None)
    s = remove_row(db, s.id, path_rows(s)[1].id, expected_revision=1)
    assert _ids(s) == [t[0].id, t[2].id]
    assert [r.position for r in path_rows(s)] == [1, 2]


def test_appunto_su_riga(db):
    t = _tracks(db, 1)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    row = path_rows(s)[0]
    s = update_row_note(db, s.id, row.id, expected_revision=1, note="  entra sul break  ")
    assert path_rows(s)[0].note == "entra sul break"
    s = update_row_note(db, s.id, row.id, expected_revision=2, note="")
    assert path_rows(s)[0].note is None


def test_revisione_sbagliata_solleva_conflitto_e_non_muta(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    with pytest.raises(RevisionConflict) as exc:
        insert_rows(db, s.id, expected_revision=0, track_ids=[t[1].id], gap=False, after_row_id=None)
    assert exc.value.current == 1
    assert _ids(get_setlist(db, s.id)) == [t[0].id]


def test_riga_inesistente(db):
    s = create_manual_set(db, name="M", playlist_id=None)
    with pytest.raises(RowNotFound):
        remove_row(db, s.id, 999, expected_revision=0)


def test_set_inesistente_e_set_non_manuale(db, seed_tracks):
    # Il set generato si costruisce a mano: `generate_set` e' sparito il
    # 2026-09-19, ma «le rotte manuali rifiutano un set generato» resta vero e
    # va verificato — finche' un set `generated` puo' esistere in archivio.
    from app.models import Setlist

    seed_tracks(n=2)
    generated = Setlist(name="Vecchio", kind="generated", generated_by="algorithmic")
    db.add(generated)
    db.commit()
    with pytest.raises(ManualSetNotFound):
        remove_row(db, 999, 1, expected_revision=0)
    with pytest.raises(ManualSetNotManual):
        insert_rows(db, generated.id, expected_revision=0, track_ids=[], gap=True, after_row_id=None)
