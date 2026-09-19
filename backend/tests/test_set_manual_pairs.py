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


# --- Task 2: compatibilita' di un passaggio ------------------------------------

from app.services.manual_pairs import bpm_of, pair_compat  # noqa: E402


def _riga(track=None, play_bpm=None, slot_kind="track"):
    return SetlistTrack(position=1, track=track, play_bpm=play_bpm, slot_kind=slot_kind)


def test_la_compatibilita_dice_pitch_e_tonalita(db):
    a, b = _due_tracce(db)          # 124 8A -> 126 9A
    c = pair_compat(_riga(a), _riga(b))
    assert (c.bpm_from, c.bpm_to) == (124.0, 126.0)
    assert c.bpm_percent == 1.6
    assert c.halftime is False
    assert c.key_relation == "adjacent"
    assert c.missing == []
    assert isinstance(c.score, int)


def test_un_dato_mancante_si_dichiara_invece_di_valere_neutro(db):
    """La spec lo chiede per nome: con BPM o tonalita' mancanti si mostra
    «sconosciuto», non il punteggio neutro che `score_transition` darebbe."""
    a, _ = _due_tracce(db)
    senza = Track(source_type="spotify", title="X", duration_seconds=300, has_local_file=True)
    db.add(senza)
    db.commit()
    c = pair_compat(_riga(a), _riga(senza))
    assert c.score is None
    assert sorted(c.missing) == ["bpm", "key"]
    assert c.bpm_percent is None
    assert c.key_relation == "unknown"


def test_la_suono_a_batte_il_bpm_della_traccia(db):
    a, b = _due_tracce(db)          # 124 -> 126
    assert bpm_of(_riga(a)) == 124.0
    assert bpm_of(_riga(a, play_bpm=126.0)) == 126.0
    # Portate allo stesso tempo, il pitch che serve e' zero.
    c = pair_compat(_riga(a, play_bpm=126.0), _riga(b))
    assert c.bpm_from == 126.0
    assert c.bpm_percent == 0.0


def test_un_varco_non_ha_compatibilita(db):
    """Regola della spec: finche' il varco e' aperto, le tracce ai suoi lati non
    sono vicine. Chi calcola non deve nemmeno essere chiamato: qui si verifica
    che una riga senza traccia non produca numeri inventati."""
    a, _ = _due_tracce(db)
    c = pair_compat(_riga(a), _riga(None, slot_kind="gap"))
    assert c.score is None
    assert sorted(c.missing) == ["bpm", "key"]


# --- Task 3: le mutazioni ------------------------------------------------------

from app.services.manual_set import (  # noqa: E402
    add_alternatives, choose_alternative, create_manual_set, insert_rows, pair_note_map,
    path_rows, set_pair_note, undo, update_row,
)


def _set_con_due(db):
    a, b = _due_tracce(db)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[a.id, b.id],
                    gap=False, after_row_id=None)
    return s, a, b


def test_l_appunto_di_coppia_si_scrive_e_si_rilegge(db):
    s, a, b = _set_con_due(db)
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="  entra sul break  ")
    assert pair_note_map(s) == {(a.id, b.id): "entra sul break"}


def test_un_appunto_vuoto_toglie_la_riga(db):
    """Niente righe vuote in giro: svuotare il campo e' cancellare l'appunto."""
    s, a, b = _set_con_due(db)
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="x")
    s = set_pair_note(db, s.id, expected_revision=2, from_track_id=a.id,
                      to_track_id=b.id, note="   ")
    assert pair_note_map(s) == {}


def test_riscrivere_la_stessa_coppia_non_crea_un_doppione(db):
    s, a, b = _set_con_due(db)
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="primo")
    s = set_pair_note(db, s.id, expected_revision=2, from_track_id=a.id,
                      to_track_id=b.id, note="secondo")
    assert pair_note_map(s) == {(a.id, b.id): "secondo"}


def test_il_giudizio_non_si_trasferisce_e_non_si_perde(db):
    """La verifica dichiarata dalla spec, senza la parola «stato»: scrivo su
    A->B, sostituisco B con C e A->C non ha appunto; rimetto B e lo ritrovo."""
    s, a, b = _set_con_due(db)
    c = Track(source_type="spotify", title="C", bpm=125.0, camelot_key="8A",
              duration_seconds=300, has_local_file=True)
    db.add(c)
    db.commit()
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="entra sul break")

    riga_b = path_rows(s)[1]
    s = add_alternatives(db, s.id, riga_b.id, expected_revision=2, track_ids=[c.id])
    s = choose_alternative(db, s.id, riga_b.id,
                           path_rows(s)[1].alternatives[0].id, expected_revision=3)
    assert [r.track_id for r in path_rows(s)] == [a.id, c.id]
    assert (a.id, c.id) not in pair_note_map(s)      # A->C e' da valutare
    assert pair_note_map(s)[(a.id, b.id)] == "entra sul break"  # non persa

    riga_c = path_rows(s)[1]
    s = choose_alternative(db, s.id, riga_c.id,
                           path_rows(s)[1].alternatives[0].id, expected_revision=4)
    assert [r.track_id for r in path_rows(s)] == [a.id, b.id]
    assert pair_note_map(s)[(a.id, b.id)] == "entra sul break"  # ritrovata


def test_la_suono_a_si_scrive_sulla_riga(db):
    s, a, b = _set_con_due(db)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, play_bpm=126.0)
    assert path_rows(s)[0].play_bpm == 126.0
    assert a.bpm == 124.0  # la libreria non si tocca


def test_scrivere_l_appunto_non_azzera_la_suono_a(db):
    """Il difetto classico di una PATCH parziale: un campo non mandato non e'
    un campo da azzerare. Senza sentinella questo test cade."""
    s, a, b = _set_con_due(db)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, play_bpm=126.0)
    s = update_row(db, s.id, riga.id, expected_revision=2, note="ciao")
    assert path_rows(s)[0].play_bpm == 126.0
    assert path_rows(s)[0].note == "ciao"
    # E azzerare resta possibile, esplicitamente.
    s = update_row(db, s.id, riga.id, expected_revision=3, play_bpm=None)
    assert path_rows(s)[0].play_bpm is None


def test_annullare_riporta_indietro_un_appunto_di_coppia(db):
    s, a, b = _set_con_due(db)
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="x")
    s = undo(db, s.id, expected_revision=2)
    assert pair_note_map(s) == {}
