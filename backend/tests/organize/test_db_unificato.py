"""F2: un solo Base, un solo engine. Le tabelle Organize e Cratory convivono
nello stesso metadata e ensure_schema le crea tutte insieme."""

import pytest
from sqlalchemy import create_engine, inspect


def test_modulo_organize_db_non_esiste_piu():
    with pytest.raises(ModuleNotFoundError):
        import app.organize.db  # noqa: F401


def test_tabelle_organize_sullo_stesso_metadata():
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401
    from app.db import Base

    nomi = set(Base.metadata.tables)
    assert {"audio_file", "issue", "dup_group", "plan", "undo_journal", "scan_root"} <= nomi
    assert {"tracks", "playlists", "dj_sets"} <= nomi


def test_ensure_schema_crea_anche_le_tabelle_organize(tmp_path):
    from app.db import ensure_schema

    eng = create_engine(f"sqlite:///{tmp_path / 'unificato.db'}")
    ensure_schema(eng)
    tabelle = set(inspect(eng).get_table_names())
    assert {"tracks", "audio_file", "issue", "plan", "undo_journal"} <= tabelle
