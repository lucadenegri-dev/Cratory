# Soulseek Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquisire i file audio di tracce gia' in libreria via il daemon Soulseek headless slskd, collegando ogni file scaricato alla sua `Track` (ownership), con una sezione Download per-playlist e un bottone Download in Discovery.

**Architecture:** Cratory orchestra; slskd fa la rete P2P. Un client HTTP (`integrations/slskd.py`) parla con la REST API di slskd. Un motore di selezione deterministico (`services/soulseek_select.py`) ordina i candidati per qualita' e aderenza ad artista+titolo. Un job in background (`services/soulseek_download_job.py`, stesso pattern threading di `local_import_job`) cerca, accoda, polla il transfer e collega il file alla `Track`. Un router (`routers/downloads.py`) espone gli endpoint. Frontend: una pagina `app/downloads` e un bottone in `LeadRow` di Discovery.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy 2.0 (SQLite), httpx, mutagen, pytest; Next.js 16 (App Router, React 19, `"use client"`), Tailwind/design system interno.

## Global Constraints

- Motore deterministico e AI separati: **nessuna AI** nel percorso di selezione/acquisizione. Tutto deterministico (CLAUDE.md regola 1).
- BPM/key/feature musicali non si toccano qui: l'acquisizione NON modifica `bpm`/`camelot_key`/feature (CLAUDE.md regole 2-3).
- Integrazioni esterne dietro interfacce in `backend/app/integrations/`, **iniettabili e fakeabili** nei test (niente rete nei test) (ARCHITECTURE.md).
- I router non contengono logica di business: solo HTTP e mapping errori (ARCHITECTURE.md).
- Migrazioni idempotenti in `ensure_schema()`: niente Alembic; `ALTER TABLE ADD COLUMN` solo se la colonna non esiste (db.py).
- Possesso del file separato dallo `status` di enrichment: nuovi campi `has_local_file`/`local_format`/`local_bitrate`, **non** un nuovo valore di `status` (spec).
- Preferenza qualita' di default: lossless prima -> MP3 >= 320 -> mai sotto 256 kbps.
- Degradazione pulita: se slskd non e' configurato, gli endpoint rispondono 409 e l'UI mostra lo stato disabilitato (pattern Shazam/`_deps_available`).
- slskd usato **solo come downloader**: nessuna funzione di condivisione.
- Frontend: leggere sempre `frontend/CLAUDE.md`. Next.js 16 ha breaking changes; le rotte dinamiche usano `params: Promise<...>` + `use(params)`; pagine interattive `"use client"`.
- Stile commit: **niente** trailer `Co-Authored-By`.

## Pre-flight (confermare prima di iniziare)

Gli endpoint slskd usati nel Task 2-3 sono basati sull'API slskd v0. **Confermarli contro lo Swagger del proprio slskd** (`<SLSKD_URL>/swagger`) prima di scrivere il client. Se differiscono, l'unico file da adattare e' `integrations/slskd.py` (i test asseriscono la forma assunta). Endpoint assunti:
- `POST /api/v0/searches` body `{"searchText": "<q>"}` -> `{"id": "<uuid>", ...}`
- `GET /api/v0/searches/{id}` -> `{"isComplete": bool, "state": "..."}`
- `GET /api/v0/searches/{id}/responses` -> `[{username, hasFreeUploadSlot, queueLength, files:[{filename,size,bitRate,length}]}]`
- `POST /api/v0/transfers/downloads/{username}` body `[{"filename","size"}]`
- `GET /api/v0/transfers/downloads/{username}` -> `{"directories":[{"files":[{filename,state}]}]}`
- Auth header: `X-API-Key: <key>`

---

### Task 1: Config slskd

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example` (se esiste; altrimenti saltare quel passo)
- Test: `backend/tests/test_slskd_config.py`

**Interfaces:**
- Produces: `settings.slskd_url: str`, `settings.slskd_api_key: str`, `settings.slskd_download_dir: str` (default `""`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_slskd_config.py
from app.core.config import Settings


def test_slskd_defaults_empty():
    s = Settings(_env_file=None)
    assert s.slskd_url == ""
    assert s.slskd_api_key == ""
    assert s.slskd_download_dir == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_slskd_config.py -v`
Expected: FAIL con `AttributeError: 'Settings' object has no attribute 'slskd_url'`.

- [ ] **Step 3: Add the settings fields**

In `backend/app/core/config.py`, dentro la classe `Settings` (accanto a `discogs_token`), aggiungere:

```python
    slskd_url: str = ""
    slskd_api_key: str = ""
    slskd_download_dir: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_slskd_config.py -v`
Expected: PASS.

- [ ] **Step 5: Update .env.example (se presente)**

Se `backend/.env.example` esiste, aggiungere:

```bash
# slskd (Soulseek download) — lascia vuoto per disattivare
SLSKD_URL=
SLSKD_API_KEY=
SLSKD_DOWNLOAD_DIR=
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_slskd_config.py
git add backend/.env.example 2>/dev/null || true
git commit -m "feat(slskd): config SLSKD_URL/API_KEY/DOWNLOAD_DIR"
```

---

### Task 2: SlskdClient — ricerca

**Files:**
- Create: `backend/app/integrations/slskd.py`
- Test: `backend/tests/test_slskd_client.py`

**Interfaces:**
- Consumes: `app.integrations._http.get_with_retries`, `app.core.config.settings`.
- Produces:
  - `class SlskdError(Exception)`, `class SlskdNotConfigured(SlskdError)`
  - `@dataclass SlskdFile(username, filename, size, bitrate, length, has_free_slot, queue_length)` con `.extension -> str`
  - `class SlskdClient(url=None, api_key=None, http=None)` con `search(artist, title, *, wait_seconds=8.0, poll_interval=1.0) -> list[SlskdFile]`
  - `slskd_configured() -> bool`, `get_slskd_client() -> SlskdClient`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_slskd_client.py
from app.integrations.slskd import SlskdClient, SlskdFile


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text, self.content = payload, status, "", b"x"

    def json(self):
        return self._p


class _FakeHttp:
    """Risponde in base al path; registra le chiamate. Nessuna rete."""

    def __init__(self, routes):
        self.routes = routes  # dict: substring del path -> payload
        self.calls = []

    def _match(self, url):
        for frag, payload in self.routes.items():
            if frag in url:
                return payload
        return {}

    def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        return _Resp(self._match(url))

    def post(self, url, json=None):
        self.calls.append(("POST", url, json))
        return _Resp(self._match(url))


def test_search_aggregates_files_from_responses():
    routes = {
        "/searches/abc/responses": [
            {
                "username": "bob",
                "hasFreeUploadSlot": True,
                "queueLength": 0,
                "files": [
                    {"filename": "Bob\\Daft Punk - Da Funk.flac", "size": 40000000,
                     "bitRate": None, "length": 220},
                ],
            }
        ],
        "/searches/abc": {"isComplete": True, "state": "Completed"},
        "/searches": {"id": "abc"},
    }
    http = _FakeHttp(routes)
    c = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    files = c.search("Daft Punk", "Da Funk", wait_seconds=0.0, poll_interval=0.0)
    assert len(files) == 1
    f = files[0]
    assert isinstance(f, SlskdFile)
    assert f.username == "bob"
    assert f.extension == "flac"
    assert f.has_free_slot is True
    # la POST di creazione ricerca include il searchText
    post = next(call for call in http.calls if call[0] == "POST")
    assert post[2] == {"searchText": "Daft Punk Da Funk"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_slskd_client.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.integrations.slskd'`.

- [ ] **Step 3: Write the client (search part)**

```python
# backend/app/integrations/slskd.py
"""Client per il daemon Soulseek headless slskd (REST API v0).

slskd fa la rete P2P (login, peer, code); Cratory orchestra. Usato SOLO come
downloader: non si sfrutta la condivisione. Confermare gli endpoint contro
lo Swagger del proprio slskd (<SLSKD_URL>/swagger).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings
from app.integrations._http import get_with_retries

BASE = "/api/v0"


class SlskdError(Exception):
    """Errore di comunicazione con slskd."""


class SlskdNotConfigured(SlskdError):
    """SLSKD_URL non impostato."""


@dataclass
class SlskdFile:
    """Un file candidato restituito da una ricerca slskd."""

    username: str
    filename: str
    size: int | None
    bitrate: int | None
    length: int | None
    has_free_slot: bool
    queue_length: int | None

    @property
    def extension(self) -> str:
        return Path(self.filename.replace("\\", "/")).suffix.lower().lstrip(".")


class SlskdClient:
    def __init__(self, url: str | None = None, api_key: str | None = None,
                 http: httpx.Client | None = None):
        self.url = (url if url is not None else settings.slskd_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.slskd_api_key
        if not self.url:
            raise SlskdNotConfigured("SLSKD_URL mancante in backend/.env.")
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        self.http = http or httpx.Client(timeout=30, headers=headers)

    def _get(self, path: str, params: dict | None = None):
        r = get_with_retries(self.http, f"{self.url}{BASE}{path}",
                             error_cls=SlskdError, params=params)
        if r.status_code >= 400:
            raise SlskdError(f"slskd {r.status_code}: {r.text[:160]}")
        return r.json()

    def _post(self, path: str, json=None):
        try:
            r = self.http.post(f"{self.url}{BASE}{path}", json=json)
        except httpx.HTTPError as exc:
            raise SlskdError(f"slskd POST {path} fallita: {exc}") from exc
        if r.status_code >= 400:
            raise SlskdError(f"slskd {r.status_code}: {r.text[:160]}")
        return r.json() if r.content else {}

    def search(self, artist: str, title: str, *, wait_seconds: float = 8.0,
               poll_interval: float = 1.0) -> list[SlskdFile]:
        text = f"{artist} {title}".strip()
        if not text:
            return []
        created = self._post("/searches", json={"searchText": text})
        search_id = created.get("id")
        if not search_id:
            raise SlskdError("slskd: ricerca senza id.")
        waited = 0.0
        while waited < wait_seconds:
            state = self._get(f"/searches/{search_id}")
            if state.get("isComplete") or "completed" in str(state.get("state", "")).lower():
                break
            time.sleep(poll_interval)
            waited += poll_interval
        responses = self._get(f"/searches/{search_id}/responses")
        return self._flatten_responses(responses)

    @staticmethod
    def _flatten_responses(responses) -> list[SlskdFile]:
        out: list[SlskdFile] = []
        for resp in responses or []:
            username = resp.get("username") or ""
            has_slot = bool(resp.get("hasFreeUploadSlot"))
            queue = resp.get("queueLength")
            for f in resp.get("files") or []:
                out.append(SlskdFile(
                    username=username,
                    filename=f.get("filename") or "",
                    size=f.get("size"),
                    bitrate=f.get("bitRate"),
                    length=f.get("length"),
                    has_free_slot=has_slot,
                    queue_length=queue,
                ))
        return out


def slskd_configured() -> bool:
    return bool(settings.slskd_url and settings.slskd_download_dir)


def get_slskd_client() -> SlskdClient:
    if not settings.slskd_url:
        raise SlskdNotConfigured("SLSKD_URL mancante in backend/.env.")
    return SlskdClient()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_slskd_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/slskd.py backend/tests/test_slskd_client.py
git commit -m "feat(slskd): client search + SlskdFile + factory"
```

---

### Task 3: SlskdClient — download e stato transfer

**Files:**
- Modify: `backend/app/integrations/slskd.py`
- Test: `backend/tests/test_slskd_transfers.py`

**Interfaces:**
- Consumes: `SlskdClient`, `SlskdFile` (Task 2).
- Produces:
  - `SlskdClient.enqueue_download(file: SlskdFile) -> None`
  - `SlskdClient.transfer_state(username: str, filename: str) -> dict | None`
  - `classify_transfer_state(state: str) -> str` (`"completed" | "failed" | "in_progress"`)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_slskd_transfers.py
from app.integrations.slskd import SlskdClient, SlskdFile, classify_transfer_state


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text, self.content = payload, status, "", b"x"

    def json(self):
        return self._p


class _FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _match(self, url):
        for frag, payload in self.routes.items():
            if frag in url:
                return payload
        return {}

    def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        return _Resp(self._match(url))

    def post(self, url, json=None):
        self.calls.append(("POST", url, json))
        return _Resp(self._match(url))


def _file():
    return SlskdFile(username="bob", filename="Bob\\x.flac", size=10, bitrate=None,
                     length=None, has_free_slot=True, queue_length=0)


def test_enqueue_posts_file_list():
    http = _FakeHttp({"/transfers/downloads/bob": {}})
    c = SlskdClient(url="http://h", api_key="k", http=http)
    c.enqueue_download(_file())
    post = http.calls[0]
    assert post[0] == "POST"
    assert post[1].endswith("/transfers/downloads/bob")
    assert post[2] == [{"filename": "Bob\\x.flac", "size": 10}]


def test_transfer_state_finds_file():
    routes = {"/transfers/downloads/bob": {
        "directories": [{"files": [{"filename": "Bob\\x.flac", "state": "Completed, Succeeded"}]}]
    }}
    c = SlskdClient(url="http://h", api_key="k", http=_FakeHttp(routes))
    st = c.transfer_state("bob", "Bob\\x.flac")
    assert st["state"] == "Completed, Succeeded"


def test_classify_transfer_state():
    assert classify_transfer_state("Completed, Succeeded") == "completed"
    assert classify_transfer_state("Completed, Errored") == "failed"
    assert classify_transfer_state("Cancelled") == "failed"
    assert classify_transfer_state("InProgress") == "in_progress"
    assert classify_transfer_state("") == "in_progress"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_slskd_transfers.py -v`
Expected: FAIL con `ImportError: cannot import name 'classify_transfer_state'`.

- [ ] **Step 3: Add transfer methods and classifier**

In `backend/app/integrations/slskd.py`, aggiungere i due metodi dentro `SlskdClient` (dopo `search`):

```python
    def enqueue_download(self, file: "SlskdFile") -> None:
        self._post(f"/transfers/downloads/{file.username}",
                   json=[{"filename": file.filename, "size": file.size or 0}])

    def transfer_state(self, username: str, filename: str) -> dict | None:
        data = self._get(f"/transfers/downloads/{username}")
        for directory in data.get("directories") or []:
            for f in directory.get("files") or []:
                if f.get("filename") == filename:
                    return f
        return None
```

E in fondo al modulo, la funzione a livello di modulo:

```python
def classify_transfer_state(state: str) -> str:
    s = (state or "").lower()
    if any(x in s for x in ("errored", "failed", "cancelled", "canceled",
                            "rejected", "timedout")):
        return "failed"
    if "completed" in s or "succeeded" in s:
        return "completed"
    return "in_progress"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_slskd_transfers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/slskd.py backend/tests/test_slskd_transfers.py
git commit -m "feat(slskd): enqueue_download + transfer_state + classify"
```

---

### Task 4: Motore di selezione deterministico

**Files:**
- Create: `backend/app/services/soulseek_select.py`
- Test: `backend/tests/test_soulseek_select.py`

**Interfaces:**
- Consumes: `app.integrations.slskd.SlskdFile`.
- Produces:
  - `@dataclass(frozen=True) QualityPreference(prefer_lossless=True, min_bitrate=256, preferred_bitrate=320)`
  - `@dataclass ScoredCandidate(file, name_score, quality_tier, score, confidence)`
  - `rank_candidates(files, *, artist, title, pref=QualityPreference()) -> list[ScoredCandidate]`
  - `best_for_auto(files, *, artist, title, pref=QualityPreference()) -> ScoredCandidate | None`
  - `AUTO_PICK_MIN_CONFIDENCE = 0.7`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_soulseek_select.py
from app.integrations.slskd import SlskdFile
from app.services.soulseek_select import (
    QualityPreference, best_for_auto, rank_candidates,
)


def _f(filename, *, bitrate=None, slot=True):
    return SlskdFile(username="u", filename=filename, size=1, bitrate=bitrate,
                     length=None, has_free_slot=slot, queue_length=0)


def test_lossless_outranks_mp3_for_same_name():
    files = [
        _f("Daft Punk - Da Funk.mp3", bitrate=320),
        _f("Daft Punk - Da Funk.flac"),
    ]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked[0].file.extension == "flac"


def test_below_min_bitrate_excluded():
    files = [_f("Daft Punk - Da Funk.mp3", bitrate=128)]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked == []


def test_weak_name_match_excluded():
    files = [_f("Completely Unrelated Song.flac")]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked == []


def test_best_for_auto_returns_none_below_threshold():
    # match parziale: nome plausibile ma non perfetto, solo mp3 a 256
    files = [_f("daft - da funk (live bootleg rip).mp3", bitrate=256)]
    best = best_for_auto(files, artist="Daft Punk", title="Da Funk")
    # confidence sotto 0.7 -> niente auto-pick
    assert best is None


def test_best_for_auto_picks_strong_lossless():
    files = [_f("Daft Punk - Da Funk.flac")]
    best = best_for_auto(files, artist="Daft Punk", title="Da Funk")
    assert best is not None
    assert best.confidence >= 0.7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_select.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.soulseek_select'`.

- [ ] **Step 3: Write the selection engine**

```python
# backend/app/services/soulseek_select.py
"""Selezione deterministica del candidato Soulseek (zero AI).

Ordina i file restituiti da slskd per aderenza ad artista+titolo e qualita',
secondo una preferenza configurabile.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.integrations.slskd import SlskdFile

_SPACE_RE = re.compile(r"\s+")
LOSSLESS_EXTS = {"flac", "wav", "aiff", "aif", "alac", "ape"}
LOSSY_EXTS = {"mp3", "m4a", "aac", "ogg", "opus", "wma"}

AUTO_PICK_MIN_CONFIDENCE = 0.7
_MIN_NAME_SCORE = 0.45


@dataclass(frozen=True)
class QualityPreference:
    prefer_lossless: bool = True
    min_bitrate: int = 256
    preferred_bitrate: int = 320


@dataclass
class ScoredCandidate:
    file: SlskdFile
    name_score: float
    quality_tier: int
    score: float
    confidence: float


def _norm(text: str | None) -> str:
    text = (text or "").lower().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _name_score(file: SlskdFile, artist: str, title: str) -> float:
    hay = _norm(file.filename.replace("\\", "/").replace("/", " "))
    a, t = _norm(artist), _norm(title)
    s = 0.0
    if t:
        s += SequenceMatcher(None, t, hay).ratio() * 0.6
        if t in hay:
            s += 0.15
    if a:
        s += SequenceMatcher(None, a, hay).ratio() * 0.2
        if a in hay:
            s += 0.05
    return min(s, 1.0)


def _quality_tier(file: SlskdFile, pref: QualityPreference) -> int:
    ext = file.extension
    if ext in LOSSLESS_EXTS:
        return 3
    if ext in LOSSY_EXTS:
        br = file.bitrate or 0
        if br >= pref.preferred_bitrate:
            return 2
        if br >= pref.min_bitrate:
            return 1
        return 0
    return 0


def rank_candidates(files, *, artist: str, title: str,
                    pref: QualityPreference = QualityPreference()) -> list[ScoredCandidate]:
    scored: list[ScoredCandidate] = []
    for f in files:
        tier = _quality_tier(f, pref)
        if tier == 0:
            continue
        name = _name_score(f, artist, title)
        if name < _MIN_NAME_SCORE:
            continue
        avail = 1.0 if f.has_free_slot else 0.6
        score = name * 100 + tier * 12 + avail * 5
        confidence = round(min(1.0, name * 0.8 + (tier / 3) * 0.2), 3)
        scored.append(ScoredCandidate(file=f, name_score=round(name, 3),
                                      quality_tier=tier, score=round(score, 2),
                                      confidence=confidence))
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def best_for_auto(files, *, artist: str, title: str,
                  pref: QualityPreference = QualityPreference()) -> ScoredCandidate | None:
    ranked = rank_candidates(files, artist=artist, title=title, pref=pref)
    if ranked and ranked[0].confidence >= AUTO_PICK_MIN_CONFIDENCE:
        return ranked[0]
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_select.py -v`
Expected: PASS. (Se `test_best_for_auto_returns_none_below_threshold` non scendesse sotto soglia, regolare `_MIN_NAME_SCORE`/pesi: il punto e' che un match dubbio NON parte in automatico.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/soulseek_select.py backend/tests/test_soulseek_select.py
git commit -m "feat(soulseek): motore di selezione deterministico dei candidati"
```

---

### Task 5: Lettura formato/bitrate del file scaricato

**Files:**
- Modify: `backend/app/integrations/local_files.py`
- Test: `backend/tests/test_local_files.py` (estendere)

**Interfaces:**
- Produces: `read_audio_quality(path) -> dict` con chiavi `{"format": str | None, "bitrate": int | None}` (bitrate in kbps).

- [ ] **Step 1: Write the failing test**

Aggiungere a `backend/tests/test_local_files.py` (riusa `_write_wav` gia' presente nel file):

```python
def test_read_audio_quality_returns_format(tmp_path):
    from app.integrations.local_files import read_audio_quality
    p = tmp_path / "a.wav"
    _write_wav(p, secs=1.0)
    q = read_audio_quality(p)
    assert q["format"] == "wav"
    # il bitrate puo' essere None o un intero, ma la chiave esiste
    assert "bitrate" in q
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_files.py::test_read_audio_quality_returns_format -v`
Expected: FAIL con `ImportError: cannot import name 'read_audio_quality'`.

- [ ] **Step 3: Add read_audio_quality**

In `backend/app/integrations/local_files.py` (accanto a `read_tags`):

```python
def read_audio_quality(path: str | Path) -> dict:
    """Formato (estensione) e bitrate (kbps) del file. Valori assenti -> None."""
    p = Path(path)
    out = {"format": p.suffix.lower().lstrip(".") or None, "bitrate": None}
    try:
        audio = mutagen.File(str(p))
    except Exception:
        return out
    info = getattr(audio, "info", None) if audio else None
    bitrate = getattr(info, "bitrate", None) if info else None
    if bitrate:
        out["bitrate"] = int(bitrate) // 1000
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_files.py::test_read_audio_quality_returns_format -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/local_files.py backend/tests/test_local_files.py
git commit -m "feat(local-files): read_audio_quality (formato + bitrate)"
```

---

### Task 6: Ownership — colonne, migrazione, serializzazione, attach

**Files:**
- Modify: `backend/app/models.py` (modello `Track`, import `Boolean`)
- Modify: `backend/app/db.py` (`additions["tracks"]`)
- Modify: `backend/app/schemas.py` (`TrackOut`)
- Modify: `backend/app/serializers.py` (`track_out`)
- Modify: `backend/app/repositories.py` (helper query)
- Create: `backend/app/services/acquisition.py`
- Test: `backend/tests/test_acquisition.py`

**Interfaces:**
- Produces:
  - `Track.has_local_file: bool`, `Track.local_format: str | None`, `Track.local_bitrate: int | None` (e `Track.local_path` gia' esistente).
  - `repositories.tracks_without_local_file(db, playlist_id) -> list[Track]`
  - `services.acquisition.attach_local_file(db, track, *, path, fmt=None, bitrate=None) -> Track`
  - `TrackOut` con `has_local_file/local_path/local_format/local_bitrate`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_acquisition.py
from app.models import Track
from app.repositories import tracks_without_local_file
from app.services.acquisition import attach_local_file


def test_attach_local_file_sets_ownership_fields(db):
    t = Track(platform="spotify", spotify_id="s1", source_type="spotify",
              title="Da Funk", artist="Daft Punk", status="imported")
    db.add(t)
    db.commit()
    attach_local_file(db, t, path="/music/x.flac", fmt="flac", bitrate=1000)
    db.refresh(t)
    assert t.has_local_file is True
    assert t.local_path == "/music/x.flac"
    assert t.local_format == "flac"
    assert t.local_bitrate == 1000
    # lo status di enrichment NON viene toccato
    assert t.status == "imported"


def test_tracks_without_local_file_filters(db):
    from app.models import Playlist
    from app.repositories import import_playlist  # gia' esistente
    pl = Playlist(name="PL", platform="spotify", platform_playlist_id="pl1", kind="spotify")
    db.add(pl)
    db.commit()
    owned = Track(platform="spotify", spotify_id="o", source_type="spotify",
                  title="A", artist="X", has_local_file=True)
    missing = Track(platform="spotify", spotify_id="m", source_type="spotify",
                    title="B", artist="Y")
    owned.playlists.append(pl)
    missing.playlists.append(pl)
    db.add_all([owned, missing])
    db.commit()
    result = tracks_without_local_file(db, pl.id)
    ids = {t.spotify_id for t in result}
    assert ids == {"m"}
```

> Nota: se la costruzione di `Playlist`/append della relazione differisce dalle factory reali, allineare al pattern in `tests/conftest.py`/`test_playlist_sync.py` (la relazione `Track.playlists` e' confermata da `serializers.track_out`). Il punto del test resta: solo le tracce con `has_local_file` falso/nullo tornano.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_acquisition.py -v`
Expected: FAIL (`ModuleNotFoundError` su `app.services.acquisition` o `AttributeError` su `has_local_file`).

- [ ] **Step 3: Add the model columns**

In `backend/app/models.py`: assicurarsi che `Boolean` sia importato da `sqlalchemy` (aggiungerlo alla riga di import esistente `from sqlalchemy import ...` se manca). Poi, dentro `class Track`, accanto a `local_path`:

```python
    has_local_file: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    local_format: Mapped[str | None] = mapped_column(String)
    local_bitrate: Mapped[int | None] = mapped_column(Integer)
```

- [ ] **Step 4: Add the idempotent migration**

In `backend/app/db.py`, dentro il dict `additions["tracks"]`, aggiungere:

```python
            "has_local_file": "BOOLEAN DEFAULT 0",
            "local_format": "VARCHAR",
            "local_bitrate": "INTEGER",
```

(Se `local_path` non e' gia' presente in `additions["tracks"]`, aggiungere anche `"local_path": "TEXT",` per i DB esistenti.)

- [ ] **Step 5: Add schema + serializer fields**

In `backend/app/schemas.py`, dentro `class TrackOut`:

```python
    has_local_file: bool = False
    local_path: str | None = None
    local_format: str | None = None
    local_bitrate: int | None = None
```

In `backend/app/serializers.py`, dentro `track_out(...)`, aggiungere ai kwargs di `TrackOut(...)`:

```python
        has_local_file=bool(track.has_local_file),
        local_path=track.local_path,
        local_format=track.local_format,
        local_bitrate=track.local_bitrate,
```

- [ ] **Step 6: Add the repository helper**

In `backend/app/repositories.py` (assicurarsi che `Playlist` e `select` siano importati; lo sono gia' per le altre query):

```python
def tracks_without_local_file(db: Session, playlist_id: int) -> list[Track]:
    """Tracce della playlist senza file locale (coda della sezione Download)."""
    return list(db.scalars(
        select(Track)
        .join(Track.playlists)
        .where(Playlist.id == playlist_id)
        .where((Track.has_local_file.is_(False)) | (Track.has_local_file.is_(None)))
        .order_by(Track.artist, Track.title)
    ))
```

- [ ] **Step 7: Add the acquisition service**

```python
# backend/app/services/acquisition.py
"""Collega un file audio acquisito a una Track esistente (ownership).

Non tocca lo status di enrichment ne' le feature musicali.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Track


def attach_local_file(db: Session, track: Track, *, path: str,
                      fmt: str | None = None, bitrate: int | None = None) -> Track:
    track.has_local_file = True
    track.local_path = path
    track.local_format = fmt
    track.local_bitrate = bitrate
    db.commit()
    db.refresh(track)
    return track
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_acquisition.py -v`
Expected: PASS.

- [ ] **Step 9: Run the full suite (no regressions on serializer/schema)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: tutti verdi.

- [ ] **Step 10: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/app/schemas.py \
        backend/app/serializers.py backend/app/repositories.py \
        backend/app/services/acquisition.py backend/tests/test_acquisition.py
git commit -m "feat(acquisition): campi ownership su Track + attach_local_file"
```

---

### Task 7: Job di download in background

**Files:**
- Create: `backend/app/services/soulseek_download_job.py`
- Test: `backend/tests/test_soulseek_download_job.py`

**Interfaces:**
- Consumes: `slskd.get_slskd_client`, `slskd.SlskdFile`, `slskd.classify_transfer_state`, `soulseek_select.best_for_auto`, `acquisition.attach_local_file`, `repositories.{get_track, tracks_without_local_file}`, `local_files.read_audio_quality`, `db.SessionLocal`, `config.settings`.
- Produces:
  - `job_state() -> dict`, `is_running() -> bool`
  - `start_playlist_job(playlist_id: int) -> dict`
  - `start_track_job(track_id: int, chosen: SlskdFile) -> dict`
  - Costanti patchabili: `POLL_INTERVAL`, `DOWNLOAD_TIMEOUT`.
  - Stato job: chiavi `status, processed, total, downloaded, needs_review, not_found, failed, playlist_id, items, error, started_at, finished_at`. Outcome per item in `items[].outcome` ∈ `{"downloaded","needs_review","not_found","failed"}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_soulseek_download_job.py
import math
import struct
import wave

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.integrations.slskd import SlskdFile
from app.models import Track
from app.services import soulseek_download_job as job


def _write_wav(path, *, freq=440, secs=0.2, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * secs))
        ))


class _FakeClient:
    """slskd fake: ritorna un file lossless e un transfer subito completo."""

    def __init__(self, filename):
        self._filename = filename
        self.enqueued = []

    def search(self, artist, title, **kw):
        return [SlskdFile(username="bob", filename=self._filename, size=10,
                          bitrate=None, length=None, has_free_slot=True, queue_length=0)]

    def enqueue_download(self, file):
        self.enqueued.append(file)

    def transfer_state(self, username, filename):
        return {"filename": filename, "state": "Completed, Succeeded"}


@pytest.fixture()
def patch_job(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    # download dir con il file gia' presente (simula slskd che ha scaricato)
    download_dir = tmp_path / "dl"
    download_dir.mkdir()
    _write_wav(download_dir / "Da Funk.flac")  # basename combacia col candidato
    monkeypatch.setattr(job, "SessionLocal", TestSession)
    monkeypatch.setattr(job.settings, "slskd_download_dir", str(download_dir))
    monkeypatch.setattr(job, "POLL_INTERVAL", 0.0)
    monkeypatch.setattr(job, "DOWNLOAD_TIMEOUT", 1.0)
    fake = _FakeClient("bob\\Da Funk.flac")
    monkeypatch.setattr(job, "get_slskd_client", lambda: fake)
    # reset stato globale
    job._state.update(status="idle", processed=0, total=0)
    return TestSession, fake


def test_track_job_downloads_and_links(patch_job):
    TestSession, fake = patch_job
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s1", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    chosen = fake.search("Daft Punk", "Da Funk")[0]
    job._run([(track_id, chosen)], None)  # esegue in-thread (sincrono) per il test

    st = job.job_state()
    assert st["status"] == "done"
    assert st["downloaded"] == 1
    db = TestSession()
    t2 = db.get(Track, track_id)
    assert t2.has_local_file is True
    assert t2.local_format == "flac"
    db.close()


def test_playlist_auto_pick_uses_search(patch_job):
    TestSession, fake = patch_job
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s2", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    job._run([(track_id, None)], playlist_id=99)  # None -> auto-pick via search
    st = job.job_state()
    assert st["downloaded"] == 1
    assert len(fake.enqueued) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_download_job.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.soulseek_download_job'`.

- [ ] **Step 3: Write the job**

```python
# backend/app/services/soulseek_download_job.py
"""Job in background per scaricare tracce via slskd e collegarle alle Track.

Mono-utente, uno-job-per-volta (come local_import_job): threading + stato in
memoria + lock. Per ogni traccia: ricerca -> selezione -> enqueue -> polling
del transfer -> link del file alla Track. Un errore su una traccia non ferma
il job.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.db import SessionLocal
from app.integrations.local_files import read_audio_quality
from app.integrations.slskd import (
    SlskdFile, classify_transfer_state, get_slskd_client,
)
from app.repositories import get_track, tracks_without_local_file
from app.services.acquisition import attach_local_file
from app.services.soulseek_select import best_for_auto

POLL_INTERVAL = 2.0
DOWNLOAD_TIMEOUT = 180.0

_lock = threading.Lock()
_state: dict = {
    "status": "idle",
    "processed": 0,
    "total": 0,
    "downloaded": 0,
    "needs_review": 0,
    "not_found": 0,
    "failed": 0,
    "playlist_id": None,
    "items": [],
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def job_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _resolve_local_path(download_dir: str, filename: str) -> str | None:
    base = Path(filename.replace("\\", "/")).name
    root = Path(download_dir)
    if not root.exists():
        return None
    for p in root.rglob(base):
        if p.is_file():
            return str(p.resolve())
    return None


def _wait_for_download(client, file: SlskdFile) -> str:
    waited = 0.0
    while waited < DOWNLOAD_TIMEOUT:
        state = client.transfer_state(file.username, file.filename)
        cls = classify_transfer_state((state or {}).get("state", ""))
        if cls in ("completed", "failed"):
            return cls
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    return "failed"


def _process_item(db, client, download_dir, track, chosen: SlskdFile | None) -> str:
    if chosen is None:
        files = client.search(track.artist or "", track.title or "")
        best = best_for_auto(files, artist=track.artist or "", title=track.title or "")
        if best is None:
            return "needs_review" if files else "not_found"
        chosen = best.file
    client.enqueue_download(chosen)
    if _wait_for_download(client, chosen) != "completed":
        return "failed"
    path = _resolve_local_path(download_dir, chosen.filename)
    if not path:
        return "failed"
    quality = read_audio_quality(path)
    attach_local_file(db, track, path=path, fmt=quality["format"],
                      bitrate=quality["bitrate"])
    return "downloaded"


def _run(items: list[tuple[int, SlskdFile | None]], playlist_id: int | None) -> None:
    db = SessionLocal()
    try:
        client = get_slskd_client()
        download_dir = settings.slskd_download_dir
        _state.update(total=len(items), playlist_id=playlist_id)
        for i, (track_id, chosen) in enumerate(items, start=1):
            track = get_track(db, track_id)
            if track is None:
                outcome = "failed"
            else:
                try:
                    outcome = _process_item(db, client, download_dir, track, chosen)
                except Exception:  # noqa: BLE001 — un fallimento non ferma il job
                    outcome = "failed"
            _state[outcome] = _state.get(outcome, 0) + 1
            _state["processed"] = i
            _state["items"].append({
                "track_id": track_id,
                "artist": getattr(track, "artist", None),
                "title": getattr(track, "title", None),
                "outcome": outcome,
            })
        _state.update(status="done")
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


def _start(items, playlist_id) -> dict:
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(status="running", processed=0, total=len(items),
                      downloaded=0, needs_review=0, not_found=0, failed=0,
                      playlist_id=playlist_id, items=[], error=None,
                      started_at=datetime.now(timezone.utc).isoformat(),
                      finished_at=None)
    threading.Thread(target=_run, args=(items, playlist_id), daemon=True).start()
    return job_state()


def start_playlist_job(playlist_id: int) -> dict:
    db = SessionLocal()
    try:
        items = [(t.id, None) for t in tracks_without_local_file(db, playlist_id)]
    finally:
        db.close()
    return _start(items, playlist_id)


def start_track_job(track_id: int, chosen: SlskdFile) -> dict:
    return _start([(track_id, chosen)], None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_download_job.py -v`
Expected: PASS. (I test chiamano `job._run(...)` direttamente per esecuzione sincrona deterministica; `_start`/threading restano coperti indirettamente.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/soulseek_download_job.py backend/tests/test_soulseek_download_job.py
git commit -m "feat(soulseek): job di download (search->enqueue->poll->link)"
```

---

### Task 8: Router downloads + registrazione

**Files:**
- Create: `backend/app/routers/downloads.py`
- Modify: `backend/app/main.py` (import + `include_router`)
- Test: `backend/tests/test_downloads_router.py`

**Interfaces:**
- Consumes: `slskd.{slskd_configured, get_slskd_client, SlskdError, SlskdFile}`, `soulseek_select.rank_candidates`, `soulseek_download_job` (as `job`), `repositories.get_track`, `db.SessionLocal`.
- Produces endpoint:
  - `GET /api/downloads/status` -> `{available, ...job_state}`
  - `POST /api/downloads/candidates` body `{artist,title}` -> `list[CandidateOut]`
  - `POST /api/downloads/playlist/{playlist_id}` (202) -> job_state
  - `POST /api/downloads/track` body `{track_id, candidate}` (202) -> job_state
  - `CandidateOut(username, filename, size, bitrate, length, format, name_score, quality_tier, confidence)`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_downloads_router.py
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import downloads as downloads_router

client = TestClient(app)


def test_status_reports_unavailable_when_not_configured(monkeypatch):
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.get("/api/downloads/status")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_candidates_409_when_not_configured(monkeypatch):
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.post("/api/downloads/candidates", json={"artist": "A", "title": "B"})
    assert r.status_code == 409


def test_candidates_returns_ranked(monkeypatch):
    from app.integrations.slskd import SlskdFile

    class _C:
        def search(self, a, t, **k):
            return [SlskdFile(username="u", filename="A - B.flac", size=1, bitrate=None,
                              length=None, has_free_slot=True, queue_length=0)]

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _C())
    r = client.post("/api/downloads/candidates", json={"artist": "A", "title": "B"})
    assert r.status_code == 200
    body = r.json()
    assert body and body[0]["format"] == "flac"
    assert "confidence" in body[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_downloads_router.py -v`
Expected: FAIL (`ModuleNotFoundError` su `app.routers.downloads` / route 404).

- [ ] **Step 3: Write the router**

```python
# backend/app/routers/downloads.py
"""HTTP per l'acquisizione file via slskd. Nessuna logica di business qui."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import SessionLocal
from app.integrations.slskd import (
    SlskdError, SlskdFile, get_slskd_client, slskd_configured,
)
from app.repositories import get_track
from app.services import soulseek_download_job as job
from app.services.soulseek_select import rank_candidates

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


class CandidateOut(BaseModel):
    username: str
    filename: str
    size: int | None = None
    bitrate: int | None = None
    length: int | None = None
    format: str | None = None
    name_score: float = 0.0
    quality_tier: int = 0
    confidence: float = 0.0


class CandidatesIn(BaseModel):
    artist: str
    title: str


class TrackDownloadIn(BaseModel):
    track_id: int
    candidate: CandidateOut


def _candidate_out(c) -> CandidateOut:
    return CandidateOut(
        username=c.file.username, filename=c.file.filename, size=c.file.size,
        bitrate=c.file.bitrate, length=c.file.length, format=c.file.extension or None,
        name_score=c.name_score, quality_tier=c.quality_tier, confidence=c.confidence,
    )


@router.get("/status")
def status():
    return {"available": slskd_configured(), **job.job_state()}


@router.post("/candidates", response_model=list[CandidateOut])
def candidates(req: CandidatesIn):
    if not slskd_configured():
        raise HTTPException(409, "slskd non configurato (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    try:
        files = get_slskd_client().search(req.artist, req.title)
    except SlskdError as exc:
        raise HTTPException(502, str(exc)) from exc
    ranked = rank_candidates(files, artist=req.artist, title=req.title)
    return [_candidate_out(c) for c in ranked]


@router.post("/playlist/{playlist_id}", status_code=202)
def download_playlist(playlist_id: int):
    if not slskd_configured():
        raise HTTPException(409, "slskd non configurato.")
    if job.is_running():
        raise HTTPException(409, "Un download e' gia' in corso.")
    return job.start_playlist_job(playlist_id)


@router.post("/track", status_code=202)
def download_track(req: TrackDownloadIn):
    if not slskd_configured():
        raise HTTPException(409, "slskd non configurato.")
    if job.is_running():
        raise HTTPException(409, "Un download e' gia' in corso.")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise HTTPException(404, "Traccia non trovata.")
    finally:
        db.close()
    c = req.candidate
    file = SlskdFile(username=c.username, filename=c.filename, size=c.size,
                     bitrate=c.bitrate, length=c.length, has_free_slot=True,
                     queue_length=None)
    return job.start_track_job(req.track_id, file)
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`: aggiungere `downloads` alla riga di import `from app.routers import (...)` e, accanto agli altri `app.include_router(...)`:

```python
app.include_router(downloads.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_downloads_router.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: tutti verdi.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/downloads.py backend/app/main.py backend/tests/test_downloads_router.py
git commit -m "feat(downloads): router candidates/playlist/track/status"
```

---

### Task 9: Frontend — client API + sezione Download + nav

**Files:**
- Modify: `frontend/lib/api.ts` (tipi + funzioni)
- Create: `frontend/app/downloads/page.tsx`
- Modify: `frontend/components/index-nav.tsx` (voce nav)

**Interfaces:**
- Consumes (backend): `GET /api/downloads/status`, `POST /api/downloads/candidates`, `POST /api/downloads/playlist/{id}`, `POST /api/downloads/track`, `GET /api/playlists`.
- Produces (frontend): `downloadStatus()`, `downloadCandidates()`, `startPlaylistDownload()`, `downloadTrack()`, tipi `DownloadCandidate`, `DownloadStatus`.

**Pre-req:** leggere `frontend/CLAUDE.md` (Next.js 16). Pagina interattiva -> `"use client"`.

- [ ] **Step 1: Add API client functions**

In `frontend/lib/api.ts` (in fondo, accanto alle altre export):

```ts
export type DownloadCandidate = {
  username: string;
  filename: string;
  size: number | null;
  bitrate: number | null;
  length: number | null;
  format: string | null;
  name_score: number;
  quality_tier: number;
  confidence: number;
};

export type DownloadItem = {
  track_id: number;
  artist: string | null;
  title: string | null;
  outcome: "downloaded" | "needs_review" | "not_found" | "failed";
};

export type DownloadStatus = {
  available: boolean;
  status: "idle" | "running" | "done" | "error";
  processed: number;
  total: number;
  downloaded: number;
  needs_review: number;
  not_found: number;
  failed: number;
  playlist_id: number | null;
  items: DownloadItem[];
  error: string | null;
};

export function downloadStatus() {
  return apiGet<DownloadStatus>("/api/downloads/status");
}

export function downloadCandidates(artist: string, title: string) {
  return apiPost<DownloadCandidate[]>("/api/downloads/candidates", { artist, title });
}

export function startPlaylistDownload(playlistId: number) {
  return apiPost<DownloadStatus>(`/api/downloads/playlist/${playlistId}`);
}

export function downloadTrack(trackId: number, candidate: DownloadCandidate) {
  return apiPost<DownloadStatus>("/api/downloads/track", { track_id: trackId, candidate });
}
```

- [ ] **Step 2: Add the nav entry**

In `frontend/components/index-nav.tsx`, nell'array `NAV`, dopo la voce `Set`:

```tsx
  { href: "/downloads", label: "Download" },
```

- [ ] **Step 3: Create the Download page**

```tsx
// frontend/app/downloads/page.tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download as DownloadIcon } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, Progress, Select } from "@/components/ui";
import {
  apiGet,
  downloadStatus,
  startPlaylistDownload,
  type DownloadStatus,
} from "@/lib/api";

type PlaylistRef = { id: number; name: string };

const OUTCOME_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  downloaded: "success",
  needs_review: "warning",
  not_found: "neutral",
  failed: "danger",
};

export default function DownloadsPage() {
  const [playlists, setPlaylists] = useState<PlaylistRef[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [status, setStatus] = useState<DownloadStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const poll = useCallback(async () => {
    try {
      const s = await downloadStatus();
      if (alive.current) setStatus(s);
    } catch {
      /* backend offline: ignora */
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    apiGet<PlaylistRef[]>("/api/playlists")
      .then((p) => alive.current && setPlaylists(p))
      .catch(() => undefined);
    poll();
    const id = setInterval(poll, 2000);
    return () => {
      alive.current = false;
      clearInterval(id);
    };
  }, [poll]);

  const start = async () => {
    if (!selected) return;
    setError(null);
    try {
      setStatus(await startPlaylistDownload(Number(selected)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const available = status?.available ?? true;
  const running = status?.status === "running";
  const pct = status && status.total > 0 ? (status.processed / status.total) * 100 : 0;

  return (
    <PageLayout title="Download" meta={status?.total || undefined}>
      {!available && (
        <Alert tone="info">
          slskd non e&apos; configurato. Imposta SLSKD_URL, SLSKD_API_KEY e
          SLSKD_DOWNLOAD_DIR in backend/.env per abilitare i download.
        </Alert>
      )}

      <Card className="flex items-center gap-3 p-3">
        <Select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={!available || running}
        >
          <option value="">Scegli una playlist…</option>
          {playlists.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        <Button onClick={start} disabled={!available || running || !selected}>
          <DownloadIcon size={14} /> Scarica playlist
        </Button>
      </Card>

      {error && <Alert tone="danger">⚠ {error}</Alert>}

      {status && status.total > 0 && (
        <Card className="mt-3 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs text-faint">
            <span>{status.processed}/{status.total}</span>
            <Badge tone="success">{status.downloaded} scaricate</Badge>
            <Badge tone="warning">{status.needs_review} da rivedere</Badge>
            <Badge tone="neutral">{status.not_found} non trovate</Badge>
            <Badge tone="danger">{status.failed} fallite</Badge>
          </div>
          <Progress value={pct} />
          <ul className="mt-3 divide-y divide-border text-sm">
            {status.items.map((it) => (
              <li key={it.track_id} className="flex items-center justify-between py-1.5">
                <span className="truncate">{it.artist} — {it.title}</span>
                <Badge tone={OUTCOME_TONE[it.outcome] ?? "neutral"}>{it.outcome}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {status && status.total === 0 && available && (
        <EmptyState icon={<DownloadIcon size={28} />} title="Nessun download">
          Scegli una playlist e avvia il download.
        </EmptyState>
      )}
    </PageLayout>
  );
}
```

> Nota: verificare i nomi esatti dei componenti importati da `@/components/ui` (Button, Card, Badge, Progress, Select, Alert, EmptyState) e la firma di `PageLayout` contro i file reali; il design system e' in `frontend/components/ui.tsx` e `frontend/components/page-layout.tsx`. Adattare prop se necessario (es. `Select` potrebbe accettare `value`/`onChange` diversi).

- [ ] **Step 4: Verify lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore di lint; build completata. Se la cache CSS dev fa scherzi, `rm -rf .next` (vedi memoria progetto).

- [ ] **Step 5: Verify in the running app**

Avviare backend (`uvicorn app.main:app --reload --port 8000`) e frontend (`npm run dev`), aprire `/downloads`. Con slskd non configurato deve comparire l'Alert info e i controlli disabilitati. Catturare conferma (screenshot o nota).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api.ts frontend/app/downloads/page.tsx frontend/components/index-nav.tsx
git commit -m "feat(frontend): sezione Download per-playlist + voce nav"
```

---

### Task 10: Frontend — bottone Download in Discovery

**Files:**
- Modify: `frontend/app/discovery/page.tsx` (componente `LeadRow`)

**Interfaces:**
- Consumes: `downloadCandidates()`, `downloadTrack()`, `discoveryAddLead()` (esistente), tipo `DownloadCandidate`.
- Flusso: ricerca candidati -> mini-selettore (Modal) -> aggiungi il lead alla libreria (`discoveryAddLead`) -> `downloadTrack(trackId, candidate)`.

- [ ] **Step 1: Confirm addLead returns the track id**

Leggere in `frontend/lib/api.ts` la funzione `discoveryAddLead` e l'endpoint backend corrispondente (`backend/app/routers/discovery.py`). Confermare che la risposta includa l&apos;`id` della `Track` creata. Se NON lo include, aggiungere `id` (o l&apos;intero `TrackOut`) alla risposta dell&apos;endpoint add-lead e al tipo di ritorno di `discoveryAddLead`. Questo e&apos; l&apos;unico punto d&apos;integrazione da verificare; il resto e&apos; codice concreto sotto.

- [ ] **Step 2: Add the Download button + mini-selector to LeadRow**

In `frontend/app/discovery/page.tsx`, dentro il componente `LeadRow`, aggiungere lo stato e gli handler in cima al componente:

```tsx
  const [dlOpen, setDlOpen] = useState(false);
  const [dlLoading, setDlLoading] = useState(false);
  const [dlCands, setDlCands] = useState<DownloadCandidate[]>([]);
  const [dlError, setDlError] = useState<string | null>(null);
  const [dlDone, setDlDone] = useState(false);

  const openDownload = async () => {
    setDlOpen(true);
    setDlLoading(true);
    setDlError(null);
    try {
      setDlCands(await downloadCandidates(l.artist, l.title));
    } catch (e) {
      setDlError(e instanceof Error ? e.message : String(e));
    } finally {
      setDlLoading(false);
    }
  };

  const pick = async (cand: DownloadCandidate) => {
    setDlLoading(true);
    setDlError(null);
    try {
      const track = await discoveryAddLead(l); // ritorna { id, ... }
      await downloadTrack(track.id, cand);
      setDlDone(true);
      setDlOpen(false);
    } catch (e) {
      setDlError(e instanceof Error ? e.message : String(e));
    } finally {
      setDlLoading(false);
    }
  };
```

Nel blocco azioni (`<div className="flex shrink-0 items-center gap-1.5">`), accanto al bottone "Salva", aggiungere:

```tsx
        <Button size="sm" variant="outline" onClick={openDownload} disabled={dlDone}>
          {dlDone ? <><Check size={14} /> Scaricato</> : <><Download size={14} /> Download</>}
        </Button>
```

E, in fondo al return del componente (dentro la `<Card>` o subito dopo, come fa il pattern Modal del progetto), il mini-selettore:

```tsx
      <Modal open={dlOpen} onClose={() => setDlOpen(false)} title={`Download — ${l.artist} ${l.title}`}>
        {dlError && <Alert tone="danger">⚠ {dlError}</Alert>}
        {dlLoading && <p className="text-sm text-faint">Ricerca su Soulseek…</p>}
        {!dlLoading && dlCands.length === 0 && (
          <p className="text-sm text-faint">Nessun candidato trovato su Soulseek.</p>
        )}
        <ul className="divide-y divide-border">
          {dlCands.map((c, i) => (
            <li key={`${c.username}-${i}`} className="flex items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="truncate text-sm">{c.filename.split(/[\\/]/).pop()}</div>
                <div className="text-xs text-faint">
                  {c.format?.toUpperCase()} {c.bitrate ? `· ${c.bitrate}kbps` : ""} · conf {Math.round(c.confidence * 100)}%
                </div>
              </div>
              <Button size="sm" variant="outline" onClick={() => pick(c)} disabled={dlLoading}>
                <Download size={13} /> Scarica
              </Button>
            </li>
          ))}
        </ul>
      </Modal>
```

Aggiornare gli import in cima a `discovery/page.tsx`:

```tsx
import { Check, Download } from "lucide-react";
import { Modal } from "@/components/ui";
import { downloadCandidates, downloadTrack, type DownloadCandidate } from "@/lib/api";
```

> Se `Check`/`Download`/`Modal`/`Alert`/`Button` sono gia&apos; importati, non duplicare. Confermare `Modal` esista in `components/ui.tsx` (l&apos;esplorazione lo ha riportato).

- [ ] **Step 3: Verify lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 4: Verify in the running app**

Aprire `/discovery`, eseguire un dig, cliccare "Download" su un lead: deve aprirsi il modal. Con slskd non configurato la chiamata candidates restituisce 409 -> il modal mostra l&apos;errore (comportamento atteso). Con slskd configurato, mostra i candidati e permette il download.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/discovery/page.tsx
git commit -m "feat(frontend): bottone Download + mini-selettore in Discovery"
```

---

### Task 11: Documentazione

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/API.md`
- Modify: `docs/ROADMAP.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: ARCHITECTURE.md**

- Nei "Principi", aggiornare la riga "non conserva file audio": dichiarare l&apos;eccezione **acquisizione persistente via Soulseek/slskd**, collegata a una `Track`, distinta dal download temporaneo Shazam.
- Aggiungere un blocco "Flusso" per l&apos;acquisizione:

```text
Track in libreria (identita' streaming)
  -> SlskdClient.search (slskd REST)
  -> selezione deterministica (qualita' + match nome + disponibilita')
  -> auto-pick (blocco) | mini-selettore (Discovery)
  -> slskd enqueue + polling transfer
  -> attach_local_file: has_local_file + local_path/format/bitrate
```

- In "Integrazioni", aggiungere riga: `| slskd (Soulseek) | attiva se configurato | download via REST API; SLSKD_URL/API_KEY/DOWNLOAD_DIR |`.
- In "Modello dati", su `Track`, aggiungere i campi `has_local_file`, `local_path`, `local_format`, `local_bitrate`.

- [ ] **Step 2: API.md**

Documentare gli endpoint nuovi: `GET /api/downloads/status`, `POST /api/downloads/candidates`, `POST /api/downloads/playlist/{id}`, `POST /api/downloads/track` (request/response sintetici, coerenti con gli altri).

- [ ] **Step 3: ROADMAP.md**

In "Stato completato" aggiungere una voce sintetica sull&apos;acquisizione Soulseek. Nel backlog tecnico, aggiungere la fast-follow **"Vista Tracce senza file"** (gap di possesso) come prossimo passo opzionale.

- [ ] **Step 4: README.md**

Aggiungere una riga al workflow su acquisizione via Soulseek e una nota di **responsabilita&apos; d&apos;uso** (strumento personale/self-hosted; l&apos;acquisizione di materiale e&apos; responsabilita&apos; dell&apos;utente). Menzionare il requisito slskd.

- [ ] **Step 5: CLAUDE.md**

Aggiornare la descrizione del progetto: oltre a "scarica audio solo in modo temporaneo per Shazam", aggiungere che **acquisisce file via Soulseek/slskd collegandoli alle tracce** (eccezione esplicita al "no store"; resta il "no play").

- [ ] **Step 6: Commit**

```bash
git add docs/ARCHITECTURE.md docs/API.md docs/ROADMAP.md README.md CLAUDE.md
git commit -m "docs: acquisizione Soulseek (slskd) — architettura, API, roadmap"
```

---

## Self-Review

**Spec coverage:**
- slskd integration (spec §"Integrazione slskd") -> Task 1-3. ✓
- Acquisizione + ownership, campi separati (spec §"Backend/Modello dati") -> Task 6. ✓
- Selezione ibrida + preferenza qualita' (spec §"Motore di selezione") -> Task 4 (deterministico), Task 7 (auto-pick blocco), Task 10 (mini-selettore Discovery). ✓
- Job async con polling (spec §"Job di download") -> Task 7 + status endpoint Task 8 + polling UI Task 9. ✓
- Sezione Download per-playlist (spec §UI) -> Task 9. ✓
- Bottone Download in Discovery (spec §UI) -> Task 10. ✓
- Degradazione pulita se non configurato (spec §"Integrazione slskd") -> Task 8 (409) + Task 9 (Alert). ✓
- Non-goal: niente AI nel percorso (deterministico) ✓; niente condivisione (documentato Task 11) ✓; niente re-import duplicato (si collega alla Track esistente, Task 6/7) ✓.
- Vista "Tracce senza file": fast-follow opzionale -> esplicitamente FUORI dal piano, citata come backlog in Task 11 §ROADMAP. ✓ (coerente con la spec).
- Doc da aggiornare (spec §"Documentazione da aggiornare") -> Task 11. ✓

**Placeholder scan:** nessun "TBD/TODO"; le poche note di verifica (signature `discoveryAddLead`, nomi prop UI, endpoint slskd) sono punti d&apos;integrazione concreti con istruzioni precise, non lavoro vago. Codice completo in ogni step.

**Type consistency:** `SlskdFile` (campi e `.extension`) coerente tra Task 2/3/4/7/8. `ScoredCandidate`/`best_for_auto` coerenti tra Task 4/7. `attach_local_file(db, track, *, path, fmt, bitrate)` coerente tra Task 6/7. `job._run(items, playlist_id)` con `items: list[tuple[int, SlskdFile|None]]` coerente tra Task 7 (test e impl) e i `start_*` job. Chiavi di `job_state()` coerenti tra Task 7/8 e i tipi frontend `DownloadStatus` (Task 9). `classify_transfer_state` coerente tra Task 3/7.

## Punti aperti (confermare in implementazione, non bloccanti)

- Endpoint/forme slskd: confermare contro Swagger (Pre-flight). L&apos;unico file impattato e&apos; `integrations/slskd.py`.
- Layout della download dir di slskd: `_resolve_local_path` cerca per basename ricorsivamente (best-effort). Se slskd espone il path locale nel transfer, preferirlo.
- `discoveryAddLead` deve restituire l&apos;id della Track (Task 10 Step 1).
- Nomi/prop esatti dei componenti `@/components/ui` e `PageLayout` (Task 9/10): allineare ai file reali.
