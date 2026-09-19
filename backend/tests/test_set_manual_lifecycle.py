"""Il set manuale nel ciclo di vita esistente: lead orfani con righe varco,
riepilogo con varchi, cancellazione della playlist di origine, pulizia legacy."""
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import _migrate_drop_legacy, ensure_schema
from app.models import (
    Playlist, Setlist, SetlistAlternative, SetlistBlock, SetlistPairNote, SetlistTrack, Track,
)
from app.repositories import (
    delete_playlist, get_setlist, merge_tracks, orphan_lead_ids, unreferenced_track_ids,
)
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


# --- Tappa 2: le alternative nel ciclo di vita ---------------------------------


def _manual_with_alternative(db, active, candidate):
    """Set manuale con una riga attiva su `active` e `candidate` fra le sue alternative."""
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    b = SetlistBlock(setlist_id=s.id, position=1)
    db.add(b)
    db.flush()
    row = SetlistTrack(setlist_id=s.id, block_id=b.id, position=1, track_id=active.id)
    db.add(row)
    db.flush()
    db.add(SetlistAlternative(setlist_track_id=row.id, track_id=candidate.id, position=1))
    db.commit()
    return s, row


def test_traccia_fra_le_alternative_non_e_orfana(db):
    attiva = Track(source_type="spotify", title="Attiva", has_local_file=True)
    candidata = Track(source_type="spotify", title="Candidata", has_local_file=False)
    db.add_all([attiva, candidata])
    db.commit()
    _manual_with_alternative(db, attiva, candidata)
    assert orphan_lead_ids(db, [candidata.id]) == []


def test_traccia_fra_le_alternative_e_referenziata(db):
    attiva = Track(source_type="spotify", title="Attiva", has_local_file=True)
    candidata = Track(source_type="spotify", title="Candidata", has_local_file=True)
    db.add_all([attiva, candidata])
    db.commit()
    _manual_with_alternative(db, attiva, candidata)
    assert candidata.id not in unreferenced_track_ids(db, [candidata.id])


def test_merge_sposta_le_alternative_sulla_traccia_che_resta(db):
    attiva = Track(source_type="spotify", title="Attiva", has_local_file=True)
    keep = Track(source_type="spotify", title="Keep", has_local_file=True)
    drop = Track(source_type="spotify", title="Drop", has_local_file=True)
    db.add_all([attiva, keep, drop])
    db.commit()
    s, row = _manual_with_alternative(db, attiva, drop)
    merge_tracks(db, keep, drop)
    db.refresh(row)
    assert [a.track_id for a in row.alternatives] == [keep.id]


def test_merge_non_duplica_una_alternativa_gia_presente(db):
    attiva = Track(source_type="spotify", title="Attiva", has_local_file=True)
    keep = Track(source_type="spotify", title="Keep", has_local_file=True)
    drop = Track(source_type="spotify", title="Drop", has_local_file=True)
    db.add_all([attiva, keep, drop])
    db.commit()
    s, row = _manual_with_alternative(db, attiva, keep)
    db.add(SetlistAlternative(setlist_track_id=row.id, track_id=drop.id, position=2))
    db.commit()
    merge_tracks(db, keep, drop)
    db.refresh(row)
    assert [a.track_id for a in row.alternatives] == [keep.id]  # una sola, non due


def test_un_lead_giudicato_in_un_passaggio_non_e_orfano(db):
    """Un appunto su A->B sopravvive all'uscita di B dal percorso: se la pulizia
    cancellasse B, l'appunto resterebbe appeso al nulla."""
    a = Track(source_type="spotify", title="A", has_local_file=True)
    b = Track(source_type="spotify", title="B")  # lead, niente file
    db.add_all([a, b])
    db.flush()
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=b.id, note="x"))
    db.commit()

    assert b.id not in orphan_lead_ids(db)
    assert b.id not in unreferenced_track_ids(db)


def test_fondere_due_tracce_sposta_gli_appunti_di_coppia(db):
    a = Track(source_type="spotify", title="A", has_local_file=True)
    b = Track(source_type="spotify", title="B", has_local_file=True)
    doppione = Track(source_type="spotify", title="B bis", has_local_file=True)
    db.add_all([a, b, doppione])
    db.flush()
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=doppione.id,
                           note="dal doppione"))
    db.commit()

    merge_tracks(db, keep=b, drop=doppione)
    db.commit()

    righe = db.scalars(select(SetlistPairNote)).all()
    assert [(p.from_track_id, p.to_track_id) for p in righe] == [(a.id, b.id)]


def test_fondere_non_crea_due_appunti_sulla_stessa_coppia(db):
    """Se esistono gia' A->keep e A->drop, dopo la fusione ne resta uno solo:
    la terna (set, from, to) e' unica, e un UPDATE cieco violerebbe l'indice."""
    a = Track(source_type="spotify", title="A", has_local_file=True)
    b = Track(source_type="spotify", title="B", has_local_file=True)
    doppione = Track(source_type="spotify", title="B bis", has_local_file=True)
    db.add_all([a, b, doppione])
    db.flush()
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add_all([
        SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=b.id, note="tengo"),
        SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=doppione.id, note="cade"),
    ])
    db.commit()

    merge_tracks(db, keep=b, drop=doppione)
    db.commit()

    righe = db.scalars(select(SetlistPairNote)).all()
    assert [p.note for p in righe] == ["tengo"]
