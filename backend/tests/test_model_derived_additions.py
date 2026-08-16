"""Additions di schema derivate dal modello (niente dict manuale in ensure_schema).

Contratto: `ensure_schema` confronta le colonne live (PRAGMA table_info) con
`Base.metadata` e aggiunge via ALTER TABLE ogni colonna del modello mancante,
con tipo/default derivati dalla `Column` stessa. Vincoli SQLite: NOT NULL solo
se accompagnato da un DEFAULT renderizzabile, altrimenti la colonna si aggiunge
nullable (i default Python callable, es. utcnow, non sono esprimibili in DDL).
Idempotente: seconda passata no-op; un DB fresco resta intatto.

VINCOLO: mai toccare il DB di sviluppo - solo engine in-memory/tmp_path.
"""
from sqlalchemy import create_engine, inspect, text

import app.models  # noqa: F401 - registra i modelli su Base.metadata
from app.db import Base, ensure_schema


def _table_info(engine, table):
    with engine.connect() as conn:
        rows = conn.execute(text(f'PRAGMA table_info("{table}")')).fetchall()
    # name -> (type, notnull, dflt_value)
    return {r[1]: (r[2], r[3], r[4]) for r in rows}


def _schema_dump(engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
        )).fetchall()


def test_colonna_fuori_dal_vecchio_dict_viene_aggiunta():
    """Una colonna del modello assente dal DB viene aggiunta anche se nessuno
    l'ha registrata a mano: `year`/`duration_seconds` non erano nel dict."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tracks DROP COLUMN year"))
        conn.execute(text("ALTER TABLE tracks DROP COLUMN duration_seconds"))
    ensure_schema(engine)
    info = _table_info(engine, "tracks")
    assert "year" in info and info["year"][0] == "INTEGER"
    assert "duration_seconds" in info and info["duration_seconds"][0] == "INTEGER"


def test_tracks_minimale_recupera_tutte_le_colonne_del_modello():
    """DB pre-migrazione ridotto alle colonne minime: dopo ensure_schema tutte
    le colonne del modello esistono, con tipo e default corretti, e i dati
    esistenti sopravvivono."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # DROP + CREATE, non RENAME->CREATE->DROP: vedi la nota in
        # `test_audio_hash_column.py` — col RENAME e le foreign key accese i
        # figli (`playlist_tracks`, `download_queue_items`, …) resterebbero a
        # puntare alla tabella temporanea, poi droppata.
        conn.execute(text("DROP TABLE tracks"))
        conn.execute(text("CREATE TABLE tracks (id INTEGER PRIMARY KEY, source_type VARCHAR)"))
        conn.execute(text("INSERT INTO tracks (id, source_type) VALUES (1, 'spotify')"))
    ensure_schema(engine)

    info = _table_info(engine, "tracks")
    model_cols = set(Base.metadata.tables["tracks"].columns.keys())
    assert model_cols <= set(info)

    # Tipi derivati dal modello (non dal vecchio dict).
    assert info["bpm"][0] == "FLOAT"
    assert info["title"][0] == "VARCHAR"
    assert info["album_art_url"][0] == "TEXT"
    assert info["created_at"][0] == "DATETIME"

    # Default scalare renderizzato in DDL + NOT NULL applicabile (SQLite lo
    # accetta solo insieme a un DEFAULT).
    typ, notnull, dflt = info["status"]
    assert dflt is not None and "imported" in dflt
    assert notnull == 1
    # server_default del modello preservato.
    assert info["archived"][2] is not None

    # NOT NULL con default Python callable (utcnow): non esprimibile in DDL,
    # la colonna viene aggiunta nullable invece di far fallire l'ALTER.
    assert info["created_at"][1] == 0

    with engine.connect() as conn:
        row = conn.execute(text("SELECT source_type, status FROM tracks WHERE id=1")).one()
    assert row[0] == "spotify"
    assert row[1] == "imported"  # backfill dal DEFAULT dell'ADD COLUMN


def test_additions_su_tutte_le_tabelle_del_modello():
    """La derivazione copre ogni tabella, non solo tracks: setlists minimale
    recupera anche le colonne che nel dict manuale non c'erano (es. strategy)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE setlists"))  # come sopra: mai RENAME con le FK accese
        conn.execute(text("CREATE TABLE setlists (id INTEGER PRIMARY KEY, name VARCHAR)"))
    ensure_schema(engine)
    info = _table_info(engine, "setlists")
    model_cols = set(Base.metadata.tables["setlists"].columns.keys())
    assert model_cols <= set(info)
    assert info["strategy"][0] == "VARCHAR"  # mai stata nel dict manuale
    assert info["validation"][0] == "JSON"


def test_seconda_passata_no_op():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tracks DROP COLUMN year"))
    ensure_schema(engine)
    before = _schema_dump(engine)
    ensure_schema(engine)
    assert _schema_dump(engine) == before


def test_db_fresco_intatto():
    """Su un DB creato dal modello corrente le additions non toccano nulla."""
    engine = create_engine("sqlite://")
    ensure_schema(engine)
    before = _schema_dump(engine)
    ensure_schema(engine)
    assert _schema_dump(engine) == before
