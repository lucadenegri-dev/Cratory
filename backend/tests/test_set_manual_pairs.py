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
