"""Il set manuale nel ciclo di vita esistente: lead orfani con righe varco,
riepilogo con varchi, cancellazione della playlist di origine, pulizia legacy."""
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import _migrate_drop_legacy, ensure_schema
from app.models import Playlist, Setlist, SetlistBlock, SetlistTrack, Track
from app.repositories import delete_playlist, get_setlist, orphan_lead_ids, unreferenced_track_ids
from app.serializers import setlist_summary_out


def _manual_with_gap(db, track=None):
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    b = SetlistBlock(setlist_id=s.id, position=1)
    db.add(b)
    db.flush()
    db.add(SetlistTrack(setlist_id=s.id, block_id=b.id, position=1, slot_kind="gap"))
    if track is not None:
        db.add(SetlistTrack(setlist_id=s.id, block_id=b.id, position=2, track_id=track.id))
    db.commit()
    return s


def test_lead_orfano_trovato_anche_se_esiste_una_riga_varco(db):
    lead = Track(source_type="spotify", title="Lead", has_local_file=False)
    db.add(lead)
    db.commit()
    _manual_with_gap(db)
    # NOT IN con un NULL nel sottoinsieme non trova mai nulla: la guardia sul
    # NULL deve esserci, altrimenti nessun lead sarebbe piu' orfano.
    assert orphan_lead_ids(db, [lead.id]) == [lead.id]


def test_lead_nel_set_manuale_non_e_orfano(db):
    lead = Track(source_type="spotify", title="Lead", has_local_file=False)
    db.add(lead)
    db.commit()
    _manual_with_gap(db, track=lead)
    assert orphan_lead_ids(db, [lead.id]) == []


def test_traccia_sganciata_trovata_anche_se_esiste_una_riga_varco(db):
    orphan = Track(source_type="spotify", title="Sganciata", has_local_file=False)
    db.add(orphan)
    db.commit()
    _manual_with_gap(db)
    # Stesso bug di orphan_lead_ids: NOT IN con un NULL nel sottoinsieme non
    # trova mai nulla, senza la guardia sul NULL nessuna traccia sarebbe piu'
    # "sganciata" appena esiste una riga varco in un set qualsiasi.
    assert unreferenced_track_ids(db, [orphan.id]) == [orphan.id]


def test_riepilogo_conta_solo_le_tracce_e_porta_il_kind(db):
    tr = Track(source_type="spotify", title="A", duration_seconds=300, has_local_file=True)
    db.add(tr)
    db.commit()
    s = _manual_with_gap(db, track=tr)
    out = setlist_summary_out(get_setlist(db, s.id))
    assert out.kind == "manual"
    assert out.track_count == 1
    assert out.total_duration_seconds == 300


def test_cancellare_la_playlist_azzera_l_origine_del_set(db):
    pl = Playlist(platform="spotify", name="Deep")
    db.add(pl)
    db.flush()
    s = Setlist(name="M", kind="manual", source_playlist_id=pl.id)
    db.add(s)
    db.commit()
    delete_playlist(db, pl.id)
    assert get_setlist(db, s.id).source_playlist_id is None


def test_pulizia_legacy_non_cancella_i_set_manuali_vuoti():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ensure_schema(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    with S() as s:
        s.add(Setlist(name="vuoto manuale", kind="manual"))
        s.add(Setlist(name="vuoto generato", kind="generated"))
        s.commit()
    with e.begin() as c:
        # Una colonna morta su tracks fa scattare il ramo di pulizia legacy.
        c.execute(text("ALTER TABLE tracks ADD COLUMN tonality VARCHAR"))
        _migrate_drop_legacy(c)
    with S() as s:
        names = set(s.scalars(select(Setlist.name)).all())
    assert names == {"vuoto manuale"}
