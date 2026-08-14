# Dependencies

Every runtime and build dependency of Cratory, with the reason it is there, plus the
external services that features rely on. `backend/requirements.txt` and
`frontend/package.json` are authoritative for versions; this document explains *why*.

## System requirements

| Requirement | Version | Needed for |
|---|---|---|
| Python | **3.11** | Backend. Not a preference: the pinned Essentia build only publishes a CPython 3.11 wheel (see below). |
| Node.js | 20.9+ | Frontend (Next 16's floor) |
| ffmpeg | system install | Audio decoding: the `audio_hash` used for library identity, the segments the Shazam module fingerprints, and the yt-dlp MP3 extraction |
| fpcalc (chromaprint) | system install, optional | AcoustID fingerprinting in Organize (`brew install chromaprint`) |

## Backend (Python) — `backend/requirements.txt`

**Web / API**
- `fastapi>=0.115,<1.0` — HTTP framework: routers, request/response models, dependency injection.
- `uvicorn[standard]>=0.32` — ASGI server.
- `python-multipart>=0.0.17` — multipart parsing, for the Rekordbox `collection.xml` upload.

**Data / validation**
- `sqlalchemy>=2.0,<3.0` — ORM over SQLite. One `Base` and one engine for both the core and the Organize models.
- `pydantic>=2.9,<3.0` — request/response schemas, and the validation gate every AI output passes before it is shown or saved.
- `pydantic-settings>=2.6,<3.0` — typed settings loaded from `backend/.env`.
- `python-dotenv>=1.0` — imported directly by `app/main.py`. `pydantic-settings` reads `.env` into `Settings` fields (`ai_api_key` among them), and all three Anthropic clients pass `settings.ai_api_key` explicitly — the SDK never reads `os.environ` itself. But `pydantic-settings`'s `env_file` only populates `Settings`, not the process's actual environment, and one value is still read straight from `os.environ`: `FPCALC` (`organize/integrations/acoustid.py`, the Chromaprint binary override). `load_dotenv()` runs at import time so a `FPCALC` set in `.env` reaches `os.environ` too. It already arrived as a transitive dependency of `pydantic-settings`; it is listed explicitly because our code imports it.

**HTTP client**
- `httpx>=0.27` — every outbound call (Spotify, SoundCloud, Discogs, Bandcamp, iTunes, slskd, MusicBrainz). Also FastAPI's test client. Provider classes take an injectable client, so the suite runs without a network.

**AI**
- `anthropic>=0.69,<1.0` — the LLM client behind `integrations/llm.py`. One key for the whole app: `ANTHROPIC_API_KEY` (`AI_API_KEY` is still read as a legacy alias for older `.env` files).

**Config editing**
- `ruamel.yaml>=0.18,<0.19` — round-trip editing of `slskd.yml` for the "Share library" flag. slskd does not accept share changes over its API at runtime, so `services/slskd_shares.py` edits its config file in place. This has to preserve comments, key order and formatting in a file that holds the user's credentials — PyYAML cannot round-trip, `ruamel.yaml` can.

**Files and tags**
- `mutagen>=1.47` — reads tags from library files on disk (including `label`: ID3 `TPUB` / Vorbis `LABEL`) and writes them in Organize, the only writer.
- `defusedxml` — hardened XML parsing for the Rekordbox collection import (anti-XXE).

**Mix identification and streaming extraction**
- `yt-dlp>=2024.0` — three jobs: temporary audio download for mix fingerprinting, metadata-only extraction for the SoundCloud playlist/likes import, and the per-track SoundCloud MP3 download.
- `shazamio>=0.5` — Shazam fingerprint lookup for mix tracklists.

**In-app BPM/key analysis**
- `essentia==2.1b6.dev1389` — deterministic BPM and key extraction for the Analysis page (`/api/analysis/*`), used only by `integrations/essentia_engine.py` and its subprocess worker. Lazy import: the app runs fine without it, and the router answers `503`.
  The pin is exact and load-bearing. Essentia publishes only rolling `2.1b6.devN` builds with patchy wheel coverage, and `2.1b6.dev1389` is the last one with a **cp311 macOS-arm64** wheel. Other platforms and other Python versions are hit and miss for this build — on a machine with no matching wheel you either build from source or run without the Analysis page.
  License **AGPL-3.0**: acceptable for personal, self-hosted, non-redistributed use. Do not bundle or distribute a build containing it.

**Organize (metadata providers)**
- `pyacoustid` — AcoustID acoustic fingerprinting → `AudioFile.mbid`. Needs the `fpcalc` system binary; without either it, the binary, or `ACOUSTID_API_KEY`, `/api/organize/fingerprint` reports `configured: false` and the "Identify now" button stays disabled.
- `Pillow` — cover thumbnails, both for provider proposals and for artwork embedded in files. Without it, thumbnails are unavailable.

**Testing**
- `pytest>=8.3` — the backend suite. `pytest.ini` sets `addopts = -m 'not network'`, so the tests that hit real provider APIs (the Bandcamp contract test) are excluded from a default run.

### Undeclared, but imported

`services/audio_energy.py` and its test do `import numpy as np`. numpy is not in
`requirements.txt`: it arrives as a dependency of `essentia`. Since `essentia` is a hard pin
and always installed, this works today — but it is a direct import resting on a transitive
dependency, and it would break in any install that skips Essentia. Worth pinning explicitly
if that ever becomes a supported configuration.

`pydub` (a `shazamio` dependency) triggers a stdlib `audioop` deprecation warning; it is
silenced by name in `pytest.ini` because it is not our code to fix.

## Frontend (Node) — `frontend/package.json`

**Runtime**
- `next@16.2.9` — App Router framework. Next 16 has breaking changes relative to older versions — read `frontend/CLAUDE.md` before touching pages or routing.
- `react@19.2.4`, `react-dom@19.2.4` — UI runtime.
- `lucide-react@^1.18.0` — the icon set. Monochrome line icons, which is what the design system asks for.
- `tailwind-merge@^3.6.0` — powers `lib/cn.ts`. It resolves conflicts between Tailwind utilities on the same property, so a `className` passed by a caller actually overrides a component's default instead of sitting next to it in the class list.

**Build / styling**
- `tailwindcss@^4` + `@tailwindcss/postcss@^4` — styling. The design tokens are declared in `app/globals.css` and mapped to utilities with `@theme inline`.
- `typescript@^5`, `@types/node@^20`, `@types/react@^19`, `@types/react-dom@^19` — types.
- `eslint@^9` + `eslint-config-next@16.2.9` — linting (`npm run lint`).

**Testing**
- `vitest@^4.1.10` + `@vitejs/plugin-react@^6.0.3` + `jsdom@^29.1.1` — the unit suite (`npm run test:unit`, config in `vitest.config.ts`).
- `@testing-library/react@^16.3.2` + `@testing-library/dom@^10.4.1` — component rendering and queries for those tests.
- `@playwright/test@^1.61.1` — the end-to-end suite (`npm run test:e2e`, config in `playwright.config.ts`), which brings up its own backend against a throwaway database.

## External services

Not packages, but required for the corresponding feature to work:

| Service | Feature | Required? |
|---|---|---|
| Spotify Web API | Track identity, editorial metadata, covers, ISRC, playlist import and export | Required for Spotify import; needs `SPOTIFY_CLIENT_ID`/`_SECRET`/`_REDIRECT_URI` |
| SoundCloud | Playlist, secret-link and likes import, and the per-track download | Optional; no key — reached through yt-dlp |
| Discogs API | Discovery dig by genre/label, release detail, and the text-metadata provider in Organize | Optional; `DISCOGS_TOKEN` only raises the rate limit and adds covers |
| Bandcamp (internal API) | Discovery dig, second source | Optional; public, no auth, undocumented endpoints |
| iTunes Search API | Discovery preview (30s clip for leads without their own stream) | Optional; public, no auth |
| MusicBrainz | Text-metadata proposals in Organize | Optional; no key, but requires an identifiable `MUSICBRAINZ_USER_AGENT` |
| AcoustID | Acoustic fingerprint → MBID in Organize | Optional; `ACOUSTID_API_KEY` plus the `fpcalc` binary |
| Anthropic API | Set curation and Organize's AI tag/genre helpers | Optional; `ANTHROPIC_API_KEY` |
| slskd daemon | File acquisition over Soulseek, and the opt-in library share | Optional; runs separately, `SLSKD_URL`/`_API_KEY`/`_DOWNLOAD_DIR` |
| Rekordbox | BPM and Camelot key via the `collection.xml` export | Required for BPM/key unless in-app analysis is used. No package and no API — a file upload |

None of these providers supplies BPM, key, mood or energy. BPM and key come from Rekordbox
or from in-app Essentia analysis; text metadata and tagging are the Organize section's job.

### Two accepted risks

**The Discovery preview's YouTube fallback.** iTunes Search is tried first (public, no key).
When it finds nothing, the preview embeds the YouTube video Discogs already associates with
the release. That embed can surface ads and sits in a grey area of YouTube's terms for this
kind of use; accepted given Cratory's personal, self-hosted, single-user scope and the fact
that nothing is downloaded or redistributed.

**Bandcamp's internal endpoints.** The second dig source talks to `bandcamp.com`'s own
undocumented endpoints (`api/discover/1/discover_web`,
`api/bcsearch_public_api/1/autocomplete_elastic`, `api/mobile/24/band_details`,
`api/mobile/24/tralbum_details`) — the same ones behind `bandcamp.com/discover` in a browser,
not a published API. No key, no token, no registration: plain unauthenticated POSTs from
`backend/app/integrations/bandcamp.py`, with an injectable `httpx` client, same shape as
`discogs.py`. Bandcamp can change or remove them without notice. The risk is accepted for the
same reason as yt-dlp on SoundCloud, and contained by the `DigSource` seam: if Bandcamp
breaks, only that source stops and Discogs keeps digging.
`backend/tests/test_bandcamp_contract.py` is the diagnostic — marked `@pytest.mark.network`
and excluded from the default suite, it hits the real API and checks the response shape. Run
it by hand when the Bandcamp dig stops returning leads.
