"""«Riempi il varco» (prima meta' della tappa 6): il generatore come strumento."""
import pytest

from app.models import Playlist, Track
from app.repositories import add_track_to_playlist
from app.services.manual_set import (
    ManualSetError, create_manual_set, fill_gap, insert_rows, move_row, path_rows,
    resolved_path, undo,
)


def _libreria(db, n=10):
    pl = Playlist(platform="spotify", name="Deep")
    db.add(pl)
    db.flush()
    tracce = []
    for i in range(n):
        t = Track(source_type="spotify", title=f"T{i}", artist=f"A{i}", bpm=124.0 + i * 0.5,
                  camelot_key="8A", duration_seconds=300, has_local_file=True)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl, added_by="test")
        tracce.append(t)
    db.commit()
    return pl, tracce


def _set_con_varco(db, pl, tracce):
    """Due tracce con un varco in mezzo."""
    s = create_manual_set(db, name="M", playlist_ids=[pl.id])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[tracce[0].id, tracce[1].id],
                    gap=False, after_row_id=None)
    prima = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=prima.id)
    return s


def test_riempire_un_varco_mette_il_numero_di_tracce_chiesto(db):
    pl, t = _libreria(db)
    s = _set_con_varco(db, pl, t)
    varco = path_rows(s)[1]
    assert varco.track_id is None

    s = fill_gap(db, s.id, varco.id, expected_revision=2, count=3)
    righe = path_rows(s)
    assert len(righe) == 5                       # 2 di prima + 3 proposte
    assert all(r.track_id is not None for r in righe)   # nessun varco rimasto
    # Il varco e' diventato la prima proposta, tenendo il suo id.
    assert righe[1].id == varco.id


def test_la_proposta_non_ripesca_cio_che_e_gia_nel_percorso(db):
    pl, t = _libreria(db)
    s = _set_con_varco(db, pl, t)
    gia_dentro = {r.track_id for r in resolved_path(s)}
    varco = path_rows(s)[1]

    s = fill_gap(db, s.id, varco.id, expected_revision=2, count=3)
    proposte = [r.track_id for r in path_rows(s)[1:4]]
    assert not (set(proposte) & gia_dentro)
    assert len(set(proposte)) == 3               # nemmeno doppioni fra loro


def test_riempire_e_una_sola_revisione_e_l_annulla_riapre_il_varco(db):
    pl, t = _libreria(db)
    s = _set_con_varco(db, pl, t)
    varco = path_rows(s)[1]

    s = fill_gap(db, s.id, varco.id, expected_revision=2, count=3)
    assert s.revision == 3                       # una sola, non tre

    s = undo(db, s.id, expected_revision=3)
    righe = path_rows(s)
    assert len(righe) == 3
    assert righe[1].id == varco.id and righe[1].track_id is None   # varco com'era


def test_un_varco_in_testa_si_riempie_lo_stesso(db):
    """Senza traccia prima, lo span parte libero: non e' un errore, e' un varco
    all'inizio del set."""
    pl, t = _libreria(db)
    s = create_manual_set(db, name="M", playlist_ids=[pl.id])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False,
                    after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=None)
    # Il varco e' in coda: lo sposto in testa.
    varco = path_rows(s)[1]
    s = move_row(db, s.id, varco.id, expected_revision=2, position=1)
    varco = path_rows(s)[0]

    s = fill_gap(db, s.id, varco.id, expected_revision=3, count=2)
    assert all(r.track_id is not None for r in path_rows(s))


def test_non_si_riempie_una_riga_che_non_e_un_varco(db):
    pl, t = _libreria(db)
    s = _set_con_varco(db, pl, t)
    riga = path_rows(s)[0]
    with pytest.raises(ManualSetError):
        fill_gap(db, s.id, riga.id, expected_revision=2, count=2)


def test_senza_materiale_il_varco_resta_aperto(db):
    """Meglio un rifiuto esplicito che un varco chiuso con niente dentro."""
    pl = Playlist(platform="spotify", name="Vuota")
    db.add(pl)
    db.flush()
    a = Track(source_type="spotify", title="A", bpm=124.0, camelot_key="8A",
              duration_seconds=300, has_local_file=True)
    db.add(a)
    db.flush()
    add_track_to_playlist(db, a, pl, added_by="test")
    db.commit()
    s = create_manual_set(db, name="M", playlist_ids=[pl.id])
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[a.id], gap=False, after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=None)
    varco = path_rows(s)[1]
    with pytest.raises(ManualSetError):
        fill_gap(db, s.id, varco.id, expected_revision=2, count=2)
    db.rollback()
    assert path_rows(s)[1].track_id is None      # ancora aperto


def test_il_riempimento_non_arriva_mai_a_un_client_ai():
    """Vincolo di progetto: il generatore-strumento e' deterministico.

    La curatela non esiste piu' (rimossa il 2026-09-19), ma `integrations/llm.py`
    si': lo usano `routers/ai.py` e i test delle credenziali. Questo test guarda
    il GRAFO DEGLI IMPORT del percorso di riempimento e pretende che non ci
    arrivi mai — cosi' chi un domani pensasse «gia' che ci siamo, chiediamo
    all'AI quale traccia scegliere» lo scopre subito.
    """
    import ast
    from pathlib import Path

    da_ispezionare = ["app/services/manual_fill.py", "app/services/set_generator.py",
                      "app/services/set_skeleton.py", "app/services/manual_set.py"]
    colpevoli = []
    for f in da_ispezionare:
        albero = ast.parse(Path(f).read_text())
        for n in ast.walk(albero):
            moduli = []
            if isinstance(n, ast.ImportFrom) and n.module:
                moduli.append(n.module)
            elif isinstance(n, ast.Import):
                moduli += [a.name for a in n.names]
            for m in moduli:
                if "llm" in m or "ai_curation" in m or "anthropic" in m.lower():
                    colpevoli.append((f, m))
    assert colpevoli == [], colpevoli
