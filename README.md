# Cratory

> A self-hosted workbench for preparing DJ sets out of a music library you actually own.

Cratory is a single-user web app that sits between your streaming accounts and your record
bag. It imports playlists from Spotify and SoundCloud, matches them against the music you
already have on disk, fills in BPM and key from Rekordbox or from its own analysis, and
builds set drafts out of tracks you can actually play. It runs entirely on your machine,
against a SQLite file and your own music folder.

The distinction it is built around: **a streaming playlist is a list of leads, your disk is
the library.** A track you found on Spotify is a candidate to acquire; only a file you own
can go into a set.

## What it does

**Library and imports**

- Import playlists and liked tracks from Spotify and SoundCloud, or paste a tracklist as text.
- De-duplicate on the way in: ISRC → platform id → artist/title/duration → fuzzy match.
- Index your music folder. Ownership comes from the disk and survives renames and moves via
  audio hash. Owned tracks play in-app, read-only, through a shared docked player — for a
  quick audition, not for mixing.

**BPM and key**

- Import a Rekordbox collection XML, or analyze files in-app with Essentia. Every value
  carries its source (`manual` > `rekordbox` > `cratory`); in-app results land in staging
  fields and reach the canonical ones only through an explicit apply. `energy` is derived.

**Set building**

- A deterministic generator builds the tracklist in two phases — a skeleton first, then a
  beam search per segment — from owned tracks only.
- Each transition is classified as technically safe, a creative risk, or a good reset. Gap
  analysis reads a playlist for structural holes: no openers, no peak, missing BPM bridges,
  flat energy, harmonic dead ends.
- Export as text, CSV, Markdown or M3U8 (for Rekordbox), or push the set to Spotify as a playlist.

**Discovery and acquisition**

- Dig by genre or label through Discogs or Bandcamp, ranked by taste rather than by technical
  fit, with an ephemeral preview so you can hear a lead before committing to it.
- A wishlist tracks everything you don't own yet, with buy links. Optional acquisition through
  your own slskd (Soulseek) daemon, or a per-track SoundCloud download, links the file back to
  the track already in your library.
- Identify the tracklist of a mix from a URL (yt-dlp → ffmpeg → Shazam), into a corpus kept
  separate from the library.

**Organize** — the one part of Cratory that writes to disk: scan for tag problems, group
duplicates, build a rename/move/retag plan, review it, apply it, undo it. Metadata proposals
come from MusicBrainz/AcoustID, Discogs and cover-art lookups.

## Two rules that shape everything

**The AI never sequences.** Import, de-duplication, scoring, roles, gap analysis, discovery
ranking and validation are ordinary deterministic code. The model interprets what you asked
for, judges mood-fit and writes explanations. It never sees the whole library — the candidate
engine caps its pool at 200 tracks, 60 per call — and every response is validated against a
Pydantic schema before anything is shown or saved: invented ids and out-of-bounds values are
dropped with a warning, and a failed call degrades to the deterministic default.

**BPM and key are measured, never guessed.** They come from a Rekordbox export or from in-app
Essentia analysis — both deterministic, both with explicit provenance. Cratory never asks a
model or a streaming provider for them.

## Quickstart

Prerequisites: **Python 3.11** and **Node.js 20.9+**. Python 3.11 specifically — the pinned
Essentia build behind in-app BPM/key analysis only ships a CPython 3.11 wheel, and only for
macOS arm64 at that — coverage on other platforms is patchy. `ffmpeg` is
needed for mix identification, `fpcalc` (chromaprint) for Organize's acoustic fingerprinting.

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

App on `http://localhost:3000`, API docs on `http://localhost:8000/docs`, health check on
`http://localhost:8000/api/health`. The frontend proxies `/api/*` through to the backend, so
there is nothing to configure on that side.

Shortcut: `./start-dev.sh` (macOS/Linux) or `start-dev.bat` (Windows) brings up both, plus a
local slskd on `:5030` if one is installed.

## Configuration

Everything lives in `backend/.env`, copied from `backend/.env.example`. The app starts fine
with that file untouched; each key switches a feature on.

| Key | Enables |
|---|---|
| `LIBRARY_ROOT` | Indexing your music folder. Without it nothing is ever owned. |
| `SPOTIFY_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` | Spotify import and playlist export (connect from Settings) |
| `ANTHROPIC_API_KEY` | AI set curation and Organize's tag suggestions — one key for both |
| `DISCOGS_TOKEN` | Raises the Discogs rate limit and adds cover art; digging works without it |
| `SLSKD_URL` / `_API_KEY` / `_DOWNLOAD_DIR` | Soulseek acquisition via your own slskd instance |
| `ACOUSTID_API_KEY` | Acoustic fingerprint lookups in Organize (needs `fpcalc` too) |
| `ARCHIVE_ROOT` | A folder of discarded tracks, recognized alongside the library |

The database is `backend/data/djassistant.db` — a legacy filename, kept on purpose. Relative
SQLite paths in `DATABASE_URL` resolve against `backend/`, so the app never scatters stray
databases per working directory. To wipe user data:

```bash
cd backend && python -m app.tools.clean_user_data library --include-backups   # --dry-run to preview
```

`library` clears playlists, tracks and sets but keeps your Spotify tokens; `all` drops those too.

## Tests

```bash
cd backend && python -m pytest tests
cd frontend && npm run lint && npm run test:unit && npm run build
```

`npm run test:e2e` runs the Playwright suite, which spins up its own backend on `:8211`
against a throwaway database.

## Documentation

| Document | What's in it |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Principles, pipelines, backend layers, data model, integrations |
| [docs/API.md](docs/API.md) | The REST contracts, endpoint by endpoint |
| [docs/DESIGN.md](docs/DESIGN.md) | Product thinking and the "editorial archive" design system |
| [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) | Every dependency and external service, and why it's there |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Backlog, open questions, what's next |

## Scope, and a note on responsible use

Cratory is not a DJ deck — no waveforms, no cues, no queue; that stays in Rekordbox — and it
is not a service. Single-user is a design choice: Spotify's API rules out a public
multi-tenant app, so the project leans the other way and optimizes for one person's library
instead of for scale. Audio it doesn't own is never kept — mix identification and discovery
previews both stream and discard. The one deliberate exception is acquisition, which saves a
file and links it to a track already in your library.

Acquisition is a thin client over your own slskd instance: it hosts, shares and redistributes
nothing. What you search for, what you download, and whether you have the right to it, is
entirely your responsibility. No license file is included; this is a personal tool, not a
package to depend on.
