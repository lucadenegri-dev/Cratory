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

> `fpcalc`/chromaprint was previously required by AcoustID fingerprinting. That feature
> was removed in the 2026-07 disk-first pivot — see the cleanup note below.

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
- `httpx>=0.27` — outbound calls to Spotify, Last.fm, Discogs, slskd; also the test client.

**AI**
- `anthropic>=0.69,<1.0` — LLM client behind the AI interface.

**Shazam / mix identification**
- `yt-dlp>=2024.0` — pulls audio for mix fingerprinting and does flat metadata extraction
  for the SoundCloud import (metadata only, never stored audio).
- `shazamio>=0.5` — Shazam fingerprint lookup.
- `mutagen>=1.47` — reads tags (incl. `label`) from library files on disk.

**XML security**
- `defusedxml` — hardened XML parsing for the Rekordbox collection import.

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
| Last.fm API | Discovery (playlist expand, similarity) | Optional (Discovery) |
| Discogs API | Discovery "Scava" (crate-dig by genre/label) | Optional (token only raises rate limit) |
| slskd daemon | File acquisition via Soulseek | Optional, runs separately |
| Rekordbox | BPM/Camelot key via `collection.xml` export | Required for BPM/key (no package dep — just a file upload) |
| Sortory (sibling app) | Text metadata enrichment + on-disk tagging | Optional, separate app |

None of Last.fm/Discogs/Spotify feed BPM/key/genre — those providers serve **Discovery
only**. BPM/key come from Rekordbox; text metadata/tagging come from Sortory.

## Cleanup note (documentation finding)

`backend/requirements.txt` still lists `pyacoustid>=1.3` with an AcoustID comment, but
AcoustID fingerprinting of the owned library was **removed in the 2026-07 disk-first
pivot** (see `docs/ROADMAP.md`). It is very likely a dead dependency. Verify and remove it
(and drop `fpcalc`/chromaprint from system requirements) in a separate code-cleanup task —
this document does not edit `requirements.txt`.
