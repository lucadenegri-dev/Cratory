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
`SLSKD_DOWNLOAD_DIR`, `organizer_url` from `ORGANIZER_URL`). `analyze_pending` counts
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
GET    /api/playlists/import/status
POST   /api/playlists/import-manual
POST   /api/playlists/create-from-tracks
GET    /api/playlists
GET    /api/playlists/{playlist_id}
DELETE /api/playlists/{playlist_id}
GET    /api/playlists/{playlist_id}/tracks
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
`DELETE /api/playlists/{playlist_id}` removes the playlist and its "orphan leads":
tracks without a local file that are in no other playlist nor in a saved set (tracks
on disk, or present in another playlist/set, stay). Responds `200` with
`{deleted_tracks}` (how many orphan tracks were removed), `404` if it does not exist.
`POST /api/playlists/import-manual` creates a playlist from pasted text. None of these
start any enrichment: the text metadata (title/artist/album/label/genre) is Sortory's
job, BPM/key come only from the Rekordbox import.
`POST /api/playlists/create-from-tracks` (`201`) creates a manual playlist composed of
tracks already in the library (disk-first), in the given order. Request:
`{name, track_ids}`. Response: `PlaylistOut`. `422` if the name is empty or a
track_id does not exist.

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
GET   /api/stats
```

Filters supported by `GET /api/tracks`: artist, title, album, genre, label
(`label`, exact match) and archived (`archived`, default `false`: archived ones are
excluded; `true` shows only the archived ones), source (incl. `local_files`), state
(`imported` | `ready_for_set`), BPM min/max, key, duration, Spotify/SoundCloud
presence, ownership (`has_local_file`), incomplete metadata, sort/order, limit/offset
— for the tracks of a playlist use `GET /api/playlists/{playlist_id}/tracks`.

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

`POST /api/library/index` (202) indexes the canonical `LIBRARY_ROOT` library
(disk-first: the disk IS the library) — scan + re-link by audio-hash + ownership
reconciliation; `409` if `LIBRARY_ROOT` is not configured. Job state on
`GET /api/library/index/status`.

`PATCH /api/tracks/{track_id}` accepts partial updates on BPM, Camelot, genre, label,
year and related fields. Manual values take precedence over imported data. `422` on a
key not in valid Camelot notation. `energy` is **not accepted**: it is always derived
from BPM+genre and is recomputed automatically when the patch touches `bpm` or
`genre`; a payload that includes `energy` is rejected with `422` (schema
`extra="forbid"`).

`POST /api/tracks/{track_id}/link-file` manually links a file on disk to the track
(ownership without download): it validates existence and audio extension, sets
`has_local_file`/`local_path`/`local_format`/`local_bitrate` + best-effort audio-hash
and clears the download outcome (`last_download_outcome`/`reason`). Request: `{path}`.
`400` on an invalid path, `404` if the track does not exist.

`GET /api/files/search?q=...` searches audio files by name (AND match of the terms,
case-insensitive) in `LIBRARY_ROOT` and `SLSKD_DOWNLOAD_DIR`; max 50 results, a query
under 2 characters returns an empty list. Response: list of
`{path, name, format, size, source}` with `source` = `library` | `downloads`.

`GET /api/stats` returns the deterministic library aggregates (`LibraryStatsOut`):
counts, BPM/key coverage, `key_distribution` and `genre_distribution` (genre->count
map; genres are merged case-insensitively keeping the most frequent spelling), BPM and
energy histogram.

## Labels

```text
GET  /api/labels
```

`GET /api/labels` returns the deterministic overview of the labels present in the
library (aggregates with normalized names and merging of variants). Each entry exposes
`label`, `track_count`, `artist_count`, `artists` (full list, for the by-artist
filter), `genres` (capped) and the year range. The `label` comes from the file tag
(read at indexing time, written by Sortory): the old backfill from Spotify has been
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
- `mode=technical|creative`: today its only effect is model selection (`AI_MODEL_CREATIVE`
  if set, see `_model_for` in `routers/sets.py`) — the curation/narrative prompts are single
  and shared regardless of `mode`. Wiring per-mode prompts is a possible follow-up.
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
GET  /api/discovery/release/{discogs_id}
GET  /api/discovery/preview
POST /api/discovery/add
POST /api/discovery/save-for-later
```

`dig` ("Scava") does crate digging via **Discogs** by genre or label: it finds
releases/tracks not yet owned. Discogs sorts the seed's whole pile by **demand**
(`sort=want` desc); `depth` (`0.0`-`1.0`, replaces the old `adventurousness`) picks
**where in that pile to fetch from** — `0.0` is the seed's classics, `1.0` is the
bottom of the crate. The pile holds up along its whole length (median `want` still
~89 at rank 10,000 in measurements), so `depth` never runs dry. `depth` chooses the
*window*, not the ranking: inside one window `want` is roughly constant and does not
discriminate leads. `genres` lists the genres and styles available as a dig seed.

Taste always ranks inside the chosen window — not a mode, not optional. The score is
**taste-only**: graduated familiarity on the artist, owned label and style affinity
with your genres. Novelty, demand and recency are **not** score inputs any more —
demand only gates which window `depth` reads (above), it does not order within it. The
taste profile is always built from the **whole library** (the former
`taste_playlist_id` reference was removed: on lead-only playlists — which carry no
file tags, hence no labels or genres — it silently zeroed the ranking); the dedup is
library-wide as well. Each lead carries deterministic `reasons[]` (`{code, data}`) to
explain why (e.g. `rare_wanted`, `deep_cut`, `label_followed`, `artist_collected`,
`style_match`, `recent`); the chip text is composed by the UI — these are display
badges, not the score's factors.

The response is **never truncated**: the window's ~300 raw releases are the natural
limit (the former `limit` field was removed — measured against the demand-sorted pile
it silently hid ~160 valid leads on every dig). How many to *show* is a client-side
lens in the UI, together with format and ordering.

Network cost: **4-5 Discogs requests per dig** — one `count_releases` probe to size
the pile (needed to place `depth`'s window) plus 3 content pages, plus one extra probe
when a `genre` seed's fine-grained `style=` filter returns nothing and falls back to
the coarser `genre=` filter. The response carries `pile_pages`: how many pages the
pile actually has. When `pile_pages <= 3` the whole pile already fits in one window and
`depth` has no effect — the UI disables the depth control and shows a note instead of
offering an inert one.

The response also says **how the seed resolved**: `seed_resolution`
(`"style" | "genre" | "label" | null`) and `pile_total` (the probe's raw item count —
`pile_pages` is capped at 100 and cannot tell 43k from 4.9M). `"genre"` means the seed
fell back to a Discogs top-level genre (~15 huge shelves like `Electronic`, 4.9M
releases): only the ~10,000 most wanted are reachable through pagination, and the UI
says so instead of letting a shelf pass for a fine-grained dig. A dead seed (unknown to
Discogs on both levels) has `pile_pages: 0` and `seed_resolution: null`.

`release/{discogs_id}` expands a Discogs release from the dig into its **real
tracklist** (fetched lazily when the release is opened): each row is a candidate track
with its position, title and duration; Discogs errors surface as an explicit `502`. The
response now also carries `videos: [{ youtube_video_id, title, duration_seconds }]`, the
YouTube videos Discogs already associates with the release.

`preview` resolves an **ephemeral audio preview** for a lead, so it can be evaluated
before acquiring it: query params `artist`, `title`, optional `discogs_id` and `level`
(`release`|`track`, default `track`). It responds `DiscoveryPreviewOut { kind:
"itunes"|"youtube"|"none", audio_url, youtube_video_id, source_url, matched_title }`.
iTunes Search is the primary source (30s clip); if there is no match, it falls back to
the YouTube video Discogs associates with the release. Provider errors resolve to
`kind: "none"` with `HTTP 200`, never an error status. Nothing is persisted.

`add` imports a candidate into the app's library idempotently. It does not write to
Spotify. The AI, if configured and requested, adds explanations but does not choose
the candidates. `save-for-later` persists a lead without attaching it to a playlist
(same idempotent import).

The old Discovery mode based on playlist gaps has been removed, and so has playlist
expansion: Discovery is now the dig alone, while Gap Analysis stays a separate
read-only endpoint.

Note: Discogs and Spotify-as-resolver are the only providers left in Cratory for
Discovery — they do not provide BPM/key/genre/mood to the library.

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

The job is single-instance (one download at a time, like library indexing): an error
on one track does not stop the others. The UI polls `GET /api/downloads/status` during
execution.

## AI and services

```text
GET /api/ai/status
GET /api/services/status
```

`/api/services/status` returns the aggregate state of the integrations: Spotify, AI,
Discogs (`connected` = `DISCOGS_TOKEN` present; works even without a token, the token
raises the rate limit), slskd and related services.

## Settings

```text
GET /api/settings/language
PUT /api/settings/language
```

Setting persisted in `AppState` (key `language`, no dedicated table: single-user local
app). `GET /api/settings/language` returns `{"language": "it"|"en"}` (default `"it"` if
not set yet). `PUT /api/settings/language` with body `{"language": "it"|"en"}` saves
the choice and returns the same object; `422` on values other than `"it"`/`"en"`.

## Conventions

- Errors via `HTTPException` with a readable `detail`.
- Long operations via jobs and polling.
- Rate limit, retry, cache and fallback live in the `integrations/` or `services/`
  layer, not in the routers.
- Routers must not contain scoring, dedup or ranking logic.
