# DjOrganizer Chunk 1 — Fondazione + Scanner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend avviabile che scansiona cartelle di musica, legge tag e info tecniche via mutagen, calcola un `content_hash` stabile al retag, e persiste tutto in SQLite — esposto via endpoint per gestire le radici e lanciare/seguire lo scan come job.

**Architecture:** Layering stile Cratory (`core/`, `db`, `models`, `schemas`, `integrations/`, `services/`, `routers/`). Il motore (`services/scanner.py`) è una funzione deterministica con callback `on_progress`, testabile senza thread; un job shell (`services/scan_job.py`, port da `enrichment_job.py` di Cratory) lo esegue in background con stato in memoria. Router sottili. SQLite con `create_all` + `ensure_schema` (niente Alembic).

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Pydantic v2 + pydantic-settings, mutagen, pytest, httpx (TestClient). `ffmpeg` solo per generare i fixture audio.

**Spec di riferimento:** [docs/superpowers/specs/2026-06-27-djorganizer-chunk1-scanner-design.md](../specs/2026-06-27-djorganizer-chunk1-scanner-design.md)

## Global Constraints

- **SQLAlchemy 2.0**, niente Alembic: schema via `Base.metadata.create_all()` + `ensure_schema()`.
- **Output validati con Pydantic** prima di esporre o eseguire.
- **Motore deterministico**, nessuna AI nel percorso critico.
- **Router sottili**: la logica sta nei `services/`.
- **Nessuna mutazione dei file audio** in questo chunk: solo lettura FS + scrittura DB.
- **`content_hash`**: stream-audio per `.mp3`/`.flac` (`hash_method="stream"`), full-file per gli altri (`hash_method="file"`); algoritmo **BLAKE2b**, esadecimale.
- **Formati audio (`AUDIO_EXTS`)**: `.mp3 .flac .wav .aiff .aif .m4a .aac` (case-insensitive).
- **`status`** di `audio_file` in questo chunk: `present` | `missing` (no `quarantined`).
- Comandi backend: `cd backend && source .venv/bin/activate`, `python -m pytest tests`, `uvicorn app.main:app --reload --port 8000`.
- Commit message in italiano, prefisso conventional (`feat:`, `test:`, `chore:`), con footer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```text
backend/
  requirements.txt
  app/
    __init__.py
    main.py                  # Task 7: FastAPI app, lifespan ensure_schema, include routers
    core/
      __init__.py
      config.py              # Task 1: pydantic-settings (database_url, audio_exts)
    db.py                    # Task 1: Base, engine, SessionLocal, ensure_schema, get_db
    models.py                # Task 1: ScanRoot, AudioFile, utcnow
    schemas.py               # Task 5/7: ScanSummary, ScanRootCreate/Read
    integrations/
      __init__.py
      content_hash.py        # Task 3: compute(path, ext) -> (hash|None, method)
      tagio.py               # Task 4: read_info, read_tags, TagReadError, TechInfo, TagData
    services/
      __init__.py
      scanner.py             # Task 5/6: scan(db, roots, on_progress) -> ScanSummary
      scan_job.py            # Task 8: start_job, job_state, is_running
    routers/
      __init__.py
      sources.py             # Task 7: CRUD radici + conteggi
      scan.py                # Task 8: POST /api/scan, GET /api/scan/status
  tests/
    __init__.py
    conftest.py              # Task 1/2: DB temp + fixture audio helpers
    fixtures/                # Task 2: silence.{mp3,flac,wav,aiff,m4a}
    test_content_hash.py     # Task 3
    test_tagio.py            # Task 4
    test_scanner.py          # Task 5/6
    test_scan_job.py         # Task 8
    test_api.py              # Task 7/8
```

---

## Task 1: Fondazione — config, db, modelli, schema

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/integrations/__init__.py`, `backend/app/services/__init__.py`, `backend/app/routers/__init__.py`, `backend/tests/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_schema.py`

**Interfaces:**
- Produces:
  - `app.core.config.settings` con `database_url: str`, `audio_exts: tuple[str, ...]`.
  - `app.db`: `Base`, `engine`, `SessionLocal`, `ensure_schema(eng=None) -> None`, `get_db()`.
  - `app.models`: `ScanRoot`, `AudioFile`, `utcnow() -> datetime`.
  - `tests/conftest.py`: fixture autouse `_fresh_db`, fixture `db` (Session).

- [ ] **Step 1: Crea lo scheletro di cartelle e i file `__init__.py`**

```bash
mkdir -p backend/app/core backend/app/integrations backend/app/services backend/app/routers backend/tests/fixtures
touch backend/app/__init__.py backend/app/core/__init__.py backend/app/integrations/__init__.py \
      backend/app/services/__init__.py backend/app/routers/__init__.py backend/tests/__init__.py
```

- [ ] **Step 2: Scrivi `backend/requirements.txt`**

```text
fastapi
uvicorn[standard]
sqlalchemy>=2.0
pydantic>=2
pydantic-settings
mutagen
pytest
httpx
```

- [ ] **Step 3: Crea il venv e installa**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 4: Scrivi `backend/app/core/config.py`**

```python
"""Configurazione applicativa (pydantic-settings). App locale mono-utente."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DJORG_", env_file=".env", extra="ignore")

    # DB SQLite locale (cartella git-ignored).
    database_url: str = "sqlite:///./data/djorganizer.db"
    # Estensioni audio riconosciute dallo Scanner (minuscole, col punto).
    audio_exts: tuple[str, ...] = (".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac")


settings = Settings()
```

- [ ] **Step 5: Scrivi `backend/app/db.py`**

```python
"""Engine, sessione e creazione schema. Niente Alembic: app locale."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args=connect_args)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ensure_schema(eng=None) -> None:
    """create_all sui modelli. L'import registra le tabelle su Base.metadata."""
    import app.models  # noqa: F401

    Base.metadata.create_all(eng or engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 6: Scrivi `backend/app/models.py`**

```python
"""Modelli SQLAlchemy del chunk 1: radici di scan e file audio."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScanRoot(Base):
    __tablename__ = "scan_root"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String, unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime)

    files: Mapped[list["AudioFile"]] = relationship(
        back_populates="root", cascade="all, delete-orphan"
    )


class AudioFile(Base):
    __tablename__ = "audio_file"
    __table_args__ = (UniqueConstraint("root_id", "path", name="uq_audio_root_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    root_id: Mapped[int] = mapped_column(ForeignKey("scan_root.id"), index=True)
    path: Mapped[str] = mapped_column(String, index=True)
    ext: Mapped[str] = mapped_column(String)
    bitrate: Mapped[int | None] = mapped_column(Integer)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String, index=True)
    hash_method: Mapped[str] = mapped_column(String)
    artist: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    album: Mapped[str | None] = mapped_column(String)
    album_artist: Mapped[str | None] = mapped_column(String)
    genre: Mapped[str | None] = mapped_column(String)
    year: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String)
    track_no: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    has_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="present", index=True)
    scan_error: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_scanned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    root: Mapped["ScanRoot"] = relationship(back_populates="files")
```

- [ ] **Step 7: Scrivi `backend/tests/conftest.py` (infrastruttura DB temporanea)**

```python
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
```

- [ ] **Step 8: Scrivi il test che fallisce — `backend/tests/test_schema.py`**

```python
from sqlalchemy import inspect

from app.db import engine
from app.models import ScanRoot


def test_schema_has_expected_tables_and_columns():
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"scan_root", "audio_file"} <= tables
    cols = {c["name"] for c in insp.get_columns("audio_file")}
    assert {"content_hash", "hash_method", "scan_error", "status"} <= cols


def test_scan_root_roundtrip(db):
    db.add(ScanRoot(path="/music", label="Main"))
    db.commit()
    got = db.query(ScanRoot).one()
    assert got.path == "/music" and got.label == "Main"
```

- [ ] **Step 9: Esegui i test e verifica che PASSINO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_schema.py -v`
Expected: 2 passed. (Lo schema è creato dalla fixture autouse `_fresh_db`.)

- [ ] **Step 10: Commit**

```bash
git add backend/requirements.txt backend/app backend/tests
git commit -m "feat: scaffold backend + modelli scan_root/audio_file

Config pydantic-settings, db (Base/engine/ensure_schema/get_db) stile Cratory,
modelli ScanRoot e AudioFile (con hash_method e scan_error), infrastruttura
pytest con DB temporaneo per-sessione.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Fixture audio reali

**Files:**
- Create: `backend/tests/fixtures/silence.mp3`, `.flac`, `.wav`, `.aiff`, `.m4a`
- Modify: `backend/tests/conftest.py` (aggiungi gli helper `fixture_path` e `copy_fixture`)
- Test: `backend/tests/test_fixtures.py`

**Interfaces:**
- Consumes: nessuno.
- Produces: fixture `fixture_path(fmt: str) -> str` (path al file `silence.<fmt>`), `copy_fixture(fmt: str, dest) -> str` (copia il fixture in `dest`, ritorna il path).

- [ ] **Step 1: Verifica ffmpeg (installa se manca)**

Run: `ffmpeg -version | head -1`
Se manca: `brew install ffmpeg`

- [ ] **Step 2: Genera i micro-file (1s di silenzio stereo 44.1kHz)**

```bash
cd backend/tests/fixtures
for fmt in mp3 flac wav aiff m4a; do
  ffmpeg -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t 1 "silence.$fmt"
done
ls -la
```
Expected: cinque file `silence.*` di pochi KB.

- [ ] **Step 3: Aggiungi gli helper a `backend/tests/conftest.py`**

Aggiungi in fondo al file:

```python
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
```

- [ ] **Step 4: Scrivi il test che fallisce — `backend/tests/test_fixtures.py`**

```python
import pytest

from mutagen import File as MutagenFile


@pytest.mark.parametrize("fmt", ["mp3", "flac", "wav", "aiff", "m4a"])
def test_fixture_is_readable_audio(fixture_path, fmt):
    mf = MutagenFile(fixture_path(fmt))
    assert mf is not None
    assert 0.5 < mf.info.length < 1.5
```

- [ ] **Step 5: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_fixtures.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/fixtures backend/tests/conftest.py backend/tests/test_fixtures.py
git commit -m "test: fixture audio reali (1s silenzio, 5 formati) + helper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `content_hash` — hash stream-audio

**Files:**
- Create: `backend/app/integrations/content_hash.py`
- Test: `backend/tests/test_content_hash.py`

**Interfaces:**
- Consumes: fixture audio (Task 2).
- Produces: `app.integrations.content_hash.compute(path: str, ext: str) -> tuple[str | None, str]` — ritorna `(hash_esadecimale | None, method)` con `method ∈ {"stream", "file"}`. `None` solo se i byte sono illeggibili.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_content_hash.py`**

```python
import shutil

from mutagen.flac import FLAC
from mutagen.mp3 import EasyMP3

from app.integrations import content_hash


def test_two_identical_copies_same_hash(copy_fixture, tmp_path):
    a = copy_fixture("flac", tmp_path / "a.flac")
    b = copy_fixture("flac", tmp_path / "b.flac")
    ha, ma = content_hash.compute(a, ".flac")
    hb, mb = content_hash.compute(b, ".flac")
    assert ha == hb and ma == mb == "stream" and ha is not None


def test_mp3_hash_stable_after_retag(copy_fixture, tmp_path):
    f = copy_fixture("mp3", tmp_path / "a.mp3")
    h1, m1 = content_hash.compute(f, ".mp3")
    audio = EasyMP3(f)
    if audio.tags is None:
        audio.add_tags()
    audio["artist"] = "Pinco Pallino"
    audio["title"] = "Una traccia con un titolo lungo"
    audio.save()
    h2, m2 = content_hash.compute(f, ".mp3")
    assert m1 == "stream" and h1 == h2


def test_flac_hash_stable_after_retag(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    h1, m1 = content_hash.compute(f, ".flac")
    audio = FLAC(f)
    audio["artist"] = "Pinco Pallino"
    audio["title"] = "Titolo"
    audio.save()
    h2, m2 = content_hash.compute(f, ".flac")
    assert m1 == "stream" and h1 == h2


def test_m4a_uses_file_method(copy_fixture, tmp_path):
    f = copy_fixture("m4a", tmp_path / "a.m4a")
    h, m = content_hash.compute(f, ".m4a")
    assert m == "file" and h is not None


def test_unreadable_returns_none(tmp_path):
    h, m = content_hash.compute(str(tmp_path / "nope.mp3"), ".mp3")
    assert h is None
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_content_hash.py -v`
Expected: errori di import (`content_hash` non ha `compute`).

- [ ] **Step 3: Implementa `backend/app/integrations/content_hash.py`**

```python
"""Identità audio: hash dello stream (non dei tag), stabile al retag.

mp3/flac: si salta il contenitore di metadata e si hasha l'audio (method='stream').
Altri formati: hash full-file (method='file'), con la nota della limitazione.
"""

import hashlib
import logging

logger = logging.getLogger(__name__)


def _synchsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _mp3_range(data: bytes) -> tuple[int, int]:
    """Intervallo [start, end) dei frame MPEG, saltando ID3v2 in testa e ID3v1 in coda."""
    start = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        start = 10 + _synchsafe(data[6:10])
        if data[5] & 0x10:  # footer ID3v2 presente
            start += 10
    end = len(data)
    if end - start >= 128 and data[end - 128 : end - 125] == b"TAG":
        end -= 128
    return start, end


def _flac_range(data: bytes) -> tuple[int, int]:
    """Intervallo dei frame audio, saltando i metadata block dopo il marker fLaC."""
    if data[:4] != b"fLaC":
        return 0, len(data)
    i = 4
    while i + 4 <= len(data):
        header = data[i]
        length = int.from_bytes(data[i + 1 : i + 4], "big")
        i += 4 + length
        if header & 0x80:  # ultimo metadata block
            break
    return i, len(data)


_STREAM = {".mp3": _mp3_range, ".flac": _flac_range}


def compute(path: str, ext: str) -> tuple[str | None, str]:
    ext = ext.lower()
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None, "file"
    ranger = _STREAM.get(ext)
    if ranger is not None:
        start, end = ranger(data)
        return hashlib.blake2b(data[start:end]).hexdigest(), "stream"
    logger.debug("content_hash full-file (no stream-strip per %s): %s", ext, path)
    return hashlib.blake2b(data).hexdigest(), "file"
```

- [ ] **Step 4: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_content_hash.py -v`
Expected: 5 passed. (Se `test_mp3_hash_stable_after_retag` fallisce, controlla che `_mp3_range` salti l'ID3v2 usando la dimensione synchsafe.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/content_hash.py backend/tests/test_content_hash.py
git commit -m "feat: content_hash stream-audio (mp3/flac) + fallback full-file

BLAKE2b sui frame MPEG/FLAC saltando i metadata, cosi' il retag non cambia
l'identita' del file. Fallback full-file per gli altri formati (hash_method).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `tagio` — wrapper mutagen

**Files:**
- Create: `backend/app/integrations/tagio.py`
- Test: `backend/tests/test_tagio.py`

**Interfaces:**
- Consumes: fixture audio (Task 2).
- Produces:
  - `app.integrations.tagio.TagReadError` (Exception).
  - `app.integrations.tagio.TechInfo` (dataclass: `bitrate, sample_rate, channels, duration_s`).
  - `app.integrations.tagio.TagData` (dataclass: `artist, title, album, album_artist, genre, year, label, track_no, comment, has_cover`).
  - `read_info(path: str) -> TechInfo`, `read_tags(path: str) -> TagData`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_tagio.py`**

```python
import pytest
from mutagen.flac import FLAC

from app.integrations import tagio


def test_read_info_flac(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    info = tagio.read_info(f)
    assert info.sample_rate == 44100
    assert info.channels == 2
    assert 0.5 < info.duration_s < 1.5


def test_read_tags_roundtrip(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    audio = FLAC(f)
    audio["artist"] = "Pinco Pallino"
    audio["title"] = "Titolo"
    audio["date"] = "2020"
    audio["tracknumber"] = "3"
    audio.save()
    tags = tagio.read_tags(f)
    assert tags.artist == "Pinco Pallino"
    assert tags.title == "Titolo"
    assert tags.year == 2020
    assert tags.track_no == 3


def test_empty_fixture_has_no_required_tags(copy_fixture, tmp_path):
    f = copy_fixture("wav", tmp_path / "a.wav")
    tags = tagio.read_tags(f)
    assert tags.artist is None and tags.title is None


def test_corrupt_file_raises(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"questo non e' audio")
    with pytest.raises(tagio.TagReadError):
        tagio.read_info(str(bad))
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tagio.py -v`
Expected: errori di import (`tagio` incompleto).

- [ ] **Step 3: Implementa `backend/app/integrations/tagio.py`**

```python
"""Lettura tag e info tecniche via mutagen. Nessuna scrittura in questo chunk."""

import re
from dataclasses import dataclass

from mutagen import File as MutagenFile
from mutagen import MutagenError


class TagReadError(Exception):
    """Il file non è leggibile/riconoscibile da mutagen."""


@dataclass
class TechInfo:
    bitrate: int | None
    sample_rate: int | None
    channels: int | None
    duration_s: float | None


@dataclass
class TagData:
    artist: str | None
    title: str | None
    album: str | None
    album_artist: str | None
    genre: str | None
    year: int | None
    label: str | None
    track_no: int | None
    comment: str | None
    has_cover: bool


def _first(tags, key):
    if not tags:
        return None
    value = tags.get(key)
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value is not None else None


def _parse_year(value):
    if not value:
        return None
    match = re.search(r"\d{4}", str(value))
    return int(match.group()) if match else None


def _parse_track(value):
    if not value:
        return None
    head = str(value).split("/")[0].strip()
    try:
        return int(head)
    except ValueError:
        return None


def _detect_cover(raw) -> bool:
    if raw is None:
        return False
    if getattr(raw, "pictures", None):  # FLAC
        return True
    tags = getattr(raw, "tags", None)
    if tags is None:
        return False
    if hasattr(tags, "getall") and tags.getall("APIC"):  # ID3 (mp3)
        return True
    try:
        if "covr" in tags:  # MP4 (m4a)
            return True
    except TypeError:
        pass
    return False


def read_info(path: str) -> TechInfo:
    try:
        mf = MutagenFile(path)
    except MutagenError as exc:
        raise TagReadError(str(exc)) from exc
    if mf is None or getattr(mf, "info", None) is None:
        raise TagReadError(f"formato non riconosciuto: {path}")
    info = mf.info
    return TechInfo(
        bitrate=getattr(info, "bitrate", None),
        sample_rate=getattr(info, "sample_rate", None),
        channels=getattr(info, "channels", None),
        duration_s=getattr(info, "length", None),
    )


def read_tags(path: str) -> TagData:
    try:
        easy = MutagenFile(path, easy=True)
        raw = MutagenFile(path)
    except MutagenError as exc:
        raise TagReadError(str(exc)) from exc
    if easy is None:
        raise TagReadError(f"formato non riconosciuto: {path}")
    tags = easy.tags or {}
    return TagData(
        artist=_first(tags, "artist"),
        title=_first(tags, "title"),
        album=_first(tags, "album"),
        album_artist=_first(tags, "albumartist"),
        genre=_first(tags, "genre"),
        year=_parse_year(_first(tags, "date")),
        label=_first(tags, "organization") or _first(tags, "label"),
        track_no=_parse_track(_first(tags, "tracknumber")),
        comment=_first(tags, "comment"),
        has_cover=_detect_cover(raw),
    )
```

- [ ] **Step 4: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tagio.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/tagio.py backend/tests/test_tagio.py
git commit -m "feat: tagio, wrapper mutagen per tag e info tecniche

read_info/read_tags con mapping uniforme (easy mode + fallback), rilevazione
cover, TagReadError per i file illeggibili.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Scanner — scan base e upsert

**Files:**
- Create: `backend/app/services/scanner.py`
- Create: `backend/app/schemas.py`
- Test: `backend/tests/test_scanner.py`

**Interfaces:**
- Consumes: `settings.audio_exts`, `app.models` (ScanRoot, AudioFile, utcnow), `tagio`, `content_hash`.
- Produces:
  - `app.schemas.ScanSummary` (Pydantic): `roots: list[int]`, `found, inserted, updated, moved, missing, errors: int`, `started_at, finished_at: datetime | None`.
  - `app.services.scanner.scan(db, roots: list[ScanRoot], on_progress=None) -> ScanSummary`.
  - `app.services.scanner._iter_audio_files(root_path) -> Iterator[tuple[str, str]]`, `_scan_file_fields(path, ext) -> dict`.

- [ ] **Step 1: Scrivi `backend/app/schemas.py` (ScanSummary)**

```python
"""Schemi Pydantic I/O validato."""

from datetime import datetime

from pydantic import BaseModel


class ScanSummary(BaseModel):
    roots: list[int]
    found: int = 0
    inserted: int = 0
    updated: int = 0
    moved: int = 0
    missing: int = 0
    errors: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

- [ ] **Step 2: Scrivi i test che falliscono — `backend/tests/test_scanner.py`**

```python
from sqlalchemy import select

from app.models import AudioFile, ScanRoot
from app.services.scanner import scan


def _make_root(db, copy_fixture, tmp_path, files):
    root_dir = tmp_path / "lib"
    for name, fmt in files:
        copy_fixture(fmt, root_dir / name)
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    return root


def test_scan_inserts_rows(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3"), ("b.flac", "flac")])
    summary = scan(db, [root])
    assert summary.found == 2 and summary.inserted == 2 and summary.updated == 0
    rows = db.scalars(select(AudioFile)).all()
    assert {r.ext for r in rows} == {"mp3", "flac"}
    assert all(r.status == "present" and r.content_hash for r in rows)


def test_progress_callback_called(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3")])
    seen = []
    scan(db, [root], on_progress=lambda p, t, ph: seen.append((p, t, ph)))
    assert seen[-1] == (1, 1, "scanning")


def test_rescan_is_idempotent(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3")])
    scan(db, [root])
    summary = scan(db, [root])
    assert summary.inserted == 0 and summary.updated == 1
    assert db.scalar(select(AudioFile)) is not None
    assert len(db.scalars(select(AudioFile)).all()) == 1


def test_unreadable_file_recorded_not_crash(db, copy_fixture, tmp_path):
    root_dir = tmp_path / "lib"
    copy_fixture("mp3", root_dir / "ok.mp3")
    (root_dir / "broken.mp3").write_bytes(b"non audio")
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    summary = scan(db, [root])
    assert summary.found == 2 and summary.errors == 1
    broken = db.scalar(select(AudioFile).where(AudioFile.path.like("%broken%")))
    assert broken.scan_error is not None
```

- [ ] **Step 3: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_scanner.py -v`
Expected: ImportError su `scan`.

- [ ] **Step 4: Implementa `backend/app/services/scanner.py`**

```python
"""Motore Scanner deterministico: walk del FS, lettura, upsert in DB."""

import os
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations import content_hash, tagio
from app.models import AudioFile, ScanRoot, utcnow
from app.schemas import ScanSummary

_TAG_FIELDS = (
    "bitrate", "sample_rate", "channels", "duration_s", "artist", "title", "album",
    "album_artist", "genre", "year", "label", "track_no", "comment", "has_cover",
)


def _iter_audio_files(root_path: str) -> Iterator[tuple[str, str]]:
    for dirpath, _dirs, names in os.walk(root_path):
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext in settings.audio_exts:
                yield os.path.join(dirpath, name), ext


def _scan_file_fields(path: str, ext: str) -> dict:
    """Campi aggiornabili di AudioFile per un file, con errori isolati per-file."""
    h, method = content_hash.compute(path, ext)
    fields = {
        "ext": ext.lstrip("."),
        "size_bytes": os.path.getsize(path),
        "content_hash": h,
        "hash_method": method,
        "scan_error": None,
        "has_cover": False,
    }
    for key in _TAG_FIELDS:
        fields.setdefault(key, None)
    try:
        info = tagio.read_info(path)
        tags = tagio.read_tags(path)
    except tagio.TagReadError as exc:
        fields["scan_error"] = str(exc)
        return fields
    fields.update(
        bitrate=info.bitrate, sample_rate=info.sample_rate,
        channels=info.channels, duration_s=info.duration_s,
        artist=tags.artist, title=tags.title, album=tags.album,
        album_artist=tags.album_artist, genre=tags.genre, year=tags.year,
        label=tags.label, track_no=tags.track_no, comment=tags.comment,
        has_cover=tags.has_cover,
    )
    return fields


def scan(db: Session, roots: list[ScanRoot], on_progress=None) -> ScanSummary:
    summary = ScanSummary(roots=[r.id for r in roots], started_at=utcnow())
    work = [(root, p, e) for root in roots for p, e in _iter_audio_files(root.path)]
    summary.found = len(work)
    for index, (root, path, ext) in enumerate(work):
        fields = _scan_file_fields(path, ext)
        existing = db.scalar(
            select(AudioFile).where(AudioFile.root_id == root.id, AudioFile.path == path)
        )
        if existing is None:
            db.add(AudioFile(
                root_id=root.id, path=path, status="present",
                first_seen_at=utcnow(), last_scanned_at=utcnow(), **fields,
            ))
            summary.inserted += 1
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.status = "present"
            existing.last_scanned_at = utcnow()
            summary.updated += 1
        if fields["scan_error"]:
            summary.errors += 1
        if on_progress is not None:
            on_progress(index + 1, summary.found, "scanning")
    for root in roots:
        root.last_scanned_at = utcnow()
    db.commit()
    summary.finished_at = utcnow()
    return summary
```

- [ ] **Step 5: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_scanner.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/scanner.py backend/app/schemas.py backend/tests/test_scanner.py
git commit -m "feat: motore Scanner — walk, lettura, upsert + ScanSummary

Scan deterministico con on_progress; upsert per (root_id, path); file
illeggibili registrati in scan_error senza interrompere lo scan.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Scanner — riconciliazione (missing + moved)

**Files:**
- Modify: `backend/app/services/scanner.py` (riscrivi `scan`, aggiungi `_reconcile`)
- Test: `backend/tests/test_scanner.py` (aggiungi i casi missing/moved)

**Interfaces:**
- Consumes: Task 5.
- Produces: `scan` aggiornata (popola `summary.missing` e `summary.moved`); `app.services.scanner._reconcile(db, roots, seen_by_root, new_inserts, summary) -> None`.

- [ ] **Step 1: Aggiungi i test che falliscono in `backend/tests/test_scanner.py`**

```python
def test_rescan_marks_missing(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.flac", "flac")])
    scan(db, [root])
    (tmp_path / "lib" / "a.flac").unlink()
    summary = scan(db, [root])
    assert summary.missing == 1 and summary.inserted == 0
    row = db.scalar(select(AudioFile))
    assert row.status == "missing"


def test_rescan_reconciles_move(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.flac", "flac")])
    scan(db, [root])
    original = db.scalar(select(AudioFile))
    original_id, first_seen = original.id, original.first_seen_at
    (tmp_path / "lib" / "a.flac").rename(tmp_path / "lib" / "b.flac")
    summary = scan(db, [root])
    assert summary.moved == 1 and summary.missing == 0 and summary.inserted == 0
    db.expire_all()
    rows = db.scalars(select(AudioFile)).all()
    assert len(rows) == 1
    assert rows[0].id == original_id
    assert rows[0].path.endswith("b.flac")
    assert rows[0].first_seen_at == first_seen
    assert rows[0].status == "present"
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_scanner.py -k "missing or move" -v`
Expected: `test_rescan_marks_missing` e `test_rescan_reconciles_move` falliscono (missing/moved restano 0).

- [ ] **Step 3: Riscrivi `scan` e aggiungi `_reconcile` in `backend/app/services/scanner.py`**

Sostituisci la funzione `scan` con questa versione e aggiungi `_reconcile` subito dopo:

```python
def scan(db: Session, roots: list[ScanRoot], on_progress=None) -> ScanSummary:
    summary = ScanSummary(roots=[r.id for r in roots], started_at=utcnow())
    work = [(root, p, e) for root in roots for p, e in _iter_audio_files(root.path)]
    summary.found = len(work)
    seen_by_root: dict[int, set[str]] = {r.id: set() for r in roots}
    new_inserts: list[AudioFile] = []
    for index, (root, path, ext) in enumerate(work):
        seen_by_root[root.id].add(path)
        fields = _scan_file_fields(path, ext)
        existing = db.scalar(
            select(AudioFile).where(AudioFile.root_id == root.id, AudioFile.path == path)
        )
        if existing is None:
            row = AudioFile(
                root_id=root.id, path=path, status="present",
                first_seen_at=utcnow(), last_scanned_at=utcnow(), **fields,
            )
            db.add(row)
            new_inserts.append(row)
            summary.inserted += 1
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.status = "present"
            existing.last_scanned_at = utcnow()
            summary.updated += 1
        if fields["scan_error"]:
            summary.errors += 1
        if on_progress is not None:
            on_progress(index + 1, summary.found, "scanning")
    db.flush()  # assegna gli id ai nuovi insert
    _reconcile(db, roots, seen_by_root, new_inserts, summary)
    for root in roots:
        root.last_scanned_at = utcnow()
    db.commit()
    summary.finished_at = utcnow()
    return summary


def _reconcile(db, roots, seen_by_root, new_inserts, summary) -> None:
    """Marca i file spariti come missing; se l'hash combacia con un nuovo insert,
    li tratta come spostamento (aggiorna il path della riga esistente)."""
    inserts_by_key: dict[tuple[int, str], AudioFile] = {}
    for row in new_inserts:
        if row.content_hash:
            inserts_by_key.setdefault((row.root_id, row.content_hash), row)
    for root in roots:
        seen = seen_by_root[root.id]
        all_rows = db.scalars(select(AudioFile).where(AudioFile.root_id == root.id)).all()
        gone = [r for r in all_rows if r.path not in seen and r.status != "missing"]
        for row in gone:
            key = (root.id, row.content_hash) if row.content_hash else None
            cand = inserts_by_key.get(key) if key else None
            if cand is not None and cand.id != row.id:
                moved_path = cand.path
                db.delete(cand)
                db.flush()
                row.path = moved_path
                row.status = "present"
                row.last_scanned_at = utcnow()
                summary.moved += 1
                summary.inserted -= 1
                del inserts_by_key[key]
            else:
                row.status = "missing"
                summary.missing += 1
```

- [ ] **Step 4: Esegui tutta la suite scanner e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_scanner.py -v`
Expected: 6 passed (i 4 di Task 5 + missing + move).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scanner.py backend/tests/test_scanner.py
git commit -m "feat: riconciliazione ri-scan — missing + spostamenti via hash

File spariti dal disco -> status=missing (riga preservata). File ricomparso con
lo stesso content_hash -> aggiorna il path della riga esistente (id e
first_seen_at preservati) invece di duplicare.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: HTTP — app FastAPI + router SOURCES

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/routers/sources.py`
- Modify: `backend/app/schemas.py` (aggiungi `ScanRootCreate`, `ScanRootRead`)
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `app.db` (get_db, ensure_schema), `app.models`, `app.schemas`.
- Produces:
  - `app.main.app` (FastAPI) con lifespan che chiama `ensure_schema()` e `GET /api/health`.
  - `app.routers.sources.router`: `GET /api/sources`, `POST /api/sources`, `DELETE /api/sources/{id}`.
  - `app.schemas.ScanRootCreate` (`path: str`, `label: str | None`), `ScanRootRead` (`id, path, label, last_scanned_at, file_count`).

- [ ] **Step 1: Aggiungi gli schemi a `backend/app/schemas.py`**

```python
from pydantic import ConfigDict  # aggiungi all'import esistente


class ScanRootCreate(BaseModel):
    path: str
    label: str | None = None


class ScanRootRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str
    label: str | None
    last_scanned_at: datetime | None
    file_count: int
```

- [ ] **Step 2: Scrivi i test che falliscono — `backend/tests/test_api.py`**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_sources_crud(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    with TestClient(app) as client:
        created = client.post("/api/sources", json={"path": str(lib), "label": "Main"})
        assert created.status_code == 201
        root_id = created.json()["id"]
        assert created.json()["file_count"] == 0

        listed = client.get("/api/sources").json()
        assert len(listed) == 1 and listed[0]["label"] == "Main"

        assert client.delete(f"/api/sources/{root_id}").status_code == 204
        assert client.get("/api/sources").json() == []


def test_add_source_rejects_missing_path():
    with TestClient(app) as client:
        resp = client.post("/api/sources", json={"path": "/percorso/inesistente/xyz"})
        assert resp.status_code == 400
```

- [ ] **Step 3: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_api.py -v`
Expected: ImportError su `app.main`.

- [ ] **Step 4: Implementa `backend/app/routers/sources.py`**

```python
"""Router SOURCES: gestione delle radici di scan + conteggi. Router sottile."""

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, ScanRoot
from app.schemas import ScanRootCreate, ScanRootRead

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _to_read(db: Session, root: ScanRoot) -> ScanRootRead:
    count = db.scalar(
        select(func.count()).select_from(AudioFile).where(AudioFile.root_id == root.id)
    )
    return ScanRootRead(
        id=root.id, path=root.path, label=root.label,
        last_scanned_at=root.last_scanned_at, file_count=count or 0,
    )


@router.get("", response_model=list[ScanRootRead])
def list_sources(db: Session = Depends(get_db)):
    return [_to_read(db, r) for r in db.scalars(select(ScanRoot)).all()]


@router.post("", response_model=ScanRootRead, status_code=201)
def add_source(body: ScanRootCreate, db: Session = Depends(get_db)):
    path = os.path.abspath(os.path.expanduser(body.path))
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Il path non esiste o non è una cartella")
    if db.scalar(select(ScanRoot).where(ScanRoot.path == path)):
        raise HTTPException(status_code=409, detail="Radice già presente")
    root = ScanRoot(path=path, label=body.label)
    db.add(root)
    db.commit()
    db.refresh(root)
    return _to_read(db, root)


@router.delete("/{root_id}", status_code=204)
def delete_source(root_id: int, db: Session = Depends(get_db)):
    root = db.get(ScanRoot, root_id)
    if root is None:
        raise HTTPException(status_code=404, detail="Radice non trovata")
    db.delete(root)
    db.commit()
```

- [ ] **Step 5: Implementa `backend/app/main.py`**

```python
"""Entrypoint FastAPI di DjOrganizer."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import ensure_schema
from app.routers import sources


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()
    yield


app = FastAPI(title="DjOrganizer", lifespan=lifespan)
app.include_router(sources.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_api.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/app/routers/sources.py backend/app/schemas.py backend/tests/test_api.py
git commit -m "feat: app FastAPI + router SOURCES (CRUD radici + conteggi)

Lifespan con ensure_schema; GET/POST/DELETE /api/sources con validazione del
path e conteggio file per radice; /api/health.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Job shell + router SCAN

**Files:**
- Create: `backend/app/services/scan_job.py`
- Create: `backend/app/routers/scan.py`
- Modify: `backend/app/main.py` (include il router scan)
- Test: `backend/tests/test_scan_job.py`, `backend/tests/test_api.py` (aggiungi i casi scan)

**Interfaces:**
- Consumes: `app.services.scanner.scan`, `app.models.ScanRoot`, `app.db.SessionLocal`, `app.main.app`.
- Produces:
  - `app.services.scan_job`: `start_job(root_ids: list[int] | None = None) -> dict`, `job_state() -> dict`, `is_running() -> bool`.
  - `app.routers.scan.router`: `POST /api/scan`, `GET /api/scan/status`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_scan_job.py`**

```python
import time

from sqlalchemy import select

from app.models import AudioFile, ScanRoot
from app.services import scan_job


def _wait_done(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = scan_job.job_state()
        if state["status"] in ("done", "error"):
            return state
        time.sleep(0.02)
    raise AssertionError("job non terminato in tempo")


def test_job_runs_and_completes(db, copy_fixture, tmp_path):
    root_dir = tmp_path / "lib"
    copy_fixture("mp3", root_dir / "a.mp3")
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    root_id = root.id

    scan_job.start_job([root_id])
    state = _wait_done()
    assert state["status"] == "done"
    assert state["result"]["inserted"] == 1
    assert db.scalar(select(AudioFile)) is not None


def test_double_start_is_rejected():
    # Forza lo stato running e verifica che start_job non lo sovrascriva.
    scan_job._state.update(status="running", processed=0, total=0)
    before = scan_job.job_state()
    returned = scan_job.start_job([1])
    assert returned["status"] == "running"
    assert scan_job.job_state()["started_at"] == before["started_at"]
    scan_job._state.update(status="idle")  # ripristina per gli altri test
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_scan_job.py -v`
Expected: ImportError su `scan_job`.

- [ ] **Step 3: Implementa `backend/app/services/scan_job.py`**

```python
"""Job di scan in background. App locale mono-utente: un job alla volta, stato
in memoria con lock. La UI lancia e poi fa polling di job_state()."""

import logging
import threading

from app.db import SessionLocal
from app.models import ScanRoot, utcnow
from app.services.scanner import scan

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "phase": None,
    "processed": 0,
    "total": 0,
    "result": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run(root_ids: list[int] | None) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        query = db.query(ScanRoot)
        roots = query.filter(ScanRoot.id.in_(root_ids)).all() if root_ids else query.all()
        summary = scan(db, roots, on_progress=on_progress)
        with _lock:
            _state.update(
                status="done", phase=None,
                result=summary.model_dump(mode="json"),
                finished_at=utcnow().isoformat(),
            )
        logger.info("Scan completato: %s", summary.model_dump())
    except Exception as exc:  # noqa: BLE001 — il job non deve propagare
        logger.exception("Scan fallito")
        with _lock:
            _state.update(status="error", error=str(exc), finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job(root_ids: list[int] | None = None) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(
            status="running", phase="scanning", processed=0, total=0,
            result=None, error=None, started_at=utcnow().isoformat(), finished_at=None,
        )
    threading.Thread(target=_run, args=(root_ids,), daemon=True).start()
    return job_state()
```

- [ ] **Step 4: Implementa `backend/app/routers/scan.py`**

```python
"""Router SCAN: avvio e stato del job di scansione. Router sottile."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import scan_job

router = APIRouter(prefix="/api/scan", tags=["scan"])


class ScanStart(BaseModel):
    root_ids: list[int] | None = None


@router.post("")
def start_scan(body: ScanStart | None = None):
    root_ids = body.root_ids if body else None
    return scan_job.start_job(root_ids)


@router.get("/status")
def scan_status():
    return scan_job.job_state()
```

- [ ] **Step 5: Includi il router in `backend/app/main.py`**

Modifica gli import e le `include_router`:

```python
from app.routers import scan, sources
```
```python
app.include_router(sources.router)
app.include_router(scan.router)
```

- [ ] **Step 6: Aggiungi il test API end-to-end in `backend/tests/test_api.py`**

```python
import time


def test_scan_endpoint_end_to_end(tmp_path, copy_fixture):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        root_id = client.post("/api/sources", json={"path": str(lib)}).json()["id"]
        started = client.post("/api/scan", json={"root_ids": [root_id]})
        assert started.status_code == 200

        deadline = time.time() + 5
        status = {}
        while time.time() < deadline:
            status = client.get("/api/scan/status").json()
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        assert status["status"] == "done"
        assert status["result"]["inserted"] == 1
```

- [ ] **Step 7: Esegui l'intera suite e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -v`
Expected: tutti i test passano (schema, fixtures, content_hash, tagio, scanner, scan_job, api).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/scan_job.py backend/app/routers/scan.py backend/app/main.py backend/tests/test_scan_job.py backend/tests/test_api.py
git commit -m "feat: job shell scan + router SCAN (start/status)

Job in background con stato in memoria e lock (un job alla volta), port del
pattern enrichment_job di Cratory; POST /api/scan + GET /api/scan/status.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verifica finale del chunk

- [ ] **Suite verde:** `cd backend && source .venv/bin/activate && python -m pytest tests -v` → tutto passa, incluso il test di retag-stabilità (`test_mp3_hash_stable_after_retag`, `test_flac_hash_stable_after_retag`).
- [ ] **Avvio reale:** `uvicorn app.main:app --reload --port 8000`; con `curl` aggiungi una radice reale, lancia lo scan, fai polling dello status fino a `done`, verifica che `audio_file` si popoli; ri-scan idempotente.
- [ ] **Definition of Done** della spec §12 soddisfatta.

## Self-Review (svolto in fase di scrittura)

- **Spec coverage:** scaffold/config/db/modelli (Task 1) ✓; `content_hash` pragmatico stream+fallback (Task 3) ✓; `tagio` mutagen (Task 4) ✓; motore Scanner + on_progress + ScanSummary (Task 5) ✓; resilienza errori (Task 5) ✓; riconciliazione missing+moved (Task 6) ✓; job shell + endpoint scan (Task 8) ✓; router sources + conteggi (Task 7) ✓; campi `hash_method`/`scan_error` (Task 1 modello, popolati Task 5) ✓; fixture reali (Task 2) ✓; test incl. retag-stabilità (Task 3) ✓.
- **Placeholder scan:** nessun TODO/TBD; tutto il codice è completo. L'unico punto con due varianti (`_mp3_range`) ha la versione canonica esplicitata nella nota.
- **Type consistency:** `compute -> (str|None, str)` usato coerentemente; `ScanSummary` con gli stessi campi in scanner/scan_job/api; `scan(db, roots, on_progress)` invariato tra Task 5 e 6; `ScanRootRead`/`ScanRootCreate` coerenti tra schema e router.
