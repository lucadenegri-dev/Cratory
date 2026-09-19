"""Durata del set manuale (tappa 5): percorso risolto e stima incompleta."""
from app.models import Track
from app.services.manual_set import (
    create_manual_set, insert_rows, path_rows, resolved_path, set_duration, update_row,
)


def _tracce(db, n, durata=300):
    out = []
    for i in range(n):
        t = Track(source_type="spotify", title=f"T{i}", bpm=124.0, camelot_key="8A",
                  duration_seconds=durata, has_local_file=True)
        db.add(t)
        out.append(t)
    db.commit()
    return out


def _set(db, tracce):
    s = create_manual_set(db, name="M", playlist_id=None)
    return insert_rows(db, s.id, expected_revision=0, track_ids=[t.id for t in tracce],
                       gap=False, after_row_id=None)


def test_il_percorso_risolto_lascia_fuori_varchi_riserva_e_banco(db):
    t = _tracce(db, 2)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=riga.id)
    da_parte = _tracce(db, 1)[0]
    s = insert_rows(db, s.id, expected_revision=2, track_ids=[da_parte.id], gap=False,
                    after_row_id=None, reserve=True)
    assert len(path_rows(s)) == 3            # il varco c'e', per chi disegna
    assert [r.track_id for r in resolved_path(s)] == [t[0].id, t[1].id]


def test_la_durata_somma_i_file(db):
    t = _tracce(db, 3, durata=300)
    s = _set(db, t)
    d = set_duration(s)
    assert d.seconds == 900
    assert d.incomplete is False
    assert (d.unknown_rows, d.open_gaps) == (0, 0)


def test_la_durata_pianificata_batte_quella_del_file(db):
    """`planned_seconds` e' il contributo NETTO: la traccia dura 5 minuti ma in
    questo set la si tiene due, e il totale deve dire due."""
    t = _tracce(db, 2, durata=300)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, planned_seconds=120)
    assert set_duration(s).seconds == 420     # 120 + 300


def test_una_traccia_senza_durata_rende_la_stima_incompleta(db):
    t = _tracce(db, 2, durata=300)
    senza = Track(source_type="spotify", title="X", has_local_file=True)
    db.add(senza)
    db.commit()
    s = _set(db, t + [senza])
    d = set_duration(s)
    assert d.seconds == 600        # somma solo cio' che sa
    assert d.incomplete is True
    assert d.unknown_rows == 1


def test_una_durata_pianificata_salva_la_stima_di_una_traccia_senza_file(db):
    t = _tracce(db, 1, durata=300)
    senza = Track(source_type="spotify", title="X", has_local_file=True)
    db.add(senza)
    db.commit()
    s = _set(db, t + [senza])
    riga = path_rows(s)[1]
    s = update_row(db, s.id, riga.id, expected_revision=1, planned_seconds=240)
    d = set_duration(s)
    assert (d.seconds, d.incomplete, d.unknown_rows) == (540, False, 0)


def test_un_varco_aperto_rende_la_stima_incompleta(db):
    t = _tracce(db, 2, durata=300)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=riga.id)
    d = set_duration(s)
    assert d.seconds == 600
    assert d.incomplete is True
    assert d.open_gaps == 1


def test_la_durata_pianificata_si_azzera(db):
    t = _tracce(db, 1, durata=300)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, planned_seconds=120)
    s = update_row(db, s.id, riga.id, expected_revision=2, planned_seconds=None)
    assert set_duration(s).seconds == 300


def test_scrivere_l_appunto_non_azzera_la_durata_pianificata(db):
    """Terza proprieta' sulla stessa PATCH parziale: la sentinella vale anche qui."""
    t = _tracce(db, 1, durata=300)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, planned_seconds=120)
    s = update_row(db, s.id, riga.id, expected_revision=2, note="ciao")
    assert path_rows(s)[0].planned_seconds == 120
