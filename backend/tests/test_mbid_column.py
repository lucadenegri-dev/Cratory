"""La colonna mbid (identita' MusicBrainz da fingerprinting) esiste su schema nuovo e migrato."""
from sqlalchemy import create_engine, inspect, text

from app import models  # noqa: F401 - importa i modelli per registrarli
from app.db import Base, ensure_schema


def test_mbid_su_schema_nuovo():
    engine = create_engine("sqlite://")
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("tracks")}
    assert "mbid" in cols


def test_mbid_su_db_esistente_senza_colonna():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tracks RENAME TO _t"))
        # tabella minima pre-migrazione (senza mbid)
        conn.execute(text("CREATE TABLE tracks (id INTEGER PRIMARY KEY, source_type VARCHAR)"))
        conn.execute(text("DROP TABLE _t"))
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("tracks")}
    assert "mbid" in cols
