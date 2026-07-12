# CLAUDE.md - Guide for the AI collaborator

The single operational guide for the AI working on Cratory.

## Project

**Cratory** is the new name of the app previously called DJ Assistant. It is a personal,
local/self-hosted, single-user web app to import streaming playlists, build DJ set drafts
on owned tracks (BPM/key from Rekordbox), analyze library gaps, do discovery, and identify
mix tracklists. **Metadata enrichment (title/artist/album/label/genre) and tagging are
Sortory's job.**

The project does not play audio. The Shazam module downloads audio only temporarily for
fingerprinting and saves a separate corpus of identified tracklists. An explicit exception
to "does not keep audio files" (the "does not play" still holds): persistent acquisition via
Soulseek/slskd, which links a file to the existing `Track` in the library
(`has_local_file`/`local_path`/`local_format`/`local_bitrate`).

## Source of truth

Read in this order:

1. `README.md` - overview, setup and workflow (showcase, in English).
2. `docs/ARCHITECTURE.md` - principles, pipeline, data and integrations.
3. `docs/API.md` - current endpoints.
4. `docs/ROADMAP.md` - status, naming, backlog and next steps (state source of truth).
5. `PROGRESS.md` - chronological diary to resume work.
6. `docs/DESIGN.md` - product context and the "editorial archive" design system.
7. `docs/DEPENDENCIES.md` - dependencies and external services reference.

## Non-negotiable rules

1. **Separate the deterministic engine and the AI.** Import, normalization, de-duplication,
   scoring, roles, gap analysis, discovery ranking and validation are deterministic code.
   Narrative, prompt interpretation and explanations are AI.
2. **BPM/key: Rekordbox è la fonte primaria, l'analisi in-app è l'alternativa
   deterministica.** Il flusso principale resta l'export XML da Rekordbox
   (`/api/rekordbox/import`). In più la pagina Analisi può calcolare BPM/key
   in-app (Essentia, deterministico) sulle tracce possedute. Ogni valore ha una
   provenienza esplicita (`bpm_source`/`key_source`: manual > rekordbox >
   cratory): l'import Rekordbox di default sovrascrive i valori `cratory` e
   protegge quelli `manual` (con `?overwrite=true` vince su tutto); l'analisi
   in-app scrive i campi `analysis_*` e tocca i canonici solo via apply (i vuoti
   in automatico, il resto su azione esplicita, la riscrittura totale con
   force). Cratory non chiede MAI BPM/key a un'AI né a provider streaming.
   `energy` è un derivato deterministico (da BPM+genere o dai file audio).
   Beatgrid/cue restano fuori scope; nessuna integrazione live con Rekordbox.
3. **Streaming does not provide mixing features.** Spotify gives track identity, editorial
   metadata, covers, duration, ISRC, URLs and playlists.
4. **The AI never receives the whole library.** It only receives candidates filtered by the
   Candidate Engine, with a cap of 60.
5. **Every AI output is validated.** Use Pydantic schemas and the Validation Engine before
   showing or saving results.
6. **The AI does not invent factual data.** It must distinguish external source, musical
   inference and creative hypothesis.
7. **The library is the disk.** Ownership (`has_local_file`) comes from indexing
   `LIBRARY_ROOT` (re-linking by `audio_hash`); streaming playlists are leads. Cratory reads
   the files but never mutates them: tags are written only by Sortory.

## Stack and layout

Backend Python + FastAPI, SQLAlchemy over SQLite, Pydantic. Frontend Next.js 16 with the App
Router, React and Tailwind/design system. External integrations behind interfaces in
`backend/app/integrations/`, with caching and error/rate-limit handling where needed.

Backend layers:

```text
backend/app/
  routers/       HTTP only: playlists, tracks, transitions, sets, spotify,
                 rekordbox, ai, discovery, services, labels, dj_sets,
                 downloads, files, pipeline
  services/      deterministic logic and orchestration
  repositories.py
  models.py
  db.py          session/engine, ensure_schema and idempotent migrations
  schemas.py
  serializers.py
  integrations/
  core/
```

No enrichment chain: BPM/key from Rekordbox, text metadata from Sortory. The remaining
external providers serve **Discovery only**: Last.fm (similarity), Discogs (dig "Scava"),
Spotify (resolver).

Discovery works by taste, not by technical compatibility (that stays with the Set Builder):
playlist expansion is Last.fm-centric (similarity) with a Spotify resolver via `/search`; the
dig "Scava" uses Discogs by genre/label. Spotify `/recommendations` must not be used: for new
apps or in development mode it returns 403/404.

## Track identity

- Streaming identity: `platform`, `platform_track_id`, `isrc`, `url`.
- De-duplication: `ISRC -> platform_track_id -> artist+title+duration -> fuzzy artist+title`.
- Track states: `imported | ready_for_set` (ready = BPM+key present).

## Commands

Backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
python -m pytest tests
```

Windows PowerShell:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
.\.venv\Scripts\python.exe -m pytest tests
```

Frontend:

```bash
cd frontend
npm run dev
npm run lint
npm run build
```

## Frontend

Next.js 16 has breaking changes compared to the known versions: in the frontend always read
`frontend/CLAUDE.md` before modifying pages or routing.
