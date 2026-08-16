"""La coda non deve rendere indistruttibile una traccia.

`DownloadQueueItem.track_id` e' una foreign key verso `tracks.id` senza
cascade, e in produzione le foreign key sono accese: ogni punto che cancella
una Track (cancellazione playlist, rimozione di una traccia da una playlist,
fusione dei doppioni dopo un download) deve prima sbrogliare gli item di coda,
altrimenti va in IntegrityError. Il vincolo lo tiene qualsiasi riga, anche
`done`/`cancelled` — cioe' lo storico, che resta finche' l'utente non lo
svuota.

I test girano sulla fixture `db` di conftest, che ha `PRAGMA foreign_keys=ON`
come la produzione: senza il pragma questi test passerebbero anche col codice
rotto (era esattamente la ragione per cui il difetto era sfuggito).
"""
from app.models import DownloadQueueItem, Playlist, Track
from app.repositories import (
    add_track_to_playlist, delete_playlist, delete_playlist_track, merge_tracks,
)


def _pl(db, name="P"):
    pl = Playlist(platform="spotify", name=name, kind="playlist")
    db.add(pl)
    db.flush()
    return pl


def _tr(db, title):
    t = Track(source_type="spotify", title=title, artist="A")
    db.add(t)
    db.flush()
    return t


def _item(db, track, state="done", **kw):
    it = DownloadQueueItem(track_id=track.id, kind="soulseek_auto", state=state,
                           position=0, **kw)
    db.add(it)
    db.flush()
    return it


def test_cancella_playlist_con_storico_in_coda(db):
    """Lo scenario ordinario: importi una playlist, accodi, cancelli la playlist.
    Il lead orfano se ne va e con lui le sue righe di coda."""
    pl, t = _pl(db), _tr(db, "lead")
    add_track_to_playlist(db, t, pl)
    _item(db, t, state="done", outcome="not_found")
    _item(db, t, state="cancelled")
    db.commit()

    assert delete_playlist(db, pl.id) == 1
    assert db.query(Track).count() == 0
    assert db.query(DownloadQueueItem).count() == 0


def test_cancella_playlist_con_item_ancora_in_coda(db):
    """Anche un item mai eseguito (`queued`) non deve impedire la cancellazione."""
    pl, t = _pl(db), _tr(db, "lead")
    add_track_to_playlist(db, t, pl)
    _item(db, t, state="queued")
    db.commit()

    assert delete_playlist(db, pl.id) == 1
    assert db.query(DownloadQueueItem).count() == 0


def test_togli_traccia_da_playlist_con_storico_in_coda(db):
    pl, t = _pl(db), _tr(db, "lead")
    add_track_to_playlist(db, t, pl)
    _item(db, t, state="done", outcome="failed")
    db.commit()

    assert delete_playlist_track(db, pl.id, t.id) == 1
    assert db.query(Track).count() == 0
    assert db.query(DownloadQueueItem).count() == 0


def test_lo_storico_di_una_traccia_che_resta_non_viene_toccato(db):
    """La pulizia deve colpire solo gli item dei lead cancellati: una traccia
    posseduta resta, e con lei il suo storico."""
    pl = _pl(db)
    lead, owned = _tr(db, "lead"), _tr(db, "owned")
    owned.has_local_file = True
    add_track_to_playlist(db, lead, pl)
    add_track_to_playlist(db, owned, pl)
    _item(db, lead, state="done", outcome="not_found")
    superstite = _item(db, owned, state="done", outcome="downloaded")
    db.commit()

    assert delete_playlist(db, pl.id) == 1
    assert [i.id for i in db.query(DownloadQueueItem).all()] == [superstite.id]


def test_merge_sposta_lo_storico_di_coda_sulla_traccia_che_resta(db):
    """`merge_tracks` e' il percorso che il runner puo' innescare da solo:
    il file scaricato collide per hash con un'altra traccia e `attach_local_file`
    fonde. Lo storico di coda di `drop` non e' un dettaglio da perdere — e
    soprattutto non deve far esplodere la fusione."""
    keep, drop = _tr(db, "keep"), _tr(db, "drop")
    storico = _item(db, drop, state="done", outcome="downloaded")
    annullato = _item(db, drop, state="cancelled")
    db.commit()

    merge_tracks(db, keep, drop)
    db.commit()

    assert db.query(Track).count() == 1
    assert {i.id: i.track_id for i in db.query(DownloadQueueItem).all()} == {
        storico.id: keep.id, annullato.id: keep.id,
    }


def test_merge_non_crea_due_item_attivi_per_la_stessa_traccia(db):
    """L'invariante della deduplica (`enqueue` salta una traccia che ha gia' un
    item attivo) deve reggere anche dopo una fusione: se entrambe le tracce
    hanno un item attivo, quello di `drop` sparisce invece di raddoppiare."""
    keep, drop = _tr(db, "keep"), _tr(db, "drop")
    attivo_keep = _item(db, keep, state="queued")
    _item(db, drop, state="running")
    db.commit()

    merge_tracks(db, keep, drop)
    db.commit()

    attivi = db.query(DownloadQueueItem).filter(
        DownloadQueueItem.state.in_(("queued", "running"))).all()
    assert [i.id for i in attivi] == [attivo_keep.id]


def test_merge_sposta_l_item_attivo_se_la_traccia_superstite_non_ne_ha(db):
    keep, drop = _tr(db, "keep"), _tr(db, "drop")
    attivo = _item(db, drop, state="queued")
    db.commit()

    merge_tracks(db, keep, drop)
    db.commit()

    assert db.get(DownloadQueueItem, attivo.id).track_id == keep.id


def test_cancella_lead_orfano_ancora_puntato_da_un_audiofile(db):
    """Difetto della stessa famiglia, preesistente alla coda ed emerso
    accendendo le foreign key: `AudioFile.track_id` (lato Organize) punta a
    `tracks.id` ed e' nullable. Cancellando via ORM SQLAlchemy lo azzera da
    solo, ma `delete_orphan_leads` cancella in blocco — e il vincolo la ferma.
    Succede quando un file sparisce dal disco: `riconcilia_possessi` riporta la
    traccia a lead senza staccare la riga `AudioFile`."""
    from app.organize.models import AudioFile, ScanRoot

    pl, t = _pl(db), _tr(db, "lead")
    add_track_to_playlist(db, t, pl)
    root = ScanRoot(path="/radice")
    db.add(root)
    db.flush()
    file_orfano = AudioFile(root_id=root.id, path="/radice/a.mp3", location="library",
                            status="missing", ext="mp3", size_bytes=1,
                            hash_method="test-stub", track_id=t.id)
    db.add(file_orfano)
    db.commit()

    assert delete_playlist(db, pl.id) == 1
    assert db.query(Track).count() == 0
    db.expire_all()  # l'UPDATE e' in blocco (synchronize_session=False)
    assert db.get(AudioFile, file_orfano.id).track_id is None
