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


def test_engine_dei_test_non_punta_al_db_reale():
    """F2 Task 3: l'isolamento non è più uno stopgap per-cartella (sostituzione a
    runtime dell'oggetto `engine`) ma una `DATABASE_URL` su file temporaneo
    impostata da `tests/conftest.py` PRIMA di ogni import di `app.*` — quindi
    prima che `app.db` costruisca l'engine di modulo. Un solo meccanismo, per
    entrambe le suite (vedi anche `tests/test_db_isolation.py`).

    Qui si verifica in più che il sessionmaker condiviso da get_db() e dai job
    service resti legato allo stesso oggetto engine: se non lo fosse, chi
    l'ha già importato altrove finirebbe per usarne un altro.
    """
    import tempfile
    from pathlib import Path

    from app.core.config import DEFAULT_DATABASE_PATH
    from app.db import SessionLocal, engine

    engine_path = Path(engine.url.database).resolve()
    assert engine_path != DEFAULT_DATABASE_PATH.resolve()

    tmp_root = Path(tempfile.gettempdir()).resolve()
    assert tmp_root in engine_path.parents
    assert engine_path.parent.name.startswith("cratory-test-")

    assert SessionLocal.kw["bind"] is engine
