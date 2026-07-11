# CLAUDE.md

Guidance for working in this repository. Read this before making changes.

## What this is

**Sortory** (formerly *DjOrganizer*) is a personal, local, standalone tool for
**organizing** music folders on disk and preparing them for import into
**Rekordbox**: tag/metadata cleanup, enrichment from external providers, file
renaming and folder structuring, deduplication and quality checks.

It does **not** play audio, does **not** store audio, and does **not** analyze
BPM/key (Rekordbox does that). It is the single writer of textual tags in the
ecosystem.

Place in the chain:

```
Downloads/ → Sortory → Library/{genre}/{artist}/Artist - Title.ext → Rekordbox
```

Sortory is a separate app from **Cratory**, with which it shares the design
system (monospace, editorial, square). The two apps never talk over the network:
the only interface between them is the disk (the tags of the files in `Library/`).

## Naming note (important)

The product was renamed **DjOrganizer → Sortory**, but historical identifiers
were kept for stability. Do **not** "fix" these:

- Local folder is still `DjOrganizer01`.
- Env-var prefix is still `DJORG_` (e.g. `DJORG_DATABASE_URL`).
- SQLite file is still `djorganizer.db`.
- The theme storage key is unchanged.
- GitHub repo: `lucadenegri-dev/Sortory`.

## Layout

```
backend/            FastAPI + SQLAlchemy + SQLite (Python 3.11)
  app/
    main.py         FastAPI entrypoint, CORS, router wiring, .env loading
    core/config.py  pydantic-settings (DJORG_ prefix)
    db.py           engine + ensure_schema()
    models.py       SQLAlchemy models (ScanRoot, AudioFile, Issue, …)
    schemas.py      Pydantic request/response schemas
    routers/        HTTP surface (one file per resource)
    services/       business logic (scanner, planner, apply, dedup, undo, AI, …)
    integrations/   I/O adapters (tag read/write, filesystem ops, HTTP providers)
  tests/            pytest suite (~295 tests)
frontend/           Next.js 16 (App Router) + React 19 + Tailwind v4 + TypeScript
  app/              one route per pipeline page
  components/       shared UI (editorial shell, tables, modals, jobs bar)
  lib/              api client, i18n (en/it)
docs/superpowers/   specs (the "what/why") and plans (the "how"), one per feature
```

## Pipeline (the product model)

```
Sources → scan → Issues → Duplicates → Plan → Apply → History (undo)   + Settings
```

Each frontend page maps to this flow and carries a contextual **Guide** in its
summary. Long jobs (scan, apply, provider search) show a fixed progress bar at
the bottom, coordinated by `components/jobs-provider.tsx`.

## Metadata ownership & precedence

Sortory is the only place that writes Title, Artist, Album, Label, Genre and
Year into file tags. Precedence, most → least authoritative:

```
manual > cleaned file tag > provider (fingerprint > text) > AI from filename
```

Every suggestion stored in `Issue.suggested_fix_json` carries a `source` marker
(`"provider"` | `"ai"`) and, for providers, a `confidence` (`"high"` = certain
match via MBID/ISRC, `"text"` = textual match, to review). A manual fix closes
the issue immediately (`accepted`). Providers overwrite AI/legacy suggestions;
AI never touches an existing `provider` suggestion. **No silent overwrites** —
conflicts stay open issues until the user accepts them.

## Safety principle

Every file operation is first a **plan** the user approves. Changes are in-place
but reversible: deletes go to **quarantine** (never hard-delete) and every run
writes an **undo journal** that can roll everything back.

## Running

Backend (from `backend/`, using the project venv — see below):

```bash
.venv/bin/uvicorn app.main:app --reload --port 8010
```

Frontend (from `frontend/`):

```bash
npm run dev          # Next dev server, defaults to :3000; expects NEXT_PUBLIC_API_BASE
```

## Tests

**Always use the project venv** — the backend uses Python 3.11 syntax
(`X | None`) that breaks under the system Python 3.9:

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

`pytest.ini` sets `filterwarnings = error`, so a new warning fails the suite.

## Configuration

Copy `backend/.env.example` → `backend/.env` and fill in. Env-vars keep the
`DJORG_` prefix; `ANTHROPIC_API_KEY` is the one exception (no prefix — read
directly by the Anthropic SDK via `os.environ`, loaded in `main.py`).

All provider keys are **optional**: without a key the provider degrades cleanly
(inactive), and the pipeline keeps working. See `DEPENDENCIES.md` for the full
list of runtime dependencies, provider keys, and the `fpcalc` binary.

## Internationalization

The UI is being translated **IT → EN** (branch `feat/i18n-it-en`). English is
the default language. Structure:

- `frontend/lib/i18n/en.ts` — the **source of truth** for keys. No `as const`;
  values stay `string`/functions so `it.ts` can type itself as `typeof en`.
- `frontend/lib/i18n/it.ts` — Italian, typed against `en` (a missing key is a
  type error).
- `frontend/lib/i18n/index.tsx` — `I18nProvider` + `useI18n` hook.
- `frontend/lib/i18n/runtime.ts` — non-React access + `translateApiError`.
- Persistence: `localStorage` (avoids flash) mirrored to the backend via
  `GET/PUT /api/settings/language` (`Settings.language` column, default `EN`).

When adding UI strings, add the key to `en.ts` first, then translate in `it.ts`.
Note that **code comments and docstrings in the codebase are largely in Italian**
— match the surrounding language of the file you are editing.

## Conventions

- Backend comments/docstrings: Italian (existing style). Keep it consistent.
- Provider adapters live in `integrations/`; orchestration in `services/`;
  HTTP shape in `routers/` + `schemas.py`. Keep those layers separate.
- Background jobs follow the `*_job.py` pattern with progress reporting.
