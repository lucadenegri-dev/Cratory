# Discovery Preview Audio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere una preview audio ai dischi del Discovery dig (Discogs), con sorgente iTunes (30s, pulita) e fallback ai video YouTube che Discogs già associa alla release, riprodotta in un player unico ancorato in basso a destra.

**Architecture:** Backend deterministico: nuovo client `ItunesClient` (HTTP puro), funzione pura `resolve_preview` che applica la catena iTunes → video Discogs → none, esposta da un endpoint `GET /api/discovery/preview`. Frontend: un player "docked" fixed in basso a destra, alimentato da pulsanti play su card e righe tracklist tramite un React context a livello pagina.

**Tech Stack:** Python 3 + FastAPI + Pydantic (backend), Next.js 16 + React + Tailwind (frontend), pytest (backend test), Vitest + Testing Library (frontend test).

## Global Constraints

- **Branch di lavoro:** `feat/discovery-preview` (già creato e attivo).
- **Errori provider backend:** usare `api_error(502, "discovery_provider_error", f"...: {exc}", reason=str(exc))` da `app.core.http_errors`, MAI `HTTPException` grezza. Gli errori iTunes/Discogs nella preview degradano a `kind="none"` con HTTP 200 (una preview mancante non è un errore).
- **Client HTTP:** ogni nuovo client eredita da `ClosableHttpClient` e usa `get_json` da `app.integrations._http`; `httpx.Client` iniettabile via parametro `http` per i test senza rete.
- **Serializzazione Discogs:** inline nel router (come già `DiscogsReleaseOut`), NON in `serializers.py` (quello è solo ORM→schema).
- **i18n:** ogni stringa nuova va aggiunta in `frontend/lib/i18n/it.ts` E `frontend/lib/i18n/en.ts` con la stessa chiave.
- **Commit message:** in italiano, stile Conventional Commits; NON aggiungere `Co-Authored-By`.
- **Frontend Next 16:** prima di modificare pagine/routing leggere `frontend/CLAUDE.md`. Qui tocchiamo solo componenti client e lib, non il routing.

---

## File Structure

**Backend (nuovi):**
- `backend/app/integrations/itunes.py` — client HTTP iTunes Search API (concreto, no auth).
- `backend/app/services/preview.py` — funzione pura `resolve_preview` + helper di parsing/matching video e cache TTL del `get_release`.
- `backend/tests/test_itunes.py` — unit del client con httpx mockato.
- `backend/tests/test_preview_service.py` — unit di `resolve_preview` e helper.
- `backend/tests/test_discovery_preview_http.py` — test dell'endpoint via TestClient.

**Backend (modificati):**
- `backend/app/schemas.py` — aggiungere `DiscogsVideoOut`, `DiscoveryPreviewOut`; campo `videos` in `DiscogsReleaseOut`.
- `backend/app/routers/discovery.py` — serializzare `videos` in `/release/{id}`; nuovo endpoint `GET /preview`.

**Frontend (nuovi):**
- `frontend/lib/preview-player.tsx` — context/provider `PreviewPlayerProvider` + hook `usePreviewPlayer`.
- `frontend/components/docked-preview-player.tsx` — il player fixed in basso a destra.
- `frontend/tests/preview-player.test.tsx` — unit del context e del player.

**Frontend (modificati):**
- `frontend/lib/api/types.ts` — tipo `DiscoveryPreview`; campo `videos` in `DiscogsRelease`.
- `frontend/lib/api/discovery.ts` — funzione `discoveryPreview`.
- `frontend/app/discovery/page.tsx` — montare `PreviewPlayerProvider` + `DockedPreviewPlayer`.
- `frontend/components/discovery-lead-grid.tsx` — pulsante play overlay su `LeadCell`.
- `frontend/components/discovery-tracklist-panel.tsx` — pulsante play in `TrackRow`.
- `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts` — stringhe preview.

**Docs (modificati):** `docs/ARCHITECTURE.md`, `CLAUDE.md`, `docs/API.md`, `docs/DEPENDENCIES.md`.

---

## Task 1: Client iTunes (`integrations/itunes.py`)

**Files:**
- Create: `backend/app/integrations/itunes.py`
- Test: `backend/tests/test_itunes.py`

**Interfaces:**
- Consumes: `ClosableHttpClient`, `get_json` da `app.integrations._http`.
- Produces:
  - `class ItunesError(Exception)`
  - `class ItunesClient(ClosableHttpClient)` con `__init__(self, http: httpx.Client | None = None)` e `search(self, term: str, *, limit: int = 5) -> list[dict]` (ritorna la lista grezza `results`).

- [ ] **Step 1: Scrivere il test che fallisce**

Create `backend/tests/test_itunes.py`:

```python
import pytest

from app.integrations.itunes import ItunesClient, ItunesError


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, ""

    def json(self):
        return self._p


class _FakeHttp:
    def __init__(self, payload, status=200):
        self.payload, self.status, self.calls = payload, status, []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _Resp(self.payload, self.status)


def test_search_builds_query_and_returns_results():
    http = _FakeHttp({"resultCount": 1, "results": [{"trackName": "X", "previewUrl": "http://a"}]})
    c = ItunesClient(http=http)
    out = c.search("rick astley never gonna", limit=3)
    assert out == [{"trackName": "X", "previewUrl": "http://a"}]
    url, params = http.calls[0]
    assert url.endswith("/search")
    assert params["term"] == "rick astley never gonna"
    assert params["media"] == "music"
    assert params["entity"] == "song"
    assert params["limit"] == 3


def test_search_empty_results():
    http = _FakeHttp({"resultCount": 0, "results": []})
    c = ItunesClient(http=http)
    assert c.search("nothing here") == []


def test_search_http_error_raises_itunes_error():
    http = _FakeHttp({}, status=500)
    c = ItunesClient(http=http)
    with pytest.raises(ItunesError):
        c.search("boom")
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_itunes.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.integrations.itunes'`.

- [ ] **Step 3: Implementare il client**

Create `backend/app/integrations/itunes.py`:

```python
"""iTunes Search API: sorgente di PREVIEW audio (clip 30s) per la Discovery.

API pubblica di Apple, nessun token/auth: `GET https://itunes.apple.com/search`.
Restituisce brani con `previewUrl` (clip AAC 30s). Usato SOLO per la preview dei
lead del dig; non fornisce BPM/key né identità (quella resta Discogs/Spotify).
httpx iniettabile -> test senza rete.
"""

import logging

import httpx

from app.integrations._http import ClosableHttpClient, get_json

logger = logging.getLogger(__name__)

BASE = "https://itunes.apple.com"


class ItunesError(Exception):
    pass


class ItunesClient(ClosableHttpClient):
    def __init__(self, http: httpx.Client | None = None):
        # Nessun token né User-Agent speciale: l'endpoint è pubblico.
        self.http = http or httpx.Client(timeout=15, follow_redirects=True)

    def search(self, term: str, *, limit: int = 5) -> list[dict]:
        payload = get_json(
            self.http, f"{BASE}/search",
            params={"term": term, "media": "music", "entity": "song", "limit": limit},
            error_cls=ItunesError, name="iTunes",
            rate_limit_message="iTunes: rate limit (riprova tra poco).",
        )
        return payload.get("results", []) or []
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_itunes.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/itunes.py backend/tests/test_itunes.py
git commit -m "feat(itunes): client iTunes Search API per preview audio"
```

---

## Task 2: Service `resolve_preview` + parsing/matching video (`services/preview.py`)

**Files:**
- Create: `backend/app/services/preview.py`
- Test: `backend/tests/test_preview_service.py`

**Interfaces:**
- Consumes: nulla dagli altri task (funzioni pure; le dipendenze di rete sono iniettate come callable).
- Produces:
  - `@dataclass PreviewResult` con campi `kind: str`, `audio_url: str | None = None`, `youtube_video_id: str | None = None`, `source_url: str | None = None`, `matched_title: str | None = None`.
  - `parse_youtube_id(uri: str) -> str | None`
  - `extract_youtube_videos(payload: dict) -> list[dict]` (ogni dict: `{"youtube_video_id": str, "title": str, "duration_seconds": int | None}`)
  - `norm_tokens(s: str) -> set[str]`
  - `pick_video(videos: list[dict], title: str, level: str) -> dict | None`
  - `itunes_hit(results: list[dict], title: str) -> dict | None` (ritorna il result iTunes che matcha, o `None`)
  - `resolve_preview(artist: str, title: str, *, itunes_search, get_release=None, discogs_id=None, level="track") -> PreviewResult` dove `itunes_search: Callable[[str], list[dict]]` e `get_release: Callable[[int], dict] | None`.

- [ ] **Step 1: Scrivere i test che falliscono**

Create `backend/tests/test_preview_service.py`:

```python
from app.services.preview import (
    PreviewResult,
    extract_youtube_videos,
    itunes_hit,
    norm_tokens,
    parse_youtube_id,
    pick_video,
    resolve_preview,
)


def test_parse_youtube_id_watch_and_short():
    assert parse_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert parse_youtube_id("https://youtu.be/dQw4w9WgXcQ?t=5") == "dQw4w9WgXcQ"
    assert parse_youtube_id("https://example.com/x") is None


def test_extract_youtube_videos_maps_fields():
    payload = {"videos": [
        {"uri": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "title": "Foo - Bar", "duration": 214},
        {"uri": "https://vimeo.com/1", "title": "skip", "duration": 10},
    ]}
    out = extract_youtube_videos(payload)
    assert out == [{"youtube_video_id": "aaaaaaaaaaa", "title": "Foo - Bar", "duration_seconds": 214}]


def test_norm_tokens_strips_noise():
    assert norm_tokens("Track Name (Original Mix)") == {"track", "name"}


def test_itunes_hit_matches_by_title_tokens():
    results = [
        {"trackName": "Other Song", "artistName": "A", "previewUrl": "http://a", "trackViewUrl": "http://va"},
        {"trackName": "Never Gonna Give You Up", "artistName": "Rick Astley", "previewUrl": "http://p", "trackViewUrl": "http://v"},
    ]
    hit = itunes_hit(results, "Never Gonna Give You Up")
    assert hit["previewUrl"] == "http://p"


def test_itunes_hit_skips_results_without_preview_url():
    results = [{"trackName": "Never Gonna Give You Up", "artistName": "R", "previewUrl": None}]
    assert itunes_hit(results, "Never Gonna Give You Up") is None


def test_itunes_hit_none_when_no_title_match():
    results = [{"trackName": "Totally Different", "previewUrl": "http://p"}]
    assert itunes_hit(results, "Never Gonna Give You Up") is None


def test_pick_video_track_level_fuzzy_match():
    videos = [
        {"youtube_video_id": "v1", "title": "Artist - Acid Trip (Original Mix)", "duration_seconds": 300},
        {"youtube_video_id": "v2", "title": "Artist - Other Track", "duration_seconds": 200},
    ]
    got = pick_video(videos, "Acid Trip", level="track")
    assert got["youtube_video_id"] == "v1"


def test_pick_video_release_level_takes_first():
    videos = [
        {"youtube_video_id": "v1", "title": "whatever", "duration_seconds": 1},
        {"youtube_video_id": "v2", "title": "second", "duration_seconds": 2},
    ]
    got = pick_video(videos, "Titolo Release", level="release")
    assert got["youtube_video_id"] == "v1"


def test_pick_video_none_when_empty():
    assert pick_video([], "x", level="track") is None
    assert pick_video([{"youtube_video_id": "v", "title": "zzz"}], "abc", level="track") is None


def test_resolve_preview_itunes_first():
    def fake_itunes(term):
        return [{"trackName": "Acid Trip", "artistName": "Artist", "previewUrl": "http://p", "trackViewUrl": "http://v"}]

    res = resolve_preview("Artist", "Acid Trip", itunes_search=fake_itunes)
    assert res.kind == "itunes"
    assert res.audio_url == "http://p"
    assert res.source_url == "http://v"
    assert res.matched_title == "Acid Trip"


def test_resolve_preview_falls_back_to_youtube():
    payload = {"videos": [{"uri": "https://youtu.be/bbbbbbbbbbb", "title": "Artist - Acid Trip", "duration": 200}]}
    res = resolve_preview(
        "Artist", "Acid Trip",
        itunes_search=lambda term: [],
        get_release=lambda rid: payload,
        discogs_id=123, level="track",
    )
    assert res.kind == "youtube"
    assert res.youtube_video_id == "bbbbbbbbbbb"
    assert res.source_url == "https://www.youtube.com/watch?v=bbbbbbbbbbb"


def test_resolve_preview_none_when_nothing_matches():
    res = resolve_preview(
        "Artist", "Acid Trip",
        itunes_search=lambda term: [],
        get_release=lambda rid: {"videos": []},
        discogs_id=123, level="track",
    )
    assert res.kind == "none"
    assert res.audio_url is None and res.youtube_video_id is None


def test_resolve_preview_none_when_get_release_raises():
    def boom(rid):
        raise RuntimeError("discogs down")

    res = resolve_preview(
        "Artist", "Acid Trip",
        itunes_search=lambda term: [],
        get_release=boom, discogs_id=123, level="track",
    )
    assert res.kind == "none"
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_preview_service.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.preview'`.

- [ ] **Step 3: Implementare il service**

Create `backend/app/services/preview.py`:

```python
"""Risoluzione preview audio per i lead del Discovery dig (funzione pura).

Catena deterministica: iTunes (clip 30s pulita) -> video YouTube della release
Discogs -> nessuna. Le dipendenze di rete sono INIETTATE come callable, così il
service è testabile senza rete. Vedi docs/superpowers/specs/2026-07-16-...
"""

import logging
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

ItunesSearch = Callable[[str], list[dict]]
GetRelease = Callable[[int], dict]

_NOISE = re.compile(r"feat\.?|featuring|remix|edit|version|original|mix", re.IGNORECASE)
_PARENS = re.compile(r"\(.*?\)|\[.*?\]")
_NONWORD = re.compile(r"[^a-z0-9 ]")


@dataclass
class PreviewResult:
    kind: str  # "itunes" | "youtube" | "none"
    audio_url: str | None = None
    youtube_video_id: str | None = None
    source_url: str | None = None
    matched_title: str | None = None


def norm_tokens(s: str) -> set[str]:
    s = (s or "").lower()
    s = _PARENS.sub(" ", s)
    s = _NOISE.sub(" ", s)
    s = _NONWORD.sub(" ", s)
    return {t for t in s.split() if len(t) > 1}


def _matches(want: set[str], got: set[str]) -> bool:
    if not want:
        return False
    return len(want & got) >= max(1, len(want) // 2)


def parse_youtube_id(uri: str) -> str | None:
    if not uri:
        return None
    u = urlparse(uri)
    host = (u.hostname or "").lower()
    if host.endswith("youtu.be"):
        vid = u.path.lstrip("/")
        return vid or None
    if "youtube.com" in host:
        qs = parse_qs(u.query)
        vals = qs.get("v")
        if vals:
            return vals[0]
    return None


def extract_youtube_videos(payload: dict) -> list[dict]:
    out = []
    for v in (payload.get("videos") or []):
        vid = parse_youtube_id(v.get("uri") or "")
        if not vid:
            continue
        out.append({
            "youtube_video_id": vid,
            "title": v.get("title") or "",
            "duration_seconds": v.get("duration"),
        })
    return out


def itunes_hit(results: list[dict], title: str) -> dict | None:
    want = norm_tokens(title)
    for r in results:
        if not r.get("previewUrl"):
            continue
        if _matches(want, norm_tokens(r.get("trackName", ""))):
            return r
    return None


def pick_video(videos: list[dict], title: str, level: str) -> dict | None:
    if not videos:
        return None
    if level == "release":
        return videos[0]
    want = norm_tokens(title)
    for v in videos:
        if _matches(want, norm_tokens(v.get("title", ""))):
            return v
    return None


def resolve_preview(
    artist: str,
    title: str,
    *,
    itunes_search: ItunesSearch,
    get_release: GetRelease | None = None,
    discogs_id: int | None = None,
    level: str = "track",
) -> PreviewResult:
    # 1. iTunes (pulito)
    term = " ".join(p for p in (artist, title) if p).strip()
    try:
        results = itunes_search(term)
    except Exception as exc:  # rete/rate: la preview manca, non è un errore fatale
        logger.info("itunes preview lookup failed: %s", exc)
        results = []
    hit = itunes_hit(results, title)
    if hit:
        return PreviewResult(
            kind="itunes",
            audio_url=hit.get("previewUrl"),
            source_url=hit.get("trackViewUrl"),
            matched_title=hit.get("trackName"),
        )
    # 2. Fallback video YouTube della release
    if discogs_id is not None and get_release is not None:
        try:
            payload = get_release(discogs_id)
            videos = extract_youtube_videos(payload)
        except Exception as exc:
            logger.info("discogs videos lookup failed: %s", exc)
            videos = []
        vid = pick_video(videos, title, level)
        if vid:
            return PreviewResult(
                kind="youtube",
                youtube_video_id=vid["youtube_video_id"],
                source_url=f"https://www.youtube.com/watch?v={vid['youtube_video_id']}",
                matched_title=vid.get("title") or None,
            )
    # 3. Niente
    return PreviewResult(kind="none")
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_preview_service.py -v`
Expected: tutti passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/preview.py backend/tests/test_preview_service.py
git commit -m "feat(preview): service resolve_preview (iTunes + fallback video Discogs)"
```

---

## Task 3: Schemi + campo `videos` in `DiscogsReleaseOut`

**Files:**
- Modify: `backend/app/schemas.py` (dopo `DiscogsTrackOut`/`DiscogsReleaseOut`, righe ~546-560)
- Modify: `backend/app/routers/discovery.py` (serializzazione release in `get_release_detail`, righe ~264-283)
- Test: `backend/tests/test_discovery_router_http.py` (aggiungere un test)

**Interfaces:**
- Consumes: `extract_youtube_videos` da `app.services.preview` (Task 2).
- Produces:
  - `class DiscogsVideoOut(BaseModel)` con `youtube_video_id: str`, `title: str`, `duration_seconds: int | None = None`.
  - `class DiscoveryPreviewOut(BaseModel)` con `kind: str`, `audio_url: str | None = None`, `youtube_video_id: str | None = None`, `source_url: str | None = None`, `matched_title: str | None = None`.
  - `DiscogsReleaseOut.videos: list[DiscogsVideoOut] = []`.

- [ ] **Step 1: Scrivere il test che fallisce**

In `backend/tests/test_discovery_router_http.py`, individuare l'helper `_fake_release()` esistente e aggiungere un test che verifica i `videos` nel dettaglio release. Aggiungere in fondo al file:

```python
def test_release_detail_exposes_youtube_videos(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient

    c, _ = client
    payload = {
        "id": 42,
        "title": "Artist - EP",
        "artists": [{"name": "Artist"}],
        "labels": [{"name": "Lbl"}],
        "images": [],
        "uri": "/release/42",
        "year": 2001,
        "tracklist": [{"type_": "track", "position": "A", "title": "Acid Trip", "duration": "5:00"}],
        "videos": [
            {"uri": "https://www.youtube.com/watch?v=abcdefghijk", "title": "Artist - Acid Trip", "duration": 300},
            {"uri": "https://vimeo.com/1", "title": "nope", "duration": 1},
        ],
    }
    monkeypatch.setattr(DiscogsClient, "get_release", lambda self, rid: payload)

    r = c.get("/api/discovery/release/42")
    assert r.status_code == 200
    body = r.json()
    assert body["videos"] == [
        {"youtube_video_id": "abcdefghijk", "title": "Artist - Acid Trip", "duration_seconds": 300}
    ]
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_router_http.py::test_release_detail_exposes_youtube_videos -v`
Expected: FAIL — la risposta non contiene la chiave `videos` (o KeyError).

- [ ] **Step 3: Aggiungere gli schemi**

In `backend/app/schemas.py`, subito dopo la classe `DiscogsTrackOut` (righe ~546-549) aggiungere:

```python
class DiscogsVideoOut(BaseModel):
    youtube_video_id: str
    title: str
    duration_seconds: int | None = None
```

e aggiungere il campo `videos` alla classe `DiscogsReleaseOut`:

```python
class DiscogsReleaseOut(BaseModel):
    discogs_id: int
    title: str
    artist: str
    thumb_url: str | None = None
    discogs_url: str | None = None
    year: int | None = None
    label: str | None = None
    tracks: list[DiscogsTrackOut] = []
    videos: list[DiscogsVideoOut] = []
```

In fondo al blocco discovery degli schemi aggiungere:

```python
class DiscoveryPreviewOut(BaseModel):
    kind: str  # "itunes" | "youtube" | "none"
    audio_url: str | None = None
    youtube_video_id: str | None = None
    source_url: str | None = None
    matched_title: str | None = None
```

- [ ] **Step 4: Serializzare i video nel router**

In `backend/app/routers/discovery.py`, in cima ai import di schema aggiungere `DiscogsVideoOut` e `DiscoveryPreviewOut` all'elenco già importato da `app.schemas`, e importare l'helper:

```python
from app.services.preview import extract_youtube_videos
```

Nella funzione `get_release_detail`, dentro la costruzione di `DiscogsReleaseOut(...)` (righe ~272-283), aggiungere il campo `videos`:

```python
    return DiscogsReleaseOut(
        discogs_id=discogs_id,
        title=payload.get("title") or "",
        artist=artist,
        thumb_url=images[0].get("uri") if images else None,
        discogs_url=f"https://www.discogs.com{uri}" if uri.startswith("/") else (uri or None),
        year=payload.get("year"),
        label=labels[0].get("name") if labels else None,
        tracks=tracks,
        videos=[DiscogsVideoOut(**v) for v in extract_youtube_videos(payload)],
    )
```

- [ ] **Step 5: Eseguire il test e verificare che passi**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_router_http.py -v`
Expected: tutti passed (incluso il nuovo test).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/discovery.py backend/tests/test_discovery_router_http.py
git commit -m "feat(discovery): espone i video YouTube della release nel dettaglio"
```

---

## Task 4: Endpoint `GET /api/discovery/preview`

**Files:**
- Modify: `backend/app/routers/discovery.py` (nuovo endpoint + cache TTL del `get_release`)
- Test: `backend/tests/test_discovery_preview_http.py`

**Interfaces:**
- Consumes: `ItunesClient` (Task 1), `resolve_preview` (Task 2), `DiscoveryPreviewOut` (Task 3), `DiscogsClient` (esistente).
- Produces: `GET /api/discovery/preview?artist=&title=&discogs_id=&level=` → `DiscoveryPreviewOut`.

- [ ] **Step 1: Scrivere il test che fallisce**

Create `backend/tests/test_discovery_preview_http.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)

    def _get_db():
        db = S()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_preview_itunes_hit(client, monkeypatch):
    from app.integrations.itunes import ItunesClient

    monkeypatch.setattr(
        ItunesClient, "search",
        lambda self, term, limit=5: [
            {"trackName": "Acid Trip", "artistName": "Artist", "previewUrl": "http://p", "trackViewUrl": "http://v"}
        ],
    )
    r = client.get("/api/discovery/preview", params={"artist": "Artist", "title": "Acid Trip"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "itunes"
    assert body["audio_url"] == "http://p"


def test_preview_youtube_fallback(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient
    from app.integrations.itunes import ItunesClient

    monkeypatch.setattr(ItunesClient, "search", lambda self, term, limit=5: [])
    monkeypatch.setattr(
        DiscogsClient, "get_release",
        lambda self, rid: {"videos": [{"uri": "https://youtu.be/abcdefghijk", "title": "Artist - Acid Trip", "duration": 200}]},
    )
    r = client.get("/api/discovery/preview", params={"artist": "Artist", "title": "Acid Trip", "discogs_id": 42})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "youtube"
    assert body["youtube_video_id"] == "abcdefghijk"


def test_preview_none(client, monkeypatch):
    from app.integrations.itunes import ItunesClient

    monkeypatch.setattr(ItunesClient, "search", lambda self, term, limit=5: [])
    r = client.get("/api/discovery/preview", params={"artist": "X", "title": "Y"})
    assert r.status_code == 200
    assert r.json()["kind"] == "none"
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_preview_http.py -v`
Expected: FAIL con 404 (endpoint inesistente).

- [ ] **Step 3: Implementare l'endpoint con cache TTL del get_release**

In `backend/app/routers/discovery.py` aggiungere gli import in cima:

```python
import time

from app.integrations.itunes import ItunesClient
from app.services.preview import resolve_preview
```

Aggiungere una piccola cache TTL a livello modulo (sotto le costanti del router, es. dopo la definizione di `router`):

```python
# Cache TTL in-memory del get_release: lo stesso disco viene interrogato più volte
# (preview della card + di più tracce). Evita chiamate Discogs ripetute.
_RELEASE_TTL_S = 600
_release_cache: dict[int, tuple[float, dict]] = {}


def _cached_get_release(client: DiscogsClient, discogs_id: int) -> dict:
    now = time.monotonic()
    cached = _release_cache.get(discogs_id)
    if cached and now - cached[0] < _RELEASE_TTL_S:
        return cached[1]
    payload = client.get_release(discogs_id)
    _release_cache[discogs_id] = (now, payload)
    return payload
```

Aggiungere l'endpoint (accanto a `/release/{discogs_id}`):

```python
@router.get("/preview", response_model=DiscoveryPreviewOut)
def get_preview(
    artist: str,
    title: str,
    discogs_id: int | None = None,
    level: str = "track",
):
    """Preview audio di un lead: iTunes (30s pulita) o fallback video YouTube della
    release Discogs. Risoluzione lazy, effimera: nessuna persistenza. Gli errori dei
    provider degradano a kind="none" (una preview mancante non è un errore)."""
    itunes = ItunesClient()
    discogs = DiscogsClient() if discogs_id is not None else None
    try:
        get_release = None
        if discogs is not None:
            get_release = lambda rid: _cached_get_release(discogs, rid)  # noqa: E731
        result = resolve_preview(
            artist, title,
            itunes_search=lambda term: itunes.search(term),
            get_release=get_release,
            discogs_id=discogs_id,
            level=level,
        )
    finally:
        itunes.close()
        if discogs is not None:
            discogs.close()
    return DiscoveryPreviewOut(
        kind=result.kind,
        audio_url=result.audio_url,
        youtube_video_id=result.youtube_video_id,
        source_url=result.source_url,
        matched_title=result.matched_title,
    )
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_preview_http.py -v`
Expected: 3 passed.

- [ ] **Step 5: Eseguire l'intera suite backend**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: tutti passed (nessuna regressione).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/discovery.py backend/tests/test_discovery_preview_http.py
git commit -m "feat(discovery): endpoint GET /api/discovery/preview"
```

---

## Task 5: Client API frontend + tipi

**Files:**
- Modify: `frontend/lib/api/types.ts` (tipo `DiscoveryPreview`; campo `videos` in `DiscogsRelease`)
- Modify: `frontend/lib/api/discovery.ts` (funzione `discoveryPreview`)

**Interfaces:**
- Consumes: `apiGet` da `frontend/lib/api/client.ts` (esistente).
- Produces:
  - Tipo `DiscoveryPreview = { kind: "itunes" | "youtube" | "none"; audio_url: string | null; youtube_video_id: string | null; source_url: string | null; matched_title: string | null }`.
  - Tipo `DiscogsVideo = { youtube_video_id: string; title: string; duration_seconds: number | null }` e `DiscogsRelease.videos: DiscogsVideo[]`.
  - `discoveryPreview(input: { artist: string; title: string; discogsId?: number | null; level?: "release" | "track" }): Promise<DiscoveryPreview>`.

- [ ] **Step 1: Aggiungere i tipi**

In `frontend/lib/api/types.ts`, vicino a `DiscogsTrack`/`DiscogsRelease` (righe ~428-443) aggiungere:

```typescript
export type DiscogsVideo = {
  youtube_video_id: string;
  title: string;
  duration_seconds: number | null;
};

export type DiscoveryPreview = {
  kind: "itunes" | "youtube" | "none";
  audio_url: string | null;
  youtube_video_id: string | null;
  source_url: string | null;
  matched_title: string | null;
};
```

e aggiungere il campo `videos` al tipo `DiscogsRelease` esistente:

```typescript
  videos: DiscogsVideo[];
```

- [ ] **Step 2: Aggiungere la funzione API**

In `frontend/lib/api/discovery.ts`, accanto a `getDiscogsRelease`, aggiungere:

```typescript
export function discoveryPreview(input: {
  artist: string;
  title: string;
  discogsId?: number | null;
  level?: "release" | "track";
}) {
  return apiGet<DiscoveryPreview>("/api/discovery/preview", {
    artist: input.artist,
    title: input.title,
    discogs_id: input.discogsId ?? undefined,
    level: input.level ?? "track",
  });
}
```

Assicurarsi che `DiscoveryPreview` sia importato/riesportato: se `discovery.ts` importa i tipi da `./types`, aggiungere `DiscoveryPreview` all'import esistente.

- [ ] **Step 3: Verificare il type-check**

Run: `cd frontend && npm run lint`
Expected: nessun errore di tipo sui file modificati.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/discovery.ts
git commit -m "feat(discovery): client API discoveryPreview + tipi"
```

---

## Task 6: Player docked + context (`preview-player.tsx`, `docked-preview-player.tsx`)

**Files:**
- Create: `frontend/lib/preview-player.tsx` (context/provider + hook)
- Create: `frontend/components/docked-preview-player.tsx` (UI fixed in basso a destra)
- Test: `frontend/tests/preview-player.test.tsx`

**Interfaces:**
- Consumes: `discoveryPreview` (Task 5), `useT` da `@/lib/i18n`.
- Produces:
  - Tipo `PreviewItem = { key: string; artist: string; title: string; discogsId: number | null; level: "release" | "track"; label: string }`.
  - `PreviewPlayerProvider({ children })` — context provider.
  - `usePreviewPlayer(): { active: PreviewItem | null; status: "idle" | "loading" | "playing" | "unavailable"; play(item: PreviewItem): void; stop(): void }`.
  - `DockedPreviewPlayer()` — da montare una sola volta nella pagina.

- [ ] **Step 1: Scrivere il test che fallisce**

Create `frontend/tests/preview-player.test.tsx`:

```tsx
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  discoveryPreview: vi.fn(),
}));

import { discoveryPreview } from "@/lib/api";
import { DockedPreviewPlayer, PreviewPlayerProvider, usePreviewPlayer } from "@/lib/preview-player";

function Harness() {
  const p = usePreviewPlayer();
  return (
    <div>
      <button onClick={() => p.play({ key: "a", artist: "Artist", title: "Acid Trip", discogsId: 42, level: "track", label: "Acid Trip" })}>
        play-a
      </button>
      <span data-testid="status">{p.status}</span>
    </div>
  );
}

function renderAll() {
  return render(
    <PreviewPlayerProvider>
      <Harness />
      <DockedPreviewPlayer />
    </PreviewPlayerProvider>,
  );
}

describe("preview player", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it("resolves an itunes preview and shows an audio element", async () => {
    (discoveryPreview as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "itunes", audio_url: "http://p", youtube_video_id: null, source_url: "http://v", matched_title: "Acid Trip",
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-a").click();
    });
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("playing"));
    expect(screen.getByTestId("preview-audio")).toHaveAttribute("src", "http://p");
  });

  it("shows unavailable when kind is none", async () => {
    (discoveryPreview as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "none", audio_url: null, youtube_video_id: null, source_url: null, matched_title: null,
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-a").click();
    });
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unavailable"));
  });

  it("renders a youtube iframe on youtube kind", async () => {
    (discoveryPreview as ReturnType<typeof vi.fn>).mockResolvedValue({
      kind: "youtube", audio_url: null, youtube_video_id: "abcdefghijk", source_url: "http://y", matched_title: "Artist - Acid Trip",
    });
    renderAll();
    await act(async () => {
      screen.getByText("play-a").click();
    });
    await waitFor(() => expect(screen.getByTestId("preview-iframe")).toBeTruthy());
    expect(screen.getByTestId("preview-iframe")).toHaveAttribute(
      "src", expect.stringContaining("youtube.com/embed/abcdefghijk"),
    );
  });
});
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `cd frontend && npm run test:unit -- preview-player`
Expected: FAIL — moduli inesistenti.

- [ ] **Step 3: Implementare context + hook**

Create `frontend/lib/preview-player.tsx`:

```tsx
"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

import { discoveryPreview, type DiscoveryPreview } from "@/lib/api";

export type PreviewItem = {
  key: string;
  artist: string;
  title: string;
  discogsId: number | null;
  level: "release" | "track";
  label: string;
};

type Status = "idle" | "loading" | "playing" | "unavailable";

type Ctx = {
  active: PreviewItem | null;
  status: Status;
  data: DiscoveryPreview | null;
  play: (item: PreviewItem) => void;
  stop: () => void;
};

const PreviewCtx = createContext<Ctx | null>(null);

export function PreviewPlayerProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<PreviewItem | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<DiscoveryPreview | null>(null);
  const reqId = useRef(0);

  const play = useCallback((item: PreviewItem) => {
    const id = ++reqId.current;
    setActive(item);
    setStatus("loading");
    setData(null);
    discoveryPreview({ artist: item.artist, title: item.title, discogsId: item.discogsId, level: item.level })
      .then((res) => {
        if (id !== reqId.current) return; // richiesta superata da un nuovo play
        setData(res);
        setStatus(res.kind === "none" ? "unavailable" : "playing");
      })
      .catch(() => {
        if (id !== reqId.current) return;
        setStatus("unavailable");
      });
  }, []);

  const stop = useCallback(() => {
    reqId.current++;
    setActive(null);
    setStatus("idle");
    setData(null);
  }, []);

  return <PreviewCtx.Provider value={{ active, status, data, play, stop }}>{children}</PreviewCtx.Provider>;
}

export function usePreviewPlayer(): Ctx {
  const ctx = useContext(PreviewCtx);
  if (!ctx) throw new Error("usePreviewPlayer must be used within PreviewPlayerProvider");
  return ctx;
}
```

- [ ] **Step 4: Implementare il player docked**

Create `frontend/components/docked-preview-player.tsx`:

```tsx
"use client";

import { X } from "lucide-react";

import { useT } from "@/lib/i18n";
import { usePreviewPlayer } from "@/lib/preview-player";

export function DockedPreviewPlayer() {
  const { active, status, data, stop } = usePreviewPlayer();
  const t = useT();
  if (!active || status === "idle") return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-line bg-panel p-3 shadow-lg">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm text-fg">{active.title}</div>
          <div className="truncate text-xs text-faint">{active.artist}</div>
        </div>
        <button aria-label={t.discovery.closePreview} onClick={stop} className="shrink-0 text-faint hover:text-fg">
          <X size={16} />
        </button>
      </div>

      {status === "loading" && <div className="py-2 text-xs text-faint">{t.discovery.previewLoading}</div>}

      {status === "unavailable" && (
        <div className="py-2 text-xs text-faint">{t.discovery.noPreview}</div>
      )}

      {status === "playing" && data?.kind === "itunes" && data.audio_url && (
        <audio data-testid="preview-audio" src={data.audio_url} controls autoPlay className="w-full" />
      )}

      {status === "playing" && data?.kind === "youtube" && data.youtube_video_id && (
        <div className="aspect-video w-full overflow-hidden rounded">
          <iframe
            data-testid="preview-iframe"
            className="h-full w-full"
            src={`https://www.youtube.com/embed/${data.youtube_video_id}?autoplay=1`}
            title={active.title}
            allow="autoplay; encrypted-media"
            allowFullScreen
          />
        </div>
      )}
    </div>
  );
}
```

Nota: le stringhe `closePreview`, `previewLoading`, `noPreview` vengono aggiunte in Task 7. Se si esegue questo task prima del 7, aggiungere subito le chiavi i18n (vedi Task 7 Step 1) per far compilare il type-check di `useT`.

- [ ] **Step 5: Eseguire i test e verificare che passino**

Run: `cd frontend && npm run test:unit -- preview-player`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/preview-player.tsx frontend/components/docked-preview-player.tsx frontend/tests/preview-player.test.tsx
git commit -m "feat(discovery): player preview docked + context"
```

---

## Task 7: Aggancio UI (pulsanti play, provider in pagina, i18n)

**Files:**
- Modify: `frontend/lib/i18n/it.ts` e `frontend/lib/i18n/en.ts` (blocco `discovery:`)
- Modify: `frontend/app/discovery/page.tsx` (montare provider + player)
- Modify: `frontend/components/discovery-tracklist-panel.tsx` (`TrackRow`: pulsante play)
- Modify: `frontend/components/discovery-lead-grid.tsx` (`LeadCell`: overlay play)

**Interfaces:**
- Consumes: `usePreviewPlayer`, `PreviewPlayerProvider`, `DockedPreviewPlayer` (Task 6).

- [ ] **Step 1: Aggiungere le stringhe i18n (IT ed EN)**

In `frontend/lib/i18n/it.ts`, dentro il blocco `discovery: { ... }` (vicino a `forLater`/`downloadNow`, ~riga 603) aggiungere:

```typescript
    playPreview: "Anteprima",
    previewLoading: "Carico l'anteprima…",
    noPreview: "Nessuna anteprima",
    closePreview: "Chiudi anteprima",
```

In `frontend/lib/i18n/en.ts`, stesso blocco (~riga 601), stesse chiavi:

```typescript
    playPreview: "Preview",
    previewLoading: "Loading preview…",
    noPreview: "No preview",
    closePreview: "Close preview",
```

- [ ] **Step 2: Montare provider + player nella pagina**

In `frontend/app/discovery/page.tsx`, aggiungere gli import:

```tsx
import { DockedPreviewPlayer } from "@/components/docked-preview-player";
import { PreviewPlayerProvider } from "@/lib/preview-player";
```

Avvolgere il contenuto renderizzato dalla pagina con `<PreviewPlayerProvider>` e montare `<DockedPreviewPlayer />` una sola volta appena dentro il provider (ad es. subito prima della chiusura del provider), così il player fixed è disponibile a tutta la pagina Scava. Esempio della struttura del `return`:

```tsx
  return (
    <PreviewPlayerProvider>
      {/* ...tutto il markup esistente della pagina, inclusa <DiscoveryLeadGrid .../> ... */}
      <DockedPreviewPlayer />
    </PreviewPlayerProvider>
  );
```

- [ ] **Step 3: Aggiungere il pulsante play in `TrackRow`**

In `frontend/components/discovery-tracklist-panel.tsx`:

Aggiungere agli import di icone `lucide-react` (riga ~4) `Play`, e importare l'hook e il tipo:

```tsx
import { Play } from "lucide-react";
import { usePreviewPlayer } from "@/lib/preview-player";
```

Il componente `TrackRow` riceve già la release/`discogsId` e la traccia. Dentro `TrackRow`, prima del `return`, ottenere il player e l'artista della traccia (l'`input` costruito a ~riga 148-151 contiene artist/title):

```tsx
  const player = usePreviewPlayer();
```

Nel gruppo bottoni `<div className="flex shrink-0 items-center gap-1.5">` (~riga 190), aggiungere come PRIMO bottone:

```tsx
        <Button
          size="sm"
          variant="outline"
          aria-label={t.discovery.playPreview}
          onClick={() =>
            player.play({
              key: `t:${discogsId ?? "x"}:${track.position}:${track.title}`,
              artist: input.artist,
              title: track.title,
              discogsId: discogsId ?? null,
              level: "track",
              label: track.title,
            })
          }
        >
          <Play size={13} />
        </Button>
```

Nota: se `discogsId` non è già una prop/variabile in `TrackRow`, ricavarlo dalla release passata al pannello (il pannello riceve `DiscogsRelease` con `discogs_id`); passarlo a `TrackRow` come prop `discogsId={release.discogs_id}` se non presente. Verificare la firma di `TrackRow` e del pannello prima di modificare.

- [ ] **Step 4: Aggiungere l'overlay play in `LeadCell`**

In `frontend/components/discovery-lead-grid.tsx`, importare l'icona e l'hook:

```tsx
import { Play } from "lucide-react";
import { usePreviewPlayer } from "@/lib/preview-player";
```

Dentro `LeadCell`, ottenere il player: `const player = usePreviewPlayer();`. La cella è un `<button onClick={onOpen}>` con l'artwork in un `<div className="relative aspect-square ...">` (~riga 122). Aggiungere dentro quel div un pulsante play in overlay che NON propaga il click alla cella:

```tsx
        <button
          type="button"
          aria-label={t.discovery.playPreview}
          className="absolute bottom-1 right-1 rounded-full bg-black/60 p-1.5 text-white opacity-0 transition group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            player.play({
              key: `r:${lead.discogs_id ?? "x"}`,
              artist: lead.artist,
              title: lead.title,
              discogsId: lead.discogs_id ?? null,
              level: "release",
              label: lead.title,
            });
          }}
        >
          <Play size={14} />
        </button>
```

Assicurarsi che il contenitore artwork abbia `group` (aggiungere `group` alla className del `<div className="relative aspect-square ...">` se non presente) perché `group-hover` funzioni. Se `t` non è già in scope in `LeadCell`, aggiungere `const t = useT();` (import `useT` da `@/lib/i18n`).

- [ ] **Step 5: Verificare lint e test**

Run: `cd frontend && npm run lint && npm run test:unit`
Expected: lint pulito, tutti i test passano.

- [ ] **Step 6: Verifica visiva nel browser**

Avviare backend (`cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000`) e frontend (`cd frontend && npm run dev`). Nel Discovery/Scava: eseguire un dig, aprire un disco, premere play su una traccia → il player appare in basso a destra; verificare che una traccia iTunes mostri la barra audio e una traccia senza iTunes ma con video Discogs mostri l'iframe YouTube; premere play su un'altra traccia ferma la precedente; una traccia senza nulla mostra "Nessuna anteprima".

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/app/discovery/page.tsx frontend/components/discovery-tracklist-panel.tsx frontend/components/discovery-lead-grid.tsx
git commit -m "feat(discovery): pulsanti play su card e tracklist + player in pagina"
```

---

## Task 8: Documentazione

**Files:**
- Modify: `docs/ARCHITECTURE.md` (righe ~30-34, sezione "does not play audio")
- Modify: `CLAUDE.md` (sezione "Project", paragrafo audio)
- Modify: `docs/API.md` (endpoint discovery + campo videos)
- Modify: `docs/DEPENDENCIES.md` (iTunes Search API)

**Interfaces:** nessuna (solo prosa).

- [ ] **Step 1: Aggiornare ARCHITECTURE.md e CLAUDE.md**

In `docs/ARCHITECTURE.md` (dopo la frase *"The app does not play audio…"*, ~riga 30) aggiungere una frase che dichiara l'eccezione:

```markdown
An additional, narrowly-scoped exception: the Discovery dig plays an **ephemeral
third-party preview** to evaluate a lead before acquiring it — a 30s iTunes clip or,
as a fallback, the YouTube video Discogs associates with the release. Nothing is
downloaded or kept; the audio is streamed from iTunes/YouTube and discarded.
```

In `CLAUDE.md`, nel paragrafo del progetto che descrive lo scope audio, aggiungere una frase equivalente (in italiano, coerente col resto del file) che cita la preview effimera di terzi nel Discovery accanto alle eccezioni Shazam/Soulseek.

- [ ] **Step 2: Aggiornare API.md**

In `docs/API.md`, nella sezione Discovery, documentare il nuovo endpoint e il campo `videos`:

```markdown
### `GET /api/discovery/preview`

Preview audio effimera di un lead del dig. Query: `artist`, `title`,
`discogs_id` (opzionale), `level` (`release`|`track`, default `track`).
Risponde `DiscoveryPreviewOut { kind: "itunes"|"youtube"|"none", audio_url,
youtube_video_id, source_url, matched_title }`. iTunes è primario (clip 30s);
fallback al video YouTube della release Discogs. Errori dei provider → `kind: "none"`
(HTTP 200). Nessuna persistenza.

Il dettaglio release `GET /api/discovery/release/{discogs_id}` ora include anche
`videos: [{ youtube_video_id, title, duration_seconds }]`.
```

- [ ] **Step 3: Aggiornare DEPENDENCIES.md**

In `docs/DEPENDENCIES.md` aggiungere una voce per iTunes Search API:

```markdown
### iTunes Search API (Apple)

- **Uso:** preview audio (clip 30s) dei lead del Discovery dig. Sorgente primaria,
  con fallback ai video YouTube già presenti nel payload Discogs.
- **Endpoint:** `GET https://itunes.apple.com/search` — pubblico, **nessuna auth,
  nessun token**.
- **Nota ToS (fallback YouTube):** l'embed dei video YouTube della release comporta
  la possibile riproduzione di pubblicità e una zona grigia dei ToS YouTube;
  accettata per uso personale/self-hosted single-user (nessuna distribuzione).
```

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md CLAUDE.md docs/API.md docs/DEPENDENCIES.md
git commit -m "docs: preview audio discovery (iTunes + fallback YouTube)"
```

---

## Self-Review checklist (già eseguita in fase di scrittura)

- **Copertura spec:** iTunes client (T1), resolve_preview + fallback + level (T2), videos in release (T3), endpoint + cache TTL (T4), API client/tipi (T5), player docked + one-at-a-time (T6), pulsanti card+tracklist + i18n + provider in pagina (T7), doc/eccezione principio (T8). Tutte le sezioni dello spec hanno un task.
- **Player docked in basso a destra:** T6 (`position: fixed bottom-4 right-4`).
- **Un solo player attivo:** garantito da `reqId` + stato singolo nel provider (T6).
- **Player differenziato per sorgente:** `<audio>` per iTunes, iframe per YouTube (T6).
- **Errori provider → none (200):** gestito in `resolve_preview` (T2) e nell'endpoint (T4).
- **Type consistency:** `DiscoveryPreview`/`DiscoveryPreviewOut` con gli stessi campi FE/BE; `PreviewItem.level` ∈ {`release`,`track`} coerente con il param `level` dell'endpoint; `discoveryPreview(...)` firma coerente tra T5 (definizione) e T6/T7 (uso).
```
