# Dependencies

A single reference for everything Sortory needs to run: language runtimes,
Python packages, Node packages, the external `fpcalc` binary, and the external
provider services (all optional, all degrade cleanly).

## Runtimes / toolchain

| Tool    | Version              | Notes |
|---------|----------------------|-------|
| Python  | **3.11** (3.11.15)   | Backend uses `X \| None` syntax — 3.9 breaks. Use `backend/.venv`. |
| Node.js | ≥ 20                 | `@types/node` pinned to `^20`; needed for Next.js 16. |
| npm     | bundled with Node    | Manages the frontend (`package-lock.json` committed). |
| SQLite  | via Python stdlib    | Local file DB, no server. |
| fpcalc / Chromaprint | any recent | **External binary**, optional. `brew install chromaprint`. Needed only for acoustic fingerprinting. |
| ffmpeg  | any recent           | **External binary**, optional. `brew install ffmpeg`. Needed only for the file-integrity check (`integrations/integrity.py`): decodes each file to find corrupt/truncated ones. Without it the check is inactive. |

## Backend — Python (`backend/requirements.txt`)

| Package             | Purpose |
|---------------------|---------|
| `fastapi`           | HTTP framework / API layer. |
| `uvicorn[standard]` | ASGI server (dev + run). |
| `sqlalchemy` `>=2.0`| ORM (`app/models.py`, `app/db.py`). |
| `pydantic` `>=2`    | Request/response schemas (`app/schemas.py`). |
| `pydantic-settings` | Env-driven config, `DJORG_` prefix (`app/core/config.py`). |
| `mutagen`           | Read/write audio tags (`integrations/tagio.py`). |
| `anthropic`         | Claude Haiku calls for the "Resolve with AI" features (`services/ai_tags.py`). |
| `pyacoustid`        | Acoustic fingerprint lookup against AcoustID (`integrations/acoustid.py`); shells out to `fpcalc`. |
| `python-dotenv`     | Loads `backend/.env` into `os.environ` at startup (`main.py`). |
| `httpx`             | HTTP client for provider integrations + FastAPI test client. |
| `pytest`            | Test runner (`backend/tests`, ~295 tests). |

Install:

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> The standard-library `sqlite3`, `pathlib`, `contextlib`, `datetime`, etc. are
> used throughout but require no install.

## Frontend — Node (`frontend/package.json`)

### Runtime dependencies

| Package        | Version  | Purpose |
|----------------|----------|---------|
| `next`         | 16.2.9   | React framework, App Router. |
| `react`        | 19.2.4   | UI library. |
| `react-dom`    | 19.2.4   | React DOM renderer. |
| `lucide-react` | ^1.18.0  | Icon set. |

### Dev dependencies

| Package                  | Version  | Purpose |
|--------------------------|----------|---------|
| `typescript`             | ^5       | Type checking. |
| `tailwindcss`            | ^4       | Styling. |
| `@tailwindcss/postcss`   | ^4       | Tailwind v4 PostCSS plugin. |
| `eslint`                 | ^9       | Linting. |
| `eslint-config-next`     | 16.2.9   | Next.js ESLint rules. |
| `@types/node`            | ^20      | Node type defs. |
| `@types/react`           | ^19      | React type defs. |
| `@types/react-dom`       | ^19      | React DOM type defs. |

Install:

```bash
cd frontend
npm install
```

## External provider services

All optional. Missing a key/binary simply deactivates that provider — the
pipeline keeps working (clean degradation). Configured via `backend/.env`
(see `backend/.env.example`).

| Provider              | Env var / requirement            | Key required? | Used for |
|-----------------------|----------------------------------|---------------|----------|
| **Anthropic (Claude Haiku)** | `ANTHROPIC_API_KEY` (no `DJORG_` prefix) | Yes, for AI actions | "Resolve with AI" (artist/title) and "Suggest genre". |
| **MusicBrainz**       | `DJORG_MUSICBRAINZ_USER_AGENT`   | No key, but needs an identifiable User-Agent (real contact email/URL) | Textual metadata + MBID resolution. |
| **Discogs**           | `DJORG_DISCOGS_TOKEN`            | Optional (works at ~25 req/min without, ~60 req/min with a free token) | Fills missing label/style/year. |
| **AcoustID**          | `DJORG_ACOUSTID_API_KEY` **+** `fpcalc` binary | Yes (key + binary) for fingerprinting | Acoustic fingerprint → certain `AudioFile.mbid`; enables fingerprint-first provider lookup. |

Getting keys:

- Anthropic: <https://console.anthropic.com/> → API Keys
- Discogs token: <https://www.discogs.com/settings/developers>
- AcoustID key: <https://acoustid.org/new-application> (and `brew install chromaprint` for `fpcalc`)

## Cross-cutting env vars

| Var                     | Default                              | Where |
|-------------------------|--------------------------------------|-------|
| `DJORG_DATABASE_URL`    | `sqlite:///./data/djorganizer.db`    | backend |
| `DJORG_COVER_CACHE_DIR` | `./data/cover_cache`                 | backend (git-ignored) |
| `NEXT_PUBLIC_API_BASE`  | `http://localhost:8010`              | frontend |

See [CLAUDE.md](CLAUDE.md) for architecture and [README.md](README.md) for the
product overview.
