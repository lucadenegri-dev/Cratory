# API

Current REST contracts of the FastAPI backend. All main responses are validated
with Pydantic in `backend/app/schemas.py`. Surface verified against the routers in
`backend/app/routers/`.

Local base:

```text
http://localhost:8000
```

## Health

```text
GET /api/health
```

## Pipeline

```text
GET /api/pipeline
```

Single snapshot for the orientation strip in the dashboard. Response `PipelineOut`:
library counts (`playlists`, `total_tracks`, `missing_key`, `wishlist`,
`archived_count`, `with_local_file`, `analyze_pending`, `ready_for_set`), download
state (`download_active`, `download_pending`) and disk state (`inbox_files` from
`SLSKD_DOWNLOAD_DIR`). `analyze_pending` counts
the owned tracks without BPM or without key, i.e. how many remain to "analyze in
Rekordbox and import" (same number as `GET /api/rekordbox/pending`). `inbox_files` is
`null` when `SLSKD_DOWNLOAD_DIR` is not configured or does not exist (neutral phase,
not an error). Library indexing is no longer a field of this snapshot (the old
`files_on_disk`/`index_mismatch`/`last_index_at` have been removed): it is launched
from the "Index" button in the nav.

## Rekordbox (source of BPM/key)

```text
GET  /api/rekordbox/pending
POST /api/rekordbox/import
```

`GET /api/rekordbox/pending` counts the owned tracks (`has_local_file`) still
without BPM or without Camelot key. Response: `{pending}`.

`POST /api/rekordbox/import` (multipart, `file` field) imports the XML exported from
Rekordbox (`File > Export Collection in xml format`). For each track in the XML it
looks for the matching owned `Track` in this order: NFC-normalized path ->
`audio_hash` fallback (gated on the basename) -> fuzzy artist+title. **Source-aware
default** (`bpm_source`/`key_source`: `manual` > `rekordbox` > `cratory`): it fills
empty `bpm`/`camelot_key` and reclaims values currently sourced from the in-app
analysis (`cratory`), but protects `manual` corrections; with `?overwrite=true` the
Rekordbox re-analysis wins over every existing value regardless of source, but a
value absent in the XML never clears the one in the library. Every write marks the
source `rekordbox`. It recomputes `energy` when the BPM changes. The
`bpm_set`/`key_set` counters count only the values that actually changed. Response:
`{in_file, matched, unmatched, bpm_set, key_set, energy_set}`. `400` on an empty file
or invalid/unsafe XML.

## Analysis (in-app BPM/key)

```text
GET  /api/analysis/overview
POST /api/analysis/start
GET  /api/analysis/status
GET  /api/analysis/divergences
POST /api/analysis/apply
```

Deterministic BPM/key analysis on owned tracks, the alternative source to the
Rekordbox import above: a local Essentia adapter
(`backend/app/integrations/essentia_engine.py`, lazy import, pinned
`essentia==2.1b6.dev1389`, AGPL-3.0). Cratory never asks an AI for BPM/key. The
background job never touches the canonical `bpm`/`camelot_key` directly: it only
writes `analysis_bpm`/`analysis_camelot`/`analyzed_at`/`analysis_error`; the bridge
to the canonical fields is the explicit apply step (source becomes `cratory`).

`GET /api/analysis/overview` returns `AnalysisOverviewOut`: `owned`,
`ready_for_set`, `missing_bpm`, `missing_key`, `bpm_by_source`/`key_by_source`
(counts by `manual`/`rekordbox`/`cratory`), `analyzed` (tracks with `analyzed_at`
set), `divergent` (in-app analysis differs from the canonical value) and
`rekordbox_pending` (same count as `GET /api/rekordbox/pending`).

`POST /api/analysis/start` (`202`) starts the background job. Body
`{scope: "missing"|"all" = "missing", track_ids?: number[]}`: `missing` analyzes
only owned tracks without BPM or key, `all` (or explicit `track_ids`) re-analyzes
regardless of current values. `503` (`analysis_engine_unavailable`) if Essentia is
not installed; `409` (`analysis_already_running`) if a job is already running. The
job writes only `analysis_*` fields, auto-applies to the canonical fields only where
they are empty (no conflict possible), and marks per-track decode failures with
`analysis_error="analysis_decode_failed"` without stopping the batch (commit per
track, so progress survives an interruption).

`GET /api/analysis/status` returns `AnalysisJobStatus`: `status`
(`idle|running|done|error`), `processed`, `total`, `analyzed`, `failed`, `applied`,
`current_label`, `error`, `started_at`, `finished_at`.

`GET /api/analysis/divergences` lists owned tracks where the in-app analysis
differs from the canonical value (`AnalysisDivergenceOut[]`): `track_id`, `artist`,
`title`, `bpm`, `bpm_source`, `analysis_bpm`, `bpm_delta`, `camelot_key`,
`key_source`, `analysis_camelot`, `key_compatibility` (`same|compatible|weak|
unknown`, the same Camelot-wheel compatibility used by transitions).

`POST /api/analysis/apply` copies `analysis_*` into the canonical fields (source
becomes `cratory`) for a selection. Body `{track_ids?: number[], mode?:
"divergent"|"all", force?: boolean}`: explicit `track_ids` or `mode="divergent"`
apply only the picked/divergent rows; `mode="all"` rewrites every analyzed track
regardless of source (including `manual`) and requires `force=true` as
confirmation. `422` (`analysis_force_required`) if `mode="all"` without `force`;
`422` (`analysis_apply_empty`) if neither `track_ids` nor `mode` is given. Response
`AnalysisApplyOut`: `{applied, skipped}`.

## Playlists

```text
GET    /api/playlists/spotify/available
POST   /api/playlists/import
POST   /api/playlists/{playlist_id}/sync
POST   /api/playlists/sync-all
GET    /api/playlists/import/status
POST   /api/playlists/import-manual
POST   /api/playlists/create-from-tracks
POST   /api/playlists/{playlist_id}/add-tracks
POST   /api/playlists/{playlist_id}/reorder
PUT    /api/playlists/{playlist_id}/order
POST   /api/playlists/{playlist_id}/duplicate
GET    /api/playlists
GET    /api/playlists/{playlist_id}
PATCH  /api/playlists/{playlist_id}
DELETE /api/playlists/{playlist_id}
GET    /api/playlists/{playlist_id}/tracks
DELETE /api/playlists/{playlist_id}/tracks/{track_id}
POST   /api/playlists/{playlist_id}/tracks/remove
POST   /api/playlists/{playlist_id}/export
GET    /api/playlists/{playlist_id}/sync-log
GET    /api/playlists/{playlist_id}/gaps
GET    /api/playlists/library/gaps
```

`GET /api/playlists/spotify/available` lists only the playlists **owned** by the
connected user (the ones by others that they follow are not importable in dev mode).
`POST /api/playlists/import` starts a **background job** (`202`, status via
`GET /api/playlists/import/status`) importing a Spotify playlist or the liked tracks:
the platform fetch — potentially minutes on thousands of liked tracks — happens inside
the job, with per-item progress in the global job bar. One shared job slot covers every
streaming import/sync operation (`409 streaming_import_already_running` if busy).
`POST /api/playlists/{playlist_id}/sync` (also `202` + the same status endpoint)
realigns an already-imported playlist with the source platform. Spotify: imports the
new tracks and unlinks the removed ones (which stay in the library; memberships added
by Cratory, `added_by='cratory'`, are never pruned). SoundCloud (see dedicated
section): always additive, never prune; only for playlists imported from URL (not the
"likes"). Responds `409` for a "like"-type SoundCloud playlist or one without a saved
`url`; provider errors surface in the job state (`error`/`error_code`).
`POST /api/playlists/sync-all` (also `202` + the same status endpoint) realigns **every**
imported Spotify and SoundCloud playlist in one job; liked playlists are excluded on both
platforms (they grow through the selective flow). A playlist that fails does not stop the
others: the job still ends `done` and the aggregate report lands in `sync_all`
(`synced`, `failed`, summed `created`/`updated`/`removed`/`skipped`, plus `failures` with
`playlist_id`, `name`, `platform` and `error`). While it runs, `current_label` carries the playlist in flight
with its own item progress, and `processed`/`total` count playlists, not tracks. Responds
`409 no_syncable_playlists` when there is nothing to realign.
`DELETE /api/playlists/{playlist_id}` removes the playlist and its "orphan leads":
tracks without a local file that are in no other playlist nor in a saved set (tracks
on disk, or present in another playlist/set, stay). Responds `200` with
`{deleted_tracks}` (how many orphan tracks were removed), `404` if it does not exist.
`POST /api/playlists/import-manual` creates a playlist from pasted text. None of these
start any enrichment: the text metadata (title/artist/album/label/genre) is the Organize section's
job, BPM/key come only from the Rekordbox import.
`POST /api/playlists/create-from-tracks` (`201`) creates a manual playlist composed of
tracks already in the library (disk-first), in the given order. Request:
`{name, track_ids}`. Response: `PlaylistOut`. `422` if the name is empty or a
track_id does not exist.
`POST /api/playlists/{playlist_id}/add-tracks` (`200`) adds tracks already in the library to
an **existing** playlist. Request: `{track_ids}` (at least one). Idempotent: track ids
already in the playlist, and duplicate ids within the same request, are counted as
`skipped` rather than added twice; every new membership is marked `added_by="cratory"`
so a later sync prune never removes it. `404 playlist_not_found` if the playlist does
not exist; `422 tracks_not_found` (with `missing`) if any track id does not exist.
Response: `{playlist, added, skipped}`.
`POST /api/playlists/{playlist_id}/reorder` moves a track to a 1-based position within
the playlist, shifting the others; the order is persisted in the `playlist_tracks.position`
column (not just a client-side sort). Request: `{track_id, position}` (`position >= 1`,
clamped to `[1, N]` for the current track count). Only on kinds whose order belongs to the
user (`manual` and `shazam`): `409 playlist_not_reorderable` on any other kind. `404
playlist_not_found` if the playlist does not exist; `404 track_not_in_playlist` if
`track_id` is not a member. Response: the reordered track list (`list[TrackOut]`), same
shape as `GET /api/playlists/{playlist_id}/tracks`.
`PUT /api/playlists/{playlist_id}/order` replaces the **whole** order in one call
(drag-and-drop): request `{track_ids}` must be an exact permutation of the current
members (`422 order_mismatch` otherwise), same reorderable-kind guard as `/reorder`.
Response: the reordered track list.
`PATCH /api/playlists/{playlist_id}` renames the playlist (`{name}`, `422
playlist_name_empty` if blank after trimming). Renaming sets `name_locked=true` on the
playlist: from then on a sync re-reads everything from the platform **except** the name.
`name_locked` is exposed in `PlaylistOut`.
`POST /api/playlists/{playlist_id}/duplicate` (`201`) forks any playlist into a manual
copy (`platform="manual"`, `kind="manual"`) with the same track order; request `{name}`
(optional, defaults to `"<name> (copia)"`). Memberships are `added_by="cratory"`. The
copy is editable and reorderable even when the source is a synced playlist.
`DELETE /api/playlists/{playlist_id}/tracks/{track_id}` removes one membership (the
track is deleted too when it becomes an orphan lead — not on disk, in no other playlist
nor set); response `{deleted_tracks}`. `POST /api/playlists/{playlist_id}/tracks/remove`
is the bulk version: request `{track_ids}`, non-member ids are ignored, response
`{removed, deleted_tracks}` (memberships removed / orphan leads deleted).
`POST /api/playlists/{playlist_id}/export?format=` exports the playlist in playlist
order: `m3u8` (default, importable in Rekordbox — only tracks with a local file, the
skipped count is noted in a comment) | `csv` | `text` | `markdown` (these three include
every track, leads too).
`GET /api/playlists/{playlist_id}/sync-log?limit=` (default 20, max 100) returns the
recent import/sync diffs, newest first: `{id, created_at, added, removed}` where
`added`/`removed` are `{id, artist, title}` snapshots (readable even after the track is
deleted as an orphan lead). Events are recorded by every import/sync that changes the
membership set (no-op syncs record nothing) and die with the playlist.
`GET /api/playlists/{playlist_id}/tracks` returns the members in playlist order; each
`TrackOut` carries `playlist_position` (1-based) and `playlist_added_at` (when the track
entered *this* playlist, from `playlist_tracks.added_at` — the platform date for imports,
"now" for memberships created by Cratory; both fields only in this endpoint, `added_at`
stays the first library import).

The system playlist **"Top"** (`platform="manual"`, `kind="rating_top"`) is not created
through any endpoint above: it comes into existence lazily, the first time a track is
voted `rating=3` (see Tracks and library), and stays in sync deterministically from then
on (`services/rating.py`, called from `PATCH /api/tracks/{track_id}` inside the same
transaction as the vote, before commit — same precedent as the Discovery playlist).
At most one such playlist exists. Membership tracks the current vote exactly: a track
enters as soon as its `rating` reaches `3` and leaves the moment it drops below that (or
the vote is cleared), regardless of how the track got into the library. New memberships
are marked `added_by="cratory"` like the other system playlists, and `track_count` is
kept realigned. Equivalent to querying `GET /api/tracks?rating=3` directly.

## Tracks and library

```text
GET   /api/tracks
GET   /api/tracks/{track_id}
GET   /api/tracks/{track_id}/cover
GET   /api/tracks/{track_id}/audio
PATCH /api/tracks/{track_id}
POST  /api/tracks/{track_id}/link-file
GET   /api/files/search
POST  /api/library/index
GET   /api/library/index/status
GET   /api/library/genres
GET   /api/stats
```

For an owned track, `genre`/`album`/`label`/`year` in `GET /api/tracks` and
`GET /api/tracks/{track_id}` carry the **effective** value: the tag on the linked file
(`Track.primary_file_id` -> `AudioFile`, resolved query-time with `COALESCE`
in `repositories._EFFECTIVE_TAGS`/`_join_primary_file` — no derived column, no
migration) when non-NULL, otherwise the value imported from streaming. `TrackOut` also
exposes `primary_file_id` and the boolean flags `genre_from_file`/`album_from_file`/
`label_from_file`/`year_from_file` (`true` when that value came from the file).
`TrackDetailOut` (detail only) additionally carries `file_artist`/`file_title`, the
artist/title tags read from the file — informational only, track identity stays
`Track.artist`/`Track.title`. Editing these four fields on an owned track is **not** a
new endpoint: it goes through `POST /api/organize/files/{file_id}/tags` (see Organize
below), the single writer of file tags, targeting the track's `primary_file_id`; a
track with no owned file keeps editing them via `PATCH /api/tracks/{track_id}` as
before.

Filters supported by `GET /api/tracks`: artist, title, album, genre, label
(`label`, exact match), rating (`rating`, `1`-`3` exact match; tracks with no vote are
never matched by this filter) and archived (`archived`, default `false`: archived ones are
excluded; `true` shows only the archived ones), source (incl. `local_files`), state
(`imported` | `ready_for_set`), BPM min/max, key, duration, Spotify/SoundCloud
presence, ownership (`has_local_file`), incomplete metadata, sort/order (`sort=rating` is
supported like the other columns; tracks with `rating IS NULL` always sort last,
regardless of `order`; `sort=added_at` sorts by first library import, NULLs last),
limit/offset, and `in_playlist` (repeatable, e.g.
`?in_playlist=1&in_playlist=2`): tracks belonging
to **any** of the given playlists (union), AND-combined with every other filter (e.g.
paired with `genre` it narrows to tracks in any of those playlists that also match the
genre) — for the tracks of a single playlist use `GET /api/playlists/{playlist_id}/tracks`.
The `genre`/`album`/`label` filters and `sort=genre`/`sort=year` all match against the
same effective value described above (file tag first, streaming fallback); so does the
candidate engine behind the Set Builder's genre pool (`repositories.effective_genre`).

`GET /api/tracks/{track_id}/cover` serves the artwork **embedded in the file** of an
owned track, read on-demand from disk (not saved in the DB). Responds with the image
bytes (`Cache-Control: max-age=3600`); `404` if the track does not exist, is not owned
(`has_local_file`), the file is missing or contains no cover. The frontend uses
`album_art_url` (Spotify) when present and falls back to this endpoint otherwise.

`GET /api/tracks/{track_id}/audio` streams the **owned local file** of a track for quick
audition, read-only: `FileResponse` with HTTP Range/seek support (a `Range` request gets a
`206` partial response). Path safety: the track's `local_path` must resolve inside one of
the allowed roots from `search_roots()` (`LIBRARY_ROOT` + the slskd download dir), checked
via `path_within_roots` (defense against traversal/symlinks pointing outside). `404` with
`track_not_found` (no such track), `track_no_local_file` (not owned), `track_file_not_allowed`
(resolved path outside the allowed roots) or `track_file_missing` (path inside the roots but
the file is gone). No transcoding: an unsupported browser format simply fails to play
client-side. One track at a time via the shared docked player (the same one used for the
Discovery ephemeral preview).

`POST /api/library/index` (202) is an **alias of the single scan job** (`scan_job`), the
same one started by `POST /api/organize/scan`: one walk over the configured roots, then
the linking phase — link to `Track`, archive pass, ownership reconciliation, energy
calibration. `409` if `LIBRARY_ROOT` is not configured, and `409` `apply_running` while
an Organize Apply is in progress (scanning a half-moved tree would mis-merge rows).

Job state on `GET /api/library/index/status`. Its shape is the job state, **not** a flat
report: `{status, phase, processed, total, result, error}`, where `phase` is one of
`scanning | linking | inspecting | deduping | null` and `result.linking` carries the
linking counters (`scanned`, `created`, `relinked`, `unchanged`, `duplicates`, `lost`,
`archived`, `energy_computed`). **`result.linking` is `null`** when the run did not walk
the library root — a scan restricted to the inbox does phase 1 only and deliberately
leaves the tracks alone.

`PATCH /api/tracks/{track_id}` accepts partial updates on BPM, Camelot, genre, label,
year and related fields. Manual values take precedence over imported data. `422` on a
key not in valid Camelot notation. `energy` is **not accepted**: it is always derived
from BPM+genre and is recomputed automatically when the patch touches `bpm` or
`genre`; a payload that includes `energy` is rejected with `422` (schema
`extra="forbid"`). It also accepts `archived` (bool, optional) to archive or restore a
track out of the wishlist; unlike the other fields, `null` does NOT clear it and is
treated as "unchanged" (the column is a NOT NULL bool). Library indexing still wins:
owning the file on disk sets `archived` back to `false`.

It also accepts `rating` (`int | null`, `1`-`3`, `422` from schema validation outside that
range): a personal 3-level vote, available on **every** track including ones not owned
(`has_local_file=false`). Unlike `archived`, an explicit `null` clears an existing vote
back to "not rated" — consistent with the other nullable fields. Setting or clearing
`rating` also deterministically syncs the "Top" playlist (see Playlists) in the same
transaction as the patch, before commit (`services/rating.py`). The vote is never sent
to the AI and never affects any deterministic score beyond the small Set Builder
tie-break bonus (see Set Builder and saved sets).

`POST /api/tracks/{track_id}/link-file` manually links a file on disk to the track
(ownership without download): it validates existence and audio extension, sets
`has_local_file`/`local_path`/`local_format`/`local_bitrate` + best-effort audio-hash
and clears the download outcome (`last_download_outcome`/`reason`). Request: `{path}`.
`400` on an invalid path, `404` if the track does not exist.

`GET /api/files/search?q=...` searches audio files by name (AND match of the terms,
case-insensitive) in `LIBRARY_ROOT` and `SLSKD_DOWNLOAD_DIR`; max 50 results, a query
under 2 characters returns an empty list. Response: list of
`{path, name, format, size, source}` with `source` = `library` | `downloads`.

- `GET /api/files/pick/availability` → `{available}`: whether the native path-picker
  dialog is available (macOS only, with osascript in the PATH).
- `POST /api/files/pick` `{kind: "folder"|"file", start?, prompt?}` → `{path}`:
  opens the native (Finder) dialog on the backend machine and returns the chosen
  path; `path: null` if the user cancels or the dialog times out (300 s). 409
  `picker_unavailable` outside macOS, 409 `picker_busy` if a dialog is already open.
  Used by the "Sfoglia…" button in Settings.

`GET /api/library/genres` returns `{genre, count}[]` (`GenreCountOut`) for the
**effective** genre (see above) among candidate tracks (BPM present), sorted by
frequency then name: feeds the Set Builder's genre multi-select.

`GET /api/stats` returns the deterministic library aggregates (`LibraryStatsOut`):
counts, BPM/key coverage, `key_distribution` and `genre_distribution` (genre->count
map; genres are merged case-insensitively keeping the most frequent spelling), BPM and
energy histogram.

## Organize (file tags)

```text
GET  /api/organize/files
POST /api/organize/files/{file_id}/tags
```

`GET /api/organize/files` lists the audio files under `LIBRARY_ROOT`/inbox
(`FileRow[]`). `status` filters by file status (default `present`; accepts a
comma-separated list, e.g. `present,missing`, to include more than one). `q` is a
case-insensitive substring match on path/artist/title. `FileRow.track_id` is the track
this file belongs to (`AudioFile.track_id`, `null` for files not linked to any track):
the FILES page uses it to link a row to the matching track detail page; the reverse
cross-link (track detail -> FILES) opens `/organize/files?q=<file path>&status=present,missing`
so the row is found even if the file went missing from disk since the last scan.

`POST /api/organize/files/{file_id}/tags` is the **single writer of text tags** on a
file (`FileTagsUpdate`, partial update: only the fields present in the body are
touched; an empty string clears the tag). This is also how `genre`/`album`/`label`/`year`
get edited for an owned track (see "Tracks and library" above) — the frontend calls it
against the track's `primary_file_id`, not a track-side PATCH. Response: the updated
`FileRow`. Side effect when the field is `genre` and the file is linked to a track
(`track_id` not null): `tracks.genre` is kept as a mirror of the new tag (same shared
rule as the scan and the one-off backfill, see `docs/ARCHITECTURE.md`), and the track's
`energy` is recomputed from it. `album`/`label`/`year` and `artist`/`title` never touch
the `Track` row this way.

## Labels

```text
GET  /api/labels
```

`GET /api/labels` returns the deterministic overview of the labels present in the
library (aggregates with normalized names and merging of variants). Each entry exposes
`label`, `track_count`, `artist_count`, `artists` (full list, for the by-artist
filter), `genres` (capped) and the year range. The `label` comes from the file tag
(read at indexing time, written by the Organize section): the old backfill from Spotify has been
removed.

## Set Builder and saved sets

```text
POST   /api/sets/generate
POST   /api/sets/generate-async
GET    /api/sets/generate-status
GET    /api/sets
GET    /api/sets/{setlist_id}
PATCH  /api/sets/{setlist_id}
DELETE /api/sets/{setlist_id}
POST   /api/sets/{setlist_id}/export
DELETE /api/sets/{setlist_id}/tracks/{position}
POST   /api/sets/{setlist_id}/tracks/{position}/move
POST   /api/sets/{setlist_id}/tracks/{position}/replace
POST   /api/sets/{setlist_id}/alternatives
```

Generation:

- `generate` returns the set immediately.
- `generate-async` starts a job and the UI reads `generate-status`.
- `use_ai`: `true` = AI curation (intent + mood-fit + anchor hints + narrative), `false` =
  pure deterministic engine, omitted = auto (AI if configured and a prompt is present).
  There is no technical/creative `mode`: AI curation has a single musical character.
- Disk-first: `owned_only` (default `true`) generates the set from owned tracks only.
  The flag stays on the saved set (exposed in `SetlistOut.owned_only`) and editing
  respects it: `alternatives` excludes leads from the pool and `replace` with a track
  without a local file responds 422.

`use_ai` (request, `bool | null`): `true` = AI curation on (intent compilation from the free
prompt, mood-fit and anchor hints feeding the deterministic generator, narrative afterwards);
`false` = purely deterministic, no LLM call; `null`/absent = auto (AI curation runs if an LLM
is configured and `prompt` is non-empty). In every case the deterministic two-phase generator
is the only thing that sequences tracks — the AI never orders or picks the tracklist, and any
AI call that fails degrades silently to the deterministic default with a warning, never a 4xx/5xx.

Track `rating` (1-3, see Tracks and library) feeds a small deterministic tie-break bonus into
the generator's scoring (`_RATING_BONUS = 2.0` per level, max `6.0`, in `_candidate_score` and
`_pick_first`): a higher vote nudges a track ahead of an equally-compatible one, but can never
outweigh actual musical compatibility. The vote is deterministic-engine input only — it is
never shown to or usable by the AI curation stage.

`SetlistOut` (AI curation fields):

- `generated_by`: `algorithmic` (no AI contribution reached the set) | `algorithmic+ai_curation`
  (at least one of intent/mood-fit/anchors/narrative was used). Sets generated before this
  redesign may still read the historical value `ai`.
- `curation` (`{}` when no curation ran): `intent_summary` (free string, "here is how I
  understood your request", empty if intent compilation did not run or produced nothing),
  `compiled` (the `SetGenerationRequest` fields the AI filled in — only fields the user left
  unset in the form are ever compiled; `owned_only`/`sources` are never compilable), `warnings`
  (list of AI-degradation messages, e.g. intent/mood/anchors/narrative unavailable).
- `validation` (`{}` for a purely deterministic set): `warnings` (same AI warnings as
  `curation.warnings`) and `missing_library_suggestions` (0-3 strings from the narrative call
  suggesting what type of track to add to the library — never a track id or an invented title).
- `SetlistTrackOut.mood_tags`: up to 3 short tags from the mood-fit judgement for that track
  (`[]` when curation did not run or did not produce a usable judgement for it). Transient
  per generation, not written back onto `Track`.

Export (`POST /api/sets/{setlist_id}/export?format=`): `text` | `csv` | `markdown` |
`m3u8`. The CSV includes the `local_path` column (empty string if the track has no
local file). The `m3u8` format produces a playlist importable in Rekordbox (`#EXTM3U`
+ `#EXTINF` per track, lines with the absolute `local_path` of the file in the
library); tracks without a local file are excluded and flagged with a comment at the
top. Alternatively, Spotify playlist creation via the Spotify endpoint.

## Transitions

```text
GET  /api/transitions/{track_id}
```

Returns the tracks **compatible** with the given one (query: `limit`, optional `lens`).
There is no before/after split: the technical score is essentially symmetric (BPM + key
dominate), so a compatible track works on either side — the set intent is the DJ's call.
Each candidate carries a technical score and a deterministic classification:

```text
technically_safe | creative_risk | good_reset
```

`lens` (one of the three classes) ranks within that class, so deliberate resets and creative
risks surface instead of staying buried under the safe picks.

## Spotify

```text
GET  /api/spotify/status
GET  /api/spotify/login
GET  /api/spotify/callback
POST /api/spotify/create-playlist
```

Spotify handles OAuth, playlist import and export. It is not a source of BPM/key.

## SoundCloud

```text
GET  /api/soundcloud/status
PUT  /api/soundcloud/config
POST /api/soundcloud/import
GET  /api/soundcloud/likes/preview
POST /api/soundcloud/import/likes
```

Import via yt-dlp: metadata only, never audio, no ISRC (SoundCloud does not expose
it). The likes preview uses flat extraction (fast, without uploader or duration);
import and sync re-fetch each track in full mode (real uploader, duration, artwork —
~1s per track, playlists inside the likes are filtered out). `GET status` returns
`available` (yt-dlp importable), `ytdlp_version` and the configured `username`. `PUT
config` saves the username (`{username}`, strips the leading `@`). The likes
preview/import endpoints without a configured username respond `409`.

`POST /api/soundcloud/import` imports a public playlist or a secret link from URL
(`{url}`) as leads in the library (same `PlaylistImportReport` as the other imports).
A `/likes` URL responds `422`: likes go only through the selective flow below.
Non-`soundcloud.com` or non-http(s) URLs respond `422` (anti-SSRF guard), yt-dlp
fetch/extraction errors respond `502`.

`GET /api/soundcloud/likes/preview?limit=100` fetches the most recent likes of the
configured user and annotates them with `already_imported` (already in the library by
`platform_track_id`), without importing anything.

`POST /api/soundcloud/import/likes` imports ONLY the selected likes
(`{track_ids: [...], limit: 100}`) into the system playlist "SoundCloud Likes".
Stateless: it re-fetches the likes and filters by id. Additive (no prune).

Dedup: no ISRC, only `platform_track_id`. `POST /api/playlists/{playlist_id}/sync` on
a SoundCloud playlist imported from URL realigns with the source in an **always
additive** way (never prune, unlike Spotify): a removed/taken-down track does not
unlink the already-imported track. The "like" playlists (`kind=liked`) are not
syncable from this endpoint: they only grow via the selective flow above.

## Discovery

```text
GET  /api/discovery/genres
POST /api/discovery/dig
GET  /api/discovery/release
GET  /api/discovery/preview
POST /api/discovery/add
POST /api/discovery/save-for-later
```

`dig` ("Scava") does crate digging by genre or label: it finds releases/tracks not yet
owned. Two sources sit behind a shared `DigSource` protocol
(`backend/app/services/dig_sources/`, `Seed`/`Pile`/`probe`/`fetch`/`to_lead`) —
**Discogs** (`source="discogs"`, the default) and **Bandcamp** (`source="bandcamp"`) —
picked per request via `DiscoveryDigRequest.source`. The engine
(`backend/app/services/discovery_dig.py`) reasons in **items**, never in pages: it asks
the source to `probe` the seed (how tall the pile is, how far *this* source reaches
into it), derives a window `(offset, count)` from `depth`, and only the source knows how
to translate that window into its own pagination — Discogs into page numbers, Bandcamp
into a sequential cursor walk (no jump-to-page on Bandcamp). `depth` (`0.0`-`1.0`) picks
**where in the pile to fetch from** — `0.0` is the seed's classics, `1.0` is the bottom
of what the source reaches — and taste always ranks inside that window, never across
it.

Discogs sorts its whole pile by **demand** (`sort=want` desc) before windowing; the pile
holds up along its whole length (median `want` still ~89 at rank 10,000 in
measurements), so `depth` never runs dry there. Bandcamp has no demand signal at all (no
have/want) and sorts by `slice: "top"` instead, the closest Bandcamp equivalent.
`genres` lists the genres and styles available as a seed — the same curated Discogs
vocabulary for both sources; Bandcamp normalizes each entry into a tag (lowercase,
runs of non-alphanumeric characters collapsed to one hyphen) with one hand-kept alias
(`"Drum n Bass"` -> `drum-and-bass`, because the naive normalization lands on a real but
wrong tag).

The response no longer carries `pile_pages`. It exposes, source-neutral, in **items**:

- `pile_total` — the pile's real height (the provider's raw count for the seed; `0` is a
  dead seed).
- `pile_reach` — how many items *this* source can actually reach into that pile
  (Discogs: `DISCOGS_MAX_PAGES * SEARCH_PER_PAGE` = 10,000, page 101 is a hard 404 wall;
  Bandcamp: `BANDCAMP_REACH` = 3,000, a cost choice, not a provider limit — the cursor
  walk makes depth cost requests, up to ~20s worst case at `depth=1.0`).

`pile_reach <= 300` means the window already covers everything the source can reach and
`depth` has no effect — the UI disables the depth control and shows a note instead of an
inert slider (the old `pile_pages <= 3` check, now source-neutral). `pile_total >
pile_reach` means only part of the pile is shown, and the UI says so (a Bandcamp label
seed always has `pile_reach == pile_total`: the whole discography is fetched once by
`probe` and `fetch` just slices it — no fetch cost left to pay). `seed_resolution` gained
two Bandcamp values: `"style"|"genre"|"label"|"tag"|"discography"|null` (`"tag"` for a
Bandcamp genre seed, `"discography"` for a Bandcamp label seed). `"genre"` still means a
Discogs seed fell back to a top-level genre (~15 huge shelves like `Electronic`,
millions of releases): only the most-wanted releases are reachable through pagination,
and the UI says so instead of letting a shelf pass for a fine-grained dig. A dead seed
(unknown to the source) has `pile_total: 0` and `seed_resolution: null`, for both
sources.

Each lead exposes `source`, `source_id`, `source_url` and `stream_url` in place of the
old `discogs_id`/`discogs_url` (two sources cannot share a field named after one of
them). `source_id` is a plain string: the Discogs release id for Discogs,
`"<band_id>:<item_id>"` for Bandcamp. `source_url` is `null` for Bandcamp leads that come
from a label seed — the discography endpoint that produces them carries no page URL; the
release detail panel below still resolves one via `tralbum_details`. `stream_url` is
populated only by Bandcamp genre-seed leads, which hand back a real per-track mp3 stream
inside the dig result itself — no fallback to iTunes/YouTube, no extra request; Discogs
leads never set it and resolve their preview the usual way (see `preview` below).
`have`/`want` stay `0` on every Bandcamp lead (the concept does not exist there) and
`style` is always `null` (Bandcamp exposes styles only in the release detail, not in the
list) — the reason codes that read those fields (`rare_wanted`, `deep_cut`,
`style_match`) simply never fire for Bandcamp leads, with no source-specific branch
needed.

Taste always ranks inside the chosen window — not a mode, not optional. The score is
**taste-only**: graduated familiarity on the artist, owned label and style affinity
with your genres. Novelty, demand and recency are **not** score inputs any more —
demand only gates which window `depth` reads on Discogs (above), it does not order
within it. On Bandcamp, which has no style signal in the result list, the style weight
redistributes into artist/label — the same mechanism already used to zero out the label
weight on a label seed. The taste profile is always built from the **whole library**
(the former `taste_playlist_id` reference was removed: on lead-only playlists — which
carry no file tags, hence no labels or genres — it silently zeroed the ranking); the
dedup is library-wide as well. Each lead carries deterministic `reasons[]` (`{code,
data}`) to explain why (e.g. `rare_wanted`, `deep_cut`, `label_followed`,
`artist_collected`, `style_match`, `recent`); the chip text is composed by the UI —
these are display badges, not the score's factors.

The response is **never truncated**: the window's ~300 raw items are the natural limit
(`WINDOW_ITEMS` in `backend/app/services/dig_sources/__init__.py`, shared by both
sources — the former `limit` field was removed, since capping it below the window
silently hid valid leads). How many to *show* is a client-side lens in the UI, together
with format and ordering.

Network cost: Discogs spends **4-5 requests per dig** — one `count_releases` probe to
size the pile (needed to place `depth`'s window) plus 3 content pages, plus one extra
probe when a `genre` seed's fine-grained `style=` filter returns nothing and falls back
to the coarser `genre=` filter. Bandcamp spends 1-6 requests depending on `depth`
(`ceil((offset + 300) / 500)`, batches of up to 500 items): 1 request at `depth=0.0`, up
to 6 (~20s) at `depth=1.0` on a deep pile — this is `BANDCAMP_REACH`'s cost trade-off,
not a rate limit.

`GET /api/discovery/release?source=&id=` replaces the old `release/{discogs_id}`,
expanding a lead from the dig into its **real tracklist** (fetched lazily when the
release is opened): `?source=discogs&id=<int>` (the numeric Discogs release id) or
`?source=bandcamp&id=<band_id>:<item_id>` (colon-separated pair, both integers). Only
integers ever cross this boundary — no URL is taken from the client and followed by the
backend, so there is no SSRF surface and no host allowlist to maintain. A malformed id
(non-numeric Discogs id, or a Bandcamp id missing the colon / with non-digit parts)
responds `400 discovery_bad_id`. Each row of the tracklist carries position, title,
duration and, Bandcamp only, `stream_url` (`DiscoveryTrackOut.stream_url`, always `null`
on Discogs). The response type is `DiscoveryReleaseOut`, with `source`/`source_url` in
place of the old `discogs_id`/`discogs_url`; `videos` (YouTube videos Discogs already
associates with the release) stays populated only for Discogs — Bandcamp tracks already
carry a real stream, so there is nothing to resolve there. Provider errors surface as an
explicit `502 discovery_provider_error` for both sources.

`preview` resolves an **ephemeral audio preview** for a lead that has no `stream_url` of
its own, so it can be evaluated before acquiring it: query params `artist`, `title`,
optional `discogs_id` and `level` (`release`|`track`, default `track`). It responds
`DiscoveryPreviewOut { kind: "itunes"|"youtube"|"none", audio_url, youtube_video_id,
source_url, matched_title }`. iTunes Search is the primary source (30s clip); if there
is no match, it falls back to the YouTube video Discogs associates with the release.
Provider errors resolve to `kind: "none"` with `HTTP 200`, never an error status. Nothing
is persisted. Bandcamp genre-seed leads skip this endpoint entirely: they already carry
a real `stream_url` in the dig result.

`add` imports a candidate into the app's library idempotently. It does not write to
Spotify. The AI, if configured and requested, adds explanations but does not choose
the candidates. `save-for-later` persists a lead without attaching it to a playlist
(same idempotent import).

The old Discovery mode based on playlist gaps has been removed, and so has playlist
expansion: Discovery is now the dig alone, while Gap Analysis stays a separate
read-only endpoint.

Note: Discogs, Bandcamp and Spotify-as-resolver are the only providers left in Cratory
for Discovery — they do not provide BPM/key/genre/mood to the library. Bandcamp's
endpoints are internal and undocumented (see `docs/DEPENDENCIES.md`): if they change,
only the Bandcamp source breaks — the `DigSource` seam keeps Discogs unaffected.

## Shazam / mix identification

```text
GET    /api/shazam/status
POST   /api/shazam/identify
GET    /api/shazam/identify-status
GET    /api/shazam/sets
GET    /api/shazam/sets/{dj_set_id}
POST   /api/shazam/sets/{dj_set_id}/import-playlist
DELETE /api/shazam/sets/{dj_set_id}
```

Requires `ffmpeg`, `yt-dlp` and `shazamio`. The job temporarily downloads the audio,
samples segments, recognizes the tracks and persists `DjSet`/`DjSetTrack`. The tracks
do not enter the main library. This is the only audio fingerprinting in the project:
it identifies the tracks of an external mix, not the library tracks.

Sampling is resilient and paced: the grid is capped at 200 segments per mix
(≈39s step on a 2-hour set, so most real tracks collect 2+ agreeing samples);
recognizer calls are spaced ≥1s apart and internally retried with growing
backoff (5/15/45s) before counting as errors, so a burst of throttling does
not kill the analysis. An unrecognized segment is retried once at a nearby
offset. Runs of the same track reappearing within 240s are merged — even
across a different match in between (a transition false positive inside a long
track), which also counts as confirmation. Tracks left with a single agreeing
sample get up to two confirmation samples at ±(6-30)s: refuted singles are
discarded as transition noise; never-verified ones (budget exhausted, service
down) stay listed as uncertain. All extra calls share a budget of 50 per mix.
`DjSetTrack.confidence`: `90` = 2+ agreeing samples, `45` = single unverified
sample (the UI marks these; sets analyzed before keep the legacy fixed `80`).
If the recognizer stops responding despite the backoff, the analysis is saved
as **partial**: `DjSet.aborted_at_seconds` records where it stopped (exposed
in `DjSetOut`; the UI shows a PARTIAL badge with the offset).

`POST /api/shazam/sets/{id}/import-playlist` promotes the identified tracks to leads in
a playlist with `source=shazam` (dedup on artist+title, ISRC kept for the disk-first
re-link). Returns a `PlaylistImportReport`. Repeat blocked while the playlist exists:
the set stores `imported_playlist_id` (exposed in `DjSetOut`) and responds `409` on the
second import; deleting that playlist clears the reference and re-enables the import.

## Downloads (Soulseek / slskd)

```text
GET    /api/downloads/status
GET    /api/downloads/pending
POST   /api/downloads/retry-pending
DELETE /api/downloads/pending/{track_id}
POST   /api/downloads/candidates
POST /api/downloads/playlist/{playlist_id}
POST /api/downloads/track
POST   /api/downloads/track/soundcloud
POST   /api/downloads/search
POST   /api/downloads/manual
```

File acquisition via the headless Soulseek daemon slskd, deterministic (zero AI):
links a file to the existing `Track` (`has_local_file`/`local_path`/`local_format`/
`local_bitrate`). Requires `SLSKD_URL` and `SLSKD_DOWNLOAD_DIR` configured; without
them, all the search/download endpoints (`candidates`, `search`, `playlist/{id}`,
`track`, `manual`, `retry-pending`) respond `409`. Still available:
`GET status` (with `available=false`), `GET pending` and `DELETE pending/{track_id}`.

`GET /api/downloads/pending` lists the "to sort out" ones (outcome `needs_review` /
`not_found` / `failed` persisted on the Track, tracks not owned and not discarded);
`POST /api/downloads/retry-pending` (`202`) retries the auto-pick on all of them;
`DELETE /api/downloads/pending/{track_id}` ("Ignore") clears the outcome and removes
the track from the archive (`404` if the track does not exist).

`GET /api/downloads/status` returns `available` (slskd configured) plus the state of
the background job: `status` (`idle|running|done|error`), `processed`, `total`,
`downloaded`, `needs_review`, `not_found`, `failed`, `playlist_id`, `items[]`,
`error`, `started_at`, `finished_at`.

`POST /api/downloads/candidates` searches on slskd and returns the candidates ordered
deterministically (quality + name adherence + availability). Request: `artist`,
`title`, `duration_seconds` (optional: duration expected from the Track, rewards the
right version in the ranking). Response: list of candidates with `username`,
`filename`, `size`, `bitrate`, `length`, `format`, `name_score`, `quality_tier`,
`confidence`.

`POST /api/downloads/search` does a free search on Soulseek. Request: `{query}`.
Empty query -> empty list. Response: same candidate list as `candidates` but without
the name-adherence threshold (the user chooses by sight). `409` if slskd is not
configured, `502` on slskd error.

`POST /api/downloads/manual` (`202`) downloads a candidate chosen from the free search
without linking it to a `Track` (the file lands in the slskd download folder).
Request: `{candidate}` (same shape as `CandidateOut`). `409` if slskd is not configured
or a job is already in progress.

`POST /api/downloads/playlist/{playlist_id}` (`202`) starts the job for all the
playlist tracks without a local file: for each it searches, automatically picks the
best candidate (auto-pick above a confidence threshold) and runs the download. `409`
if slskd is not configured or a job is already in progress.

`POST /api/downloads/track` (`202`) starts the job for a single track with an
explicitly chosen candidate (mini-selector, e.g. from Discovery). Request: `track_id`,
`candidate` (same shape as `CandidateOut`). `404` if the track does not exist, `409` if
slskd is not configured or a job is already in progress.

`POST /api/downloads/track/soundcloud` (`202`) downloads via yt-dlp the audio of a
single SoundCloud track (`platform == "soundcloud"`, `url` present), extracts it to MP3
into the shared `SLSKD_DOWNLOAD_DIR` folder and links it to the `Track`
(`has_local_file`). Reuses the Soulseek download job/bar (one download at a time).
Request: `{track_id}`. Response: `202 {"available": true, ...job_state}`. Errors: `409
ytdlp_unavailable` · `409 ffmpeg_unavailable` · `409 download_dir_not_configured` ·
`409 download_already_running` · `404 track_not_found` · `422 not_a_soundcloud_track`.

The job is single-instance (one download at a time, like library indexing): an error
on one track does not stop the others. The UI polls `GET /api/downloads/status` during
execution.

## Soulseek connection (slskd server)

```text
GET  /api/slskd/status
POST /api/slskd/connect
POST /api/slskd/disconnect
```

Login to the Soulseek network from the Settings page. The Soulseek account credentials
are **not** handled here: they stay in slskd's own config (`slskd.yml` or
`SLSKD_SLSK_USERNAME`/`SLSKD_SLSK_PASSWORD`) — slskd's REST API exposes no clean way to
set them. Cratory only reads the connection state and drives connect/disconnect on the
daemon, reusing the `SLSKD_API_KEY` already in use (maps onto slskd's
`GET`/`PUT`/`DELETE /api/v0/server`).

`GET /api/slskd/status` returns `configured` (`SLSKD_URL` present — we know where the
daemon is), `reachable` (the daemon answered), `is_connected`, `is_logged_in`,
`is_connecting`, `is_transitioning`, `state` (raw slskd state string), `username`
(the Soulseek account configured in slskd, from `GET /api/v0/options`; password stays
masked) and `web_url` (slskd's web UI = `SLSKD_URL`, trailing slash stripped; `null`
when unconfigured). `web_url` is populated as soon as `configured`, **even when the
daemon is unreachable** — the Wishlist links to it so the user can search/download by
hand in slskd exactly when a Cratory download fails. The connection flags are meaningful
only when `reachable`. Two graceful degradations, both `200` (so the UI can poll without
treating them as hard errors): `SLSKD_URL` empty -> `configured:false`; daemon
unreachable -> `configured:true`, `reachable:false`.

`POST /api/slskd/connect` connects the daemon to the Soulseek network (login with the
credentials already in slskd) and `POST /api/slskd/disconnect` disconnects it; both
return the refreshed status. slskd stays "in transition" for a few seconds after the
action (Connecting -> LoggingIn -> LoggedIn), so the UI polls `status` until
`is_transitioning` is false. `409` if `SLSKD_URL` is not configured, `502` on slskd
error.

## AI and services

```text
GET /api/ai/status
GET /api/services/status
```

`/api/services/status` returns the aggregate state of ALL external integrations, in
order: `spotify, anthropic, discogs, musicbrainz, acoustid, slskd, soundcloud` (one
list for the whole app — the former `/api/organize/providers` was absorbed here and
removed). Unified field semantics for every entry:

- `configured` (bool): the **required** configuration is present (intrinsically `true`
  for services that work without a key, e.g. Discogs and MusicBrainz);
- `connected` (bool | null): live session state where it exists (Spotify OAuth),
  `null` where the concept does not apply. For slskd the live state stays on
  `GET /api/slskd/status`, polled by the UI row (no HTTP call to the daemon here);
- `env` (list): required variables; `optional_env` (list): optional variables
  (e.g. `DISCOGS_TOKEN`), rendered by the UI as "recommended" instead of making the
  service look unconfigured; `optional_ok` (bool | null): `true`/`false` = optional
  variables present/absent, `null` = the service has none.

## Settings

```text
GET   /api/settings/language
PUT   /api/settings/language
GET   /api/settings/config
PATCH /api/settings/config
PUT   /api/settings/share-library
```

Settings persisted in `AppState` (no dedicated table: single-user local app), letti in
cache da `core/runtime_settings`.

`GET`/`PUT /api/settings/language`: `{"language": "it"|"en"}` (default `"it"`); `422` su
valori diversi.

`GET /api/settings/config` returns the editable config that **overrides `backend/.env` at
runtime, without restarting the backend**. Editable fields (`library_root`, `archive_root`,
`slskd_download_dir`, `slskd_url`, `slskd_config_path`) each come as
`{value, source: "env"|"db", valid, detail}` — `source` says whether the effective value is
a DB override or the `.env` default. Plus `share_library` (bool) and `warning` (soft note).
The override lives in `AppState` under keys `cfg.*`; the affected read-sites now call
`runtime_settings.<field>()` instead of `settings.<field>`, so a change takes effect on the
next indexing run / slskd client / file search.

`PATCH /api/settings/config` with any subset of the editable fields: a non-empty value sets
an override, an empty string clears it (back to `.env`). Everything is validated **before**
persisting anything (`422 invalid_setting` with `params.field`/`detail` on a bad path/URL;
a directory must exist, `slskd_url` must be `http(s)://`). Returns the same shape as `GET`.
If `share_library` is on and `library_root` changed, the share is re-applied best-effort
(`warning` set on soft failure).

`PUT /api/settings/share-library` with `{"enabled": bool}` toggles library sharing on
Soulseek. slskd can't change shares via API at runtime, so Cratory edits `shares.directories`
in slskd's own YAML (round-trip preserving comments/permissions, with a `.bak` backup) and
forces a rescan (`PUT /api/v0/shares`). Returns `{share_library, applied_to_yaml, rescan}`
(`rescan:false` when the daemon is down — the share applies at its next start). `409
share_precondition` when the slskd config is missing/not writable, or enabling without a
`library_root`.

## Conventions

- Errors via `HTTPException` with a readable `detail`.
- Long operations via jobs and polling.
- Rate limit, retry, cache and fallback live in the `integrations/` or `services/`
  layer, not in the routers.
- Routers must not contain scoring, dedup or ranking logic.
