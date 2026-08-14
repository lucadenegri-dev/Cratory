# CLAUDE.md - Guide for the AI collaborator

The single operational guide for the AI working on Cratory.

## Project

**Cratory** is the new name of the app previously called DJ Assistant. It is a personal,
local/self-hosted, single-user web app to import streaming playlists, build DJ set drafts
on owned tracks (BPM/key from Rekordbox), analyze library gaps, do discovery, and identify
mix tracklists. **Metadata enrichment (title/artist/album/label/genre) and tagging
belong to the Organize section** (`/organize`, ex Sortory: absorbed into this app by
the F1-F6 fusion), which is the single writer of textual tags.

The project does not act as a DJ deck (no waveform/cue/queue — that stays with the Set
Builder/Rekordbox) and does not transcode or persist third-party audio. "Does not play
audio" no longer holds in absolute terms: Cratory now plays its **own owned library**,
read-only, for quick audition — `GET /api/tracks/{id}/audio` streams a track's local file
(`has_local_file`) through a single shared docked player, one track at a time, and never
mutates the file (tags remain the Organize section's job). The Shazam module downloads
audio only temporarily for fingerprinting and saves a separate corpus of identified
tracklists. An explicit exception to "does not keep audio files": persistent acquisition via
Soulseek/slskd, which links a file to the existing `Track` in the library
(`has_local_file`/`local_path`/`local_format`/`local_bitrate`). A parallel exception:
per-track SoundCloud download via yt-dlp from the track detail page, which extracts an
MP3 into the same shared download folder (`SLSKD_DOWNLOAD_DIR`) and links it to the
existing `Track` (`has_local_file`/`local_path`/`local_format`/`local_bitrate`); tags
stay the Organize section's job. Eccezione ulteriore, a scope ristretto: il dig di Discovery
riproduce una **preview effimera di terzi** (clip iTunes 30s, in fallback il video
YouTube associato alla release da Discogs, oppure — quando il lead viene da Bandcamp —
lo stream reale per-traccia che Bandcamp restituisce già dentro il risultato del dig,
senza risoluzione aggiuntiva) per valutare un lead prima di acquisirlo; nulla viene
scaricato o conservato in nessun caso. Lo stesso player docked condiviso riproduce sia
questa preview sia le tracce possedute.

## Source of truth

Read in this order:

1. `README.md` - overview, setup and workflow (showcase, in English).
2. `docs/ARCHITECTURE.md` - principles, pipeline, data and integrations.
3. `docs/API.md` - current endpoints.
4. `docs/ROADMAP.md` - current state per area and the real open backlog (state source of truth).
5. `PROGRESS.md` - current state summary; full chronological diary in
   `docs/archive/PROGRESS-diario-completo.md`.
6. `docs/DESIGN.md` - product context and the "editorial archive" design system.
7. `docs/DEPENDENCIES.md` - dependencies and external services reference.

Sortory's own documentation from when it was a separate app is historical reference,
not operational, and lives in `docs/archive/` (see `docs/archive/README.md`). The
fusion that absorbed it into Cratory's `/organize` section is specified in
`docs/archive/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md`.

## Non-negotiable rules

1. **Separate the deterministic engine and the AI.** Import, normalization, de-duplication,
   scoring, roles, gap analysis, discovery ranking and validation are deterministic code.
   The AI's job is intent interpretation, pool curation (mood-fit, anchor hints) and
   narrative/explanations — never sequencing: the deterministic engine always builds the
   tracklist.
2. **BPM/key: Rekordbox è la fonte primaria, l'analisi in-app (Essentia, pagina
   Analisi) è l'alternativa deterministica.** Ogni valore ha una provenienza
   esplicita (`bpm_source`/`key_source`: manual > rekordbox > cratory); il
   dettaglio delle regole di sovrascrittura e dell'apply è in `docs/API.md`
   (sezioni rekordbox e analysis). Cratory non chiede MAI BPM/key a un'AI
   (per lo streaming vedi regola 3). `energy` è un derivato deterministico.
   Beatgrid/cue restano fuori scope; nessuna integrazione live con Rekordbox.
3. **Streaming does not provide mixing features.** Spotify gives track identity, editorial
   metadata, covers, duration, ISRC, URLs and playlists.
4. **The AI never receives the whole library.** It only receives candidates filtered by the
   Candidate Engine: pool cap 200, seen by any single call in batches of at most 60.
5. **Every AI output is validated.** Use Pydantic schemas and deterministic checks
   (schema-constrained outputs, foreign ids and out-of-bounds values discarded with
   warnings) before showing or saving results.
6. **The AI does not invent factual data.** It must distinguish external source, musical
   inference and creative hypothesis.
7. **The library is the disk.** Ownership (`has_local_file`) comes from indexing
   `LIBRARY_ROOT` (re-linking by `audio_hash`); streaming playlists are leads. Cratory reads
   the files but never mutates them: tags are written only by the Organize section.
   Owned files are also **playable, read-only** (`GET /api/tracks/{id}/audio`, one
   track at a time via the shared docked player, for quick audition) — playback never
   touches the file or its tags.

## Stack and layout

Backend Python + FastAPI, SQLAlchemy over SQLite, Pydantic. Frontend Next.js 16 with the App
Router, React and Tailwind/design system. External integrations behind interfaces in
`backend/app/integrations/`, with caching and error/rate-limit handling where needed.

Backend layers:

```text
backend/app/
  routers/       mostly HTTP-only, but not a hard rule — a few carry real
                 logic (best-transition ranking in transitions.py,
                 ISRC/artist+title matching in dj_sets.py, one rule per
                 export format in sets.py): tracks, playlists, sets,
                 transitions, labels, analysis, rekordbox, discovery,
                 dj_sets (=/api/shazam), downloads, files, slskd,
                 soundcloud, spotify, ai, pipeline, services, settings —
                 full list and grouping in docs/ARCHITECTURE.md
  services/      deterministic logic and orchestration
  repositories.py
  models.py
  db.py          session/engine, ensure_schema and idempotent migrations
  schemas.py
  serializers.py
  integrations/
  core/
  tools/         maintenance scripts: clean_user_data, merge_duplicate_tracks
  organize/      the ex-Sortory section, under its own namespace:
                 models.py (AudioFile, Issue, DupGroup, DupMember, Plan,
                 PlanOp, UndoJournal, Settings, ScanRoot),
                 routers/ (scan, analyze, issues, duplicates, plan, apply,
                 history, …), services/ (scanner, planner, apply, dedup,
                 undo, inspector, …), integrations/ (tagio, fsops,
                 acoustid, musicbrainz, …).
                 `AudioFile` lives here, not in the core `models.py` — the
                 core `Track` reaches it through `primary_file_id` and the
                 effective-tag COALESCE in `repositories.py`, and the one
                 relationship that crosses the boundary (`AudioFile.track`)
                 is declared on the Organize side with a backref, so
                 `app/models.py` stays independent. Its HTTP surface is
                 entirely under `/api/organize/*`.
```

No enrichment chain outside Organize: BPM/key come from Rekordbox/Essentia, text
metadata from Organize's own providers under `organize/integrations/`. Discovery's
own providers are Discogs and Bandcamp (dig "Scava", two sources behind the
`DigSource` protocol), plus Spotify as an identity resolver; Discogs is queried a
second time, through Organize's own separate client, for text-metadata proposals —
never the same client object across the boundary. `backend/app/integrations/` also
holds clients that are neither Discovery's nor enrichment's — SoundCloud, slskd,
Shazam, the LLM client, local file serving — for import, acquisition, mix
identification and AI curation.

Discovery works by taste, not by technical compatibility (that stays with the Set Builder):
the dig "Scava" uses Discogs or Bandcamp by genre/label, with Spotify only as an identity
resolver.
Spotify `/recommendations` must not be used: for new apps or in development mode it returns
403/404.

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
