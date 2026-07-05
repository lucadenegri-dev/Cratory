"""PRAGMA WAL/busy_timeout/foreign_keys attivi sulle connessioni SQLite (fix E1)."""
from sqlalchemy import text

from app.db import _make_engine


def test_sqlite_pragmas_applied(tmp_path):
    db_path = tmp_path / "test.db"
    engine = _make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
