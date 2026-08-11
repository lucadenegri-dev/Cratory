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
    """Stopgap (F2, correzione post Task 1): il conftest di questa cartella
    sostituisce `app.db.engine` con uno costruito su un file temporaneo
    per-sessione (serve un rimpiazzo dell'oggetto engine, non solo dell'env
    var: `tests/conftest.py`, caricato da pytest PRIMA di questo, importa già
    `app.db` col DATABASE_URL del .env). Senza quel rimpiazzo la fixture
    autouse `_fresh_db` farebbe drop_all/create_all sul DB reale dell'utente
    (backend/data/djassistant.db) a ogni test Organize.

    Non si importa qui `tests.organize.conftest` per leggere il suo `_TMP_DB`:
    "tests" non è un package (niente `__init__.py`), quindi un import con
    quel dotted path esegue il modulo una seconda volta sotto un'identità
    diversa da quella usata da pytest, con un secondo mkdtemp — falso
    negativo già osservato in sviluppo. Si verifica quindi solo la forma e
    la provenienza del path, non l'uguaglianza con la variabile del conftest.
    """
    import tempfile
    from pathlib import Path

    from app.core.config import DEFAULT_DATABASE_PATH
    from app.db import SessionLocal, engine

    engine_path = Path(engine.url.database).resolve()
    assert engine_path != DEFAULT_DATABASE_PATH.resolve()

    tmp_root = Path(tempfile.gettempdir()).resolve()
    assert tmp_root in engine_path.parents
    assert engine_path.parent.name.startswith("organize-test-")

    # La sostituzione deve valere anche per il sessionmaker condiviso da
    # get_db() e dai job service: se il bind non è lo stesso oggetto, chi ha
    # già importato SessionLocal altrove continuerebbe a usare l'engine vecchio.
    assert SessionLocal.kw["bind"] is engine
