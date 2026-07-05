"""PRAGMA WAL/busy_timeout/foreign_keys e indici mancanti sui DB esistenti (fix E1)."""
from sqlalchemy import inspect, text

from app.db import Base, _make_engine, ensure_schema


def test_sqlite_pragmas_applied(tmp_path):
    db_path = tmp_path / "test.db"
    engine = _make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_ensure_schema_creates_missing_indexes(tmp_path):
    db_path = tmp_path / "old.db"
    engine = _make_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    # Simula un DB "vecchio": rimuovi gli indici che create_all avrebbe
    # creato insieme alle tabelle, per isolare cosa fa (o non fa) ensure_schema.
    inspector = inspect(engine)
    with engine.begin() as conn:
        for idx in inspector.get_indexes("tracks"):
            conn.exec_driver_sql(f"DROP INDEX {idx['name']}")

    ensure_schema(engine)

    inspector = inspect(engine)
    index_cols = {tuple(idx["column_names"]) for idx in inspector.get_indexes("tracks")}
    assert ("archived",) in index_cols
    assert ("audio_hash",) in index_cols
    assert ("has_local_file",) in index_cols
    assert ("bpm",) in index_cols
