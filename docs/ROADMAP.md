# Roadmap

## Current state

What Cratory does today, by area. For how it's built, see `docs/ARCHITECTURE.md`; for
endpoints, `docs/API.md`.

- **Library & import.** Ownership comes from indexing `LIBRARY_ROOT` on disk
  (`has_local_file`, re-linked by `audio_hash` so renames and retags don't break it);
  Spotify/SoundCloud playlists and pasted text are leads until a file backs them.
  De-duplication runs ISRC → platform id → artist/title/duration → fuzzy match. For
  owned tracks, `genre`/`album`/`label`/`year` resolve from the physical file's tags
  first (COALESCE over `primary_file_id` → `AudioFile`) everywhere those fields are
  shown or filtered; `artist`/`title` stay the streaming identity. `Track.genre` is
  kept as a mirror of that effective tag by `services/genre_align.align_track_genre`,
  called from every write path (Organize's manual edit, scan, apply, library indexing,
  acquisition). Owned tracks are playable, read-only, one at a time, through a shared
  bottom player bar (`GET /api/tracks/{id}/audio`; custom transport with seek,
  prev/next over the originating list, auto-advance on owned tracks, Media Session) —
  playback never touches the file or its tags.
- **BPM & key.** Two deterministic sources with explicit provenance
  (`bpm_source`/`key_source`: `manual` > `rekordbox` > `cratory`): a Rekordbox XML
  import (`POST /api/rekordbox/import`, three-level match — NFC-normalized path →
  `audio_hash` → fuzzy artist+title — with a source-aware overwrite that protects
  manual corrections) and in-app analysis via Essentia (`/analysis`, writes staging
  `analysis_*` fields and reaches the canonical fields only through an explicit
  apply). `energy` is a deterministic derivative (estimated from BPM+genre, or
  computed from the audio itself). Cratory never asks an AI for BPM or key.
- **Set Builder.** A deterministic two-phase generator — a skeleton of
  opening/peak/closing/reset anchors and a genre arc first, then a beam search per
  segment — always builds the tracklist from owned tracks only. An optional AI
  curation stage (`use_ai`) compiles intent from the free prompt, judges mood-fit in
  batches and suggests anchors as non-binding scoring terms; it never sequences. A
  personal 1–3 `rating` gives a small tie-break bonus in the generator and keeps a
  system "Top" playlist in sync with every track voted 3. Export as text, CSV,
  Markdown or M3U8, or push the set to Spotify as a playlist.
- **Transitions & gap analysis.** `/api/transitions` classifies a pair of tracks
  (technically safe, a creative risk, or a good reset); `services/gap_analysis.py`
  reads a playlist for structural holes — no openers, no peak, missing BPM bridges,
  flat energy, harmonic dead ends.
- **Discovery ("Dig").** Seeds on one to four genres and/or labels (the union of
  their piles, with the 300-item window split between them) and digs into Discogs or
  Bandcamp behind a shared `DigSource` protocol, chosen per request; the source's
  pile is sorted by demand and `depth` picks a window to fetch from it, with taste
  ranking (familiarity + label + style) inside that window. A lead can be previewed
  before acquisition — an iTunes 30-second clip, falling back to the YouTube video
  Discogs associates with the release, or Bandcamp's own per-track stream when the
  lead came from there — and nothing is ever downloaded or kept. Spotify is only an
  identity resolver; `/recommendations` is never used.
  From a track you own, **"Similar"** (`/discovery?similar=<track_id>`) digs the
  graph around it on Bandcamp instead of a genre seed: the rest of the artist's
  discography, the label's, and — behind a switch — the same style within ±3 years.
  Resolution degrades explicitly (`release` → `artist_only` → no origin at all) and
  each edge reports its lead count or why it was not walked.
  The "Similar" search is reachable from the Dig bar too (mode "Track", a free-text
  search over the library); the dig's per-artist cap exempts the artist edge, which
  is one artist by construction. Discogs can be hidden as a dig source from Settings
  (UI preference, default on; Organize's own Discogs client is untouched).
- **Acquisition & Wishlist.** Every non-owned track carries its download outcome,
  playlist provenance and buy links (Bandcamp, Beatport, Discogs); archiving is
  reversible. The wishlist supports multi-select, for batch actions alongside the
  existing per-row ones. Acquisition runs through the user's own slskd (Soulseek)
  daemon — deterministic ranking by quality, name match and availability,
  auto-pick above a confidence floor or a manual pick — through a **persistent
  download queue** with its own page (`/downloads`), replacing the old
  one-job-at-a-time model: a worker pool `download_slots` wide (Settings, default
  3, hot-reloaded) downloads several tracks in parallel, best-effort per item, with
  a circuit breaker that pauses slskd-dependent work — and reopens it on its own
  once the daemon answers again — if slskd becomes unreachable, and a queue that
  survives a backend restart (in-flight items resume as `queued`, not lost). A
  per-track **integrated Soulseek search** (`POST /api/downloads/search`, opened
  from the wishlist row menu or the track detail page) covers what the auto-pick
  misses: the user's literal query goes to slskd once, the raw results come back
  unfiltered — low bitrate and weak name matches included — with the auto-pick's
  query variants offered as one-click suggestions, and the same ranking used only
  to order them and to mark the ones the auto-pick would have accepted. Picking a
  file enqueues it on the same queue, single track or a batch. Alternatively, a
  per-track SoundCloud download via yt-dlp. All of them link the file back to the
  existing `Track` (`has_local_file`/`local_path`/`local_format`/`local_bitrate`);
  tagging stays Organize's job. A file already on disk can also be linked by hand
  from the track detail page.
- **Playlists.** Import and sync from Spotify and SoundCloud (playlists, secret
  links, selective likes), plus manual playlists and a bulk "Sync all" background job
  (a failing playlist is reported and skipped, never fatal to the rest). Rename with
  a locked name, drag-and-drop reordering, multi-select bulk actions (add to another
  playlist, remove, queue the missing ones for download), "duplicate as manual" fork,
  a per-playlist sync history, a user-uploaded cover on manual/Shazam playlists, and
  export in four formats.
- **Mix identification (Shazam).** Identifies the tracklist of an external mix from
  a URL (yt-dlp → ffmpeg segments → Shazam), building a separate corpus
  (`DjSet`/`DjSetTrack`) kept apart from the library; the downloaded audio is
  temporary and deleted. This is the project's only audio fingerprinting.
- **Organize** (`/organize`, ex Sortory). The single writer of tags, filenames and
  folder layout: scan → analyze (issue detection + dedup) → plan (RETAG / RENAME /
  MOVE / DELETE / COVER against naming and folder templates) → apply (journaled) →
  undo. Provider enrichment from AcoustID/MusicBrainz (fingerprint →
  `AudioFile.mbid`) and Discogs, plus AI-assisted "resolve with AI" on individual
  issues and a genre review pass.
- **Settings & internationalization.** One external-services status endpoint
  (`GET /api/services/status`), one AI key (`ANTHROPIC_API_KEY`, `AI_API_KEY` read as
  a fallback) shared by Set curation and Organize's AI helpers, and a single
  `/settings` page in four groups (Language · Paths & library · External services ·
  Organize). The app is bilingual (IT/EN): a persistent language setting, a typed
  frontend dictionary, backend errors as stable codes translated by the frontend, and
  deterministic phrases/AI output produced directly in the selected language.
- **Guided setup** (2026-08-21). First launch opens a six-step wizard at `/setup`
  (welcome, prerequisites, library paths, external services, slskd, summary), gated by
  `GET /api/setup/state` so a backend that's down never strands the user there.
  `services/system_probe.py` detects three external binaries — `ffmpeg`, `fpcalc`,
  `slskd` — through a declarative registry (`yt-dlp`/`essentia` are plain Python
  dependencies pip already installs, not registry entries); `services/binary_manifest.py`
  pins a version, download URL and SHA256 per component per platform, and
  `services/binary_installer.py` downloads, verifies, extracts and — only once the
  binary has actually run — installs it, with streamed log output. macOS has no pinned
  `ffmpeg` build (no upstream publishes a checksummed native arm64 static binary): there
  the installer falls back to running the registry's recipe itself (`brew install
  ffmpeg`, streamed into the same log, verified the same way) whenever `brew` is on the
  system, and only the manual command otherwise — `install_method` in the probe payload
  ("download"/"recipe"/"manual") tells the two apart. `services/slskd_daemon.py` goes a step
  further for slskd alone: it writes `slskd.yml` (touching only the four keys it needs,
  the rest of the user's file untouched) and starts/stops it as a detached process,
  never touching a process it didn't start itself (ownership is proved by the exact
  executable path recorded at launch, not by PID alone). `services/credential_tests.py`
  makes one real call per provider (Spotify, Anthropic, Discogs, AcoustID) and surfaces
  the provider's own error message. Credentials are runtime-writable the same way paths
  and URLs already were (`core/runtime_settings.py`'s `SECRET_KEYS`): a key saved from
  the wizard or from `/settings` (which shares the same field components, so a key can
  be changed without re-running the wizard) takes effect immediately, no restart — and
  its value never appears in an API response, only whether it's configured and where it
  came from.
- **Bundle-ready** (2026-08-22). The backend no longer writes inside its own
  checkout: `core/paths.py` splits `BACKEND_DIR` (where the code is) from
  `DATA_DIR` (where the writes go), with `CRATORY_DATA_DIR` selecting the
  second and everything unchanged when it is unset. An invariant test starts
  the app in a subprocess with the variable set and asserts that nothing new
  appears under `BACKEND_DIR` — a regression guard over the paths the exercise
  script touches explicitly, not an automatic detector of one left out;
  whoever adds a new write site has to extend the script too, or the test
  stays green while missing it (as it did with four slskd anchors, caught
  only in final review).
  First of the four sub-projects of the Tauri packaging work
  (`docs/superpowers/specs/2026-08-22-tauri-decomposizione-design.md`).
- **Frontend without the Next proxy** (2026-08-22). The frontend exports
  statically behind `CRATORY_STATIC_EXPORT=1`, which also drops `rewrites()` —
  there is no Next server in a bundle to apply them. Both HTTP clients now
  derive their base URL from one place (`lib/api/base.ts`), closing a
  duplication the backlog already flagged: only one of the two had an override,
  so half the app would have lost its calls. The five dynamic routes became
  query strings (`/tracks?id=42`, `/playlists/detail?id=7`), because a dynamic
  path segment cannot be statically exported — `generateStaticParams` over
  arbitrary ids does not exist. Bookmarks to the old URLs break; on a
  single-user personal app that was judged an acceptable price. Second of the
  four sub-projects of the Tauri packaging work.
- **Desktop shell** (2026-08-22). `src-tauri/` is a Tauri v2 shell (crate
  `cratory`) that starts the backend as a child process, waits for
  `/api/setup/state` to answer, and only then shows the window — reloading it
  once at that point, since the webview begins loading while the backend is
  typically still a few seconds from being up, and a one-shot fetch made in
  that window never retries on its own. The backend runs from a relocatable
  CPython 3.11 bundled inside the app (about 195 MB pruned) instead of a
  frozen binary, because `essentia_engine.py` spawns
  `[sys.executable, "-m", …]` and a frozen executable's `sys.executable` does
  not accept `-m`. Three build scripts under `src-tauri/scripts/` assemble
  the bundle: `costruisci_runtime.py` builds and prunes that runtime,
  verifying it by importing essentia and the rest rather than just checking
  the files extracted; `costruisci_binari.py` relocates ffmpeg from a local
  Homebrew install (no upstream publishes a checksummed native arm64 macOS
  build) and reads `fpcalc`/`slskd` from the existing `binary_manifest`
  instead of duplicating its URLs and hashes; `assembla.py` orchestrates both
  plus the frontend export and `tauri build`. Port 8000 stays fixed, never
  scanned for a free one, because Spotify's redirect URI is registered on it.
  The three environment seams (`CRATORY_DATA_DIR`, `CRATORY_BIN_DIR`,
  `CRATORY_VERSION`) needed no backend change — the first two sub-projects
  had already prepared them, and the shell wires them from Tauri's own path
  APIs at launch — but the backend was not otherwise untouched: `main.py`'s
  CORS middleware unions in the webview's fixed origin (`tauri://localhost`),
  and the five call sites that actually invoke ffmpeg/ffprobe/fpcalc
  (`integrations/local_files.py`, `services/mix_identify.py`,
  `organize/integrations/integrity.py`, `organize/integrations/acoustid.py`)
  now resolve the binary through `system_probe.resolve_binary` instead of a
  bare name on `PATH` — they used to disagree with the availability probes,
  which already used that seam, so the setup wizard could report every
  component present while the operations that used them broke on a
  Finder-launched app inheriting launchd's minimal `PATH`. `python3
  src-tauri/scripts/assembla.py` produces a working, ad-hoc-signed
  `Cratory.app`, verified end to end against a real
  library: essentia analyzing a real file, the relocated ffmpeg decoding a
  real FLAC, data landing under `~/Library/Application
  Support/com.cratory.app/` with nothing written inside the bundle, and no
  orphan process left once the window closes. **Not yet distributable**:
  signed ad-hoc, not by Apple, and the `.dmg` `tauri build` produces
  alongside it — a side effect of bundling for `"all"` targets — is not a
  release artifact. Third of the four sub-projects of the Tauri packaging work.
- **Release** (2026-08-22). The bundle became something that can be handed to
  someone: `LICENSE` carries the AGPL-3.0, which follows from shipping Essentia
  rather than from preference, and the README says so and drops its old claim
  that no license file exists. `bundle.targets` is now `["dmg"]` — the `.dmg`
  is what is being built rather than a side effect of `"all"`. The README
  explains, before anyone hits it, that the first launch on another Mac fails
  with *"Cratory" Not Opened* — Apple could not verify it is free of malware:
  not a broken download, just an un-notarized build, and the way through is
  System Settings → Privacy & Security → Open Anyway, since the old right-click
  shortcut no longer works. Every version needs that again, because the ad-hoc
  signature the approval is tied to changes with each build. **Two things are
  deliberately absent.** There is no Apple signature or notarization, which
  needs a paid developer account. And there is **no auto-updater**: Tauri's
  needs a signing keypair, a published manifest and an existing release, none
  of which existed then — configuring an automatic update path that cannot be
  exercised end to end would be worse than leaving it out. The repository is
  public now and releases exist, so the Settings button really does report when
  a newer version is out;
  installing it is a manual download. Last of the four sub-projects.
- **What the bundle got wrong that development never showed** (2026-08-23,
  released as 1.0.2). Two visible failures in the packaged app, one root: the
  page is served from `tauri://localhost` while everything it touches is
  somewhere else. Neither could appear in `npm run dev`, where the Next proxy
  makes the backend same-origin and a browser handles `target="_blank"` itself.
  **The Home spectrum was still flat**, despite 1.0.1 claiming to have fixed
  it: that fix declared `crossOrigin="anonymous"` on the audio element, but
  `attachAnalyser` returns before touching the element when the source is not
  same-origin, so the declaration was never reached — the analyser read zeros
  for every owned track, with no error to explain it, and the test shipped with
  it was a grep over the source, green for the wrong reason. The predicate is
  now "is this ours?" — the page **or** the backend, which admits the webview
  origin in CORS and answers `Access-Control-Allow-Origin` on Range requests
  too — and it lives once in `frontend/lib/api/base.ts` (`isOwnOrigin`),
  compared as scheme+host+port rather than `URL.origin`, because `tauri:` is
  not a special scheme and its origin is the opaque string `"null"`, which
  would make every other opaque origin look like the page itself. `crossOrigin`
  became conditional as a direct consequence, and that is not cosmetic: the
  same element plays the dig's previews, `t4.bcbits.com` answers without
  `Access-Control-Allow-Origin`, and asking for a permission nobody grants does
  not degrade the analysis — it fails the load, silencing Bandcamp.
  **Every external link did nothing at all** — Spotify, SoundCloud, Discogs,
  the docs links in Settings, slskd's web UI. `target="_blank"` asks WKWebView
  for a new webview; wry creates one only if a new-window handler is
  registered, and Tauri never registers one, so the click fell into the void:
  no tab, no navigation, no error. One capture-phase click listener on
  `document`, mounted once by the root layout, now hands external http(s) URLs
  to `tauri-plugin-opener` (scope limited to `http://*`/`https://*`) — one
  place instead of the thirteen files that write `target="_blank"`, and inert
  outside the desktop shell. Both were verified in the release artifact itself,
  mounted from the `.dmg` and running the bundled Python runtime, not only in a
  development build. **The install instructions were wrong too**, in the README
  and in all three published releases: macOS does not say the app is "damaged"
  — it says *"Cratory" Not Opened*, Apple could not verify it is free of
  malware — and the Privacy & Security approval does not carry over to the next
  version, because it is tied to a signature that ad-hoc signing changes with
  every build.

- **The updater** (2026-08-23). The Settings button no longer only reports:
  the app checks on startup, and downloads, verifies and installs a new version
  on confirmation. `tauri-plugin-updater` reads `latest.json`, published as a
  release asset by a new `src-tauri/scripts/pubblica.py` — deliberately a
  second script, because building is repeatable and harmless while publishing
  is neither. **The sequence lives in Rust**, in
  `src-tauri/src/aggiornamento.rs`, and not in the page: the Python backend
  runs from inside the bundle about to be replaced, so it must be terminated
  between `download` and `install`, and `download_and_install` — the documented
  shortcut — leaves no room for that. Error codes are the phase reached, not a
  guessed cause, because the plugin's error variants are not a contract;
  `permessi` is the exception and is decided *before* the download, with
  `libc::access(W_OK)` on the folder holding the bundle, so an app installed
  somewhere unwritable fails in a second instead of after 172 MB. Signing is
  minisign, unrelated to Apple: an unsigned or tampered package is refused.
  `bundle.targets` went back to two entries, `["app", "dmg"]` — not a reversal
  of the Release decision that made it `["dmg"]` but its correction: the
  updater's artifact is built from the `app` target, and with `dmg` alone the
  build succeeds while leaving `bundle/macos/` empty. That cost a twenty-minute
  build to discover, and a guard test now asserts both targets, because
  `createUpdaterArtifacts: true` on its own is a green light that proves
  nothing. Still absent, and still for the same reason: Apple signature and
  notarization. **Now proven**, and it is the part that motivated the whole
  thing: a bundle replaced by the app itself escapes the *"Cratory" Not Opened*
  dialog. Going from 1.0.4 to 1.0.5 the app downloaded, restarted and came back
  with nothing asked — the dialog follows the quarantine flag a browser
  attaches to a download, and an in-place update never passes through one. The
  four steps through System Settings are the price of the first install only,
  and the README now says so.

- **The updater that stopped the app from starting** (2026-08-24, released as
  1.0.4). 1.0.3 was published and pulled within the hour: it never opened.
  `tauri-plugin-updater` depends on reqwest with `rustls-no-provider`, and
  Cargo unifies features across every consumer of a crate — so the shell's own
  HTTP client, the one that only ever talks to `127.0.0.1:8000` and never sees
  a byte of TLS, was suddenly built with rustls and no crypto provider.
  `Client::new()` panicked on the first line of the thread that launches the
  backend; the thread died, the backend never started, and the window — hidden
  by design until the backend answers — never appeared. A live process, an
  invisible app, and **not one line of log**, because the panic landed before
  the logger was installed. The plugin now uses `native-tls`
  (Security.framework, already on every Mac) and rustls is out of the graph.
  **Two guards, one per mistake.** A Rust test builds that client on every
  `cargo test` — red with the bug, green without, one millisecond — so the next
  dependency that touches reqwest fails the suite instead of shipping an app
  that will not open. And `pubblica.py` now **opens the bundle and asks the
  backend which version it is** before publishing anything, refusing to release
  what does not start; it was tried against the broken 1.0.3 still installed at
  the time, which it rejected. The deeper failure was in the verification, not
  in the code: every suite was green, and none of them opened the app. The
  signal had been there sixteen hours earlier — in `tauri dev` the backend was
  not coming up and the log was not being written — and it was filed away as
  "recompilations".

- **slskd è un servizio, non un componente** (2026-08-24). Nel bundle i binari
  esterni viaggiano dentro l'app, e il passo *Prerequisiti* del wizard mostrava
  a chi aveva appena installato Cratory due righe verdi su cui non c'era niente
  da fare. La premessa "sono integrati, quindi non serve configurarli" reggeva
  però per due dei tre: **slskd non è un binario da avere ma un servizio da
  configurare**, e la sua presenza non è un file su `PATH` ma una risposta
  HTTP. È uscito da `system_probe.REGISTRY` — dove restano due binari di
  sistema e un `kind` con un valore solo — e vive dove già stava, fra i
  servizi. **La scoperta che ha cambiato il disegno**: le due interfacce che lo
  gestivano non erano duplicati ma **due metà complementari**. Il wizard sapeva
  scaricare il binario e scrivere lo YAML, Impostazioni sapeva collegare e
  gestire il demone, e per questo la riga di Impostazioni *rimandava al
  wizard* quando il binario mancava: non sapeva installarlo davvero.
  Cancellarla come doppione avrebbe perso installazione e configurazione. Ora
  una riga sola copre l'intero percorso — scarica, configura, avvia, collega —
  montata sia dal wizard sia da Impostazioni. Il passo *Prerequisiti* resta per
  ffmpeg e fpcalc e **non si monta quando entrambi vengono dal bundle**: quattro
  passi invece di cinque, senza saltare un numero nel contatore. Due
  comportamenti sono scesi insieme a slskd invece di essere persi: la ricaduta
  sull'indirizzo di default quando l'URL non è configurato (ora in
  `is_reachable`, con un timeout più corto perché quell'indirizzo è indovinato
  e non scritto da nessuno) e le tre etichette di `owned`, incluso il perché il
  bottone *Ferma* compare solo per un demone avviato da Cratory.

## Backlog

Real open items from the code and docs review closed on 2026-08-13. Grouped by size —
biggest first — not by area. Evidence and file references for each item are in
`docs/archive/superpowers/plans/2026-08-13-revisione-log.md` (section "Segnalazioni
(livello 3)") if more detail is needed than what's here.

### Deferred to their own design cycle

These four showed up during the review as real duplication, but merging any of them
means picking a winning behavior for an entire class of call sites — not a mechanical
cleanup, and each was explicitly left alone this time.

- **`fmtDuration`/`fmtDate` duplication.** `frontend/lib/api/format.ts:25` and `:32`
  vs `frontend/lib/organize/api.ts:526` and `:534` are two live implementations of
  each, with different behavior — not just different code. `fmtDuration`: the
  Organize copy rounds the seconds before dividing; the core one doesn't, so it
  spits out decimal seconds on a float. `fmtDate`: the Organize copy is
  language-aware (locale from `getCurrentLanguage()`, shows hours and minutes); the
  core one wasn't. Task 8c fixed the core copy's *locale bug* (it ignored the
  active language entirely) but explicitly left this structural duplication alone.
  Merging means picking one behavior — rounding, and date format — per call site.
- **Two parallel HTTP clients.** The frontend has `frontend/lib/api/client.ts`
  (typed `ApiError` with `status`/`code`, `AbortSignal` support, array query params,
  `apiUpload`) and `frontend/lib/organize/api.ts`'s own `handle`/`apiGet`/`apiSend`
  (throws a bare `Error`, none of the above) — same skeleton, not interchangeable.
  The backend has the same split one layer down: `backend/app/integrations/_http.py`
  (212 lines, carries a TLS 1.2 workaround) vs
  `backend/app/organize/integrations/_http.py` (44 lines, has an extra
  `post_with_retries` the core one lacks) — two forks, neither a subset of the
  other. Unifying either pair means choosing one error/retry semantics for every
  Organize call site that currently relies on the other one's behavior.
- **Two independent language stores with different defaults.** The core app reads
  and writes language from `AppState` (key `language`, default `it`, backs
  `GET|PUT /api/settings/language`). Organize has its own `Settings.language` column,
  default `en` (`backend/app/organize/services/planning.py`). The Organize HTTP
  surface (`GET|PUT /api/organize/settings/language`) has already been removed — it
  had no frontend caller — but the store itself is untouched and still diverges from
  the core one. Unifying the two stores (and picking one default) is a product
  decision.
- **Two near-photocopy pages with no test coverage.**
  `frontend/app/playlists/import-spotify/liked/page.tsx` (160 lines) and
  `frontend/app/playlists/import-soundcloud/likes/page.tsx` (159 lines):
  normalizing platform names collapses the diff between them to about 15 lines —
  everything else (state, preview, filter, selection, import, table) is identical.
  Extracting a shared component parameterized on the two data shapes is a
  legitimate refactor, but neither page is in `e2e/smoke.spec.ts` or has a unit
  test, so it would be done blind today.

### Needs a merge decision

- `backend/app/core/http_errors.py` vs `backend/app/organize/core/http_errors.py` —
  two `api_error()` implementations; the Organize one is a superset (an extra
  `headers` param used for thumbnail `Cache-Control`). Merging means adopting the
  superset inside `organize/`.
- Four hand-rolled job state machines (`backend/app/services/audio_analysis_job.py`,
  `backend/app/services/streaming_import_job.py`,
  `backend/app/services/mix_identify_job.py`, `backend/app/routers/sets.py`'s
  async-generate job) each with their own locking discipline, status-payload shape
  and start-guard semantics (three return the current state on a second start;
  `routers/sets.py` deliberately raises `409` instead, with a comment explaining
  why). A shared base class needs those three questions answered first; only the
  `_spawn()` helper has been factored out so far
  (`backend/app/services/job_spawn.py`). Soulseek/SoundCloud download used to be a
  fifth (`soulseek_download_job.py`) but no longer fits the pattern at all: it
  moved to a persistent queue with a parallel worker pool
  (`backend/app/services/download_queue.py`, `download_dispatcher.py`,
  `download_runner.py`) instead of a single-instance job, so it dropped out of
  this list rather than needing the same merge decision.
- The "load or 404" idiom is repeated roughly 40 times across
  `backend/app/routers/` (`playlists.py`, `tracks.py`, `sets.py`, `dj_sets.py`,
  `downloads.py`, `transitions.py`, `spotify.py`). The idiomatic fix
  (`Depends(get_x_or_404)`) would break the tests that call handlers directly
  instead of through HTTP — the decision needed isn't just the refactor, it's
  whether to also change the test style that depends on today's shape.

### One-line cleanups

- `organize.common.never` (i18n key) is dead — `frontend/lib/organize/api.ts:536`
  already hardcodes the same two values (`lang === "it" ? "mai" : "never"`). Wire
  the key into that call site, or delete it.
- `frontend/components/organize/files-table.tsx:78-83` — the FILES table's
  sortable column headers ("Path", "Artist", "Title", "Fmt", "Kbps", "Dur") are
  hardcoded in English while the rest of the page is translated. Needs new i18n
  keys if it should be bilingual.
- `export class ApiError` in `frontend/lib/api/client.ts` has no `instanceof`
  caller in the frontend today, but it's the client's public error surface
  (`status`/`code`), re-exported from the barrel `frontend/lib/api.ts`. Decide
  whether to stop exporting it or keep it public on purpose.
- `file_tags_for_tracks(db, [x.id]).get(x.id)` is repeated 5 times
  (`backend/app/routers/downloads.py`, `backend/app/routers/discovery.py`) where a
  `file_tags_for_track(db, x.id)` wrapper next to `backend/app/repositories.py:203`
  would do. Mechanical, cosmetic.
- `frontend/app/playlists/detail/page.tsx:592` renders
  `new Date(ev.created_at).toLocaleString()` with no locale argument, so it follows
  the browser's system locale instead of the app's active language — same bug class
  already fixed in `frontend/lib/api/format.ts`
  (`fmtDate`/`fmtDateShort`/`trackLabel`), just never applied here.
- `backend/app/organize/schemas.py:190` — the Pydantic `LanguageSetting` model has
  no importer left after the Organize language-endpoint removal above. Distinct
  from the same-named, still-live `LanguageSetting` in
  `backend/app/routers/settings.py`.
- `backend/app/services/genre_align.py:41` — `align_track_genre(..., apply: bool)`'s
  `apply=False` (dry-run) branch has no caller or test left since the CLI that used
  it was removed in this review; the five surviving call sites all pass
  `apply=True`. Dropping the parameter is a small API-contract choice, not a pure
  cleanup, so it's listed rather than done.

### Product backlog

- **Acquisition sub-project C, then the auto-pick recall fix.** The integrated
  Soulseek search (spec `docs/superpowers/specs/2026-08-15-ricerca-soulseek-integrata-design.md`,
  sub-project A) attacked the loudest symptom of "I'll just search Soulseek by hand".
  **Sub-project B, a persistent parallel download queue** (spec
  `docs/superpowers/specs/2026-08-15-coda-download-design.md`) is done: see
  "Acquisition & Wishlist" above and `docs/ARCHITECTURE.md`'s Acquisition section —
  a worker pool replaced the old one-job-at-a-time model, with a `/downloads` page,
  a `download_slots` setting and multi-select in the wishlist. One sub-project is
  left, scoped out of sub-project A's spec on purpose and existing only inside it:
  **(C) A richer wishlist row with the attempt history** — the row carries only the
  last outcome (`last_download_outcome`/`last_download_reason`), so what has already
  been tried for a track, and with which query, is lost. **The auto-pick cascade's
  recall fix** comes last on purpose: the cascade produces `not_found` for tracks that
  do exist on Soulseek, but which variants actually fail is a question C's data
  answers — fixing it blind would just be a different guess.
- **Shazam phase 2.** Use the `DjSetTrack` corpus for co-occurrence suggestions
  (which tracks tend to get mixed together) — not started.
- **PostgreSQL.** Low priority: SQLite is enough for personal, single-user use; only
  worth revisiting for an eventual multi-user setup.

### Documentation editing note

Two kinds of doc residue keep surviving review in this codebase: a parenthetical added to
sound helpful, riding along on a sentence whose main claim is correct so nobody re-checks
the aside; and a "see X" cross-reference, which is a claim about X and needs to be followed,
not just left plausible-looking. When editing `ARCHITECTURE.md`/`API.md`/`DEPENDENCIES.md`/
`ROADMAP.md`, check parentheticals and cross-references on their own, separately from the
sentence they're attached to.
