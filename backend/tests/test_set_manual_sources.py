"""Origini multiple di un set (2026-09-19): modello, travaso, ciclo di vita."""
import pytest
from sqlalchemy import select

from app.models import Playlist, Setlist, SetlistSource, Track
from app.repositories import add_track_to_playlist, delete_playlist


def _playlist(db, nome, n=2):
    pl = Playlist(platform="spotify", name=nome)
    db.add(pl)
    db.flush()
    for i in range(n):
        t = Track(source_type="spotify", title=f"{nome}-{i}", artist="A",
                  duration_seconds=300, bpm=124.0, camelot_key="8A", has_local_file=True)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl, added_by="test")
    db.commit()
    return pl


def test_un_set_puo_avere_piu_origini_in_ordine(db):
    a, b = _playlist(db, "A"), _playlist(db, "B")
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add_all([
        SetlistSource(setlist_id=s.id, playlist_id=b.id, position=2),
        SetlistSource(setlist_id=s.id, playlist_id=a.id, position=1),
    ])
    db.commit()
    db.refresh(s)
    assert [src.playlist_id for src in s.sources] == [a.id, b.id]


def test_cancellare_il_set_cancella_le_sue_origini_non_le_playlist(db):
    a = _playlist(db, "A")
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistSource(setlist_id=s.id, playlist_id=a.id, position=1))
    db.commit()
    db.delete(s)
    db.commit()
    assert db.scalars(select(SetlistSource)).all() == []
    assert db.get(Playlist, a.id) is not None


def test_cancellare_una_playlist_toglie_l_origine_e_lascia_il_set(db):
    """Regola di sempre: il set resta, il materiale si riduce. Prima la riga di
    origine veniva azzerata; ora va tolta, altrimenti resta appesa a una
    playlist che non c'e' piu'."""
    a, b = _playlist(db, "A"), _playlist(db, "B")
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add_all([SetlistSource(setlist_id=s.id, playlist_id=a.id, position=1),
                SetlistSource(setlist_id=s.id, playlist_id=b.id, position=2)])
    db.commit()

    delete_playlist(db, a.id)

    db.expire_all()
    s = db.get(Setlist, s.id)
    assert s is not None
    assert [src.playlist_id for src in s.sources] == [b.id]


def test_un_set_vecchio_ritrova_la_sua_origine_dopo_la_migrazione(tmp_path):
    """Chi aggiorna ha set con `source_playlist_id`: se la tabella nuova nascesse
    vuota, il materiale si ridurrebbe alla ricerca in libreria e sembrerebbe che
    l'app abbia dimenticato da dove venivano."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.db import Base, ensure_schema
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    eng = create_engine(f"sqlite:///{tmp_path / 'vecchio.db'}")
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as sess:
        pl = Playlist(platform="spotify", name="Deep")
        sess.add(pl)
        sess.flush()
        sess.add(Setlist(name="Vecchio", kind="manual", source_playlist_id=pl.id))
        sess.commit()
        pl_id = pl.id
    # La tabella nuova nasce vuota, come su un database che aggiorna.
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM setlist_sources"))

    ensure_schema(eng)

    with eng.begin() as conn:
        righe = conn.execute(text(
            "SELECT playlist_id, position FROM setlist_sources")).fetchall()
    assert [tuple(r) for r in righe] == [(pl_id, 1)]


def test_il_travaso_si_puo_rieseguire(tmp_path):
    """`ensure_schema` gira a ogni avvio: la seconda volta non deve duplicare."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.db import Base, ensure_schema
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    eng = create_engine(f"sqlite:///{tmp_path / 'due-volte.db'}")
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as sess:
        pl = Playlist(platform="spotify", name="Deep")
        sess.add(pl)
        sess.flush()
        sess.add(Setlist(name="Vecchio", kind="manual", source_playlist_id=pl.id))
        sess.commit()
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM setlist_sources"))

    ensure_schema(eng)
    ensure_schema(eng)

    with eng.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM setlist_sources")).scalar_one() == 1


# --- Task 2: materiale e mutazioni --------------------------------------------

from app.services.manual_material import material_for, material_for_playlists  # noqa: E402
from app.services.manual_set import (  # noqa: E402
    ManualSetError, add_source, create_manual_set, insert_rows, path_rows, remove_source,
)


def test_il_materiale_unisce_le_playlist_senza_doppioni(db):
    a, b = _playlist(db, "A"), _playlist(db, "B")
    # Una traccia sta in tutt'e due: deve comparire una volta sola.
    comune = db.scalars(select(Track).where(Track.title == "A-0")).one()
    add_track_to_playlist(db, comune, b, added_by="test")
    db.commit()

    s = create_manual_set(db, name="M", playlist_ids=[a.id, b.id])
    titoli = [t.title for t, *_ in material_for(db, s, q=None, owned=False, unused=False)]
    assert titoli.count("A-0") == 1
    assert {"A-0", "A-1", "B-0", "B-1"} <= set(titoli)


def test_l_ordine_delle_origini_e_quello_del_materiale(db):
    a, b = _playlist(db, "A"), _playlist(db, "B")
    s = create_manual_set(db, name="M", playlist_ids=[b.id, a.id])
    titoli = [t.title for t, *_ in material_for(db, s, q=None, owned=False, unused=False)]
    assert titoli.index("B-0") < titoli.index("A-0")


def test_si_aggiunge_e_si_toglie_un_origine_mentre_si_lavora(db):
    a, b = _playlist(db, "A"), _playlist(db, "B")
    s = create_manual_set(db, name="M", playlist_ids=[a.id])
    s = add_source(db, s.id, expected_revision=0, playlist_id=b.id)
    assert [src.playlist_id for src in s.sources] == [a.id, b.id]

    s = remove_source(db, s.id, expected_revision=1, playlist_id=a.id)
    assert [src.playlist_id for src in s.sources] == [b.id]
    titoli = [t.title for t, *_ in material_for(db, s, q=None, owned=False, unused=False)]
    assert not any(t.startswith("A-") for t in titoli)


def test_togliere_un_origine_non_tocca_il_percorso(db):
    """Una traccia gia' scelta e' una decisione presa: sparisce dal materiale,
    non dal set."""
    a = _playlist(db, "A")
    s = create_manual_set(db, name="M", playlist_ids=[a.id])
    traccia = db.scalars(select(Track).where(Track.title == "A-0")).one()
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[traccia.id],
                    gap=False, after_row_id=None)

    s = remove_source(db, s.id, expected_revision=1, playlist_id=a.id)
    assert [r.track_id for r in path_rows(s)] == [traccia.id]
    # E resta nel materiale, perche' e' nel set: solo non piu' "dalla playlist".
    voci = {t.title: from_pl for t, _in_set, from_pl, _ in
            material_for(db, s, q=None, owned=False, unused=False)}
    assert voci["A-0"] is False


def test_la_stessa_origine_non_si_aggiunge_due_volte(db):
    a = _playlist(db, "A")
    s = create_manual_set(db, name="M", playlist_ids=[a.id])
    with pytest.raises(ManualSetError):
        add_source(db, s.id, expected_revision=0, playlist_id=a.id)


def test_il_materiale_di_una_bozza_non_ha_un_set(db):
    """La bozza non ha ancora un set: il materiale si chiede per playlist, e
    nessuna traccia risulta «nel set»."""
    a, b = _playlist(db, "A"), _playlist(db, "B")
    voci = material_for_playlists(db, [a.id, b.id], q=None, owned=False)
    assert len(voci) == 4
    assert all(not in_set and not in_reserve for _t, in_set, _fp, in_reserve in voci)
