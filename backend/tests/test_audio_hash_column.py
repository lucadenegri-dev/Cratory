"""La colonna audio_hash esiste sia su schema nuovo sia su DB migrato."""
from sqlalchemy import create_engine, inspect, text

from app import models  # noqa: F401 - importa i modelli per registrarli
from app.db import Base, ensure_schema


def test_audio_hash_su_schema_nuovo():
    engine = create_engine("sqlite://")
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("tracks")}
    assert "audio_hash" in cols


def test_audio_hash_su_db_esistente_senza_colonna():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # DROP + CREATE, non RENAME->CREATE->DROP: con le foreign key accese
        # (come in produzione e, da questa suite, anche nei test) il RENAME di
        # `tracks` riscrive le clausole REFERENCES dei figli verso il nome
        # temporaneo, che poi viene droppato — il DB simulato resterebbe con
        # `playlist_tracks` che punta a una tabella inesistente. Il DROP non
        # rinomina nulla: le FK dei figli restano intatte per costruzione.
        conn.execute(text("DROP TABLE tracks"))
        # tabella minima pre-migrazione (senza audio_hash)
        conn.execute(text("CREATE TABLE tracks (id INTEGER PRIMARY KEY, source_type VARCHAR)"))
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("tracks")}
    assert "audio_hash" in cols
