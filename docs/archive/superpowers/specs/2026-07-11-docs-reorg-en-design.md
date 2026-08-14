# Documentation reorganization + English + dependencies file — Design

**Date:** 2026-07-11
**Branch:** `claude/reorganize-project-docs-2d2144`
**Status:** approved (design)

## Goal

Reorganize and simplify Cratory's documentation, translate it to English, and add a
dedicated dependencies reference. Reduce duplication across the doc set while keeping a
single source of truth for each concern.

## Coordination constraint (parallel session)

A parallel session on branch `i18n-it-en` is doing frontend i18n and **also edits
`docs/API.md` (+20 lines) and `docs/ARCHITECTURE.md` (+2 lines)**. To avoid merge
conflicts, **this session must NOT touch `docs/API.md` or `docs/ARCHITECTURE.md`.** They
will be translated/reconciled in a later session, after the i18n branch merges.

## Decisions (from brainstorming)

1. **Consolidate** into fewer files (not just clean each file in place).
2. **Everything in English**, including `CLAUDE.md` and `PROGRESS.md`.
3. **Do not touch** `docs/API.md` and `docs/ARCHITECTURE.md` (parallel session owns them).
4. **ROADMAP:** remove the `Stato completato` changelog; history lives only in PROGRESS.
5. **PRODUCT.md:** merge into `docs/DESIGN.md` (which becomes "Product & Design"); delete
   `PRODUCT.md`.
6. **DEPENDENCIES:** new file at `docs/DEPENDENCIES.md`; `AUDIT-2026-07-05.md` stays frozen
   (dated historical snapshot, NOT translated).

## Target document set (all English unless noted)

### Root

| File | Action |
|---|---|
| `README.md` | Keep (already EN). Update the "Documentation" table to the new structure; remove the "reference docs are in Italian" note; point to `docs/DEPENDENCIES.md`. |
| `CLAUDE.md` | Translate to EN and slim. The "regole non negoziabili" restate ARCHITECTURE — condense them. Keep it the AI operational guide (source-of-truth reading order, rules, stack/layout, track identity, commands). Update the reading-order list to the new file names/roles. |
| `PROGRESS.md` | Translate to EN. Becomes the single home of chronological history. |

### docs/

| File | Action |
|---|---|
| `ARCHITECTURE.md` | **Untouched** (parallel session). |
| `API.md` | **Untouched** (parallel session). |
| `ROADMAP.md` | Translate to EN. **Remove the `Stato completato` changelog.** Replace with a short "Current state" paragraph pointing to PROGRESS. Keep: naming, current phase, next steps, technical backlog, audit-backlog summary (still references `AUDIT-2026-07-05.md`), risks, consolidated decisions. |
| `DESIGN.md` | Translate remaining Italian phrases to EN. **Absorb `PRODUCT.md`** (users, job-to-be-done, product purpose, brand personality, anti-references, design principles, accessibility) as a "Product context" front section. Keep the YAML frontmatter (design tokens) intact. Retitle to reflect "Product & Design". |
| `PRODUCT.md` | **Deleted** (content moved into DESIGN.md). |
| `DEPENDENCIES.md` | **New.** See below. |
| `AUDIT-2026-07-05.md` | **Frozen.** No translation, no content change. Remains linked from ROADMAP for backlog IDs. |

## DEPENDENCIES.md — content spec

Grounded in the actual manifests (`backend/requirements.txt`, `frontend/package.json`),
not invented. Sections:

1. **System requirements** — Python 3.12+, Node.js 20+, system `ffmpeg` (Shazam), and note
   `fpcalc`/chromaprint only if `pyacoustid` is kept (see finding below).
2. **Backend (Python)** — grouped by purpose, each with the pinned range and one-line role:
   - Web/API: `fastapi`, `uvicorn[standard]`, `python-multipart` (rekordbox.xml upload)
   - Data/validation: `sqlalchemy`, `pydantic`, `pydantic-settings`
   - HTTP client: `httpx`
   - AI: `anthropic`
   - Shazam / mix identification: `yt-dlp`, `shazamio`, `mutagen`
   - XML security: `defusedxml`
   - Testing: `pytest`
3. **Frontend (Node)** — `next` 16.2.9, `react`/`react-dom` 19, `lucide-react`; dev:
   `tailwindcss` v4 + `@tailwindcss/postcss`, `typescript`, `eslint` + `eslint-config-next`,
   `@types/*`.
4. **External services & runtime dependencies** (not package deps, but required to run
   features): Spotify Web API (identity/metadata), Last.fm (Discovery), Discogs (Discovery
   "Scava"), slskd daemon (file acquisition), Rekordbox XML export (BPM/key), sibling
   Sortory app (tagging/enrichment, optional).
5. **Finding / cleanup note:** `pyacoustid` is still in `requirements.txt` with an AcoustID
   comment, but AcoustID fingerprinting was removed in the 2026-07 pivot (per ROADMAP). Flag
   it as a likely dead dependency to verify/remove. **This is a documentation finding only —
   do not edit `requirements.txt` in this session** (keep docs work and code cleanup
   separate). If confirmed dead, remove `fpcalc`/chromaprint from system requirements too.

Location: `docs/DEPENDENCIES.md`, linked from README (Documentation table + a pointer near
Quickstart's prerequisites).

## Non-goals

- No edits to `docs/API.md` or `docs/ARCHITECTURE.md`.
- No edits to `requirements.txt` / `package.json` (deps cleanup is a separate task; this
  session only documents).
- No translation of `AUDIT-2026-07-05.md`.
- No new content invented — translation + reorganization + a dependencies doc derived from
  existing manifests and docs.

## Cross-reference integrity (must verify at the end)

After the moves, every internal doc link must still resolve:
- README "Documentation" table → new file set (no PRODUCT.md link; add DEPENDENCIES.md).
- CLAUDE.md reading-order list → updated names/roles (no PRODUCT.md).
- PROGRESS.md header pointer → ROADMAP/README/ARCHITECTURE/CLAUDE.
- ROADMAP → PROGRESS (history), AUDIT-2026-07-05 (backlog IDs), DESIGN.
- DESIGN.md self-references and any `PRODUCT.md`/`DESIGN.md` links updated.
- Grep the repo for `PRODUCT.md` references and fix all.

## Definition of done

- All target docs are in English (except the frozen AUDIT).
- `PRODUCT.md` deleted; its content lives in DESIGN.md.
- ROADMAP has no `Stato completato` changelog; history is in PROGRESS.
- `docs/DEPENDENCIES.md` exists and matches the real manifests.
- No internal link points to a moved/deleted file.
- `docs/API.md` and `docs/ARCHITECTURE.md` are byte-for-byte unchanged.
