# Roadmap

## Naming

Chosen name: **Cratory** (`crate` + `-ory`, "a repository/archive of crates").

Why:

- it evokes crate digging: the DJ's archive of tracks;
- it fits the editorial brand (archive, monospace, square);
- it is coined and brandable, short and easy in the interface;
- it is more specific and distinctive than "DJ Assistant" (and avoids the collision of the
  old provisional name "SetArc", which already exists).

`cratory.com` availability to be confirmed with a registrar. Legacy technical paths
(`djassistant.db`, log files) are kept unchanged for local compatibility, barring a future
explicit migration.

## Current state

Core streaming-first is complete; **disk-first is complete** (the library is the disk,
streaming playlists = leads); the **disk-first + Rekordbox pivot is complete** (the internal
enrichment engine and AcoustID fingerprinting were retired toward Sortory, BPM/key now come
only from a Rekordbox XML import, `energy` is derived deterministically). **The Analysis
page is complete**: BPM/key now have two deterministic sources — Rekordbox import
(primary, source-aware overwrite) and in-app analysis via Essentia (alternative,
`/analysis`) — with explicit per-value provenance (`bpm_source`/`key_source`: manual >
rekordbox > cratory) and an explicit apply bridge to the canonical fields. Discovery is
operational (Last.fm expand + Discogs dig, now taste-only). The Set Builder
(technical/creative) guarantees owned-only. The dashboard shows a five-stage pipeline (Index
moved to a nav button). Mix identification via Shazam is integrated (phase 1; co-occurrence
in backlog). SoundCloud import (playlists/secret links + selective likes) works via yt-dlp.

Full chronological history lives in [PROGRESS.md](../PROGRESS.md).

## Product direction

Cratory is an **excellent personal/self-hosted tool** for DJs, NOT a public multi-tenant
SaaS. Blocking constraint (verified): the Spotify Web API does not allow a public
Spotify-based SaaS (development mode caps at 5 users / Premium / reduced endpoints; extended
quota mode only for organizations with a launched service and ≥ 250k monthly users). The
value is product quality, not scale.

## Next steps

In the agreed order (operational detail in [PROGRESS.md](../PROGRESS.md)):

1. **Discovery improvement.** The taste + explanations slice of the dig is **DONE** (taste
   signals on a selectable reference + reason-code chips). Per-release tracklists are also
   **DONE** (2026-07-12, `get_release_detail`). Last.fm tags as a 2nd dig source is **parked**
   (deprioritized on 2026-07-12, not planned for now); the expand/dig unification is superseded
   (Discovery is DIG-only, expand
   lives in the Playlist context on purpose).
2. **Light audit + quick wins** — the main quick wins are DONE (SSRF, `library_stats`, dead
   endpoint, dependencies); robustness confirmed solid. Small threat model (no public users),
   no SaaS-style authz.

(The documentation rework, the third agreed step, is complete.)

## Suspended / revised

- **Pagina Analisi (import Rekordbox + analisi in-app)** — DONE (2026-07-12). BPM/key data on
  owned tracks now has two deterministic sources with explicit provenance
  (`bpm_source`/`key_source`: manual > rekordbox > cratory): the Rekordbox XML import (now
  source-aware, reclaims `cratory` values, protects `manual`) and a new in-app analysis via
  Essentia (`/api/analysis/*`, page `/analysis`), which writes staging `analysis_*` fields and
  reaches the canonical fields only through an explicit apply. Cratory still never asks an AI
  for BPM/key. (See "Settled decisions" and PROGRESS.)
- **Copy + multi-language (IT/EN)** — DONE (2026-07-12). The app is bilingual with a persistent
  language toggle: UI dictionary, backend error codes, deterministic phrases and AI output are
  all localized. (See "Settled decisions" and PROGRESS.)
- **Public multi-account** — suspended (Spotify wall + personal direction). A possible future
  reshape = a small self-hosted crew with their own Spotify credentials, only if needed.
- **Pitch** — to be reframed around the product's real nature (not a "Spotify SaaS").
- **Name change** — DONE (Cratory). Only `cratory.com` remains to be confirmed with a
  registrar.

## Technical backlog (non-blocking)

- **Discovery: enrich the dig.** Last.fm tags as a 2nd source is **parked** (deprioritized
  2026-07-12, not planned for now). (Per-release tracklists DONE 2026-07-12; Genre + Label
  already unified; Playlist stays Spotify-resolved on purpose, a different goal.)
- **Shazam phase 2.** `DjSetTrack` as a corpus for co-occurrence suggestions.
- **PostgreSQL.** Low priority: SQLite is enough for personal use (only needed for an
  eventual multi-user setup).

### Audit backlog (re-verified against the code on 2026-07-12 — per-ID detail in [docs/AUDIT-2026-07-05.md](AUDIT-2026-07-05.md))

Re-triage of the 2026-07-05 audit backlog against the **actual current code** (not the docs,
which had drifted). **Closed since the audit** (removed from the backlog): A1 (set export
M3U/CSV/markdown + real Blob download), A3 (the 7 Set Builder strategies are now genuinely
distinct), A8 (needs_review path persisted + retry/review flow), B5 (path to the editable set
`/sets/[id]`), the dig's per-release tracklists (`get_release_detail`), B16 (label backfill
removed — Sortory's job), E12-TLS (`tls12_context` is opt-in/unused, not forced).

**Fixed on branch `fix/quick-wins-correttezza-discovery`** (2026-07-12): E8 (`~` expanded in
config paths), E9 (`ci_equals` — exact case-insensitive match with %/_ escaping, wired into
manual/playlist/index matching), A11 (dedup by artist+title+duration in `import_playlist`, so
manual-then-Spotify no longer duplicates), A16 (expand dedups owned variants via the dig's
`_dedup_key`), A27 (Labels→Discovery "dig this label" link). A15 was dropped after review: the
label returns via the own→Sortory→index loop, and writing it in Cratory would fight Sortory's
ownership of that field.

**Fixed on master (incremental, post-triage):** A25 (playlist sync now refreshes name/cover/owner
from the source — Spotify via `get_playlist_meta`, SoundCloud via the fetched `title`/thumbnails;
2026-07-12); A18 (mix with no yt-dlp duration: `probe_duration` ffprobe fallback in
`identify_set`, real duration backfilled into the set meta; 2026-07-12); E5
(`_retry_after_seconds` — Retry-After parsed per RFC 7231, delta-seconds or HTTP-date, never an
exception; 2026-07-12); E1e (selectinload on `Track.playlists` in setlist/transitions/
download-pending); A19 (Soulseek auto-pick filters by confidence first, then score —
`auto_pick_candidates`); A17 (dig: Discogs pagination up to 3 pages + explicit 502
`discovery_provider_error` instead of silent empty results); A28 ("Search on Soulseek" button on
the wishlist track detail, wired to the existing per-track auto-pick endpoint); E12 (Last.fm
User-Agent per ToS + 300s in-memory TTL cache on the client — errors never cached); A23 (energy
in the composite transition score: centered ±7.5/−4.5 correction only when both tracks have
energy, bit-identical scores otherwise); B9 (shared ConfirmModal replaces all 6 native
`window.confirm`); B24 (relative `/api` paths + Next rewrite to `BACKEND_URL` — the app now works
from any LAN device, verified live via network IP). All 2026-07-12, TDD on the backend + live
browser checks for the UI items.

Legend: **OPEN** = to do; **⚠️** = partial (core done, residual noted). Order is indicative.

- **Discovery** — *(Last.fm tags as a 2nd dig source: parked, see above.)*
- **Set → console / editor** — A14 "add this track" in the editor (only delete/move/replace);
  ⚠️ A22 after move/remove the AI roles and `ai_reason`/notes stay stale (transitions *are*
  recomputed); ⚠️ B12 reorder is now optimistic but still arrow-buttons, no drag-and-drop;
  ⚠️ B17 preset is highlighted but with no summary of the applied values (they live in a
  collapsed "Advanced options" panel).
- **Scoring** — ⚠️ A4 half/double-time is implemented but thresholds are still absolute
  (±2/±5/±8), not %; ⚠️ A5 stratified sampling done but degenerates without a BPM constraint
  (still picks the 60 lowest-BPM tracks); A21 gap thresholds still fixed/house-centric (derive
  from percentiles); dead code `bpm/key/mood_compatibility_score` (tests-only) + `POST
  /api/transitions/score` (never called): remove or document as a block; (new, from A23) the
  generator's `_candidate_score` now counts energy twice — via the energy-aware
  `score_transition` AND its own `_feature_fit` term — mild, tests pass, but worth deduplicating.
- **Shazam** — ⚠️ A2 set→playlist import done, but per-track library cross-match
  (IN LIBRARY/OWNED/NEW) + per-track save-lead still missing; B13 detail UX (no polling while
  running, h1 off-system, just-started set absent from the list, native confirm).
- **Soulseek/download** — ⚠️ A7 manual grab does not mark ownership (file in inbox, counts
  "downloaded") — now an intentional flow (Sortory catalogs), confirm as a decision; A20 fixed
  180s DOWNLOAD_TIMEOUT wall (needs byte-progress stall detection; only a queue-patience guard
  exists); E6 slskd (no cancel of transfers/searches, filename-only match, basename+mtime
  resolution, ~45s synchronous on /candidates); ⚠️ B11 issue counters now navigable, but grab
  has no per-candidate state and LinkLocalFileModal search does not auto-start.
- **Streaming import/sync (Spotify + SoundCloud)** — A10 import/sync synchronous in the request
  (thousands of liked = minutes with no progress): job+polling; A12 sync unlinks Discovery-added
  tracks (no `added_by` provenance column exists). NB: SoundCloud import (yt-dlp) now exists too —
  A10 applies to it as well (the flat extraction is sequential/slow); A11 dedup and A25 name/cover
  refresh are already platform-agnostic (both covered for Spotify + SoundCloud).
- **Library/index** — A6-UI library gaps not shown in the dashboard (reintroduce the
  `libraryGaps` client); ⚠️ B2 per-row ownership badge present, but the ownership *filter* in the
  playlist table is missing; B1 filters/sort/pagination lost on back-nav (serialize into the
  querystring: /library, /downloads); B10 Spotify import ("Carica" only on click, no filter, no
  artwork); B15 Library table (no overflow-x, headers not a11y, KeyBadge unused, misleading empty
  state with active filters); ⚠️ E7 duplicate-ownership guard done, but `attach_local_file` still
  saves no mtime/size (re-hash on reindex) and one fuzzy `ilike` branch is unguarded.
- **Frontend technical** — B6 Modal has no Enter-to-submit in TrackEditModal (saves only via
  button); B14 job-bar errors vanish after 4s (persist + dismiss); ⚠️ B18 loading/empty/error
  states: Labels ok, Transitions still weak (swallows errors); ⚠️ B19 settings poller removed,
  but shazam is not exposed by the provider and set-builder still self-polls; B20 zero
  AbortController/sequence guards (stale responses); B21 `api.ts` monolith (965 lines, 131
  exports): split; B22 no `ApiError` with status, `err()` duplicated in ~16 files; ⚠️ B23 cover
  fallback centralized, but zero lazy-load and playlist detail without pagination/virtualization;
  B25 `cn()` without tailwind-merge; B26 Set Builder reads `?playlist=` from `window.location` →
  useSearchParams;
  B27 poller always active even on a hidden tab → visibilitychange; B28 types
  (`DownloadOutcome` not shared, `track_id` nullability inconsistent, nested `<Link><Button>` →
  ButtonLink).
- **Backend robustness** — E1c migrations `additions` dict still manual (the drop is already
  model-derived); ⚠️ E2 job-state copy done, but `index_library` is still one transaction + an
  unguarded per-file `stat()`; E10 (residual): transitions recompute each score twice, `file_search`
  materializes the tree per keystroke, generate-async/mix_identify return untyped dicts,
  Discovery `_explain` without Pydantic (the one spot outside rule 5), duplicate risk thresholds
  scoring/generator (pipeline reduced to 1 walk, still no TTL cache); ⚠️ E11 only transport
  retry centralized, 429/UA/retry still duplicated across the 4 clients + httpx clients never
  closed; E12 (residual): Shazam new event loop+session per segment, no timeout.
- **Tests** — E13 gaps: `mix_identify_job` zero coverage, job double-start guard untested,
  Spotify OAuth callback (anti-CSRF state) untested, transitions/discovery routers with no HTTP
  coverage; E14 tautological `or True` assert in test_set_editing, engine/overrides setup copied
  in ~20 files → shared fixture, module-global job state never reset; E15 frontend has no tests
  (minimum = Playwright smoke + a jobs-provider merge unit).
- **Cleanup** — stale worktree `.claude/worktrees/compassionate-montalcini-c29d1a` (2 files, one
  is the removed `enrichment_job.py`) → 1-min inspection + `git worktree remove --force`; trim
  the redundancy of CLAUDE.md rules 2/7; stale comments in `local_files.py`/`scoring.py`. Legacy
  columns `Track.playlist_id`/`playlist_name`: **not droppable** on SQLite (FK baked into
  `playlist_id`) — they stay empty in the schema, not an actionable TODO. `Track.release_date`
  and the dead `rekordboxPending`/`libraryGaps` api.ts exports were already removed (2026-07-08).
  **Reversal note:** `python-multipart` is needed (rekordbox.xml upload) — do not remove.

## Risks

| Risk | Mitigation |
|---|---|
| Tracks without BPM/key | the track status stays `imported` (unusable by the Set Builder) until a Rekordbox import arrives; no automatic estimation |
| Rate limits or network errors (Discovery providers) | retry/backoff, async jobs |
| Invented AI output | candidate cap, Pydantic schema, Validation Engine |
| Spotify recommendation unavailable | Discovery based on Last.fm and the Spotify `/search` resolver |
| Spotify dev-mode limits depth (5 users, `label:` search cap 10) | genre/label depth from Discogs (open); Spotify only as a resolver |
| Product rename breaks data paths | legacy paths kept, migration only if explicit |
| Rekordbox import misaligned (path/hash/name do not match) | three match levels (NFC path → audio_hash gated on basename → artist+title), report with an `unmatched` count |

## Settled decisions

- Cratory is a personal/self-hosted tool, not a public SaaS (Spotify policy wall).
- Rekordbox is back in the project (2026-07 pivot) but only as a source for BPM/key import via
  XML export — the old scope does not return (beatgrid/cue stay out, no live integration with
  the Rekordbox app).
- BPM/key (2026-07-12): Rekordbox import is the primary source, in-app analysis via Essentia
  (`/analysis`) is the deterministic alternative — never an AI. Every value carries an explicit
  source (`bpm_source`/`key_source`: manual > rekordbox > cratory) so the two sources and
  manual corrections never silently overwrite each other.
- Spotify is a source of identity/metadata, not of mixing features.
- Discovery: genre/label depth from Discogs (open); Spotify stays only an identity resolver
  (at save time).
- Discovery does not use Spotify `/recommendations`.
- Discovery no longer suggests tracks from playlist gaps; those gaps stay a separate analysis.
- Discovery works by taste, not by technical compatibility: BPM/key/transitions are the Set
  Builder's competence.
- The Shazam module does not populate the library directly: it produces a separate corpus (it
  remains the project's only audio fingerprinting — it identifies external mixes, not the
  library).
- Text metadata enrichment (title/artist/album/label/genre) and on-disk tagging are Sortory's
  competence, not Cratory's (2026-07 pivot).
- SQLite stays sufficient for local single-user use.
- Disk-first: the library is the disk (`LIBRARY_ROOT`), not the streaming playlists (which stay
  leads). Cratory reads the files to index them but never writes them: tagging and organization
  stay Sortory's competence.
- Bilingual IT/EN app (2026-07): language as a persistent setting (default `it`), no per-locale
  routing. UI via a typed TypeScript dictionary; backend errors as stable codes translated by
  the frontend; deterministic phrases and AI output produced in the selected language. `en.ts`
  is the source of truth for the keys.
