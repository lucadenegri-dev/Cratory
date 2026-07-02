# Lotto A — Indice Incrementale e Avvio Automatico — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L'indicizzazione salta i file invariati (niente ri-hash ffmpeg) e parte da sola all'avvio del backend.

**Architecture:** Due colonne nuove su `Track` (`local_mtime`, `local_size`) memorizzano lo stato del file agganciato; `index_library` confronta path+mtime+size e salta il flusso completo per i file invariati (contatore `unchanged` nel report). Il lifespan di FastAPI lancia `library_index_job.start_job()` se `LIBRARY_ROOT` è configurata.

**Tech Stack:** Python/FastAPI + SQLAlchemy + pytest. Spec: `~/Develop/docs/superpowers/specs/2026-07-02-metadati-stati-automazioni-design.md` (Lotto A).

## Global Constraints

- Repo: `/Users/lucadenegri/Develop/DJProject01`, lavorare su branch dedicato.
- Commenti/docstring in italiano. Niente Alembic: colonne nuove via `ensure_schema` (ALTER idempotente in `backend/app/db.py`).
- Test: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/ -q` — tutti verdi (364 attuali).
- I test dell'indice usano la fixture `fake_audio` di `tests/test_library_index.py` (monkeypatch di `audio_hash`/`read_tags`/`read_audio_quality` sul modulo `library_index`): replicarne il pattern, non inventarne altri.

---

### Task 1: Colonne `local_mtime`/`local_size` popolate all'aggancio

**Files:**
- Modify: `backend/app/models.py` (blocco campi locali di `Track`, righe ~44-52)
- Modify: `backend/app/db.py` (dict `additions["tracks"]`)
- Modify: `backend/app/services/library_index.py` (funzione `_own`, righe ~73-80)
- Test: `backend/tests/test_library_index_incremental.py` (nuovo)

**Interfaces:**
- Consumes: fixture `db` di conftest; pattern `fake_audio` da `tests/test_library_index.py`.
- Produces: `Track.local_mtime: float | None`, `Track.local_size: int | None`, valorizzati da `_own()` per ogni file agganciato. Il Task 2 li confronta con `Path.stat()`.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `backend/tests/test_library_index_incremental.py`:

```python
"""Indicizzazione incrementale: skip dei file invariati (path+mtime+size)."""
import pytest


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Stesso pattern di test_library_index.py: file finti, hash/tag deterministici."""
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


def test_own_salva_mtime_e_size(db, fake_audio):
    """L'aggancio memorizza mtime e size del file (base dell'incrementale)."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    p = make("Techno/A/A - T1.mp3", digest="H1", artist="A", title="T1")
    index_library(db, root=root)

    t = db.query(Track).filter(Track.audio_hash == "H1").one()
    stat = p.stat()
    assert t.local_mtime == stat.st_mtime
    assert t.local_size == stat.st_size
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/test_library_index_incremental.py -v`
Expected: FAIL (`Track` non ha `local_mtime`)

- [ ] **Step 3: Implementa**

In `backend/app/models.py`, nel blocco dei campi locali di `Track`, dopo `local_bitrate`:

```python
    # Stato del file all'ultimo aggancio (per la scansione incrementale:
    # path+mtime+size invariati => niente ri-hash).
    local_mtime: Mapped[float | None] = mapped_column(Float)
    local_size: Mapped[int | None] = mapped_column(Integer)
```

In `backend/app/db.py`, dentro `additions["tracks"]` (in coda al dict, dopo le voci ownership):

```python
            "local_mtime": "FLOAT",
            "local_size": "INTEGER",
```

In `backend/app/services/library_index.py`, funzione `_own`:

```python
def _own(track: Track, *, path: Path, digest: str) -> None:
    quality = read_audio_quality(path)
    stat = path.stat()
    track.local_path = str(path.resolve())
    track.has_local_file = True
    track.local_format = quality["format"]
    track.local_bitrate = quality["bitrate"]
    track.audio_hash = digest
    track.local_mtime = stat.st_mtime
    track.local_size = stat.st_size
```

- [ ] **Step 4: Verifica che passi + suite**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/test_library_index_incremental.py tests/test_library_index.py -v && .venv/bin/python -m pytest tests/ -q`
Expected: tutti PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add backend/app/models.py backend/app/db.py backend/app/services/library_index.py backend/tests/test_library_index_incremental.py
git commit -m "feat: Track.local_mtime/local_size salvati all'aggancio del file"
```

---

### Task 2: Skip dei file invariati + contatore `unchanged`

**Files:**
- Modify: `backend/app/services/library_index.py` (loop di `index_library`, righe ~82-120)
- Modify: `backend/app/services/library_index_job.py` (chiavi copiate in `_state`)
- Modify: `backend/app/schemas.py` (`LibraryIndexJobStatus`, riga ~506)
- Test: `backend/tests/test_library_index_incremental.py` (aggiunte)

**Interfaces:**
- Consumes: `local_mtime`/`local_size` dal Task 1.
- Produces: `index_library` con chiave report `unchanged: int`; file invariato ⇒ nessuna chiamata a `audio_hash`/`read_tags`, ma il path conta come "visto" per la riconciliazione e il suo hash noto entra in `seen_digests`.

- [ ] **Step 1: Scrivi i test che falliscono**

In coda a `backend/tests/test_library_index_incremental.py`:

```python
def test_file_invariato_niente_rehash(db, fake_audio, monkeypatch):
    """Secondo run senza modifiche: 0 hash calcolati, contatore unchanged, niente lost."""
    from app.services import library_index as li
    from app.services.library_index import index_library

    make, root = fake_audio
    make("Techno/A/A - T1.mp3", digest="H1", artist="A", title="T1")
    index_library(db, root=root)  # primo run: aggancia

    calls = []
    original = li.audio_hash
    monkeypatch.setattr(li, "audio_hash", lambda p: calls.append(p) or original(p))
    report = index_library(db, root=root)  # secondo run: tutto invariato

    assert calls == []                      # nessun ri-hash
    assert report["unchanged"] == 1
    assert report["scanned"] == 1
    assert report["lost"] == 0              # il file "visto" non risulta perso
    assert report["matched"] == 0           # non ha rifatto il match


def test_file_modificato_viene_rielaborato(db, fake_audio):
    """mtime/size cambiati: il file rientra nel flusso completo."""
    import os
    from app.services.library_index import index_library

    make, root = fake_audio
    p = make("Techno/A/A - T1.mp3", digest="H1", artist="A", title="T1")
    index_library(db, root=root)

    p.write_bytes(b"xy")  # size cambia
    os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 10))
    report = index_library(db, root=root)

    assert report["unchanged"] == 0
    assert report["matched"] == 1  # riagganciato per hash


def test_duplicato_di_file_invariato_rilevato(db, fake_audio):
    """L'hash del file skippato entra in seen_digests: un duplicato nuovo si conta."""
    from app.services.library_index import index_library

    make, root = fake_audio
    make("Techno/A/A - T1.mp3", digest="H1", artist="A", title="T1")
    index_library(db, root=root)

    make("House/A/A - T1 copia.mp3", digest="H1")  # stesso audio altrove
    report = index_library(db, root=root)

    assert report["unchanged"] == 1
    assert report["duplicates"] == 1
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/test_library_index_incremental.py -v`
Expected: i 3 nuovi FAIL con `KeyError: 'unchanged'`

- [ ] **Step 3: Implementa lo skip**

In `backend/app/services/library_index.py`, dentro `index_library`:

Nel dict `report` iniziale aggiungi la chiave:

```python
    report = {"scanned": len(files), "matched": 0, "created": 0,
              "relinked": 0, "duplicates": 0, "lost": 0, "failed": 0,
              "unchanged": 0, "errors": []}
```

All'inizio del corpo del loop `for i, path in enumerate(files, start=1):`, PRIMA del blocco `try: digest = audio_hash(path)`:

```python
        # Incrementale: path noto con mtime+size invariati => niente ri-hash.
        resolved = str(path.resolve())
        stat = path.stat()
        known = db.scalar(select(Track).where(Track.local_path == resolved))
        if (known is not None and known.local_mtime == stat.st_mtime
                and known.local_size == stat.st_size):
            report["unchanged"] += 1
            seen_paths.add(resolved)
            if known.audio_hash:
                seen_digests.add(known.audio_hash)
            if on_progress is not None:
                on_progress(i, len(files))
            continue
```

(`select` e `Track` sono già importati nel modulo.)

In `backend/app/services/library_index_job.py`:

- nel dict `_state` iniziale aggiungi `"unchanged": 0,` accanto a `"duplicates": 0,`
- nelle DUE tuple di chiavi copiate dal report in `_run_job` (`_state.update(status="done", ...)` e il log) aggiungi `"unchanged"`:

```python
        _state.update(status="done", **{k: report[k] for k in
                      ("scanned", "matched", "created", "relinked", "duplicates", "lost", "failed", "unchanged", "errors")})
        logger.info("Indicizzazione libreria completata: %s", {
            k: report[k] for k in ("scanned", "matched", "created", "relinked", "lost", "failed", "unchanged")})
```

- in `start_job`, nell'`_state.update(...)` di reset aggiungi `unchanged=0,` accanto a `duplicates=0,`.

In `backend/app/schemas.py`, `LibraryIndexJobStatus`, dopo `duplicates: int = 0`:

```python
    unchanged: int = 0
```

- [ ] **Step 4: Verifica che passino + suite**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/test_library_index_incremental.py -v && .venv/bin/python -m pytest tests/ -q`
Expected: tutti PASS (attenzione ai test esistenti di `test_library_index.py`: lo skip non deve cambiare i loro esiti perché lì ogni run parte da file appena creati)

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add backend/app/services/library_index.py backend/app/services/library_index_job.py backend/app/schemas.py backend/tests/test_library_index_incremental.py
git commit -m "feat: indicizzazione incrementale (skip file invariati, contatore unchanged)"
```

---

### Task 3: Scansione automatica all'avvio

**Files:**
- Modify: `backend/app/main.py` (lifespan, righe ~29-34)
- Test: `backend/tests/test_startup_index.py` (nuovo)

**Interfaces:**
- Consumes: `library_index_job.start_job()` esistente (no-op se già in corso); `settings.library_root`.
- Produces: all'avvio dell'app (lifespan), se `LIBRARY_ROOT` è configurata parte il job in background. Nessun nuovo simbolo per altri task.

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `backend/tests/test_startup_index.py`:

```python
"""Avvio: se LIBRARY_ROOT è configurata, l'indicizzazione parte da sola."""
from fastapi.testclient import TestClient

from app.main import app


def test_avvio_lancia_indicizzazione(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import library_index_job

    called = []
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(library_index_job, "start_job", lambda: called.append(True) or {})

    with TestClient(app):  # il context manager esegue il lifespan
        pass
    assert called == [True]


def test_avvio_senza_library_root_non_lancia(monkeypatch):
    from app.core.config import settings
    from app.services import library_index_job

    called = []
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(library_index_job, "start_job", lambda: called.append(True) or {})

    with TestClient(app):
        pass
    assert called == []
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/test_startup_index.py -v`
Expected: `test_avvio_lancia_indicizzazione` FAIL (`called == []`), l'altro PASS

**Nota per l'implementatore:** il monkeypatch sostituisce `start_job` sull'oggetto modulo `library_index_job`, quindi `main.py` DEVE chiamarlo come attributo del modulo (`library_index_job.start_job()`), non importare la funzione direttamente.

- [ ] **Step 3: Implementa**

In `backend/app/main.py`:

Aggiungi l'import (dopo `from app.db import ensure_schema`):

```python
from app.services import library_index_job
```

Modifica il lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    ensure_schema()
    # Disk-first: il disco È la libreria — riallineala a ogni avvio.
    # Il job è un thread daemon in background: non blocca l'avvio; con la
    # scansione incrementale il costo dei run ripetuti è minimo.
    if settings.library_root:
        library_index_job.start_job()
    yield
```

- [ ] **Step 4: Verifica che passino + suite completa**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/test_startup_index.py -v && .venv/bin/python -m pytest tests/ -q`
Expected: tutti PASS. Attenzione: gli altri test che usano `TestClient(app)` come context manager ora eseguono il lifespan — se qualcuno fallisse per il job avviato, la causa è `settings.library_root` non vuoto nell'ambiente di test: in tal caso monkeypatchare `library_root=""` in quel test, NON cambiare il lifespan.

- [ ] **Step 5: Smoke test reale e commit**

Run (dalla cartella `backend`):

```bash
(.venv/bin/uvicorn app.main:app --port 8766 > /tmp/smoke-a.log 2>&1 &) && sleep 4 && curl -s http://127.0.0.1:8766/api/library/index/status | .venv/bin/python -m json.tool; pkill -f "port 8766"
```

Expected: `status` = `running` o `done` (non `idle`), con `unchanged` valorizzato al secondo avvio.

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add backend/app/main.py backend/tests/test_startup_index.py
git commit -m "feat: indicizzazione automatica all'avvio del backend"
```
