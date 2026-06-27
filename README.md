# Cratory

> A personal, self-hosted workbench that turns streaming playlists into thought-out DJ sets.
> (Formerly "DJ Assistant"; legacy technical names like `djassistant.db` are kept for local compatibility.)

Cratory is a personal, local/self-hosted, single-user web app for DJ set preparation. It
imports Spotify playlists (or pasted tracklists), normalizes and de-duplicates tracks,
enriches them with mixing features (BPM, Camelot key, mood, energy) from external
providers, analyzes library gaps, generates explained set drafts, and helps you discover
music that fits your taste.

It is **not a SaaS** — and that is a design choice, not a limitation. Spotify's Web API
forbids a public multi-tenant Spotify app (development mode caps at 5 users; extended
quota needs a launched organization with 250k+ monthly users), so Cratory leans the other
way on purpose: a single-user tool where the value is product quality, not scale. It never
plays or stores audio — the Shazam module downloads audio only temporarily to fingerprint
external mixes, and persists only the identified tracklist.

## Features

- Import Spotify playlists, liked tracks, and pasted tracklists.
- De-duplicate by `ISRC → platform id → artist/title/duration → fuzzy match`.
- Enrich features via Deezer, MusicBrainz, AcousticBrainz, GetSongBPM and Last.fm —
  keeping source and confidence, and never overwriting existing BPM/key.
- Manual corrections for BPM, Camelot, mood, energy, genre and label (manual wins).
- Generate sets with a deterministic engine plus optional, validated AI.
- Classify transitions as technically safe, creative risk, or good reset.
- Discovery by taste: expand a playlist (Last.fm + Spotify resolver) or crate-dig by
  genre/label via Discogs ("Scava").
- Identify mix tracklists via Shazam/yt-dlp/ffmpeg into a corpus kept separate from the library.

## Architecture at a glance

![Cratory architecture](docs/architettura.svg)

A **deterministic engine** owns the facts: import, de-duplication, enrichment, scoring,
roles, gap analysis, discovery ranking and validation. The **AI layer** owns language:
prompt interpretation, narrative direction and explanations. The AI never sees the whole
library — the Candidate Engine passes it at most 60 candidates — and every AI output is
validated against Pydantic schemas before it is shown or saved. BPM, key and musical
features are never invented: they come from providers or explicit manual correction.

Full picture in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech stack

```text
Backend:   Python, FastAPI, SQLAlchemy, Pydantic
Frontend:  Next.js 16, React, Tailwind / design system
Database:  SQLite (local); PostgreSQL in backlog
AI:        LLM behind an interface, outputs validated with Pydantic
External:  Spotify, Deezer, MusicBrainz, AcousticBrainz, GetSongBPM, Last.fm, Discogs, Shazam
```

## Quickstart

Prerequisites: Python 3.12+, Node.js 20+. The Shazam module also needs system `ffmpeg`
plus the `yt-dlp` and `shazamio` Python dependencies (in `backend/requirements.txt`).

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Local URLs: app at `http://localhost:3000`, API docs at `http://localhost:8000/docs`,
health at `http://localhost:8000/api/health`.

## Configuration

Variables live in `backend/.env` (start from `backend/.env.example`).

Minimum for Spotify import:

```text
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/spotify/callback
```

Recommended providers:

```text
MUSICBRAINZ_USER_AGENT=
GETSONGBPM_API_KEY=
LASTFM_API_KEY=
DISCOGS_TOKEN=
DEEZER_ENABLED=true
ACOUSTICBRAINZ_ENABLED=true
AI_API_KEY=
AI_MODEL=
AI_MODEL_CREATIVE=
```

Spotify provides track identity, editorial metadata, covers, duration, ISRC, URLs and
playlists — not reliable mixing BPM/key. `DISCOGS_TOKEN` is optional: Discovery "Scava"
works without it; the token only raises the rate limit.

## Database

The canonical local database is `backend/data/djassistant.db` (the legacy name is kept on
purpose). Relative SQLite paths in `DATABASE_URL` resolve against `backend/`, so the app
doesn't create stray databases per working directory. To wipe user data:

```bash
cd backend
python -m app.tools.clean_user_data library --include-backups
```

The `library` mode clears playlists, tracks, sets and the enrichment cache while preserving
Spotify tokens; `all` also removes tokens unless `--preserve-tokens` is passed.

## Workflow

Start backend + frontend → in Settings, connect Spotify → import a playlist or paste a
tracklist → let enrichment run → fix any important missing BPM/key → generate a set
(technical or creative) → review transitions, warnings and alternatives → export or create
a Spotify playlist → use Discovery (expand, or "Scava" by genre/label via Discogs) to find
tracks that fit your taste.

## Tests

```bash
cd backend && python -m pytest tests
cd frontend && npm run lint && npm run build
```

## Documentation

| Document | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Principles, pipeline, backend layers, data model, integrations |
| [docs/API.md](docs/API.md) | Current FastAPI REST contracts |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Status, naming, backlog, next steps — the source of truth for project state |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Product brief: users, job-to-be-done, principles |
| [docs/DESIGN.md](docs/DESIGN.md) | Design system ("editorial archive") |
| [PROGRESS.md](PROGRESS.md) | Chronological work diary |
| [CLAUDE.md](CLAUDE.md) | Guide for the AI collaborator |

> Note: the README is in English as the project's showcase; the reference docs above are in
> Italian (except the design system).

## Status

Core is settled; documentation has been reworked; the next open front is Discovery quality.
See [docs/ROADMAP.md](docs/ROADMAP.md) for the current state and backlog.
