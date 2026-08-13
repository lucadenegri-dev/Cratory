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
enrichment engine and AcoustID fingerprinting were retired toward Organize, BPM/key now come
only from a Rekordbox XML import, `energy` is derived deterministically). **The Analysis
page is complete**: BPM/key now have two deterministic sources — Rekordbox import
(primary, source-aware overwrite) and in-app analysis via Essentia (alternative,
`/analysis`) — with explicit per-value provenance (`bpm_source`/`key_source`: manual >
rekordbox > cratory) and an explicit apply bridge to the canonical fields. Discovery is
operational (Discogs dig). **The dig's engine was redesigned
(2026-07-16):** the Discogs pile for a seed is sorted by demand (`sort=want`) and
`depth` picks where to fetch a window from it (0.0 = the seed's classics, 1.0 = the
bottom of the crate) — taste always ranks inside that window, it is no longer a mode.
**A second dig source, Bandcamp, was added (2026-07-23):** the engine was generalized
to reason in items behind a `DigSource` protocol (`probe`/`fetch`/`to_lead`), so
Discogs and Bandcamp share the same window/taste/dedup machinery and the user picks
the source per dig. Bandcamp gives up rarity/style signal and unlimited depth (capped
at `reach` = 3,000 items, a cost choice) in exchange for a real per-track stream and a
richer release detail — accepted as noisier by design (see "Suspended / revised"
below). The Set Builder
guarantees owned-only; **its deterministic generator was reworked into two
phases (2026-07-19, phase 1)** — a skeleton (anchors, bomb reserve, genre plan) is built first,
then filled with beam search per segment, same external interface. **An AI curation stage
(phase 2, 2026-07-19)** sits on top when enabled: the AI compiles the intent from the free
prompt, judges mood-fit and suggests anchors, while the engine always sequences; the only
AI axis is curation on/off (`use_ai`), no technical/creative mode. The dashboard shows a five-stage pipeline (Index
moved to a nav button). Mix identification via Shazam is integrated (phase 1; co-occurrence
in backlog). SoundCloud import (playlists/secret links + selective likes) works via yt-dlp.
**Owned tracks are now playable, read-only, for quick audition** (`GET /api/tracks/{id}/audio`,
single shared docked player also used for the Discovery preview, `TrackPlayButton` on track
rows) — one track at a time, no transcoding, no DJ-deck features (waveform/cue/queue stay
with the Set Builder/Rekordbox). **Detail pages now return where you came from**
(2026-07-21): links into a detail page carry a validated internal `?from=<path+query>`, so
the back link restores the origin — library filters included — instead of always falling
back to the library. **Playlists gained a bulk "Sync all"**: one background job realigns
every Spotify and SoundCloud playlist (liked excluded, they grow through the selective
flow); a failing playlist is reported and skipped, never fatal to the rest. **Tracks now
carry a personal 1-3 rating** (`rating`, nullable — NULL means "not rated", available on
every track, owned or not): set via `PATCH /api/tracks/{track_id}` (`null` clears it),
filterable and sortable on `GET /api/tracks` (unvoted tracks always sort last), a small
tie-break bonus in the Set Builder generator (`_RATING_BONUS`, never above compatibility,
never seen by the AI), and a system playlist **"Top"** (`kind="rating_top"`) that stays
deterministically in sync with every track voted `3`. **Playlist management is now
complete** (2026-08-08): rename with `name_locked` (a sync re-reads everything from the
platform except a user-chosen name), drag-and-drop reordering (full-order
`PUT /order`, `manual` and `shazam` kinds), multi-select bulk actions in the detail page
(remove from playlist / add to another), "duplicate as manual" fork for any playlist, a
per-playlist sync history (`playlist_sync_events` + `GET /sync-log`, added/removed
snapshots per event) and export in four formats (`m3u8|csv|text|markdown`).
**Settings folder picker and local file link modal**
(2026-08-07): native macOS dialog for path selection (`GET /api/files/pick/availability`,
`POST /api/files/pick`), "Sfoglia…" button in Settings for `library_root`, `archive_root`,
`slskd_download_dir` (folder pick) and `slskd_config_path` (file pick),
same button in the "Collega file locale" modal next to the "percorso esatto" input (file pick only) —
availability gated by `usePickerAvailability()` hook, shared by both contexts.
**Settings unified post-fusion (2026-08-13):** one external-services source
(`GET /api/services/status`, 7 entries with `optional_env`/`optional_ok`;
`/api/organize/providers` removed), one AI key (`ANTHROPIC_API_KEY`, with `AI_API_KEY`
still read as fallback) shared by the Set Agent and Organize's tag/genre AI, and the
`/settings` page reorganized into 4 groups (Language · Paths & library · External
services · Organize) with inline actions on the service rows (Spotify OAuth, slskd
login, SoundCloud username, AcoustID fingerprint) — the standalone Soulseek/SoundCloud
cards and Organize's duplicate provider list are gone.

**Library shows the file's effective tags (2026-08-13):** for owned tracks, `genre`,
`album`, `label` and `year` now resolve at query time to the physical file's tags first,
falling back to the streaming value (COALESCE over `tracks.primary_file_id` -> `audio_file`,
no derived column); `artist`/`title` stay the streaming identity. The rule applies
everywhere those fields are shown or filtered — Library list/detail, playlists, set
detail/alternatives, transitions, downloads, discovery, CSV/Markdown export, the genres
overview — so what the user sees always matches what they filter on. `TrackEditModal`
saves those four fields to the file via Organize's single writer
(`POST /api/organize/files/{id}/tags`) for owned tracks, everything else via the usual
track PATCH. The two sections cross-link both ways: track detail -> FILES row and back.

Full chronological history lives in [PROGRESS.md](../PROGRESS.md).

## Product direction

Cratory is an **excellent personal/self-hosted tool** for DJs, NOT a public multi-tenant
SaaS. Blocking constraint (verified): the Spotify Web API does not allow a public
Spotify-based SaaS (development mode caps at 5 users / Premium / reduced endpoints; extended
quota mode only for organizations with a launched service and ≥ 250k monthly users). The
value is product quality, not scale.

## Next steps

**The agreed plan is complete** (2026-07-12): Discovery improvement done (taste +
explanations, per-release tracklists; a similarity-based 2nd dig source closed as not
applicable — see below), audit + quick wins done, documentation rework done, and the
whole 2026-07-05 audit backlog cleared (see the historical section below). No committed
next step: new work starts from fresh product ideas, not from this backlog.

**2026-07-19:** the Discovery playlist-expansion flow (similarity-based suggestions plus
a Spotify resolver) was removed entirely, backend to frontend to docs. Discovery is now
the dig ("Scava"/Discogs) alone. This also closes, as not applicable, the backlog item
below that assumed the expansion flow still existed ("similarity tags as a 2nd dig
source").

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
- **Discovery dig engine redesign** — DONE (2026-07-16). The dig used to fetch Discogs
  results with no sort at all: the first 300 releases of a seed with, say, 43,345 total
  — an arbitrary 0.69% sample with not a single release above 1,000 owners and 46%
  under five. Now the pile is sorted by demand (`sort=want`) and `depth` picks the
  window to fetch from it; `novelty`/`demand`/`recency` left the score (inside one
  window `want` is roughly constant, so they could not discriminate leads anyway) and
  taste ranks inside the window unconditionally, not as a mode. Cost: 4-5 Discogs
  requests per dig. See `docs/API.md` (Discovery) and PROGRESS.md for detail.
- **Dig second source: Bandcamp** — DONE (2026-07-23). Added behind a `DigSource`
  protocol (`Seed`/`Pile`/`probe`/`fetch`/`to_lead`,
  `backend/app/services/dig_sources/`): the engine now reasons in items and each source
  translates the `(offset, count)` window into its own pagination — Discogs into page
  numbers, Bandcamp into a sequential cursor walk. `POST /api/discovery/dig` gained
  `source: "discogs" | "bandcamp"` (default `"discogs"`); the response replaced
  `pile_pages` with `pile_total`/`pile_reach`; leads use `source_id`/`source_url`/
  `stream_url` instead of `discogs_id`/`discogs_url`; `GET /api/discovery/release/{id}`
  became `GET /api/discovery/release?source=&id=` (integer ids only — no URL crosses
  the boundary, so there is no SSRF surface and no host allowlist to maintain).
  Accepted limits, by design: Bandcamp has no have/want (no rarity signal), no styles
  in the result list (only in the release detail), a capped `reach` of 3,000 items
  (`BANDCAMP_REACH`, a cost choice — depth costs cursor-walk requests, not a page jump),
  a derived `format_badge` (its one inferred field, from track count), and is overall
  **more noisy** than Discogs (no demand/format/self-released de-noise signal exists on
  Bandcamp). One accepted regression, measured exhaustively: the Discogs window can now
  differ from the retired page-based formula by **up to 2 pages, at any pile height** —
  the new item-based window is more correct (the old one promised depth that short
  piles didn't have), pinned by
  `test_window_stays_within_two_pages_of_the_retired_page_formula`. Bandcamp's
  endpoints are internal and undocumented: if they change, only the Bandcamp source
  breaks (`DigSource` isolates it), diagnosed with the `@pytest.mark.network` contract
  test. See `docs/superpowers/specs/2026-07-22-dig-bandcamp-design.md`, `docs/API.md`,
  `docs/ARCHITECTURE.md`, `docs/DEPENDENCIES.md` and PROGRESS.md for detail.
- **Set Builder: two-phase generator + AI curation** — DONE (2026-07-19), both phases.
  Phase 1: `generate_set()` plans a skeleton first (opening/peak/closing/reset anchors elected
  per strategy, a bomb reserve — top 15% by impact score — freed only in the peak window, a
  genre plan with a principal family at peak and a calmer one elsewhere) and then fills it with
  beam search per segment, instead of one flat beam search over the whole set. Falls back to
  the previous single-phase flow for short expected sets (< 6 tracks) or small pools
  (< 8 candidates). Phase 2: the "AI orders the tracklist" path (`generate_ai_set()`,
  `services/ai_agent.py`, `services/validation.py`'s `validate_ai_set()`) is retired; a new
  `services/ai_curation.py` reads the pool instead of ordering it — intent compilation from the
  free prompt (only for fields the user left open), mood-fit judged in batches of 50 (pool cap
  200, per-call cap 60) feeding the generator as a non-binding scoring term, anchor hints
  (opening/peak/closing) feeding the anchor election as a bonus, and a narrative pass over the
  finished set. Any AI call that fails degrades to the deterministic default with a warning,
  never an error. `use_ai` semantics: `true` = AI curation on, `false` = purely deterministic,
  absent = auto. `generated_by` is now `algorithmic` | `algorithmic+ai_curation` (historical
  sets may read `ai`). Fully deterministic sequencing throughout, same external API. See
  `docs/superpowers/specs/2026-07-19-set-builder-two-phase-ai-curation-design.md`,
  `docs/ARCHITECTURE.md` and PROGRESS.md for detail.
- **Wishlist redesign** — DONE (2026-07-19). `/downloads` → `/wishlist`: every non-owned
  track with its download outcome, playlist provenance, buy links (Bandcamp/Beatport/
  Discogs) and reversible archiving via `PATCH /api/tracks/{id}` (`archived`). See
  `docs/API.md` and PROGRESS.md for detail.
- **Dig refactor** — DONE (2026-07-19). Navigazione: la voce Discovery è rinominata "Dig"
  (route `/discovery` invariata) e la Wishlist passa nel gruppo "Discover" (Dig · Shazam ·
  Wishlist). La ricerca Soulseek libera è in testa alla pagina Wishlist. Rimosso Juno
  Download dai buy-link (negozio non più funzionante). Solo frontend, nessun cambio API.

## Technical backlog (non-blocking)

- **Discovery: enrich the dig.** Tagging the dig from a similarity-based 2nd source is
  **closed as not applicable (2026-07-19)**: the provider it would have relied on was
  removed along with the whole playlist-expansion flow. (Per-release tracklists DONE
  2026-07-12; Genre + Label already unified; Playlist stays Spotify-resolved on
  purpose, a different goal.) Not to be confused with the **Bandcamp dig source** added
  2026-07-23 (see "Suspended / revised" above): that one is a full alternate crate to
  dig from, chosen per request, not a tagging enrichment of the Discogs dig.
- **Shazam phase 2.** `DjSetTrack` as a corpus for co-occurrence suggestions.
- **PostgreSQL.** Low priority: SQLite is enough for personal use (only needed for an
  eventual multi-user setup).

### Audit backlog — **CLEARED 2026-07-12** (historical; per-ID detail in [docs/AUDIT-2026-07-05.md](AUDIT-2026-07-05.md))

**The 2026-07-05 audit backlog is done.** Every actionable item was either implemented (all
verified: TDD on the backend, live browser checks on the UI), resolved by decision (A7
confirmed as-is; dead scores + `POST /transitions/score` removed), consciously parked (tags
from the since-removed similarity provider as a 2nd dig source; the E14 test-fixture dedup —
invasive, low value), or noted as a
minor non-planned residual inside the theme bullets below. E2E presidio added (Playwright
smoke + jobs-provider unit). Final state: backend 842 tests green, frontend 12 e2e + 4 unit
green, lint/tsc/build clean.

What follows is the historical record of the sweep.

Re-triage of the 2026-07-05 audit backlog against the **actual current code** (not the docs,
which had drifted). **Closed since the audit** (removed from the backlog): A1 (set export
M3U/CSV/markdown + real Blob download), A3 (the 7 Set Builder strategies are now genuinely
distinct), A8 (needs_review path persisted + retry/review flow), B5 (path to the editable set
`/sets/[id]`), the dig's per-release tracklists (`get_release_detail`), B16 (label backfill
removed — the Organize section's job), E12-TLS (`tls12_context` is opt-in/unused, not forced).

**Fixed on branch `fix/quick-wins-correttezza-discovery`** (2026-07-12): E8 (`~` expanded in
config paths), E9 (`ci_equals` — exact case-insensitive match with %/_ escaping, wired into
manual/playlist/index matching), A11 (dedup by artist+title+duration in `import_playlist`, so
manual-then-Spotify no longer duplicates), A16 (expand dedups owned variants via the dig's
`_dedup_key`), A27 (Labels→Discovery "dig this label" link). A15 was dropped after review: the
label returns via the own→Organize→index loop, and writing it elsewhere would fight the
Organize section's ownership of that field.

**Fixed on master (incremental, post-triage):** A25 (playlist sync now refreshes name/cover/owner
from the source — Spotify via `get_playlist_meta`, SoundCloud via the fetched `title`/thumbnails;
2026-07-12); A18 (mix with no yt-dlp duration: `probe_duration` ffprobe fallback in
`identify_set`, real duration backfilled into the set meta; 2026-07-12); E5
(`_retry_after_seconds` — Retry-After parsed per RFC 7231, delta-seconds or HTTP-date, never an
exception; 2026-07-12); E1e (selectinload on `Track.playlists` in setlist/transitions/
download-pending); A19 (Soulseek auto-pick filters by confidence first, then score —
`auto_pick_candidates`); A17 (dig: Discogs pagination up to 3 pages + explicit 502
`discovery_provider_error` instead of silent empty results); A28 ("Search on Soulseek" button on
the wishlist track detail, wired to the existing per-track auto-pick endpoint); E12 (the
since-removed similarity provider's client got a compliant User-Agent + 300s in-memory TTL
cache — errors never cached); A23 (energy
in the composite transition score: centered ±7.5/−4.5 correction only when both tracks have
energy, bit-identical scores otherwise); B9 (shared ConfirmModal replaces all 6 native
`window.confirm`); B24 (relative `/api` paths + Next rewrite to `BACKEND_URL` — the app now works
from any LAN device, verified live via network IP); A22 (roles reassigned via the generator's
`assign_roles` + `ai_reason`/`transition_note` cleared for the touched positions after
move/remove); A4 (BPM bands now percentage-based 1.6%/4%/6.5%, anchored to preserve ~128 BPM
behavior, applied on the folded half/double grid too); B26 (Set Builder reads `?playlist=` via
`useSearchParams` + Suspense, live-verified); B14+B27 (job-bar error outcomes persist with a
dismiss ✕, success keeps the 4s; the 2s poller pauses on hidden tabs and catches up on return);
A12 (`added_by` provenance on `playlist_tracks` + idempotent migration — the sync prune never
unlinks 'cratory' memberships, e.g. Discovery adds whose Spotify write-back failed); E7-residual
(`attach_local_file` persists mtime/size so the next incremental index skips the file; the exact
name-match branch no longer steals a file from an owned track); B2 (ownership filter in the
playlist detail table, reusing the Library i18n keys); B15 (Library table: overflow-x wrapper,
sortable headers as real buttons with `aria-sort`, KeyBadge, honest filtered empty state); A5
(candidate anchor = pool median BPM when no BPM constraint — no more 60-slowest degeneracy); E2
(incremental commits every 50 files + guarded per-file `stat()` in `index_library`); A21 (gap
opener/peak thresholds from the playlist's P25/P75, absolute fallback under 8 tracks); E1c
(column ADDs derived from `Base.metadata` — no more hand-maintained dict); E10-partial
(transitions endpoint computes each score once; generator risk thresholds deduplicated into
`risk_from_score`); B1 (filters/sort/offset serialized in the querystring on Library and
Downloads, restored on mount — live-verified); B10 (Spotify import auto-loads with name filter
and covers); B6 (Enter submits TrackEditModal via real form semantics); B18 (Transitions page:
loading/error/zero-results states, errors no longer swallowed); B28 (shared `DownloadOutcome`,
`DownloadItem.track_id` number|null per backend truth, `ButtonLink` replaces nested
`<Link><Button>` in playlists/sets/shazam); A14 ("add this track" in the set editor:
`POST /api/sets/{id}/tracks` with owned-only guarantee + search modal, live-verified); A2+B13
(per-track library cross-match with OWNED/IN LIBRARY badges + save-as-lead, detail polling while
identifying, list shows just-started sets); A20 (byte-progress stall detection: STALL 60s /
HARD 1800s replace the flat 180s wall); E11 (shared raise_for_status/get_json in `_http.py` +
`ClosableHttpClient` on all 4 clients); E12-Shazam (loop+client reused across segments,
30s recognize timeout); B17 (preset applied-values summary line, live-verified); B23 (lazy
covers + 50-row pagination in the playlist detail); B25 (`cn()` with tailwind-merge — caller
classNames now reliably override component defaults); B12 (drag-and-drop reorder with
move-to-position endpoint, arrows kept as keyboard fallback + replace_track note cleanup +
rename-modal form semantics + add-track artist search); B4+B19 (set generation in the global
job bar, shazam state exposed by the provider — no page-local pollers left); A6-UI (library
gaps card on the dashboard, live-verified); E13+E14 (mix_identify_job 10 tests, double-start
guards, OAuth state anti-CSRF, transitions/discovery HTTP coverage, tautological assert fixed,
autouse job-state reset + real-library-scan guard in conftest); backend residuals (archive
stat guard, client close() wiring in discovery/playlists/spotify routers + soulseek job, mix
job state under lock); frontend residuals (instant lead badge, Outcome via Exclude, form
semantics in link-local-file-modal, ButtonLink in playlist detail); E6 (slskd robustness:
best-effort cancel of abandoned transfers and harvested searches, freshest-entry+username
transfer matching, /candidates worst-case ~15s with early-exit on stable results, close() in the
downloads router); OAuth multi-origin bug fixed for real (callback redirects to the FIRST
origin of the FRONTEND_ORIGIN CSV; the strict xfail is now a green test) + close() in
services_status; E10 residuals (file_search 30s TTL cache, pipeline inbox 10s TTL cache, typed
Pydantic responses for generate-async and mix-identify start/status, Discovery `_explain`
validated via Pydantic — rule-5 violation closed); gap texts bilingual (codes+params, `gaps`
i18n namespace, backend description as fallback); A10 (streaming import/sync as a background
job: 202 + `GET /api/playlists/import/status`, one shared slot, per-item progress in the global
job bar, provider errors in the job state — 12 tests converted, 24 new); E10 final tail
(serializer + CSV export reuse the persisted `transition_score` instead of recomputing);
B20+B21+B22 (lib/api.ts → 13-line barrel over lib/api/ modules with zero page-import churn;
`ApiError {status, code}` + shared `errText` replacing 16 duplicated `err()` helpers;
AbortController + stale-response guards on library/downloads/playlist-detail/transitions).
All 2026-07-12.

Legend: **OPEN** = to do; **⚠️** = partial (core done, residual noted). Order is indicative.

- **Discovery** — *(similarity-based 2nd dig source: closed as not applicable, 2026-07-19 — see above.)*
- **Set → console / editor** — (nothing open).
- **Scoring** — **DECIDED (2026-07-12): dead scores removed** (`bpm/key/mood_compatibility_score`
  + `POST /api/transitions/score` deleted with their tests — never called by the app; the
  composite `score_transition` carries the logic). Minor notes, not planned: the generator's
  `_candidate_score` counts energy twice (mild, tests pass); a few text-only consumers still use
  absolute BPM bands (`classify_transition` bpm_close ≤5, `mixing_tip`/`mixing_overview`,
  `validation.py` >8); with ≥8 tracks the P25/P75 gap design makes `missing_openers` nearly
  never fire (by design).
- **Shazam** — (nothing open).
- **Soulseek/download** — **DECIDED (2026-07-12): A7 confirmed as-is** — the manual grab leaves
  the file in the inbox without marking ownership: cataloging is the Organize section's job, ownership comes
  from indexing. ⚠️ B11 issue counters now navigable, but grab has no per-candidate state and
  LinkLocalFileModal search does not auto-start (minor, not planned).
- **Streaming import/sync (Spotify + SoundCloud)** — (nothing open).
- **Library/index** — (nothing open).
- **Frontend technical** — (nothing open).
- **Backend robustness** — (nothing open).
- **Tests** — E15 DONE (2026-07-12): Playwright smoke on 12 routes (dedicated servers
  8211/3211, throwaway e2e DB, `NEXT_DIST_DIR=.next-e2e` to dodge next dev's single-instance
  lock) + 4 Vitest units on the real JobsProvider (`npm run test:e2e` / `test:unit`). E14
  residual (engine/overrides setup copied in ~20 test files → shared fixture) deliberately
  parked: invasive, low value.
- **Cleanup** — DONE (2026-07-12): stale worktree removed (its only salvageable idea — the lock
  on the mix job state — was implemented for real), stale comments in
  `local_files.py`/`scoring.py` updated to the current paradigm, CLAUDE.md rule 2 slimmed
  (mechanics now pointed at docs/API.md). Legacy columns `Track.playlist_id`/`playlist_name`:
  **not droppable** on SQLite (FK baked into `playlist_id`) — not an actionable TODO.
  **Reversal note:** `python-multipart` is needed (rekordbox.xml upload) — do not remove.

## Risks

| Risk | Mitigation |
|---|---|
| Tracks without BPM/key | the track status stays `imported` (unusable by the Set Builder) until a Rekordbox import arrives; no automatic estimation |
| Rate limits or network errors (Discovery providers) | retry/backoff, async jobs |
| Invented AI output | pool/per-call caps, JSON-schema-constrained calls, foreign ids and out-of-bounds values discarded with a warning |
| Spotify recommendation unavailable | Discovery based on Discogs/Bandcamp crate digging |
| Spotify dev-mode limits depth (5 users, `label:` search cap 10) | genre/label depth from Discogs/Bandcamp (open); Spotify only as a resolver |
| Bandcamp's dig endpoints are internal/undocumented and may change without notice | `DigSource` seam isolates it — only the Bandcamp source breaks, Discogs keeps working; diagnosed via the `@pytest.mark.network` contract test |
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
- Discovery dig has two sources, Discogs and Bandcamp, chosen per request behind a
  shared `DigSource` protocol (2026-07-23) — same taste ranking and UI regardless of
  source, adding a third does not require a rewrite of the engine.
- Discovery does not use Spotify `/recommendations`.
- Discovery no longer suggests tracks from playlist gaps; those gaps stay a separate analysis.
- Discovery works by taste, not by technical compatibility: BPM/key/transitions are the Set
  Builder's competence.
- The Shazam module does not populate the library directly: it produces a separate corpus (it
  remains the project's only audio fingerprinting — it identifies external mixes, not the
  library).
- Text metadata enrichment (title/artist/album/label/genre) and on-disk tagging are the Organize section's
  competence, not Cratory's (2026-07 pivot).
- SQLite stays sufficient for local single-user use.
- Disk-first: the library is the disk (`LIBRARY_ROOT`), not the streaming playlists (which stay
  leads). Cratory reads the files to index them but never writes them: tagging and organization
  stay the Organize section's competence.
- Owned files are now playable, read-only, for quick audition (`GET /api/tracks/{id}/audio`,
  single shared docked player, one track at a time): "Cratory does not play audio" no longer
  holds in absolute terms. Still true: no transcoding, no queue/waveform/cue (Set
  Builder/Rekordbox keep those), and the file is never mutated.
- Bilingual IT/EN app (2026-07): language as a persistent setting (default `it`), no per-locale
  routing. UI via a typed TypeScript dictionary; backend errors as stable codes translated by
  the frontend; deterministic phrases and AI output produced in the selected language. `en.ts`
  is the source of truth for the keys.
