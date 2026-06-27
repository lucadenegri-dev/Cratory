"""Fixture pytest condivise. Il DB punta a un file temporaneo per-sessione."""

import os
import tempfile

# DEVE precedere qualsiasi import di app.*: settings legge l'env all'import.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="djorg-test-"), "test.db")
os.environ["DJORG_DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

import pytest  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    """Schema pulito prima di ogni test (import dei modelli per registrarli)."""
    import app.models  # noqa: F401

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
from pathlib import Path  # noqa: E402

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
