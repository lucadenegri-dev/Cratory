# DjOrganizer Chunk 6a — Frontend Fondazione + SOURCES + FILES — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Costruire lo scheletro dell'intera UI di DjOrganizer (scaffold Next.js + port del design system di Cratory) con le prime due pagine funzionanti — SOURCES e FILES — e i due endpoint backend read-only che le alimentano.

**Architecture:** Backend FastAPI esistente (porta 8010) + un nuovo router sottile `library.py` (read-only: lista file + statistiche). Frontend Next.js separato (porta 3000) che parla col backend via `NEXT_PUBLIC_API_BASE`. Estetica "editorial archive" copiata da Cratory (`~/Develop/DJProject01/frontend`): token CSS commutati da `data-theme`, shell a colonne (nav + content + marginalia), scan come job non bloccante con polling.

**Tech Stack:** Backend — Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest. Frontend — Next 16.2.9, React 19.2.4, Tailwind 4, TypeScript 5, lucide-react.

## Global Constraints

- Backend router **sottili**: la logica di query sta nel router (read-only puro), nessun servizio nuovo. Stile dei router esistenti (`select`, `func`, `Depends(get_db)`).
- Backend test **pristine**: nessun warning (`filterwarnings = error`). Pattern test: fixture `db` semina righe + `with TestClient(app) as client`.
- Severità issue ammesse: **`error` > `warning` > `info`** (ranking per `worst_severity`). Issue "aperte" = `status == "open"`. Gruppi doppioni attivi = `dismissed == False`. File presenti = `status == "present"`.
- Frontend: copia fedele dei pattern di Cratory. Il "test" del frontend è **`npm run lint` + `npm run build` verdi** (NON pytest/TDD — preferenza utente esplicita nella spec). Ogni task frontend termina con lint+build verdi + commit.
- Base URL backend nel frontend: env var **`NEXT_PUBLIC_API_BASE`**, default `http://localhost:8010`.
- Temi: **Dark default** (nessun attributo) + **Paper** (`html[data-theme="paper"]`), chiave localStorage **`djorganizer-theme`**.
- Tutti i comandi `npm` si lanciano da `frontend/`. I comandi `pytest` da `backend/`.
- Spec di riferimento: `docs/superpowers/specs/2026-06-28-djorganizer-chunk6a-frontend-foundation-design.md`.

---

## File Structure

**Backend (nuovi/modificati):**
- Create: `backend/app/routers/library.py` — router read-only: `GET /api/files`, `GET /api/library/stats`
- Modify: `backend/app/schemas.py` — aggiunge `FileRow`, `LibraryStatsRead`
- Modify: `backend/app/main.py` — registra `library.router`
- Create: `backend/tests/test_library_api.py` — test dei due endpoint

**Frontend (tutto nuovo, sotto `frontend/`):**
- Config: `package.json`, `next.config.ts`, `tsconfig.json`, `postcss.config.mjs`, `eslint.config.mjs`, `.gitignore`, `.env.example`
- `app/globals.css` — token design system (+ token `--c-warning`)
- `app/layout.tsx` — root layout (font, no-FOUC tema, shell)
- `app/page.tsx` — redirect → `/sources`
- `app/sources/page.tsx`, `app/files/page.tsx` — pagine funzionanti
- `app/issues/page.tsx`, `app/duplicates/page.tsx`, `app/plan/page.tsx`, `app/history/page.tsx`, `app/settings/page.tsx` — placeholder "in arrivo"
- `lib/cn.ts`, `lib/api.ts` — util + client API tipizzato
- `components/ui.tsx` — Card/Button/Input/Select/Badge/Progress/Equalizer/EqMeter/EmptyState/Alert/Field/Checkbox/Modal
- `components/theme-toggle.tsx`, `components/clock.tsx`
- `components/editorial-shell.tsx`, `components/index-nav.tsx`, `components/page-layout.tsx`, `components/jobs-provider.tsx`
- `components/sources-table.tsx`, `components/add-source.tsx`, `components/files-table.tsx`

---

## Task 1: Backend — `GET /api/library/stats`

**Files:**
- Modify: `backend/app/schemas.py` — aggiunge `LibraryStatsRead`
- Create: `backend/app/routers/library.py` — router + endpoint stats
- Modify: `backend/app/main.py` — registra il router
- Test: `backend/tests/test_library_api.py`

**Interfaces:**
- Produces: `GET /api/library/stats` → `{ files_total: int, by_ext: dict[str,int], issues_by_severity: dict[str,int], dup_groups: int, sources: int }`. Conta solo file `present`, issue `open`, gruppi non `dismissed`.

- [ ] **Step 1: Scrivi il test che fallisce**

In `backend/tests/test_library_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, DupGroup, DupMember, Issue, ScanRoot


def _seed_stats(db):
    db.add(ScanRoot(id=1, path="/m", label="M"))
    db.add(AudioFile(id=1, root_id=1, path="/m/a.flac", ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(AudioFile(id=2, root_id=1, path="/m/b.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(AudioFile(id=3, root_id=1, path="/m/c.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="missing", has_cover=False))
    db.add(Issue(file_id=1, type="bad_bitrate", field=None, severity="error",
                 detail="x", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=2, type="missing_metadata", field="genre", severity="warning",
                 detail="x", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=2, type="resolved_one", field="x", severity="info",
                 detail="x", suggested_fix_json=None, status="dismissed"))
    db.add(DupGroup(id=1, match_kind="hash", keeper_file_id=1, signature="s1"))
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    db.commit()


def test_library_stats(db):
    _seed_stats(db)
    with TestClient(app) as client:
        s = client.get("/api/library/stats").json()
        assert s["files_total"] == 2          # solo i present
        assert s["by_ext"] == {"flac": 1, "mp3": 1}
        assert s["issues_by_severity"] == {"error": 1, "warning": 1}  # la dismissed esclusa
        assert s["dup_groups"] == 1
        assert s["sources"] == 1
```

- [ ] **Step 2: Lancia il test, verifica che fallisce**

Run: `cd backend && python -m pytest tests/test_library_api.py::test_library_stats -v`
Expected: FAIL (404 / `library.router` inesistente).

- [ ] **Step 3: Aggiungi lo schema**

In `backend/app/schemas.py`, in fondo:

```python
class LibraryStatsRead(BaseModel):
    files_total: int
    by_ext: dict[str, int]
    issues_by_severity: dict[str, int]
    dup_groups: int
    sources: int
```

- [ ] **Step 4: Crea il router con l'endpoint stats**

`backend/app/routers/library.py`:

```python
"""Router LIBRARY: letture read-only per il frontend (statistiche + lista file).
Router sottile: query dirette, nessun servizio nuovo."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, DupGroup, Issue, ScanRoot
from app.schemas import LibraryStatsRead

router = APIRouter(prefix="/api", tags=["library"])


@router.get("/library/stats", response_model=LibraryStatsRead)
def library_stats(db: Session = Depends(get_db)):
    files_total = db.scalar(
        select(func.count()).select_from(AudioFile).where(AudioFile.status == "present")
    ) or 0
    by_ext = {
        ext: n
        for ext, n in db.execute(
            select(AudioFile.ext, func.count())
            .where(AudioFile.status == "present")
            .group_by(AudioFile.ext)
        ).all()
    }
    issues_by_severity = {
        sev: n
        for sev, n in db.execute(
            select(Issue.severity, func.count())
            .where(Issue.status == "open")
            .group_by(Issue.severity)
        ).all()
    }
    dup_groups = db.scalar(
        select(func.count()).select_from(DupGroup).where(DupGroup.dismissed.is_(False))
    ) or 0
    sources = db.scalar(select(func.count()).select_from(ScanRoot)) or 0
    return LibraryStatsRead(
        files_total=files_total,
        by_ext=by_ext,
        issues_by_severity=issues_by_severity,
        dup_groups=dup_groups,
        sources=sources,
    )
```

- [ ] **Step 5: Registra il router in main.py**

In `backend/app/main.py`, aggiorna l'import e l'include:

```python
from app.routers import analyze, apply, duplicates, history, issues, library, plan, scan, settings, sources
```

e dopo `app.include_router(history.router)`:

```python
app.include_router(library.router)
```

- [ ] **Step 6: Lancia il test, verifica che passa**

Run: `cd backend && python -m pytest tests/test_library_api.py::test_library_stats -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/schemas.py backend/app/routers/library.py backend/app/main.py backend/tests/test_library_api.py
git commit -m "feat(api): GET /api/library/stats — conteggi libreria per il frontend"
```

---

## Task 2: Backend — `GET /api/files`

**Files:**
- Modify: `backend/app/schemas.py` — aggiunge `FileRow`
- Modify: `backend/app/routers/library.py` — aggiunge l'endpoint `/files`
- Test: `backend/tests/test_library_api.py` — aggiunge i test della lista file

**Interfaces:**
- Consumes: `ScanRoot`, `AudioFile`, `Issue`, `DupGroup`, `DupMember` (modelli esistenti).
- Produces: `GET /api/files` → `list[FileRow]` con query `root_id?`, `status="present"`, `has_issues?: bool`, `q?`, `sort` (`path|artist|title|bitrate|duration`, default `path`), `limit=500`, `offset=0`. Ogni riga: `{ id, root_id, path, ext, artist, title, bitrate, duration_s, status, issue_count, worst_severity, in_dup_group }`. `worst_severity ∈ {error,warning,info,null}`.

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi in `backend/tests/test_library_api.py` (riusa `_seed_stats`):

```python
def test_list_files_basic_and_indicators(db):
    _seed_stats(db)
    with TestClient(app) as client:
        rows = client.get("/api/files").json()
        assert [r["path"] for r in rows] == ["/m/a.flac", "/m/b.mp3"]  # ordinati per path, no missing
        a = next(r for r in rows if r["id"] == 1)
        b = next(r for r in rows if r["id"] == 2)
        assert a["issue_count"] == 1 and a["worst_severity"] == "error"
        assert a["in_dup_group"] is True and b["in_dup_group"] is True
        assert b["worst_severity"] == "warning"  # la dismissed non conta


def test_list_files_filters(db):
    _seed_stats(db)
    with TestClient(app) as client:
        only_issues = client.get("/api/files", params={"has_issues": True}).json()
        assert {r["id"] for r in only_issues} == {1, 2}
        by_root = client.get("/api/files", params={"root_id": 1}).json()
        assert len(by_root) == 2
        searched = client.get("/api/files", params={"q": "a.flac"}).json()
        assert [r["id"] for r in searched] == [1]
        missing = client.get("/api/files", params={"status": "missing"}).json()
        assert [r["id"] for r in missing] == [3]


def test_list_files_sort_and_paging(db):
    _seed_stats(db)
    with TestClient(app) as client:
        ext_first = client.get("/api/files", params={"sort": "title"}).json()
        assert len(ext_first) == 2
        page = client.get("/api/files", params={"limit": 1, "offset": 1}).json()
        assert [r["id"] for r in page] == [2]
```

- [ ] **Step 2: Lancia i test, verifica che falliscono**

Run: `cd backend && python -m pytest tests/test_library_api.py -k list_files -v`
Expected: FAIL (404 sull'endpoint `/files`).

- [ ] **Step 3: Aggiungi lo schema FileRow**

In `backend/app/schemas.py`, dopo `LibraryStatsRead`:

```python
class FileRow(BaseModel):
    id: int
    root_id: int
    path: str
    ext: str
    artist: str | None
    title: str | None
    bitrate: int | None
    duration_s: float | None
    status: str
    issue_count: int
    worst_severity: str | None
    in_dup_group: bool
```

- [ ] **Step 4: Aggiungi l'endpoint /files al router**

In `backend/app/routers/library.py`, aggiorna gli import in testa:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, DupGroup, DupMember, Issue, ScanRoot
from app.schemas import FileRow, LibraryStatsRead
```

e aggiungi in fondo al file:

```python
_SEV_RANK = {"error": 3, "warning": 2, "info": 1}
_RANK_SEV = {3: "error", 2: "warning", 1: "info"}
_SORT_COLS = {
    "path": AudioFile.path,
    "artist": AudioFile.artist,
    "title": AudioFile.title,
    "bitrate": AudioFile.bitrate,
    "duration": AudioFile.duration_s,
}


@router.get("/files", response_model=list[FileRow])
def list_files(
    db: Session = Depends(get_db),
    root_id: int | None = None,
    status: str = "present",
    has_issues: bool | None = None,
    q: str | None = None,
    sort: str = "path",
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    issue_count = (
        select(func.count())
        .select_from(Issue)
        .where(Issue.file_id == AudioFile.id, Issue.status == "open")
        .scalar_subquery()
    )
    worst_rank = (
        select(func.max(case(_SEV_RANK, value=Issue.severity, else_=0)))
        .where(Issue.file_id == AudioFile.id, Issue.status == "open")
        .scalar_subquery()
    )
    in_dup = (
        select(func.count())
        .select_from(DupMember)
        .join(DupGroup, DupGroup.id == DupMember.group_id)
        .where(DupMember.file_id == AudioFile.id, DupGroup.dismissed.is_(False))
        .scalar_subquery()
    )

    stmt = select(AudioFile, issue_count, worst_rank, in_dup).where(
        AudioFile.status == status
    )
    if root_id is not None:
        stmt = stmt.where(AudioFile.root_id == root_id)
    if has_issues is True:
        stmt = stmt.where(issue_count > 0)
    elif has_issues is False:
        stmt = stmt.where(issue_count == 0)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(AudioFile.path.ilike(like), AudioFile.artist.ilike(like),
                AudioFile.title.ilike(like))
        )
    stmt = stmt.order_by(_SORT_COLS.get(sort, AudioFile.path)).limit(limit).offset(offset)

    rows = []
    for f, n_issues, rank, dup_n in db.execute(stmt).all():
        rows.append(FileRow(
            id=f.id, root_id=f.root_id, path=f.path, ext=f.ext,
            artist=f.artist, title=f.title, bitrate=f.bitrate, duration_s=f.duration_s,
            status=f.status, issue_count=n_issues or 0,
            worst_severity=_RANK_SEV.get(rank or 0), in_dup_group=bool(dup_n),
        ))
    return rows
```

- [ ] **Step 5: Lancia tutti i test del file, verifica che passano**

Run: `cd backend && python -m pytest tests/test_library_api.py -v`
Expected: PASS (4 test)

- [ ] **Step 6: Lancia l'intera suite backend (nessuna regressione, output pristine)**

Run: `cd backend && python -m pytest -q`
Expected: tutti verdi, zero warning.

- [ ] **Step 7: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/schemas.py backend/app/routers/library.py backend/tests/test_library_api.py
git commit -m "feat(api): GET /api/files — lista file con indicatori issue/doppioni, filtri e sort"
```

---

## Task 3: Frontend scaffold + design tokens

**Files:**
- Create: `frontend/package.json`, `frontend/next.config.ts`, `frontend/tsconfig.json`, `frontend/postcss.config.mjs`, `frontend/eslint.config.mjs`, `frontend/.gitignore`, `frontend/.env.example`
- Create: `frontend/lib/cn.ts`
- Create: `frontend/app/globals.css`, `frontend/app/layout.tsx` (minimale), `frontend/app/page.tsx` (placeholder temporaneo)

**Interfaces:**
- Produces: progetto Next compilabile. `cn(...)` util. Token CSS `--c-*` + utility Tailwind `bg-bg`, `text-fg`, `border-border`, … e `text-warning` (nuovo). Classi loader `.eq*` / `.eqm*`.

- [ ] **Step 1: Crea i file di config (copia da Cratory, identici)**

`frontend/package.json`:

```json
{
  "name": "djorganizer-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint"
  },
  "dependencies": {
    "lucide-react": "^1.18.0",
    "next": "16.2.9",
    "react": "19.2.4",
    "react-dom": "19.2.4"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "16.2.9",
    "tailwindcss": "^4",
    "typescript": "^5"
  }
}
```

`frontend/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
```

`frontend/postcss.config.mjs`:

```js
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
```

`frontend/eslint.config.mjs`:

```js
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);

export default eslintConfig;
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts", ".next/dev/types/**/*.ts", "**/*.mts"],
  "exclude": ["node_modules"]
}
```

`frontend/.gitignore`:

```gitignore
/node_modules
/.next/
/out/
/build
next-env.d.ts
*.tsbuildinfo
.env*.local
.DS_Store
```

`frontend/.env.example`:

```bash
# URL del backend FastAPI di DjOrganizer (default sviluppo: porta 8010)
NEXT_PUBLIC_API_BASE=http://localhost:8010
```

- [ ] **Step 2: Crea `frontend/lib/cn.ts`**

```ts
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
```

- [ ] **Step 3: Crea `frontend/app/globals.css`** (design system + token `--c-warning` nuovo)

```css
@import "tailwindcss";

/* Design system "editorial archive": monospace, monocromo, filetti, squadrato.
   I valori vivono nelle variabili runtime --c-* (commutate da data-theme);
   @theme inline mappa le utility Tailwind a quelle variabili. */
@theme inline {
  --color-bg: var(--c-bg);
  --color-surface: var(--c-surface);
  --color-surface-2: var(--c-surface-2);
  --color-elevated: var(--c-elevated);
  --color-border: var(--c-border);
  --color-border-strong: var(--c-border-strong);
  --color-muted: var(--c-muted);
  --color-faint: var(--c-faint);
  --color-fg: var(--c-fg);
  --color-fg-strong: var(--c-fg-strong);
  --color-danger: var(--c-danger);
  --color-warning: var(--c-warning);

  --radius: 0px;

  --font-ui: var(--font-ibm-plex-mono), ui-monospace, "SF Mono", "Cascadia Code", Menlo, monospace;
  --font-sans: var(--font-ui);
  --font-mono: var(--font-ui);
}

/* Dark = default (nessun attributo) */
:root {
  --c-bg: #0d0d0d;
  --c-surface: #161616;
  --c-surface-2: #1c1c1c;
  --c-elevated: #222222;
  --c-border: #2b2b2b;
  --c-border-strong: #3d3d3d;
  --c-muted: #787878;
  --c-faint: #555555;
  --c-fg: #c4c4c4;
  --c-fg-strong: #ededed;
  --c-danger: #d8593f;
  --c-warning: #c9a23a;
}

/* Paper = toggle */
html[data-theme="paper"] {
  --c-bg: #e9e5db;
  --c-surface: #f1eee6;
  --c-surface-2: #eae6dc;
  --c-elevated: #e2ddd0;
  --c-border: #cdc7b8;
  --c-border-strong: #b2ab99;
  --c-muted: #86806f;
  --c-faint: #a79f8d;
  --c-fg: #2a2823;
  --c-fg-strong: #15140f;
  --c-danger: #a83a22;
  --c-warning: #8a6d18;
}

html, body { height: 100%; }

body {
  background-color: var(--color-bg);
  color: var(--color-fg);
  font-family: var(--font-ui);
  -webkit-font-smoothing: antialiased;
}

/* numeri tabellari */
.tnum { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }

/* scrollbar discreta */
* { scrollbar-width: thin; scrollbar-color: var(--color-border-strong) transparent; }
*::-webkit-scrollbar { width: 10px; height: 10px; }
*::-webkit-scrollbar-thumb { background: var(--color-border-strong); border: 2px solid var(--color-bg); }

/* ---- DJ loaders: EQ inline (.eq*) + waveform (.eqm*) ---------------------- */
.eq { display: inline-flex; align-items: flex-end; gap: 2px; }
.eq-bar { position: relative; flex: 1; height: 100%; min-width: 2px; }
.eq-track { position: absolute; inset: 0; background: repeating-linear-gradient(to top, var(--c-border) 0 3px, transparent 3px 5px); }
.eq-fill { position: absolute; left: 0; right: 0; bottom: 0; height: 40%; background: repeating-linear-gradient(to top, var(--c-fg) 0 3px, transparent 3px 5px); }
.eq-fill::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 2px; background: var(--c-danger); }
.eq-l1 { animation: eqA 0.90s ease-in-out infinite -0.20s; }
.eq-l2 { animation: eqB 0.75s ease-in-out infinite -0.45s; }
.eq-l3 { animation: eqC 1.05s ease-in-out infinite -0.10s; }
.eq-l5 { animation: eqK 0.60s ease-in-out infinite -0.05s; }

@keyframes eqA { 0%,100% { height: 35%; } 25% { height: 95%; } 50% { height: 55%; } 75% { height: 80%; } }
@keyframes eqB { 0%,100% { height: 70%; } 25% { height: 30%; } 50% { height: 92%; } 75% { height: 45%; } }
@keyframes eqC { 0%,100% { height: 50%; } 30% { height: 85%; } 60% { height: 25%; } 85% { height: 78%; } }
@keyframes eqK { 0%,100% { height: 22%; } 12% { height: 100%; } 30% { height: 38%; } 55% { height: 28%; } }

.eqm { position: relative; overflow: hidden; }
.eqm-wave { position: absolute; inset: 0; display: flex; align-items: center; gap: 1px; }
.eqm-bar { flex: 1; }
.eqm-off { background: var(--c-border); }
.eqm-on { background: linear-gradient(to top, var(--c-fg), color-mix(in oklab, var(--c-danger) 60%, var(--c-fg)) 50%, var(--c-fg-strong)); animation: eqmBreathe 1.7s ease-in-out infinite; }
.eqm-ph { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--c-danger); }
.eqm-scan { position: absolute; top: 0; bottom: 0; left: -14%; width: 64px; background: linear-gradient(to right, transparent, color-mix(in srgb, var(--c-fg) 42%, transparent)); border-right: 2px solid var(--c-danger); animation: eqmScan 1.5s linear infinite; }
@keyframes eqmScan { from { left: -14%; } to { left: 100%; } }
@keyframes eqmBreathe { 0%, 100% { transform: scaleY(0.80); } 50% { transform: scaleY(1); } }

@media (prefers-reduced-motion: reduce) {
  .eq-l1, .eq-l2, .eq-l3, .eq-l5 { animation: none !important; }
  .eq-fill { height: 62% !important; }
  .eqm-scan { animation: none; left: 38%; }
  .eqm-on { animation: none; transform: none; }
}
```

- [ ] **Step 4: Crea un `app/layout.tsx` minimale temporaneo** (verrà ampliato nel Task 6)

```tsx
import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "DjOrganizer",
  description: "Organizza i file musicali e preparali per Rekordbox",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className={`h-full ${ibmPlexMono.variable}`} suppressHydrationWarning>
      <body className="h-full">{children}</body>
    </html>
  );
}
```

- [ ] **Step 5: Crea un `app/page.tsx` placeholder temporaneo** (verrà sostituito dal redirect nel Task 6)

```tsx
export default function Home() {
  return <main className="p-6 text-fg-strong">DjOrganizer — scaffold ok</main>;
}
```

- [ ] **Step 6: Installa le dipendenze**

Run: `cd frontend && npm install`
Expected: installazione senza errori (genera `package-lock.json` + `node_modules`).

- [ ] **Step 7: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: lint senza errori; build "Compiled successfully".

- [ ] **Step 8: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/package.json frontend/package-lock.json frontend/next.config.ts frontend/tsconfig.json frontend/postcss.config.mjs frontend/eslint.config.mjs frontend/.gitignore frontend/.env.example frontend/lib/cn.ts frontend/app/globals.css frontend/app/layout.tsx frontend/app/page.tsx
git commit -m "feat(fe): scaffold Next.js + design tokens (editorial archive, +warning)"
```

---

## Task 4: Frontend — client API tipizzato (`lib/api.ts`)

**Files:**
- Create: `frontend/lib/api.ts`

**Interfaces:**
- Produces: tipi `ScanRoot`, `ScanResult`, `ScanJobState`, `FileRow`, `LibraryStats`, `FileQuery`; funzioni `listSources()`, `addSource(path, label?)`, `deleteSource(id)`, `startScan(rootIds?)`, `scanJobStatus()`, `listFiles(query?)`, `libraryStats()`; helper `fmtDuration(s)`, `fmtDate(iso)`. Base URL da `NEXT_PUBLIC_API_BASE` (default `http://localhost:8010`).

- [ ] **Step 1: Crea `frontend/lib/api.ts`**

```ts
const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8010";

export interface ScanRoot {
  id: number;
  path: string;
  label: string | null;
  last_scanned_at: string | null;
  file_count: number;
}

export interface ScanResult {
  roots: number[];
  found: number;
  inserted: number;
  updated: number;
  moved: number;
  missing: number;
  errors: number;
  started_at: string | null;
  finished_at: string | null;
  analysis?: {
    issues_total: number;
    issues_by_severity: Record<string, number>;
    dup_groups: number;
    dup_files: number;
  };
}

export interface ScanJobState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  result: ScanResult | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export type Severity = "error" | "warning" | "info";

export interface FileRow {
  id: number;
  root_id: number;
  path: string;
  ext: string;
  artist: string | null;
  title: string | null;
  bitrate: number | null;
  duration_s: number | null;
  status: string;
  issue_count: number;
  worst_severity: Severity | null;
  in_dup_group: boolean;
}

export interface LibraryStats {
  files_total: number;
  by_ext: Record<string, number>;
  issues_by_severity: Record<string, number>;
  dup_groups: number;
  sources: number;
}

export interface FileQuery {
  root_id?: number;
  status?: string;
  has_issues?: boolean;
  q?: string;
  sort?: "path" | "artist" | "title" | "bitrate" | "duration";
  limit?: number;
  offset?: number;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function apiGet<T>(path: string, params?: FileQuery): Promise<T> {
  const url = new URL(API + path);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
    }
  }
  return handle<T>(await fetch(url));
}

async function apiSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(API + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

// --- SOURCES ----------------------------------------------------------------
export function listSources() {
  return apiGet<ScanRoot[]>("/api/sources");
}
export function addSource(path: string, label?: string) {
  return apiSend<ScanRoot>("POST", "/api/sources", { path, label: label || null });
}
export function deleteSource(id: number) {
  return apiSend<void>("DELETE", `/api/sources/${id}`);
}

// --- SCAN (job) -------------------------------------------------------------
export function startScan(rootIds?: number[]) {
  return apiSend<ScanJobState>("POST", "/api/scan", { root_ids: rootIds ?? null });
}
export function scanJobStatus() {
  return apiGet<ScanJobState>("/api/scan/status");
}

// --- FILES + STATS ----------------------------------------------------------
export function listFiles(query?: FileQuery) {
  return apiGet<FileRow[]>("/api/files", query);
}
export function libraryStats() {
  return apiGet<LibraryStats>("/api/library/stats");
}

// --- helpers ----------------------------------------------------------------
export function fmtDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "mai";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
```

- [ ] **Step 2: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi (il modulo compila anche se non ancora importato).

- [ ] **Step 3: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/lib/api.ts
git commit -m "feat(fe): client API tipizzato (sources, scan job, files, stats)"
```

---

## Task 5: Frontend — componenti UI di base (`ui.tsx`, `theme-toggle`, `clock`)

**Files:**
- Create: `frontend/components/ui.tsx` (copia verbatim da Cratory)
- Create: `frontend/components/theme-toggle.tsx` (chiave localStorage adattata)
- Create: `frontend/components/clock.tsx` (copia verbatim)

**Interfaces:**
- Produces: `Card`, `CardHeader`, `Button`, `Input`, `Textarea`, `Select`, `Field`, `Checkbox`, `Badge`, `Progress`, `Equalizer`/`Spinner`, `EqMeter`, `EmptyState`, `Modal`, `Alert` (da `@/components/ui`); `ThemeToggle`, `Clock`.

- [ ] **Step 1: Copia `ui.tsx` verbatim da Cratory**

Copia il contenuto di `~/Develop/DJProject01/frontend/components/ui.tsx` in `frontend/components/ui.tsx` **senza modifiche**: è già costruito sui token `--c-*`/utility Tailwind e su `@/lib/cn`, nessuna dipendenza Cratory-specifica.

Run: `cp ~/Develop/DJProject01/frontend/components/ui.tsx frontend/components/ui.tsx`

- [ ] **Step 2: Crea `frontend/components/clock.tsx`** (verbatim da Cratory)

```tsx
"use client";

import { useEffect, useState } from "react";

export function Clock() {
  const [time, setTime] = useState<string>("--:--:--");

  useEffect(() => {
    const fmt = () => new Date().toLocaleTimeString("it-IT", { hour12: false });
    const raf = requestAnimationFrame(() => setTime(fmt()));
    const id = setInterval(() => setTime(fmt()), 1000);
    return () => {
      cancelAnimationFrame(raf);
      clearInterval(id);
    };
  }, []);

  return <span className="tnum text-faint">{time}</span>;
}
```

- [ ] **Step 3: Crea `frontend/components/theme-toggle.tsx`** (chiave `djorganizer-theme`)

```tsx
"use client";

import { useEffect, useState } from "react";

type Theme = "dark" | "paper";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = (localStorage.getItem("djorganizer-theme") as Theme | null) ?? "dark";
    const raf = requestAnimationFrame(() => setTheme(stored));
    return () => cancelAnimationFrame(raf);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "paper" : "dark";
    setTheme(next);
    localStorage.setItem("djorganizer-theme", next);
    if (next === "paper") {
      document.documentElement.setAttribute("data-theme", "paper");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  };

  return (
    <button
      onClick={toggle}
      aria-label="Cambia tema"
      className="inline-flex items-center gap-1.5 uppercase tracking-wider text-muted transition-colors hover:text-fg"
    >
      <span aria-hidden>◑</span>
      {theme === "dark" ? "Paper" : "Dark"}
    </button>
  );
}
```

- [ ] **Step 4: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 5: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/components/ui.tsx frontend/components/clock.tsx frontend/components/theme-toggle.tsx
git commit -m "feat(fe): componenti UI di base (ui.tsx, clock, theme-toggle)"
```

---

## Task 6: Frontend — shell, nav, jobs-provider, layout, pagine placeholder

**Files:**
- Create: `frontend/components/jobs-provider.tsx` (poller dello scan)
- Create: `frontend/components/editorial-shell.tsx`
- Create: `frontend/components/index-nav.tsx` (wordmark DJORGANIZER + 7 sezioni con conteggi)
- Create: `frontend/components/page-layout.tsx` (verbatim da Cratory)
- Modify: `frontend/app/layout.tsx` (no-FOUC + shell)
- Replace: `frontend/app/page.tsx` (redirect → `/sources`)
- Create: `frontend/app/sources/page.tsx`, `app/files/page.tsx`, `app/issues/page.tsx`, `app/duplicates/page.tsx`, `app/plan/page.tsx`, `app/history/page.tsx`, `app/settings/page.tsx` (placeholder "in arrivo"; sources/files saranno riempite nei Task 7–8)

**Interfaces:**
- Consumes: `scanJobStatus`, `startScan`, `libraryStats` (Task 4); `EqMeter` (Task 5); `Clock`, `ThemeToggle` (Task 5).
- Produces: `useJobs()` → `{ scan: ScanJobState, startScan: (rootIds?: number[]) => Promise<void>, refresh: () => void }`; `EditorialShell`, `IndexNav`, `PageLayout`.

- [ ] **Step 1: Crea `frontend/components/jobs-provider.tsx`** (adattato: poller dello scan job)

```tsx
"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { scanJobStatus, startScan as apiStartScan, type ScanJobState } from "@/lib/api";
import { EqMeter } from "./ui";

const IDLE: ScanJobState = {
  status: "idle", phase: null, processed: 0, total: 0,
  result: null, error: null, started_at: null, finished_at: null,
};

type JobsApi = {
  scan: ScanJobState;
  startScan: (rootIds?: number[]) => Promise<void>;
  refresh: () => void;
};

const JobsCtx = createContext<JobsApi>({ scan: IDLE, startScan: async () => {}, refresh: () => {} });

export function useJobs() {
  return useContext(JobsCtx);
}

/**
 * Poller globale del job di scan. Vive nello shell, quindi continua a girare
 * anche cambiando pagina: il progresso è mostrato in una barra fissa in basso
 * finché lo scan è in corso. Le pagine leggono `scan` dal context.
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const [scan, setScan] = useState<ScanJobState>(IDLE);
  const alive = useRef(true);

  const pollOnce = useCallback(async () => {
    try {
      const s = await scanJobStatus();
      if (alive.current) setScan(s);
    } catch {
      /* backend offline: mantieni l'ultimo stato noto */
    }
  }, []);

  const refresh = useCallback(() => { pollOnce(); }, [pollOnce]);

  const startScan = useCallback(async (rootIds?: number[]) => {
    const s = await apiStartScan(rootIds);
    setScan(s);
  }, []);

  useEffect(() => {
    alive.current = true;
    pollOnce();
    const id = setInterval(pollOnce, 1500);
    return () => { alive.current = false; clearInterval(id); };
  }, [pollOnce]);

  const api = useMemo<JobsApi>(() => ({ scan, startScan, refresh }), [scan, startScan, refresh]);

  return (
    <JobsCtx.Provider value={api}>
      {children}
      {scan.status === "running" && <GlobalProgress scan={scan} />}
    </JobsCtx.Provider>
  );
}

function GlobalProgress({ scan }: { scan: ScanJobState }) {
  const pct = scan.total > 0 ? Math.round((scan.processed / scan.total) * 100) : null;
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface px-4 py-2.5">
      <div className="mx-auto flex max-w-5xl items-center gap-4">
        <span className="whitespace-nowrap text-[10px] font-medium uppercase tracking-wider text-muted">
          Scansione{scan.phase ? ` · ${scan.phase}` : ""}
        </span>
        <div className="flex-1"><EqMeter value={pct} className="h-6 w-full" /></div>
        <span className="tnum whitespace-nowrap text-[10px] text-muted">
          {scan.processed}/{scan.total || "?"}{pct != null ? ` · ${pct}%` : ""}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Crea `frontend/components/page-layout.tsx`** (verbatim da Cratory)

```tsx
import type { ReactNode } from "react";

export function PageLayout({
  title, meta, marginalia, marginaliaTitle, children,
}: {
  title?: string;
  meta?: ReactNode;
  marginalia?: ReactNode;
  marginaliaTitle?: string;
  children: ReactNode;
}) {
  return (
    <div className={marginalia ? "lg:grid lg:grid-cols-[1fr_240px]" : ""}>
      <section className="min-w-0 px-5 py-5 lg:px-6 lg:py-6">
        {title && (
          <header className="mb-5 flex items-baseline gap-3 border-b border-border pb-3">
            <h1 className="text-sm font-semibold uppercase tracking-[0.12em] text-fg-strong">{title}</h1>
            {meta != null && <span className="tnum text-xs text-muted">{meta}</span>}
          </header>
        )}
        {children}
      </section>
      {marginalia && (
        <aside className="border-t border-border px-5 py-5 lg:border-l lg:border-t-0 lg:py-6">
          {marginaliaTitle && (
            <div className="mb-3 text-[10px] uppercase tracking-wider text-muted">{marginaliaTitle}</div>
          )}
          {marginalia}
        </aside>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Crea `frontend/components/editorial-shell.tsx`**

```tsx
import type { ReactNode } from "react";
import { IndexNav } from "./index-nav";
import { JobsProvider } from "./jobs-provider";

export function EditorialShell({ children }: { children: ReactNode }) {
  return (
    <JobsProvider>
      <div className="min-h-screen lg:grid lg:grid-cols-[200px_1fr]">
        <aside className="border-b border-border lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-b-0 lg:border-r">
          <IndexNav />
        </aside>
        <main className="min-w-0">{children}</main>
      </div>
    </JobsProvider>
  );
}
```

- [ ] **Step 4: Crea `frontend/components/index-nav.tsx`** (wordmark DJORGANIZER + 7 sezioni con conteggi da `/api/library/stats`)

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { libraryStats, type LibraryStats } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useJobs } from "./jobs-provider";
import { Clock } from "./clock";
import { ThemeToggle } from "./theme-toggle";

const NAV = [
  { href: "/sources", label: "Sources" },
  { href: "/files", label: "Files" },
  { href: "/issues", label: "Issues" },
  { href: "/duplicates", label: "Duplicates" },
  { href: "/plan", label: "Plan" },
  { href: "/history", label: "History" },
  { href: "/settings", label: "Settings" },
] as const;

function sumIssues(s: LibraryStats | null): number {
  if (!s) return 0;
  return Object.values(s.issues_by_severity).reduce((a, b) => a + b, 0);
}

export function IndexNav() {
  const pathname = usePathname();
  const { scan } = useJobs();
  const [stats, setStats] = useState<LibraryStats | null>(null);

  const load = useCallback(() => {
    libraryStats().then(setStats).catch(() => setStats(null));
  }, []);

  // ricarica i conteggi all'avvio e quando uno scan finisce
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (scan.status === "done") load();
  }, [scan.status, load]);

  const counts: Record<string, string> = {
    "/sources": stats ? String(stats.sources) : "—",
    "/files": stats ? String(stats.files_total) : "—",
    "/issues": stats ? String(sumIssues(stats)) : "—",
    "/duplicates": stats ? String(stats.dup_groups) : "—",
    "/plan": "—",
    "/history": "—",
    "/settings": "",
  };

  const isActive = (href: string) => pathname.startsWith(href);

  return (
    <nav className="flex h-full flex-col">
      <div className="px-4 py-4">
        <Link href="/sources" className="block text-sm font-semibold tracking-[0.12em] text-fg-strong">
          DJORGANIZER
        </Link>
        <p className="mt-1 text-[9px] uppercase tracking-wider text-faint">file → rekordbox</p>
      </div>

      <ul className="flex gap-4 overflow-x-auto px-2 pb-3 lg:flex-1 lg:flex-col lg:gap-px lg:overflow-visible lg:pb-0">
        {NAV.map(({ href, label }) => {
          const active = isActive(href);
          return (
            <li key={href} className="shrink-0">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center justify-between gap-2 whitespace-nowrap px-2 py-1.5 text-xs uppercase tracking-wider transition-colors",
                  active
                    ? "border-l-2 border-danger bg-surface-2 text-fg-strong"
                    : "border-l-2 border-transparent text-muted hover:text-fg",
                )}
              >
                <span>{label}</span>
                <span className={cn("tnum text-[10px]", active ? "text-fg" : "text-faint")}>
                  {counts[href]}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="hidden items-center justify-between gap-2 border-t border-border px-4 py-3 text-[10px] lg:flex">
        <Clock />
        <ThemeToggle />
      </div>
    </nav>
  );
}
```

- [ ] **Step 5: Aggiorna `frontend/app/layout.tsx`** (no-FOUC tema + shell)

```tsx
import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { EditorialShell } from "@/components/editorial-shell";

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "DjOrganizer",
  description: "Organizza i file musicali e preparali per Rekordbox",
};

const NO_FOUC = `(function(){try{var t=localStorage.getItem('djorganizer-theme');if(t==='paper'){document.documentElement.setAttribute('data-theme','paper');}}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className={`h-full ${ibmPlexMono.variable}`} suppressHydrationWarning>
      <body className="h-full">
        <script dangerouslySetInnerHTML={{ __html: NO_FOUC }} />
        <EditorialShell>{children}</EditorialShell>
      </body>
    </html>
  );
}
```

- [ ] **Step 6: Sostituisci `frontend/app/page.tsx`** con il redirect

```tsx
import { redirect } from "next/navigation";

export default function Home() {
  redirect("/sources");
}
```

- [ ] **Step 7: Crea le 5 pagine placeholder + 2 stub per sources/files**

Crea un componente placeholder riusabile e le pagine. Per `issues`, `duplicates`, `plan`, `history`, `settings` usa lo stesso markup cambiando il titolo. Esempio `frontend/app/issues/page.tsx`:

```tsx
import { PageLayout } from "@/components/page-layout";
import { EmptyState } from "@/components/ui";

export default function IssuesPage() {
  return (
    <PageLayout title="Issues">
      <EmptyState title="In arrivo">Questa sezione sarà disponibile in un prossimo aggiornamento.</EmptyState>
    </PageLayout>
  );
}
```

Replica identico (cambiando solo `title` e il nome funzione) per:
- `frontend/app/duplicates/page.tsx` → `title="Duplicates"`, `DuplicatesPage`
- `frontend/app/plan/page.tsx` → `title="Plan"`, `PlanPage`
- `frontend/app/history/page.tsx` → `title="History"`, `HistoryPage`
- `frontend/app/settings/page.tsx` → `title="Settings"`, `SettingsPage`

E stub temporanei per le due pagine reali (riempite nei Task 7–8) — `frontend/app/sources/page.tsx`:

```tsx
import { PageLayout } from "@/components/page-layout";

export default function SourcesPage() {
  return <PageLayout title="Sources">…</PageLayout>;
}
```

`frontend/app/files/page.tsx`:

```tsx
import { PageLayout } from "@/components/page-layout";

export default function FilesPage() {
  return <PageLayout title="Files">…</PageLayout>;
}
```

- [ ] **Step 8: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi; le route `/sources /files /issues /duplicates /plan /history /settings` compaiono nell'output del build.

- [ ] **Step 9: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/components/jobs-provider.tsx frontend/components/page-layout.tsx frontend/components/editorial-shell.tsx frontend/components/index-nav.tsx frontend/app/layout.tsx frontend/app/page.tsx frontend/app/sources frontend/app/files frontend/app/issues frontend/app/duplicates frontend/app/plan frontend/app/history frontend/app/settings
git commit -m "feat(fe): shell editoriale, nav 7 sezioni con conteggi, jobs-provider scan, pagine placeholder"
```

---

## Task 7: Frontend — pagina SOURCES

**Files:**
- Create: `frontend/components/add-source.tsx` — riga "aggiungi radice"
- Create: `frontend/components/sources-table.tsx` — tabella radici + scan
- Replace: `frontend/app/sources/page.tsx` — compone il tutto + marginalia ultimo scan

**Interfaces:**
- Consumes: `listSources`, `addSource`, `deleteSource`, `ScanRoot` (Task 4); `useJobs` (Task 6); `Button`, `Input`, `EqMeter`, `EmptyState`, `Alert` (Task 5); `PageLayout` (Task 6); `fmtDate` (Task 4).

- [ ] **Step 1: Crea `frontend/components/add-source.tsx`**

```tsx
"use client";

import { useState } from "react";
import { addSource } from "@/lib/api";
import { Button, Input } from "./ui";

export function AddSource({ onAdded }: { onAdded: () => void }) {
  const [path, setPath] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!path.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await addSource(path.trim(), label.trim() || undefined);
      setPath("");
      setLabel("");
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">Aggiungi radice</div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="/percorso/alla/cartella di musica…"
          className="sm:flex-1"
        />
        <Input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="etichetta"
          className="sm:w-40"
        />
        <Button onClick={submit} disabled={busy || !path.trim()}>+ Aggiungi</Button>
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Crea `frontend/components/sources-table.tsx`**

```tsx
"use client";

import { fmtDate, type ScanRoot } from "@/lib/api";
import { useJobs } from "./jobs-provider";
import { Button, EqMeter } from "./ui";

export function SourcesTable({
  roots, onScan, onDelete,
}: {
  roots: ScanRoot[];
  onScan: () => void;
  onDelete: (id: number) => void;
}) {
  const { scan } = useJobs();
  const running = scan.status === "running";
  const pct = scan.total > 0 ? Math.round((scan.processed / scan.total) * 100) : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="border border-border">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
              <th className="px-3 py-2 font-normal">Path</th>
              <th className="px-3 py-2 font-normal">Label</th>
              <th className="px-3 py-2 text-right font-normal">Files</th>
              <th className="px-3 py-2 font-normal">Ultimo scan</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {roots.map((r) => (
              <tr key={r.id} className="border-b border-surface-2 last:border-0">
                <td className="px-3 py-2 text-fg-strong">{r.path}</td>
                <td className="px-3 py-2 text-muted">{r.label || "—"}</td>
                <td className="tnum px-3 py-2 text-right text-fg">{r.file_count}</td>
                <td className="px-3 py-2 text-muted">{fmtDate(r.last_scanned_at)}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => onDelete(r.id)}
                    aria-label="Rimuovi radice"
                    className="text-faint transition-colors hover:text-danger"
                  >×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {running ? (
        <div className="flex flex-col gap-2 border border-border bg-surface px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-wider text-fg-strong">
              Scansione in corso{scan.phase ? ` · ${scan.phase}` : ""}
            </span>
            <span className="tnum text-xs text-fg-strong">{scan.processed} / {scan.total || "?"}</span>
          </div>
          <EqMeter value={pct} className="h-6 w-full" />
        </div>
      ) : (
        <div>
          <Button onClick={onScan} disabled={roots.length === 0}>▶ Scansiona</Button>
          {scan.status === "error" && (
            <p className="mt-2 text-xs text-danger">Scan fallito: {scan.error}</p>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Sostituisci `frontend/app/sources/page.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { listSources, deleteSource, type ScanRoot } from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { AddSource } from "@/components/add-source";
import { SourcesTable } from "@/components/sources-table";
import { Alert, EmptyState } from "@/components/ui";

export default function SourcesPage() {
  const { scan, startScan, refresh } = useJobs();
  const [roots, setRoots] = useState<ScanRoot[]>([]);
  const [offline, setOffline] = useState(false);

  const load = useCallback(() => {
    listSources()
      .then((r) => { setRoots(r); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);

  useEffect(() => { load(); }, [load]);
  // ricarica conteggi/last_scanned quando uno scan finisce
  useEffect(() => { if (scan.status === "done") load(); }, [scan.status, load]);

  const onScan = async () => { await startScan(); refresh(); };
  const onDelete = async (id: number) => { await deleteSource(id); load(); };

  const r = scan.result;

  return (
    <PageLayout
      title="Sources"
      meta={`${roots.length} radici`}
      marginaliaTitle="Ultimo scan"
      marginalia={
        r ? (
          <div className="flex flex-col gap-1.5 text-xs">
            <Row k="trovati" v={r.found} />
            <Row k="nuovi" v={`+${r.inserted}`} />
            <Row k="aggiornati" v={r.updated} />
            <Row k="spostati" v={r.moved} />
            <Row k="mancanti" v={r.missing} />
            <Row k="errori" v={r.errors} danger={r.errors > 0} />
          </div>
        ) : (
          <p className="text-xs text-faint">Nessuno scan in questa sessione.</p>
        )
      }
    >
      <div className="flex flex-col gap-5">
        {offline && <Alert>Backend non raggiungibile su {process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8010"}. Avvia il server FastAPI.</Alert>}
        <AddSource onAdded={load} />
        {roots.length === 0 && !offline ? (
          <EmptyState title="Nessuna radice">Aggiungi una cartella di musica per iniziare.</EmptyState>
        ) : (
          <SourcesTable roots={roots} onScan={onScan} onDelete={onDelete} />
        )}
      </div>
    </PageLayout>
  );
}

function Row({ k, v, danger }: { k: string; v: string | number; danger?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{k}</span>
      <span className={`tnum ${danger ? "text-danger" : "text-fg"}`}>{v}</span>
    </div>
  );
}
```

- [ ] **Step 4: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 5: Verifica live** (backend + frontend in esecuzione)

In un terminale: `cd backend && DJORG_DATABASE_URL="sqlite:///$HOME/Develop/DjOrganizer01/backend/dev.db" python -m uvicorn app.main:app --port 8010`
In un altro: `cd frontend && npm run dev`
Apri `http://localhost:3000` → reindirizza a `/sources`. Aggiungi una cartella reale di musica, premi "Scansiona": compare il pannello con EqMeter + `processed/total`; a fine scan la marginalia mostra il riepilogo e i conteggi nella nav si aggiornano. Il toggle Dark/Paper funziona.

- [ ] **Step 6: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/components/add-source.tsx frontend/components/sources-table.tsx frontend/app/sources/page.tsx
git commit -m "feat(fe): pagina SOURCES — radici, aggiunta, scan job con EqMeter, marginalia ultimo scan"
```

---

## Task 8: Frontend — pagina FILES

**Files:**
- Create: `frontend/components/files-table.tsx` — tabella densa + indicatori
- Replace: `frontend/app/files/page.tsx` — filtri/sort + marginalia stats

**Interfaces:**
- Consumes: `listFiles`, `libraryStats`, `listSources`, `FileRow`, `LibraryStats`, `ScanRoot`, `FileQuery`, `fmtDuration` (Task 4); `useJobs` (Task 6); `Select`, `Input`, `EmptyState`, `Alert` (Task 5); `PageLayout` (Task 6).

- [ ] **Step 1: Crea `frontend/components/files-table.tsx`** (con l'indicatore issue/doppione)

```tsx
"use client";

import { fmtDuration, type FileRow } from "@/lib/api";
import { cn } from "@/lib/cn";

function Indicator({ row }: { row: FileRow }) {
  const sev = row.worst_severity;
  return (
    <span className="inline-flex items-center justify-center gap-1">
      {row.issue_count > 0 ? (
        <span
          className={cn(
            "tnum",
            sev === "error" ? "text-danger" : sev === "warning" ? "text-warning" : "text-muted",
          )}
        >
          {sev === "error" ? "▲" : "●"}{row.issue_count}
        </span>
      ) : !row.in_dup_group ? (
        <span className="text-faint">·</span>
      ) : null}
      {row.in_dup_group && <span className="text-muted" title="doppione">⧉</span>}
    </span>
  );
}

export function FilesTable({ rows }: { rows: FileRow[] }) {
  return (
    <div className="overflow-x-auto border border-border">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
            <th className="px-3 py-2 font-normal">Path</th>
            <th className="px-3 py-2 font-normal">Artist</th>
            <th className="px-3 py-2 font-normal">Title</th>
            <th className="px-3 py-2 font-normal">Fmt</th>
            <th className="px-3 py-2 text-right font-normal">Kbps</th>
            <th className="px-3 py-2 text-right font-normal">Dur</th>
            <th className="px-3 py-2 text-center font-normal">!</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-surface-2 last:border-0 hover:bg-surface">
              <td className="max-w-[260px] truncate px-3 py-1.5 text-muted" title={r.path}>{r.path}</td>
              <td className="px-3 py-1.5 text-fg">{r.artist || <span className="text-faint">—</span>}</td>
              <td className="px-3 py-1.5 text-fg-strong">{r.title || <span className="text-faint">—</span>}</td>
              <td className="px-3 py-1.5 uppercase text-muted">{r.ext}</td>
              <td className="tnum px-3 py-1.5 text-right text-fg">{r.bitrate ?? "—"}</td>
              <td className="tnum px-3 py-1.5 text-right text-fg">{fmtDuration(r.duration_s)}</td>
              <td className="px-3 py-1.5 text-center"><Indicator row={r} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Sostituisci `frontend/app/files/page.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listFiles, libraryStats, listSources,
  type FileRow, type LibraryStats, type ScanRoot, type FileQuery,
} from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { FilesTable } from "@/components/files-table";
import { Alert, EmptyState, Input, Select } from "@/components/ui";

const LIMIT = 500;

export default function FilesPage() {
  const { scan } = useJobs();
  const [rows, setRows] = useState<FileRow[]>([]);
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [roots, setRoots] = useState<ScanRoot[]>([]);
  const [offline, setOffline] = useState(false);

  const [rootId, setRootId] = useState<string>("");
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [sort, setSort] = useState<FileQuery["sort"]>("path");
  const [q, setQ] = useState("");

  const load = useCallback(() => {
    const query: FileQuery = {
      root_id: rootId ? Number(rootId) : undefined,
      has_issues: onlyIssues ? true : undefined,
      sort,
      q: q.trim() || undefined,
      limit: LIMIT,
    };
    listFiles(query)
      .then((r) => { setRows(r); setOffline(false); })
      .catch(() => setOffline(true));
    libraryStats().then(setStats).catch(() => setStats(null));
  }, [rootId, onlyIssues, sort, q]);

  useEffect(() => { listSources().then(setRoots).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (scan.status === "done") load(); }, [scan.status, load]);

  return (
    <PageLayout
      title="Files"
      meta={stats ? `${rows.length}${stats.files_total > rows.length ? ` di ${stats.files_total}` : ""}` : undefined}
      marginaliaTitle="Libreria"
      marginalia={<Marginalia stats={stats} />}
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}

        <div className="flex flex-wrap items-center gap-2">
          <Select value={rootId} onChange={(e) => setRootId(e.target.value)} className="w-auto">
            <option value="">tutte le radici</option>
            {roots.map((r) => <option key={r.id} value={r.id}>{r.label || r.path}</option>)}
          </Select>
          <Select value={onlyIssues ? "issues" : "all"} onChange={(e) => setOnlyIssues(e.target.value === "issues")} className="w-auto">
            <option value="all">tutti</option>
            <option value="issues">con issue</option>
          </Select>
          <Select value={sort} onChange={(e) => setSort(e.target.value as FileQuery["sort"])} className="w-auto">
            <option value="path">ordina: path</option>
            <option value="artist">ordina: artist</option>
            <option value="title">ordina: title</option>
            <option value="bitrate">ordina: kbps</option>
            <option value="duration">ordina: durata</option>
          </Select>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="cerca…" className="w-48" />
        </div>

        {rows.length === 0 && !offline ? (
          <EmptyState title="Nessun file">Aggiungi una radice in Sources e lancia uno scan.</EmptyState>
        ) : (
          <FilesTable rows={rows} />
        )}
      </div>
    </PageLayout>
  );
}

function Marginalia({ stats }: { stats: LibraryStats | null }) {
  if (!stats) return <p className="text-xs text-faint">—</p>;
  const sev = stats.issues_by_severity;
  const issuesTotal = Object.values(sev).reduce((a, b) => a + b, 0);
  return (
    <div className="flex flex-col gap-4 text-xs">
      <Stat v={stats.files_total} k="file" />
      <div>
        <Stat v={issuesTotal} k="issue" />
        <div className="mt-1 flex gap-3 text-[11px]">
          <span className="text-danger">{sev.error ?? 0} err</span>
          <span className="text-warning">{sev.warning ?? 0} warn</span>
          <span className="text-muted">{sev.info ?? 0} info</span>
        </div>
      </div>
      <Stat v={stats.dup_groups} k="doppioni" />
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">Formati</div>
        <div className="flex flex-col gap-1">
          {Object.entries(stats.by_ext).sort((a, b) => b[1] - a[1]).map(([ext, n]) => (
            <div key={ext} className="flex justify-between">
              <span className="text-muted">{ext}</span>
              <span className="tnum text-fg">{n}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ v, k }: { v: number; k: string }) {
  return (
    <div>
      <div className="tnum text-2xl leading-none text-fg-strong">{v}</div>
      <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">{k}</div>
    </div>
  );
}
```

- [ ] **Step 3: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 4: Verifica live**

Con backend + `npm run dev` attivi e una libreria scansionata (dal Task 7), apri `/files`: tabella densa con Path/Artist/Title/Fmt/Kbps/Dur + indicatore (`▲N` rosso, `●N` giallo, `·`, `⧉`); i filtri (radice, con issue), il sort e la ricerca aggiornano la lista; la marginalia mostra file totali, issue per severità, doppioni e breakdown formati.

- [ ] **Step 5: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/components/files-table.tsx frontend/app/files/page.tsx
git commit -m "feat(fe): pagina FILES — tabella densa con indicatori, filtri/sort/ricerca, marginalia stats"
```

---

## Self-Review

**1. Spec coverage:**
- Scaffold Next 16/React 19/Tailwind 4/TS → Task 3 ✓
- Port design system (globals.css token, EditorialShell, PageLayout, ui.tsx, index-nav, theme-toggle, clock, jobs-provider, EqMeter) → Task 3–6 ✓
- lib/api.ts client → Task 4 ✓
- Pagina SOURCES (add-root + roots table + scan job EqMeter + marginalia ultimo scan) → Task 7 ✓
- Pagina FILES (tabella densa + indicatori + filtri/sort + marginalia stats) → Task 8 ✓
- Endpoint `GET /api/files` (con worst_severity + in_dup_group) → Task 2 ✓
- Endpoint `GET /api/library/stats` → Task 1 ✓
- Nav 7 sezioni con conteggi; placeholder per le sezioni 6b/6c → Task 6 ✓
- Temi Dark/Paper persistiti; stati offline/vuoti → Task 3/5/7/8 ✓
- Test: pytest per i 2 endpoint (Task 1–2); lint+build per il frontend (ogni task FE) ✓

**2. Placeholder scan:** Nessun "TBD/TODO". Le pagine placeholder "in arrivo" (Task 6) sono un deliverable voluto dalla spec, non un buco del piano. Gli stub sources/files del Task 6 sono sostituiti integralmente nei Task 7–8.

**3. Type consistency:**
- `ScanJobState` (api.ts) ↔ `scan_job.job_state()` backend (status/phase/processed/total/result/error/started_at/finished_at) ✓
- `FileRow` frontend ↔ `FileRow` Pydantic (id/root_id/path/ext/artist/title/bitrate/duration_s/status/issue_count/worst_severity/in_dup_group) ✓
- `LibraryStats` frontend ↔ `LibraryStatsRead` Pydantic (files_total/by_ext/issues_by_severity/dup_groups/sources) ✓
- `useJobs()` espone `{ scan, startScan, refresh }`, consumato coerentemente in index-nav, sources-table, sources/page, files/page ✓
- token `--c-warning`/`text-warning` definito in globals.css (Task 3) e usato in files-table + marginalia (Task 8) ✓

---

## Execution Handoff

Piano completo e salvato in `docs/superpowers/plans/2026-06-28-djorganizer-chunk6a-frontend-foundation.md`.
