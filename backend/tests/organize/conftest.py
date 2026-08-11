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

from app.db import Base, SessionLocal, engine  # noqa: E402

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
