"""Banco di preparazione, tappa 1: colonne nuove, tabella setlist_blocks e il
rebuild una tantum che rende nullable setlist_tracks.track_id (varco)."""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import ensure_schema
from app.models import Setlist, SetlistBlock, SetlistTrack, Track


def _engine(*, foreign_keys: bool = False):
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    if foreign_keys:
        # Come `app.db._make_engine` in produzione: senza questo, SQLite non
        # applica le FK e il rebuild non riprodurrebbe il fallimento reale.
        @event.listens_for(e, "connect")
        def _fk_on(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return e


def _notnull(conn, table: str, col: str) -> bool:
    return {r[1]: bool(r[3]) for r in conn.execute(text(f'PRAGMA table_info("{table}")'))}[col]


def test_db_nuovo_ha_colonne_e_track_id_nullable():
    e = _engine()
    ensure_schema(e)
    with e.connect() as c:
        assert _notnull(c, "setlist_tracks", "track_id") is False
        cols = {r[1] for r in c.execute(text('PRAGMA table_info("setlist_tracks")'))}
        assert {"slot_kind", "block_id", "note"} <= cols
        scols = {r[1] for r in c.execute(text('PRAGMA table_info("setlists")'))}
        assert {"kind", "source_playlist_id", "notes", "revision"} <= scols
        assert c.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='setlist_blocks'"
        )).first()


_LEGACY_SETLIST_TRACKS = """
CREATE TABLE setlist_tracks (
  id INTEGER NOT NULL PRIMARY KEY,
  setlist_id INTEGER NOT NULL REFERENCES setlists (id),
  track_id INTEGER NOT NULL REFERENCES tracks (id),
  position INTEGER NOT NULL,
  role VARCHAR, transition_score FLOAT, transition_reason TEXT, transition_note TEXT,
  ai_reason TEXT, risk_level VARCHAR, mood_tags JSON, created_at DATETIME
)"""


def test_db_esistente_ricostruito_conservando_le_righe():
    e = _engine()
    ensure_schema(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    with S() as s:
        s.add(Track(source_type="spotify", title="A"))
        s.add(Setlist(name="S"))
        s.commit()
    with e.begin() as c:
        c.execute(text("DROP TABLE setlist_tracks"))
        c.execute(text(_LEGACY_SETLIST_TRACKS))
        c.execute(text("INSERT INTO setlist_tracks (setlist_id, track_id, position, created_at) "
                       "VALUES (1, 1, 1, '2026-01-01 00:00:00')"))
    with e.connect() as c:
        assert _notnull(c, "setlist_tracks", "track_id") is True  # premessa del test

    ensure_schema(e)

    with e.connect() as c:
        assert _notnull(c, "setlist_tracks", "track_id") is False
        row = c.execute(text(
            "SELECT setlist_id, track_id, position, slot_kind FROM setlist_tracks"
        )).one()
        assert tuple(row) == (1, 1, 1, "track")
        assert not c.execute(text(
            "SELECT 1 FROM sqlite_master WHERE name='setlist_tracks__rebuild'"
        )).first()
        idx = {r[1] for r in c.execute(text('PRAGMA index_list("setlist_tracks")'))}
        assert "ix_setlist_tracks_track_id" in idx
    ensure_schema(e)  # idempotente: seconda run senza errori
    with e.connect() as c:
        assert c.execute(text("SELECT count(*) FROM setlist_tracks")).scalar() == 1


def test_riga_varco_senza_traccia_e_blocco(db):
    s = Setlist(name="Manuale", kind="manual")
    db.add(s)
    db.flush()
    b = SetlistBlock(setlist_id=s.id, position=1)
    db.add(b)
    db.flush()
    db.add(SetlistTrack(setlist_id=s.id, block_id=b.id, position=1, slot_kind="gap"))
    db.commit()
    db.refresh(s)
    assert s.tracks[0].track is None and s.tracks[0].slot_kind == "gap"
    assert s.blocks[0].rows[0].id == s.tracks[0].id
    assert s.revision == 0 and s.kind == "manual"


def test_rebuild_scarta_le_righe_con_track_id_pendente():
    """Una riga di `setlist_tracks` il cui `track_id` punta a una traccia gia'
    cancellata puo' sopravvivere indefinitamente (SQLite non applica le FK in
    scrittura di suo): il rebuild che rende nullable la colonna la copia con
    `INSERT ... SELECT` sotto FK accese, e senza una pulizia preventiva quella
    singola riga abortisce l'intera transazione di `ensure_schema` (l'app non
    parte piu')."""
    e = _engine(foreign_keys=True)
    ensure_schema(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    with S() as s:
        s.add(Track(source_type="spotify", title="A"))
        s.add(Setlist(name="S"))
        s.commit()
    # PRAGMA foreign_keys e' un no-op dentro una transazione esplicita: va
    # spento fuori da un BEGIN per poter scrivere la riga pendente, cosi' come
    # sarebbe potuta arrivare in un DB scritto prima che le FK fossero accese.
    with e.connect() as raw:
        c = raw.execution_options(isolation_level="AUTOCOMMIT")
        c.execute(text("PRAGMA foreign_keys=OFF"))
        c.execute(text("DROP TABLE setlist_tracks"))
        c.execute(text(_LEGACY_SETLIST_TRACKS))
        c.execute(text("INSERT INTO setlist_tracks (setlist_id, track_id, position, created_at) "
                       "VALUES (1, 1, 1, '2026-01-01 00:00:00')"))
        # Riga pendente: punta a una traccia inesistente. Sopravvive perche' e'
        # stata scritta prima che le FK fossero accese (o mai controllate).
        c.execute(text("INSERT INTO setlist_tracks (setlist_id, track_id, position, created_at) "
                       "VALUES (1, 999, 2, '2026-01-01 00:00:00')"))
        c.execute(text("PRAGMA foreign_keys=ON"))

    ensure_schema(e)  # non deve sollevare IntegrityError

    with e.connect() as c:
        rows = c.execute(text("SELECT track_id FROM setlist_tracks ORDER BY position")).all()
        assert [r[0] for r in rows] == [1]  # la riga pendente (999) e' stata scartata


def test_rebuild_ripulisce_la_tabella_temporanea_di_una_run_interrotta():
    """Se una run precedente e' stata interrotta a meta' rebuild, resta
    `setlist_tracks__rebuild`: la funzione la droppa difensivamente all'inizio
    (`DROP TABLE IF EXISTS`), ma quel percorso non aveva mai un test."""
    e = _engine(foreign_keys=True)
    ensure_schema(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    with S() as s:
        s.add(Track(source_type="spotify", title="A"))
        s.add(Setlist(name="S"))
        s.commit()
    with e.begin() as c:
        c.execute(text("DROP TABLE setlist_tracks"))
        c.execute(text(_LEGACY_SETLIST_TRACKS))
        c.execute(text("INSERT INTO setlist_tracks (setlist_id, track_id, position, created_at) "
                       "VALUES (1, 1, 1, '2026-01-01 00:00:00')"))
        # Leftover di una run precedente interrotta dopo il CREATE ma prima del
        # DROP/RENAME finale.
        c.execute(text(_LEGACY_SETLIST_TRACKS.replace(
            "CREATE TABLE setlist_tracks", 'CREATE TABLE "setlist_tracks__rebuild"')))

    ensure_schema(e)  # deve ripulire il leftover e completare senza errori

    with e.connect() as c:
        assert not c.execute(text(
            "SELECT 1 FROM sqlite_master WHERE name='setlist_tracks__rebuild'"
        )).first()
        assert c.execute(text("SELECT count(*) FROM setlist_tracks")).scalar() == 1


def test_cancellare_il_set_cancella_blocchi_e_righe(db):
    s = Setlist(name="Manuale", kind="manual")
    db.add(s)
    db.flush()
    b = SetlistBlock(setlist_id=s.id, position=1)
    db.add(b)
    db.flush()
    db.add(SetlistTrack(setlist_id=s.id, block_id=b.id, position=1, slot_kind="gap"))
    db.commit()
    db.delete(s)
    db.commit()
    assert db.query(SetlistBlock).count() == 0
    assert db.query(SetlistTrack).count() == 0
