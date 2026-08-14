# SoundCloud download via yt-dlp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere nel dettaglio traccia (`/tracks/[id]`), solo per le tracce SoundCloud, un bottone "Scarica da SoundCloud" che scarica l'audio via yt-dlp, lo estrae in MP3 nella cartella di download condivisa e lo collega alla `Track` come file posseduto.

**Architecture:** Un nuovo helper `integrations/soundcloud_audio.py` scarica+estrae l'MP3 (unico punto che tocca yt-dlp/audio). Un nuovo worker `_run_soundcloud` in `soulseek_download_job.py` riusa lo stesso stato/lock/barra del download Soulseek (un solo download alla volta) e collega il file con `attach_local_file`. Un nuovo endpoint `POST /api/downloads/track/soundcloud` fa da gate. Il frontend aggiunge un bottone gemello a "Cerca su Soulseek".

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy + Pydantic (backend), yt-dlp + ffmpeg (download/estrazione), Next.js 16 + React + Tailwind (frontend), pytest (test backend).

## Global Constraints

- yt-dlp e ffmpeg sono già dipendenze del backend (`backend/requirements.txt`, `docs/DEPENDENCIES.md`). Non aggiungere dipendenze nuove.
- Cartella di download: `settings.slskd_download_dir` (`SLSKD_DOWNLOAD_DIR` nel `.env`). **Nessuna nuova variabile d'ambiente.**
- Formato di output: **MP3**, estratto via postprocessor `FFmpegExtractAudio`, qualità VBR ~V0 (`preferredquality="0"`). Niente upscaling forzato.
- Linking del possesso: **solo** via `attach_local_file(db, track, *, path, fmt, bitrate)` — identico a Soulseek. Non duplicare la logica di possesso.
- SSRF guard: validare sempre l'URL con l'allowlist host di `integrations/soundcloud.py` (solo `soundcloud.com` e sottodomini; niente `file://`/schemi locali) prima di passarlo a yt-dlp.
- Un solo download alla volta: il nuovo job condivide `_state`/`_lock` con il download Soulseek.
- I tag del file NON vengono toccati (compito di Sortory).
- Commit message: convenzioni del repo (`feat(...)`, `test(...)`, `docs(...)`). **Mai** aggiungere `Co-Authored-By`.
- Branch di lavoro: `feat/soundcloud-download-ytdlp` (già creato, lo spec è già committato lì).
- Comandi test backend: da `backend/` con venv attivo → `python -m pytest tests/<file> -v`.

---

### Task 1: Validatore URL SoundCloud condiviso

Espone un helper pubblico per lo SSRF guard, così `soundcloud_audio` non deve importare un simbolo privato tra moduli.

**Files:**
- Modify: `backend/app/integrations/soundcloud.py` (aggiunta funzione, dopo `_validate_url`, ~riga 53)
- Test: `backend/tests/test_soundcloud_validate_url.py` (nuovo)

**Interfaces:**
- Consumes: `_validate_url(url) -> str` e `SoundCloudInvalidUrl` (già in `soundcloud.py`).
- Produces: `validate_soundcloud_url(url: str) -> str` (ritorna l'URL se valido; solleva `SoundCloudInvalidUrl` su input ostile).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_soundcloud_validate_url.py`:
```python
import pytest

from app.integrations.soundcloud import SoundCloudInvalidUrl, validate_soundcloud_url


def test_validate_accepts_soundcloud_url():
    url = "https://soundcloud.com/artist/track"
    assert validate_soundcloud_url(url) == url


def test_validate_rejects_file_scheme():
    with pytest.raises(SoundCloudInvalidUrl):
        validate_soundcloud_url("file:///etc/passwd")


def test_validate_rejects_foreign_host():
    with pytest.raises(SoundCloudInvalidUrl):
        validate_soundcloud_url("https://evil.example.com/track")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_soundcloud_validate_url.py -v`
Expected: FAIL con `ImportError: cannot import name 'validate_soundcloud_url'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/integrations/soundcloud.py`, subito dopo `_validate_url` (dopo la riga `return url`, ~riga 53), aggiungi:
```python
def validate_soundcloud_url(url: str) -> str:
    """Valida un URL SoundCloud (allowlist host, solo http(s)) e lo ritorna.

    Wrapper pubblico di `_validate_url`: stesso SSRF guard usato anche da
    `soundcloud_audio`, senza importare un simbolo privato tra moduli.
    """
    return _validate_url(url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_soundcloud_validate_url.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/soundcloud.py backend/tests/test_soundcloud_validate_url.py
git commit -m "feat(soundcloud): validate_soundcloud_url pubblico per lo SSRF guard condiviso"
```

---

### Task 2: Helper di download+estrazione MP3

L'unità isolata che scarica l'audio SoundCloud via yt-dlp e lo estrae in MP3. Unico punto che tocca yt-dlp/audio per questa feature.

**Files:**
- Create: `backend/app/integrations/soundcloud_audio.py`
- Test: `backend/tests/test_soundcloud_audio.py` (nuovo)

**Interfaces:**
- Consumes: `validate_soundcloud_url(url) -> str` (Task 1), `SoundCloudInvalidUrl`.
- Produces:
  - `download_track_audio(url: str, dest_dir: str) -> str` (ritorna il path assoluto dell'MP3 scaricato).
  - `SoundCloudAudioError(RuntimeError)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_soundcloud_audio.py`:
```python
import pytest

from app.integrations.soundcloud import SoundCloudInvalidUrl
from app.integrations.soundcloud_audio import (
    SoundCloudAudioError, download_track_audio,
)


class _FakeYDL:
    """YoutubeDL finto: registra le opzioni e simula un download riuscito."""
    last_opts = None

    def __init__(self, opts):
        _FakeYDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download):
        assert download is True
        return {"title": "Song", "requested_downloads": [{"filepath": "/dl/Song.mp3"}]}

    def prepare_filename(self, info):
        return "/dl/Song.webm"


def test_download_returns_mp3_path(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", _FakeYDL)
    assert download_track_audio("https://soundcloud.com/a/b", "/dl") == "/dl/Song.mp3"


def test_download_sets_bestaudio_and_mp3_postprocessor(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", _FakeYDL)
    download_track_audio("https://soundcloud.com/a/b", "/dl")
    opts = _FakeYDL.last_opts
    assert opts["format"] == "bestaudio/best"
    assert opts["postprocessors"][0]["key"] == "FFmpegExtractAudio"
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"


def test_download_falls_back_to_prepared_name(monkeypatch):
    class _NoRequested(_FakeYDL):
        def extract_info(self, url, download):
            return {"title": "Song"}  # nessun requested_downloads

    monkeypatch.setattr("yt_dlp.YoutubeDL", _NoRequested)
    assert download_track_audio("https://soundcloud.com/a/b", "/dl") == "/dl/Song.mp3"


def test_download_rejects_empty_dest_dir():
    with pytest.raises(SoundCloudAudioError):
        download_track_audio("https://soundcloud.com/a/b", "")


def test_download_rejects_hostile_url():
    with pytest.raises(SoundCloudInvalidUrl):
        download_track_audio("file:///etc/passwd", "/dl")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_soundcloud_audio.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.integrations.soundcloud_audio'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/integrations/soundcloud_audio.py`:
```python
"""Download dell'audio di una singola traccia SoundCloud via yt-dlp, estratto in MP3.

Eccezione esplicita a "non conserva audio di terzi", come Soulseek: scarica un
file e lo collega alla Track come posseduto. Solo la singola traccia dal dettaglio,
mai batch. Scrive nella cartella di download condivisa (SLSKD_DOWNLOAD_DIR); i tag
NON vengono toccati (compito di Sortory).
"""
from __future__ import annotations

import os

from app.integrations.soundcloud import validate_soundcloud_url

_SOCKET_TIMEOUT = 30


class SoundCloudAudioError(RuntimeError):
    """Download/estrazione audio SoundCloud fallito (rete, yt-dlp, ffmpeg...)."""


def download_track_audio(url: str, dest_dir: str) -> str:
    """Scarica l'audio di `url` in `dest_dir`, lo estrae in MP3 e ritorna il path.

    SSRF guard: valida l'host (solo soundcloud.com). Solleva SoundCloudAudioError
    se la cartella manca o se yt-dlp/ffmpeg falliscono; SoundCloudInvalidUrl su
    URL ostile (delega a validate_soundcloud_url).
    """
    validate_soundcloud_url(url)
    if not dest_dir:
        raise SoundCloudAudioError("Cartella di download non configurata (SLSKD_DOWNLOAD_DIR).")

    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "socket_timeout": _SOCKET_TIMEOUT,
        "outtmpl": os.path.join(dest_dir, "%(title)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "0",
        }],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            pre_pp_name = ydl.prepare_filename(info)
    except Exception as exc:  # noqa: BLE001 — yt-dlp/ffmpeg sollevano tipi eterogenei
        raise SoundCloudAudioError(
            f"Download SoundCloud fallito ({exc}). Se l'URL è corretto, prova ad aggiornare yt-dlp."
        ) from exc
    return _final_mp3_path(info, pre_pp_name)


def _final_mp3_path(info: dict, pre_pp_name: str) -> str:
    """Path del file dopo il postprocessor MP3.

    yt-dlp lo espone in `requested_downloads[*].filepath`; se manca si ripiega sul
    nome pre-postprocessor con estensione .mp3.
    """
    downloads = info.get("requested_downloads") or []
    if downloads and downloads[0].get("filepath"):
        return downloads[0]["filepath"]
    return os.path.splitext(pre_pp_name)[0] + ".mp3"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_soundcloud_audio.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/soundcloud_audio.py backend/tests/test_soundcloud_audio.py
git commit -m "feat(soundcloud): download_track_audio via yt-dlp con estrazione MP3"
```

---

### Task 3: Worker del job condiviso

Aggiunge al job di download Soulseek un worker SoundCloud che riusa stato/lock/barra e collega il file con `attach_local_file`. Estrae anche `_reset_running_state` per non duplicare il reset di stato.

**Files:**
- Modify: `backend/app/services/soulseek_download_job.py` (import in testa; `_reset_running_state` + refactor `_start` ~riga 307; `start_soundcloud_track_job` + `_run_soundcloud` in fondo)
- Test: `backend/tests/test_soundcloud_download_job.py` (nuovo)

**Interfaces:**
- Consumes: `download_track_audio(url, dest_dir) -> str` e `SoundCloudAudioError` (Task 2); `get_track`, `read_audio_quality`, `attach_local_file`, `settings`, `SessionLocal`, `_track_label`, `_state`, `_lock`, `job_state` (già nel modulo).
- Produces:
  - `start_soundcloud_track_job(track_id: int) -> dict` (avvia il worker, ritorna `job_state()`).
  - `_run_soundcloud(track_id: int) -> None` (worker; scrive `_state` e `track.last_download_outcome/reason/path`).
  - `_reset_running_state(total: int, playlist_id: int | None) -> None`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_soundcloud_download_job.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Track
from app.services import soulseek_download_job as job
from app.integrations.soundcloud_audio import SoundCloudAudioError


def _factory_with_track():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    factory = sessionmaker(bind=e, expire_on_commit=False)
    db = factory()
    t = Track(source_type="soundcloud", platform="soundcloud",
              url="https://soundcloud.com/a/b", title="B", artist="A")
    db.add(t)
    db.commit()
    return factory, t.id


def test_run_soundcloud_success(monkeypatch):
    factory, track_id = _factory_with_track()
    monkeypatch.setattr(job, "SessionLocal", factory)
    monkeypatch.setattr(job, "download_track_audio", lambda url, d: "/dl/A - B.mp3")
    monkeypatch.setattr(job, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 245})
    linked = {}

    def _fake_attach(db, track, *, path, fmt, bitrate):
        track.has_local_file = True
        linked.update(path=path, fmt=fmt, bitrate=bitrate)

    monkeypatch.setattr(job, "attach_local_file", _fake_attach)

    job._state.update(status="running")
    job._run_soundcloud(track_id)

    assert job._state["status"] == "done"
    assert job._state["downloaded"] == 1
    assert linked == {"path": "/dl/A - B.mp3", "fmt": "mp3", "bitrate": 245}
    db = factory()
    tr = db.get(Track, track_id)
    assert tr.has_local_file is True
    assert tr.last_download_outcome == "downloaded"


def test_run_soundcloud_failure(monkeypatch):
    factory, track_id = _factory_with_track()
    monkeypatch.setattr(job, "SessionLocal", factory)

    def _boom(url, d):
        raise SoundCloudAudioError("boom")

    monkeypatch.setattr(job, "download_track_audio", _boom)
    called = {"attach": False}
    monkeypatch.setattr(job, "attach_local_file",
                        lambda *a, **k: called.update(attach=True))

    job._state.update(status="running")
    job._run_soundcloud(track_id)

    assert job._state["status"] == "done"
    assert job._state["failed"] == 1
    assert called["attach"] is False
    db = factory()
    tr = db.get(Track, track_id)
    assert tr.has_local_file is False
    assert tr.last_download_outcome == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_soundcloud_download_job.py -v`
Expected: FAIL con `AttributeError: module 'app.services.soulseek_download_job' has no attribute 'download_track_audio'` (o `_run_soundcloud`).

- [ ] **Step 3: Write minimal implementation**

3a. In `backend/app/services/soulseek_download_job.py`, aggiungi l'import dopo la riga `from app.services.soulseek_select import auto_pick_candidates, search_candidates` (~riga 24):
```python
from app.integrations.soundcloud_audio import SoundCloudAudioError, download_track_audio
```

3b. Sostituisci la funzione `_start` esistente (~righe 307-318) con la versione che usa il reset estratto:
```python
def _reset_running_state(total: int, playlist_id: int | None) -> None:
    _state.update(status="running", processed=0, total=total,
                  downloaded=0, needs_review=0, not_found=0, failed=0,
                  playlist_id=playlist_id, items=[], error=None,
                  current_label=None,
                  started_at=datetime.now(timezone.utc).isoformat(),
                  finished_at=None)


def _start(items, playlist_id) -> dict:
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _reset_running_state(len(items), playlist_id)
    threading.Thread(target=_run, args=(items, playlist_id), daemon=True).start()
    return job_state()
```

3c. In fondo al file (dopo `start_manual_job`), aggiungi:
```python
def start_soundcloud_track_job(track_id: int) -> dict:
    """Scarica via yt-dlp l'audio di una singola traccia SoundCloud e la collega.

    Riusa lo stesso stato/lock/barra del download Soulseek (un solo download alla
    volta). Nessun candidato slskd: scarica direttamente da track.url.
    """
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _reset_running_state(1, None)
    threading.Thread(target=_run_soundcloud, args=(track_id,), daemon=True).start()
    return job_state()


def _run_soundcloud(track_id: int) -> None:
    """Worker: scarica l'audio SoundCloud della traccia e la collega. Niente slskd."""
    db = SessionLocal()
    outcome = "failed"
    reason: str | None = None
    try:
        track = get_track(db, track_id)
        if track is None:
            _state.update(status="error", error="track_not_found")
            return
        _state["current_label"] = _track_label(track)
        try:
            path = download_track_audio(track.url, settings.slskd_download_dir)
            quality = read_audio_quality(path)
            attach_local_file(db, track, path=path, fmt=quality["format"],
                              bitrate=quality["bitrate"])
            outcome = "downloaded"
        except SoundCloudAudioError as exc:
            reason = str(exc)
            logger.warning("Download SoundCloud fallito per track_id=%s: %s", track_id, exc)
        except Exception:  # noqa: BLE001 — un fallimento non deve lasciare il job appeso
            reason = "error"
            logger.exception("Download SoundCloud fallito per track_id=%s", track_id)
        _state[outcome] = _state.get(outcome, 0) + 1
        _state["processed"] = 1
        track.last_download_outcome = outcome
        track.last_download_reason = reason
        track.last_download_path = None
        db.commit()
        _state["items"].append({
            "track_id": track_id,
            "artist": track.artist,
            "title": track.title,
            "outcome": outcome,
            "reason": reason,
        })
        _state.update(status="done")
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Job download SoundCloud interrotto: %s", exc)
    finally:
        _state["current_label"] = None
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_soundcloud_download_job.py tests/test_job_double_start.py -v`
Expected: PASS (i due nuovi test + i test doppio-avvio esistenti restano verdi dopo il refactor di `_start`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/soulseek_download_job.py backend/tests/test_soundcloud_download_job.py
git commit -m "feat(downloads): worker SoundCloud nel job condiviso (stessa barra Soulseek)"
```

---

### Task 4: Endpoint HTTP con gating

Espone `POST /api/downloads/track/soundcloud` con i controlli di disponibilità e identità traccia, poi avvia il job.

**Files:**
- Modify: `backend/app/routers/downloads.py` (import; `_ffmpeg_available`; modello `TrackSoundcloudIn`; endpoint)
- Test: `backend/tests/test_soundcloud_download_router.py` (nuovo)

**Interfaces:**
- Consumes: `soundcloud_available()` (da `app.integrations.soundcloud`), `settings` (da `app.core.config`), `job.is_running()`, `job.start_soundcloud_track_job(track_id)` (Task 3), `get_track`, `SessionLocal`, `api_error`.
- Produces: `_ffmpeg_available() -> bool`; endpoint `POST /api/downloads/track/soundcloud` → 202 `{available: True, **job_state}` oppure 409/404/422.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_soundcloud_download_router.py`:
```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import Base
from app.main import app
from app.models import Track
from app.routers import downloads as downloads_router
from app.services import soulseek_download_job as job

client = TestClient(app)


def _factory():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return sessionmaker(bind=e, expire_on_commit=False)


def _ok(monkeypatch):
    monkeypatch.setattr(downloads_router, "soundcloud_available", lambda: True)
    monkeypatch.setattr(downloads_router, "_ffmpeg_available", lambda: True)
    monkeypatch.setattr(settings, "slskd_download_dir", "/dl")
    monkeypatch.setattr(job, "is_running", lambda: False)


def test_409_when_ytdlp_missing(monkeypatch):
    monkeypatch.setattr(downloads_router, "soundcloud_available", lambda: False)
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": 1})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ytdlp_unavailable"


def test_409_when_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr(downloads_router, "soundcloud_available", lambda: True)
    monkeypatch.setattr(downloads_router, "_ffmpeg_available", lambda: False)
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": 1})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ffmpeg_unavailable"


def test_409_when_dir_not_configured(monkeypatch):
    monkeypatch.setattr(downloads_router, "soundcloud_available", lambda: True)
    monkeypatch.setattr(downloads_router, "_ffmpeg_available", lambda: True)
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": 1})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "download_dir_not_configured"


def test_409_when_already_running(monkeypatch):
    _ok(monkeypatch)
    monkeypatch.setattr(job, "is_running", lambda: True)
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": 1})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "download_already_running"


def test_404_when_track_missing(monkeypatch):
    _ok(monkeypatch)
    monkeypatch.setattr(downloads_router, "SessionLocal", _factory())
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": 999})
    assert r.status_code == 404


def test_422_when_not_a_soundcloud_track(monkeypatch):
    _ok(monkeypatch)
    factory = _factory()
    db = factory()
    t = Track(source_type="spotify", platform="spotify", title="X", artist="Y")
    db.add(t)
    db.commit()
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": t.id})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "not_a_soundcloud_track"


def test_202_starts_job(monkeypatch):
    _ok(monkeypatch)
    factory = _factory()
    db = factory()
    t = Track(source_type="soundcloud", platform="soundcloud",
              url="https://soundcloud.com/a/b", title="B", artist="A")
    db.add(t)
    db.commit()
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    started = []
    monkeypatch.setattr(job, "start_soundcloud_track_job",
                        lambda tid: started.append(tid) or {"status": "running"})
    r = client.post("/api/downloads/track/soundcloud", json={"track_id": t.id})
    assert r.status_code == 202
    assert r.json()["available"] is True
    assert started == [t.id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_soundcloud_download_router.py -v`
Expected: FAIL — l'endpoint non esiste (404 su tutte, o `AttributeError` su `soundcloud_available`).

- [ ] **Step 3: Write minimal implementation**

3a. In `backend/app/routers/downloads.py`, aggiungi agli import in testa (dopo gli import esistenti, ~riga 23):
```python
from app.core.config import settings
from app.integrations.soundcloud import soundcloud_available
```

3b. Aggiungi un helper a livello di modulo (dopo `_slskd_file`, ~riga 95):
```python
def _ffmpeg_available() -> bool:
    """ffmpeg presente? Serve al postprocessor MP3 di yt-dlp."""
    import shutil

    return shutil.which("ffmpeg") is not None
```

3c. Aggiungi il modello di request accanto agli altri (dopo `TrackAutopickIn`, ~riga 53):
```python
class TrackSoundcloudIn(BaseModel):
    track_id: int
```

3d. Aggiungi l'endpoint dopo `download_track_auto` (~riga 196):
```python
@router.post("/track/soundcloud", status_code=202)
def download_track_soundcloud(req: TrackSoundcloudIn):
    """Scarica via yt-dlp l'audio di una singola traccia SoundCloud (dal dettaglio
    traccia) e la collega come file posseduto. Stessa barra/job del download
    Soulseek: un solo download alla volta."""
    if not soundcloud_available():
        raise api_error(409, "ytdlp_unavailable", "yt-dlp not available on the backend.")
    if not _ffmpeg_available():
        raise api_error(409, "ffmpeg_unavailable", "ffmpeg not available on the backend.")
    if not settings.slskd_download_dir:
        raise api_error(409, "download_dir_not_configured",
                        "Download dir not configured (SLSKD_DOWNLOAD_DIR).")
    if job.is_running():
        raise api_error(409, "download_already_running", "A download is already running.")
    db = SessionLocal()
    try:
        track = get_track(db, req.track_id)
        if track is None:
            raise api_error(404, "track_not_found", "Track not found.")
        if track.platform != "soundcloud" or not track.url:
            raise api_error(422, "not_a_soundcloud_track", "Track has no SoundCloud URL.")
        return {"available": True, **job.start_soundcloud_track_job(track.id)}
    finally:
        db.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_soundcloud_download_router.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Run the full backend suite (nessuna regressione)**

Run: `python -m pytest tests -q`
Expected: PASS (nessun test rotto dal refactor di `_start` e dai nuovi moduli).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/downloads.py backend/tests/test_soundcloud_download_router.py
git commit -m "feat(downloads): endpoint POST /api/downloads/track/soundcloud con gating"
```

---

### Task 5: Frontend — bottone nel dettaglio traccia

Client API + bottone gemello a "Cerca su Soulseek" (solo tracce SoundCloud senza file locale) + label i18n.

**Files:**
- Modify: `frontend/lib/api/downloads.ts` (nuovo helper)
- Modify: `frontend/app/tracks/[id]/page.tsx` (import, stato, handler, bottone, riga errore)
- Modify: `frontend/lib/i18n/it.ts` (~dopo riga 463) e `frontend/lib/i18n/en.ts` (~dopo riga 461)

**Interfaces:**
- Consumes: endpoint `POST /api/downloads/track/soundcloud` (Task 4); `Track.platform`, `Track.url`, `Track.has_local_file` (già in `types.ts`).
- Produces: `downloadTrackSoundcloud(trackId: number)`; chiavi i18n `tracks.downloadSoundcloud`, `tracks.soundcloudQueued`.

- [ ] **Step 1: Aggiungi il client API**

In `frontend/lib/api/downloads.ts`, subito dopo `downloadTrackAuto` (righe 11-13), aggiungi:
```ts
export function downloadTrackSoundcloud(trackId: number) {
  return apiPost<DownloadStatus>("/api/downloads/track/soundcloud", { track_id: trackId });
}
```
(È esportato verso l'app via `lib/api.ts`, che già re-esporta `downloads.ts` — stesso percorso di `downloadTrackAuto`. Verifica in Step 5.)

- [ ] **Step 2: Aggiungi le label i18n**

In `frontend/lib/i18n/it.ts`, dopo `soulseekQueued: "Ricerca avviata",` (riga 463), aggiungi:
```ts
    downloadSoundcloud: "Scarica da SoundCloud",
    soundcloudQueued: "Download avviato",
```
In `frontend/lib/i18n/en.ts`, dopo `soulseekQueued: "Search started",` (riga 461), aggiungi:
```ts
    downloadSoundcloud: "Download from SoundCloud",
    soundcloudQueued: "Download started",
```

- [ ] **Step 3: Aggiungi import, stato e handler nella pagina**

3a. In `frontend/app/tracks/[id]/page.tsx`, riga 7, aggiungi `downloadTrackSoundcloud` all'import da `@/lib/api`:
```tsx
import { apiGet, downloadTrackAuto, downloadTrackSoundcloud, fmtDuration, transitions, trackLabel, type TrackDetail, type TransitionCandidate } from "@/lib/api";
```

3b. Dopo lo stato `dlError` (riga 47), aggiungi:
```tsx
  const [scState, setScState] = useState<"idle" | "running" | "queued">("idle");
  const [scError, setScError] = useState<string | null>(null);
```

3c. Dopo l'handler `searchSoulseek` (dopo la riga 68), aggiungi:
```tsx
  const downloadSoundcloud = async () => {
    setScState("running");
    setScError(null);
    try {
      await downloadTrackSoundcloud(track.id);
      // Stesso job bar globale del download Soulseek: aggancia il progresso da solo.
      setScState("queued");
    } catch (e) {
      setScError(String((e as { message?: string })?.message ?? e));
      setScState("idle");
    }
  };
```

- [ ] **Step 4: Aggiungi il bottone e la riga d'errore**

4a. Nella card "Disco", dentro il `<div className="flex items-center gap-2">` dell'`action`, subito **dopo** il bottone Soulseek (dopo la riga 135, la chiusura `)}`), aggiungi:
```tsx
                {!track.has_local_file && track.platform === "soundcloud" && track.url && (
                  <Button size="sm" variant={scState === "queued" ? "ghost" : "outline"} onClick={downloadSoundcloud} disabled={scState !== "idle"}>
                    {scState === "queued" ? <><Check size={14} /> {t.tracks.soundcloudQueued}</>
                      : scState === "running" ? <Spinner />
                      : <><Download size={14} /> {t.tracks.downloadSoundcloud}</>}
                  </Button>
                )}
```

4b. Subito dopo la riga dell'errore Soulseek (riga 142, `{dlError && ...}`), aggiungi la riga per l'errore SoundCloud:
```tsx
          {scError && <p className="border-b border-border/50 px-4 py-2 text-xs text-danger">⚠ {scError}</p>}
```

- [ ] **Step 5: Verifica lint + build**

Run (da `frontend/`): `npm run lint && npm run build`
Expected: nessun errore di lint; build completata. Se `downloadTrackSoundcloud` non risolve, verifica che `frontend/lib/api.ts` contenga il re-export di `./api/downloads` (es. `export * from "./api/downloads";`) — se il pattern è a export nominati, aggiungi `downloadTrackSoundcloud` alla lista.

- [ ] **Step 6: Verifica visiva nel preview**

Avvia il dev server (preview_start) e apri il dettaglio di una traccia SoundCloud senza file locale (`platform === "soundcloud"`, `url` presente, `has_local_file` false). Attesa: nella card "Disco" compaiono **due** bottoni — "Cerca su Soulseek" e "Scarica da SoundCloud" — accanto a "Collega file". Su una traccia Spotify il secondo bottone **non** deve comparire. Cattura uno screenshot come prova.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/api/downloads.ts frontend/app/tracks/[id]/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(tracks): bottone 'Scarica da SoundCloud' (yt-dlp) nel dettaglio traccia"
```

---

### Task 6: Documentazione e policy

Allinea CLAUDE.md (eccezione acquisizione persistente), API.md (nuovo endpoint) e PROGRESS.md (milestone).

**Files:**
- Modify: `CLAUDE.md` (paragrafo introduttivo sulle eccezioni ad "audio")
- Modify: `docs/API.md` (sezione downloads)
- Modify: `PROGRESS.md` (nuova voce di milestone in cima al diario)

**Interfaces:** nessuna (solo documentazione).

- [ ] **Step 1: CLAUDE.md — estendi l'eccezione di acquisizione persistente**

In `CLAUDE.md`, nel paragrafo introduttivo, subito dopo la frase che inizia con *"An explicit exception to \"does not keep audio files\": persistent acquisition via Soulseek/slskd, which links a file to the existing `Track`..."*, aggiungi:
```
A parallel exception: per-track SoundCloud download via yt-dlp from the track
detail page, which extracts an MP3 into the same shared download folder
(`SLSKD_DOWNLOAD_DIR`) and links it to the existing `Track`
(`has_local_file`/`local_path`/`local_format`/`local_bitrate`); tags stay
Sortory's job.
```

- [ ] **Step 2: docs/API.md — documenta il nuovo endpoint**

In `docs/API.md`, nella sezione degli endpoint `downloads` (accanto a `POST /api/downloads/track/auto`), aggiungi:
```
### POST /api/downloads/track/soundcloud

Scarica via yt-dlp l'audio della singola traccia SoundCloud (`platform ==
"soundcloud"`, `url` presente), lo estrae in MP3 nella cartella condivisa
`SLSKD_DOWNLOAD_DIR` e lo collega alla `Track` (`has_local_file`). Riusa il job/
barra del download Soulseek (un solo download alla volta).

Body: `{ "track_id": <int> }`. Risposta: `202 { "available": true, ...job_state }`.

Errori: `409 ytdlp_unavailable` · `409 ffmpeg_unavailable` · `409
download_dir_not_configured` · `409 download_already_running` · `404
track_not_found` · `422 not_a_soundcloud_track`.
```

- [ ] **Step 3: PROGRESS.md — voce di milestone**

In cima al diario `PROGRESS.md` (rispettando lo stile delle voci esistenti), aggiungi una voce datata 2026-07-23 che riassume: bottone "Scarica da SoundCloud" nel dettaglio traccia; download yt-dlp → MP3 in `SLSKD_DOWNLOAD_DIR`; job condiviso con Soulseek (`_run_soundcloud`, stessa barra); nuovo endpoint `POST /api/downloads/track/soundcloud`; nuovi moduli `integrations/soundcloud_audio.py` e test.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/API.md PROGRESS.md
git commit -m "docs: download SoundCloud via yt-dlp (endpoint, eccezione acquisizione, milestone)"
```

---

## Self-Review

**Spec coverage:**
- Formato MP3 (ffmpeg, V0) → Task 2. ✅
- Job condiviso + barra globale → Task 3 (`_run_soundcloud` riusa `_state`/`_lock`; nessun nuovo poller: `jobs-provider` già polla `/api/downloads/status`). ✅
- Cartella condivisa `SLSKD_DOWNLOAD_DIR` → Task 3 (`settings.slskd_download_dir`), gate in Task 4. ✅
- Linking identico via `attach_local_file` → Task 3. ✅
- SSRF guard → Task 1 + Task 2. ✅
- Endpoint + 6 rami di gating → Task 4. ✅
- Bottone solo su tracce SoundCloud nel dettaglio + i18n → Task 5. ✅
- No auto-refetch (parità Soulseek) → Task 5 (l'handler non rifà fetch, come `searchSoulseek`). ✅
- Docs/policy → Task 6. ✅
- Test (validator, downloader, job success/failure, router gating) → Task 1-4. ✅

**Placeholder scan:** nessun TBD/TODO; ogni step di codice mostra il codice completo. ✅

**Type consistency:** `download_track_audio(url, dest_dir) -> str`, `SoundCloudAudioError`, `validate_soundcloud_url`, `start_soundcloud_track_job`, `_run_soundcloud`, `_ffmpeg_available`, `TrackSoundcloudIn`, `downloadTrackSoundcloud`, chiavi `downloadSoundcloud`/`soundcloudQueued`: nomi coerenti tra tutte le task. `read_audio_quality` ritorna `{"format", "bitrate"}`, coerente con l'uso in `attach_local_file(fmt=..., bitrate=...)`. ✅
