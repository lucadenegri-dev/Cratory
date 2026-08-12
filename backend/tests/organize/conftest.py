"""Fixture pytest di Organize.

Il DB temporaneo è impostato dal conftest radice (un solo engine da F2): qui
resta solo lo schema pulito per test. Le fixture autouse del conftest radice
(reset runtime_settings, no-LLM, no-scan, reset job state) restano attive e
sono innocue per questi test.
"""

from pathlib import Path

import pytest

from app.db import Base, SessionLocal, engine

_ORGANIZE_TESTS = Path(__file__).resolve().parent

# ScanRoot canoniche seminate da _fresh_db (vedi sotto). Contratto condiviso:
# i test che seminano una propria ScanRoot devono usare id >= SCAN_ROOT_NEXT_ID
# o incappano in "UNIQUE constraint failed: scan_root.id". Un solo posto per
# questa regola invece dei ~13 commenti che la ripetevano sparsi nei test.
SEEDED_SCAN_ROOT_IDS = (1, 2)
SCAN_ROOT_NEXT_ID = max(SEEDED_SCAN_ROOT_IDS) + 1


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
    """Schema pulito prima di ogni test (import dei modelli per registrarli).

    Semina anche le due ScanRoot canoniche SEEDED_SCAN_ROOT_IDS (id 1 e 2):
    F2: l'engine unificato accende PRAGMA foreign_keys=ON (app/db.py), che il
    vecchio engine di Organize non aveva. Le fixture creano AudioFile con
    root_id 1/2 senza inserire la ScanRoot: qui le seminiamo una volta, così
    il vincolo è soddisfatto senza toccare 71 test.
    F3b lascia scan_root come schema morto (audio_file.root_id resta NOT
    NULL con FK viva): questa semina resta necessaria, non se ne va.

    Regola per chi scrive nuovi test: una ScanRoot propria va creata con
    id >= SCAN_ROOT_NEXT_ID (id 1 e 2 sono occupati da questa semina), o la
    UNIQUE constraint su ScanRoot.id fallisce.
    """
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    from app.organize.models import ScanRoot

    with SessionLocal() as seed:
        seed.add_all([
            ScanRoot(id=1, path="/inbox"),
            ScanRoot(id=2, path="/library"),
        ])
        seed.commit()

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
