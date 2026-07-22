# Dependencies

Every runtime and build dependency of Cratory, grouped by purpose, plus the external
services features rely on. Package versions are sourced from `backend/requirements.txt`
and `frontend/package.json` — those manifests are authoritative; this document explains
*why* each dependency is here.

## System requirements

| Requirement | Version | Needed for |
|---|---|---|
| Python | 3.12+ | Backend |
| Node.js | 20+ | Frontend |
| ffmpeg | system install | Shazam module (audio decode for fingerprinting) |

## Backend (Python) — `backend/requirements.txt`

**Web / API**
- `fastapi>=0.115,<1.0` — HTTP framework (routers, request/response).
- `uvicorn[standard]>=0.32` — ASGI server.
- `python-multipart>=0.0.17` — multipart parsing for the Rekordbox `collection.xml` upload.

**Data / validation**
- `sqlalchemy>=2.0,<3.0` — ORM over SQLite.
- `pydantic>=2.9,<3.0` — schemas; validates every AI output before it is shown or saved.
- `pydantic-settings>=2.6,<3.0` — typed settings from `.env`.

**HTTP client**
- `httpx>=0.27` — outbound calls to Spotify, Discogs, slskd; also the test client.

**AI**
- `anthropic>=0.69,<1.0` — LLM client behind the AI interface.

**Shazam / mix identification**
- `yt-dlp>=2024.0` — pulls audio for mix fingerprinting and does flat metadata extraction
  for the SoundCloud import (metadata only, never stored audio).
- `shazamio>=0.5` — Shazam fingerprint lookup.
- `mutagen>=1.47` — reads tags (incl. `label`) from library files on disk.

**XML security**
- `defusedxml` — hardened XML parsing for the Rekordbox collection import.

**Analysis (in-app BPM/key)**
- `essentia==2.1b6.dev1389` — deterministic BPM/key extraction for the Analysis page
  (`/api/analysis/*`), used only by `backend/app/integrations/essentia_engine.py`
  (lazy import: the app runs without it, the router returns `503` if missing). Pin is
  exact and load-bearing: Essentia only publishes rolling `2.1b6.devN` builds with
  patchy wheel coverage, and `2.1b6.dev1389` is the last one with a `cp311
  macosx-arm64` wheel. License **AGPL-3.0** — acceptable for personal, self-hosted,
  non-redistributed use; do not bundle/distribute a build containing it.

**Testing**
- `pytest>=8.3` — backend test suite.

## Frontend (Node) — `frontend/package.json`

**Runtime**
- `next@16.2.9` — App Router framework. (Next 16 has breaking changes — see `frontend/CLAUDE.md`.)
- `react@19.2.4`, `react-dom@19.2.4` — UI runtime.
- `lucide-react@^1.18.0` — icon set (monochrome, per the design system).

**Dev / build**
- `tailwindcss@^4` + `@tailwindcss/postcss@^4` — styling / design tokens.
- `typescript@^5`, `@types/node@^20`, `@types/react@^19`, `@types/react-dom@^19` — types.
- `eslint@^9` + `eslint-config-next@16.2.9` — linting.

## External services & runtime dependencies

Not Python/Node packages, but required for the corresponding feature to work:

| Service | Feature | Required? |
|---|---|---|
| Spotify Web API | Track identity, editorial metadata, covers, ISRC, playlist import/export | Required for Spotify import |
| Discogs API | Discovery "Scava" (crate-dig by genre/label) | Optional (token only raises rate limit) |
| Bandcamp (internal API) | Discovery "Scava" second dig source (crate-dig by genre/label) | Optional (Discovery), public — no auth/token, undocumented endpoints |
| iTunes Search API | Discovery preview (30s audio clip for dig leads without their own stream) | Optional (Discovery), public — no auth/token |
| slskd daemon | File acquisition via Soulseek | Optional, runs separately |
| Rekordbox | BPM/Camelot key via `collection.xml` export | Required for BPM/key (no package dep — just a file upload) |
| Sortory (sibling app) | Text metadata enrichment + on-disk tagging | Optional, separate app |

None of Discogs/Spotify feed BPM/key/genre — those providers serve **Discovery
only**. BPM/key come from Rekordbox; text metadata/tagging come from Sortory.

The Discovery preview's fallback embeds the YouTube video Discogs already associates
with a release (`GET https://itunes.apple.com/search` is tried first, no key required).
That embed can surface ads and sits in a ToS grey area for this kind of use; accepted
here given Cratory's personal, self-hosted, single-user scope (no redistribution).

**Bandcamp** is the second Discovery dig source, behind the same `DigSource` seam as
Discogs (see `docs/ARCHITECTURE.md`). It talks to `bandcamp.com`'s own internal,
undocumented endpoints (`api/discover/1/discover_web`,
`api/bcsearch_public_api/1/autocomplete_elastic`, `api/mobile/24/band_details`,
`api/mobile/24/tralbum_details`) — the same ones behind `bandcamp.com/discover` in a
browser, not a published API. No key, no token, no registration: plain unauthenticated
POST requests (`backend/app/integrations/bandcamp.py`, `httpx` client injectable for
tests, same shape as `discogs.py`). Because the endpoints are internal, Bandcamp can
change or remove them without notice; the risk is accepted for Cratory's personal,
self-hosted, single-user scope (the same posture already taken for yt-dlp on
SoundCloud) and contained by the `DigSource` seam — if Bandcamp breaks, only that
source stops working, Discogs keeps digging. `backend/tests/test_bandcamp_contract.py`
is marked `@pytest.mark.network` and excluded from the default suite (`pytest.ini`:
`addopts = -m 'not network'`); it hits the real API and checks the shape of the
response, and is the diagnostic to run by hand when the Bandcamp dig stops returning
leads.

## History

`pyacoustid` (and the `fpcalc`/chromaprint system requirement) backed AcoustID
fingerprinting of the owned library. That feature was **removed in the 2026-07 disk-first
pivot**; the dead dependency was dropped from `requirements.txt` on 2026-07-11.
