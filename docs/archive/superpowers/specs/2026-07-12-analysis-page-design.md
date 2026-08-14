# Design: "Analysis" page — Rekordbox import + in-app BPM/key analysis

Date: 2026-07-12
Status: approved by user (pending written-spec review)

## Goal

A new frontend page **Analisi** (`/analysis`) that unifies the two ways BPM/key enter
Cratory:

1. **Rekordbox XML import** (moved here from the dashboard pipeline strip).
2. **In-app analysis** of owned local files (new), powered by Essentia, as a full
   alternative to Rekordbox — not just a fallback.

Every BPM/key value carries an explicit **provenance** (`manual` > `rekordbox` >
`cratory`), and the page shows a **divergence comparison** between the in-app analysis
and the current canonical values, with per-track and bulk apply.

This deliberately amends non-negotiable rule #2 in `CLAUDE.md` ("Cratory never
estimates or invents BPM/key"). New formulation: *Rekordbox is the primary source;
Cratory may analyze audio in-app deterministically, with explicit provenance and the
source hierarchy manual > rekordbox > cratory. Cratory still never asks an AI for
BPM/key.* `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md` are
updated as part of this work.

## Data model (Track)

New columns, added via the existing idempotent migration pattern in `db.py`:

| Column | Type | Meaning |
|---|---|---|
| `bpm_source` | `str \| None` | `'rekordbox' \| 'cratory' \| 'manual'`; null iff `bpm` is null |
| `key_source` | `str \| None` | same, for `camelot_key` |
| `analysis_bpm` | `float \| None` | last in-app analysis result |
| `analysis_camelot` | `str \| None` | last in-app analysis result (Camelot, canonical `7A` form) |
| `analyzed_at` | `datetime \| None` | when the in-app analysis last ran for this track |
| `analysis_error` | `str \| None` | per-track failure code from the last run (null on success) |

Backfill: existing non-null `bpm`/`camelot_key` values get source `'rekordbox'`
(the only historical import source; a value that was actually a manual fix gets
re-labeled on its next manual edit).

**Separation rule:** the analysis job writes ONLY `analysis_*` columns. Canonical
`bpm`/`camelot_key` change only through: manual edit, Rekordbox import, or an
explicit/auto apply step. Analysis is therefore always non-destructive and the
divergence view needs no extra bookkeeping.

### Precedence rules (manual > rekordbox > cratory)

- **Manual edit** (existing endpoint in `routers/tracks.py`): sets the value and
  `source='manual'`.
- **Rekordbox import** (`services/rekordbox_import.py`, made source-aware):
  - default: writes a field if it is empty **or** its source is `'cratory'`;
    never touches `'manual'` values;
  - `?overwrite=true`: writes regardless of source (explicit user intent, same as
    today). A value absent from the XML still never nulls an existing value.
  - Every write sets `source='rekordbox'`.
- **Apply analysis**: copies `analysis_bpm`/`analysis_camelot` into
  `bpm`/`camelot_key` and sets `source='cratory'`. Three paths:
  - **Auto-apply after the job**, only for tracks whose `bpm`/`camelot_key` were
    empty (no conflict possible — the "fallback" behavior is automatic).
  - **Explicit apply** from the divergence table (per-row or selected rows).
  - **Force apply** (`mode='all', force=true`): bulk rewrite of ALL analyzed tracks,
    overwriting any source including `'manual'`. Guarded by a UI confirmation.
    This is the deliberate exception to the hierarchy, analogous to
    `?overwrite=true` on the Rekordbox import.
- Every apply recomputes estimated energy (`apply_estimated_energy`) and
  `refresh_status()` (a track may become `ready_for_set`).

## Backend

### Engine adapter — `integrations/essentia_engine.py`

- Interface-style adapter like other integrations: `analyze(path) -> AnalysisResult`
  with `bpm: float` and `camelot: str`.
- Implementation: Essentia `MonoLoader` (own decoding — mp3/flac/aiff/wav, no ffmpeg
  shell-out), `RhythmExtractor2013(method='multifeature')` for BPM,
  `KeyExtractor(profileType='edma')` for key, converted with the existing
  `pitch_to_camelot()` in `services/camelot.py`.
- **Lazy import**: `import essentia` happens inside the module functions; the app
  starts fine without the library. Missing engine surfaces as the API error
  `analysis_engine_unavailable`, never a crash.
- Dependency: `essentia==2.1b6.dev1389` pinned in `requirements.txt` (verified
  cp311 macosx arm64 wheel; pin comment explains the rolling-dev versioning and
  AGPL-3.0 license note — irrelevant for personal self-hosted use).

### Job — `services/audio_analysis_job.py`

Same pattern as `library_index_job.py` / `soulseek_download_job.py`:

- module-level `_state` dict + `_lock`, daemon thread, one job at a time,
  `job_state()` snapshot with `status: idle|running|done|error`, `processed`,
  `total`, `failed`, `applied` (auto-applied count), `current_label`,
  `started_at`/`finished_at`, `error`.
- Scope: `'missing'` (owned tracks lacking bpm OR key), `'all'` (all owned tracks),
  or explicit `track_ids` (single-track re-analysis).
- Only `has_local_file=true` tracks. Per-track try/except: failures store an error
  code in `analysis_error` and the job continues (downloads pattern).
- After the batch: auto-apply on empty fields (see precedence), energy recalibration
  is NOT triggered here (computed energy already comes from the index job; only the
  estimated-energy derivation runs on applied tracks).

### API — new router `routers/analysis.py`

| Endpoint | Behavior |
|---|---|
| `GET /api/analysis/overview` | coverage: owned count, ready_for_set, missing bpm/key, per-source breakdown, analyzed count, divergence count, Rekordbox pending count |
| `POST /api/analysis/start` | body `{scope: 'missing'\|'all', track_ids?: int[]}` → 202; 409 `analysis_already_running` if busy; 503 `analysis_engine_unavailable` if Essentia missing |
| `GET /api/analysis/status` | job snapshot for the global poller |
| `GET /api/analysis/divergences` | tracks where `analysis_*` differs from canonical values: both values, sources, BPM delta, Camelot distance via existing `camelot_compatibility()` (lets the UI flag harmless vs real divergences) |
| `POST /api/analysis/apply` | body `{track_ids: int[]}` or `{mode: 'divergent'}` or `{mode: 'all', force: true}` → apply report `{applied, skipped}` |

`POST /api/rekordbox/import` stays in its router, gains source-awareness.
`GET /api/rekordbox/pending` stays; overview aggregates it.

Divergence definition: a track diverges when it has both an analysis value and a
canonical value and they differ — BPM compared after rounding to 1 decimal, key
compared as canonical Camelot strings.

## Frontend

- **New page** `frontend/app/analysis/page.tsx`; nav entry in the **Collect** group
  next to Library (`components/index-nav.tsx`), i18n label "Analisi"/"Analysis".
- Page layout, top to bottom:
  1. **Coverage tiles**: owned, ready_for_set, missing bpm/key, per-source counts.
  2. **Rekordbox import card**: the existing `RekordboxImportPanel` moves here
     nearly unchanged (file input, overwrite checkbox, report grid).
  3. **In-app analysis card**: scope choice (missing/all), start button, engine
     status; job progress rides the existing global jobs bar.
  4. **Divergence table**: track (artist — title), current value with source badge,
     Cratory value, BPM delta, Camelot distance with a "compatible/divergent"
     badge, per-row apply, row selection with "apply selected", and a
     **"force apply all"** action behind a confirmation dialog.
- **Dashboard**: the "Analizza" stage of `PipelineStrip`
  (`components/dashboard/pipeline.tsx`) becomes a link to `/analysis`; the inline
  panel is removed. Single entry point, no duplication.
- **Jobs provider** (`components/jobs-provider.tsx`): add `analysisStatus()` to the
  parallel poll; the terminal-style `EqMeter` bar works unchanged.
- **API client** (`lib/api.ts`): `analysisOverview()`, `startAnalysis()`,
  `analysisStatus()`, `analysisDivergences()`, `applyAnalysis()`, types for the
  reports.
- **i18n**: new `analysis` section in `en.ts`/`it.ts`; error codes
  `analysis_engine_unavailable`, `analysis_already_running`,
  `analysis_no_local_file`, `analysis_decode_failed`.

## Errors and edge cases

- Essentia not installed → 503 `analysis_engine_unavailable`; the analysis card
  shows the message and a short setup hint instead of the start button.
- Corrupt/missing file → per-track `analysis_error` (`analysis_decode_failed` /
  `analysis_no_local_file`), job continues, failure count in the job report.
- Concurrency: one analysis job at a time (409). The job only reads audio files —
  safe alongside the library index job; no cross-job lock needed.
- Tracks without a local file are excluded from every scope.
- No file mutation ever: tags remain Sortory's job.

## Testing

- **Precedence/apply logic**: pure service tests with a fake engine — rekordbox
  import over cratory/manual values (default and overwrite), auto-apply on empty,
  explicit apply, force apply, divergence computation, energy/status refresh.
- **Engine adapter**: one test generating a short synthetic audio file (known tempo
  click track), `pytest.mark.skipif` when Essentia is not importable.
- **Router tests**: start/409/status/divergences/apply following existing test
  patterns in `backend/tests/`.

## Out of scope

- Confidence scores from Essentia (key strength, beat confidence) — possible later
  addition to the divergence table; columns are easy to add with the same migration
  pattern.
- Waveform/beatgrid, cue points, live Rekordbox integration (unchanged project
  non-goals).
- Any AI involvement in analysis: the whole pipeline is deterministic engine code.
