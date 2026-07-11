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
only from a Rekordbox XML import, `energy` is derived deterministically). Discovery is
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
   signals on a selectable reference + reason-code chips). Still in the technical backlog:
   the dig's extra sources (Last.fm tags, per-release tracklists); the expand/dig unification
   is superseded (Discovery is DIG-only, expand lives in the Playlist context on purpose).
2. **Light audit + quick wins** — the main quick wins are DONE (SSRF, `library_stats`, dead
   endpoint, dependencies); robustness confirmed solid. Small threat model (no public users),
   no SaaS-style authz.

(The documentation rework, the third agreed step, is complete.)

## Suspended / revised

- **Copy + multi-language (English)** — suspended (deferred). String extraction for i18n and
  a page-by-page copy/microcopy review; the Cratory name rollout is already done.
- **Public multi-account** — suspended (Spotify wall + personal direction). A possible future
  reshape = a small self-hosted crew with their own Spotify credentials, only if needed.
- **Pitch** — to be reframed around the product's real nature (not a "Spotify SaaS").
- **Name change** — DONE (Cratory). Only `cratory.com` remains to be confirmed with a
  registrar.

## Technical backlog (non-blocking)

- **Discovery: enrich the dig.** Per-release tracklists (expand a release into its tracks)
  and Last.fm tags as a 2nd source. (Genre + Label already unified; Playlist stays
  Spotify-resolved on purpose, a different goal.)
- **Shazam phase 2.** `DjSetTrack` as a corpus for co-occurrence suggestions.
- **PostgreSQL.** Low priority: SQLite is enough for personal use (only needed for an
  eventual multi-user setup).

### Audit backlog (post-pivot triage — per-ID detail in [docs/AUDIT-2026-07-05.md](AUDIT-2026-07-05.md))

~70 still-valid items from the 2026-07-05 multi-agent audit, re-triaged on 2026-07-06 after
the pivot (9 already resolved, ~12 obsolete, 4 migrated to Sortory). By theme, in indicative
order of value:

- **Close the set → console flow** — A1 M3U/CSV export with `local_path` (even more sensible
  post-pivot: real BPM/key), A14 "add track" in the editor, B4/B5 set generation in the job
  bar + path to the set, A22 stale roles/notes, B12 drag-and-drop reordering, B17 presets with
  a summary.
- **Shazam** — A2 phase 2 "lite" (library badge + save lead), A18 ffprobe fallback, B13 detail
  UX, E13 test coverage for `mix_identify_job`.
- **Soulseek/download** — A7 ownership not marked on ISRC dedup, A8 needs_review without a path
  + retry loop, A19 auto-pick by confidence, A20 stall detection, E6 (cancel transfer, historic
  match log, synchronous waits), B11 per-candidate feedback.
- **Spotify import/sync** — A10 job+polling, A11 level-3 dedup, A12 Discovery membership
  protection, A25 name/cover, E13 OAuth/integration tests.
- **Discovery** — A15 leads that drop label/style/year, A16 variant dedup in expand, A17 Discogs
  pagination + explicit errors, A27 Labels→Scava link, E12 expand/dig cache, E10 `_explain` with
  Pydantic.
- **Set Builder/scoring** — A3 no-op strategies, A4 half/double-time + % thresholds, A5 AI
  candidate ranking, A21 gap thresholds from percentiles, A23 energy in the score (now that it is
  derived from real BPM), the kept C items (scores used only by the tests + dead
  `mood_coherence_score`: decide as a block).
- **Library/index** — E7 fuzzy-steal + mtime/size on attach, A28 "Search on Soulseek" from the
  detail, A6-UI gaps in the dashboard, B1 filters in the querystring, B2 per-row ownership badge,
  B15 table (overflow/a11y/empty), B8 unified status labels.
- **Backend robustness** — E2 `index_library` (incremental commit, per-file guards, job state
  copy), E8 `expanduser` on config paths, E9 ilike escaping, E10 (transitions double compute,
  pipeline 2 FS walks with a TTL cache, `file_search`, `backfill_labels` that does not converge),
  E5-residual Retry-After, E1c/E1e (additions from the model, selectinload N+1).
- **Frontend technical** — B24 relative API URL (prerequisite for LAN use), B19/B27 pollers
  (shazam in the provider, visibilitychange), B20 AbortController, B21/B22 split api.ts +
  ApiError, B23 images/virtualization, B25/B26/B28, B9/B10/B14/B16/B18 minor UX, E15 Playwright
  smoke.
- **Cleanup** — legacy columns `Track.playlist_id`/`playlist_name`: **not droppable** on SQLite
  (FK baked into `playlist_id` → would require a rebuild of `tracks`, which the project avoids);
  they stay in the schema but dead and empty. `Track.release_date` dropped (2026-07-08), dead
  exports `rekordboxPending`/`libraryGaps` in api.ts removed (2026-07-08). Remaining: stale
  worktree `compassionate-montalcini` to remove, trim the redundancy of CLAUDE.md rules 2/7, stale
  comments in `local_files.py`/`scoring.py`. **Reversal note:** `python-multipart` is now needed
  (rekordbox.xml upload) — do not remove.

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
