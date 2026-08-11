"""Fixture pytest di Organize. Il DB punta a un file temporaneo per-sessione.

Nota: il conftest di livello superiore (backend/tests/conftest.py) resta attivo
anche qui — le sue fixture autouse (reset runtime_settings, no-LLM, no-scan,
reset job state) toccano solo moduli Cratory e sono innocue per questi test.
"""

import os
import tempfile

# DEVE precedere qualsiasi import di app.organize.*: le settings leggono l'env
# al momento dell'import del modulo.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="organize-test-"), "test.db")
os.environ["DJORG_DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

import app.db as _cratory_db  # noqa: E402
from app.db import Base, SessionLocal  # noqa: E402

# Stopgap del Task 1 (F2): da quando questo conftest importa `engine` da
# `app.db` invece che dal defunto `app.organize.db`, DJORG_DATABASE_URL sopra
# non basta più a isolare l'engine — e impostare anche DATABASE_URL qui non
# risolverebbe nulla: il conftest radice (`tests/conftest.py`), che pytest
# carica PRIMA di questo perché vive nella directory padre, fa già
# `from app.db import Base` in testa al file, quindi `app.db.engine` è già
# stato costruito dal DATABASE_URL del .env (path RELATIVO, risolto contro la
# BACKEND_DIR di chi esegue pytest) nel momento in cui questo modulo viene
# eseguito. La fixture _fresh_db qui sotto fa Base.metadata.drop_all(engine)
# prima di ogni test: senza questo rimpiazzo puntava al DB reale dell'utente.
# Va quindi sostituito l'oggetto engine stesso (non solo l'env var che lo
# genera) e ripropagato a SessionLocal: è un sessionmaker condiviso (get_db()
# e tutti i job service lo importano come stesso oggetto), quindi
# `.configure()` lo fa vedere anche a chi l'ha già importato prima d'ora.
#
# Guardia di re-entrancy: "tests" non è un package (niente `__init__.py`),
# mentre "tests/organize" lo è — quindi pytest importa questo file come
# `organize.conftest`, ma qualunque test che scriva
# `from tests.organize.conftest import ...` (es. per `make_audio_file`) lo fa
# risolvere come un modulo DIVERSO (`tests.organize.conftest`) e Python lo
# RIESEGUE da capo. Prima di questa guardia la seconda esecuzione creava un
# secondo file temporaneo e un secondo engine, sovrascrivendo di nuovo
# `app.db.engine`/`SessionLocal`: la fixture `_fresh_db` (legata alla prima
# esecuzione) continuava a fare drop_all/create_all sul PRIMO file, mentre il
# codice applicativo interrogava ormai il secondo, privo di schema
# ("no such table"). Se `app.db.engine` punta già a un file dentro una
# directory "organize-test-*" (cioè un'esecuzione precedente di *questo*
# file l'ha già isolato) lo riusiamo invece di sostituirlo di nuovo.
_existing_db = Path(_cratory_db.engine.url.database or "")
if _existing_db.parent.name.startswith("organize-test-"):
    engine = _cratory_db.engine
else:
    engine = _cratory_db._make_engine(f"sqlite:///{_TMP_DB}")
    _cratory_db.engine = engine
    SessionLocal.configure(bind=engine)
# Il Task 3 sposta questo isolamento nel conftest radice — dove può agire
# PRIMA che app.db venga importato la prima volta — e rimuove
# DJORG_DATABASE_URL: non toccare quella riga qui.

_ORGANIZE_TESTS = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    """Strictness sui warning ristretta ai test Organize finché la suite Cratory
    non è ripulita (vedi spec F1). Rimuovere quando `filterwarnings = error`
    varrà per tutta la suite.

    ATTENZIONE: questo hook, pur vivendo in un conftest di sottocartella, riceve
    da pytest l'elenco COMPLETO degli item della sessione — anche quelli di
    Cratory. Senza il filtro sul path la strictness si applicherebbe a tutta la
    suite, ed è esattamente ciò che questa funzione deve evitare."""
    for item in items:
        if _ORGANIZE_TESTS in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.filterwarnings("error"))


@pytest.fixture(autouse=True)
def _fresh_db():
    """Schema pulito prima di ogni test (import dei modelli per registrarli)."""
    import app.organize.models  # noqa: F401

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


import shutil  # noqa: E402

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_path():
    def _path(fmt: str) -> str:
        return str(_FIXTURES / f"silence.{fmt}")

    return _path


@pytest.fixture
def copy_fixture():
    def _copy(fmt: str, dest) -> str:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_FIXTURES / f"silence.{fmt}", dest)
        return str(dest)

    return _copy


from app.organize.models import AudioFile  # noqa: E402


def make_audio_file(id: int, **overrides) -> AudioFile:
    """AudioFile NON persistito con default sensati, per i test puri.
    I service puri leggono solo gli attributi; l'id va passato esplicito."""
    defaults = dict(
        root_id=1, path=f"/music/{id}.mp3", ext="mp3", size_bytes=1000,
        content_hash=f"hash{id}", hash_method="file", status="present",
        artist=None, title=None, album=None, album_artist=None, genre=None,
        year=None, label=None, track_no=None, comment=None, isrc=None, has_cover=False,
        bitrate=None, sample_rate=None, channels=None, duration_s=None, scan_error=None,
    )
    defaults.update(overrides)
    return AudioFile(id=id, **defaults)
