import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db import Base  # noqa: E402

PROJECT_ROOT = BACKEND_DIR.parent
SAMPLE_XML = PROJECT_ROOT / "export_rekordbox.xml"


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def sample_xml_bytes() -> bytes:
    assert SAMPLE_XML.exists(), f"fixture mancante: {SAMPLE_XML}"
    return SAMPLE_XML.read_bytes()
