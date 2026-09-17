"""Banco di preparazione, tappa 1: colonne nuove, tabella setlist_blocks e il
rebuild una tantum che rende nullable setlist_tracks.track_id (varco)."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import ensure_schema
from app.models import Setlist, SetlistBlock, SetlistTrack, Track


def _engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False},
                         poolclass=StaticPool)


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
