# Miniature delle copertine nelle tabelle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrare la copertina di ogni traccia (32px) nelle tabelle di FILES, ISSUES, DUPLICATES e PLAN, generandola on-demand dall'artwork embeddato nei file e cachandola su disco.

**Architecture:** `tagio.read_cover()` estrae i byte dell'artwork dai tag; `services/thumbs.py` li ridimensiona con Pillow a 96px e li cacha in `data/thumb_cache/{file_id}.jpg`, invalidando per mtime del file audio; `GET /api/files/{file_id}/thumb` serve la miniatura con fallback alla proposta provider già in `cover_cache`; il frontend usa un unico componente `<CoverThumb>` in tutte e quattro le tabelle.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, mutagen, **Pillow** (nuova), pytest — Next.js 16, React 19, Tailwind v4, TypeScript.

**Spec:** `docs/superpowers/specs/2026-07-21-cover-thumbnails-in-tables-design.md`

## Global Constraints

- **Venv obbligatorio:** i test girano con `backend/.venv/bin/python`, mai col Python di sistema (3.9 rompe su `X | None`). Tutti i comandi di questo piano si lanciano dalla **radice del repo**.
- `pytest.ini` ha `filterwarnings = error`: un warning nuovo fa fallire la suite.
- Commenti e docstring del **backend in italiano** (stile esistente). Il frontend segue lo stile del file che si tocca.
- Stringhe UI: la chiave si aggiunge **prima** in `frontend/lib/i18n/en.ts`, poi si traduce in `it.ts` (che è tipizzato su `en`, quindi una chiave mancante è un errore di tipo).
- Una miniatura non deve **mai** produrre un 500 né rompere la riga: ogni errore di lettura/decodifica diventa 404 → placeholder.
- Branch di lavoro: `feat/cover-thumbnails` (già creato, contiene lo spec).
- Dimensione miniatura a schermo: **32px**. Lato lungo della thumb cachata: **96px**.

---

## File Structure

**Backend**
- `backend/app/integrations/tagio.py` — *modifica*: aggiunge `read_cover()`, speculare a `write_cover()`.
- `backend/app/services/thumbs.py` — *nuovo*: cache su disco + ridimensionamento delle cover **embeddate**. Gemello di `cover_cache.py` (che resta dedicato alle cover **proposte** dai provider).
- `backend/app/core/config.py` — *modifica*: `thumb_cache_dir`.
- `backend/app/routers/library.py` — *modifica*: endpoint `GET /files/{file_id}/thumb` + `cover_source` nella query di `list_files`.
- `backend/app/schemas.py` — *modifica*: `FileRow.cover_source`.
- `backend/requirements.txt`, `DEPENDENCIES.md` — *modifica*: Pillow.

**Frontend**
- `frontend/components/cover-thumb.tsx` — *nuovo*: il componente condiviso dalle quattro tabelle.
- `frontend/app/globals.css` — *modifica*: classe `.cv-none` (placeholder dither).
- `frontend/lib/api.ts` — *modifica*: `fileThumbUrl()` + `FileRow.cover_source`.
- `frontend/lib/i18n/en.ts`, `it.ts` — *modifica*: due chiavi in `common`.
- `frontend/components/files-table.tsx` — *modifica*: colonna miniatura + path troncato a sinistra.
- `frontend/components/dup-group.tsx`, `plan-ops.tsx`, `issues-table.tsx` — *modifica*: miniatura nella riga.

---

### Task 1: `tagio.read_cover()` — estrarre l'artwork dai tag

**Files:**
- Modify: `backend/app/integrations/tagio.py` (dopo `remove_cover`, riga 258)
- Test: `backend/tests/test_tagio_cover.py` (esiste già, si aggiunge in coda)

**Interfaces:**
- Consumes: niente (primo task).
- Produces: `tagio.read_cover(path: str) -> bytes | None` — byte grezzi dell'immagine embeddata (front cover se distinguibile), `None` se non c'è o il file è illeggibile. **Non solleva mai.**

- [ ] **Step 1: Scrivere i test che falliscono**

In coda a `backend/tests/test_tagio_cover.py` (la costante `_JPG` è già definita in cima al file):

```python
@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff", "wav"])
def test_read_cover_roundtrip(copy_fixture, tmp_path, fmt):
    f = copy_fixture(fmt, tmp_path / f"a.{fmt}")
    assert tagio.read_cover(f) is None       # fixture pulita
    tagio.write_cover(f, _JPG)
    assert tagio.read_cover(f) == _JPG


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff", "wav"])
def test_read_cover_after_remove(copy_fixture, tmp_path, fmt):
    f = copy_fixture(fmt, tmp_path / f"a.{fmt}")
    tagio.write_cover(f, _JPG)
    tagio.remove_cover(f)
    assert tagio.read_cover(f) is None


def test_read_cover_unreadable_file(tmp_path):
    """Un file che non è audio non deve sollevare: è semplicemente senza cover."""
    p = tmp_path / "nope.mp3"
    p.write_bytes(b"questo non e' audio")
    assert tagio.read_cover(str(p)) is None


def test_read_cover_missing_file(tmp_path):
    assert tagio.read_cover(str(tmp_path / "fantasma.flac")) is None
```

- [ ] **Step 2: Lanciare i test e verificare che falliscano**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_tagio_cover.py -q`
Expected: FAIL — `AttributeError: module 'app.integrations.tagio' has no attribute 'read_cover'`

- [ ] **Step 3: Implementare `read_cover`**

In `backend/app/integrations/tagio.py`, subito dopo `remove_cover`:

```python
def read_cover(path: str) -> bytes | None:
    """Byte della copertina embeddata (front cover se distinguibile), o None.
    Speculare a write_cover. Non solleva: un file illeggibile è, ai fini della
    miniatura, un file senza copertina."""
    try:
        raw = MutagenFile(path)
    except (MutagenError, OSError):
        return None
    if raw is None:
        return None
    pictures = getattr(raw, "pictures", None)
    if pictures:  # FLAC
        front = next((p for p in pictures if p.type == 3), pictures[0])
        return bytes(front.data)
    tags = getattr(raw, "tags", None)
    if tags is None:
        return None
    if hasattr(tags, "getall"):  # ID3: mp3, wav, aiff
        apics = tags.getall("APIC")
        if apics:
            front = next((a for a in apics if a.type == 3), apics[0])
            return bytes(front.data)
    try:
        covers = tags.get("covr")  # MP4 (m4a)
    except (TypeError, AttributeError):
        return None
    return bytes(covers[0]) if covers else None
```

- [ ] **Step 4: Lanciare i test e verificare che passino**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_tagio_cover.py -q`
Expected: PASS (13 test: 3 preesistenti + 10 nuovi)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/tagio.py backend/tests/test_tagio_cover.py
git commit -m "feat(tagio): read_cover() per estrarre l'artwork embeddato"
```

---

### Task 2: `services/thumbs.py` — generazione e cache delle miniature

**Files:**
- Create: `backend/app/services/thumbs.py`
- Create: `backend/tests/test_thumbs.py`
- Modify: `backend/app/core/config.py` (dopo `cover_cache_dir`, riga 27)
- Modify: `backend/requirements.txt`
- Modify: `DEPENDENCIES.md`

**Interfaces:**
- Consumes: `tagio.read_cover(path) -> bytes | None` (Task 1).
- Produces:
  - `thumbs.THUMB_MAX_PX: int = 96`
  - `thumbs.thumb_path(file_id: int) -> str`
  - `thumbs.get_thumb(file_id: int, audio_path: str) -> bytes | None` — JPEG pronto da servire, dalla cache o rigenerato.
  - `settings.thumb_cache_dir: str = "./data/thumb_cache"`

- [ ] **Step 1: Installare Pillow e dichiararlo**

Aggiungere `Pillow` a `backend/requirements.txt`, in coda alla lista:

```
pyacoustid
Pillow
```

Poi installarlo nel venv:

```bash
backend/.venv/bin/pip install Pillow
```

In `DEPENDENCIES.md`, nella tabella "Backend — Python", aggiungere una riga dopo `pyacoustid`:

```markdown
| `Pillow`            | Ridimensiona le copertine embeddate in miniature 96px (`services/thumbs.py`). Obbligatoria: le cover nei tag arrivano a diversi MB. |
```

- [ ] **Step 2: Aggiungere `thumb_cache_dir` alla config**

In `backend/app/core/config.py`, subito dopo `cover_cache_dir`:

```python
    # Cache thumbnail delle cover **embeddate** nei file, generate on-demand.
    # Separata da cover_cache_dir: entrambe indicizzano per {file_id}.jpg e
    # condividerle confonderebbe l'artwork reale con la proposta di un provider.
    thumb_cache_dir: str = "./data/thumb_cache"
```

- [ ] **Step 3: Scrivere i test che falliscono**

Creare `backend/tests/test_thumbs.py`:

```python
"""Miniature generate dall'artwork embeddato: generazione, cache, invalidazione."""

import io
import os

import pytest
from PIL import Image

from app.core.config import settings
from app.integrations import tagio
from app.services import thumbs


def _jpeg(size=(500, 400), color=(200, 30, 30)) -> bytes:
    """JPEG vero: Pillow deve poterlo aprire (il _JPG dei test tagio è un
    header senza dati e non è decodificabile)."""
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    d = tmp_path / "tc"
    monkeypatch.setattr(settings, "thumb_cache_dir", str(d))
    return d


def test_get_thumb_generates_and_caches(copy_fixture, tmp_path, cache_dir):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg())

    data = thumbs.get_thumb(1, f)

    assert data is not None
    assert os.path.exists(cache_dir / "1.jpg")
    img = Image.open(io.BytesIO(data))
    assert max(img.size) == thumbs.THUMB_MAX_PX   # 500x400 → 96x76
    assert img.format == "JPEG"


def test_get_thumb_second_call_reads_the_cache(copy_fixture, tmp_path, cache_dir, monkeypatch):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg())
    first = thumbs.get_thumb(1, f)

    calls = []
    monkeypatch.setattr(thumbs.tagio, "read_cover", lambda p: calls.append(p))
    assert thumbs.get_thumb(1, f) == first
    assert calls == []          # il file audio non è stato riaperto


def test_get_thumb_invalidated_by_mtime(copy_fixture, tmp_path, cache_dir):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg(color=(200, 30, 30)))
    red = thumbs.get_thumb(1, f)

    tagio.write_cover(f, _jpeg(color=(30, 30, 200)))
    future = os.path.getmtime(f) + 10
    os.utime(f, (future, future))   # deterministico: l'audio è più recente della thumb

    assert thumbs.get_thumb(1, f) != red


def test_get_thumb_without_cover_is_none(copy_fixture, tmp_path, cache_dir):
    f = copy_fixture("flac", tmp_path / "a.flac")
    assert thumbs.get_thumb(1, f) is None
    assert not os.path.exists(cache_dir / "1.jpg")


def test_get_thumb_missing_file_is_none(tmp_path, cache_dir):
    assert thumbs.get_thumb(1, str(tmp_path / "fantasma.flac")) is None


def test_get_thumb_corrupt_artwork_is_none(copy_fixture, tmp_path, cache_dir):
    """Artwork che Pillow non sa aprire: trattato come 'senza copertina'."""
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, b"questa non e' un'immagine")
    assert thumbs.get_thumb(1, f) is None
```

- [ ] **Step 4: Lanciare i test e verificare che falliscano**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_thumbs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.thumbs'`

- [ ] **Step 5: Implementare il servizio**

Creare `backend/app/services/thumbs.py`:

```python
"""Miniature delle copertine **già embeddate** nei file: generate alla prima
richiesta, cachate su disco, invalidate dall'mtime del file audio.

Gemello di cover_cache.py, che invece ospita le copertine *proposte* dai
provider e non richiede né lettura del file né ridimensionamento."""

import io
import os

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.integrations import tagio

# 3x rispetto ai 32px a schermo: nitida su display retina, ~4 KB per file.
THUMB_MAX_PX = 96


def _dir() -> str:
    os.makedirs(settings.thumb_cache_dir, exist_ok=True)
    return settings.thumb_cache_dir


def thumb_path(file_id: int) -> str:
    return os.path.join(_dir(), f"{file_id}.jpg")


def _render(data: bytes) -> bytes | None:
    """Ridimensiona a THUMB_MAX_PX (lato lungo) e ricodifica in JPEG.
    None se l'immagine non è decodificabile: artwork rotto = nessuna cover."""
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80)
        return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def get_thumb(file_id: int, audio_path: str) -> bytes | None:
    """Miniatura JPEG della cover embeddata, dalla cache o rigenerata.
    La cache è valida finché è più recente del file audio: apply, undo e
    ri-taggature cambiano l'mtime e quindi la invalidano da sé."""
    try:
        audio_mtime = os.path.getmtime(audio_path)
    except OSError:
        return None
    cached = thumb_path(file_id)
    if os.path.exists(cached) and os.path.getmtime(cached) >= audio_mtime:
        with open(cached, "rb") as fh:
            return fh.read()
    raw = tagio.read_cover(audio_path)
    if raw is None:
        return None
    thumb = _render(raw)
    if thumb is None:
        return None
    with open(cached, "wb") as fh:
        fh.write(thumb)
    return thumb
```

- [ ] **Step 6: Lanciare i test e verificare che passino**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_thumbs.py -q`
Expected: PASS (6 test)

- [ ] **Step 7: Lanciare la suite intera (Pillow non deve introdurre warning)**

Run: `backend/.venv/bin/python -m pytest backend/tests -q`
Expected: PASS, nessun errore da `filterwarnings = error`

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/thumbs.py backend/tests/test_thumbs.py \
        backend/app/core/config.py backend/requirements.txt DEPENDENCIES.md
git commit -m "feat(thumbs): cache su disco delle miniature dalle cover embeddate"
```

---

### Task 3: endpoint `GET /api/files/{file_id}/thumb`

**Files:**
- Modify: `backend/app/routers/library.py` (import in testa, riga 4-10; nuova route in coda)
- Create: `backend/tests/test_file_thumb_api.py`

**Interfaces:**
- Consumes: `thumbs.get_thumb(file_id, audio_path)` (Task 2), `cover_cache.read_thumb(file_id)` (esistente in `app/services/cover_cache.py`), `api_error(status, code, message)` da `app.core.http_errors`.
- Produces: `GET /api/files/{file_id}/thumb` → `200 image/jpeg` con header `ETag` e `Cache-Control: no-cache`, `304` su `If-None-Match` combaciante, `404` se non c'è niente da mostrare.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_file_thumb_api.py`:

```python
"""Endpoint miniatura: embedded → proposta provider → 404."""

import io

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.integrations import tagio
from app.main import app
from app.models import AudioFile, ScanRoot
from app.services import cover_cache


def _jpeg(color=(10, 200, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color).save(buf, format="JPEG")
    return buf.getvalue()


def _seed(db, path: str, *, has_cover: bool, file_id: int = 1) -> None:
    db.add(ScanRoot(id=1, path="/m", label="M"))
    db.add(AudioFile(id=file_id, root_id=1, path=path, ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=has_cover))
    db.commit()


def test_thumb_from_embedded_cover(db, copy_fixture, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg())
    _seed(db, f, has_cover=True)

    with TestClient(app) as client:
        r = client.get("/api/files/1/thumb")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(r.content)).format == "JPEG"


def test_thumb_falls_back_to_provider_proposal(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    _seed(db, "/m/senza-cover.flac", has_cover=False)
    cover_cache.save_thumb(1, b"\xff\xd8proposta")

    with TestClient(app) as client:
        r = client.get("/api/files/1/thumb")
    assert r.status_code == 200
    assert r.content == b"\xff\xd8proposta"


def test_thumb_404_when_nothing_available(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    _seed(db, "/m/senza-cover.flac", has_cover=False)

    with TestClient(app) as client:
        assert client.get("/api/files/1/thumb").status_code == 404


def test_thumb_404_for_unknown_file(db):
    with TestClient(app) as client:
        assert client.get("/api/files/999/thumb").status_code == 404


def test_thumb_does_not_open_file_when_has_cover_is_false(db, tmp_path, monkeypatch):
    """has_cover=False è la cache negativa: il file non va nemmeno aperto."""
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    _seed(db, "/m/senza-cover.flac", has_cover=False)

    def _boom(*a, **kw):
        raise AssertionError("get_thumb non deve essere chiamata")

    from app.routers import library
    monkeypatch.setattr(library.thumbs, "get_thumb", _boom)

    with TestClient(app) as client:
        assert client.get("/api/files/1/thumb").status_code == 404


def test_thumb_304_on_matching_etag(db, copy_fixture, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thumb_cache_dir", str(tmp_path / "tc"))
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg())
    _seed(db, f, has_cover=True)

    with TestClient(app) as client:
        first = client.get("/api/files/1/thumb")
        again = client.get("/api/files/1/thumb",
                           headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""
```

- [ ] **Step 2: Lanciare i test e verificare che falliscano**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_file_thumb_api.py -q`
Expected: FAIL — tutte 404 (route inesistente) e `AttributeError` su `library.thumbs`

- [ ] **Step 3: Implementare la route**

In `backend/app/routers/library.py`, sostituire il blocco di import (righe 1-11) con:

```python
"""Router LIBRARY: letture read-only per il frontend (statistiche + lista file).
Router sottile: query dirette, nessun servizio nuovo."""

import os

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.models import AudioFile, DupGroup, DupMember, Issue, ScanRoot
from app.schemas import FileRow, LibraryFacets, LibraryStatsRead
from app.services import cover_cache, thumbs

router = APIRouter(prefix="/api", tags=["library"])
```

Poi, **in coda al file**, la nuova route:

```python
@router.get("/files/{file_id}/thumb")
def file_thumb(file_id: int, request: Request, db: Session = Depends(get_db)):
    """Miniatura della traccia: l'artwork embeddato se c'è, altrimenti la
    copertina proposta dai provider già in cache. 404 se non c'è nulla — il
    frontend disegna il placeholder e non ritenta."""
    f = db.get(AudioFile, file_id)
    if f is None:
        raise api_error(404, "file_not_found", "File not found")

    # ETag sull'mtime del *file audio*: un apply che riscrive i tag invalida
    # anche la copia nel browser, non solo quella su disco.
    try:
        stamp = str(os.path.getmtime(f.path))
    except OSError:
        stamp = "0"
    etag = f'W/"{file_id}-{stamp}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})

    data = thumbs.get_thumb(file_id, f.path) if f.has_cover else None
    if data is None:
        data = cover_cache.read_thumb(file_id)
    if data is None:
        raise api_error(404, "thumb_missing", "No thumbnail")
    return Response(content=data, media_type="image/jpeg",
                    headers={"ETag": etag, "Cache-Control": "no-cache"})
```

- [ ] **Step 4: Lanciare i test e verificare che passino**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_file_thumb_api.py -q`
Expected: PASS (6 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/library.py backend/tests/test_file_thumb_api.py
git commit -m "feat(api): GET /api/files/{id}/thumb con fallback alla proposta provider"
```

---

### Task 4: `FileRow.cover_source`

**Files:**
- Modify: `backend/app/schemas.py:233-249` (classe `FileRow`)
- Modify: `backend/app/routers/library.py` (funzione `list_files`, righe ~101-155)
- Test: `backend/tests/test_library_api.py` (esiste già, si aggiunge in coda)

**Interfaces:**
- Consumes: niente dai task precedenti (è indipendente da 1-3).
- Produces: campo JSON `cover_source: "embedded" | "provider" | null` in ogni riga di `GET /api/files`.

- [ ] **Step 1: Scrivere i test che falliscono**

In coda a `backend/tests/test_library_api.py`:

```python
def test_list_files_cover_source(db):
    db.add(ScanRoot(id=1, path="/m", label="M"))
    db.add(AudioFile(id=1, root_id=1, path="/m/con-cover.flac", ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=True))
    db.add(AudioFile(id=2, root_id=1, path="/m/proposta.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(AudioFile(id=3, root_id=1, path="/m/niente.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    # la proposta provider esiste solo come issue missing_cover aperta
    db.add(Issue(file_id=2, type="missing_cover", field="cover", severity="info",
                 detail="x", suggested_fix_json={"thumb_ref": "cover_cache/2.jpg"},
                 status="open"))
    # una accettata NON è più una proposta da mostrare come tale
    db.add(Issue(file_id=3, type="missing_cover", field="cover", severity="info",
                 detail="x", suggested_fix_json=None, status="accepted"))
    db.commit()

    with TestClient(app) as client:
        rows = {r["id"]: r["cover_source"] for r in client.get("/api/files").json()}
    assert rows == {1: "embedded", 2: "provider", 3: None}
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_library_api.py::test_list_files_cover_source -q`
Expected: FAIL — `KeyError: 'cover_source'`

- [ ] **Step 3: Aggiungere il campo allo schema**

In `backend/app/schemas.py`, dentro `class FileRow`, dopo `in_dup_group: bool`:

```python
    # "embedded" = artwork nei tag, "provider" = solo una proposta in cache,
    # None = niente da mostrare (il frontend salta del tutto la richiesta).
    cover_source: str | None = None
```

- [ ] **Step 4: Calcolarlo nella query**

In `backend/app/routers/library.py`, dentro `list_files`, dopo la scalar-subquery `in_dup` (riga ~119) aggiungere:

```python
    cover_proposal = (
        select(func.count())
        .select_from(Issue)
        .where(Issue.file_id == AudioFile.id, Issue.type == "missing_cover",
               Issue.status == "open")
        .scalar_subquery()
    )
```

Cambiare la `select` principale (riga ~121) da:

```python
    stmt = select(AudioFile, issue_count, worst_rank, in_dup).where(
        AudioFile.status == status
    )
```

a:

```python
    stmt = select(AudioFile, issue_count, worst_rank, in_dup, cover_proposal).where(
        AudioFile.status == status
    )
```

E il ciclo finale (righe ~146-154) da:

```python
    rows = []
    for f, n_issues, rank, dup_n in db.execute(stmt).all():
        rows.append(FileRow(
            id=f.id, root_id=f.root_id, path=f.path, ext=f.ext,
            artist=f.artist, title=f.title, album=f.album, genre=f.genre,
            year=f.year, label=f.label, bitrate=f.bitrate, duration_s=f.duration_s,
            status=f.status, issue_count=n_issues or 0,
            worst_severity=_RANK_SEV.get(rank or 0), in_dup_group=bool(dup_n),
        ))
    return rows
```

a:

```python
    rows = []
    for f, n_issues, rank, dup_n, cover_n in db.execute(stmt).all():
        rows.append(FileRow(
            id=f.id, root_id=f.root_id, path=f.path, ext=f.ext,
            artist=f.artist, title=f.title, album=f.album, genre=f.genre,
            year=f.year, label=f.label, bitrate=f.bitrate, duration_s=f.duration_s,
            status=f.status, issue_count=n_issues or 0,
            worst_severity=_RANK_SEV.get(rank or 0), in_dup_group=bool(dup_n),
            cover_source="embedded" if f.has_cover else ("provider" if cover_n else None),
        ))
    return rows
```

- [ ] **Step 5: Lanciare i test e verificare che passino**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_library_api.py -q`
Expected: PASS (tutti i test del file, compreso il nuovo)

- [ ] **Step 6: Lanciare la suite backend intera**

Run: `backend/.venv/bin/python -m pytest backend/tests -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/library.py backend/tests/test_library_api.py
git commit -m "feat(api): cover_source in FileRow (embedded/provider/null)"
```

---

### Task 5: componente `<CoverThumb>` + placeholder + i18n

**Files:**
- Create: `frontend/components/cover-thumb.tsx`
- Modify: `frontend/app/globals.css` (in coda, dopo il blocco dei loader)
- Modify: `frontend/lib/api.ts` (interfaccia `FileRow` righe 45-62; nuova funzione accanto a `coverThumbUrl`, riga 257)
- Modify: `frontend/lib/i18n/en.ts` (sezione `common`, riga 29), `frontend/lib/i18n/it.ts` (sezione `common`)

**Interfaces:**
- Consumes: `GET /api/files/{id}/thumb` (Task 3), `FileRow.cover_source` (Task 4).
- Produces:
  - `fileThumbUrl(fileId: number): string` in `lib/api.ts`
  - `type CoverSource = "embedded" | "provider" | null`
  - `<CoverThumb fileId={number} size?={number} source?={CoverSource} />` — `source` omesso (`undefined`) = "prova a caricarla e ricadi sul placeholder"; `source === null` = "non c'è nulla, non fare la richiesta".

- [ ] **Step 1: Aggiungere la classe placeholder al design system**

In coda a `frontend/app/globals.css`:

```css
/* ---- Miniature copertine ------------------------------------------------- */
/* Placeholder "nessuna copertina": stesso dither a scacchiera di .eqm-rest,
   così un buco nella tabella resta coerente col resto del sistema. */
.cv-none {
  background-image: conic-gradient(var(--c-border-strong) 0 90deg, transparent 90deg 180deg, var(--c-border-strong) 180deg 270deg, transparent 270deg 360deg);
  background-size: 4px 4px;
  opacity: 0.45;
}
```

- [ ] **Step 2: Aggiungere URL e tipo al client API**

In `frontend/lib/api.ts`, dentro `export interface FileRow`, dopo `in_dup_group: boolean;`:

```ts
  cover_source: "embedded" | "provider" | null;
```

E accanto a `coverThumbUrl` (riga 257):

```ts
/** Miniatura della traccia: artwork embeddato, o proposta provider come fallback. */
export function fileThumbUrl(fileId: number): string {
  return `${API}/api/files/${fileId}/thumb`;
}
```

- [ ] **Step 3: Aggiungere le chiavi i18n**

In `frontend/lib/i18n/en.ts`, dentro `common`, dopo `never: "never",`:

```ts
    coverAlt: "cover",
    coverProposed: "Cover proposed by a provider — not embedded in the file yet",
```

In `frontend/lib/i18n/it.ts`, nella stessa posizione dentro `common`:

```ts
    coverAlt: "copertina",
    coverProposed: "Copertina proposta da un provider — non ancora nel file",
```

- [ ] **Step 4: Scrivere il componente**

Creare `frontend/components/cover-thumb.tsx`:

```tsx
"use client";

import { useState } from "react";
import { fileThumbUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

export type CoverSource = "embedded" | "provider" | null;

/** Miniatura quadrata della traccia, condivisa da FILES, ISSUES, DUPLICATES e PLAN.
 *
 * `source` arriva solo da FILES (l'unica lista che lo espone): quando è `null` si
 * disegna il placeholder senza nemmeno fare la richiesta, quando è `"provider"` la
 * copertina è tratteggiata perché è una proposta, non ciò che c'è nel file.
 * Nelle altre liste si omette e si ricade sul placeholder via `onError`. */
export function CoverThumb({ fileId, size = 32, source }: {
  fileId: number;
  size?: number;
  source?: CoverSource;
}) {
  const t = useT();
  const [failed, setFailed] = useState(false);
  const box = { width: size, height: size };

  if (source === null || failed) {
    return <span aria-hidden className="cv-none block shrink-0 border border-border" style={box} />;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={fileThumbUrl(fileId)}
      alt={t.common.coverAlt}
      title={source === "provider" ? t.common.coverProposed : undefined}
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      style={box}
      className={cn("block shrink-0 border border-border object-cover",
        source === "provider" && "border-dashed opacity-50")}
    />
  );
}
```

- [ ] **Step 5: Verificare tipi e lint**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore ESLint, build completata. (Se `it.ts` non ha entrambe le chiavi, il build fallisce con un errore di tipo: è il comportamento voluto.)

- [ ] **Step 6: Commit**

```bash
git add frontend/components/cover-thumb.tsx frontend/app/globals.css \
        frontend/lib/api.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts
git commit -m "feat(ui): componente CoverThumb + placeholder dither + chiavi i18n"
```

---

### Task 6: FILES — colonna miniatura e path troncato a sinistra

**Files:**
- Modify: `frontend/components/files-table.tsx:67-97` (`FilesTable`)

**Interfaces:**
- Consumes: `<CoverThumb>` e `CoverSource` (Task 5), `FileRow.cover_source` (Task 4).
- Produces: niente per i task successivi.

- [ ] **Step 1: Importare il componente**

In testa a `frontend/components/files-table.tsx`, dopo gli import esistenti:

```tsx
import { CoverThumb } from "@/components/cover-thumb";
```

- [ ] **Step 2: Aggiungere la colonna in intestazione**

Nel `<thead>`, come **prima** cella della riga (prima di `<SortHead label="Path" …>`):

```tsx
            <th className="w-8 px-3 py-2" aria-label="cover" />
```

- [ ] **Step 3: Aggiungere la miniatura e troncare il path a sinistra**

Sostituire il `<tr>` del corpo (righe 83-91) con:

```tsx
            <tr key={r.id} className="border-b border-surface-2 last:border-0 hover:bg-surface">
              <td className="py-1 pl-3 pr-0">
                <CoverThumb fileId={r.id} source={r.cover_source} />
              </td>
              {/* dir=rtl porta l'ellissi in testa: si legge la coda del percorso
                  (il nome del file), non l'inizio sempre uguale */}
              <td className="max-w-[300px] px-3 py-1 text-muted" title={r.path}>
                <span dir="rtl" className="block truncate text-left">{r.path}</span>
              </td>
              <td className="px-3 py-1 text-fg">{r.artist || <span className="text-faint">—</span>}</td>
              <td className="px-3 py-1 text-fg-strong">{r.title || <span className="text-faint">—</span>}</td>
              <td className="px-3 py-1 uppercase text-muted">{r.ext}</td>
              <td className="tnum px-3 py-1 text-right text-fg">{r.bitrate ?? "—"}</td>
              <td className="tnum px-3 py-1 text-right text-fg">{fmtDuration(r.duration_s)}</td>
              <td className="px-3 py-1 text-center"><Indicator row={r} /></td>
            </tr>
```

(Il passaggio da `py-1.5` a `py-1` tiene la riga a ~40px con la miniatura da 32px invece di ~44px.)

- [ ] **Step 4: Verificare tipi e lint**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore

- [ ] **Step 5: Verifica visiva nel browser**

Avviare backend e frontend, aprire `/files` e controllare:
1. le righe con copertina la mostrano a 32px;
2. le righe senza mostrano il quadrato a scacchiera, **senza** richieste 404 in rete (il placeholder non fa richieste — verificabile nella scheda Network);
3. la colonna Path mostra la coda (`…/Artist - Title.flac`), non l'inizio;
4. lo scroll non scatta e non ci sono salti di layout.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/files-table.tsx
git commit -m "feat(files): miniatura copertina in tabella + path troncato a sinistra"
```

---

### Task 7: ISSUES, DUPLICATES e PLAN — miniatura nella riga

**Files:**
- Modify: `frontend/components/issues-table.tsx` (cella "track", righe 113-116)
- Modify: `frontend/components/dup-group.tsx:47-67` (riga membro)
- Modify: `frontend/components/plan-ops.tsx:26-63` (`OpRow`)

**Interfaces:**
- Consumes: `<CoverThumb>` (Task 5). In queste tre liste `source` **non** viene passato: gli schemi `Issue`, `DupMember` e `PlanOp` non espongono `cover_source` (scelta esplicita dello spec), quindi la miniatura tenta il caricamento e ricade sul placeholder via `onError`.
- Produces: niente.

- [ ] **Step 1: ISSUES — miniatura dentro la cella "track"**

In `frontend/components/issues-table.tsx`, aggiungere l'import in testa:

```tsx
import { CoverThumb } from "@/components/cover-thumb";
```

Sostituire la cella track (righe 113-116) con:

```tsx
      <td className="px-3 py-2 align-top">
        <div className="flex items-start gap-2">
          <CoverThumb fileId={issue.file_id} />
          <div className="min-w-0">
            <div className="text-fg-strong">{issue.artist || t.common.empty}{issue.title ? ` — ${issue.title}` : ""}</div>
            <div className="max-w-[240px] truncate text-[10px] text-faint" title={issue.file_path}>{issue.file_path}</div>
          </div>
        </div>
      </td>
```

La miniatura va **dentro** la cella esistente, non in una colonna nuova: `colCount` (riga 217) è usato come `colspan` delle righe di gruppo e resterebbe da ricalcolare in due punti per zero guadagno visivo.

- [ ] **Step 2: DUPLICATES — nuova colonna nella griglia**

In `frontend/components/dup-group.tsx`, aggiungere l'import in testa:

```tsx
import { CoverThumb } from "@/components/cover-thumb";
```

Cambiare la griglia della riga membro (riga 52) da:

```tsx
                "grid grid-cols-[64px_1fr_auto] items-center gap-3 border-b border-surface-2 px-3 py-1.5 last:border-0",
```

a:

```tsx
                "grid grid-cols-[32px_64px_1fr_auto] items-center gap-3 border-b border-surface-2 px-3 py-1.5 last:border-0",
```

e inserire la miniatura come **primo** figlio del `<div>` della riga, subito prima dello `<span>` con `KEEP`/`REMOVE`:

```tsx
              <CoverThumb fileId={m.file_id} />
```

- [ ] **Step 3: PLAN — miniatura in testa alla riga**

In `frontend/components/plan-ops.tsx`, aggiungere l'import in testa:

```tsx
import { CoverThumb } from "@/components/cover-thumb";
```

Nel `<div>` di `OpRow` (riga 30) cambiare `items-baseline` in `items-center` — con un'immagine nella riga l'allineamento alla baseline sballa:

```tsx
    <div className={cn("flex items-center gap-3 border border-t-0 border-surface-2 px-3 py-1.5 first:border-t",
```

e inserire la miniatura come **primo** figlio, prima del badge `op.skipped`:

```tsx
      <CoverThumb fileId={op.file_id} />
```

L'`<img>` già presente nel ramo `op.kind === "COVER"` (righe 40-42) **resta**: mostra la copertina che l'operazione sta per embeddare, che è il contenuto dell'op, non l'identità della traccia.

- [ ] **Step 4: Verificare tipi e lint**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore

- [ ] **Step 5: Verifica visiva nel browser**

Aprire le tre pagine e controllare:
1. `/issues` — la miniatura è allineata in alto accanto ad artista/titolo, e per le issue `missing_cover` la colonna "fix" mostra ancora la sua anteprima grande da 56px;
2. `/duplicates` — due membri dello stesso gruppo con copertine diverse si distinguono a colpo d'occhio; le colonne restano allineate;
3. `/plan` — la miniatura non sfalsa l'allineamento verticale del testo, e nelle op `COVER` si vedono due immagini (traccia a sinistra, copertina da embeddare al centro).

- [ ] **Step 6: Lanciare la suite backend intera un'ultima volta**

Run: `backend/.venv/bin/python -m pytest backend/tests -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/components/issues-table.tsx frontend/components/dup-group.tsx \
        frontend/components/plan-ops.tsx
git commit -m "feat(ui): miniatura copertina in ISSUES, DUPLICATES e PLAN"
```

---

## Note di integrazione

A implementazione finita il branch `feat/cover-thumbnails` va integrato con la
skill `superpowers:finishing-a-development-branch`. Il default per questo
progetto è **merge in `main` + push**.
