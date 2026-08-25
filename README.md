# Cratory

> A self-hosted workbench for preparing DJ sets out of a music library you actually own.

Cratory is a single-user web app that sits between your streaming accounts and your record
bag. It imports playlists from Spotify and SoundCloud, matches them against the music you
already have on disk, fills in BPM and key from Rekordbox or from its own analysis, and
builds set drafts out of tracks you can actually play. It runs entirely on your machine,
against a SQLite file and your own music folder.

The distinction it is built around: **a streaming playlist is a list of leads, your disk is
the library.** A track you found on Spotify is a candidate to acquire; only a file you own
can go into a set.

## What it does

**Library and imports**

- Import playlists and liked tracks from Spotify and SoundCloud, or paste a tracklist as text.
- De-duplicate on the way in: ISRC → platform id → artist/title/duration → fuzzy match.
- Index your music folder. Ownership comes from the disk and survives renames and moves via
  audio hash. Owned tracks play in-app, read-only, through a shared bottom player bar
  (custom transport with seek, prev/next over the originating list, auto-advance on
  owned tracks, OS media keys via Media Session) — for a quick audition, not for mixing.

**BPM and key**

- Import a Rekordbox collection XML, or analyze files in-app with Essentia. Every value
  carries its source (`manual` > `rekordbox` > `cratory`); in-app results land in staging
  fields and reach the canonical ones only through an explicit apply. `energy` is derived.

**Set building**

- A deterministic generator builds the tracklist in two phases — a skeleton first, then a
  beam search per segment — from owned tracks only.
- Each transition is classified as technically safe, a creative risk, or a good reset. Gap
  analysis reads a playlist for structural holes: no openers, no peak, missing BPM bridges,
  flat energy, harmonic dead ends.
- Export as text, CSV, Markdown or M3U8 (for Rekordbox), or push the set to Spotify as a playlist.

**Discovery and acquisition**

- Dig by genre or label through Discogs or Bandcamp, ranked by taste rather than by technical
  fit, with an ephemeral preview so you can hear a lead before committing to it.
- A wishlist tracks everything you don't own yet, with buy links. Optional acquisition through
  your own slskd (Soulseek) daemon, or a per-track SoundCloud download, links the file back to
  the track already in your library.
- Identify the tracklist of a mix from a URL (yt-dlp → ffmpeg → Shazam), into a corpus kept
  separate from the library.

**Organize** — the one part of Cratory that writes to disk: scan for tag problems, group
duplicates, build a rename/move/retag plan, review it, apply it, undo it. Metadata proposals
come from MusicBrainz/AcoustID, Discogs and cover-art lookups.

## Two rules that shape everything

**The AI never sequences.** Import, de-duplication, scoring, roles, gap analysis, discovery
ranking and validation are ordinary deterministic code. The model interprets what you asked
for, judges mood-fit and writes explanations. It never sees the whole library — the candidate
engine caps its pool at 200 tracks, 60 per call — and every response is validated against a
Pydantic schema before anything is shown or saved: invented ids and out-of-bounds values are
dropped with a warning, and a failed call degrades to the deterministic default.

**BPM and key are measured, never guessed.** They come from a Rekordbox export or from in-app
Essentia analysis — both deterministic, both with explicit provenance. Cratory never asks a
model or a streaming provider for them.

## Quickstart

Prerequisites: **Python 3.11** and **Node.js 20.9+**. Python 3.11 specifically — the pinned
Essentia build behind in-app BPM/key analysis only ships a CPython 3.11 wheel, and only for
macOS arm64 at that — coverage on other platforms is patchy. `ffmpeg` is
needed for mix identification, `fpcalc` (chromaprint) for Organize's acoustic fingerprinting.

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

App on `http://localhost:3000`, API docs on `http://localhost:8000/docs`, health check on
`http://localhost:8000/api/health`. The frontend proxies `/api/*` through to the backend, so
there is nothing to configure on that side.

Shortcut: `./start-dev.sh` (macOS/Linux) or `start-dev.bat` (Windows) brings up both, plus a
local slskd on `:5030` if one is installed.

## Configuration

The first time you open the app, it takes you straight into a guided setup wizard at
`/setup`: pick a language, see which external tools it found (and download and install
the ones it can — `ffmpeg` and `fpcalc`; platforms without a prebuilt binary just get an
install command instead), point it at your music folder, and paste in whichever API keys
you want to use, testing each one against the real provider as you go. Nothing in it is
mandatory — skip it, or any step, and reopen it later from Settings.

**In the packaged app that step is not there at all.** `ffmpeg` and `fpcalc` travel
inside the bundle, so there is nothing to install and nothing to choose: the wizard has
four steps instead of five rather than showing two green rows you cannot act on.

**slskd is a service, not a component**, and lives among the others: one row that covers
the whole path — download the daemon, write its configuration from your Soulseek
account, start it, connect. The same row appears in the wizard and in Settings, because
it is the same row.

`backend/.env`, copied from `backend/.env.example`, still supplies the defaults — the
app starts fine with just that file untouched, and it's the only way to set a value
before the very first launch. Anything set through the wizard or through Settings is
stored in the database instead and **takes precedence over `.env`, with no backend
restart needed**; clearing a field in the UI reverts it to whatever `.env` says.
Credentials set this way are never echoed back by the API — a response only ever says
whether one is configured and where it came from, never the value itself.

| Key | Enables |
|---|---|
| `LIBRARY_ROOT` | Indexing your music folder. Without it nothing is ever owned. |
| `SPOTIFY_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` | Spotify import and playlist export (connect from Settings) |
| `ANTHROPIC_API_KEY` | AI set curation and Organize's tag suggestions — one key for both |
| `DISCOGS_TOKEN` | Raises the Discogs rate limit and adds cover art; digging works without it |
| `SLSKD_URL` / `_API_KEY` / `_DOWNLOAD_DIR` | Soulseek acquisition via your own slskd instance |
| `ACOUSTID_API_KEY` | Acoustic fingerprint lookups in Organize (needs `fpcalc` too) |
| `ARCHIVE_ROOT` | A folder of discarded tracks, recognized alongside the library |

The database is `backend/data/djassistant.db` — a legacy filename, kept on purpose. Relative
SQLite paths in `DATABASE_URL` resolve against `backend/`, so the app never scatters stray
databases per working directory. To wipe user data:

```bash
cd backend && python -m app.tools.clean_user_data library --include-backups   # --dry-run to preview
```

`library` clears playlists, tracks and sets but keeps your Spotify tokens; `all` drops those too.

## Releases

The version lives in one place: the `VERSION` file at the repository root.
`frontend/package.json` carries the same number because npm requires one, and a
test fails if the two drift apart.

To publish a version:

1. Bump `VERSION` and `frontend/package.json` together.
2. Tag it `vX.Y.Z` — the tag carries the `v`, the file does not.
3. Put the updater's signing key in the environment. Without it the build stops
   immediately, before doing any work:

   ```bash
   export TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.tauri/cratory.key)"
   export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="<the key's password>"
   ```

4. Build the bundle: `python3 src-tauri/scripts/assembla.py`. It needs Homebrew
   with ffmpeg installed **on the build machine** — never on the machine of
   whoever installs the app.
5. Write the release notes to a file and publish:
   `python3 src-tauri/scripts/pubblica.py --note-file NOTES.md`. It refuses to
   run on a dirty working tree, on a mismatch between `VERSION` and
   `package.json`, or if HEAD does not carry the tag — publishing is
   irreversible, and those are the realistic ways to get it wrong. It then
   builds `latest.json` and creates the release with four attachments: the
   `.dmg` (first install), `Cratory.app.tar.gz` and its `.sig` (what the
   updater downloads), and `latest.json` (what the updater reads). The notes
   go into both the release body and the manifest, so Settings → Version shows
   the same words whichever path it took.

**The signing key is the one thing that cannot be regenerated.** Its public
half is walled into every bundle already distributed, so a different key
produces signatures those bundles reject: lose `~/.tauri/cratory.key` and no
already-installed copy of Cratory can ever update itself again. Keep a backup
somewhere that outlives the build machine.

**The app updates itself.** On startup it checks whether a newer version was
published; if one was, a dot appears next to *Settings* in the index, and
Settings → Version offers to download and install it. Nothing happens without an
explicit confirmation, which spells out what it costs: roughly 172 MB, the app
closes and starts again on its own, and anything running right now — an
analysis, a download — is interrupted, because installing means terminating the
backend first. Three outcomes and they stay three: up to date, version X is
available, or it could not be determined — the last never disguised as the
first. "Open the release" stays alongside the install button as the way out
when the automatic path cannot work, and a failed install offers a restart:
by then the backend is already gone, and only a restart puts the app back
together.

Downloads are verified before they are installed. Each `Cratory.app.tar.gz` is
signed with a minisign key at build time and checked against the public half
compiled into the running app — an unsigned or tampered package is refused, not
installed. This is separate from Apple code signing, which this project still
does not have.

Outside the desktop shell — running from a checkout in a browser — the same
Settings card only *reports*, because there is nothing to install: it asks the
backend, which reads GitHub's public releases API.

## Opening it on another Mac

The `.dmg` is signed ad-hoc, not with an Apple Developer certificate, and it is
not notarized — that requires a paid Apple account this project does not have.

**So the first attempt to open it will fail.** macOS says *"Cratory" Not
Opened* — "Apple could not verify "Cratory" is free of malware that may harm
your Mac or compromise your privacy." Nothing is wrong with the download, and
downloading it again will not help: that is simply what macOS says about
software it cannot check with Apple, because this build was never sent to Apple
to be checked.

To open it:

1. Open the `.dmg` and drag **Cratory** into Applications.
2. Try to open it. Dismiss the warning — without moving the app to the Trash.
3. Go to **System Settings → Privacy & Security**, scroll to the security
   section, and press **Open Anyway** next to the message about Cratory.
4. Confirm once more. Later launches of *that* build are normal.

On recent macOS versions the old right-click → Open shortcut no longer works for
un-notarized apps, which is why the System Settings route is the one described
here.

**Every new version installed this way needs the same four steps again.** The
approval is tied to the app's signature, and an ad-hoc signature is different in
every build — so macOS treats 1.0.2 as an app it has never been told to trust,
even if you allowed 1.0.1 on the same Mac.

**Updates the app installs itself do not.** Observed going from 1.0.4 to 1.0.5:
the app downloaded it, restarted, and came back with nothing asked. The dialog
follows the quarantine flag a browser attaches to what you download — and a
bundle the app replaces itself never passes through a browser. So the four
steps above are the price of the *first* install only.

## Desktop bundle

Cratory can also be packaged as a native macOS app, `Cratory.app`, that opens
with a double click and needs nothing else installed — no Python, no Node.js,
no terminal. The backend, a Python runtime and its three external binaries
(ffmpeg, fpcalc, slskd) all travel inside the bundle; see
`docs/ARCHITECTURE.md` for how the pieces fit together and why.

```bash
python3 src-tauri/scripts/assembla.py
```

One command does the whole build: static frontend export, a relocatable
CPython 3.11 with every backend dependency, the three binaries, and finally
`tauri build`. Every run downloads and rebuilds each piece from scratch rather
than patching one in place, so it is slow but repeatable.

**Homebrew is required on the machine that builds the bundle — never on the
machine that runs it.** No upstream publishes a checksummed native `arm64`
macOS build of ffmpeg, so the build relocates the one from a local Homebrew
install instead of downloading a prebuilt one. The finished app carries its
own copy and needs nothing from Homebrew at runtime.

The result is a working `.app`. It is ad-hoc signed, which is enough to run it
on the machine that built it, but it is **not signed or notarized by Apple**.
`bundle.targets` is `["app", "dmg"]`, and both are wanted: the `.dmg` is how
someone installs Cratory the first time, and the `.app` is what
`createUpdaterArtifacts` turns into the signed `Cratory.app.tar.gz` the updater
downloads afterwards. Dropping `app` leaves `bundle/macos/` empty and the
release with nothing to update from — a build that succeeds and produces half
of what is needed.

## Tests

```bash
cd backend && python -m pytest tests
cd frontend && npm run lint && npm run test:unit && npm run build
```

`npm run test:e2e` runs the Playwright suite, which spins up its own backend on `:8211`
against a throwaway database.

## Documentation

| Document | What's in it |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Principles, pipelines, backend layers, data model, integrations |
| [docs/API.md](docs/API.md) | The REST contracts, endpoint by endpoint |
| [docs/DESIGN.md](docs/DESIGN.md) | Product thinking and the "editorial archive" design system |
| [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) | Every dependency and external service, and why it's there |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Backlog, open questions, what's next |

## Scope, and a note on responsible use

Cratory is not a DJ deck — no waveforms, no cues, no queue; that stays in Rekordbox — and it
is not a service. Single-user is a design choice: Spotify's API rules out a public
multi-tenant app, so the project leans the other way and optimizes for one person's library
instead of for scale. Audio it doesn't own is never kept — mix identification and discovery
previews both stream and discard. The one deliberate exception is acquisition, which saves a
file and links it to a track already in your library.

Acquisition is a thin client over your own slskd instance: it hosts, shares and redistributes
nothing. What you search for, what you download, and whether you have the right to it, is
entirely your responsibility. Cratory is licensed under the **AGPL-3.0** (see `LICENSE`),
and that follows from a technical decision rather than a preference: the desktop bundle
ships Essentia, which is AGPL-3.0, so the combined work inherits it. If you hand the
`.dmg` to someone, you owe them the corresponding source. It remains a personal tool, not
a package to depend on.
