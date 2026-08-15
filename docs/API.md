# API

Endpoint reference for the FastAPI backend. 141 routes, all under `/api`.

Base URL when running locally:

```text
http://localhost:8000
```

Request and response schemas are Pydantic models (`backend/app/schemas.py`,
`backend/app/organize/schemas.py`) and the backend serves them interactively at
`/docs` and `/openapi.json`. This document does not repeat them: it says what a
caller needs that the schema does not tell them — which endpoints pair with which,
what a call does to the data, and the rules that decide whether a write lands.

## Conventions

**Errors come in two shapes, and a client has to handle both.**

*Errors a handler raises deliberately* go through `api_error` and carry a structured
object:

```json
{"detail": {"code": "playlist_not_found", "message": "Playlist not found",
            "params": {"…": "optional"}}}
```

`code` is a stable identifier the frontend translates; `message` is English, for
`curl` and logs. These are the errors named inline throughout this document.

*Request validation failures* never reach a handler, so they never get that shape.
The backend registers no `RequestValidationError` handler, so Pydantic and `Query`
rejections keep FastAPI's default form — a **list**, with no `code` at all:

```json
{"detail": [{"type": "extra_forbidden", "loc": ["body", "energy"],
             "msg": "Extra inputs are not permitted", "input": 50}]}
```

Every `422` this document attributes to a schema or a query-parameter pattern is of
the second kind: `energy` rejected by `extra="forbid"`, a `language` outside
`it`/`en`, a `sort` outside its whitelist, a `rating` outside `1`-`3`, the move
request's "exactly one of `direction`/`to`". The `422`s raised in handler code —
`analysis_force_required`, `analysis_apply_empty`, `invalid_camelot_key`,
`order_mismatch`, `tracks_not_found`, `invalid_setting`, and the rest — are of the
first. **Do not parse `detail.code` unconditionally**: check whether `detail` is an
object or a list first.

**Jobs and polling.** Anything that can take longer than a request runs as a
background job: the start endpoint returns the initial job state, and a paired
status endpoint is polled until `status` leaves `running`. Each job is
single-instance — a second start while one is running gets `409` or the state of the
running job, never a queue slot.

**The success code of a start endpoint is per endpoint, not a convention** — some
return `202`, some `200`. The table below is the authority; do not assume `202`.

| Job | Start | Status |
| --- | --- | --- |
| Library scan / index | `POST /api/organize/scan` (**200**), `POST /api/library/index` (**202**) | `GET /api/organize/scan/status`, `GET /api/library/index/status` |
| Organize apply | `POST /api/organize/apply` (**200**) | `GET /api/organize/apply/status` |
| Streaming import/sync | `POST /api/playlists/import`, `/import/liked/selected`, `/{id}/sync`, `/sync-all`, `POST /api/soundcloud/import`, `/import/likes` (all **202**) | `GET /api/playlists/import/status` |
| Set generation | `POST /api/sets/generate-async` (**200**) | `GET /api/sets/generate-status` |
| BPM/key analysis | `POST /api/analysis/start` (**202**) | `GET /api/analysis/status` |
| Soulseek / SoundCloud download | `POST /api/downloads/playlist/{id}`, `/track`, `/track/auto`, `/track/soundcloud`, `/retry-pending` (all **202**) | `GET /api/downloads/status` |
| Mix identification | `POST /api/shazam/identify` (**200**) | `GET /api/shazam/identify-status` |
| Provider rescan | `POST /api/organize/issues/provider-rescan` (**200**) | `GET /api/organize/issues/provider-rescan/status` |
| Integrity check | `POST /api/organize/issues/integrity-check` (**200**) | `GET /api/organize/issues/integrity-check/status` |
| AI genre review | `POST /api/organize/genre-review` (**200**) | `GET /api/organize/genre-review/status` |

Jobs also exclude each other across areas where the data would tear: a scan
refuses to start while an Organize apply is running (`409 apply_running`) and vice
versa (`409 scan_running`), because scanning a half-moved tree mis-merges rows.

**Layering.** Scoring, dedup, ranking, rate limiting, retry and caching live in
`services/` and `integrations/`. Routers are mostly HTTP-only, but not as a hard
rule — see `CLAUDE.md`'s stack-and-layout list for the named exceptions.

## Health and pipeline

```text
GET /api/health
GET /api/pipeline
```

`GET /api/health` → `{status: "ok"}`. Registered directly on the app, not in a
router.

`GET /api/pipeline` is the single snapshot behind the dashboard's orientation
strip: library counts (`playlists`, `total_tracks`, `missing_key`, `wishlist`,
`archived_count`, `with_local_file`, `analyze_pending`, `ready_for_set`), download
state (`download_active`, `download_pending`) and disk state (`inbox_files`).
`analyze_pending` counts owned tracks missing BPM or key — the same number as
`GET /api/rekordbox/pending`. `inbox_files` is `null` when `SLSKD_DOWNLOAD_DIR` is
unset or does not exist; that is a neutral state, not an error. The inbox count is
cached for 10 seconds so a 2-second poll does not re-walk the folder every time.

## Playlists

```text
GET    /api/playlists
GET    /api/playlists/{playlist_id}
PATCH  /api/playlists/{playlist_id}
DELETE /api/playlists/{playlist_id}
GET    /api/playlists/{playlist_id}/tracks
GET    /api/playlists/{playlist_id}/sync-log
GET    /api/playlists/{playlist_id}/gaps
GET    /api/playlists/library/gaps
POST   /api/playlists/{playlist_id}/export
```

```text
GET    /api/playlists/spotify/available
GET    /api/playlists/spotify/liked/preview
POST   /api/playlists/import
POST   /api/playlists/import/liked/selected
POST   /api/playlists/{playlist_id}/sync
POST   /api/playlists/sync-all
GET    /api/playlists/import/status
POST   /api/playlists/import-manual
```

```text
POST   /api/playlists/create-from-tracks
POST   /api/playlists/{playlist_id}/duplicate
POST   /api/playlists/{playlist_id}/add-tracks
POST   /api/playlists/{playlist_id}/reorder
PUT    /api/playlists/{playlist_id}/order
DELETE /api/playlists/{playlist_id}/tracks/{track_id}
POST   /api/playlists/{playlist_id}/tracks/remove
```

### Import and sync from streaming

The four entry points here, plus the two SoundCloud ones, feed **one shared job
slot** — six routes, one job. A second start gets
`409 streaming_import_already_running`. Progress and the final report come from
`GET /api/playlists/import/status` (`status`, `kind`, `phase` = `fetching` |
`importing`, `processed`/`total`, `current_label`, `result`, `sync_all`, `error`,
`error_code`). Provider failures surface in the job state, not as an HTTP error on
the start call.

`GET /api/playlists/spotify/available` lists only playlists **owned** by the
connected user; playlists they merely follow are excluded, because Spotify's
development mode denies access to their items.

`GET /api/playlists/spotify/liked/preview` lists the saved (liked) tracks and marks
which are already in the local Liked playlist. Nothing is imported.
`POST /api/playlists/import/liked/selected` then imports only the chosen ones
(additive, never prunes).

`POST /api/playlists/import` imports a Spotify playlist, or the whole liked set
when `playlist_id` is the literal string `"liked"`.

`POST /api/playlists/{playlist_id}/sync` realigns an already-imported playlist with
its source. **Spotify prunes, SoundCloud does not**: Spotify adds new tracks and
unlinks removed ones (the tracks stay in the library), while SoundCloud is always
additive so a taken-down track never unlinks anything. Memberships Cratory created
itself (`added_by='cratory'`) are never pruned on either platform.

**Only Spotify and SoundCloud playlists can be synced at all** — a manual, Shazam,
Discovery or Top playlist has no source to realign with. Four ways this call is
refused:

- `404 playlist_not_found` — no such playlist.
- `409 playlist_platform_not_syncable` — the playlist is not from Spotify or
  SoundCloud.
- `409 playlist_not_syncable` — a Spotify playlist with no
  `platform_playlist_id` (liked playlists are exempt from this check).
- `409 soundcloud_playlist_not_syncable` — a SoundCloud "likes" playlist, or one
  with no stored `url`. Likes only grow through the selective flow.

The same rule decides which playlists `sync-all` picks up.

`POST /api/playlists/sync-all` realigns every imported Spotify and SoundCloud
playlist in one job; liked playlists are excluded on both platforms. A playlist
that fails does not stop the others: the job still ends `done` and the aggregate
lands in `sync_all` (`synced`, `failed`, summed `created`/`updated`/`removed`/
`skipped`, and `failures[]` with `playlist_id`, `name`, `platform`, `error`).
During the run `processed`/`total` count playlists, not tracks, and
`current_label` carries the playlist in flight with its own item progress.
`409 no_syncable_playlists` when there is nothing to realign.

`POST /api/playlists/import-manual` creates a playlist from pasted text
(`Artist - Title` lines or CSV). `422 no_tracks_recognized` if nothing parses.

None of these start any enrichment: text metadata is the Organize section's job and
BPM/key come from Rekordbox or the in-app analysis.

### Building playlists by hand

`POST /api/playlists/create-from-tracks` (`201`) builds a manual playlist from
tracks already in the library, in the given order. `422 playlist_name_empty`,
`422 tracks_not_found` (with `missing`).

`POST /api/playlists/{playlist_id}/duplicate` (`201`) forks any playlist into a
manual copy with the same order — the way to get an editable, reorderable version
of a synced playlist. `name` defaults to `"<name> (copia)"`.

`POST /api/playlists/{playlist_id}/add-tracks` adds library tracks to an existing
playlist. Idempotent: ids already present, and repeats inside one request, count as
`skipped`. New memberships are `added_by="cratory"`, so a later sync prune leaves
them alone.

`POST /api/playlists/{playlist_id}/reorder` moves one track to a 1-based position
(clamped to `[1, N]`); `PUT /api/playlists/{playlist_id}/order` replaces the whole
order in one call and requires `track_ids` to be an exact permutation of the current
members (`422 order_mismatch`). Both are limited to playlists whose order belongs to
the user — kinds `manual` and `shazam` — and answer `409 playlist_not_reorderable`
otherwise. Order is persisted in `playlist_tracks.position`, not a client-side sort.

Both return the reordered members in the new order. The rows are `TrackOut`, but
unlike `GET .../tracks` they leave `playlist_position` and `playlist_added_at`
unset — read the position from the array index, or re-fetch the tracks endpoint if
you need `playlist_added_at`.

`PATCH /api/playlists/{playlist_id}` renames the playlist and sets
`name_locked=true` (exposed in the response): from then on a sync re-reads
everything from the platform **except** the name.

### Removal and orphan leads

`DELETE /api/playlists/{playlist_id}` removes the playlist and any "orphan leads" it
leaves behind — tracks with no local file that are in no other playlist and no saved
set. Tracks on disk, or referenced elsewhere, survive. Response `{deleted_tracks}`.

`DELETE /api/playlists/{playlist_id}/tracks/{track_id}` removes one membership with
the same orphan rule (`404 playlist_track_not_found` if the membership does not
exist). `POST /api/playlists/{playlist_id}/tracks/remove` is the bulk version:
non-member ids are ignored, response `{removed, deleted_tracks}`.

### Reading

`GET /api/playlists/{playlist_id}/tracks` returns members in playlist order. Each
row carries `playlist_position` (1-based) and `playlist_added_at` — when the track
entered *this* playlist, which for imports is the platform's date. Both fields exist
only on this endpoint; `added_at` elsewhere is the first library import.

`GET /api/playlists/{playlist_id}/sync-log?limit=` (default 20, max 100) returns
recent import/sync diffs newest first: `{id, created_at, added, removed}` where the
two lists are `{id, artist, title}` snapshots, readable even after a track was
deleted as an orphan. Only syncs that changed the membership set record an event.

`GET /api/playlists/{playlist_id}/gaps` and `GET /api/playlists/library/gaps` run
the deterministic gap analysis over one playlist or the whole library.

`POST /api/playlists/{playlist_id}/export?format=` exports in playlist order:
`m3u8` (default, importable in Rekordbox — only tracks with a local file, the
skipped count noted in a comment), or `csv` | `text` | `markdown`, which include
every track, leads too.

### The system playlists

Three playlists are maintained by the app rather than created through an endpoint:

- **"Top"** (`kind="rating_top"`) mirrors the rating exactly: a track joins the
  moment its `rating` reaches `3` and leaves when it drops below or is cleared. It
  is created lazily on the first `rating=3` and there is at most one. The sync runs
  inside the same transaction as `PATCH /api/tracks/{track_id}`, before commit.
  Equivalent to querying `GET /api/tracks?rating=3`.
- **"Discovery"** collects leads from `POST /api/discovery/save-for-later`.
- **"SoundCloud Likes"** collects selectively imported likes.

Memberships in all three are `added_by="cratory"`.

## Tracks and library

```text
GET   /api/tracks
GET   /api/tracks/{track_id}
PATCH /api/tracks/{track_id}
GET   /api/tracks/{track_id}/cover
GET   /api/tracks/{track_id}/audio
POST  /api/tracks/{track_id}/link-file
POST  /api/library/index
GET   /api/library/index/status
GET   /api/library/genres
GET   /api/stats
```

### Effective tags

For an owned track, `genre`/`album`/`label`/`year` carry the **effective** value:
the tag on the linked file (`Track.primary_file_id` → `AudioFile`) when it is set,
otherwise the value imported from streaming. This is resolved at query time with a
`COALESCE`, not stored in a derived column. `TrackOut` exposes `primary_file_id` and
the flags `genre_from_file`/`album_from_file`/`label_from_file`/`year_from_file`;
the detail response additionally has `file_artist`/`file_title`, informational only
— track identity stays `Track.artist`/`Track.title`.

The same effective value backs the `genre`/`album`/`label` filters, `sort=genre`,
`sort=year`, the exports, the transitions list, the set alternatives and the
candidate engine's genre pool. Callers should not expect the streaming value to
show through anywhere.

**Editing those four fields on an owned track does not go through the track API.**
For a manual, ad-hoc edit, the endpoint is `POST /api/organize/files/{file_id}/tags`,
called against the track's `primary_file_id` — `tagio.write_tags` also has two other
callers that are not manual edits: Organize's apply (a RETAG op) and undo (restoring
`prior_tags_json`); see `docs/ARCHITECTURE.md`'s Organize section. A track with no owned
file edits them through `PATCH /api/tracks/{track_id}` as usual.

### Listing and filtering

`GET /api/tracks` filters on:

- **substring, case-insensitive**: `artist`, `title`, `album`, `genre`.
- **exact**: `label` (the drill-down from the labels page), `source`
  (`spotify|soundcloud|manual|local_files`), `status` (`imported|ready_for_set`),
  `rating` (`1`-`3`; unrated tracks never match this filter).
- **exact but case-insensitive**: `key` (so `7a` finds `7A`).
- **range**: `bpm_min`/`bpm_max`, `duration_min`/`duration_max`.
- **boolean**: `has_spotify`, `has_soundcloud`, `has_local_file`,
  `incomplete_metadata`, `archived` (default `false` — archived tracks are excluded
  unless you ask for them).
- `in_playlist` — repeatable (`?in_playlist=1&in_playlist=2`), matching tracks in
  **any** of those playlists, AND-combined with every other filter. For the members
  of a single playlist use `GET /api/playlists/{playlist_id}/tracks` instead, which
  also gives position.

`sort` accepts `title|artist|source|bpm|key|energy|genre|duration|year|status|
rating|added_at` with `order=asc|desc`; `rating IS NULL` always sorts last
regardless of `order`, and `added_at` is the first library import. `limit` defaults
to 100, max 500, and `limit=0` means no pagination; `offset` (default 0) pages
through the rest. The response carries `total` alongside `items`, so `total` is the
unpaginated match count.

### Writing

`PATCH /api/tracks/{track_id}` is a partial update: fields absent from the body are
untouched, an explicit `null` clears the field. Manual values always win over
imported ones.

- `camelot_key` must be valid Camelot notation — `422 invalid_camelot_key`
  otherwise.
- `energy` is **rejected** (`422`, the schema is `extra="forbid"`): it is derived
  from BPM plus genre and recomputed automatically when the patch touches either.
- `archived` is the exception to "null clears": the column is a NOT NULL bool, so
  an explicit `null` means unchanged. Library indexing still wins — owning the file
  on disk sets `archived` back to `false`.
- `rating` is `1`-`3` or `null`, available on every track including ones not owned.
  An explicit `null` clears the vote. Setting or clearing it syncs the "Top"
  playlist in the same transaction. The vote never reaches the AI and affects no
  deterministic score beyond the Set Builder tie-break below.

`POST /api/tracks/{track_id}/link-file` links a file on disk to the track —
ownership without a download. It validates existence and audio extension, sets
`has_local_file`/`local_path`/`local_format`/`local_bitrate` plus a best-effort
audio hash, and clears any pending download outcome. `400 track_link_failed` on an
invalid path.

### Media

`GET /api/tracks/{track_id}/cover` serves the artwork **embedded in the file** of an
owned track, read from disk on demand and never stored in the DB
(`Cache-Control: max-age=3600`). `404` if the track does not exist, is not owned,
the file is gone, or there is no embedded cover. The frontend prefers Spotify's
`album_art_url` and falls back here.

`GET /api/tracks/{track_id}/audio` streams the owned local file for quick audition,
read-only — the file and its tags are never touched. `FileResponse` handles Range
requests, so a seek gets a `206`. The resolved `local_path` must sit inside one of
the allowed roots (`LIBRARY_ROOT` plus the slskd download dir), which defends
against traversal and symlinks pointing outward. Distinct 404 codes:
`track_not_found`, `track_no_local_file`, `track_file_not_allowed` (outside the
roots), `track_file_missing` (inside the roots but gone). No transcoding — a format
the browser cannot decode simply fails client-side. One track at a time through the
shared docked player, the same one used for the Discovery preview.

### Indexing

`POST /api/library/index` (`202`) is an **alias for the single scan job**, exactly
what `POST /api/organize/scan` starts with no location restriction: one walk over
the configured roots, then the linking phase (link to `Track`, archive pass,
ownership reconciliation, energy calibration). `409 apply_running` while an Organize
apply is in progress; `409 library_root_not_configured` when no library root is set.

`GET /api/library/index/status` returns that job's state — `{status, phase,
processed, total, result, error, started_at, finished_at}` — not a flat report.
`phase` is `scanning | linking | inspecting | deduping | null`. `result` is the scan
summary (`found`, `inserted`, `updated`, `unchanged`, `moved`, `missing`, `errors`)
plus `result.linking` with the linking counters (`scanned`, `matched`, `created`,
`relinked`, `unchanged`, `duplicates`, `failed`, `lost`, `archived`,
`orphans_removed`, `energy_computed`, the `archive_*` counterparts and `errors[]`)
and `result.analysis` with the issue/duplicate recount. **`result.linking` is `null`**
when the run did not walk the library root: a scan restricted to the inbox stops
after the walk and deliberately leaves the tracks alone.

`GET /api/library/index/status` and `GET /api/organize/scan/status` are the same
job state; either can be polled.

### Aggregates

`GET /api/library/genres` returns `{genre, count}[]` over the effective genre among
candidate tracks (BPM present), sorted by frequency then name — this feeds the Set
Builder's genre multi-select.

`GET /api/stats` returns the deterministic library aggregates: counts, BPM/key
coverage, `key_distribution`, `genre_distribution` (genres merged
case-insensitively, keeping the most frequent spelling), and BPM and energy
histograms.

## Set Builder and saved sets

```text
POST   /api/sets/generate-async
GET    /api/sets/generate-status
GET    /api/sets
GET    /api/sets/{setlist_id}
PATCH  /api/sets/{setlist_id}
DELETE /api/sets/{setlist_id}
POST   /api/sets/{setlist_id}/export
POST   /api/sets/{setlist_id}/tracks
DELETE /api/sets/{setlist_id}/tracks/{position}
POST   /api/sets/{setlist_id}/tracks/{position}/move
POST   /api/sets/{setlist_id}/tracks/{position}/replace
POST   /api/sets/{setlist_id}/alternatives
```

### Generation

Generation is always the async job: `POST /api/sets/generate-async` returns
`200` with `{status, phase, using_ai}` immediately — **not `202`** — and the UI polls
`GET /api/sets/generate-status` for `phase`, `setlist_id` and `error`. A second
start while one runs is `409 set_generation_in_progress` — never folded into the
running job, which may be using a different engine.

`use_ai` decides the engine: `true` = AI curation (intent compilation from the free
`prompt`, mood-fit, anchor hints, narrative), `false` = purely deterministic with no
LLM call, absent/`null` = auto, meaning AI runs only if an LLM is configured and
`prompt` is non-empty. `409 ai_not_configured` if `use_ai=true` without an API key.
There is no technical/creative `mode`.

**The deterministic two-phase generator is the only thing that sequences tracks.**
The AI never orders or picks the tracklist, and any AI call that fails degrades
silently to the deterministic default with a warning — never a 4xx/5xx.

`owned_only` (default `true`) generates from owned tracks only. The flag persists on
the saved set and the editor enforces it: `alternatives` excludes leads from the
pool, and **both** the insert (`POST .../tracks`) and the `replace` refuse a track
with no local file, with `422`.

Track `rating` feeds a small deterministic tie-break into the generator's scoring
(2.0 per level, max 6.0): a higher vote nudges a track ahead of an equally
compatible one but never outweighs actual musical compatibility. It is
deterministic-engine input only and is never shown to the AI stage.

### What the saved set carries

- `generated_by`: `algorithmic` when no AI contribution reached the set,
  `algorithmic+ai_curation` when at least one of intent/mood-fit/anchors/narrative
  was used.
- `curation` (`{}` when no curation ran): `intent_summary` (how the request was
  understood), `compiled` (the request fields the AI filled in — only fields the
  user left unset are ever compiled; `owned_only` and `sources` never are),
  `warnings` (AI-degradation messages).
- `validation` (`{}` for a purely deterministic set): `warnings`, and
  `missing_library_suggestions` — 0-3 strings from the narrative call describing
  what kind of track the library is missing, never a track id or invented title.
- `SetlistTrackOut.mood_tags`: up to 3 short tags from the mood-fit judgement, empty
  when curation did not run. Transient per generation, never written back onto
  `Track`.
- `mixing_overview` and the per-track `mix_tip`, `transition_class`,
  `transition_score`, `risk_level` are all deterministic.

### Editing

`POST .../tracks` inserts a track (`position` optional, appends when absent);
`DELETE .../tracks/{position}` removes one; `.../tracks/{position}/move` takes
either `direction` (`up`/`down`, one step) or `to` (1-based absolute, for
drag-and-drop) — exactly one of the two; `.../tracks/{position}/replace` swaps in a
different `track_id`. All four return the whole updated setlist. Edit failures come
back as `set_edit_error` with `404`, `409` or `422` depending on the cause.

`POST /api/sets/{setlist_id}/alternatives` proposes replacements for one position:
`mode` is `safer` | `softer` | `harder` | `same_artist` | `surprising`, `limit`
1-10 (default 5). Each alternative carries the transition score against both
neighbours.

`PATCH /api/sets/{setlist_id}` renames; `DELETE` returns `204`.

### Export

`POST /api/sets/{setlist_id}/export?format=` — `text` (default) | `csv` |
`markdown` | `m3u8`. CSV includes `local_path` (empty for tracks without a file).
`m3u8` is importable in Rekordbox and lists absolute local paths; tracks without a
local file are excluded and their count noted in a leading comment. To export to
Spotify instead, use `POST /api/spotify/create-playlist`.

## Transitions

```text
GET /api/transitions/{track_id}
```

Returns the tracks **compatible** with the given one (`limit`, default 20, max 100;
optional `lens`). There is no before/after split: both directions are scored and the
better one is kept, so a track that works well *before* the anchor does not
disappear for losing a few energy points in the other direction.

Each candidate carries a technical score and a deterministic classification:
`technically_safe` | `creative_risk` | `good_reset`. `lens` takes one of those three
and ranks within that class, so deliberate resets and creative risks surface instead
of staying buried under the safe picks; an unrecognized `lens` is ignored rather
than rejected.

## BPM and key

Two deterministic sources, one precedence rule. Every value stores its provenance in
`bpm_source`/`key_source`, and the ranking is:

```text
manual > rekordbox > cratory
```

`manual` is a hand-entered `PATCH /api/tracks/{id}`, `rekordbox` is the XML import,
`cratory` is the in-app Essentia analysis. Cratory never asks an AI or a streaming
provider for BPM or key. `energy` is derived from BPM plus genre and recomputed
whenever BPM changes.

### Rekordbox import

```text
GET  /api/rekordbox/pending
POST /api/rekordbox/import
```

`GET /api/rekordbox/pending` → `{pending}`: owned tracks still missing BPM or
Camelot key.

`POST /api/rekordbox/import` takes the XML exported from Rekordbox
(`File > Export Collection in xml format`) as multipart `file`. For each track in
the XML it looks for the matching owned `Track` in this order: NFC-normalized path →
`audio_hash` fallback (gated on the basename) → exact artist+title, compared
lowercased. There is no fuzzy matching: a track whose artist or title differs by
more than case will not match on that last level.

By default the import **fills empty values and reclaims values currently sourced
from the in-app analysis (`cratory`), but never overwrites `manual`**. With
`?overwrite=true` the Rekordbox re-analysis wins over every existing value whatever
its source. In both modes a value absent from the XML never clears the one already
in the library. Every write marks the source `rekordbox`. `energy` is recomputed for
**every matched track**, not only the ones whose BPM changed — it is only the
`energy_set` counter that is conditional on the value actually moving.

Response `{in_file, matched, unmatched, bpm_set, key_set, energy_set}`, where the
`_set` counters count only values that actually changed. `400 rekordbox_empty_file`
on an empty upload, `400 rekordbox_import_failed` on invalid or unsafe XML.

### In-app analysis

```text
GET  /api/analysis/overview
POST /api/analysis/start
GET  /api/analysis/status
GET  /api/analysis/divergences
POST /api/analysis/apply
POST /api/analysis/dismiss
```

Deterministic analysis of owned tracks through a local Essentia adapter — the
alternative to the Rekordbox import for tracks not yet analyzed in Rekordbox.

**The job never writes the canonical fields directly.** It only writes
`analysis_bpm`/`analysis_camelot`/`analyzed_at`/`analysis_error`; the explicit apply
step is the only bridge to `bpm`/`camelot_key`, and it sets the source to `cratory`.
The one shortcut: during the run, a value is auto-applied where the canonical field
is empty, since no conflict is possible there.

`GET /api/analysis/overview` → `owned`, `ready_for_set`, `missing_bpm`,
`missing_key`, `bpm_by_source`/`key_by_source` (counts per `manual`/`rekordbox`/
`cratory`), `analyzed`, `divergent`, `rekordbox_pending`.

`POST /api/analysis/start` (`202`) — body `{scope: "missing"|"all", track_ids?}`.
`missing` (default) takes only owned tracks without BPM or key; `all`, or an explicit
`track_ids` list, re-analyzes regardless of current values.
`503 analysis_engine_unavailable` if Essentia is not installed,
`409 analysis_already_running` otherwise. Per-track decode failures are recorded as
`analysis_error="analysis_decode_failed"` without stopping the batch, and the commit
is per track so progress survives an interruption.

`GET /api/analysis/status` → `status` (`idle|running|done|error`), `processed`,
`total`, `analyzed`, `failed`, `applied`, `current_label`, `error`, timestamps.

`GET /api/analysis/divergences` lists owned tracks where the analysis disagrees with
the canonical value: `track_id`, artist/title, `bpm`, `bpm_source`, `analysis_bpm`,
`bpm_delta`, `camelot_key`, `key_source`, `analysis_camelot`, `key_compatibility`
(`same|compatible|weak|unknown`, the same Camelot-wheel rule as transitions).
Dismissed divergences are excluded.

`POST /api/analysis/apply` copies `analysis_*` into the canonical fields for a
selection. Body `{track_ids?, mode?: "divergent"|"all", force?}`: explicit
`track_ids` or `mode="divergent"` apply only the picked or divergent rows;
`mode="all"` rewrites every analyzed track regardless of source — **including
`manual`** — and therefore requires `force=true`. `422 analysis_force_required`
without it, `422 analysis_apply_empty` if neither `track_ids` nor `mode` is given.
Response `{applied, skipped}`.

`POST /api/analysis/dismiss` marks divergences as seen-and-ignored: body
`{track_ids}` snapshots each track's current values on BOTH sides — the
analyzed `analysis_bpm`/`analysis_camelot` and the canonical `bpm`/
`camelot_key` at the moment of dismissal. A dismissed divergence disappears
from `/divergences`, from the overview `divergent` count and from
`mode="divergent"` apply; it reappears when EITHER side later stops matching
its snapshot (BPM compared at 1 decimal, key exact) — a new analysis run with
a different result, but also a manual edit or a Rekordbox import that changes
the canonical `bpm`/`camelot_key` after the dismissal.
`mode="all"` + `force` still rewrites dismissed tracks. `422
analysis_dismiss_empty` on an empty list. Response `{dismissed}`.

## Discovery

```text
GET  /api/discovery/genres
POST /api/discovery/dig
GET  /api/discovery/release
GET  /api/discovery/preview
POST /api/discovery/add
POST /api/discovery/save-for-later
```

The dig ("Scava") does crate digging by genre or label and returns releases and
tracks not yet owned. Two sources sit behind a shared `DigSource` protocol —
**Discogs** (`source="discogs"`, the default) and **Bandcamp**
(`source="bandcamp"`) — chosen per request.

### How depth works

The engine reasons in **items**, never in pages. It asks the source to probe the
seed (how tall the pile is, how far this source reaches into it), derives a window
`(offset, count)` from `depth` (`0.0`-`1.0`), and lets the source translate that
window into its own pagination — page numbers for Discogs, a sequential cursor walk
for Bandcamp, which cannot jump to a page. `depth` picks **where in the pile to
fetch from**: `0.0` is the seed's classics, `1.0` is the bottom of what the source
reaches. Taste always ranks inside that window, never across it.

Discogs sorts the whole pile by demand (`sort=want` desc) before windowing. Bandcamp
has no demand signal at all and sorts by its `top` slice instead.

The response reports, source-neutral, in items:

- `pile_total` — the pile's real height for that seed; `0` means the source does not
  know the seed at all (a dead seed, with `seed_resolution: null`).
- `pile_reach` — how many of those items this source can actually reach. Discogs:
  10,000, a hard wall (page 101 is a 404). Bandcamp: 3,000, a cost choice rather
  than a provider limit.

`pile_reach <= 300` means the window already covers everything reachable and `depth`
has no effect — the UI disables the control instead of showing an inert slider.
`pile_total > pile_reach` means only part of the pile is visible. A Bandcamp label
seed always has `pile_reach == pile_total`: the whole discography is fetched once by
the probe and the window just slices it.

`seed_resolution` is `style` | `genre` | `label` | `tag` | `discography` | `null`.
`tag` and `discography` are the Bandcamp forms. `genre` means a Discogs seed fell
back from a fine-grained style to a top-level genre — one of ~15 huge shelves like
`Electronic` — where only the most-wanted releases are reachable through pagination;
the UI says so rather than letting a shelf pass for a fine dig.

`GET /api/discovery/genres` returns the seed vocabulary: `library` (genres already
in the library) and `styles` (a hand-curated Discogs style list). Both sources share
it; Bandcamp normalizes each entry into a tag (lowercase, runs of non-alphanumeric
characters collapsed to one hyphen) with one hand-kept alias
(`Drum n Bass` → `drum-and-bass`, because the naive normalization lands on a real
but wrong tag).

### Leads

Each lead exposes `source`, `source_id`, `source_url` and `stream_url`. `source_id`
is a plain string: the Discogs release id, or `"<band_id>:<item_id>"` for Bandcamp.
`source_url` is `null` for Bandcamp leads from a label seed — the discography
endpoint that produces them carries no page URL, though the release detail below can
still resolve one. `stream_url` is populated only by Bandcamp genre-seed leads,
which hand back a real per-track mp3 stream inside the dig result; Discogs leads
never set it and resolve a preview the usual way.

On Bandcamp leads `have`/`want` stay `0` and `style` is always `null` — neither
concept exists in Bandcamp's list results — so the reason codes reading those fields
simply never fire.

Ranking is taste-only and not optional: graduated familiarity on the artist, owned
label, and style affinity with your genres. Novelty, demand and recency are not
score inputs; demand only decides which window `depth` reads on Discogs. The taste
profile and the dedup are always built from the **whole library**. Each lead carries
deterministic `reasons[]` (`{code, data}` — `rare_wanted`, `deep_cut`,
`label_followed`, `artist_collected`, `style_match`, `recent`) which the UI renders
as chips; they are display badges, not the score's factors.

The response is never truncated: the window's ~300 raw items are the natural limit.
How many to show is a client-side lens.

Expect one dig to cost 4-5 Discogs requests, or 1-6 Bandcamp requests depending on
`depth` — up to roughly 20s at `depth=1.0` on a deep pile. Provider failures are an
explicit `502 discovery_provider_error`, never a silent empty result: the caller
must be able to tell "nothing there" from "no answer".

### Release detail and preview

`GET /api/discovery/release?source=&id=` expands a lead into its real tracklist,
fetched lazily when the release is opened: `?source=discogs&id=<int>` or
`?source=bandcamp&id=<band_id>:<item_id>`. **Only integers cross this boundary** —
no URL is taken from the client and followed by the backend, so there is no SSRF
surface and no host allowlist to keep correct. A malformed id is
`400 discovery_bad_id`. Each row carries position, title, duration and — Bandcamp
only — `stream_url`. `videos` (YouTube videos Discogs associates with the release)
is populated for Discogs only. **This endpoint is not cached**: reopening the same
release hits the provider again.

`GET /api/discovery/preview?artist=&title=&discogs_id=&level=` resolves an
**ephemeral** audio preview for a lead that has no `stream_url` of its own, so it
can be judged before being acquired. `level` is `release` or `track` (default
`track`). Response `{kind: "itunes"|"youtube"|"none", audio_url, youtube_video_id,
source_url, matched_title}`: iTunes Search is primary (30s clip), with the YouTube
video Discogs associates with the release as fallback. Provider errors resolve to
`kind: "none"` with `200` — a missing preview is not an error. Nothing is persisted.
Bandcamp genre-seed leads skip this endpoint entirely.

The Discogs release payloads fetched by the fallback **are** cached in memory for 10
minutes, so previewing several tracks off one card costs a single provider call.
That cache is local to this endpoint and does not serve
`GET /api/discovery/release`.

### Acquiring

`POST /api/discovery/add` imports a candidate into the library, idempotently. It
does not write to Spotify. `POST /api/discovery/save-for-later` does the same import
and files the track in the system "Discovery" playlist. Neither downloads anything —
for that, see the downloads endpoints.

## Downloads

```text
GET    /api/downloads/status
GET    /api/downloads/pending
POST   /api/downloads/retry-pending
DELETE /api/downloads/pending/{track_id}
GET    /api/downloads/auto-link
POST   /api/downloads/candidates
POST   /api/downloads/search
POST   /api/downloads/playlist/{playlist_id}
POST   /api/downloads/track
POST   /api/downloads/track/auto
POST   /api/downloads/track/soundcloud
GET    /api/downloads/review/{track_id}
POST   /api/downloads/keep-review
POST   /api/downloads/discard-review
```

File acquisition through the headless Soulseek daemon slskd, fully deterministic
(zero AI). A successful download links the file to the **existing** `Track`
(`has_local_file`/`local_path`/`local_format`/`local_bitrate`) rather than creating
a new one.

`SLSKD_URL` and `SLSKD_DOWNLOAD_DIR` must both be configured, or the six
Soulseek-backed routes — `candidates`, `search`, `playlist/{id}`, `track`,
`track/auto`, `retry-pending` — answer `409 slskd_not_configured`.
`track/soundcloud` does not touch slskd and has its own preconditions (see
below). Available regardless:
`GET /status` (with `available: false`), `GET /pending`,
`DELETE /pending/{track_id}`, `GET /auto-link` and the review endpoints.

**One download job at a time**, shared by the five routes that start one —
`playlist/{id}`, `track`, `track/auto`, `track/soundcloud`, `retry-pending` (a
different set from the slskd-gated five above, which includes `candidates` and
excludes `track/soundcloud`). A second start is `409 download_already_running`. An
error on one track does not stop the others.
`GET /api/downloads/status` returns `available` plus the job state (`status`,
`processed`, `total`, `downloaded`, `needs_review`, `not_found`, `failed`,
`playlist_id`, `items[]`, `current_label`, `error`, timestamps).

### Starting a download

`POST /api/downloads/candidates` searches slskd and returns candidates ranked
deterministically on quality, name adherence and availability. Request `artist`,
`title`, optional `duration_seconds` (the duration expected from the `Track`, which
rewards the right version). Each candidate has `username`, `filename`, `size`,
`bitrate`, `length`, `format`, `name_score`, `quality_tier`, `confidence`. Provider
failure is `502 slskd_error`.

`POST /api/downloads/search` is the manual-search counterpart used by the wishlist's
per-track search modal: one slskd search with the literal query the user typed — no
variant cascade (that stays exclusive to auto-pick) and no confidence threshold (the
ranking guides sort order and badges, it never excludes a result). Body
`{query, track_id?}`. Without `track_id` it returns slskd's raw results unfiltered,
non-audio files included; with it, results pass through `rank_candidates`
(`QualityPreference(min_bitrate=1)`), which drops files with an unrecognized
extension and lossy files reporting bitrate 0, and each surviving result also
carries `score`/`confidence` (ranked against the Track's artist/title/expected
duration) plus `auto_ok`, true only for the results the auto-pick would have
accepted — both of its bars, the confidence floor and the default
`QualityPreference()` quality tier, not the relaxed one used to rank here; the
response's `variants` list the same queries the auto-pick
cascade would try, as clickable suggestions. Errors: `409 slskd_not_configured`,
`404 track_not_found`, `502 slskd_error`.

`POST /api/downloads/playlist/{playlist_id}` (`202`) runs the whole playlist: for
each track without a local file it searches, auto-picks the best candidate above a
confidence threshold, and downloads.

`POST /api/downloads/track` (`202`) downloads one track with a candidate the user
picked explicitly (body `track_id` + `candidate`, the same shape `candidates`
returned).

`POST /api/downloads/track/auto` (`202`) downloads one track with no candidate
chosen — same search cascade and auto-pick as the playlist job. Body `{track_id}`.

`POST /api/downloads/track/soundcloud` (`202`) is the non-Soulseek exception: it
downloads a single SoundCloud track's audio through yt-dlp, extracts it to MP3 into
the same `SLSKD_DOWNLOAD_DIR`, and links it to the `Track`. It reuses the same job
and progress bar. The track must have `platform == "soundcloud"` and a `url`
(`422 not_a_soundcloud_track`). Errors: `409 ytdlp_unavailable`,
`409 ffmpeg_unavailable`, `409 download_dir_not_configured`,
`409 download_already_running`, `404 track_not_found`.

### The "to sort out" queue

Failed and doubtful downloads persist their outcome on the `Track`
(`needs_review` / `not_found` / `failed`), so they survive job, session and restart.

`GET /api/downloads/pending` lists them (not owned, not discarded).
`POST /api/downloads/retry-pending` (`202`) retries the auto-pick across all of
them. `DELETE /api/downloads/pending/{track_id}` is the "ignore" action: it clears
the outcome and takes the track out of the archive.

`GET /api/downloads/auto-link` is read-only: for every pending track it returns the
best matching local file it can find, `{track_id, label, artist, title, hit}` with
`hit: null` when there is no match. It links nothing — confirmation goes through
`POST /api/tracks/{track_id}/link-file`.

`GET /api/downloads/review/{track_id}` returns the expected-vs-downloaded comparison
behind a `needs_review` outcome (typically a duration mismatch).
`POST /api/downloads/keep-review` accepts the downloaded file — links it and clears
the outcome (`409 download_review_error` if the file is not there any more) — and
`POST /api/downloads/discard-review` deletes it from the inbox and unlinks the
track. Both take `{track_id}` and return the updated track.

## Soulseek connection

```text
GET  /api/slskd/status
POST /api/slskd/connect
POST /api/slskd/disconnect
```

Logging the slskd daemon into the Soulseek network, driven from the Settings page.
**The Soulseek account credentials never pass through Cratory**: they live in
slskd's own config (`slskd.yml` or `SLSKD_SLSK_USERNAME`/`SLSKD_SLSK_PASSWORD`),
because slskd's REST API exposes no clean way to set them. Cratory reads the
connection state and drives connect/disconnect using the `SLSKD_API_KEY` it already
uses.

`GET /api/slskd/status` returns `configured` (`SLSKD_URL` is set, so we know where
the daemon is), `reachable` (it answered), `is_connected`, `is_logged_in`,
`is_connecting`, `is_transitioning`, `state` (raw slskd string), `username` (the
Soulseek account configured in slskd; the password stays masked) and `web_url`.
`web_url` is populated as soon as `configured`, **even when the daemon is
unreachable** — the wishlist links to it precisely when a Cratory download fails.
The connection flags are only meaningful when `reachable`.

Both degradations return `200` so the UI can poll without treating them as hard
errors: no `SLSKD_URL` → `configured: false`; daemon down → `configured: true,
reachable: false`.

`POST /api/slskd/connect` and `POST /api/slskd/disconnect` return the refreshed
status. slskd stays in transition for a few seconds afterwards (Connecting →
LoggingIn → LoggedIn), so poll `status` until `is_transitioning` is false.
`409 slskd_not_configured`, `502 slskd_error`.

## Spotify

```text
GET  /api/spotify/status
GET  /api/spotify/login
GET  /api/spotify/callback
POST /api/spotify/create-playlist
```

Spotify supplies track identity, editorial metadata, covers, duration, ISRC, URLs
and playlists. It is never a source of BPM or key.

`GET /api/spotify/status` → `configured`, `user_connected`, and `redirect_uri`,
which is shown in the UI because it must match the Spotify dashboard entry exactly.

`GET /api/spotify/login` redirects into the OAuth authorize flow.
`GET /api/spotify/callback` is the redirect target: it validates the one-shot CSRF
state (10-minute TTL), exchanges the code, and always redirects back to the
frontend's `/settings` with `?spotify=connected` or `?spotify=error&detail=…`. It
never returns JSON, and never an error status.

`POST /api/spotify/create-playlist` (`{setlist_id, name?}`) creates a Spotify
playlist from a saved set; tracks without a `spotify_id` are skipped. Response
`{playlist_url, tracks_added, tracks_skipped}`. `404 set_not_found`,
`422 set_no_spotify_tracks` when none of the tracks are on Spotify.

Spotify failures map to `409 spotify_not_configured`, `401 spotify_not_connected`
and `502 spotify_error` on the routes that raise at all — the playlist import and
sync routes, and `create-playlist`. Two do not raise:

- `GET /api/spotify/callback` always redirects, never returning an error status.
- `GET /api/spotify/status` and `GET /api/services/status` swallow the failure into
  `user_connected: false` (`connected: false` in the aggregate) rather than raising,
  so a UI polling them does not have to treat a dead session as a hard error.

## SoundCloud

```text
GET  /api/soundcloud/status
PUT  /api/soundcloud/config
POST /api/soundcloud/import
GET  /api/soundcloud/likes/preview
POST /api/soundcloud/import/likes
```

Import through yt-dlp: metadata only, no ISRC (SoundCloud does not expose one), so
dedup falls back to `platform_track_id`. Audio is downloaded only by the explicit
per-track route in the downloads section.

`GET /api/soundcloud/status` → `available` (yt-dlp importable), `ytdlp_version` and
the configured `username`. `PUT /api/soundcloud/config` saves the username, stripping
a leading `@` (`422 soundcloud_username_invalid` if empty). The two likes endpoints
answer `409 soundcloud_username_missing` without one.

`POST /api/soundcloud/import` (`202`) imports a public playlist or a secret link
from `{url}` as leads. A `/likes` URL is refused
(`422 soundcloud_likes_url_not_supported`) — likes only go through the selective
flow. Non-`soundcloud.com` or non-http(s) URLs are `422 soundcloud_invalid_url` (an
anti-SSRF guard); yt-dlp failures are `502 soundcloud_error`.

`GET /api/soundcloud/likes/preview?limit=` fetches the configured user's likes and
marks each with `already_imported`, without importing anything. Without `limit` it
returns all of them. The preview uses flat extraction, which is fast but carries no
uploader or duration.

`POST /api/soundcloud/import/likes` (`202`) imports only the selected likes
(`{track_ids, limit}`) into the system "SoundCloud Likes" playlist, additive, never
pruning. It is stateless — the job re-fetches the likes and filters by id — and
re-fetches each selected track in full mode to get the real uploader, duration and
artwork (roughly 1s each, which is why it is a job). If a full fetch fails it falls
back to the flat entry: a poor lead beats a lost one.

## Labels

```text
GET /api/labels
```

Deterministic overview of the labels in the library, with normalized names and
variants merged. Each entry has `label`, `track_count`, `artist_count`, `artists`
(the full list, for the by-artist filter), `genres` (capped) and the year range. The
label value comes from the file tag, read at indexing time and written by the
Organize section.

## Shazam — mix identification

```text
GET    /api/shazam/status
POST   /api/shazam/identify
GET    /api/shazam/identify-status
GET    /api/shazam/sets
GET    /api/shazam/sets/{dj_set_id}
POST   /api/shazam/sets/{dj_set_id}/import-playlist
DELETE /api/shazam/sets/{dj_set_id}
```

Identifies the tracklist of an external mix (a SoundCloud/Mixcloud/YouTube URL) by
fingerprinting. This is the only audio fingerprinting of *third-party* audio in the
project — it identifies someone else's mix, not the library. The job downloads the
audio temporarily, samples segments, recognizes them and persists `DjSet` /
`DjSetTrack`. **Identified tracks do not enter the main library**; they stay
attached to the set until explicitly promoted.

`GET /api/shazam/status` → `{available}`: requires `ffmpeg`, `yt-dlp` and
`shazamio` on the backend. `POST /api/shazam/identify` `{url}` starts the job and
returns the job state plus `dj_set_id` and `cached`. **The same URL is never
re-analyzed**: if it was already identified successfully, `cached: true` comes back
with the existing set and nothing runs. A previous failed attempt is cleaned up and
retried. `409 shazam_deps_missing` when a dependency is absent.

Sampling is paced and resilient: at most 200 segments per mix (a ~39s step on a
two-hour set, so most real tracks collect two or more agreeing samples), recognizer
calls spaced and retried with backoff before counting as errors, and runs of the
same track reappearing within 240s merged into one. Tracks left with a single sample
get confirmation attempts nearby, sharing a per-mix budget of 50 extra calls:
refuted singles are dropped as transition noise, never-verified ones stay listed as
uncertain. Read `DjSetTrack.confidence` accordingly — `90` means two or more
agreeing samples, `45` a single unverified one. If the recognizer stops responding
the analysis is saved as **partial**, with `DjSet.aborted_at_seconds` recording
where it stopped.

`GET /api/shazam/sets/{dj_set_id}` returns the set with, per track, a deterministic
cross-match against the library (ISRC first, then exact case-insensitive
artist+title): `library_track_id` and `library_status` (`owned` | `in_library` |
`null`).

`POST /api/shazam/sets/{dj_set_id}/import-playlist` (`201`) promotes the identified
tracks to leads in a playlist with `source=shazam` (dedup on artist+title, ISRC kept
for the disk-first re-link). Repeating it is blocked: the set stores
`imported_playlist_id` and answers `409 dj_set_already_imported`. Deleting that
playlist clears the reference and re-enables the import.

`DELETE /api/shazam/sets/{dj_set_id}` returns `204`.

## Local files and the native picker

```text
GET  /api/files/search
GET  /api/files/pick/availability
POST /api/files/pick
```

`GET /api/files/search?q=` searches audio files by name across `LIBRARY_ROOT` and
`SLSKD_DOWNLOAD_DIR` — an AND match of the terms, case-insensitive, max 50 results,
and an empty list for a query under 2 characters. Each hit is
`{path, name, format, size, source}` with `source` = `library` | `downloads`.

`GET /api/files/pick/availability` → `{available}`: the native path picker exists
only on macOS with `osascript` in the PATH.

`POST /api/files/pick` `{kind: "folder"|"file", start?, prompt?}` opens the Finder
dialog **on the backend machine** and returns `{path}`, or `path: null` if the user
cancels or the dialog times out (300s). `409 picker_unavailable` off macOS,
`409 picker_busy` if a dialog is already open.

## Services, settings and AI

```text
GET   /api/services/status
GET   /api/ai/status
GET   /api/settings/language
PUT   /api/settings/language
GET   /api/settings/config
PATCH /api/settings/config
PUT   /api/settings/share-library
```

`GET /api/services/status` is the single aggregate state of **all** external
integrations, in order: `spotify`, `anthropic`, `discogs`, `musicbrainz`,
`acoustid`, `slskd`, `soundcloud`. Field semantics are uniform across entries:

- `configured` (bool): the **required** configuration is present — intrinsically
  `true` for services that work without a key, such as Discogs and MusicBrainz.
- `connected` (bool | null): live session state where the concept exists (Spotify
  OAuth), `null` where it does not. For slskd the live state comes from
  `GET /api/slskd/status`; this endpoint makes no HTTP call to the daemon.
- `env` / `optional_env` (lists): required and optional variables. The UI renders
  optional ones as "recommended" instead of making the service look unconfigured.
- `optional_ok` (bool | null): optional variables present / absent, `null` when the
  service has none.
- plus `key`, `name`, `category`, `detail`, `docs` for display.

`GET /api/ai/status` → `{configured, model}`, `model` being `null` when no key is
set. One key (`ANTHROPIC_API_KEY`) covers all AI in the app.

Settings persist in `AppState` — no dedicated table, this is a single-user app — and
are read through a cache in `core/runtime_settings`.

`GET`/`PUT /api/settings/language` — `{"language": "it"|"en"}`, default `"it"`,
`422` on anything else.

`GET /api/settings/config` returns the editable configuration that **overrides
`backend/.env` at runtime, with no backend restart**. The editable fields are
`library_root`, `archive_root`, `slskd_download_dir`, `slskd_url` and
`slskd_config_path`, each as `{value, source: "env"|"db", valid, detail}` — `source`
tells you whether the effective value is a DB override or the `.env` default. Plus
`share_library` (bool) and `warning` (a soft note). Overrides live in `AppState`
under `cfg.*`; read sites call `runtime_settings.<field>()`, so a change takes
effect on the next scan, slskd client or file search.

`PATCH /api/settings/config` accepts any subset of those fields: a non-empty value
sets an override, an empty string clears it back to `.env`. **Everything is
validated before anything is persisted** — no partial state. A directory must exist
and be a directory; `slskd_url` must be `http(s)://`; `slskd_config_path` must be an
existing writable file. Failures are `422 invalid_setting` with `params.field` and
`params.detail`. If `share_library` is on and `library_root` changed, the share is
re-applied best-effort and a soft failure comes back in `warning` rather than as an
error.

`PUT /api/settings/share-library` `{"enabled": bool}` toggles library sharing on
Soulseek. slskd cannot change shares through its API at runtime, so Cratory edits
`shares.directories` in slskd's own YAML — a round-trip that preserves comments and
permissions, with a `.bak` backup — and forces a rescan. Response
`{share_library, applied_to_yaml, rescan}`, with `rescan: false` when the daemon is
down (the share then applies at its next start). `409 share_precondition` when the
slskd config is missing or not writable, or when enabling without a `library_root`.

## Organize

The Organize section (`/organize` in the UI) is the library's file-level workshop
and **the single writer of textual tags**. Its whole HTTP surface is under
`/api/organize/*`. It shares the core `AudioFile` model and the scan job with the
rest of the app.

The working cycle is: **scan** the disk → **analyze** into issues and duplicate
groups → accept or dismiss issues → build a **plan** of concrete operations →
**apply** it → keep it in **history**, with undo.

### Scan and analyze

```text
POST /api/organize/scan
GET  /api/organize/scan/status
POST /api/organize/analyze
```

`POST /api/organize/scan` starts the single scan job. Optional body
`{locations: ["inbox"|"library"]}` restricts the walk; absent means both configured
roots. `409 apply_running` while an apply is in progress. `GET .../scan/status` is
the same job state described under `GET /api/library/index/status` — a scan limited
to the inbox leaves `result.linking` at `null`.

`POST /api/organize/analyze` recomputes issues and duplicate groups from the data
already in the DB, with no filesystem walk. Synchronous; returns the analyze summary
(`issues_total`, `issues_by_severity`, `dup_groups`, `dup_files`).

### Reading the library

```text
GET /api/organize/library/stats
GET /api/organize/library/facets
GET /api/organize/files
GET /api/organize/files/{file_id}/thumb
```

`GET /api/organize/library/stats` → `files_total` (present files), `by_ext`,
`issues_by_severity` (open issues), `dup_groups` (not dismissed), `sources` (how
many of the two configured folders are set).

`GET /api/organize/library/facets` → the distinct values among present files for
`genre`, `artist`, `album`, `label`, `ext`, `year`, for the per-tag filters.

`GET /api/organize/files` lists indexed audio files. `status` defaults to `present`
and accepts a comma-separated list (`present,missing`) — the one case a caller
cannot know the status in advance is the cross-link from a track detail page, where
the file may have vanished from disk since the last scan. Other filters: `location`
(`inbox`|`library`), `has_issues`, `q` (case-insensitive substring over path, artist
and title, with LIKE wildcards escaped), exact `genre`/`artist`/`album`/`label`/
`ext`/`year`, plus `sort` (`path|artist|title|ext|bitrate|duration`), `dir`, `limit`
(default 500, max 5000) and `offset`. Each row carries `issue_count`,
`worst_severity`, `in_dup_group` and `cover_source` (`embedded` | `provider` |
`null`), and `track_id` — the `Track` this file belongs to, which is how the FILES
page links a row to the track detail page.

`GET /api/organize/files/{file_id}/thumb` serves the file's thumbnail: the embedded
artwork if there is one, otherwise a provider-proposed cover already in cache. It is
`ETag`-validated on the audio file's mtime (plus the cached cover's, when the
artwork is not embedded), so an apply that rewrites tags also invalidates the
browser copy. `404 thumb_missing` when there is nothing — the frontend then draws a
placeholder and does not retry.

### Editing tags

```text
POST /api/organize/files/{file_id}/tags
```

**The single writer of text tags on a file.** Partial update: only fields present in
the body are touched, and an empty string clears a tag. Editable fields are
`artist`, `title`, `album`, `album_artist`, `genre`, `year`, `label`, `track_no`,
`comment`. This is also how `genre`/`album`/`label`/`year` get edited for an owned
track — the frontend calls it against the track's `primary_file_id`, not a track-side
PATCH. Returns the updated file row.

**This is the one Organize write that does not wait for an apply.** It writes the
tags to disk immediately, and journals itself as a synthetic `Plan` +
`UndoJournal` RETAG — so a manual edit shows up in `GET /api/organize/history` and
is undone through `POST /api/organize/history/{plan_id}/undo` like any other run.
Fields already equal to the stored value are ignored, and an edit where nothing
differs is a no-op that creates no run.

**The DB is aligned to what actually landed on disk, not to what you sent.** After
writing, the file is re-read: some formats silently drop some fields (`comment` on
mp3 is the standard case), and the row keeps the on-disk value for those. If nothing
at all landed, the run is deleted rather than left in history as a misleading no-op
undo.

Open issues on the fields just edited are auto-accepted, with their suggestion
rewritten to `source: "manual"` — a hand correction outranks any provider or AI
proposal.

Side effect on the linked `Track`: when `genre` is among the fields that actually
landed and the file is linked, `tracks.genre` mirrors the new tag and the track's
`energy` is recomputed. **Clearing the genre does not clear the mirror** — the rule
never overwrites with an empty value, so the last known genre survives on the
`Track` row. `album`/`label`/`year` and `artist`/`title` never touch `Track` this
way.

Errors: `404 file_not_found`; `400 field_not_editable` (a field outside the list
above, with `params.fields`); `400 value_invalid` (`year`/`track_no` not a
non-negative number, with `params.field`/`params.reason`); `409 file_not_writable`
(the file is missing, has a scan error, or its tags cannot be read);
`500 tag_write_failed` (the write failed — the run is rolled back);
`500 tag_verify_failed` (the disk changed but could not be re-read, so the DB is
left unaligned until the next scan reconciles it).

### Issues

```text
GET  /api/organize/issues
POST /api/organize/issues/{issue_id}/status
POST /api/organize/issues/{issue_id}/fix
POST /api/organize/issues/bulk
GET  /api/organize/issues/cover-thumb/{file_id}
POST /api/organize/issues/detect-ratings
POST /api/organize/issues/ai-suggest
POST /api/organize/issues/provider-suggest
POST /api/organize/issues/provider-rescan
GET  /api/organize/issues/provider-rescan/status
POST /api/organize/issues/provider-override/accept-strong
POST /api/organize/issues/integrity-check
GET  /api/organize/issues/integrity-check/status
```

An issue is one detected problem on one file, with a `type`, a `field`, a
`severity`, and possibly a `suggested_fix_json` (`{field, action, to, source?,
confidence?}`). Its `status` is `open`, `accepted` or `dismissed` — **only
`accepted` issues become plan operations**, so accepting is the act that stages a
change, and nothing on this path reaches the disk until the apply. (The one write
that bypasses the plan entirely is the manual tag edit above.)

`GET /api/organize/issues` filters on `severity`, `type`, `status`, `location`, `q`
(path/artist/title) and `only_new` (files seen in exactly one scan). Each row
includes the file path, the current value of the field and `is_new`.

`POST .../{issue_id}/status` sets the status. Accepting an issue with no suggested
fix is refused (`400 issue_not_autofixable`) — there would be nothing to apply.

`POST .../{issue_id}/fix` accepts a hand-typed `value` for the issue's field: it
writes the suggestion itself and marks the issue `accepted` in one step. The field
must be one of the editable tag fields (`400 issue_field_not_editable`) and the
value non-empty (`400 issue_value_empty`). Any `source`/`confidence` markers on an
existing suggestion are preserved, so accepting a provider proposal by hand does not
lose its confidence badge.

`POST .../bulk` sets a status across issues matched by `type` and/or `severity`.
Two types are deliberately excluded unless targeted **by type**: `provider_override`
and `genre_review`. Both were paid for in network calls or AI tokens, and "dismiss
all the info-level ones" should not wipe them in a single click. Response
`{updated}`.

`GET .../cover-thumb/{file_id}` serves the provider-proposed cover held in cache,
`404 thumb_missing` when there is none.

`POST .../detect-ratings` scans for files with an embedded star rating and creates
`stray_rating` issues (the fix strips them). Synchronous.

`POST .../ai-suggest` fills in `suggested_fix` for open `missing_required_tag`
issues on `artist`/`title`, by asking the model to read the filename. It only
touches issues with no suggestion yet, and marks what it writes `source: "ai"`.
Returns `{configured, files, suggested, unresolved}` — `configured: false` with
zeroes when no API key is set, rather than an error.

`POST .../provider-suggest` fills suggestions from the metadata providers
(MusicBrainz, then Discogs), **fingerprint-first**: if the file has no MBID and
AcoustID is configured, it fingerprints first so the lookup is an exact match with
`confidence: "high"` instead of a text match. It touches only open issues of type
`missing_required_tag` / `missing_metadata` / `dirty_genre` on the six tag fields,
and only where the suggestion is missing or not already `source: "provider"` — so it
overwrites AI guesses but is idempotent over its own. One lookup per file. With
`covers: true` (the default) it also fetches a cover for files resolved in this pass
that have none, caching it on disk and creating a `missing_cover` issue.
Synchronous. Returns `{configured, acoustid_available, files, suggested, unresolved,
fingerprinted, covers}`.

`POST .../provider-rescan` is the background version, for re-querying providers over
a wider scope: `folder`, `genre`, `fields` (subset of `genre`, `album`, `label`,
`year`, `artist`, `title`; anything else is rejected by validation),
`include_accepted`, `include_dismissed`, `covers`, `only_new`.
`409 scan_or_apply_running`. Poll `GET .../provider-rescan/status`.

`POST .../provider-override/accept-strong` bulk-accepts open `provider_override`
issues whose suggestion carries a strong confidence — the safe subset of "the
provider disagrees with your existing tag". Returns `{updated}`.

`POST .../integrity-check` starts the background file-integrity check (`force` to
re-check files already verified), `409 scan_or_apply_running`; poll
`GET .../integrity-check/status`.

### Duplicates

```text
GET  /api/organize/duplicates
POST /api/organize/duplicates/{group_id}/keeper
POST /api/organize/duplicates/{group_id}/dismiss
```

`GET` lists the duplicate groups with their `match_kind`, the current
`keeper_file_id`, whether the keeper was `keeper_overridden`, whether the group is
`dismissed`, and every member with its path, extension, bitrate, duration and
content hash plus its `action` (`keep` | `remove`).

`POST .../{group_id}/keeper` `{file_id}` overrides the automatically chosen keeper:
that member becomes `keep`, every other becomes `remove`, the group is un-dismissed
and `keeper_overridden` is set. `404 dup_group_not_found`,
`400 dup_file_not_member` if the id is not in the group.

`POST .../{group_id}/dismiss` marks the group dismissed and sets **every** member to
`keep`, so the plan proposes no deletion for it.

### Plan, apply, history

```text
GET  /api/organize/plan
POST /api/organize/plan
POST /api/organize/apply
GET  /api/organize/apply/status
GET  /api/organize/history
POST /api/organize/history/{plan_id}/undo
GET  /api/organize/settings
PUT  /api/organize/settings
```

`POST /api/organize/plan` compiles the current accepted issues, duplicate decisions
and naming templates into a **draft plan**: an ordered list of concrete operations
(`retag`, `cover`, `rename`, `move`, `delete`), each with its `before`/`after`, plus
detected `conflicts` and `stats` (per-kind counts, `space_freed_bytes`,
`n_conflicts`, `n_skipped`, `blocking`). An operation in conflict is marked
`skipped` and is passed over at apply time rather than blocking the plan;
`blocking: true` means every operation is in conflict, so there is nothing to apply.
The plan is a preview — it changes no files.

`GET /api/organize/plan` reads back the current draft, `404 plan_draft_missing` if
there is none.

`POST /api/organize/apply` executes the draft. `409 scan_running` while a scan is in
progress, `400 plan_draft_missing` with no draft. Poll
`GET /api/organize/apply/status`; when it reaches `done`, `result` holds `run_id`,
`applied_ops`, `skipped_ops` and the flags `refused`, `stale` (the plan no longer
matches what is on disk) and `partial` with `failed_op_seq`.

`GET /api/organize/history` lists applied and undone runs, newest first, with
`n_ops` and the run `kind`. `POST /api/organize/history/{plan_id}/undo` reverses one
applied run from its journal, returning `{run_id, reversed_ops, error}`.
`404 run_not_found`; `400 run_not_applied` if the run is not in the `applied` state
(an already-undone run cannot be undone twice).

`GET`/`PUT /api/organize/settings` read and write the two global templates,
`naming_template` and `folder_template`, which the planner uses to derive rename and
move operations. `PUT` accepts either field on its own.

### Fingerprint and AI genre review

```text
POST /api/organize/fingerprint
POST /api/organize/genre-review
GET  /api/organize/genre-review/status
GET  /api/organize/genre-review/preview
```

`POST /api/organize/fingerprint` computes the acoustic identity of files through
AcoustID/Chromaprint and stores the resulting MBID on the file, which is what makes
a later MusicBrainz lookup exact rather than textual. Synchronous. When AcoustID is
not configured, or `fpcalc` is missing, it returns
`{configured: false, identified: 0, below_threshold: 0, not_found: 0, errors: 0,
total: 0}` rather than an error.

`POST /api/organize/genre-review` starts the AI genre review job over a scope
(`folder`, `genre`, `redo` to revisit files already reviewed). Its proposals land as
`genre_review` issues to accept or dismiss like any other. `409
scan_or_apply_running`. With no API key configured it returns the full job-state
shape with `configured: false` instead of erroring, so the client always gets the
declared shape. Poll `GET .../genre-review/status`.

`GET .../genre-review/preview` answers "how much would this cost" before starting:
same `folder`/`genre`/`redo` parameters, returns `{configured, files}` — the number
of candidate files.
