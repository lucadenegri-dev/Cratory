# Pipeline di Orientamento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendere visibile il flusso d'uso di Cratory: una pipeline a sei fasi con contatori vivi in dashboard, il menu raggruppato per fasi, e la card "Prossimo passo" estesa al ciclo cross-app (inbox → DjOrganizer → re-index).

**Architecture:** Un nuovo endpoint `GET /api/pipeline` aggrega in una chiamata i conteggi DB (playlist, tracce senza key, wishlist, pronte per set), i conteggi disco (file audio in inbox e in Libreria) e lo stato indicizzazione (persistito in una nuova mini-tabella KV `app_state`). Il frontend lo consuma in un componente `PipelineStrip` in cima alla dashboard e nella `recommend()` esistente. Il menu (`index-nav.tsx`) passa da lista piatta a gruppi.

**Tech Stack:** Backend Python/FastAPI + SQLAlchemy + pytest (348 test esistenti). Frontend Next.js app router + Tailwind (nessun test frontend: verifica con `npm run build`).

**Spec:** `docs/superpowers/specs/2026-07-02-pipeline-orientamento-design.md`

## Global Constraints

- Repo: `/Users/lucadenegri/Develop/DJProject01`. Backend in `backend/`, frontend in `frontend/`.
- Commenti, docstring e stringhe UI **in italiano** (convenzione del codebase).
- Niente Alembic: lo schema si crea con `Base.metadata.create_all` via `ensure_schema` (`backend/app/db.py`) — una nuova tabella non richiede migrazioni.
- Regola "mai sovrascrivere" (enrichment/manuale autorevoli) non toccata. Nessuna modifica a DjOrganizer o DJPlayer.
- Test backend: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/ -q` — devono restare tutti verdi.
- Build frontend: `cd /Users/lucadenegri/Develop/DJProject01/frontend && npm run build` — deve compilare senza errori.
- I test in-memory SQLite che condividono il DB tra sessione del test e route/job DEVONO usare `poolclass=StaticPool` (vedi `backend/tests/test_track_lookup.py` per il perché).

---

### Task 1: Modello `AppState` + helper get/set

Mini chiave-valore persistente. Oggi lo stato del job di indicizzazione è solo in memoria (`library_index_job._state`) e si perde al riavvio: `app_state` ospiterà `last_index_at`.

**Files:**
- Modify: `backend/app/models.py` (in coda al file)
- Create: `backend/app/services/app_state.py`
- Test: `backend/tests/test_app_state.py`

**Interfaces:**
- Consumes: `Base`, `utcnow` già definiti in `app/models.py`; fixture `db` di `tests/conftest.py`.
- Produces: `get_state(db: Session, key: str) -> str | None` e `set_state(db: Session, key: str, value: str) -> None` in `app.services.app_state` (usati dai Task 2 e 3). `set_state` fa commit.

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `backend/tests/test_app_state.py`:

```python
"""Mini chiave-valore app_state: stato applicativo persistente (es. last_index_at)."""
from app.services.app_state import get_state, set_state


def test_get_su_chiave_assente(db):
    assert get_state(db, "manca") is None


def test_set_e_get(db):
    set_state(db, "last_index_at", "2026-07-02T10:00:00+00:00")
    assert get_state(db, "last_index_at") == "2026-07-02T10:00:00+00:00"


def test_set_sovrascrive(db):
    set_state(db, "k", "v1")
    set_state(db, "k", "v2")
    assert get_state(db, "k") == "v2"
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/test_app_state.py -v`
Expected: FAIL/ERROR con `ModuleNotFoundError: No module named 'app.services.app_state'`

- [ ] **Step 3: Implementa modello e helper**

In `backend/app/models.py`, in coda al file, aggiungi:

```python
class AppState(Base):
    """Chiave-valore minimale per stato applicativo persistente (es. last_index_at:
    lo stato del job di indicizzazione vive in memoria e si perde al riavvio)."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
```

(`String`, `Text`, `DateTime`, `Mapped`, `mapped_column`, `datetime`, `utcnow` sono già importati/definiti in testa al file.)

Crea `backend/app/services/app_state.py`:

```python
"""Stato applicativo persistente: mini chiave-valore (niente Alembic, app locale).

Per fatti che devono sopravvivere al riavvio ma non meritano una tabella
dedicata: es. `last_index_at` (ultima indicizzazione libreria completata).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AppState


def get_state(db: Session, key: str) -> str | None:
    row = db.get(AppState, key)
    return row.value if row else None


def set_state(db: Session, key: str, value: str) -> None:
    row = db.get(AppState, key)
    if row is None:
        db.add(AppState(key=key, value=value))
    else:
        row.value = value
    db.commit()
```

- [ ] **Step 4: Verifica che passino**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/test_app_state.py -v`
Expected: 3 PASS

- [ ] **Step 5: Suite completa e commit**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/ -q`
Expected: tutti verdi (348 + 3 nuovi)

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add backend/app/models.py backend/app/services/app_state.py backend/tests/test_app_state.py
git commit -m "feat: tabella app_state (KV persistente) con helper get/set"
```

---

### Task 2: Persistenza di `last_index_at` nel job di indicizzazione

**Files:**
- Modify: `backend/app/services/library_index_job.py` (funzione `_run_job`)
- Test: `backend/tests/test_app_state.py` (aggiunta in coda)

**Interfaces:**
- Consumes: `set_state`/`get_state` dal Task 1; pattern di test sincrono del job da `tests/test_library_index_router.py` (monkeypatch di `SessionLocal` e `_spawn`).
- Produces: alla fine di ogni indicizzazione **riuscita**, la chiave `app_state["last_index_at"]` contiene l'istante UTC in ISO 8601. Il Task 3 la legge con `get_state(db, "last_index_at")`.

- [ ] **Step 1: Scrivi il test che fallisce**

In coda a `backend/tests/test_app_state.py` aggiungi:

```python
def test_job_indicizzazione_persiste_last_index_at(monkeypatch, tmp_path):
    """A fine indicizzazione riuscita, last_index_at è salvato in app_state."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.config import settings
    from app.db import Base
    from app.services import library_index_job

    # StaticPool: connessione unica condivisa, così la sessione del job e quella
    # di verifica vedono lo stesso DB in-memory (vedi test_track_lookup.py).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(library_index_job, "SessionLocal", factory)
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(library_index_job, "_spawn", lambda fn: fn())  # sincrono nel test

    library_index_job.start_job()

    session = factory()
    try:
        assert get_state(session, "last_index_at") is not None
    finally:
        session.close()
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/test_app_state.py::test_job_indicizzazione_persiste_last_index_at -v`
Expected: FAIL su `assert ... is not None` (la chiave non viene mai scritta)

- [ ] **Step 3: Implementa**

In `backend/app/services/library_index_job.py`:

Aggiungi l'import (dopo `from app.services.library_index import index_library`):

```python
from app.services.app_state import set_state
```

In `_run_job`, subito dopo la riga `report = index_library(db, root=root, on_progress=on_progress)` e prima di `_state.update(status="done", ...)`:

```python
        set_state(db, "last_index_at", datetime.now(timezone.utc).isoformat())
```

(`datetime`/`timezone` sono già importati nel modulo. La chiamata sta nel `try`: in caso di eccezione di `index_library` non si persiste nulla — corretto, la scansione non è avvenuta.)

- [ ] **Step 4: Verifica che passi**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/test_app_state.py tests/test_library_index_router.py -v`
Expected: tutti PASS (anche i test esistenti del job: la scrittura extra non li rompe)

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add backend/app/services/library_index_job.py backend/tests/test_app_state.py
git commit -m "feat: persisti last_index_at in app_state a fine indicizzazione"
```

---

### Task 3: Servizio `pipeline_snapshot` + setting `organizer_url`

Il cuore backend: un'unica funzione che aggrega DB, disco e stato job.

**Files:**
- Modify: `backend/app/core/config.py` (dopo la riga `library_root: str = ""`, riga 26)
- Modify: `backend/.env.example`
- Create: `backend/app/services/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `settings.slskd_download_dir`, `settings.library_root` (esistenti), `settings.organizer_url` (nuovo); `scan_folder(path, *, recurse=True) -> list[Path]` da `app.services.local_import` (filtra già per `AUDIO_EXTENSIONS`); `soulseek_download_job.job_state() -> dict` (chiavi `status`, `total`, `processed`); `get_state` dal Task 1; fixture `db` e `seed_tracks` di conftest (il seed crea tracce con `camelot_key` valorizzata, `status="ready_for_set"`, `has_local_file=True`).
- Produces: `pipeline_snapshot(db: Session) -> dict` con chiavi: `playlists: int`, `total_tracks: int`, `missing_key: int`, `wishlist: int`, `with_local_file: int`, `ready_for_set: int`, `download_active: bool`, `download_pending: int`, `inbox_files: int | None`, `files_on_disk: int | None`, `index_mismatch: bool | None`, `last_index_at: str | None`, `organizer_url: str | None`. I campi disco sono `None` quando la cartella non è configurata o non esiste (fase neutra, non errore). Il Task 4 espone questo dict così com'è.

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `backend/tests/test_pipeline.py`:

```python
"""pipeline_snapshot: conteggi DB + disco per la striscia di orientamento."""
import pytest

from app.core.config import settings
from app.services.pipeline import pipeline_snapshot


@pytest.fixture(autouse=True)
def _no_dirs(monkeypatch):
    """Default: nessuna cartella/URL configurati (i test che servono li impostano)."""
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "organizer_url", "")


def test_snapshot_vuoto(db):
    snap = pipeline_snapshot(db)
    assert snap["total_tracks"] == 0
    assert snap["playlists"] == 0
    assert snap["download_active"] is False
    assert snap["inbox_files"] is None
    assert snap["files_on_disk"] is None
    assert snap["index_mismatch"] is None
    assert snap["last_index_at"] is None
    assert snap["organizer_url"] is None


def test_conteggi_db(db, seed_tracks):
    seed_tracks(10)
    snap = pipeline_snapshot(db)
    assert snap["total_tracks"] == 10
    assert snap["missing_key"] == 0   # il seed ha sempre la key
    assert snap["wishlist"] == 0      # il seed ha has_local_file=True
    assert snap["ready_for_set"] == 10


def test_inbox_conta_solo_file_audio(db, tmp_path, monkeypatch):
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.flac").write_bytes(b"x")
    (tmp_path / "note.txt").write_bytes(b"x")
    monkeypatch.setattr(settings, "slskd_download_dir", str(tmp_path))
    assert pipeline_snapshot(db)["inbox_files"] == 2


def test_inbox_cartella_vuota(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "slskd_download_dir", str(tmp_path))
    assert pipeline_snapshot(db)["inbox_files"] == 0


def test_inbox_cartella_inesistente_e_neutra(db, monkeypatch):
    monkeypatch.setattr(settings, "slskd_download_dir", "/percorso/che/non/esiste")
    assert pipeline_snapshot(db)["inbox_files"] is None


def test_disallineamento_disco_db(db, seed_tracks, tmp_path, monkeypatch):
    seed_tracks(3)                          # 3 tracce possedute nel DB...
    (tmp_path / "a.mp3").write_bytes(b"x")  # ...ma 1 solo file su disco
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    snap = pipeline_snapshot(db)
    assert snap["files_on_disk"] == 1
    assert snap["index_mismatch"] is True


def test_disco_db_allineati(db, seed_tracks, tmp_path, monkeypatch):
    seed_tracks(2)
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.mp3").write_bytes(b"x")
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    assert pipeline_snapshot(db)["index_mismatch"] is False


def test_organizer_url_esposto(db, monkeypatch):
    monkeypatch.setattr(settings, "organizer_url", "http://localhost:3100")
    assert pipeline_snapshot(db)["organizer_url"] == "http://localhost:3100"
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/test_pipeline.py -v`
Expected: ERROR con `ModuleNotFoundError: No module named 'app.services.pipeline'`

- [ ] **Step 3: Aggiungi il setting `organizer_url`**

In `backend/app/core/config.py`, subito dopo `library_root: str = ""`:

```python
    organizer_url: str = ""
```

In `backend/.env.example`, dopo la riga `LIBRARY_ROOT=`:

```
# URL del frontend DjOrganizer per il link "Apri DjOrganizer" in dashboard (opzionale)
ORGANIZER_URL=
```

- [ ] **Step 4: Implementa il servizio**

Crea `backend/app/services/pipeline.py`:

```python
"""Snapshot per la pipeline di orientamento in dashboard.

Un'unica lettura che risponde a "a che punto del ciclo sono?": conteggi DB
(playlist, tracce senza key, wishlist, pronte per set), conteggi disco (file
audio in inbox e in Libreria) e stato indicizzazione. Deterministico: il
disallineamento disco/DB e' un confronto di conteggi, niente euristiche opache.
Cartella non configurata o assente -> campo None (fase neutra, non errore).
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Playlist, Track
from app.services import soulseek_download_job
from app.services.app_state import get_state
from app.services.local_import import scan_folder


def _count_audio_files(root: str) -> int | None:
    """Conta i file audio sotto `root` (walk senza hashing: veloce anche su
    librerie grandi). None se la cartella non e' configurata o non esiste."""
    if not root or not Path(root).is_dir():
        return None
    return len(scan_folder(root))


def pipeline_snapshot(db: Session) -> dict:
    def count(*conds) -> int:
        q = select(func.count()).select_from(Track)
        if conds:
            q = q.where(*conds)
        return db.scalar(q) or 0

    total = count()
    with_key = count(Track.camelot_key.is_not(None), Track.camelot_key != "")
    with_local_file = count(Track.has_local_file.is_(True))

    inbox_files = _count_audio_files(settings.slskd_download_dir)
    files_on_disk = _count_audio_files(settings.library_root)

    download = soulseek_download_job.job_state()
    download_active = download["status"] == "running"

    return {
        "playlists": db.scalar(select(func.count()).select_from(Playlist)) or 0,
        "total_tracks": total,
        "missing_key": total - with_key,
        "wishlist": total - with_local_file,
        "with_local_file": with_local_file,
        "ready_for_set": count(Track.status == "ready_for_set"),
        "download_active": download_active,
        "download_pending": max(download["total"] - download["processed"], 0) if download_active else 0,
        "inbox_files": inbox_files,
        "files_on_disk": files_on_disk,
        "index_mismatch": None if files_on_disk is None else files_on_disk != with_local_file,
        "last_index_at": get_state(db, "last_index_at"),
        "organizer_url": settings.organizer_url or None,
    }
```

- [ ] **Step 5: Verifica che passino**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/test_pipeline.py -v`
Expected: 9 PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add backend/app/core/config.py backend/.env.example backend/app/services/pipeline.py backend/tests/test_pipeline.py
git commit -m "feat: servizio pipeline_snapshot (conteggi DB+disco) e setting organizer_url"
```

---

### Task 4: Schema `PipelineOut` + router `GET /api/pipeline`

**Files:**
- Modify: `backend/app/schemas.py` (dopo `LibraryStatsOut`, ~riga 542)
- Create: `backend/app/routers/pipeline.py`
- Modify: `backend/app/main.py` (import dei router ~riga 10, `include_router` ~riga 72)
- Test: `backend/tests/test_pipeline_router.py`

**Interfaces:**
- Consumes: `pipeline_snapshot(db) -> dict` dal Task 3 (chiavi elencate lì); pattern `dependency_overrides` + `StaticPool` da `tests/test_track_lookup.py`.
- Produces: `GET /api/pipeline` → JSON con esattamente le chiavi dello snapshot, validate da `PipelineOut`. Il frontend (Task 5) lo consuma via `getPipeline()`.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `backend/tests/test_pipeline_router.py`:

```python
"""GET /api/pipeline: snapshot unico per la striscia di orientamento."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    # StaticPool: TestClient esegue la route in un altro thread, serve la
    # connessione unica condivisa (vedi test_track_lookup.py).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_get_pipeline(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "organizer_url", "")

    r = client.get("/api/pipeline")
    assert r.status_code == 200
    body = r.json()
    assert body["total_tracks"] == 0
    assert body["download_active"] is False
    assert body["inbox_files"] is None
    assert body["index_mismatch"] is None
    assert body["organizer_url"] is None
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/test_pipeline_router.py -v`
Expected: FAIL con status 404 (route inesistente)

- [ ] **Step 3: Implementa schema, router e registrazione**

In `backend/app/schemas.py`, subito dopo la classe `LibraryStatsOut`:

```python
class PipelineOut(BaseModel):
    """Snapshot della pipeline di orientamento (dashboard). Campi disco None = non configurato."""
    playlists: int
    total_tracks: int
    missing_key: int
    wishlist: int
    with_local_file: int
    ready_for_set: int
    download_active: bool
    download_pending: int
    inbox_files: int | None = None
    files_on_disk: int | None = None
    index_mismatch: bool | None = None
    last_index_at: str | None = None
    organizer_url: str | None = None
```

Crea `backend/app/routers/pipeline.py`:

```python
"""GET /api/pipeline: snapshot unico per la striscia di orientamento in dashboard."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import PipelineOut
from app.services.pipeline import pipeline_snapshot

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.get("", response_model=PipelineOut)
def get_pipeline(db: Session = Depends(get_db)):
    return pipeline_snapshot(db)
```

In `backend/app/main.py`: aggiungi `pipeline` alla tupla `from app.routers import (...)` (ordine alfabetico) e, accanto agli altri `include_router` (dopo `app.include_router(downloads.router)`):

```python
app.include_router(pipeline.router)
```

- [ ] **Step 4: Verifica che passi + suite completa**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && python -m pytest tests/test_pipeline_router.py -v && python -m pytest tests/ -q`
Expected: tutti PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add backend/app/schemas.py backend/app/routers/pipeline.py backend/app/main.py backend/tests/test_pipeline_router.py
git commit -m "feat: endpoint GET /api/pipeline per la striscia di orientamento"
```

---

### Task 5: Frontend — tipo `PipelineStatus`, `getPipeline()` e componente `PipelineStrip`

**Files:**
- Modify: `frontend/lib/api.ts` (tipo dopo `LibraryStats` ~riga 375; funzione accanto a `libraryIndexStatus()` ~riga 239)
- Create: `frontend/components/dashboard/pipeline.tsx`

**Interfaces:**
- Consumes: `apiGet`/`apiPost` e `startLibraryIndex()` esistenti in `lib/api.ts`; `fmtDate` esistente; `cn` da `@/lib/cn`; `Card` da `@/components/ui` (prende solo `children`); token CSS esistenti (`text-fg-strong`, `text-muted`, `text-faint`, `bg-elevated`, `border-border`).
- Produces: `getPipeline(): Promise<PipelineStatus>` in `lib/api.ts`; componente `PipelineStrip({ p, onRefresh }: { p: PipelineStatus; onRefresh: () => void })` esportato da `components/dashboard/pipeline.tsx`. Il Task 6 li importa in `app/page.tsx`.

- [ ] **Step 1: Aggiungi tipo e fetch in `lib/api.ts`**

Dopo l'interfaccia `LibraryStats`:

```ts
export interface PipelineStatus {
  playlists: number;
  total_tracks: number;
  missing_key: number;
  wishlist: number;
  with_local_file: number;
  ready_for_set: number;
  download_active: boolean;
  download_pending: number;
  inbox_files: number | null;
  files_on_disk: number | null;
  index_mismatch: boolean | null;
  last_index_at: string | null;
  organizer_url: string | null;
}
```

Dopo `libraryIndexStatus()`:

```ts
export function getPipeline() {
  return apiGet<PipelineStatus>("/api/pipeline");
}
```

- [ ] **Step 2: Crea il componente**

Crea `frontend/components/dashboard/pipeline.tsx`:

```tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, ExternalLink } from "lucide-react";
import { cn } from "@/lib/cn";
import { fmtDate, startLibraryIndex, type PipelineStatus } from "@/lib/api";
import { Card } from "@/components/ui";

/* Una fase della striscia: numero vivo + etichetta, "accesa" (pallino) se c'è
   lavoro pendente. Fasi con href navigano; Organizza apre il pannello cross-app;
   Indicizza lancia la scansione. */
type StageDef = {
  key: string;
  label: string;
  value: string;
  sub: string;
  hot: boolean;
  href?: string;
};

function StageCell({ s }: { s: StageDef }) {
  return (
    <div className="flex min-w-[8.5rem] flex-1 flex-col gap-0.5 px-4 py-3 text-left">
      <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted">
        {s.label}
        {s.hot && <span className="h-1.5 w-1.5 rounded-full bg-fg-strong" aria-hidden />}
      </span>
      <span className={cn("tnum text-lg font-semibold", s.hot ? "text-fg-strong" : "text-fg")}>{s.value}</span>
      <span className="whitespace-nowrap text-[10px] text-faint">{s.sub}</span>
    </div>
  );
}

export function PipelineStrip({ p, onRefresh }: { p: PipelineStatus; onRefresh: () => void }) {
  const [organizeOpen, setOrganizeOpen] = useState(false);
  const [scanStarted, setScanStarted] = useState(false);

  const startScan = async () => {
    try {
      await startLibraryIndex();
      setScanStarted(true);
      onRefresh();
    } catch {
      /* 409 = LIBRARY_ROOT mancante o job già in corso: la striscia resta com'è */
    }
  };

  const diskConfigured = p.files_on_disk !== null;
  const stages: StageDef[] = [
    {
      key: "scopri", label: "Scopri", value: String(p.playlists),
      sub: "playlist importate", hot: p.total_tracks === 0, href: "/playlists",
    },
    {
      key: "arricchisci", label: "Arricchisci", value: String(p.missing_key),
      sub: "tracce senza key", hot: p.missing_key > 0, href: "/library",
    },
    {
      key: "acquisisci", label: "Acquisisci", value: String(p.wishlist),
      sub: p.download_active ? `download attivi · ${p.download_pending} in coda` : "in wishlist",
      hot: p.wishlist > 0 || p.download_active, href: "/downloads",
    },
    {
      key: "organizza", label: "Organizza ⤴",
      value: p.inbox_files === null ? "—" : String(p.inbox_files),
      sub: "inbox · DJPlayer → DjOrganizer", hot: (p.inbox_files ?? 0) > 0,
    },
    {
      key: "indicizza", label: "Indicizza",
      value: scanStarted ? "…" : p.index_mismatch ? "≠" : "ok",
      sub: scanStarted
        ? "scansione avviata"
        : p.last_index_at
          ? `ultima: ${fmtDate(p.last_index_at)} · clic per scansionare`
          : "mai eseguita · clic per scansionare",
      hot: !scanStarted && diskConfigured && (p.index_mismatch === true || !p.last_index_at),
    },
    {
      key: "suona", label: "Suona", value: String(p.ready_for_set),
      sub: "pronte per un set", hot: false, href: "/set-builder",
    },
  ];

  return (
    <Card>
      <div className="flex items-stretch overflow-x-auto">
        {stages.map((s, i) => (
          <div key={s.key} className="flex flex-1 items-center">
            {i > 0 && <ChevronRight size={14} className="shrink-0 text-faint" aria-hidden />}
            {s.href ? (
              <Link href={s.href} className="flex-1 transition-colors hover:bg-elevated">
                <StageCell s={s} />
              </Link>
            ) : (
              <button
                type="button"
                onClick={s.key === "organizza" ? () => setOrganizeOpen((v) => !v) : startScan}
                className="flex-1 transition-colors hover:bg-elevated"
              >
                <StageCell s={s} />
              </button>
            )}
          </div>
        ))}
      </div>
      {organizeOpen && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-xs text-muted">
          <span>
            {p.inbox_files === null
              ? "Inbox non configurata: imposta SLSKD_DOWNLOAD_DIR nel .env del backend."
              : `${p.inbox_files} file audio in inbox aspettano il triage (DJPlayer) e l'organizzazione (DjOrganizer); poi torna qui e indicizza.`}
          </span>
          {p.organizer_url && (
            <a
              href={p.organizer_url} target="_blank" rel="noreferrer"
              className="inline-flex shrink-0 items-center gap-1.5 text-fg-strong hover:underline"
            >
              Apri DjOrganizer <ExternalLink size={12} />
            </a>
          )}
        </div>
      )}
    </Card>
  );
}
```

- [ ] **Step 3: Verifica che compili**

Run: `cd /Users/lucadenegri/Develop/DJProject01/frontend && npm run build`
Expected: build verde, nessun errore TypeScript (il componente non è ancora usato: normale che non appaia)

- [ ] **Step 4: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add frontend/lib/api.ts frontend/components/dashboard/pipeline.tsx
git commit -m "feat: tipo PipelineStatus, getPipeline() e componente PipelineStrip"
```

---

### Task 6: Dashboard — striscia in cima + `recommend()` potenziato

**Files:**
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `PipelineStrip` e `getPipeline`/`PipelineStatus` dal Task 5; `recommend()`, `load()`, `Reco`, `QuickAction` esistenti in `page.tsx`.
- Produces: dashboard che mostra `PipelineStrip` sopra le statistiche quando ci sono dati, e "Prossimo passo" con le due nuove priorità cross-app in testa.

- [ ] **Step 1: Aggiorna import e stato**

In `frontend/app/page.tsx`:

Aggiungi alle icone importate da `lucide-react`: `FolderOpen, RefreshCw`.

Estendi l'import da `@/lib/api` con: `getPipeline` e `type PipelineStatus`.

Aggiungi l'import del componente:

```tsx
import { PipelineStrip } from "@/components/dashboard/pipeline";
```

Nel componente `Dashboard`, accanto agli altri `useState`:

```tsx
const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
```

Dentro `load()`, accanto alle altre fetch:

```tsx
getPipeline().then(setPipeline).catch(() => setPipeline(null));
```

- [ ] **Step 2: Sostituisci `recommend()` con la versione a priorità cross-app**

Sostituisci l'intera funzione `recommend` esistente con:

```tsx
/** "Prossimo passo" suggerito: guida l'utente nel ciclo (anche cross-app) in base allo stato. */
function recommend(s: LibraryStats, p: PipelineStatus | null): Reco | null {
  if (s.total_tracks === 0) return null; // gestito dall'empty state
  if (p && (p.inbox_files ?? 0) > 0) {
    return {
      icon: <FolderOpen size={22} />, tag: "Prossimo passo", title: "Organizza i download",
      desc: `${p.inbox_files} file in inbox aspettano il triage e l'organizzazione (DJPlayer → DjOrganizer).`,
      href: p.organizer_url ?? "/downloads", cta: p.organizer_url ? "Apri DjOrganizer" : "Vedi download",
    };
  }
  if (p?.index_mismatch) {
    return {
      icon: <RefreshCw size={22} />, tag: "Prossimo passo", title: "La Libreria è cambiata",
      desc: "I file su disco non coincidono con le tracce possedute: lancia una scansione dalla striscia qui sopra o dalla Libreria.",
      href: "/library", cta: "Vai alla Libreria",
    };
  }
  const keyPct = s.total_tracks ? s.with_key / s.total_tracks : 0;
  if (keyPct < 0.6) {
    return {
      icon: <Gauge size={22} />, tag: "Prossimo passo", title: "Completa BPM e tonalità",
      desc: `${s.with_key} tracce su ${s.total_tracks} hanno la tonalità. Arricchisci le feature o inserisci i valori a mano per sbloccare il Set Builder.`,
      href: "/playlists", cta: "Arricchisci",
    };
  }
  if (s.ready_for_set > 0) {
    return {
      icon: <Sparkles size={22} />, tag: "Prossimo passo", title: "Sei pronto per un set",
      href: "/set-builder", cta: "Costruisci un set",
    };
  }
  return {
    icon: <Compass size={22} />, tag: "Prossimo passo", title: "Espandi la libreria",
    desc: "Scopri tracce affini al gusto delle tue playlist e aggiungile alla libreria.",
    href: "/discovery", cta: "Scopri musica",
  };
}
```

E aggiorna il punto di chiamata:

```tsx
const reco = stats ? recommend(stats, pipeline) : null;
```

- [ ] **Step 3: Renderizza la striscia**

Nel JSX, subito dopo il blocco `{empty && (...)}` e prima del contenuto principale della dashboard, aggiungi:

```tsx
{!empty && pipeline && (
  <div className="mb-6">
    <PipelineStrip p={pipeline} onRefresh={load} />
  </div>
)}
```

- [ ] **Step 4: Verifica build + visiva**

Run: `cd /Users/lucadenegri/Develop/DJProject01/frontend && npm run build`
Expected: build verde.

Verifica visiva (backend attivo su :8000, `npm run dev`): la striscia appare sopra le statistiche con 6 fasi; le fasi con lavoro pendente hanno il pallino; clic su "Organizza" apre il pannello; clic su "Indicizza" avvia la scansione (o resta inerte con 409 se `LIBRARY_ROOT` manca).

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add frontend/app/page.tsx
git commit -m "feat: striscia pipeline in dashboard e Prossimo passo cross-app"
```

---

### Task 7: Menu raggruppato per fasi

**Files:**
- Modify: `frontend/components/index-nav.tsx`

**Interfaces:**
- Consumes: struttura esistente del componente (`isActive`, blocco Impostazioni/Clock invariati).
- Produces: menu con gruppi SCOPRI / COLLEZIONA / SUONA; su mobile lista orizzontale con separatori; nessuna rotta cambia.

- [ ] **Step 1: Sostituisci la costante `NAV` e la `<ul>`**

In `frontend/components/index-nav.tsx`, sostituisci la costante `NAV` con:

```tsx
/* Il menu racconta la sequenza del flusso: Scopri → Colleziona → Suona. */
const NAV_GROUPS: { title: string | null; items: { href: string; label: string }[] }[] = [
  { title: null, items: [{ href: "/", label: "Dashboard" }] },
  {
    title: "Scopri",
    items: [
      { href: "/playlists", label: "Playlist" },
      { href: "/discovery", label: "Discovery" },
      { href: "/shazam", label: "Shazam" },
      { href: "/labels", label: "Etichette" },
    ],
  },
  {
    title: "Colleziona",
    items: [
      { href: "/library", label: "Libreria" },
      { href: "/downloads", label: "Download" },
    ],
  },
  { title: "Suona", items: [{ href: "/sets", label: "Set" }] },
];
```

Sostituisci l'attuale blocco `<ul className="flex gap-4 overflow-x-auto ...">...</ul>` con:

```tsx
<div className="flex gap-4 overflow-x-auto px-4 pb-3 lg:flex-1 lg:flex-col lg:gap-0 lg:overflow-visible lg:pb-0">
  {NAV_GROUPS.map((g, gi) => (
    <div
      key={g.title ?? "root"}
      className={cn("flex shrink-0 gap-4 lg:block", gi > 0 && "border-l border-border pl-4 lg:border-l-0 lg:pl-0")}
    >
      {g.title && (
        <div className="hidden lg:mb-1 lg:mt-4 lg:block text-[9px] font-semibold uppercase tracking-[0.14em] text-faint">
          {g.title}
        </div>
      )}
      <ul className="flex gap-4 lg:flex-col lg:gap-0">
        {g.items.map(({ href, label }) => (
          <li key={href} className="shrink-0">
            <Link
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={cn(
                "block whitespace-nowrap py-1 text-xs uppercase tracking-wider transition-colors",
                isActive(href) ? "text-fg-strong underline underline-offset-4" : "text-muted hover:text-fg",
              )}
            >
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  ))}
</div>
```

(Il resto del componente — header, Impostazioni, Clock, ThemeToggle — resta invariato.)

- [ ] **Step 2: Verifica build + visiva**

Run: `cd /Users/lucadenegri/Develop/DJProject01/frontend && npm run build`
Expected: build verde.

Verifica visiva: desktop → colonna con intestazioni SCOPRI/COLLEZIONA/SUONA sopra i rispettivi link; mobile (viewport stretto) → lista orizzontale scrollabile con separatori verticali tra i gruppi; evidenziazione voce attiva invariata.

- [ ] **Step 3: Commit e suite finale**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add frontend/components/index-nav.tsx
git commit -m "feat: menu raggruppato per fasi (Scopri / Colleziona / Suona)"
cd backend && python -m pytest tests/ -q
```

Expected: tutti i test verdi.
