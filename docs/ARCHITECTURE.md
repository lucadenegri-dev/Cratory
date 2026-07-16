# Architecture

Cratory is a local/self-hosted, single-user web app that turns streaming playlists
and an on-disk library into operational DJ material: set drafts, gap analysis,
discovery and a corpus of identified mixes.

## Principles

- The deterministic engine handles facts, scores, de-duplication, roles, ranking and validation.
- The AI handles language, narrative, prompt interpretation and explanations.
- **BPM and Camelot/key have two deterministic sources**: the Rekordbox XML import
  (primary) and in-app analysis via Essentia (`services/audio_analysis`,
  `integrations/essentia_engine`), the deterministic alternative. Cratory never
  estimates, invents or asks an AI for BPM/key. Every value carries an explicit
  source (`bpm_source`/`key_source`: `manual` > `rekordbox` > `cratory`): Rekordbox
  import fills empty values and reclaims `cratory` ones by default (protects
  `manual`), `?overwrite=true` wins over everything; in-app analysis writes
  `analysis_*` and reaches the canonical fields only through an explicit apply
  (auto-apply fills only the empty ones).
- **`energy` is always derived** (deterministic, from BPM+genre or computed from the
  audio file): it is not a provider datum nor a manually editable field.
- **Cratory reads audio files but never writes them.** Tags, renaming and on-disk
  organization remain Sortory's job; the textual enrichment of metadata
  (title/artist/album/label/genre) is also Sortory's.
- Spotify provides no mixing features: it serves identity, metadata, import/export.
- The remaining external providers (Last.fm, Discogs, Spotify) serve **Discovery only**,
  for taste and similarity, not the feature pipeline.
- The AI never receives the whole library: the Candidate Engine passes it at most 60 candidates.
- Every AI output goes through a Pydantic schema and the Validation Engine.
- The app is not a DJ deck (no waveform/cue/queue — that stays with the Set Builder/
  Rekordbox) and does not transcode or persist third-party audio. "The app does not play
  audio" no longer holds in absolute terms: Cratory plays its **own owned library**,
  read-only, for quick audition — see "Playback (quick audition)" below. It does not keep
  *other* audio files, with one declared exception: persistent acquisition via
  Soulseek/slskd, linked to an existing `Track`
  (`has_local_file`/`local_path`/`local_format`/`local_bitrate`). This stays distinct from the
  Shazam module, which downloads audio only temporarily for fingerprinting and
  does not keep it.
- An additional, narrowly-scoped exception: the Discovery dig plays an **ephemeral
  third-party preview** to evaluate a lead before acquiring it — a 30s iTunes clip or,
  as a fallback, the YouTube video Discogs associates with the release. Nothing is
  downloaded or kept; the audio is streamed from iTunes/YouTube and discarded. The same
  shared docked player also plays owned tracks (see below).

## Main flow

```text
Spotify / manual import
  -> Playlist Importer
  -> normalization + de-duplication
  -> SQLite
  -> Library Explorer / Gap Analysis
  -> Candidate Engine
  -> deterministic Set Builder
  -> optional AI Set Agent
  -> Validation Engine
  -> Set Editor / Export / Discovery write-back
```

In parallel, the BPM/key source:

```text
Rekordbox (user analysis)
  -> File > Export Collection in xml format
  -> POST /api/rekordbox/import
  -> path match (NFC) -> audio_hash (gated on basename) -> artist+title
  -> bpm/camelot_key filled only if absent (never overwritten)
  -> energy recomputed deterministically
```

Discovery has two parallel branches, both oriented toward **taste** (not technical
compatibility, which stays with the Set Builder). Playlist expansion:

```text
imported playlist
  -> artist/track seeds
  -> Last.fm similarity
  -> dedup vs library
  -> Spotify /search resolver
  -> taste ranking + label annotation (boost if already collected)
  -> optional AI explanation
  -> add to library
```

Crate digging (Scava), an alternative source via Discogs (no Last.fm/Spotify):

```text
seed: genre or label
  -> Discogs pile sorted by demand (want desc); `depth` picks WHERE in the pile
     to fetch a 3-page window (0.0 = the seed's classics, 1.0 = bottom of the crate)
  -> unowned leads, dedup vs library + variant dedup
  -> taste-only ranking inside the window (familiarity + label + style), per-artist cap
  -> add to library
```

Gap Analysis stays a deterministic read of a playlist's gaps, but the old Discovery
section that suggested tracks starting from gaps has been removed.

Mix identification:

```text
SoundCloud/Mixcloud/YouTube URL
  -> yt-dlp temporary download
  -> ffmpeg audio segments
  -> Shazam recognizer
  -> dedup consecutive matches
  -> DjSet + DjSetTrack
```

Tracks identified in mixes do not enter the main library: they stay a separate corpus
for future analysis and suggestions. This is the only fingerprinting Cratory
performs: it identifies the tracks of an external mix via Shazam, not the library's tracks.

File acquisition via Soulseek (slskd), distinct from the temporary Shazam download:

```text
Track in library (streaming identity)
  -> SlskdClient.search (slskd REST)
  -> deterministic selection (quality + name match + availability)
     | free search -> manual selection (/api/downloads/search + /manual)
  -> auto-pick (playlist block) | mini-selector (Discovery)
  -> slskd enqueue + transfer polling
  -> attach_local_file: has_local_file + local_path/format/bitrate
```

It is deterministic (zero AI), single-job (one download at a time) and best-effort: an
error on one track does not stop the job. It requires slskd configured; without it, the
endpoints respond `409`. The file stays linked to the `Track` as a local reference,
it is not re-uploaded or redistributed by the app.

Beyond auto-pick, `POST /api/downloads/search` offers free search on slskd with
manual selection of the candidate (`POST /api/downloads/manual`). Outcomes to review
(`needs_review|not_found|failed`) stay in a "to fix" queue, persisted on
`Track.last_download_outcome`/`last_download_reason` so they survive jobs and
restarts (`GET /api/downloads/pending`, `DELETE /api/downloads/pending/{track_id}`,
`POST /api/downloads/retry-pending`). A file already on disk can also be
linked manually from the track detail (`POST /api/tracks/{track_id}/link-file`,
search by name in `LIBRARY_ROOT` and in the slskd download folder via
`GET /api/files/search`), with the same `attach_local_file`/`audio_hash`
as acquisition.

## Disk-first

The library is the disk: a track's ownership (`has_local_file`) is not a
side-effect of Soulseek acquisition alone, but the state of a canonical
folder that Cratory actively indexes. **Cratory reads audio files but never
mutates them** — tags, renaming and organization remain Sortory's exclusive job.

- **`LIBRARY_ROOT`**: the organized folder (managed by Sortory) that Cratory
  indexes from Settings -> "Library (disk)". Empty = indexing disabled.
  Indexing also starts automatically at every app startup (background job,
  if `LIBRARY_ROOT` is configured), as well as on-demand.
- **`ARCHIVE_ROOT`**: the archive of discarded tracks (DJPlayer PASSED), scanned
  together with the library. A match in the archive marks the Track `archived=True` and
  removes ownership, without creating new tracks; ownership in the Library always
  wins over the discard and re-enables the track.
- **`audio_hash`**: SHA-256 of the first seconds of audio decoded via ffmpeg (mono,
  22050 Hz, s16le) — stable across rename and retag, unlike path or ID3/MP4 tags.
  Computed both by library indexing and by Soulseek acquisition
  (`attach_local_file`) and by the fallback match of the Rekordbox import, so the
  paths converge on the same identifier.
- **`library_index`** (`backend/app/services/library_index.py`, deterministic):
  for each file under `LIBRARY_ROOT` it computes the hash and looks for a match in the order
  `audio_hash -> legacy digest (historical local imports, in platform_track_id) ->
  ISRC -> exact fuzzy artist+title -> normalized fuzzy`; if it finds nothing it creates
  a new `Track`. The **normalized fuzzy** match hooks titles with different suffixes
  but the same track (stripping `feat./ft.`, `(Original Mix)`, `- ... Remix`, diacritics and
  punctuation) by comparing normalized artist+title, but **only on leads without a
  file** and with a **duration guard** (±7s): it does not steal the file from an owned track
  nor merge a track with its remix of a different duration. The file's
  tags fill only the empty identity fields, read-only (never overwrite
  BPM/key or manual corrections; Cratory never writes to the file). `label` too
  (ID3 `TPUB` / Vorbis `LABEL`) is read from the file and filled only if absent.
  The scan **always ignores hidden folders and files** (name starting with `.`, e.g.
  `.quarantine`, `.DS_Store`, `.git`): they are not library content, neither for the
  count nor for indexing. Incremental scan: a file with unchanged path+mtime+size
  is not re-hashed. Reconciliation: an ownership whose file the scan
  **did not see** — deleted, moved outside `LIBRARY_ROOT`, or
  ended up in a hidden folder (e.g. `.quarantine`) — is unlinked
  (`has_local_file=False`, `local_path` cleared) but keeps `audio_hash`, so the
  re-link is immediate if the file reappears (even for an existing Spotify lead via
  ISRC or artist+title). If the unlinked track is not in any playlist nor in a saved
  set it is **deleted** (no ghost leads, `orphans_removed` counter);
  otherwise it stays as a lead without a file (`lost` counter). Anti-unmount guard: a
  zero-file scan (empty root, wrong path, unmounted disk) does not touch existing
  ownerships. `duplicates` counts files with the same hash seen in the same run (the
  first wins; on-disk dedup remains Sortory's job). Exposed via
  `POST /api/library/index` (202, async job) and `GET /api/library/index/status`;
  responds `409` if `LIBRARY_ROOT` is not configured.
- **Cover art:** the owned track's artwork is served on-demand from the file
  (`GET /api/tracks/{id}/cover`, embedded artwork read on the fly, not saved in DB;
  covers FLAC/OGG, ID3 APIC, MP4 `covr`). The Spotify cover (`album_art_url`) takes
  precedence when present; the frontend falls back to the endpoint only for owned tracks
  without a streaming cover.
- **Playback (quick audition):** an owned track's audio is streamed read-only, on-demand,
  via `GET /api/tracks/{id}/audio` (`FileResponse`, HTTP Range/seek supported, `404` if not
  found/owned/allowed/present — see `docs/API.md`). Same path-safety guard as the rest of
  disk-first: the resolved path must sit inside `search_roots()` (`LIBRARY_ROOT` + the slskd
  download dir), checked via `path_within_roots`. Frontend: a single shared docked player
  (one track at a time, no queue) generalized from the Discovery preview player, so it plays
  either a third-party Discovery preview or an owned local track; `TrackPlayButton` is the
  reusable play control on track rows, mounted app-wide. No transcoding (unsupported
  browser formats just fail to play) and no DJ-deck features (waveform/cue/queue stay with
  the Set Builder/Rekordbox).
- **Orphan leads and cleanup.** An "orphan lead" is a track without a file on disk that
  belongs to no playlist nor a saved set: it has no more reason to
  exist. They are removed in two places, with the shared helper `delete_orphan_leads`
  / `unreferenced_track_ids` (in `repositories.py`): when a **playlist is deleted**
  (`DELETE /api/playlists/{id}` returns `{deleted_tracks}`) and during **index
  reconciliation** (see above). For a one-off alignment of the DB
  to the disk-first paradigm there is `backend/app/tools/cleanup_disk_first.py` (dry-run by
  default, `--apply` to write), which relies on
  `backend/app/services/db_hygiene.py`: it merges same-file duplicates, deletes orphan
  leads, clears the residual legacy fields on leads (`genre`/`bpm`/`camelot_key`/`energy`,
  with no writer in the current flow) and **re-reads owned tracks from disk**, making it
  authoritative on disk-derivable
  fields (never touches BPM/key from Rekordbox nor the Spotify cover; read-only
  access to the files).
- **Merging duplicates (same track in two rows).** The helper `merge_tracks(keep, drop)`
  (in `repositories.py`) moves playlist/set membership onto `keep`, fills its
  empty fields from `drop` (keep stays authoritative on what it already has) and deletes `drop`.
  Used in two places: the **manual linking of a file** (`attach_local_file`)
  merges a track that already owns that same file (same `audio_hash`/
  `local_path`), so two rows do not remain; and the **dedup by `audio_hash`**
  (`dedupe_by_audio_hash` in `db_hygiene`, an operation of the
  `cleanup_disk_first` script) merges rows that share the same file, keeping the one
  with streaming identity (`spotify_id`/`isrc`). With these and the normalized fuzzy match
  the manual match should rarely be necessary.
- Ownership also feeds the Set Builder: `SetGenerationRequest.owned_only` (default
  `True`) filters the Candidate Engine's candidates to only tracks with a local file;
  the choice is persisted on `Setlist.owned_only` and respected by the editor too
  (alternatives, track replacement — 422 if the replacement is not owned and the set
  was born "owned only").

## BPM/key sources: Rekordbox import + in-app analysis

Cratory does not estimate or invent BPM/key, and never asks an AI for them: the two
deterministic sources are the Rekordbox XML export (primary) and an in-app Essentia
analysis (alternative, for tracks the user has not yet analyzed in Rekordbox). Every
value on `Track` carries an explicit provenance, `bpm_source`/`key_source` (`manual`
> `rekordbox` > `cratory`), so the two sources and manual corrections never silently
clobber each other. Beatgrid, cue and other Rekordbox fields stay out of scope.

### Rekordbox import

- **`POST /api/rekordbox/import`** (multipart, field `file`): parses the XML
  (`defusedxml`, anti-XXE) and for each `TRACK` looks for the matching owned
  `Track` in the order: **NFC-normalized path** (macOS/Rekordbox can
  decode `Location` in NFD) -> fallback **`audio_hash`**, gated on the
  path basename to avoid an expensive ffmpeg decode on rows not ours ->
  **fuzzy artist+title**. On a match, it is **source-aware**: by default it fills
  empty `bpm`/`camelot_key` and reclaims values currently sourced from the in-app
  analysis (`cratory`), but protects `manual` corrections; `?overwrite=true` wins
  over every existing value regardless of source (a value absent in the XML never
  clears the one already in the library). Every write is marked `bpm_source`/
  `key_source = "rekordbox"`. It recomputes `energy` deterministically when the BPM
  is set, and updates the track state. Responds with the counts (`in_file`,
  `matched`, `unmatched`, `bpm_set`, `key_set`, `energy_set`). `400` on an empty file
  or invalid/unsafe XML. Implementation: `backend/app/services/rekordbox_import.py`
  (pure parser + `apply_collection`), router `backend/app/routers/rekordbox.py`.
- **`GET /api/rekordbox/pending`**: counts the owned tracks (`has_local_file`)
  still without BPM or without key — the number the user still has to "analyze in
  Rekordbox and import". Also exposed in `GET /api/pipeline` as
  `analyze_pending`.

### In-app analysis (Essentia)

The Analysis page (`/analysis`) offers a deterministic alternative to Rekordbox for
owned tracks: local BPM/key extraction via Essentia, without leaving Cratory.

- **`integrations/essentia_engine.py`**: thin, lazily-imported adapter (the app
  starts and runs fine without the dependency installed; `is_available()` gates the
  router's `503`). `analyze(path)` decodes the file (`MonoLoader`), runs
  `RhythmExtractor2013` (method `multifeature`) for BPM and `KeyExtractor` (profile
  `edma`, tuned for electronic music) for key, converting the result to the
  project's canonical Camelot notation. Pinned to `essentia==2.1b6.dev1389`
  (AGPL-3.0) — see `docs/DEPENDENCIES.md`. `analyze_subprocess(path)` runs the same
  analysis in a short-lived child process (`essentia_worker.py`): Essentia is C++
  and holds the GIL for seconds per real track, so running it in the job thread of
  the single-worker server would freeze every concurrent request — the subprocess
  isolates that CPU-bound work (same rationale as ffmpeg in the library index), and
  the job calls this variant, not `analyze`.
- **`services/audio_analysis.py`**: the only bridge from `analysis_*` to the
  canonical `bpm`/`camelot_key`. `diverges(track)` flags a mismatch (BPM compared
  at 1-decimal precision, key exact match). `apply_analysis` copies the analyzed
  values unconditionally (source becomes `cratory`); `auto_apply_missing` copies
  only into empty canonical fields (no conflict possible, used by the job). Also
  recomputes `energy` and refreshes track status on any write.
- **`services/audio_analysis_job.py`**: background job (same in-memory
  single-job-with-lock pattern as `library_index_job`). Selects owned tracks with a
  local file (`scope="missing"` = without BPM or key, `scope="all"` or explicit
  `track_ids` = every candidate), analyzes each with `essentia_engine.analyze_subprocess`,
  writes `analysis_bpm`/`analysis_camelot`/`analyzed_at` (or `analysis_error` on a
  decode failure, without stopping the batch), then calls `auto_apply_missing`.
  Commits per track so progress survives an interruption.
- **`routers/analysis.py`** (`/api/analysis/*`): `overview` (coverage by source),
  `start` (202, `503` if Essentia missing, `409` if already running), `status`,
  `divergences` (canonical vs analyzed, with Camelot-wheel compatibility), `apply`
  (writes the selection into the canonical fields; `mode="all"` requires
  `force=true`). Full contract in `docs/API.md`.

## Backend layers

```text
backend/app/
  routers/        FastAPI endpoints, HTTP only and error mapping
  services/       deterministic application logic and orchestration
  repositories.py SQLAlchemy queries and DB mutations
  models.py       SQLAlchemy models
  db.py           session/engine, ensure_schema and idempotent migrations
  schemas.py      Pydantic request/response
  serializers.py  ORM -> Pydantic, derived fields
  integrations/   external clients behind interfaces
  core/           config, logging
  tools/          maintenance scripts (e.g. clean_user_data, cleanup_disk_first)
```

Routers must contain no business logic. External integrations must be
injectable or isolatable, so tests can use fake clients without a network.

## Deterministic engine

Responsibilities:

- playlist import and manual import;
- de-duplication with priority `ISRC -> platform_track_id -> artist+title+duration -> fuzzy`;
- Rekordbox import (BPM/key, source-aware overwrite) and in-app Essentia analysis
  (BPM/key alternative, apply bridge), and recomputation of derived `energy`;
- track state (`imported`, `ready_for_set`);
- BPM, Camelot, energy, genre and duration scores (the contract also includes a mood
  coherence score, today always neutral: `Track` no longer has a mood field since
  the enrichment engine was retired). Genre similarity uses a deterministic
  map of families (techno/house/breaks/chill/...): subgenres of the same
  family are coherent even without a common token, super-genres ("Electronic")
  are neutral, different families count as a break. In the set generator genre
  coherence is a dedicated ranking term (like the energy arc), modulated per
  strategy (`StrategyProfile.genre_coherence`: exploratory strategies reduce it);
- transition classification;
- role assignment across the set arc;
- candidate filtering with a cap of 60;
- gap analysis;
- discovery ranking;
- AI output validation.

The absence of BPM/key does not block the system: the track stays `imported` (not
usable by the Set Builder until they arrive from a Rekordbox import) and partial
scores use neutral values where possible.

## AI

The AI can:

- interpret free prompts;
- propose a narrative direction;
- explain choices and transitions;
- suggest creative alternatives;
- comment on Discovery candidates.

The AI cannot:

- invent track_id;
- invent BPM/key/ISRC/sources;
- select tracks outside the candidates it received;
- bypass the Validation Engine;
- touch BPM/key/energy.

Set Builder modes:

- `technical`: cautious, based on the data provided.
- `creative`: also uses general musical knowledge, but stays bound to candidates and validation.

## Internationalization (i18n IT/EN)

Cratory is bilingual Italian/English. The language is a persistent setting
(key `language` in `AppState`, default `it`), chosen by a toggle in Settings;
no per-locale routing (single-user app, no SEO). Endpoint `GET/PUT
/api/settings/language`.

Three surfaces, three strategies:

- **Frontend UI**: a home-grown TypeScript dictionary in `frontend/lib/i18n/`.
  `en.ts` is the source of truth for the keys; `it.ts` is typed `: Dictionary`
  (`= typeof en`), so a missing or extra key is a compile error.
  `I18nProvider`/`useT()` expose the active dictionary; `runtime.ts` keeps the
  language state accessible outside React (used by `lib/api.ts`) without import cycles.
- **Backend errors**: language-agnostic. Every `HTTPException` goes through
  `api_error(status, code, message, **params)` (`app/core/http_errors.py`) with a structured
  `detail` `{code, message, params?}`; the frontend translates the `code` from the
  `errors` namespace of the dictionary (`translateApiError`), with the English `message` as fallback.
- **Generated phrases + AI output**: produced by the backend directly in the selected
  language. Enum labels (e.g. transition classification) stay codes
  translated by the frontend; composed phrases (reason/mixing tip/overview in
  `services/scoring.py`, job phases, AI agent texts in `services/ai_agent.py`)
  come from per-language catalogs indexed by `get_language(db)` at the entry point.
  The AI system prompts stay in Italian as instructions to the model: only the
  directive on the output language is parametric.

Known limitation: the `transition_reason` values persisted in the DB at set generation
time stay in the language active at that moment (the future display language is not
known at generation time).

## Data model

Main entities:

- `Playlist`: playlist imported from Spotify or manual import.
- `Track`: library track, with streaming identity, editorial metadata,
  BPM/Camelot (from Rekordbox import or in-app Essentia analysis), derived
  `energy` and state. Provenance of BPM/key: `bpm_source`/`key_source`
  (`manual`/`rekordbox`/`cratory`, null if the value itself is null), hierarchy
  `manual` > `rekordbox` > `cratory` (see "BPM/key sources"). In-app analysis
  staging fields, written only by the analysis job and never read by the rest of
  the app: `analysis_bpm`, `analysis_camelot`, `analyzed_at`, `analysis_error`
  (reach the canonical fields only via the apply step). Local file
  ownership (`LIBRARY_ROOT` indexing, Soulseek acquisition or manual
  link-file): `has_local_file`, `local_path`, `local_format`,
  `local_bitrate`, `audio_hash` (see "Disk-first"). Other fields: `archived` (file
  ended up in the archive of discarded tracks), `local_mtime`/`local_size` (incremental
  scan), `last_download_outcome`/`last_download_reason` (download "to
  fix" queue).
- `playlist_tracks`: M2M association table (Playlist <-> Track) with `added_at`
  per-playlist. A track can belong to multiple playlists; the import adds
  membership without overwriting.
- `Setlist`: generated set, prompt, strategy, global explanation, validation and
  `owned_only` ("owned only" guarantee, see "Disk-first").
- `SetlistTrack`: position, role, score, transition notes, AI reason and risk.
- `SpotifyToken`: Spotify OAuth tokens persisted for the local user.
- `DjSet`: external mix identified via Shazam, separate from the library.
- `DjSetTrack`: track identified within a `DjSet`.
- `AppState`: persistent key-value for application state (e.g. `last_index_at`).

Legacy Rekordbox fields such as beatgrid, cue, `rekordbox_track_id`, `play_count` and
`tonality` are out of the model. There is no longer an internal enrichment engine nor
an audio provider cache: `energy` is a derived field (`services/energy`), not
an external cacheable datum. Also removed were the last remnants
of the legacy enrichment (the `LastFmTagProvider`, `MusicFeatureProvider` providers) and the
unused `Track.release_date` column (dropped with an FK-safe migration). The
pre-M2M columns `Track.playlist_id`/`playlist_name` remain in the schema — they are not
droppable on SQLite due to a baked-in FK on `playlist_id` — but are dead and empty
(membership lives on `playlist_tracks`).

## Integrations

| Integration | State | Notes |
|---|---|---|
| Spotify | active | OAuth, import, Discovery resolver, playlist export |
| Last.fm | active | artist/track similarity for Discovery (playlist expansion) |
| Discogs | active | Discovery "Scava" crate digging by genre/label; works without a token, `DISCOGS_TOKEN` raises the rate limit |
| LLM | active if configured | structured and validated outputs |
| Shazam | active if dependencies present | ffmpeg, yt-dlp, shazamio; fingerprinting of external mixes, not of the library |
| slskd (Soulseek) | active if configured | download via REST API; `SLSKD_URL`/`SLSKD_API_KEY`/`SLSKD_DOWNLOAD_DIR` |
| Rekordbox | manual (via XML export) | BPM/key source: `POST /api/rekordbox/import`; no external API/dependency, only file parsing |
| Essentia (`integrations/essentia_engine`) | active if installed | in-app deterministic BPM/key analysis for owned tracks (`/api/analysis/*`); lazy import (app runs without it, `is_available()` gates the `503`), pinned `essentia==2.1b6.dev1389` (cp311 macosx-arm64 wheel), AGPL-3.0 (ok for personal self-hosted use, no redistribution) |
| SoundCloud | active if dependencies present | yt-dlp (metadata only, never audio) for playlists/secret links and likes: flat like preview (fast), import/sync with full per-track extraction (uploader/duration/artwork, ~1s per track); no ISRC (not exposed), dedup on `platform_track_id`; sync always additive (never prune, unlike Spotify) |
| PostgreSQL | backlog | SQLite is enough for single-user |

The remaining external providers (Last.fm, Discogs, Spotify) serve **Discovery
only**: none of them provides BPM/key/mood/energy anymore. The textual
enrichment of metadata (title/artist/album/label/genre) is Sortory's
job, not Cratory's. Spotify `/recommendations` must not be used: for
new apps or in development mode it can return 403/404.

## Persistence and migrations

SQLite remains the operational database:

```text
backend/data/djassistant.db
```

`ensure_schema()` creates tables and applies idempotent migrations (including the
FK-safe ones that dropped the columns of the old enrichment engine). There is no
Alembic. For a product rename, do not automatically rename the DB: plan
a migration or keep the legacy path for compatibility.
