# Sortory

> **Documento storico, non operativo.** Descrive Sortory quando era
> un'applicazione autonoma. La fusione F1-F6 l'ha assorbita in Cratory come
> sezione `/organize`: per la guida corrente vedi `CLAUDE.md` e `docs/` nella
> radice del repo. Conservato come riferimento sul perché delle scelte.

Personal, local, standalone tool to **organize** music folders on disk and
prepare them for import into **Rekordbox**: tag/metadata cleanup, enrichment from
external providers, file renaming and folder structuring, deduplication and
quality checks.

It does not play audio, does not store audio, and **does not analyze BPM/key**
(Rekordbox does that).

A separate app from **Cratory**, with which it shares the design system
(monospace, editorial, square). The two apps never talk over the network: the
only interface between them is the disk (the file tags in `Library/`). Sortory
always works 100% on its own.

> Formerly named **DjOrganizer**. Some historical identifiers were kept for
> stability: the local folder (`DjOrganizer01`), the `DJORG_` env-var prefix, and
> the SQLite file (`djorganizer.db`). See [CLAUDE.md](CLAUDE.md).

## Status

Operational end-to-end, ~295 backend tests green. Full pipeline:
`Sources → scan → Issues → Duplicates → Plan → Apply → History (undo)` +
`Settings`. Single owner of the textual metadata (Title/Artist/Album/Label/
Genre/Year): it cleans them, enriches them from external providers, and certifies
their identity via acoustic fingerprint.

Interface: a page-based pipeline with a contextual **Guide** in each page's
summary; long jobs (scan, apply, provider search) show a fixed **progress bar**
at the bottom.

The UI is bilingual **English / Italian** (English is the default); switch the
language in **Settings**. See [Internationalization](#internationalization).

## Place in the chain

`Downloads/` → **Sortory** → `Library/{genre}/{artist}/Artist - Title.ext` →
Rekordbox. The only tag writer in the ecosystem.

## Textual metadata ownership

Sortory is the only point in the ecosystem that writes Title, Artist, Album,
Label, Genre and Year into file tags. Precedence chain, most → least
authoritative:

```
manual > cleaned file tag > provider (fingerprint > text) > AI from filename
```

Every suggestion saved in `Issue.suggested_fix_json` carries a `source` marker
(`"provider"` | `"ai"`) and, for providers, a `confidence` (`"high"` = certain
match via MBID/ISRC, `"text"` = textual match, to review). A manual fix closes
the issue immediately (`accepted`), out of competition. Among open suggestions
the provider overwrites AI and legacy; AI never touches a suggestion already
marked `provider`. No silent overwrites: conflicts stay open issues until you
accept them yourself.

### Actions on the Issues page

- **Resolve Artist/Title with AI** (`/api/issues/ai-suggest`) — Claude Haiku
  derives artist/title from the filename. Manual.
- **Resolve Genre with AI** (`/api/issues/ai-suggest-genre`) — Haiku proposes the
  primary genre from artist+title. Low confidence, to review.
- **Import missing metadata from Providers** (`/api/issues/provider-suggest`) —
  **fingerprint-first**: if the file has no `mbid` and AcoustID is configured, it
  fingerprints before the MusicBrainz→Discogs lookup → exact match and `high`
  confidence; otherwise a textual match. Fills only open issues, never accepts on
  its own.
- **Import all metadata from Providers** (`/api/issues/provider-rescan`) —
  provider search **per track** (not per-issue): re-queries providers on
  **already-tagged** tracks to reclassify the library, creating synthetic
  `provider_override` issues (with confidence) only where the value differs from
  the one on the file. Runs as a **background job** with progress; filterable by
  folder/genre and by field (`genre/album/label/year`); a pop-up asks whether to
  reconsider already accepted/ignored proposals too.
- **Accept all high confidence** (`/api/issues/provider-override/accept-high`) —
  bulk-accepts `high` overrides. Plus *accept fixable* / *ignore info* for bulk
  actions.

## Acoustic fingerprint (AcoustID)

`POST /api/fingerprint` computes the acoustic fingerprint of files (via
`fpcalc`/Chromaprint) and matches them against the AcoustID database to resolve a
certain `AudioFile.mbid`. It is also used automatically by *Import missing/all
metadata from Providers* (fingerprint-first). `GET /api/fingerprint/status`
reports whether the feature is configured (AcoustID key + `fpcalc` binary).
Without it, everything degrades cleanly (textual match only) and the pipeline
keeps working.

## Providers and status

`GET /api/providers` lists the providers (MusicBrainz, Discogs,
AcoustID/Chromaprint, Anthropic) with category, env-var, docs and status
(`configured`/`connected`/`missing`), shown on the **Settings** page in a style
uniform with Cratory.

## Files page

`/api/files` filters by tag (`genre/artist/album/label/ext/year`) and searches by
path/artist/title; `GET /api/library/facets` provides the distinct values for the
filters.

## Configuration (`.env`)

Copy `backend/.env.example` to `backend/.env` and fill it in (env-vars keep the
historical `DJORG_` prefix):

- `DJORG_DATABASE_URL` — local SQLite DB (default `./data/djorganizer.db`).
- `ANTHROPIC_API_KEY` — Anthropic key for the AI actions (Claude Haiku). No
  `DJORG_` prefix. Without it, the AI buttons stay disabled.
- `DJORG_MUSICBRAINZ_USER_AGENT` — no key required, but an identifiable
  User-Agent is needed: put a real contact (email or URL).
- `DJORG_DISCOGS_TOKEN` — optional: works without it (~25 req/min), a free token
  raises it to ~60/min. Generate one at discogs.com/settings/developers.
- `DJORG_ACOUSTID_API_KEY` — free key from acoustid.org/new-application. Also
  needs the `fpcalc` binary: `brew install chromaprint`.

See [DEPENDENCIES.md](DEPENDENCIES.md) for the full dependency list.

## Internationalization

The UI ships in **English (default)** and **Italian**. The chosen language is
persisted per-user in the backend (`Settings.language`, endpoints
`GET/PUT /api/settings/language`) and mirrored to `localStorage` to avoid a flash
on load. Dictionaries live in `frontend/lib/i18n/` — `en.ts` is the source of
truth for keys and `it.ts` is typed against it, so a missing translation is a
compile error.

## Running

Backend (from `backend/`):

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8010
```

Frontend (from `frontend/`):

```bash
npm install && npm run dev
```

Tests (use the venv — the code needs Python 3.11):

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

## Safety principle

Every file operation is first a **plan** you approve. Changes are in-place but
reversible: deletes go to **quarantine** (never hard-delete) and every run writes
an **undo journal** to roll everything back.
