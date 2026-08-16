# PROGRESS

Cratory is a personal, local/self-hosted, single-user web app to import streaming
playlists, build DJ set drafts on owned tracks, analyze library gaps, discover new
music by taste, and identify mix tracklists via Shazam. It is not a DJ deck and does
not keep third-party audio, aside from the narrow acquisition/preview exceptions
described in `CLAUDE.md`.

## Current state by area

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

## Where to look next

- Full chronological development diary: `docs/archive/PROGRESS-diario-completo.md`.
- Current backlog, open decisions and next steps: `docs/ROADMAP.md`.
