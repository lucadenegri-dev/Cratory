# PROGRESS

Cratory is a personal, local/self-hosted, single-user web app to import streaming
playlists, build DJ set drafts on owned tracks, analyze library gaps, discover new
music by taste, and identify mix tracklists via Shazam. It is not a DJ deck and does
not keep third-party audio, aside from the narrow acquisition/preview exceptions
described in `CLAUDE.md`.

## Current state by area

- **Frontend without the Next proxy** (2026-08-22): `CRATORY_STATIC_EXPORT=1`
  builds a static frontend with no `rewrites()`; one shared base URL feeds both
  HTTP clients; the five detail routes read their id from the query string
  instead of the path. Unset, `npm run dev` behaves exactly as before. Step two
  of four toward a Tauri desktop build.
- **Bundle-ready** (2026-08-22): the backend runs entirely from a read-only code
  directory. `CRATORY_DATA_DIR` — same seam shape as `CRATORY_BIN_DIR` and
  `CRATORY_VERSION` — redirects database, logs, caches, managed binaries,
  slskd's own config/downloads/pid/log files and `.env`; unset, nothing
  changes. Step one of four toward a Tauri desktop build.
- **Version and updates** (2026-08-22): the app has a single version (`VERSION` at
  the repository root, `CRATORY_VERSION` overriding it for a packaged build) shown
  in Settings, with a button that compares it against the latest GitHub release.
  Three outcomes kept apart — up to date, update available, could-not-check — and
  the comparison is numeric, so `0.10.0` correctly beats `0.9.0`. Nothing is
  downloaded yet: that arrives with the packaged build, off the same releases.
- **Library**: ownership comes from indexing `LIBRARY_ROOT` on disk (`has_local_file`,
  re-linked by `audio_hash`); streaming playlists (Spotify, SoundCloud) are leads.
  Owned tracks show the physical file's effective tags (genre/album/label/year,
  resolved from the primary file) and are playable read-only, one at a time, through
  the shared bottom player bar (custom transport with seek, prev/next over the
  originating list, auto-advance on owned tracks, OS Media Session).
- **Set Builder**: a deterministic two-phase generator (skeleton first, then beam
  search per segment) always builds the tracklist from owned tracks only; an optional
  AI curation stage judges mood-fit and suggests anchors, never sequences.
- **Discovery**: the "Dig" searches Discogs or Bandcamp by genre/label (taste ranks
  inside a demand-sorted window), with Spotify only as an identity resolver; leads can
  be previewed (iTunes clip / YouTube / Bandcamp stream, ephemeral) before acquisition.
- **Organize** (`/organize`, ex Sortory): the single writer of textual tags — scan,
  issue detection, plan/apply with undo, dedup, provider enrichment
  (MusicBrainz/AcoustID, Discogs, cover art).
- **Analysis**: BPM/key have two deterministic sources, Rekordbox XML import
  (primary) and in-app Essentia analysis (alternative), each with explicit
  provenance (`bpm_source`/`key_source`); `energy` is derived.
- **Shazam**: mix tracklist identification (phase 1) building a corpus of identified
  tracklists; co-occurrence suggestions are backlog.
- **Downloads/Wishlist**: every non-owned track with its download outcome, playlist
  provenance and buy links; acquisition via Soulseek (slskd) or a per-track
  SoundCloud/yt-dlp download links a file back to the existing track. A per-track
  manual Soulseek search (raw slskd results, no variant cascade, no confidence
  filter) lives in a single modal reachable from the wishlist row and the track
  detail page, replacing the old review-only modal. Acquisition runs on a
  persistent SQLite queue, not a single in-memory job: a worker pool
  (`download_slots`, default 3, adjustable in Settings) downloads several tracks
  at once, a circuit breaker pauses and later resumes slskd-dependent work on its
  own if the daemon goes unreachable, and the queue survives a backend restart. Its
  own page, `/downloads`, replaces the redirect that used to send that route back
  to the wishlist; the wishlist itself gained multi-select for batch downloads.

Settings are unified across sections: one external-services endpoint, one AI key
(`ANTHROPIC_API_KEY`), a single `/settings` page.

- **Setup** (2026-08-21): first launch opens a six-step guided wizard (`/setup`) —
  welcome/language, prerequisites, library paths, external services, slskd,
  summary — gated by `GET /api/setup/state` so a down backend never strands the
  user there. A declarative registry (`services/system_probe.py`) detects three
  external binaries — ffmpeg, fpcalc, slskd (yt-dlp and essentia are plain Python
  dependencies pip already installs, not registry entries). `services/binary_manifest.py`
  pins a version/URL/SHA256 per component per platform, and `services/binary_installer.py`
  downloads, verifies, extracts and installs each one — valid only once the binary
  has actually run, since a verified download can still fail to execute. macOS has
  no pinned `ffmpeg` build on purpose (no upstream ships a checksummed native arm64
  static binary): there the installer falls back to running the registry's recipe
  itself (`brew install ffmpeg`, same streamed log, same run-it-to-verify discipline)
  whenever `brew` is present, and only the manual command otherwise — the probe
  payload's `install_method` tells the two routes apart. `services/slskd_daemon.py`
  additionally writes `slskd.yml` (only the four keys it needs, the rest of the
  user's file untouched) and starts/stops the daemon as a detached process, never
  touching one it didn't start itself. Each provider credential (Spotify, Anthropic,
  Discogs, AcoustID) can be tested for real before moving on. Credentials became
  runtime-writable the same way paths/URLs already were (`core/runtime_settings.py`'s
  `SECRET_KEYS`): a key saved from the wizard or from `/settings` (same shared field
  components, so a key can be changed without re-running the wizard) takes effect
  immediately, no restart, and its value never appears in an API response.

## Where to look next

- Full chronological development diary: `docs/archive/PROGRESS-diario-completo.md`.
- Current backlog, open decisions and next steps: `docs/ROADMAP.md`.
