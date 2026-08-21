# Architecture

Cratory is a local, single-user web app that turns streaming playlists and a folder of
audio files into operational DJ material: set drafts, gap analysis, crate digging, an
organized library on disk, and a corpus of identified mixes.

This document describes how the system is put together. `docs/API.md` has the endpoint
contracts; `docs/DEPENDENCIES.md` has the packages and external services.

## Principles

**The deterministic engine decides, the model explains.** Import, normalization,
de-duplication, scoring, roles, sequencing, gap analysis, discovery ranking and validation
are ordinary Python. The LLM interprets a free-text prompt, judges mood-fit, suggests
anchors and writes prose. It never sequences a tracklist.

**The AI never sees the whole library.** The curation stage works on a pool capped at 200
candidates (`POOL_CAP`), and no single LLM call sees more than 60 of them (`PER_CALL_CAP`);
mood-fit runs in batches of 50. Every response is parsed into a Pydantic schema and
checked: ids outside the batch that was sent, and values outside declared bounds, are
dropped with a warning. A failed AI call degrades to the deterministic default with a
warning on the setlist — never to an error.

**BPM and key are measured, never guessed.** Two deterministic sources: the Rekordbox XML
export (primary) and in-app Essentia analysis (the alternative for tracks not yet analyzed
in Rekordbox). Every value carries its provenance in `bpm_source`/`key_source` —
`manual` > `rekordbox` > `cratory` — so the two sources and manual corrections never
silently clobber each other. Cratory never asks an LLM or a streaming provider for BPM or
key. Beatgrid and cue points are out of scope; there is no live Rekordbox integration.

**`energy` is derived, never supplied.** Either estimated from BPM + genre
(`services/energy.py`) or computed from the audio itself (`services/audio_energy.py`:
RMS, spectral centroid, spectral flux, calibrated by percentile against the user's own
library). `energy_source` says which. It is not a provider field and not hand-editable.

**The library is the disk.** Ownership (`has_local_file`) is the state of a folder that
Cratory indexes, not a side effect of any single acquisition path. A streaming playlist is
a list of leads.

**Cratory reads audio files; only Organize writes them.** Tag editing, renaming and on-disk
layout belong to `/organize`, which is the single writer. Everything else — indexing,
cover extraction, playback, hashing, analysis — opens files read-only.

**Streaming provides identity, not mixing data.** Spotify and SoundCloud supply title,
artist, album, cover, duration, ISRC, URLs and playlist membership. The remaining external
providers (Discogs, Bandcamp, iTunes) serve Discovery; Discogs is also queried by
Organize, through its own separate client, for text-metadata proposals. Spotify
`/recommendations` must
not be used: for new apps, or an app in development mode, it returns 403/404.

**Third-party audio is streamed, not kept.** Mix identification downloads temporarily and
deletes; Discovery previews stream from the provider and are discarded. Two deliberate
exceptions save a file and link it to a track already in the library: Soulseek acquisition
and the per-track SoundCloud download. Cratory is not a DJ deck — no waveform, no cue, no
queue — but it does play the files you own, read-only, through one shared docked player.

## Backend layers

```text
backend/app/
  main.py            FastAPI app: lifespan (ensure_schema, runtime settings, startup
                     library scan), CORS, request logging, router mounting
  db.py              engine/session, ensure_schema + idempotent migrations
  models.py          SQLAlchemy models (core)
  schemas.py         Pydantic request/response
  serializers.py     ORM -> Pydantic, derived fields
  repositories.py    queries and DB mutations, incl. the effective-tag COALESCE

  core/
    config.py            pydantic-settings Settings + logging setup
    runtime_settings.py  Settings-UI overrides over the .env defaults — plain
                         fields (ENV_BACKED_KEYS: paths, URLs, ai_model) and
                         credentials (SECRET_KEYS) alike, cached in memory so
                         every integration reads a live value with no restart
    http_errors.py       api_error(): structured {code, message, params} details

  routers/           mostly HTTP only — a few carry real logic (best-transition
                     ranking in transitions.py, ISRC/artist+title matching in
                     dj_sets.py, one export-format rule per branch in sets.py
                     and playlists.py); see CLAUDE.md's stack-and-layout list
    tracks.py (/api: tracks, library/index, stats, genres)  playlists.py
    sets.py  transitions.py  labels.py  analysis.py  rekordbox.py
    discovery.py  dj_sets.py (/api/shazam)  downloads.py  files.py
    slskd.py  soundcloud.py  spotify.py  ai.py  pipeline.py  services.py
    settings.py  setup.py (/api/setup, the guided wizard)

  services/          deterministic logic and orchestration
    import        playlist_import  manual_import  local_import  streaming_import_job
    identity      library_index  auto_link  file_search  genre_align  genre_norm
                  track_status  camelot
    bpm/key       rekordbox_import  audio_analysis  audio_analysis_job
    scoring       scoring  energy  audio_energy  candidate_engine
    set building  set_skeleton  set_generator  set_editor  alternatives
                  ai_curation  export_render
    discovery     discovery_dig  dig_sources/{__init__,discogs,bandcamp}  preview
    acquisition   acquisition  soulseek_select  download_queue  download_dispatcher
                  download_runner  download_review  slskd_shares
    mixes         mix_identify  mix_identify_job
    setup         system_probe  binary_manifest  binary_installer  slskd_daemon
                  credential_tests
    misc          gap_analysis  labels  pipeline  rating  app_state
                  track_label  job_spawn  native_picker

  integrations/      external clients behind injectable interfaces
    spotify  soundcloud  soundcloud_audio  discogs  bandcamp  itunes
    slskd  shazam  llm  essentia_engine  essentia_worker  local_files  _http

  tools/             maintenance scripts
    clean_user_data  merge_duplicate_tracks

  organize/          the /organize section, its own namespace under /api/organize/*
    models.py        ScanRoot, AudioFile, Issue, DupGroup, DupMember, Settings,
                     Plan, PlanOp, UndoJournal
    schemas.py       Pydantic schemas for the section
    core/            http_errors.py
    routers/         scan  analyze  issues  duplicates  plan  apply  history
                     library  files  fingerprint  genre_review  settings
    services/        scanner  scan_job  inspector  dedup  planner  planning
                     conflict  apply  apply_job  undo  manual_edit  file_link
                     roots  analysis  covers  cover_cache  thumbs  ratings
                     fingerprint  integrity  integrity_job  match_distance
                     genre_review  genre_review_job  provider_rescan
                     provider_rescan_job  text_providers  ai_tags
    integrations/    tagio  fsops  acoustid  musicbrainz  discogs_meta
                     cover_art  content_hash  integrity  _http
```

Not every integration takes an injectable client — 4 of the 12 modules in
`app/integrations/` do:

```
$ grep -n 'http: httpx.Client | None = None' backend/app/integrations/*.py
bandcamp.py:41
discogs.py:46
itunes.py:25
slskd.py:55
$ grep -n '= httpx.Client(\|anthropic.Anthropic(\|_OneShotHTTPClient()' backend/app/integrations/*.py
llm.py:81            self.client = anthropic.Anthropic(...)
shazam.py:155        self._shazam = Shazam(http_client=_OneShotHTTPClient())
spotify.py:100       self.http = httpx.Client(timeout=20)
```

The other 8 build their own client (`spotify.py:98-100`, `llm.py:68,81`, `shazam.py:155`)
or have no HTTP/process client to inject at all (`soundcloud.py`, `soundcloud_audio.py`,
`essentia_engine.py`, `essentia_worker.py`, `local_files.py` expose no client class). Their
tests still avoid the network, but by other means per module — e.g.
`monkeypatch.setattr(client, "http", ...)` after construction for `spotify.py`, a scripted
implementation of the `LLMClient` interface for `llm.py`, `monkeypatch.setattr("shazamio.Shazam", ...)`
for `shazam.py` — not a constructor parameter. Routers mostly map HTTP to a service call and
exceptions to status codes through `api_error`, but not as a hard rule — see the `routers/`
list above for the named exceptions.

`app/organize` imports from the core (`app.models.Track`, `app.core`, `app.services.genre_align`);
the core never imports from `app.organize`. The one relationship that spans the boundary,
`AudioFile.track`, is declared on the Organize side with a backref, so `app/models.py` stays
independent. `ensure_schema()` pulls in the Organize models with a deferred import.

Background jobs follow one pattern: a module-level lock, in-memory status, and a daemon
thread. Most spawn that thread with a bare `threading.Thread`; only the two single-user
jobs (BPM/key analysis, streaming import/sync) go through `services/job_spawn.spawn`, a
thin wrapper tests monkeypatch to run synchronously. Each job is single-instance, but the
guard on a second start splits into two families, and `docs/API.md`'s jobs table doesn't
say which is which (it only carries the start endpoint's success code):
analysis (`analysis_already_running`), streaming import/sync
(`streaming_import_already_running`) and set generation
(`set_generation_in_progress`) reject a second start with `409`, checked in the router
before `start_job` runs (e.g. `routers/analysis.py:59-60`); library scan/index, organize
apply, mix identification, provider rescan, integrity check and AI genre review instead
let `start_job` notice the module-level lock is held and hand back the *current* running
job's state with no error (`if _state["status"] == "running": return dict(_state)`,
e.g. `organize/services/scan_job.py:112-113`) — a second `POST` is harmless, just not an
error. CPU-bound work that would hold the GIL — ffmpeg decoding, Essentia analysis — runs
in a subprocess.

Soulseek/SoundCloud download does not fit either family any more: it moved from a
single-instance job to a persistent queue (see "Acquisition" below) with an N-wide
worker pool, so there is no "already running" to reject — every start endpoint enqueues
and answers `200`.

## The library is the disk

A track is *owned* when a file for it exists under `LIBRARY_ROOT`. Ownership survives
renames, moves and retagging because identity is anchored to the audio, not the path.

- **`LIBRARY_ROOT`** — the organized folder, set in Settings → "Library (disk)". Empty
  disables indexing (`409`).
- **`SLSKD_DOWNLOAD_DIR`** — the inbox, walked by the same scan. A file here is an
  `AudioFile` with `location = "inbox"`; a file under `LIBRARY_ROOT` is `location =
  "library"`. There is no third case.
- **`ARCHIVE_ROOT`** — the archive of discarded tracks, scanned alongside the library. A
  match there sets `archived=True` and drops ownership, without creating tracks; ownership
  in the library always wins and re-enables the track. Archive files matching no track are
  remembered in `archive_seen` (path, mtime, size) so they are not re-hashed every run.
- **`audio_hash`** — SHA-256 of the first seconds of the decoded audio stream (ffmpeg, mono,
  22050 Hz, s16le). Stable across rename and retag, unlike a path or an ID3 tag. Computed by
  library indexing, by acquisition (`attach_local_file`) and by the Rekordbox import's
  fallback match, so all three paths converge on the same identifier.

### One scan, two doors

There is a single scan job, `organize/services/scan_job.py`, reachable two ways:
`POST /api/organize/scan` (optionally scoped with `locations: ["inbox"|"library"]`) and
`POST /api/library/index`, its whole-library alias kept for the frontend's "Index" button.
Each has its own start status code and its own `/status` route — see the jobs table in
`docs/API.md` rather than assuming a convention here. It also runs once at
startup, through `start_job_if_due()`, which skips if the last run finished less than 15
minutes ago — otherwise every uvicorn reload would re-index in development.

The scan and Organize's apply are mutually exclusive: each returns `409` while the other is
running. A scan during an apply would walk a half-moved tree, and reconciliation could then
merge a file 1:1 across the inbox/library boundary.

**Phase 1** (`organize/services/scanner.py`) walks the roots, reads tags and upserts
`AudioFile` rows. **Phase 2** (`_aggancia_le_tracce`, delegating to
`services/library_index.py`) attaches tracks to the files phase 1 just wrote —
`collega_tracce`, `indicizza_archivio`, `riconcilia_possessi`, plus the energy recompute. The
import is deferred inside the function, because `library_index.py` already imports from
`app/organize` and a module-level import would close the cycle.

For each file, phase 2 computes the hash and looks for a track to attach it to, in order:
`audio_hash` → legacy digest (historical local imports, stored in `platform_track_id`) →
ISRC → exact fuzzy artist+title → normalized fuzzy. Nothing matched means a new `Track`.

The **normalized fuzzy** step catches the same track under a different suffix — it strips
`feat./ft.`, `(Original Mix)`, `- … Remix`, diacritics and punctuation before comparing —
but only against **leads without a file**, and only within a **±7s duration guard**. It
therefore cannot steal a file from an owned track, nor merge a track with a remix of a
different length.

Tags from the file fill empty identity fields only. They never overwrite BPM, key or a
manual correction, and nothing is ever written back. `label` (ID3 `TPUB` / Vorbis `LABEL`)
follows the same fill-if-empty rule.

Hidden folders and files (leading `.` — `.quarantine`, `.DS_Store`, `.git`) are always
skipped, for the count as well as for indexing. The scan is incremental: unchanged
path+mtime+size means no re-hash.

**Reconciliation.** An ownership whose file the scan did not see — deleted, moved out of the
root, or moved into a hidden folder such as `.quarantine` — is unlinked (`has_local_file=False`,
`local_path` cleared) but keeps its `audio_hash`, so re-linking is instant if the file
reappears. If the unlinked track belongs to no playlist and no saved set it is deleted
outright (`orphans_removed`); otherwise it survives as a lead (`lost`). A scan that sees
**zero** files — unmounted disk, wrong path — touches no existing ownership. `duplicates`
counts same-hash files seen in one run; the first wins, and on-disk de-duplication is
Organize's job.

### Effective tags

For an owned track, the authoritative text tag is the one in the file, not the one imported
from streaming. `repositories._EFFECTIVE_TAGS` resolves `genre`, `album`, `label` and `year`
at query time as `COALESCE(audio_file.field, track.field)` over the join on
`tracks.primary_file_id`. Edit a tag in Organize and every read reflects it, with no
re-indexing.

`genre` is the one field also mirrored onto `tracks.genre`, as a convenience for code paths
that hold a `Track` and no pool-wide map. One shared rule maintains the mirror —
`services/genre_align.align_track_genre` — called from exactly five sites: Organize's manual
tag edit, Organize's scan (tag changed outside the app), Organize's apply (a RETAG touching
genre), library indexing (a lead acquiring a file), and acquisition (`attach_local_file`,
where the `AudioFile` row is inserted rather than updated, so the scan's changed-tag guard
never fires). Writing the mirror also recomputes the derived `energy`, since it depends on
BPM + genre — a set's energy arc can visibly shift after a genre edit. The COALESCE read
path stays authoritative regardless of the mirror's state; the rule compares after light
normalization (case, dashes, underscores), so the mirror may lag the literal text without
any endpoint ever returning a wrong value.

`artist` and `title` never follow the file: they are the streaming identity used for
de-duplication and matching.

### Serving files

- **Cover art** — `GET /api/tracks/{id}/cover` reads embedded artwork on the fly (FLAC/OGG
  pictures, ID3 `APIC`, MP4 `covr`); nothing is cached in the DB. A Spotify
  `album_art_url` takes precedence when present, and the frontend falls back to the endpoint
  only for owned tracks without one.
- **Playback** — `GET /api/tracks/{id}/audio` streams the local file with `FileResponse`
  (HTTP Range/seek supported). The resolved path must sit inside `search_roots()`
  (`LIBRARY_ROOT` plus the slskd download folder), checked by `path_within_roots`; anything
  else is a `404`. No transcoding: a format the browser cannot decode simply does not play.
  The frontend mounts one shared docked player app-wide — one track at a time, no queue —
  which also plays Discovery previews; `TrackPlayButton` is the reusable play control on
  track rows.

### Housekeeping helpers

Both live in `repositories.py` and are shared by several call sites:

- `delete_orphan_leads` / `unreferenced_track_ids` — a lead with no file, no playlist and no
  saved set has no reason to exist. Removed when a playlist is deleted
  (`DELETE /api/playlists/{id}` returns `{deleted_tracks}`) and during index reconciliation.
- `merge_tracks(keep, drop)` — moves playlist and set membership onto `keep`, fills its empty
  fields from `drop`, deletes `drop`. Used by manual file linking, which merges a track that
  already owns the same file (same `audio_hash`/`local_path`) instead of leaving two rows.

## Import and de-duplication

```text
Spotify / SoundCloud / pasted text
  -> playlist_import: normalization
  -> de-duplication: ISRC -> platform_track_id -> artist+title+duration -> fuzzy
  -> Track (status: imported)
  -> BPM + key arrive -> status: ready_for_set
```

A track can belong to several playlists: membership lives on the `playlist_tracks`
association table with a per-playlist `added_at`, and an import adds membership without
overwriting. Each import or sync records its diff in `PlaylistSyncEvent` as a textual
snapshot (artist/title), because a removed track may itself disappear as an orphan lead.

Spotify sync prunes tracks removed upstream; SoundCloud sync is always additive, since the
SoundCloud path has no ISRC and de-duplicates on `platform_track_id` alone. Long imports run
through `services/streaming_import_job.py`.

Missing BPM/key does not block anything: the track stays `imported` — the Set Builder will
not use it — and partial scores fall back to neutral values.

## BPM and key

### Rekordbox import

`POST /api/rekordbox/import` (multipart, field `file`) parses the collection XML with
`defusedxml` and, for each `TRACK` element, looks for the owned `Track` in this order:

1. **NFC-normalized path** — macOS and Rekordbox can write `Location` in NFD.
2. **`audio_hash`**, gated on the path basename so an ffmpeg decode is not paid for rows
   that are not ours.
3. **fuzzy artist+title**.

On a match the write is source-aware: by default it fills empty `bpm`/`camelot_key` and
reclaims values currently sourced from in-app analysis (`cratory`), while protecting
`manual` corrections. `?overwrite=true` wins over any source. A value absent from the XML
never clears one already in the library. Every write stamps `bpm_source`/`key_source =
"rekordbox"`, recomputes `energy` when BPM is set, and refreshes the track status. The
response carries the counts (`in_file`, `matched`, `unmatched`, `bpm_set`, `key_set`,
`energy_set`); an empty or unsafe XML is a `400`.

`GET /api/rekordbox/pending` counts owned tracks still missing BPM or key — the backlog the
user still has to analyze in Rekordbox. The same number appears in `GET /api/pipeline` as
`analyze_pending`.

Implementation: `services/rekordbox_import.py` (a pure parser plus `apply_collection`),
router `routers/rekordbox.py`.

### In-app analysis (Essentia)

The `/analysis` page extracts BPM and key locally, without leaving Cratory.

- **`integrations/essentia_engine.py`** — a thin, lazily-imported adapter. The app starts and
  runs fine without Essentia installed; `is_available()` gates the router's `503`.
  `analyze(path)` decodes with `MonoLoader`, runs `RhythmExtractor2013` (`multifeature`) for
  BPM and `KeyExtractor` (profile `edma`, tuned for electronic music) for key, converting to
  the project's Camelot notation. `analyze_subprocess(path)` runs the same work in a
  short-lived child process (`essentia_worker.py`): Essentia is C++ and holds the GIL for
  seconds per track, which would freeze concurrent requests on a single-worker server. The
  job calls the subprocess variant.
- **`services/audio_analysis.py`** — the only bridge from the `analysis_*` staging fields to
  the canonical ones. `diverges(track)` flags a mismatch (BPM at one decimal, key exact).
  `apply_analysis` copies unconditionally (source becomes `cratory`); `auto_apply_missing`
  copies only into empty canonical fields, so no conflict is possible. Both recompute
  `energy` and refresh the status.
- **`services/audio_analysis_job.py`** — the background job. Selects owned tracks
  (`scope="missing"` = missing BPM or key, `scope="all"` or explicit `track_ids` = every
  candidate), analyzes each, writes `analysis_bpm`/`analysis_camelot`/`analyzed_at` — or
  `analysis_error` on a decode failure, without stopping the batch — then calls
  `auto_apply_missing`. It commits per track, so progress survives an interruption.
- **`routers/analysis.py`** — `overview` (coverage by source), `start` (202; `503` without
  Essentia, `409` if already running), `status`, `divergences` (canonical vs analyzed, with
  Camelot-wheel compatibility), `apply` (`mode="all"` requires `force=true`), `dismiss`
  (marks divergences seen-and-ignored, see `services/audio_analysis.py`).

## Set building

```text
filters + prompt
  -> Candidate Engine (owned_only, sources, genre, BPM/key/energy windows)
  -> [optional] AI curation: intent compilation, mood-fit, anchor hints
  -> Phase 1  build_skeleton: anchors, peak reserve, genre arc
  -> Phase 2  beam search per segment
  -> assign_roles
  -> [optional] AI narrative: title, explanation, missing-library suggestions
  -> Setlist + SetlistTrack
```

### Deterministic scoring

`services/scoring.py` scores BPM, Camelot, energy, genre and duration. The contract also
carries a mood-coherence score, today always neutral — `Track` has no mood field. Genre
similarity uses a deterministic family map (techno / house / breaks / chill / …):
subgenres of one family are coherent even without a shared token, super-genres like
"Electronic" are neutral, different families count as a break. In the generator, genre
coherence is a ranking term of its own, modulated per strategy
(`StrategyProfile.genre_coherence` — exploratory strategies lower it).

Every genre read along this chain resolves the **effective** genre, not `Track.genre`: the
candidate engine builds a `genre_map` once per pool
(`repositories.effective_genres_for_tracks`, one query) and threads it through as a plain
argument (`scoring.genre_of`). Callers outside the Set Builder that build no pool-wide map
— `/api/transitions`, alternatives, the set editor — read the streaming `Track.genre`.

### Two-phase generation

**Phase 1, `services/set_skeleton.py`.** Elects opening / peak / closing / reset anchors
according to the strategy, reserves the top 15% of candidates by impact score (0.7 × energy
percentile + 0.3 × BPM percentile) for the peak segment alone, and plans a genre arc: the
dominant family at the peak, a calmer family elsewhere, computed on the effective genre. The
arc degenerates to no plan above an 80% dominant share, or when no second family reaches
15%. `build_skeleton` returns `None` — and the generator falls back to the older
single-phase beam search — when the pool is under 8 candidates (`_MIN_POOL_FOR_SKELETON`) or
the expected set is under 6 tracks (`_MIN_EXPECTED_TRACKS`, target duration over the median
track length).

**Phase 2, `services/set_generator.py`.** Fills each segment with a span-budgeted beam search
(`_beam_search_span`) that converges toward the incoming anchor, follows the segment's genre
plan, and penalizes spending a reserved track outside the peak window. Fully deterministic;
the external interface is identical whether or not AI curation ran.

After an edit in the workbench, roles are re-derived positionally by `assign_roles` (peak at
~70%). For strategies whose peak sits elsewhere — a descending/closing arc puts it at ~20% —
the label can drift from the anchor elected at generation time.

### AI curation (`services/ai_curation.py`)

Optional, enabled by a truthy `use_ai`. It is read-only on the pool and never sequences.
Up to four LLM calls, all under the 200/60 caps:

1. **Intent compilation** — the free prompt becomes `SetGenerationRequest` overrides, but
   only for fields the user left unset (`model_fields_set` is the discriminant;
   `owned_only` and `sources` are never compilable). The compiled `start_bpm`/`end_bpm`/
   `start_energy`/`end_energy` are set-arc preferences on the request, not per-track BPM or
   key — the "never ask an AI for BPM/key" rule is intact.
2. **Mood-fit**, in batches of 50 — a 0–100 score plus up to 3 tags per candidate.
   Candidates a batch fails to judge default to 50, so they neither win nor lose.
3. **Anchor hints** — up to 3 track ids per role (opening / peak / closing) among the
   mood-fit leaders.
4. **Narrative**, after the set is built — title, global explanation, and up to 3
   missing-library suggestions.

Mood-fit and anchor hints enter the deterministic engine as two non-binding extra terms: a
×0.30 weight in `_candidate_score` at the fill stage, and a ×0.2 weight plus a +12 bonus in
the anchor election. The AI nudges scores; it never picks a track. Failures land in
`Setlist.curation.warnings`. If every call fails or produces nothing usable, `generated_by`
stays `algorithmic`; otherwise it becomes `algorithmic+ai_curation` (sets generated before
the two-phase rework may still read `ai`).

There is a single AI axis — on or off. The curation has one character, musical, so the
mood/anchor/narrative system prompts are unique and there is no technical/creative toggle.

### Around the generator

`services/set_editor.py` and `services/alternatives.py` back the workbench: reorder, remove,
replace a track, list alternatives for a slot. A set born `owned_only` keeps the guarantee —
`Setlist.owned_only` is persisted and the editor answers `422` to a replacement that is not
owned. `POST /api/sets/{id}/export` serves four formats — `text`, `csv`, `markdown`, `m3u8`;
the M3U8 comes from `services/export_render.render_m3u8`, which lists local paths and notes
how many tracks were skipped for lack of a file. `routers/spotify.py` pushes a set back as a
Spotify playlist.

`services/gap_analysis.py` reads a playlist for structural holes (no openers, no peak,
missing BPM bridges, flat energy, harmonic dead ends). `/api/transitions` classifies a pair
of tracks on its own. `services/labels.py` aggregates the library per record label, reading
the label from the effective tag.

## Discovery

Discovery works by **taste**, not by technical compatibility — that stays with the Set
Builder. The dig ("Scava") seeds on a genre or a label and reaches into one of two sources.

```text
seed: genre or label
  -> DigSource.probe: how tall the pile is, how far this source reaches into it
  -> the engine picks an (offset, count) window from `depth`, in ITEMS
     (0.0 = the seed's classics, 1.0 = the bottom of what the source reaches)
  -> DigSource.fetch translates that window into the provider's own pagination:
     Discogs jumps to a page number, Bandcamp walks a cursor
  -> DigSource.to_lead maps raw results; unowned leads only, deduped against the
     library and against variants of each other
  -> taste ranking inside the window (familiarity + label + style), per-artist cap
  -> POST /api/discovery/add (into the library as a lead) or /save-for-later
```

The engine reasons only in items, never in a provider's pagination unit. That boundary —
`probe` / `fetch` / `to_lead` in `services/dig_sources/__init__.py` — is what let a second
source arrive without the engine learning anything about it.

**Bandcamp trades three signals for reach**, all measured against the live API: no have/want
counts (no rarity signal, so `rare_wanted` and `deep_cut` never fire), no styles in the
result list (only in the release detail, so `style_match` never fires and its weight
redistributes into artist and label), and a `reach` capped at 3,000 items
(`BANDCAMP_REACH`). The cap is a cost choice, not a Bandcamp limit: depth there costs a
sequential cursor walk rather than a page jump, and the pile itself can be far larger. In
exchange Bandcamp hands back a real per-track stream inside the dig result — no preview
resolution needed for those leads — and a richer release detail (real tags, price, exact
release date). Its one inferred field is `format_badge` (Single/EP/Album), derived from the
track count; Discogs declares the format on the release.

**Previews** (`services/preview.py`) are a pure function with injected network callables:
iTunes Search for a clean 30-second clip, falling back to the YouTube video Discogs
associates with the release, and nothing if neither resolves. Bandcamp leads skip the chain
entirely. Nothing is downloaded or kept; the same docked player handles previews and owned
tracks.

## Acquisition

```text
Track in the library (a lead)
  -> POST /api/downloads/queue (or one of the shortcut routes) enqueues a
     DownloadQueueItem — the persistent SQLite queue, services/download_queue.py
  -> download_dispatcher.fill() claims items into an N-wide worker pool
     (N = download_slots, Settings, default 3, hot-reloaded)
  -> download_runner.run_item: SlskdClient.search (slskd REST)
     -> soulseek_select ranks deterministically: quality + name match + availability
     -> auto-pick above a confidence floor, or the candidate the user chose by hand
     -> slskd enqueue + transfer polling
  -> attach_local_file: has_local_file + local_path/format/bitrate + audio_hash
```

Three modules, one job each: `download_queue` is data only — enqueue, claim, finish,
cancel, requeue — no thread and no network, so it is tested in memory. `download_dispatcher`
owns the worker pool: it decides *when* to work — how many slots are occupied, when the
slskd circuit breaker is open, when the periodic retry loop should re-poke a stalled pool
— but not *how* to download. `download_runner` (`run_item`) is the *how*: search, auto-pick,
transfer polling, exactly the logic the old single job used, now driving one item instead
of a whole batch. Zero AI throughout; best-effort — a failure on one item never blocks the
others, since each item is independent instead of steps in one sequential job.

An item is `queued` → `running` → `done` (or `cancelled` at any point before finishing); a
`done` item also carries an `outcome` in the same vocabulary the `Track` fields already
used (`downloaded`/`needs_review`/`not_found`/`failed`). Enqueuing deduplicates against a
track's own active item, so re-submitting the same track — a second click, a repeated
`retry-pending` — is a no-op rather than a duplicate download. With one exception: an
enqueue carrying a user-picked candidate replaces the payload of an item still waiting,
rather than losing to the auto-pick that got queued first.

If slskd stops responding mid-item — connection refused, but also 401/403 or any 5xx from a
daemon that answers but is unwell, and the `409 "must be connected"` of a live daemon that is
not logged into the Soulseek network — `download_runner` raises, the item goes back to `queued`
untouched (no outcome written), and the dispatcher trips a circuit breaker: for 60s, items
that need slskd are not claimed at all (a `soundcloud`-kind item, which never touches
slskd, is unaffected and keeps running). A background thread in the dispatcher retries every
30s so a queue paused by a dead daemon reopens on its own once it comes back — necessary
because nothing else calls `fill()` on an idle pool; every enqueue endpoint only does so on a
*successful* enqueue. On backend restart, any item still `running` — its worker thread is
gone — is put back to `queued` by `requeue_stale()` rather than left stranded; `boot()` does
this, then fills the pool and starts the retry loop. Behind that classification sits a blunt
safety net: five consecutive items failing for the *same* reason trip the breaker too, even
when nobody recognised the failure as infrastructural — a daemon that always fails the same
way is not a problem with the individual tracks, and 300 queued items should not be burnt
one at a time to find that out.

It requires slskd to be configured for the slskd-backed routes, which answer `409` without
it; SoundCloud download has its own preconditions instead. The file becomes a local
reference on the existing `Track`; the app neither re-uploads nor redistributes it.

Outcomes needing attention (`needs_review` | `not_found` | `failed`) go to a "to fix" queue
persisted on `Track.last_download_outcome`/`last_download_reason`, so it survives queue
churn and restarts (`GET /api/downloads/pending`, `DELETE /api/downloads/pending/{track_id}`,
`POST /api/downloads/retry-pending`). A duration mismatch also keeps
`last_download_path`, so `services/download_review.py` can offer "keep anyway / discard".

`GET /api/downloads/status`, kept for the frontend's existing global bar, derives its
aggregates from the queue rather than from a single job's state, and only for the current
"round" (a persisted marker, not the whole history — see `docs/API.md`). The `/downloads`
page (`GET /api/downloads/queue`) is the fuller view: every item, its `phase` and byte
progress while `running`, and per-item actions (cancel, move to top).

A file already on disk can be linked by hand from the track detail
(`POST /api/tracks/{track_id}/link-file`, searching by name in `LIBRARY_ROOT` and in the
slskd download folder via `GET /api/files/search`), through the same
`attach_local_file`/`audio_hash` path as acquisition.

**Per-track SoundCloud download** (`integrations/soundcloud_audio.py`) is the second
save-a-file exception: yt-dlp extracts an MP3 into the same shared download folder
(`SLSKD_DOWNLOAD_DIR`) and links it to the existing track. Single track only, from the
detail page, never a batch. Tags are untouched.

**Library sharing** is opt-in and off by default. slskd does not accept share changes over
its API at runtime — shares live in its YAML — so `services/slskd_shares.py` edits
`shares.directories` in slskd's own config (round-trip through `ruamel.yaml` to preserve
comments and formatting, `.bak` backup, permissions kept) and forces a rescan. Enabling it
exposes the library's filenames to the network.

## Mix identification

```text
SoundCloud / Mixcloud / YouTube URL
  -> yt-dlp temporary download
  -> ffmpeg audio segments
  -> Shazam recognizer
  -> consecutive matches deduped
  -> DjSet + DjSetTrack
```

Tracks identified in a mix do **not** enter the main library: they are a separate corpus for
later analysis and suggestions. This is the only fingerprinting Cratory does — on someone
else's mix, never on the library. The downloaded audio is temporary and deleted.

## Organize

`/organize` is the section that owns the disk. It is the only writer of tags, filenames and
folder layout, and every mutation is journaled so it can be undone.

```text
scan        walk LIBRARY_ROOT + SLSKD_DOWNLOAD_DIR, read tags, upsert AudioFile,
            then link files to Tracks — the same job as POST /api/library/index,
            see "One scan, two doors"
analyze     recompute over the rows already in the DB, no filesystem walk:
            inspector -> Issue rows (missing_required_tag, missing_metadata,
                         junk_tag, dirty_genre, inconsistent_casing,
                         filename_tag_mismatch, low_quality, corrupt_file, …)
            dedup     -> DupGroup + DupMember, with a proposed keeper
            the merge preserves decisions the user already made
plan        planner turns issues, dedup keepers and overrides into PlanOp rows:
            RETAG | RENAME | MOVE | DELETE | COVER, against the naming and folder
            templates ({artist} - {title}, {genre}/{artist})
            conflict runs the pre-flight: stale snapshots, colliding targets
apply       executes op by op, writing an UndoJournal entry for each; DELETE moves
            the file into a .quarantine folder instead of unlinking it
undo        replays the journal of a run backwards: retag from prior_tags_json,
            move back, restore from quarantine, strip an added cover
```

Two roots and no more: `organize/services/roots.py` derives them from Settings —
`LIBRARY_ROOT` ("library") and `SLSKD_DOWNLOAD_DIR` ("inbox"). The `scan_root` table
survives as dead schema, because `audio_file.root_id` is NOT NULL inside a unique constraint
that SQLite cannot drop; `roots.py` is the only place that writes it.

Alongside the main loop: acoustic fingerprinting through AcoustID/MusicBrainz
(`AudioFile.mbid`), text-metadata proposals from MusicBrainz and Discogs
(`services/text_providers.py`, `provider_rescan`), cover lookup and thumbnail caching
(`covers`, `cover_cache`, `thumbs`), a file-integrity check (`integrity`), a genre review
pass, and two AI-assisted helpers (`services/ai_tags.py`: "resolve with AI" on an issue, and
the genre review). Each degrades cleanly when its key or binary is missing.

Every mutation that touches a `genre` also calls `align_track_genre`, keeping the
`tracks.genre` mirror and the derived `energy` in step (see "Effective tags").

## Data model

Core (`app/models.py`):

- **`Track`** — the central row. Streaming identity (`platform`, `platform_track_id`,
  `isrc`, `url`, `spotify_id`, `soundcloud_id`, `source_type`); editorial metadata
  (`title`, `artist`, `album`, `genre`, `year`, `label`, `duration_seconds`,
  `album_art_url`); `bpm`/`camelot_key` with `bpm_source`/`key_source`; the analysis staging
  fields, all written only by the analysis job (`audio_analysis_job.py`) — `analysis_bpm` and
  `analysis_camelot` are read by the divergence check and the `/divergences` display
  (`services/audio_analysis.py: diverges`, `divergence_row`) and copied into the canonical
  `bpm`/`camelot_key` by the apply step (`apply_analysis`, `auto_apply_missing`);
  `analyzed_at` is read by the `/overview` counts and the apply endpoint's `mode="all"`
  selection; `analysis_error` (set at `audio_analysis_job.py:62,65`) is read by nothing —
  not exposed in any schema, not read by any router, service, or serializer, verified with
  `grep -rn analysis_error backend/app frontend/app frontend/components frontend/lib` (only
  the model declaration, the job's two writes, and an `essentia_engine.py` docstring) — it
  exists to be visible in a DB inspection after a failed batch, not to drive behavior;
  `analysis_dismissed_bpm`/`analysis_dismissed_camelot` and
  `analysis_dismissed_of_bpm`/`analysis_dismissed_of_camelot` — the dismiss snapshot
  (`services/audio_analysis.py: dismiss_divergence`, `is_dismissed`), one pair per side
  (analyzed, canonical) so a later change to either reopens the divergence;
  `energy` with `energy_raw` and
  `energy_source` (`computed` | `estimated`); ownership (`has_local_file`, `local_path`,
  `local_format`, `local_bitrate`, `local_mtime`, `local_size`, `audio_hash`,
  `primary_file_id` → the representative `AudioFile`); `archived`; a 1–3 personal `rating`
  (a 3 puts the track in the special `kind='rating_top'` playlist, kept in sync inside the
  same transaction by `services/rating.py`); the
  download queue fields `last_download_outcome`, `last_download_reason`,
  `last_download_path`; and `status` (`imported` | `ready_for_set`).
- **`Playlist`** and **`playlist_tracks`** — the M2M association carries a per-playlist
  `added_at`. **`PlaylistSyncEvent`** stores each import's diff as a textual snapshot.
- **`Setlist`** — prompt, strategy, explanation, `owned_only`, `generated_by`,
  `validation` (AI warnings and missing-library suggestions; `{}` without AI) and `curation`
  (`intent_summary`, compiled constraints, warnings; `{}` without curation).
  **`SetlistTrack`** — position, role, score, transition notes, AI reason, risk, `mood_tags`.
- **`DjSet`** / **`DjSetTrack`** — an identified external mix and its tracks; a corpus kept
  apart from the library.
- **`SpotifyToken`** — OAuth tokens for the local user (`kind='user'` or `'client'`).
- **`DownloadQueueItem`** — one acquisition job in the persistent download queue (see
  "Acquisition"): `track_id`, `kind` (`soulseek_auto` | `soulseek_chosen` | `soundcloud`),
  `payload` (JSON, only for `soulseek_chosen` — the user-picked candidate), `state`
  (`queued` | `running` | `done` | `cancelled`), `outcome` (only meaningful once `done`,
  same vocabulary as `Track.last_download_outcome`), `position` (queue order), `attempts`,
  `phase`/`bytes_done`/`bytes_total` (live progress while `running`), `error`,
  `enqueued_at`/`started_at`/`finished_at`. `state` and `outcome` are kept apart on purpose:
  a downloaded-but-suspect file is `state='done', outcome='needs_review'`, never a hybrid
  state.
- **`AppState`** — persistent key/value for app state (`language`, `last_index_at`, …), also
  where `download_slots` and the queue's current-round marker
  (`downloads_queue_round_start_id`) live.
- **`ArchiveSeen`** — (path, mtime, size) of archive files matching no track, so the
  incremental pass can skip re-hashing them.

Organize (`app/organize/models.py`):

- **`AudioFile`** — one physical file: path, `location` (`library` | `inbox`), technical
  fields (ext, bitrate, sample rate, channels, duration, size, mtime), `content_hash`, the
  nine editable text tags, `isrc`, `mbid`, `has_cover`, `has_rating`, `status`, integrity
  results, and `track_id` → the `Track` it is a copy of (NULL while unrecognized). A `Track`
  can have several files; `Track.primary_file_id` names the representative one.
- **`Issue`**, **`DupGroup`** / **`DupMember`**, **`Plan`** / **`PlanOp`**,
  **`UndoJournal`**, **`Settings`** (naming and folder templates), **`ScanRoot`** (dead
  schema, see above).

Scope notes: beatgrid, cue points, `rekordbox_track_id`, `play_count` and `tonality` are not
in the model — Cratory imports BPM and key, nothing else, from Rekordbox. The pre-M2M columns
`Track.playlist_id` and `Track.playlist_name` are still in the schema but dead and empty:
SQLite cannot drop `playlist_id` without rebuilding `tracks`, because of a baked-in FK, and
the project avoids that.

## Integrations

| Integration | State | Boundary |
|---|---|---|
| Spotify | active | OAuth, playlist import and export, Discovery identity resolver. No BPM/key; `/recommendations` unusable. |
| SoundCloud | active if yt-dlp present | Playlists, secret links and likes via yt-dlp, **metadata only** — flat preview for speed, full per-track extraction (uploader, duration, artwork) on import. No ISRC, so dedup falls back to `platform_track_id`; sync is always additive. |
| SoundCloud (audio) | active if yt-dlp present | Per-track MP3 download from the detail page — the one place SoundCloud audio is saved. |
| Discogs | active | Discovery dig by genre/label, plus release detail and the YouTube preview fallback. Works without a token; `DISCOGS_TOKEN` raises the rate limit and adds covers. Also a text-metadata provider inside Organize. |
| Bandcamp | active | Second dig source behind the same `DigSource` seam. Internal, undocumented endpoints, no key. Contract-tested under `@pytest.mark.network`, excluded from the default suite. |
| iTunes Search | active | 30-second preview clips for dig leads. Public, no key. |
| Rekordbox | manual, via XML | BPM/key source. No API and no dependency — a file upload and a parser. |
| Essentia | active if installed | In-app deterministic BPM/key analysis. Lazy import: the app runs without it and `is_available()` gates the `503`. Pinned `essentia==2.1b6.dev1389`, AGPL-3.0. |
| Shazam | active if deps present | ffmpeg + yt-dlp + shazamio. Fingerprints an external mix, never the library. |
| slskd (Soulseek) | active if configured | Acquisition over the local daemon's REST API, plus the opt-in share flag. `SLSKD_URL` / `SLSKD_API_KEY` / `SLSKD_DOWNLOAD_DIR`. |
| AcoustID + MusicBrainz | active if configured | Organize only: acoustic fingerprint → `AudioFile.mbid`, and text-metadata proposals. Needs the `fpcalc` binary and `ACOUSTID_API_KEY`. |
| Anthropic (LLM) | active if configured | Set curation and Organize's tag/genre helpers. One key, `ANTHROPIC_API_KEY` (`AI_API_KEY` is read as a legacy alias). Schema-constrained output. |

None of the external providers supplies BPM, key, mood or energy. Text metadata and tagging
are Organize's job.

Shared plumbing: `integrations/_http.py` retries transient transport failures (TLS handshake
drops, resets, timeouts) with backoff before letting the provider's exception through, so a
flaky network becomes "not found" for one track rather than a dead job.

## Internationalization

Cratory is bilingual, Italian and English. The language is a persistent setting (key
`language` in `AppState`, default `it`), toggled in Settings; there is no per-locale routing
— single user, no SEO. Endpoints `GET`/`PUT /api/settings/language`.

Three surfaces, three strategies:

- **Frontend UI** — a hand-rolled TypeScript dictionary in `frontend/lib/i18n/`. `en.ts` is
  the source of truth for the key set; `it.ts` is typed `: Dictionary` (`= typeof en`), so a
  missing or extra key is a compile error. `I18nProvider`/`useT()` expose the active
  dictionary, and `runtime.ts` keeps the language readable outside React (for `lib/api.ts`)
  without an import cycle.
- **Backend errors** — language-agnostic. Every `HTTPException` goes through
  `api_error(status, code, message, **params)` (`app/core/http_errors.py`), producing a
  structured `detail` of `{code, message, params?}`; the frontend translates `code` from the
  dictionary's `errors` namespace, with the English `message` as the fallback.
- **Generated phrases and AI output** — produced by the backend directly in the selected
  language. Enum labels stay codes, translated on the frontend; composed phrases (reason,
  mixing tip and overview in `services/scoring.py`, job phases and curation text in
  `services/ai_curation.py`) come from per-language catalogs indexed by `get_language(db)` at
  the entry point. The AI system prompts stay in Italian as instructions to the model; only
  the directive about the output language is parametric.

Known limitation: `transition_reason` values are persisted at generation time in whatever
language was active then — the future display language is not knowable in advance.

## Setup and credentials

First launch (`setup.completed` unset in `AppState`) sends the user to `/setup`, a
six-step wizard — welcome/language, prerequisites, library paths, external services,
slskd, summary — gated by `SetupGate` (mounted in `app/layout.tsx`, inside
`I18nProvider`/`PlayerProvider`, before the page shell renders): it reads
`GET /api/setup/state` on every navigation and redirects only on a *successful*
`completed: false` response, so a backend that's down never strands the user on a
wizard it can't drive. Finishing the wizard and skipping it both write `completed:
true` through `PUT /api/setup/state`, with no distinction between the two; "reopen
wizard" in `/settings` writes it back to `false` and sends the user to `/setup`
again. `CredentialField`/`ServiceGuide`, wrapped together as `ServiceCard`, are the
one implementation shared between the wizard's services and slskd steps and
`/settings`' own expandable per-service row — a key can be changed from either place
without re-running the rest of the wizard. `PathField` and `ComponentRow`
(prerequisites) stay wizard-only: `/settings`' path editor (`ConfigCard`) is a
separate, pre-existing implementation.

**Credentials became runtime-writable.** `core/runtime_settings.py` now covers two
groups: `ENV_BACKED_KEYS` (plain fields — paths, URLs, `ai_model`) and `SECRET_KEYS`
(`spotify_client_id`, `spotify_client_secret`, `ai_api_key`, `discogs_token`,
`acoustid_api_key`, `slskd_api_key`). Both resolve a DB override (`AppState`, key
prefix `cfg.`) over the `.env` default, cached in memory — loaded once at startup,
kept in sync on every `apply`/`clear` — because most read sites (the slskd client,
indexing/download jobs, `file_search`) don't have a DB session at hand. Every
integration that used to read a `Settings` constant (`settings.SPOTIFY_CLIENT_ID` and
similar) directly now goes through `runtime_settings.secret(...)` or the matching
plain-field accessor, so a key saved from the wizard or from `/settings` takes effect
on the very next call — no restart. `GET`/`PATCH /api/settings/config` exposes
secrets only masked (`configured`, `source`, `hint` — never the value); see
`docs/API.md`.

**Detecting and installing external components.** `services/system_probe.py` is a
declarative registry of three external binaries — `ffmpeg`, `fpcalc`, `slskd` — how to
detect each, what it unlocks, and (for `ffmpeg`/`fpcalc`) the install recipe per
platform. `yt-dlp` and `essentia` used to be registry entries too; they left because they
were never external binaries — they're ordinary Python packages pinned in
`requirements.txt`, and `pip install -r requirements.txt` already puts them in the
backend's own venv, so probing for them and offering to "auto-install" was solving a
problem `pip` had already solved. Detection follows how the app actually consumes what's
left: `ffmpeg`/`fpcalc` are resolved on disk (`resolve_binary`); `slskd` is a daemon,
probed by calling its own `/health` rather than by looking for a binary — the same module
also downloads, configures and starts it now, see below. Presence for the two binaries is
decided by the subprocess exit code, never by its output: a non-zero exit returns no
version, otherwise a failure message on stderr — wrong architecture, permission denied,
a corrupt or partial download — would read as a version string and report a missing or
broken component as installed. The registry carries no prose — only feature keys
the frontend translates and a `docs` URL per component, which for `slskd` (no install
recipe exists) is the only guidance the UI can offer.

There are two ways the wizard can install a component for real, and a manifest entry
always wins: if `binary_manifest` has a pinned build for this platform, it downloads —
the install stays inside the app's own managed folder, removable by deleting it. Where
no such build exists, the fallback is to run the registry's recipe itself
(`binary_installer.run_recipe`, a plain `subprocess.Popen` over the recipe's argv as a
list — never a shell string, and no user input reaches it), but only when the recipe's
own command is actually present on the system (`system_probe.available_recipe`, checked
with `shutil.which`): `brew` doesn't ship with macOS, so a recipe alone is not the same
promise as a build we can supply ourselves — it modifies the system, with its
dependencies, not just Cratory's folder. `install_method` in the probe payload
(`"download"` / `"recipe"` / `"manual"`) tells the frontend which of the two `true`
cases of `installable` applies, so the row can say which promise it's making before the
button is pressed. `install_command` itself is unconditional — the platform's recipe,
shown as the manual fallback regardless of which route the button would take, or `null`
where none exists (`slskd`). This is **why macOS has no `ffmpeg` entry in the
manifest**: BtbN, the only upstream that publishes static builds with checksums, ships no
macOS asset, and no other source publishes a native `arm64` build with a checksum to pin
— an Intel binary that depends on Rosetta, shipped as the one *required* component, was
judged worse than running `brew install ffmpeg` through the recipe route instead.

`services/binary_manifest.py` holds the download side, deliberately separate from the
registry above: this file changes at the cadence of version bumps, the registry describes
behavior. Per component per platform tag (`darwin-arm64`, `linux-x86_64`, …) it pins a
version, a download URL and a SHA256 — fixed in code, not fetched at install time. Both
matter for a different reason: the pinned hash is what stops a tampered release upstream
from being accepted (a digest read from GitHub's own API at install time would come from
the same source a compromised release would also control, so it can't be the thing trusted
at that moment), while a download that verified and extracted cleanly can still produce a
binary that will not run — wrong architecture, a missing signature — which is why
`services/binary_installer.py` treats **an install as valid only once the binary has
actually executed**, not once the bytes match (or, on the recipe route, once the package
manager's own exit code says success). The download sequence is download-while-hashing →
verify against the pin → extract to a temp directory → run with the component's version
flag → only then move into the managed folder, so an installation interrupted at any
point never leaves a half-installed binary in place of a working one. The recipe route
runs the same verification after the recipe finishes: it invalidates the probe's cache
first (the binary now lives on the system `PATH`, not the managed folder the cache
otherwise assumes) and only then re-resolves and runs the binary — a `brew install
ffmpeg` that exits 0 while ffmpeg still isn't runnable fails the install exactly like a
bad download would. `routers/setup.py` is HTTP-only over probe/install;
`services/credential_tests.py` (unrelated to binaries) makes one real, minimal call per
provider (`spotify`, `anthropic`, `discogs`, `acoustid`) and returns the provider's own
error message, not a paraphrase.

**The boundary around slskd moved.** Elsewhere in this document slskd is described as an
external service Cratory only reaches over HTTP — that's still how Cratory talks to it once
it's running, but no longer the whole story: `services/slskd_daemon.py` now downloads it
(through `binary_installer` above), writes its configuration and starts it as a detached
process, a deliberate exception to "Cratory doesn't run its own services." Two rules keep
the exception contained. The user's own config file is never destroyed: `write_config`
touches only the four keys Cratory needs — Soulseek username/password, web port, download
directory — and leaves everything else in `slskd.yml` (shares, API key, comments) exactly
as it was, writing a `.bak` before every rewrite, with the same restrictive permissions as
the file it backs up (both hold the same clear-text password). And only a daemon this app
started is ever stopped: `stop()`'s sole authority is `owned_pid()`, which doesn't trust a
bare PID (the OS reuses them) but checks that the live process under that PID is still, bit
for bit, the same executable path `start()` recorded in the pid file when it launched it —
a mismatch means the pid file is stale, and it gets removed rather than acted on. When
`write_config` creates `slskd.yml` from scratch, the port and download directory it picked
(explicit or default) also get written into Cratory's own settings (`slskd_url`,
`slskd_download_dir`) — `is_reachable()`, the criterion `start()` polls against after
spawning the process, reads those settings, not the YAML file, so without this write-back a
freshly configured daemon spawns, runs and answers `/health` correctly while Cratory still
concludes the start failed and tears it back down.

**One seam exists purely for an eventual Tauri desktop build**, where Cratory's own
binaries and processes stop being "whatever this dev machine's `PATH` happens to have" and
become part of a shipped app bundle: `system_probe.resolve_binary(name, env_override)`
checks a component-specific env var, then `CRATORY_BIN_DIR`, then falls back to
`shutil.which` on `PATH`. `CRATORY_BIN_DIR` isn't new — it was already consulted ahead of
`PATH` app-wide — it simply gained a default (`managed_bin_dir()`, a `bin/` folder under the
backend) so there's always somewhere for the installer to write even when nobody has set
the env var. `resolve_binary` knows both layouts `binary_manifest.py` can produce: `single`
puts the executable straight at `<bin_dir>/<name>` (fpcalc), `bundle` — the executable isn't
self-contained, ffmpeg and slskd both ship this way — puts it one level down, at
`<bin_dir>/<key>/<name>`, and `resolve_binary` tries both before falling back to `PATH`. A
Tauri build that ships `ffmpeg`/`fpcalc`/`slskd` inside the bundle, laid out the same way,
only has to set `CRATORY_BIN_DIR` once at launch — nothing else in the probe, the installer
or the daemon changes. The seam isn't probe-only: `acoustid.fpcalc_available`,
`organize/integrations/integrity`'s `ffmpeg_available`, and the ffmpeg checks in
`routers/downloads.py` and `routers/dj_sets.py` all delegate to it too, so a bundle build
can't leave those disagreeing with the wizard about the same binary.

## Frontend

Next.js 16 with the App Router, React 19, Tailwind 4. `frontend/CLAUDE.md` documents the
Next 16 breaking changes; read it before touching pages or routing.

`app/layout.tsx` mounts, in order: the DM Mono font variable, an inline no-FOUC script that
restores the theme and language from `localStorage`, `I18nProvider`, `PlayerProvider`,
`SetupGate` (see "Setup and credentials" above), `ShellSwitch` and the app-wide
`DockedPlayer`. `ShellSwitch` is a thin client component that picks the frame by pathname:
every route gets `EditorialShell` (the hairline shell: a sticky 180px INDEX nav beside the
content), while `/setup` renders full-screen without it, so the wizard has the whole viewport.
It receives `children` as a prop, so the pages inside stay server-rendered. `PageLayout`
adds the page title and the optional 240px MARGINALIA
column on top of that. Pages live under `app/` (dashboard, playlists, library, tracks, set-builder,
sets, transitions, analysis, discovery, wishlist, downloads, labels, statistics, shazam,
organize, settings, setup); the
typed API client is split by area under `lib/api/`, with `lib/organize/api.ts` for the
Organize surface. `docs/DESIGN.md` holds the design system.

## Persistence and migrations

SQLite, one file:

```text
backend/data/djassistant.db
```

The filename is legacy and deliberately kept. Relative SQLite paths in `DATABASE_URL` are
resolved against `backend/`, never against the process working directory, so the app cannot
scatter stray databases.

`ensure_schema()` creates the tables — core and Organize share one `Base` and one engine —
and applies idempotent migrations, including the FK-safe rewrites needed where SQLite cannot
drop a column in place. There is no Alembic. If the product is ever renamed, do not rename
the database automatically: either plan a migration or keep the legacy path.
