# Disk-first core (fetta 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La libreria di Cratory diventa il disco: indicizzazione di `LIBRARY_ROOT` con riaggancio per audio-hash, possesso (`has_local_file`) come filtro di prima classe, vista wishlist (tracce senza file).

**Architecture:** Nuova colonna `Track.audio_hash` (identità stabile a rinomina/retag, calcolata al download e all'indicizzazione). Nuovo servizio deterministico `library_index` (walk + match `audio_hash → legacy digest → ISRC → fuzzy → crea`) + riconciliazione dei possessi orfani. Job in background con lo stesso pattern di `local_import_job`. Filtro `has_local_file` su repository/router/frontend.

**Tech Stack:** Python/FastAPI/SQLAlchemy/Pydantic (backend), pytest, Next.js 16 + React + Tailwind (frontend).

## Global Constraints

- Spec di riferimento: `~/Develop/docs/superpowers/specs/2026-07-01-dj-ecosystem-disk-first-design.md`.
- Test backend: `cd backend && .venv/bin/python -m pytest tests -q` (usare `source .venv/bin/activate` se preferito). Tutti verdi prima di ogni commit.
- Frontend: `cd frontend && npm run lint && npm run build` verdi prima del commit dei task frontend. **Next.js 16 ha breaking changes: leggere `frontend/CLAUDE.md` e i doc in `node_modules/next/dist/docs/` prima di toccare pagine/routing.**
- Copy UI e commenti in italiano, stile del codebase (commenti brevi che spiegano il perché).
- Regole non negoziabili di `CLAUDE.md`: BPM/key non si inventano e non si sovrascrivono; il servizio è deterministico, nessuna AI.
- Branch: `feat/disk-first-core` da `master`. Commit frequenti (uno per task).
- Non toccare: enrichment chain, discovery, set builder (fetta 2), Shazam.

---

### Task 0: Branch

**Files:** nessuno.

- [ ] **Step 1: Creare il branch**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git checkout master && git pull --ff-only 2>/dev/null; git checkout -b feat/disk-first-core
```

---

### Task 1: Colonna `Track.audio_hash`

**Files:**
- Modify: `backend/app/models.py` (classe `Track`, dopo `local_bitrate`, ~riga 49)
- Modify: `backend/app/db.py` (dict `additions["tracks"]`, ~riga 62)
- Test: `backend/tests/test_audio_hash_column.py`

**Interfaces:**
- Produces: `Track.audio_hash: str | None` (colonna indicizzata, SHA-256 hex dello stream audio; stessa semantica del digest usato come `platform_track_id` dalle tracce `local_files`).

- [ ] **Step 1: Test fallente**

```python
# backend/tests/test_audio_hash_column.py
"""La colonna audio_hash esiste sia su schema nuovo sia su DB migrato."""
from sqlalchemy import create_engine, inspect, text

from app.db import Base, ensure_schema


def test_audio_hash_su_schema_nuovo():
    engine = create_engine("sqlite://")
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("tracks")}
    assert "audio_hash" in cols


def test_audio_hash_su_db_esistente_senza_colonna():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tracks RENAME TO _t"))
        # tabella minima pre-migrazione (senza audio_hash)
        conn.execute(text("CREATE TABLE tracks (id INTEGER PRIMARY KEY, source_type VARCHAR)"))
        conn.execute(text("DROP TABLE _t"))
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("tracks")}
    assert "audio_hash" in cols
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && .venv/bin/python -m pytest tests/test_audio_hash_column.py -q`
Expected: FAIL (`assert 'audio_hash' in cols`).

- [ ] **Step 3: Implementazione minima**

In `backend/app/models.py`, dentro `Track`, dopo la riga `local_bitrate`:

```python
    # Identità audio (SHA-256 dello stream decodificato, vedi integrations/local_files.audio_hash):
    # stabile a rinomina/retag. Calcolata al download (acquisition) e all'indicizzazione libreria.
    audio_hash: Mapped[str | None] = mapped_column(String, index=True)
```

In `backend/app/db.py`, nel dict `additions["tracks"]`, dopo `"local_bitrate": "INTEGER",`:

```python
            "audio_hash": "VARCHAR",
```

- [ ] **Step 4: Verifica che passi**

Run: `cd backend && .venv/bin/python -m pytest tests/test_audio_hash_column.py -q`
Expected: 2 passed.

- [ ] **Step 5: Suite completa + commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q` → tutti verdi.

```bash
git add backend/app/models.py backend/app/db.py backend/tests/test_audio_hash_column.py
git commit -m "feat(disk-first): colonna Track.audio_hash (identità stabile a rinomina/retag)"
```

---

### Task 2: `attach_local_file` calcola e salva l'hash

**Files:**
- Modify: `backend/app/services/acquisition.py`
- Test: `backend/tests/test_acquisition.py` (estendere)

**Interfaces:**
- Consumes: `app.integrations.local_files.audio_hash(path) -> str` (solleva `LocalFilesError`).
- Produces: `attach_local_file(db, track, *, path, fmt=None, bitrate=None) -> Track` — firma INVARIATA (i chiamanti in `soulseek_download_job.py` non cambiano), ma ora valorizza anche `track.audio_hash` (best-effort: hash fallito ⇒ resta `None`, il collegamento file NON fallisce).

- [ ] **Step 1: Test fallente** (aggiungere in coda a `backend/tests/test_acquisition.py`, riusando lo stile dei test esistenti del file)

```python
def test_attach_salva_audio_hash(db, monkeypatch):
    from app.models import Track
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "abc123")
    t = Track(source_type="spotify")
    db.add(t); db.commit()
    out = acquisition.attach_local_file(db, t, path="/x/y.mp3", fmt="mp3", bitrate=320)
    assert out.audio_hash == "abc123"
    assert out.has_local_file is True


def test_attach_hash_fallito_non_blocca(db, monkeypatch):
    from app.integrations.local_files import LocalFilesError
    from app.models import Track
    from app.services import acquisition

    def boom(p):
        raise LocalFilesError("ffmpeg assente")

    monkeypatch.setattr(acquisition, "audio_hash", boom)
    t = Track(source_type="spotify")
    db.add(t); db.commit()
    out = acquisition.attach_local_file(db, t, path="/x/y.mp3")
    assert out.has_local_file is True
    assert out.audio_hash is None
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && .venv/bin/python -m pytest tests/test_acquisition.py -q`
Expected: FAIL (`AttributeError: ... has no attribute 'audio_hash'` sul monkeypatch).

- [ ] **Step 3: Implementazione**

Sostituire il contenuto di `backend/app/services/acquisition.py` con:

```python
"""Collega un file audio acquisito a una Track esistente (ownership).

Non tocca lo status di enrichment ne' le feature musicali. Calcola l'audio-hash
(best-effort): e' la chiave di riaggancio quando DjOrganizer rinomina/sposta il
file nella libreria canonica.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.integrations.local_files import LocalFilesError, audio_hash
from app.models import Track

logger = logging.getLogger(__name__)


def attach_local_file(db: Session, track: Track, *, path: str,
                      fmt: str | None = None, bitrate: int | None = None) -> Track:
    track.has_local_file = True
    track.local_path = path
    track.local_format = fmt
    track.local_bitrate = bitrate
    try:
        track.audio_hash = audio_hash(path)
    except LocalFilesError as exc:
        # L'hash e' il riaggancio futuro, non un requisito del possesso: non bloccare.
        logger.warning("Audio-hash non calcolabile per %s: %s", path, exc)
    db.commit()
    db.refresh(track)
    return track
```

- [ ] **Step 4: Verifica che passi**

Run: `cd backend && .venv/bin/python -m pytest tests/test_acquisition.py tests/test_soulseek_download_job.py -q`
Expected: tutti verdi (il job soulseek usa la stessa firma). Se `test_soulseek_download_job.py` fallisce perché ora `attach_local_file` invoca ffmpeg su path finti, monkeypatchare `app.services.acquisition.audio_hash` nelle fixture di quel file con `lambda p: "hash-" + str(p)`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/acquisition.py backend/tests/test_acquisition.py backend/tests/test_soulseek_download_job.py
git commit -m "feat(disk-first): attach_local_file salva l'audio-hash al download"
```

---

### Task 3: Config `library_root`

**Files:**
- Modify: `backend/app/core/config.py` (classe `Settings`, dopo `local_import_root`)
- Test: `backend/tests/test_library_index.py` (nuovo file, primo test)

**Interfaces:**
- Produces: `settings.library_root: str` (vuoto = indicizzazione disattiva). Env: `LIBRARY_ROOT`.

- [ ] **Step 1: Test fallente**

```python
# backend/tests/test_library_index.py
"""Indicizzazione della libreria canonica (LIBRARY_ROOT)."""
from app.core.config import Settings


def test_library_root_default_vuoto():
    s = Settings(_env_file=None)
    assert s.library_root == ""
```

- [ ] **Step 2: Run** `cd backend && .venv/bin/python -m pytest tests/test_library_index.py -q` → FAIL (`AttributeError`).

- [ ] **Step 3: Implementazione** — in `backend/app/core/config.py`, sotto la riga `local_import_root: str = ""`:

```python
    # Libreria canonica su disco (disk-first): radice indicizzata da /api/library/index.
    # Vuoto = indicizzazione disattiva. I file qui dentro SONO la libreria posseduta.
    library_root: str = ""
```

- [ ] **Step 4: Run** stesso comando → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_library_index.py
git commit -m "feat(disk-first): config LIBRARY_ROOT (radice della libreria canonica)"
```

---

### Task 4: Servizio `library_index` — matching e upsert

**Files:**
- Create: `backend/app/services/library_index.py`
- Test: `backend/tests/test_library_index.py` (estendere)

**Interfaces:**
- Consumes: `scan_folder` da `app.services.local_import`; `read_tags`, `read_audio_quality`, `audio_hash`, `LocalFilesError` da `app.integrations.local_files`; `parse_line` da `app.services.manual_import`.
- Produces: `index_library(db, *, root: str | Path, on_progress=None) -> dict` con report `{"scanned": int, "matched": int, "created": int, "relinked": int, "lost": int, "failed": int, "errors": list[dict]}`. Ordine di match per file: `Track.audio_hash` → legacy digest (`platform=="local_files"` e `platform_track_id==digest`) → `Track.isrc` (dal tag) → fuzzy `artist+title` (ilike, entrambi presenti) → crea nuova `Track(source_type="local_files")`. Ogni match aggiorna `local_path/has_local_file/local_format/local_bitrate/audio_hash` e riempie SOLO i campi identità vuoti (mai sovrascrivere enrichment).

- [ ] **Step 1: Test fallenti** (aggiungere a `backend/tests/test_library_index.py`)

```python
import pytest


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Crea file finti e monkeypatcha hash/tag/qualita' per renderli deterministici."""
    from app.services import library_index as li

    hashes: dict[str, str] = {}
    tags: dict[str, dict] = {}

    def make(rel: str, *, digest: str, artist=None, title=None, isrc=None):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        hashes[str(p.resolve())] = digest
        tags[str(p.resolve())] = {
            "title": title, "artist": artist, "album": None, "year": None,
            "duration_seconds": 200, "isrc": isrc,
        }
        return p

    monkeypatch.setattr(li, "audio_hash", lambda p: hashes[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_tags", lambda p: tags[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 320})
    return make, tmp_path


def test_riaggancio_per_audio_hash(db, fake_audio):
    """File rinominato/ritaggato: stesso hash ⇒ stessa Track, local_path aggiornato."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", spotify_id="s1", title="Origin", artist="A",
              has_local_file=True, local_path="/vecchio/inbox/file.mp3", audio_hash="H1")
    db.add(t); db.commit()

    make("Techno/A/A - Origin.mp3", digest="H1")
    report = index_library(db, root=root)

    db.refresh(t)
    assert report["relinked"] == 1 and report["created"] == 0
    assert t.local_path.endswith("A - Origin.mp3")
    assert t.has_local_file is True and t.local_format == "mp3"


def test_match_per_isrc_da_tag(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", isrc="ISRC001", title="X", artist="A")
    db.add(t); db.commit()

    make("f.mp3", digest="H9", isrc="ISRC001")
    index_library(db, root=root)

    db.refresh(t)
    assert t.has_local_file is True and t.audio_hash == "H9"


def test_match_fuzzy_artista_titolo(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", title="My Song", artist="Someone")
    db.add(t); db.commit()

    make("g.mp3", digest="H8", artist="someone", title="my song")
    index_library(db, root=root)

    db.refresh(t)
    assert t.has_local_file is True


def test_file_sconosciuto_crea_track_local_files(db, fake_audio):
    from sqlalchemy import select
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    report = index_library(db, root=root)

    assert report["created"] == 1
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert t is not None and t.source_type == "local_files"
    assert t.platform_track_id == "H7" and t.artist == "N"


def test_non_sovrascrive_identita_esistente(db, fake_audio):
    """I tag del file riempiono solo i campi vuoti (l'enrichment/manuale resta autorevole)."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", title="Titolo Corretto", artist="A",
              genre="Techno", audio_hash="H1")
    db.add(t); db.commit()

    make("f.mp3", digest="H1", artist="A", title="titolo sbagliato dal tag")
    index_library(db, root=root)

    db.refresh(t)
    assert t.title == "Titolo Corretto" and t.genre == "Techno"
```

- [ ] **Step 2: Run** `cd backend && .venv/bin/python -m pytest tests/test_library_index.py -q` → FAIL (`ModuleNotFoundError: app.services.library_index`).

- [ ] **Step 3: Implementazione**

```python
# backend/app/services/library_index.py
"""Indicizzazione della libreria canonica (disk-first): il disco È la libreria.

Deterministico, senza AI. Per ogni file audio sotto LIBRARY_ROOT:
hash → match (audio_hash → digest legacy → ISRC → fuzzy artist+title) → upsert
del possesso (local_path/has_local_file/formato/bitrate/audio_hash). I tag del
file riempiono SOLO i campi identità vuoti: enrichment e correzioni manuali
restano autorevoli (regola: mai sovrascrivere).
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.local_files import (
    LocalFilesError,
    audio_hash,
    read_audio_quality,
    read_tags,
)
from app.models import Track
from app.services.manual_import import parse_line
from app.services.local_import import scan_folder
from app.services.track_status import refresh_status

logger = logging.getLogger(__name__)

PLATFORM = "local_files"


def _find_track(db: Session, *, digest: str, tags: dict) -> tuple[Track | None, str]:
    """Match nell'ordine di affidabilità. Ritorna (track, come) — come ∈ hash|digest|isrc|fuzzy."""
    hit = db.scalar(select(Track).where(Track.audio_hash == digest))
    if hit:
        return hit, "hash"
    # Import locali storici: il digest viveva in platform_track_id.
    hit = db.scalar(select(Track).where(
        Track.platform == PLATFORM, Track.platform_track_id == digest))
    if hit:
        return hit, "digest"
    if tags.get("isrc"):
        hit = db.scalar(select(Track).where(Track.isrc == tags["isrc"]))
        if hit:
            return hit, "isrc"
    artist, title = tags.get("artist"), tags.get("title")
    if artist and title:
        hit = db.scalar(select(Track).where(
            Track.artist.ilike(artist), Track.title.ilike(title)))
        if hit:
            return hit, "fuzzy"
    return None, ""


def _fill_identity(track: Track, tags: dict, path: Path) -> None:
    """Riempie SOLO i campi vuoti dai tag (fallback dal nome file, come l'import locale)."""
    artist, title = tags.get("artist"), tags.get("title")
    if not artist or not title:
        parsed = parse_line(path.stem)
        if parsed is not None:
            artist = artist or parsed[0]
            title = title or parsed[1]
    track.title = track.title or title
    track.artist = track.artist or artist
    track.album = track.album or tags.get("album")
    track.year = track.year or tags.get("year")
    track.duration_seconds = track.duration_seconds or tags.get("duration_seconds")
    track.isrc = track.isrc or tags.get("isrc")


def _own(track: Track, *, path: Path, digest: str) -> None:
    quality = read_audio_quality(path)
    track.local_path = str(path.resolve())
    track.has_local_file = True
    track.local_format = quality["format"]
    track.local_bitrate = quality["bitrate"]
    track.audio_hash = digest


def index_library(db: Session, *, root: str | Path, on_progress=None) -> dict:
    """Indicizza la libreria canonica. Vedi docstring del modulo per la semantica."""
    files = scan_folder(root)
    report = {"scanned": len(files), "matched": 0, "created": 0,
              "relinked": 0, "lost": 0, "failed": 0, "errors": []}
    seen_paths: set[str] = set()

    for i, path in enumerate(files, start=1):
        try:
            digest = audio_hash(path)
        except LocalFilesError as exc:
            report["failed"] += 1
            report["errors"].append({"path": str(path), "error": str(exc)})
            logger.warning("File saltato %s: %s", path, exc)
            continue
        tags = read_tags(path)
        track, how = _find_track(db, digest=digest, tags=tags)
        if track is None:
            track = Track(source_type=PLATFORM, platform=PLATFORM, platform_track_id=digest)
            db.add(track)
            report["created"] += 1
        else:
            report["matched"] += 1
            if track.local_path != str(path.resolve()):
                report["relinked"] += 1
        _fill_identity(track, tags, path)
        _own(track, path=path, digest=digest)
        refresh_status(track)
        seen_paths.add(str(path.resolve()))
        if on_progress is not None:
            on_progress(i, len(files))

    db.commit()
    return report
```

Nota: `report["lost"]` resta 0 in questo task — la riconciliazione arriva nel Task 5.

- [ ] **Step 4: Run** `cd backend && .venv/bin/python -m pytest tests/test_library_index.py -q` → tutti PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/library_index.py backend/tests/test_library_index.py
git commit -m "feat(disk-first): servizio library_index (match hash→digest→ISRC→fuzzy, upsert possesso)"
```

---

### Task 5: Riconciliazione — file spariti tornano wishlist

**Files:**
- Modify: `backend/app/services/library_index.py`
- Test: `backend/tests/test_library_index.py` (estendere)

**Interfaces:**
- Produces: `index_library` ora riconcilia: ogni `Track` con `has_local_file=True` il cui `local_path` non esiste più su disco (e non è appena stato visto) perde il possesso (`has_local_file=False`, `local_path=None`, formato/bitrate azzerati, **`audio_hash` CONSERVATO** — è l'identità per un eventuale ritorno). Conteggiata in `report["lost"]`.

- [ ] **Step 1: Test fallenti**

```python
def test_riconciliazione_file_sparito(db, fake_audio, tmp_path):
    """Possesso orfano (file cancellato/spostato fuori) ⇒ torna wishlist, hash conservato."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    sparito = Track(source_type="spotify", title="Gone", artist="A",
                    has_local_file=True, local_path=str(tmp_path / "non-esiste.mp3"),
                    local_format="mp3", audio_hash="HGONE")
    db.add(sparito); db.commit()

    make("resta.mp3", digest="HSTAY", artist="B", title="Stay")
    report = index_library(db, root=root)

    db.refresh(sparito)
    assert report["lost"] == 1
    assert sparito.has_local_file is False and sparito.local_path is None
    assert sparito.audio_hash == "HGONE"


def test_riconciliazione_non_tocca_i_visti(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", title="Here", artist="A", audio_hash="H1")
    db.add(t); db.commit()
    make("here.mp3", digest="H1")
    report = index_library(db, root=root)

    db.refresh(t)
    assert report["lost"] == 0 and t.has_local_file is True
```

- [ ] **Step 2: Run** → FAIL (`lost` resta 0 / possesso non azzerato).

- [ ] **Step 3: Implementazione** — in `index_library`, sostituire le due righe finali (`db.commit()` / `return report`) con:

```python
    # Riconciliazione: possessi il cui file non esiste piu' (spostato in archive/,
    # cancellato a mano, inbox ripulita). L'audio_hash resta: se il file ricompare
    # altrove, il riaggancio e' immediato.
    owned = db.scalars(select(Track).where(Track.has_local_file.is_(True))).all()
    for track in owned:
        if not track.local_path or track.local_path in seen_paths:
            continue
        if Path(track.local_path).exists():
            continue
        track.has_local_file = False
        track.local_path = None
        track.local_format = None
        track.local_bitrate = None
        refresh_status(track)
        report["lost"] += 1

    db.commit()
    return report
```

- [ ] **Step 4: Run** `cd backend && .venv/bin/python -m pytest tests/test_library_index.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/library_index.py backend/tests/test_library_index.py
git commit -m "feat(disk-first): riconciliazione possessi orfani (file sparito ⇒ wishlist, hash conservato)"
```

---

### Task 6: Job in background + endpoint `/api/library/index`

**Files:**
- Create: `backend/app/services/library_index_job.py`
- Modify: `backend/app/routers/tracks.py` (nuovi endpoint)
- Modify: `backend/app/schemas.py` (nuovo schema, accanto a `LibraryStatsOut` ~riga 486)
- Test: `backend/tests/test_library_index_router.py`

**Interfaces:**
- Consumes: `index_library` (Task 4/5), `settings.library_root` (Task 3).
- Produces:
  - `library_index_job.start_job() -> dict` / `job_state() -> dict` / `is_running() -> bool` (stesso pattern di `local_import_job`).
  - `POST /api/library/index` → 202 con `LibraryIndexJobStatus`; 409 se `library_root` non configurata.
  - `GET /api/library/index/status` → `LibraryIndexJobStatus`.
  - Schema `LibraryIndexJobStatus(BaseModel)`: `status: str; processed: int; total: int; scanned: int; matched: int; created: int; relinked: int; lost: int; failed: int; errors: list[dict]; error: str | None; root: str | None; started_at: str | None; finished_at: str | None`.

- [ ] **Step 1: Test fallente**

```python
# backend/tests/test_library_index_router.py
"""Endpoint /api/library/index: avvio job e polling stato."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_409_senza_library_root(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", "")
    r = client.post("/api/library/index")
    assert r.status_code == 409
    assert "LIBRARY_ROOT" in r.json()["detail"]


def test_avvio_e_status(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import library_index_job

    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    # niente thread reale nel test: il job gira sincrono
    monkeypatch.setattr(library_index_job, "_spawn", lambda fn: fn())
    r = client.post("/api/library/index")
    assert r.status_code == 202
    s = client.get("/api/library/index/status").json()
    assert s["status"] == "done"
    assert s["scanned"] == 0  # cartella vuota
```

- [ ] **Step 2: Run** `cd backend && .venv/bin/python -m pytest tests/test_library_index_router.py -q` → FAIL (404 sugli endpoint).

- [ ] **Step 3: Implementazione**

```python
# backend/app/services/library_index_job.py
"""Job di indicizzazione libreria in background (pattern di local_import_job:
mono-utente, un job alla volta, stato in memoria con lock)."""

import logging
import threading
from datetime import datetime, timezone

from app.core.config import settings
from app.db import SessionLocal
from app.services.library_index import index_library

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "processed": 0, "total": 0,
    "scanned": 0, "matched": 0, "created": 0, "relinked": 0, "lost": 0, "failed": 0,
    "errors": [], "error": None, "root": None,
    "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _spawn(fn) -> None:
    """Separato per i test (che lo rendono sincrono)."""
    threading.Thread(target=fn, daemon=True).start()


def _run_job(root: str) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int) -> None:
        _state.update(processed=processed, total=total)

    try:
        report = index_library(db, root=root, on_progress=on_progress)
        _state.update(status="done", **{k: report[k] for k in
                      ("scanned", "matched", "created", "relinked", "lost", "failed", "errors")})
        logger.info("Indicizzazione libreria completata: %s", {
            k: report[k] for k in ("scanned", "matched", "created", "relinked", "lost", "failed")})
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Indicizzazione libreria fallita")
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


def start_job() -> dict:
    """Avvia il job sulla LIBRARY_ROOT configurata. No-op se già in corso."""
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(status="running", processed=0, total=0, scanned=0, matched=0,
                      created=0, relinked=0, lost=0, failed=0, errors=[], error=None,
                      root=settings.library_root,
                      started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
    _spawn(lambda: _run_job(settings.library_root))
    return job_state()
```

In `backend/app/schemas.py`, prima di `class LibraryStatsOut`:

```python
class LibraryIndexJobStatus(BaseModel):
    """Stato del job di indicizzazione della libreria canonica (disk-first)."""

    status: str
    processed: int = 0
    total: int = 0
    scanned: int = 0
    matched: int = 0
    created: int = 0
    relinked: int = 0
    lost: int = 0
    failed: int = 0
    errors: list[dict] = []
    error: str | None = None
    root: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
```

In `backend/app/routers/tracks.py` — aggiungere agli import: `from fastapi import status as http_status` non serve; aggiungere `from app.core.config import settings`, `from app.schemas import LibraryIndexJobStatus` (nell'import esistente da `app.schemas`) e `from app.services import library_index_job`. Poi, sopra `@router.get("/stats", ...)`:

```python
@router.post("/library/index", response_model=LibraryIndexJobStatus, status_code=202)
def start_library_index():
    """Indicizza la libreria canonica (LIBRARY_ROOT): il disco È la libreria."""
    if not settings.library_root:
        raise HTTPException(
            status_code=409,
            detail="LIBRARY_ROOT non configurata: imposta nel .env la cartella della libreria canonica.",
        )
    return library_index_job.start_job()


@router.get("/library/index/status", response_model=LibraryIndexJobStatus)
def library_index_status():
    return library_index_job.job_state()
```

- [ ] **Step 4: Run** `cd backend && .venv/bin/python -m pytest tests/test_library_index_router.py -q` → PASS. Poi suite intera → verde.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/library_index_job.py backend/app/routers/tracks.py backend/app/schemas.py backend/tests/test_library_index_router.py
git commit -m "feat(disk-first): job + endpoint POST /api/library/index e /status"
```

---

### Task 7: Filtro possesso su `GET /api/tracks` + sorgente `local_files`

**Files:**
- Modify: `backend/app/repositories.py` (`_apply_track_filters`, firma e corpo)
- Modify: `backend/app/routers/tracks.py` (`get_tracks`: nuovo param + pattern `source`)
- Test: `backend/tests/test_library_query.py` (estendere)

**Interfaces:**
- Produces: `GET /api/tracks?has_local_file=true|false` (None = tutte); `source` accetta anche `local_files`. Il filtro repo: `has_local_file: bool | None = None` in `_apply_track_filters`.

- [ ] **Step 1: Test fallenti** (in coda a `backend/tests/test_library_query.py`, riusando le fixture del file)

```python
def test_filtro_has_local_file(db):
    from app.models import Track
    from app.repositories import list_tracks

    db.add(Track(source_type="spotify", title="Owned", artist="A", has_local_file=True))
    db.add(Track(source_type="spotify", title="Wish", artist="B", has_local_file=False))
    db.commit()

    total_owned, owned = list_tracks(db, has_local_file=True)
    total_wish, wish = list_tracks(db, has_local_file=False)
    assert total_owned == 1 and owned[0].title == "Owned"
    assert total_wish == 1 and wish[0].title == "Wish"


def test_filtro_source_local_files(db):
    from app.models import Track
    from app.repositories import list_tracks

    db.add(Track(source_type="local_files", title="Loc", artist="A"))
    db.add(Track(source_type="spotify", title="Sp", artist="B"))
    db.commit()

    total, rows = list_tracks(db, source="local_files")
    assert total == 1 and rows[0].title == "Loc"
```

- [ ] **Step 2: Run** `cd backend && .venv/bin/python -m pytest tests/test_library_query.py -q` → FAIL (`TypeError: unexpected keyword argument 'has_local_file'`).

- [ ] **Step 3: Implementazione**

In `backend/app/repositories.py`, `_apply_track_filters`: aggiungere il parametro `has_local_file: bool | None = None,` dopo `has_soundcloud`, e nel corpo, dopo il blocco `has_soundcloud`:

```python
    if has_local_file is not None:
        # Possesso disk-first: True = in libreria (file su disco), False = wishlist.
        stmt = (
            stmt.where(Track.has_local_file.is_(True))
            if has_local_file
            else stmt.where((Track.has_local_file.is_(False)) | (Track.has_local_file.is_(None)))
        )
```

In `backend/app/routers/tracks.py`, `get_tracks`: cambiare il pattern di `source` in `"^(spotify|soundcloud|manual|local_files)$"`, aggiungere il parametro `has_local_file: bool | None = None,` dopo `has_soundcloud`, e passarlo a `list_tracks(...)` (`has_local_file=has_local_file,`).

- [ ] **Step 4: Run** test file + suite → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories.py backend/app/routers/tracks.py backend/tests/test_library_query.py
git commit -m "feat(disk-first): filtro has_local_file e sorgente local_files su GET /api/tracks"
```

---

### Task 8: `library_stats.with_local_file`

**Files:**
- Modify: `backend/app/repositories.py` (`library_stats`)
- Modify: `backend/app/schemas.py` (`LibraryStatsOut`)
- Test: `backend/tests/test_stats_histograms.py` (estendere)

**Interfaces:**
- Produces: chiave `with_local_file: int` nel dict di `library_stats` e campo in `LibraryStatsOut` (la dashboard la userà nella fetta 4).

- [ ] **Step 1: Test fallente** (in coda a `backend/tests/test_stats_histograms.py`)

```python
def test_stats_with_local_file(db):
    from app.models import Track
    from app.repositories import library_stats

    db.add(Track(source_type="spotify", title="O", artist="A", has_local_file=True))
    db.add(Track(source_type="spotify", title="W", artist="B"))
    db.commit()
    assert library_stats(db)["with_local_file"] == 1
```

- [ ] **Step 2: Run** → FAIL (`KeyError`).

- [ ] **Step 3: Implementazione** — in `library_stats`, dopo la riga `ready_for_set = count_where(...)`:

```python
    with_local_file = count_where(Track.has_local_file.is_(True))
```

e nel dict di ritorno, dopo `"ready_for_set": ready_for_set,`:

```python
        "with_local_file": with_local_file,
```

In `backend/app/schemas.py`, dentro `LibraryStatsOut` (leggere i campi esistenti e aggiungere coerentemente):

```python
    with_local_file: int = 0
```

- [ ] **Step 4: Run** file + suite → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories.py backend/app/schemas.py backend/tests/test_stats_histograms.py
git commit -m "feat(disk-first): conteggio with_local_file nelle stats di libreria"
```

---

### Task 9: Frontend — possesso in libreria (filtro + badge) e wishlist

**Files:**
- Modify: `frontend/lib/api.ts` (interface `Track` + tipi)
- Modify: `frontend/app/library/page.tsx` (filtro possesso + badge FILE)

**Interfaces:**
- Consumes: `GET /api/tracks?has_local_file=` (Task 7). I campi `has_local_file/local_path/local_format/local_bitrate` sono GIÀ nel payload backend (`TrackOut`), mancano solo nel tipo TS.
- Produces: select "Possesso" nei filtri della libreria (Tutte / Solo posseduti / Wishlist — senza file) e badge `FILE` accanto allo stato nelle righe possedute.

**Prima di toccare il frontend: leggere `frontend/CLAUDE.md` (Next.js 16 ha breaking changes).**

- [ ] **Step 1: Tipi in `frontend/lib/api.ts`** — nell'`interface Track` (riga 3), dopo `enrichment_confidence: number | null;`:

```typescript
  has_local_file: boolean;
  local_path: string | null;
  local_format: string | null;
  local_bitrate: number | null;
```

- [ ] **Step 2: Filtro in `frontend/app/library/page.tsx`** — aggiungere lo stato dopo `const [incomplete, setIncomplete] = useState(false);`:

```typescript
  const [owned, setOwned] = useState(""); // "" = tutte | "true" = possedute | "false" = wishlist
```

nel `load` (chiamata `apiGet`), aggiungere ai parametri:

```typescript
      has_local_file: owned || undefined,
```

e aggiungere `owned` all'array di dipendenze del `useCallback`. Nel blocco `filters`, dopo la `Select` delle sorgenti (che va estesa con `<option value="local_files">File locali</option>`):

```tsx
      <Select className="h-9" value={owned} onChange={(e) => { setOwned(e.target.value); setOffset(0); }}>
        <option value="">Possesso: tutte</option>
        <option value="true">Solo posseduti</option>
        <option value="false">Wishlist (senza file)</option>
      </Select>
```

- [ ] **Step 3: Badge FILE** — nella cella della tabella dove viene renderizzato il badge di stato (cercare `STATUS_LABEL` nel body della riga), aggiungere accanto:

```tsx
      {t.has_local_file && <Badge tone="success">FILE</Badge>}
```

(usare il componente `Badge` già importato; se la prop del tono ha un nome diverso, uniformarsi al Badge dello stato).

- [ ] **Step 4: Verifica**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 errori.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/library/page.tsx
git commit -m "feat(disk-first): filtro possesso + badge FILE nella libreria"
```

---

### Task 10: Frontend — trigger indicizzazione in Impostazioni

**Files:**
- Modify: `frontend/lib/api.ts` (tipo job + funzioni)
- Modify: `frontend/app/settings/page.tsx` (sezione "Libreria (disco)")

**Interfaces:**
- Consumes: `POST /api/library/index` (202/409) e `GET /api/library/index/status` (Task 6).
- Produces: sezione in Impostazioni con bottone "Indicizza ora", polling dello stato ogni 2s mentre `running`, riepilogo `scanned/matched/created/relinked/lost/failed` a fine job, messaggio chiaro se 409 (LIBRARY_ROOT mancante).

- [ ] **Step 1: API client** — in `frontend/lib/api.ts`, vicino alle altre funzioni (dopo `enrichTrack`):

```typescript
export interface LibraryIndexJob {
  status: "idle" | "running" | "done" | "error";
  processed: number;
  total: number;
  scanned: number;
  matched: number;
  created: number;
  relinked: number;
  lost: number;
  failed: number;
  errors: { path: string; error: string }[];
  error: string | null;
  root: string | null;
}

/** Indicizza la libreria canonica (LIBRARY_ROOT): il disco è la libreria. */
export function startLibraryIndex() {
  return apiPost<LibraryIndexJob>("/api/library/index");
}

export function libraryIndexStatus() {
  return apiGet<LibraryIndexJob>("/api/library/index/status");
}
```

(`apiPost`/`apiGet` sono gli helper già presenti nel file: verificarne la firma esatta e uniformarsi.)

- [ ] **Step 2: Sezione in Impostazioni** — in `frontend/app/settings/page.tsx`, studiare come sono fatte le sezioni esistenti (es. quella slskd o backfill etichette) e replicare il pattern con questo contenuto:

```tsx
// Stato in cima al componente:
const [libJob, setLibJob] = useState<LibraryIndexJob | null>(null);
const [libError, setLibError] = useState<string | null>(null);

// Polling mentre gira (pattern degli altri job della pagina):
useEffect(() => {
  if (libJob?.status !== "running") return;
  const t = setInterval(() => libraryIndexStatus().then(setLibJob).catch(() => {}), 2000);
  return () => clearInterval(t);
}, [libJob?.status]);

const runIndex = () => {
  setLibError(null);
  startLibraryIndex().then(setLibJob).catch((e) => setLibError(String(e.message ?? e)));
};
```

e nel JSX una sezione "Libreria (disco)" con: descrizione breve («La libreria canonica è la cartella LIBRARY_ROOT sul disco: indicizzala dopo ogni riorganizzazione»), bottone `Indicizza ora` (disabilitato se `libJob?.status === "running"`), barra/contatore `processed/total` durante il run, e a `done` il riepilogo:

```tsx
{libJob?.status === "done" && (
  <p className="text-sm">
    {libJob.scanned} file · {libJob.matched} riagganciate · {libJob.created} nuove ·
    {" "}{libJob.relinked} path aggiornati · {libJob.lost} perse · {libJob.failed} errori
  </p>
)}
{libError && <Alert tone="danger">{libError}</Alert>}
```

(adattare `Alert`/`Badge`/`Button` ai componenti reali di `components/ui.tsx`.)

- [ ] **Step 3: Verifica**

Run: `cd frontend && npm run lint && npm run build` → 0 errori.
Verifica manuale (facoltativa ma consigliata): backend attivo con `LIBRARY_ROOT` puntata a una cartella di prova → il bottone avvia e il riepilogo appare.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/app/settings/page.tsx
git commit -m "feat(disk-first): sezione Impostazioni per indicizzare la libreria canonica"
```

---

### Task 11: Verifica finale e chiusura fetta

**Files:** nessuno (verifica).

- [ ] **Step 1: Suite backend completa**

Run: `cd backend && .venv/bin/python -m pytest tests -q`
Expected: tutti verdi (294+ test).

- [ ] **Step 2: Frontend**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 errori.

- [ ] **Step 3: Aggiornare `.env.example`** (se esiste in `backend/`) con:

```
# Libreria canonica su disco (disk-first). Vuoto = indicizzazione disattiva.
LIBRARY_ROOT=
```

- [ ] **Step 4: Commit finale**

```bash
git add -A
git commit -m "chore(disk-first): chiusura fetta 1 — libreria = disco (indice, riaggancio, wishlist)"
```

Il merge su `master` avviene dopo la code review della fetta (workflow superpowers).
