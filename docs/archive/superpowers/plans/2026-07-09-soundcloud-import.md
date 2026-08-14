# Import SoundCloud (playlist + like) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importare in Cratory i metadati di playlist SoundCloud (pubbliche e private via secret link) e dei like dell'utente, via yt-dlp solo-metadati.

**Architecture:** Client yt-dlp in `integrations/soundcloud.py` (API Python, `extract_flat`, mai audio); normalizzatore `normalize_soundcloud_item` che alimenta il motore esistente `import_playlist`; router `/api/soundcloud/*` gemello di `spotify.py`; sync additivo (mai prune) per playlist SoundCloud; frontend con pagina incolla-URL, preview selettiva dei like e username in Settings.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, Pydantic, yt-dlp (già in `requirements.txt`), Next.js 16 + Tailwind.

**Spec:** `docs/superpowers/specs/2026-07-09-soundcloud-import-design.md` (leggerla prima di iniziare).

## Global Constraints

- Solo metadati: MAI scaricare/salvare audio (`skip_download`, `extract_flat="in_playlist"`).
- BPM/key non si toccano: vengono solo da Rekordbox.
- `isrc` per SoundCloud è sempre `None`: la dedup usa `platform_track_id` poi fuzzy.
- Sync/re-import SoundCloud sempre `prune=False` (additivo).
- Nessun test parla con la rete: yt-dlp sempre mockato via `monkeypatch`.
- Docstring e commenti in italiano, come il resto del codebase.
- Commit message in italiano stile repo (`feat(soundcloud): …`), SENZA riga `Co-Authored-By`.
- Frontend: Next.js 16 ha breaking changes — leggere `frontend/CLAUDE.md`; attenzione allo spazio JSX a fine riga (usare `{" "}` esplicito se il testo va a capo).
- Comandi backend: `cd backend && source .venv/bin/activate`; test: `python -m pytest tests/<file> -v`.
- Branch di lavoro: `soundcloud-import`.

---

### Task 1: Integrazione yt-dlp (`integrations/soundcloud.py`)

**Files:**
- Create: `backend/app/integrations/soundcloud.py`
- Test: `backend/tests/test_soundcloud_import.py` (nuovo)

**Interfaces:**
- Produces (usate dai task 4-5):
  - `class SoundCloudError(RuntimeError)` e `class SoundCloudInvalidUrl(SoundCloudError)`
  - `soundcloud_available() -> bool`
  - `ytdlp_version() -> str | None`
  - `is_likes_url(url: str) -> bool`
  - `fetch_playlist(url: str) -> dict` — info dict yt-dlp con `entries` materializzate in lista
  - `fetch_likes(username: str, limit: int = DEFAULT_LIKES_LIMIT) -> dict`
  - `DEFAULT_LIKES_LIMIT = 100`

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_soundcloud_import.py`:

```python
"""Integrazione SoundCloud via yt-dlp (solo metadati) e normalizzazione."""

import pytest

from app.integrations import soundcloud as sc
from app.integrations.soundcloud import (
    SoundCloudError,
    SoundCloudInvalidUrl,
    fetch_likes,
    fetch_playlist,
    is_likes_url,
)


# --- helper fixture: entry flat e info dict realistici -----------------------

def _entry(i: int = 1, title: str = "Artist X - Cool Track", uploader: str | None = "channelY", **kw) -> dict:
    e = {
        "_type": "url",
        "id": str(1000 + i),
        "url": f"https://soundcloud.com/u/track-{i}",
        "title": title,
        "duration": 245.0,
        "uploader": uploader,
    }
    e.update(kw)
    return e


def _info(entries: list, **kw) -> dict:
    info = {
        "id": "12345",
        "title": "Deep Crate",
        "uploader": "digger",
        "webpage_url": "https://soundcloud.com/digger/sets/deep-crate",
        "entries": entries,
    }
    info.update(kw)
    return info


# --- validazione URL (pura, niente rete) --------------------------------------

def test_fetch_playlist_rifiuta_url_non_http():
    with pytest.raises(SoundCloudInvalidUrl):
        fetch_playlist("file:///etc/passwd")


def test_fetch_playlist_rifiuta_host_non_soundcloud():
    with pytest.raises(SoundCloudInvalidUrl):
        fetch_playlist("https://example.com/sets/x")


def test_is_likes_url():
    assert is_likes_url("https://soundcloud.com/luca/likes")
    assert is_likes_url("https://soundcloud.com/luca/likes/")
    assert not is_likes_url("https://soundcloud.com/luca/sets/crate")


# --- fetch con estrattore mockato ----------------------------------------------

def test_fetch_playlist_materializza_le_entries(monkeypatch):
    def fake_extract(url, *, limit=None):
        return _info(iter([_entry(1), _entry(2)]))  # generatore: va materializzato

    monkeypatch.setattr(sc, "_extract", fake_extract)
    info = fetch_playlist("https://soundcloud.com/digger/sets/deep-crate")
    assert isinstance(info["entries"], list)
    assert len(info["entries"]) == 2


def test_fetch_likes_costruisce_url_e_passa_il_limit(monkeypatch):
    seen = {}

    def fake_extract(url, *, limit=None):
        seen["url"] = url
        seen["limit"] = limit
        return _info([_entry(1)])

    monkeypatch.setattr(sc, "_extract", fake_extract)
    fetch_likes("  @luca ", limit=50)
    assert seen["url"] == "https://soundcloud.com/luca/likes"
    assert seen["limit"] == 50


def test_fetch_likes_senza_username_solleva():
    with pytest.raises(SoundCloudError):
        fetch_likes("   ")
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_soundcloud_import.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.integrations.soundcloud'`

- [ ] **Step 3: Implementazione**

Creare `backend/app/integrations/soundcloud.py`:

```python
"""Client SoundCloud via yt-dlp: SOLO metadati, mai audio.

Fetcher provvisorio in attesa dell'API ufficiale (che richiede Artist Pro):
usa l'estrazione flat di yt-dlp per leggere playlist pubbliche, secret link
e like. Failure mode noto: se SoundCloud cambia qualcosa, l'estrazione si
rompe finché non si aggiorna yt-dlp (il messaggio d'errore lo dice).

Fetch sequenziali, nessun parallelismo: profilo basso su API non ufficiale.
"""
from __future__ import annotations

import importlib.util
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_LIKES_LIMIT = 100
_SOCKET_TIMEOUT = 20
_ALLOWED_HOSTS = {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"}


class SoundCloudError(RuntimeError):
    """Errore nel fetch da SoundCloud (rete, estrazione, URL vuoto...)."""


class SoundCloudInvalidUrl(SoundCloudError):
    """URL non valido come input: mappa su HTTP 422, non 502."""


def soundcloud_available() -> bool:
    return importlib.util.find_spec("yt_dlp") is not None


def ytdlp_version() -> str | None:
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return None


def _validate_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        # Evita che yt-dlp riceva file://, schemi locali o host vuoti (SSRF / lettura file).
        raise SoundCloudInvalidUrl("URL non valido: ammessi solo link http(s).")
    if parsed.netloc.lower() not in _ALLOWED_HOSTS:
        raise SoundCloudInvalidUrl("URL non valido: atteso un link soundcloud.com.")
    return url


def is_likes_url(url: str) -> bool:
    """True per gli URL /likes: nel flusso import-playlist vanno rifiutati (422)."""
    return urlparse(url or "").path.rstrip("/").endswith("/likes")


def _extract(url: str, *, limit: int | None = None) -> dict:
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",  # solo metadati delle entry, mai risolvere l'audio
        "skip_download": True,
        "socket_timeout": _SOCKET_TIMEOUT,
    }
    if limit:
        opts["playlistend"] = limit
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001 — yt-dlp solleva tipi eterogenei
        raise SoundCloudError(
            f"Fetch SoundCloud fallito ({exc}). Se l'URL è corretto, prova ad aggiornare yt-dlp."
        ) from exc
    if not info:
        raise SoundCloudError("Nessun dato all'URL indicato.")
    return info


def _materialized(info: dict) -> dict:
    # yt-dlp può restituire `entries` come generatore: materializza e scarta i None.
    info["entries"] = [e for e in (info.get("entries") or []) if e]
    if not info["entries"]:
        raise SoundCloudError("Nessuna traccia trovata all'URL indicato.")
    return info


def fetch_playlist(url: str) -> dict:
    """Playlist (pubblica o secret link) -> info dict con `entries` in lista."""
    return _materialized(_extract(_validate_url(url)))


def fetch_likes(username: str, limit: int = DEFAULT_LIKES_LIMIT) -> dict:
    """Like pubblici dell'utente -> info dict con `entries` in lista (più recenti prima)."""
    username = (username or "").strip().lstrip("@")
    if not username:
        raise SoundCloudError("Username SoundCloud non configurato.")
    return _materialized(_extract(f"https://soundcloud.com/{username}/likes", limit=limit))
```

- [ ] **Step 4: Verificare che passino**

Run: `python -m pytest tests/test_soundcloud_import.py -v`
Expected: PASS (7 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/soundcloud.py backend/tests/test_soundcloud_import.py
git commit -m "feat(soundcloud): client yt-dlp solo-metadati per playlist e like"
```

---

### Task 2: Normalizzatore `normalize_soundcloud_item`

**Files:**
- Modify: `backend/app/services/playlist_import.py` (dopo `normalize_spotify_item`, ~riga 90)
- Test: `backend/tests/test_soundcloud_import.py` (append)

**Interfaces:**
- Consumes: `NormalizedTrack` (dataclass esistente in `playlist_import.py`).
- Produces (usate dai task 3-5):
  - `split_artist_title(raw_title: str | None, uploader: str | None) -> tuple[str | None, str | None]`
  - `normalize_soundcloud_item(entry: dict) -> NormalizedTrack | None`

- [ ] **Step 1: Scrivere i test che falliscono**

Append a `backend/tests/test_soundcloud_import.py`:

```python
# --- normalizzazione -----------------------------------------------------------

from app.services.playlist_import import normalize_soundcloud_item, split_artist_title


def test_split_alla_prima_occorrenza():
    # trattini multipli: solo il primo separa artista e titolo
    assert split_artist_title("Artist X - Cool Track - Extended", "chan") == (
        "Artist X", "Cool Track - Extended",
    )


def test_split_senza_separatore_usa_uploader():
    assert split_artist_title("Cool Track (Bootleg)", "channelY") == ("channelY", "Cool Track (Bootleg)")


def test_split_senza_separatore_ne_uploader():
    assert split_artist_title("Cool Track", None) == (None, "Cool Track")


def test_split_titolo_vuoto():
    assert split_artist_title(None, "channelY") == ("channelY", None)


def test_normalize_entry_completa():
    norm = normalize_soundcloud_item(_entry(1))
    assert norm is not None
    assert norm.platform == "soundcloud"
    assert norm.platform_track_id == "1001"
    assert norm.artist == "Artist X"
    assert norm.title == "Cool Track"
    assert norm.duration_seconds == 245
    assert norm.url == "https://soundcloud.com/u/track-1"
    assert norm.isrc is None


def test_normalize_entry_senza_id_scartata():
    assert normalize_soundcloud_item(_entry(1, id=None)) is None
    assert normalize_soundcloud_item({}) is None
    assert normalize_soundcloud_item(None) is None


def test_normalize_campi_mancanti():
    norm = normalize_soundcloud_item({"id": 42, "title": "Solo Titolo"})
    assert norm is not None
    assert norm.platform_track_id == "42"  # id numerico -> stringa
    assert norm.artist is None
    assert norm.title == "Solo Titolo"
    assert norm.duration_seconds is None
    assert norm.artwork_url is None
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_soundcloud_import.py -v`
Expected: FAIL con `ImportError: cannot import name 'normalize_soundcloud_item'`

- [ ] **Step 3: Implementazione**

In `backend/app/services/playlist_import.py`, subito dopo `normalize_spotify_item`:

```python
SC_TITLE_SEPARATOR = " - "


def split_artist_title(raw_title: str | None, uploader: str | None) -> tuple[str | None, str | None]:
    """Split deterministico "Artist - Title" alla PRIMA occorrenza del separatore.

    Su SoundCloud il titolo spesso contiene tutto e l'"artista" è lo username
    dell'uploader (magari un canale): senza separatore si ripiega su quello.
    È normalizzazione da import (competenza Cratory), non enrichment (Sortory).
    """
    raw_title = (raw_title or "").strip()
    uploader = (uploader or "").strip() or None
    if SC_TITLE_SEPARATOR in raw_title:
        left, _, right = raw_title.partition(SC_TITLE_SEPARATOR)
        return (left.strip() or uploader), (right.strip() or raw_title)
    return uploader, (raw_title or None)


def normalize_soundcloud_item(entry: dict | None) -> NormalizedTrack | None:
    """Entry flat yt-dlp -> NormalizedTrack. Niente ISRC: SoundCloud non lo espone."""
    if not entry:
        return None
    tid = entry.get("id")
    if not tid:
        return None
    artist, title = split_artist_title(entry.get("title"), entry.get("uploader"))
    duration = entry.get("duration")
    thumbnails = entry.get("thumbnails") or []
    return NormalizedTrack(
        platform="soundcloud",
        platform_track_id=str(tid),
        title=title,
        artist=artist,
        album=None,
        duration_seconds=int(duration) if duration else None,
        url=entry.get("url") or entry.get("webpage_url"),
        artwork_url=(thumbnails[-1].get("url") if thumbnails else None),
        isrc=None,
        added_at=None,  # non disponibile in flat mode
    )
```

- [ ] **Step 4: Verificare che passino**

Run: `python -m pytest tests/test_soundcloud_import.py tests/test_import_playlist_normalize.py -v`
Expected: PASS (tutti; il secondo file garantisce che il motore esistente non è rotto)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/playlist_import.py backend/tests/test_soundcloud_import.py
git commit -m "feat(soundcloud): normalizzatore entry yt-dlp con split Artist - Title"
```

---

### Task 3: Servizi like (preview selettiva + import selezionati)

**Files:**
- Modify: `backend/app/services/playlist_import.py` (dopo `import_selected_liked_tracks`, ~riga 340)
- Test: `backend/tests/test_soundcloud_import.py` (append)

**Interfaces:**
- Consumes: `_liked_playlist(db, platform)`, `tracks_for_playlist`, `import_playlist`, `normalize_soundcloud_item` (task 2).
- Produces (usate dal task 4):
  - `SC_LIKED_PLAYLIST_NAME = "SoundCloud Likes"`
  - `preview_soundcloud_likes(db, entries: list[dict]) -> list[dict]` — chiavi: `track_id, title, artist, duration_seconds, artwork_url, url, already_imported`
  - `import_selected_soundcloud_likes(db, entries: list[dict], track_ids: list[str]) -> dict` (report di `import_playlist`)

- [ ] **Step 1: Scrivere i test che falliscono**

Append a `backend/tests/test_soundcloud_import.py`:

```python
# --- like: preview selettiva e import dei selezionati ---------------------------

from app.models import Playlist
from app.services.playlist_import import (
    SC_LIKED_PLAYLIST_NAME,
    import_selected_soundcloud_likes,
    preview_soundcloud_likes,
)


def test_preview_marca_gia_importate(db):
    entries = [_entry(1), _entry(2, title="Other - Tune")]
    # primo import: entra solo la traccia 1
    import_selected_soundcloud_likes(db, entries, ["1001"])
    preview = preview_soundcloud_likes(db, entries)
    assert [p["track_id"] for p in preview] == ["1001", "1002"]
    assert preview[0]["already_imported"] is True
    assert preview[1]["already_imported"] is False
    assert preview[0]["artist"] == "Artist X"


def test_import_selected_filtra_e_riusa_la_playlist_liked(db):
    entries = [_entry(1), _entry(2, title="Other - Tune"), _entry(3, title="Third - One")]
    r1 = import_selected_soundcloud_likes(db, entries, ["1001", "1003"])
    assert r1["created"] == 2
    # secondo giro: idempotente sulla stessa playlist di sistema, additivo
    r2 = import_selected_soundcloud_likes(db, entries, ["1002"])
    assert r2["created"] == 1
    assert r2["removed"] == 0
    liked = db.query(Playlist).filter(
        Playlist.platform == "soundcloud", Playlist.kind == "liked",
    ).all()
    assert len(liked) == 1
    assert liked[0].name == SC_LIKED_PLAYLIST_NAME
    assert liked[0].track_count == 3
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_soundcloud_import.py -v`
Expected: FAIL con `ImportError: cannot import name 'preview_soundcloud_likes'`

- [ ] **Step 3: Implementazione**

In `backend/app/services/playlist_import.py`, dopo `import_selected_liked_tracks`:

```python
SC_LIKED_PLAYLIST_NAME = "SoundCloud Likes"


def preview_soundcloud_likes(db: Session, entries: list) -> list[dict]:
    """Entry like yt-dlp -> anteprima selezionabile, senza importare nulla.

    ``already_imported`` = la traccia è già collegata alla playlist liked
    SoundCloud locale (match per platform_track_id: l'ISRC qui non esiste).
    """
    playlist = _liked_playlist(db, "soundcloud")
    platform_ids: set[str] = set()
    if playlist is not None:
        for t in tracks_for_playlist(db, playlist.id):
            if t.platform_track_id:
                platform_ids.add(t.platform_track_id)

    out: list[dict] = []
    for entry in entries:
        norm = normalize_soundcloud_item(entry)
        if norm is None or not norm.platform_track_id:
            continue
        out.append({
            "track_id": norm.platform_track_id,
            "title": norm.title,
            "artist": norm.artist,
            "duration_seconds": norm.duration_seconds,
            "artwork_url": norm.artwork_url,
            "url": norm.url,
            "already_imported": norm.platform_track_id in platform_ids,
        })
    return out


def import_selected_soundcloud_likes(db: Session, entries: list, track_ids: list[str]) -> dict:
    """Importa nella playlist liked SoundCloud SOLO le entry selezionate. Additivo."""
    wanted = {str(t) for t in track_ids}
    selected = [e for e in entries if e and str(e.get("id")) in wanted]
    return import_playlist(
        db, platform="soundcloud", name=SC_LIKED_PLAYLIST_NAME,
        items=selected, normalize=normalize_soundcloud_item,
        kind="liked", prune=False,
    )
```

- [ ] **Step 4: Verificare che passino**

Run: `python -m pytest tests/test_soundcloud_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/playlist_import.py backend/tests/test_soundcloud_import.py
git commit -m "feat(soundcloud): preview selettiva e import dei like nella playlist di sistema"
```

---

### Task 4: Schemi + router `/api/soundcloud/*`

**Files:**
- Modify: `backend/app/schemas.py` (dopo `ManualImportRequest`, ~riga 319)
- Create: `backend/app/routers/soundcloud.py`
- Modify: `backend/app/main.py` (import dei router ~riga 11, `include_router` ~riga 82)
- Test: `backend/tests/test_soundcloud_api.py` (nuovo)

**Interfaces:**
- Consumes: task 1 (`fetch_playlist`, `fetch_likes`, `is_likes_url`, `soundcloud_available`, `ytdlp_version`, `SoundCloudError`, `SoundCloudInvalidUrl`, `DEFAULT_LIKES_LIMIT`), task 3 (`preview_soundcloud_likes`, `import_selected_soundcloud_likes`), `import_playlist` + `normalize_soundcloud_item`, `app_state.get_state/set_state`, schema esistente `PlaylistImportReport`.
- Produces: endpoint `GET /api/soundcloud/status`, `PUT /api/soundcloud/config`, `POST /api/soundcloud/import`, `GET /api/soundcloud/likes/preview`, `POST /api/soundcloud/import/likes`; chiave AppState `soundcloud_username`.

- [ ] **Step 1: Aggiungere gli schemi**

In `backend/app/schemas.py`, dopo `ManualImportRequest`:

```python
# --- SoundCloud ---------------------------------------------------------------


class SoundCloudStatus(BaseModel):
    available: bool  # yt-dlp importabile
    ytdlp_version: str | None = None
    username: str | None = None


class SoundCloudConfigRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)


class SoundCloudImportRequest(BaseModel):
    url: str = Field(min_length=1)  # playlist pubblica o secret link


class SoundCloudLikedTrackPreview(BaseModel):
    track_id: str
    title: str | None = None
    artist: str | None = None
    duration_seconds: int | None = None
    artwork_url: str | None = None
    url: str | None = None
    already_imported: bool = False


class SoundCloudLikedSelectedRequest(BaseModel):
    track_ids: list[str] = Field(default_factory=list)
    limit: int = 100  # quanti like recenti rifetchare per filtrare i selezionati
```

- [ ] **Step 2: Scrivere i test che falliscono**

Creare `backend/tests/test_soundcloud_api.py`:

```python
"""Router /api/soundcloud: import da URL, config username, like selettivi."""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.integrations.soundcloud import SoundCloudError, SoundCloudInvalidUrl
from app.main import app
from app.models import Playlist
from app.routers import soundcloud as sc_router

client = TestClient(app)


@pytest.fixture()
def api_db(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)


def _entry(i: int = 1, title: str = "Artist X - Cool Track", **kw) -> dict:
    e = {"id": str(1000 + i), "url": f"https://soundcloud.com/u/track-{i}",
         "title": title, "duration": 245.0, "uploader": "channelY"}
    e.update(kw)
    return e


def _info(entries: list) -> dict:
    return {"id": "12345", "title": "Deep Crate", "uploader": "digger",
            "webpage_url": "https://soundcloud.com/digger/sets/deep-crate",
            "entries": entries}


def test_status_e_config(api_db, monkeypatch):
    monkeypatch.setattr(sc_router, "soundcloud_available", lambda: True)
    monkeypatch.setattr(sc_router, "ytdlp_version", lambda: "2026.01.01")
    r = client.get("/api/soundcloud/status")
    assert r.status_code == 200
    assert r.json() == {"available": True, "ytdlp_version": "2026.01.01", "username": None}

    r = client.put("/api/soundcloud/config", json={"username": " luca "})
    assert r.status_code == 200
    assert r.json()["username"] == "luca"
    assert client.get("/api/soundcloud/status").json()["username"] == "luca"


def test_import_da_url_crea_playlist(api_db, monkeypatch):
    monkeypatch.setattr(sc_router, "fetch_playlist", lambda url: _info([_entry(1), _entry(2)]))
    r = client.post("/api/soundcloud/import",
                    json={"url": "https://soundcloud.com/digger/sets/deep-crate/s-abc123"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 2
    pl = api_db.get(Playlist, body["playlist_id"])
    assert pl.platform == "soundcloud"
    assert pl.platform_playlist_id == "12345"
    # l'URL salvato è quello incollato (conserva il secret link), non il canonico
    assert pl.url == "https://soundcloud.com/digger/sets/deep-crate/s-abc123"


def test_import_rifiuta_url_likes(api_db):
    r = client.post("/api/soundcloud/import", json={"url": "https://soundcloud.com/luca/likes"})
    assert r.status_code == 422


def test_import_mappa_errori(api_db, monkeypatch):
    def boom_invalid(url):
        raise SoundCloudInvalidUrl("URL non valido")
    monkeypatch.setattr(sc_router, "fetch_playlist", boom_invalid)
    assert client.post("/api/soundcloud/import", json={"url": "x"}).status_code == 422

    def boom_remote(url):
        raise SoundCloudError("estrazione fallita")
    monkeypatch.setattr(sc_router, "fetch_playlist", boom_remote)
    r = client.post("/api/soundcloud/import", json={"url": "https://soundcloud.com/a/sets/b"})
    assert r.status_code == 502


def test_likes_preview_409_senza_username(api_db):
    assert client.get("/api/soundcloud/likes/preview").status_code == 409


def test_likes_preview_e_import_selettivo(api_db, monkeypatch):
    client.put("/api/soundcloud/config", json={"username": "luca"})
    monkeypatch.setattr(sc_router, "fetch_likes",
                        lambda username, limit=100: _info([_entry(1), _entry(2, title="Other - Tune")]))
    r = client.get("/api/soundcloud/likes/preview")
    assert r.status_code == 200
    assert [p["track_id"] for p in r.json()] == ["1001", "1002"]

    r = client.post("/api/soundcloud/import/likes", json={"track_ids": ["1002"]})
    assert r.status_code == 200
    assert r.json()["created"] == 1
    # nella preview successiva la 1002 risulta importata
    preview = client.get("/api/soundcloud/likes/preview").json()
    assert {p["track_id"]: p["already_imported"] for p in preview} == {"1001": False, "1002": True}
```

- [ ] **Step 3: Verificare che falliscano**

Run: `python -m pytest tests/test_soundcloud_api.py -v`
Expected: FAIL con `ImportError: cannot import name 'soundcloud'` (router inesistente)

- [ ] **Step 4: Implementazione router + registrazione**

Creare `backend/app/routers/soundcloud.py`:

```python
"""HTTP only: stato/config SoundCloud, import playlist da URL, like selettivi."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.soundcloud import (
    DEFAULT_LIKES_LIMIT,
    SoundCloudError,
    SoundCloudInvalidUrl,
    fetch_likes,
    fetch_playlist,
    is_likes_url,
    soundcloud_available,
    ytdlp_version,
)
from app.schemas import (
    PlaylistImportReport,
    SoundCloudConfigRequest,
    SoundCloudImportRequest,
    SoundCloudLikedSelectedRequest,
    SoundCloudLikedTrackPreview,
    SoundCloudStatus,
)
from app.services.app_state import get_state, set_state
from app.services.playlist_import import (
    import_playlist,
    import_selected_soundcloud_likes,
    normalize_soundcloud_item,
    preview_soundcloud_likes,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/soundcloud", tags=["soundcloud"])

USERNAME_KEY = "soundcloud_username"


def _http_error(exc: SoundCloudError) -> HTTPException:
    if isinstance(exc, SoundCloudInvalidUrl):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


def _username_or_409(db: Session) -> str:
    username = get_state(db, USERNAME_KEY)
    if not username:
        raise HTTPException(status_code=409, detail="Username SoundCloud non configurato (Impostazioni).")
    return username


@router.get("/status", response_model=SoundCloudStatus)
def status(db: Session = Depends(get_db)):
    return SoundCloudStatus(
        available=soundcloud_available(),
        ytdlp_version=ytdlp_version(),
        username=get_state(db, USERNAME_KEY),
    )


@router.put("/config", response_model=SoundCloudStatus)
def set_config(req: SoundCloudConfigRequest, db: Session = Depends(get_db)):
    set_state(db, USERNAME_KEY, req.username.strip().lstrip("@"))
    return status(db)


@router.post("/import", response_model=PlaylistImportReport)
def import_from_url(req: SoundCloudImportRequest, db: Session = Depends(get_db)):
    """Importa una playlist SoundCloud (pubblica o secret link) come lead."""
    if is_likes_url(req.url):
        raise HTTPException(status_code=422, detail="Per i like usa il flusso 'I miei like' (import selettivo).")
    try:
        info = fetch_playlist(req.url)
    except SoundCloudError as exc:
        raise _http_error(exc) from exc
    thumbnails = info.get("thumbnails") or []
    report = import_playlist(
        db, platform="soundcloud",
        name=info.get("title") or "Playlist SoundCloud",
        items=info["entries"],
        normalize=normalize_soundcloud_item,
        platform_playlist_id=str(info["id"]) if info.get("id") else None,
        owner=info.get("uploader"),
        url=req.url.strip(),  # conserva il secret link incollato (resta solo nel DB locale)
        artwork_url=thumbnails[-1].get("url") if thumbnails else None,
    )
    return PlaylistImportReport(**report)


@router.get("/likes/preview", response_model=list[SoundCloudLikedTrackPreview])
def likes_preview(limit: int = DEFAULT_LIKES_LIMIT, db: Session = Depends(get_db)):
    """Anteprima dei like recenti, selezionabili. Non importa nulla."""
    username = _username_or_409(db)
    try:
        info = fetch_likes(username, limit=limit)
    except SoundCloudError as exc:
        raise _http_error(exc) from exc
    return [SoundCloudLikedTrackPreview(**p) for p in preview_soundcloud_likes(db, info["entries"])]


@router.post("/import/likes", response_model=PlaylistImportReport)
def import_likes(req: SoundCloudLikedSelectedRequest, db: Session = Depends(get_db)):
    """Importa SOLO i like selezionati. Stateless: rifetcha e filtra per id. Additivo."""
    username = _username_or_409(db)
    try:
        info = fetch_likes(username, limit=req.limit)
    except SoundCloudError as exc:
        raise _http_error(exc) from exc
    report = import_selected_soundcloud_likes(db, info["entries"], req.track_ids)
    return PlaylistImportReport(**report)
```

In `backend/app/main.py`: aggiungere `soundcloud` all'import dei router (riga ~11, in ordine alfabetico nella tupla) e, dopo `app.include_router(rekordbox.router)`:

```python
app.include_router(soundcloud.router)
```

- [ ] **Step 5: Verificare che passino**

Run: `python -m pytest tests/test_soundcloud_api.py tests/test_soundcloud_import.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/soundcloud.py backend/app/main.py backend/tests/test_soundcloud_api.py
git commit -m "feat(soundcloud): router import da URL, config username e like selettivi"
```

---

### Task 5: Sync per piattaforma (SoundCloud additivo)

**Files:**
- Modify: `backend/app/routers/playlists.py:162-191` (`sync_playlist`)
- Test: `backend/tests/test_soundcloud_api.py` (append)

**Interfaces:**
- Consumes: task 1 (`fetch_playlist`, `SoundCloudError`, `SoundCloudInvalidUrl`), task 2 (`normalize_soundcloud_item`).
- Produces: `POST /api/playlists/{id}/sync` funzionante anche per playlist `platform="soundcloud"` (kind `playlist`, con `prune=False`); i liked SoundCloud restano NON sincronizzabili (409, si usa il flusso selettivo).

- [ ] **Step 1: Scrivere i test che falliscono**

Append a `backend/tests/test_soundcloud_api.py`:

```python
# --- sync per piattaforma --------------------------------------------------------


def test_sync_soundcloud_additivo_senza_prune(api_db, monkeypatch):
    monkeypatch.setattr(sc_router, "fetch_playlist", lambda url: _info([_entry(1), _entry(2)]))
    body = client.post("/api/soundcloud/import",
                       json={"url": "https://soundcloud.com/digger/sets/deep-crate"}).json()

    # al secondo fetch la traccia 1 è sparita (takedown) e c'è una nuova traccia 3
    import app.routers.playlists as pl_router
    monkeypatch.setattr(pl_router, "sc_fetch_playlist",
                        lambda url: _info([_entry(2), _entry(3, title="Third - One")]))
    r = client.post(f"/api/playlists/{body['playlist_id']}/sync")
    assert r.status_code == 200
    report = r.json()
    assert report["created"] == 1
    assert report["removed"] == 0  # additivo: il takedown non scollega nulla
    pl = api_db.get(Playlist, body["playlist_id"])
    assert pl.track_count == 3


def test_sync_liked_soundcloud_409(api_db, monkeypatch):
    client.put("/api/soundcloud/config", json={"username": "luca"})
    monkeypatch.setattr(sc_router, "fetch_likes", lambda username, limit=100: _info([_entry(1)]))
    client.post("/api/soundcloud/import/likes", json={"track_ids": ["1001"]})
    liked = api_db.query(Playlist).filter(
        Playlist.platform == "soundcloud", Playlist.kind == "liked",
    ).one()
    assert client.post(f"/api/playlists/{liked.id}/sync").status_code == 409
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_soundcloud_api.py -v`
Expected: FAIL — il primo test riceve 409 ("Solo le playlist Spotify sono sincronizzabili."), e `sc_fetch_playlist` non esiste in `pl_router` (AttributeError nel monkeypatch)

- [ ] **Step 3: Implementazione**

In `backend/app/routers/playlists.py`, aggiungere agli import (vicino agli import Spotify esistenti):

```python
from app.integrations.soundcloud import (
    SoundCloudError,
    SoundCloudInvalidUrl,
    fetch_playlist as sc_fetch_playlist,
)
from app.services.playlist_import import normalize_soundcloud_item
```

Poi in `sync_playlist` sostituire il blocco del check piattaforma e aggiungere il ramo SoundCloud PRIMA della logica Spotify esistente:

```python
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist non trovata")

    if playlist.platform == "soundcloud":
        # I liked SoundCloud crescono solo via flusso selettivo: niente sync totale.
        if playlist.kind == "liked" or not playlist.url:
            raise HTTPException(status_code=409, detail="Playlist SoundCloud non sincronizzabile: usa il flusso selettivo dei like o reimporta l'URL.")
        try:
            info = sc_fetch_playlist(playlist.url)
        except SoundCloudError as exc:
            status_code = 422 if isinstance(exc, SoundCloudInvalidUrl) else 502
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        # Additivo (prune=False): su SoundCloud un takedown non significa
        # "non mi interessa più" — il lead resta collegato.
        report = import_playlist(
            db, platform="soundcloud", name=playlist.name, items=info["entries"],
            normalize=normalize_soundcloud_item,
            platform_playlist_id=playlist.platform_playlist_id,
            owner=playlist.owner, url=playlist.url, artwork_url=playlist.artwork_url,
            kind=playlist.kind, prune=False,
        )
        return PlaylistImportReport(**report)

    if playlist.platform != "spotify":
        raise HTTPException(status_code=409, detail="Solo le playlist Spotify e SoundCloud sono sincronizzabili.")
    if playlist.kind != "liked" and not playlist.platform_playlist_id:
        raise HTTPException(status_code=409, detail="Playlist non sincronizzabile da Spotify.")
    # ... resto del corpo Spotify INVARIATO (client, items, import_playlist con prune=True)
```

Nota: il docstring dell'endpoint va aggiornato: "Riallinea la playlist con la piattaforma d'origine: Spotify con prune, SoundCloud solo additivo."

- [ ] **Step 4: Verificare che passino (inclusa la non-regressione Spotify)**

Run: `python -m pytest tests/test_soundcloud_api.py tests -v` (suite completa)
Expected: PASS — nessuna regressione sugli altri test

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/playlists.py backend/tests/test_soundcloud_api.py
git commit -m "feat(soundcloud): sync additivo per playlist SoundCloud (mai prune)"
```

---

### Task 6: Frontend — API client e Settings

**Files:**
- Modify: `frontend/lib/api.ts` (helper `apiPut` vicino ad `apiPatch` ~riga 385; funzioni SoundCloud dopo il blocco playlist ~riga 447)
- Modify: `frontend/app/settings/page.tsx` (card SoundCloud accanto alle card esistenti)

**Interfaces:**
- Consumes: endpoint del task 4.
- Produces (usate dal task 7): `soundcloudStatus()`, `setSoundcloudUsername(username)`, `importSoundcloudPlaylist(url)`, `previewSoundcloudLikes(limit?)`, `importSelectedSoundcloudLikes(trackIds, limit?)`, tipi `SoundCloudStatus` e `SoundCloudLikedTrackPreview`.

- [ ] **Step 1: API client**

In `frontend/lib/api.ts`, accanto ad `apiPatch`:

```ts
export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return handle<T>(await fetch(API + path, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify(body ?? {}) }));
}
```

(Verificare come `apiPatch` costruisce headers/body e replicare identico, cambiando solo il метод: se usa un helper condiviso, usare quello.)

Dopo il blocco delle funzioni playlist (~riga 447):

```ts
// --- SoundCloud ---------------------------------------------------------------

export interface SoundCloudStatus {
  available: boolean;
  ytdlp_version: string | null;
  username: string | null;
}

export function soundcloudStatus() {
  return apiGet<SoundCloudStatus>("/api/soundcloud/status");
}

export function setSoundcloudUsername(username: string) {
  return apiPut<SoundCloudStatus>("/api/soundcloud/config", { username });
}

/** Importa una playlist SoundCloud da URL (pubblica o secret link). Solo metadati. */
export function importSoundcloudPlaylist(url: string) {
  return apiPost<PlaylistImportReport>("/api/soundcloud/import", { url });
}

export interface SoundCloudLikedTrackPreview {
  track_id: string;
  title: string | null;
  artist: string | null;
  duration_seconds: number | null;
  artwork_url: string | null;
  url: string | null;
  already_imported: boolean;
}

/** Anteprima dei like SoundCloud recenti: non importa nulla. */
export function previewSoundcloudLikes(limit = 100) {
  return apiGet<SoundCloudLikedTrackPreview[]>("/api/soundcloud/likes/preview", { limit });
}

/** Importa nella playlist "SoundCloud Likes" solo i brani selezionati (additivo). */
export function importSelectedSoundcloudLikes(trackIds: string[], limit = 100) {
  return apiPost<PlaylistImportReport>("/api/soundcloud/import/likes", { track_ids: trackIds, limit });
}
```

- [ ] **Step 2: Card in Settings**

Leggere `frontend/app/settings/page.tsx` e aggiungere, accanto alle card esistenti (stessa struttura `Card`/`CardHeader` del file), una card SoundCloud autonoma:

```tsx
function SoundCloudCard() {
  const [status, setStatus] = useState<SoundCloudStatus | null>(null);
  const [username, setUsername] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    soundcloudStatus()
      .then((s) => {
        setStatus(s);
        setUsername(s.username ?? "");
      })
      .catch(() => setStatus(null));
  }, []);

  const save = async () => {
    setError(null);
    setSaving(true);
    try {
      setStatus(await setSoundcloudUsername(username.trim()));
    } catch (e) {
      setError(String((e as { message?: string })?.message ?? e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title="SoundCloud"
        subtitle="Username per l'import dei like. Le playlist si importano incollando l'URL."
      />
      <div className="grid gap-3 p-4">
        {status && !status.available && (
          <Alert tone="warning">yt-dlp non disponibile nel backend: l&apos;import SoundCloud non funzionerà.</Alert>
        )}
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        <Field label="Username SoundCloud">
          <div className="flex items-center gap-2">
            <Input
              className="flex-1"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="es. luca-denegri"
              disabled={saving}
            />
            <Button size="sm" onClick={save} disabled={saving || username.trim() === ""}>
              {saving ? <Spinner /> : "Salva"}
            </Button>
          </div>
        </Field>
        {status?.ytdlp_version && (
          <p className="text-xs text-faint">yt-dlp {status.ytdlp_version}</p>
        )}
      </div>
    </Card>
  );
}
```

Import necessari nel file: `soundcloudStatus`, `setSoundcloudUsername`, `type SoundCloudStatus` da `@/lib/api`; verificare che `Card, CardHeader, Button, Alert, Spinner, Input, Field` siano già importati da `@/components/ui` (aggiungere i mancanti). Montare `<SoundCloudCard />` nel punto della pagina dove stanno le altre card di configurazione.

- [ ] **Step 3: Verifica**

Run: `cd frontend && npm run lint && npm run build`
Expected: exit 0, nessun errore

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/app/settings/page.tsx
git commit -m "feat(soundcloud): API client e username SoundCloud in Impostazioni"
```

---

### Task 7: Frontend — pagine import e like

**Files:**
- Create: `frontend/app/playlists/import-soundcloud/page.tsx`
- Create: `frontend/app/playlists/import-soundcloud/likes/page.tsx`
- Modify: `frontend/app/playlists/page.tsx:57-58` (aggiunta link import)

**Interfaces:**
- Consumes: funzioni e tipi del task 6.

- [ ] **Step 1: Pagina import da URL**

Creare `frontend/app/playlists/import-soundcloud/page.tsx` (pattern di `import-manual/page.tsx`):

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, Heart, Settings } from "lucide-react";
import { importSoundcloudPlaylist, soundcloudStatus, type SoundCloudStatus } from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Field } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportSoundcloudPage() {
  const router = useRouter();
  const [status, setStatus] = useState<SoundCloudStatus | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    soundcloudStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const doImport = async () => {
    setError(null);
    setBusy(true);
    try {
      await importSoundcloudPlaylist(url.trim());
      router.push("/playlists");
    } catch (e) {
      setError(`Import fallito: ${err(e)}`);
      setBusy(false);
    }
  };

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>Solo metadati: titolo, artista, durata, link. Nessun audio, mai.</p>
      <p>Per una playlist privata incolla il <span className="text-fg">secret link</span> (Share → Copy link).</p>
      <p>Su SoundCloud l&apos;artista è spesso l&apos;uploader: i titoli &quot;Artista - Titolo&quot; vengono separati in automatico.</p>
    </div>
  );

  return (
    <PageLayout title="Import — SoundCloud" marginaliaTitle="Note" marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Playlist
      </Link>
      <p className="mb-6 text-sm text-muted">
        Incolla l&apos;URL di una playlist SoundCloud: le tracce entrano come lead,
        da arricchire, scaricare e organizzare.
      </p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {status && !status.available && (
        <div className="mb-6">
          <Alert tone="warning">yt-dlp non disponibile nel backend: l&apos;import non funzionerà.</Alert>
        </div>
      )}

      <div className="grid gap-4">
        <Card>
          <CardHeader title="Playlist da URL" subtitle="Pubblica o secret link" />
          <div className="grid gap-3 p-4">
            <Field label="URL playlist">
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://soundcloud.com/utente/sets/nome-playlist"
                disabled={busy}
              />
            </Field>
            <div className="flex justify-end">
              <Button onClick={doImport} disabled={busy || url.trim() === ""}>
                {busy ? <Spinner /> : <Download size={15} />} Importa playlist
              </Button>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="I miei like"
            subtitle={status?.username
              ? `Like recenti di ${status.username}, con selezione`
              : "Configura lo username SoundCloud in Impostazioni"}
            action={status?.username ? (
              <Button size="sm" variant="outline" onClick={() => router.push("/playlists/import-soundcloud/likes")}>
                <Heart size={15} /> Apri
              </Button>
            ) : (
              <Button size="sm" variant="outline" onClick={() => router.push("/settings")}>
                <Settings size={15} /> Impostazioni
              </Button>
            )}
          />
        </Card>
      </div>
    </PageLayout>
  );
}
```

- [ ] **Step 2: Pagina like selettivi**

Creare `frontend/app/playlists/import-soundcloud/likes/page.tsx` (pattern di `import-spotify/liked/page.tsx`, con `track_id` al posto di `spotify_id`):

```tsx
"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, Search } from "lucide-react";
import {
  previewSoundcloudLikes,
  importSelectedSoundcloudLikes,
  fmtDuration,
  type SoundCloudLikedTrackPreview,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportSoundcloudLikesPage() {
  const router = useRouter();
  const [preview, setPreview] = useState<SoundCloudLikedTrackPreview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    previewSoundcloudLikes()
      .then(setPreview)
      .catch((e) => setError(err(e)));
  }, []);

  const alreadyCount = useMemo(
    () => (preview ?? []).filter((t) => t.already_imported).length,
    [preview],
  );

  const filtered = useMemo(() => {
    const rows = preview ?? [];
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(
      (t) =>
        (t.title ?? "").toLowerCase().includes(needle) ||
        (t.artist ?? "").toLowerCase().includes(needle),
    );
  }, [preview, q]);

  const toggle = (id: string) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const selectVisible = () =>
    setSelected((cur) => {
      const next = new Set(cur);
      for (const t of filtered) if (!t.already_imported) next.add(t.track_id);
      return next;
    });

  const doImport = async () => {
    setError(null);
    setImporting(true);
    try {
      await importSelectedSoundcloudLikes([...selected]);
      router.push("/playlists");
    } catch (e) {
      setError(`Import fallito: ${err(e)}`);
      setImporting(false);
    }
  };

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>La playlist <span className="text-fg">SoundCloud Likes</span> cresce solo con i brani che selezioni. L&apos;import è additivo.</p>
      <p>Vengono mostrati gli ultimi 100 like: quelli già importati appaiono spuntati e disabilitati.</p>
    </div>
  );

  return (
    <PageLayout title="Import — Like SoundCloud" marginaliaTitle="Note" marginalia={marginalia}>
      <Link href="/playlists/import-soundcloud" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Import SoundCloud
      </Link>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {!preview && !error && <Loading />}

      {preview && (
        <Card>
          <CardHeader
            title="I tuoi like recenti"
            subtitle={`${preview.length} like · ${alreadyCount} già importati · ${selected.size} selezionati`}
            action={
              <Button size="sm" onClick={doImport} disabled={selected.size === 0 || importing}>
                {importing ? <Spinner /> : <Download size={15} />} Importa selezionati ({selected.size})
              </Button>
            }
          />
          <div className="px-5 py-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <div className="relative min-w-0 flex-1">
                <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                <Input
                  className="h-9 pl-8"
                  placeholder="Filtra per artista o titolo"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
              <Button size="sm" variant="outline" onClick={selectVisible}>Seleziona visibili</Button>
              <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())} disabled={selected.size === 0}>Deseleziona</Button>
            </div>

            {preview.length === 0 && <p className="text-sm text-muted">Nessun like trovato.</p>}
            {preview.length > 0 && filtered.length === 0 && <p className="text-sm text-muted">Nessun brano con questo filtro.</p>}

            <div className="max-h-[32rem] overflow-y-auto">
              <div className="grid gap-1">
                {filtered.map((t) => {
                  const checked = t.already_imported || selected.has(t.track_id);
                  return (
                    <label
                      key={t.track_id}
                      className={`flex items-center gap-3 border border-border px-3 py-2 ${t.already_imported ? "opacity-50" : "cursor-pointer hover:bg-elevated/40"}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={t.already_imported}
                        onChange={() => toggle(t.track_id)}
                        className="h-4 w-4 shrink-0 accent-[var(--color-fg)]"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{t.title ?? <span className="italic text-faint">senza titolo</span>}</div>
                        <div className="truncate text-xs text-faint">{t.artist ?? "—"}</div>
                      </div>
                      <span className="tnum shrink-0 text-xs text-muted">{fmtDuration(t.duration_seconds)}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          </div>
        </Card>
      )}
    </PageLayout>
  );
}
```

- [ ] **Step 3: Link nella pagina Playlists**

In `frontend/app/playlists/page.tsx`, dopo il link a `import-spotify` (~riga 57), aggiungere:

```tsx
<Link href="/playlists/import-soundcloud" className="block"><Button size="sm" variant="outline" className="w-full"><CloudDownload size={15} /> Importa da SoundCloud</Button></Link>
```

Aggiungere `CloudDownload` all'import lucide del file. Aggiornare anche il testo vuoto (~riga 82) citando SoundCloud tra le opzioni.

- [ ] **Step 4: Verifica**

Run: `cd frontend && npm run lint && npm run build`
Expected: exit 0

Poi verifica end-to-end col dev server (backend `uvicorn` + frontend `npm run dev`): pagina `/playlists/import-soundcloud` raggiungibile, card visibili, stato yt-dlp corretto; con backend spento gli errori appaiono come Alert e non come crash.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/playlists/import-soundcloud frontend/app/playlists/page.tsx
git commit -m "feat(soundcloud): pagine import da URL e like selettivi"
```

---

### Task 8: Documentazione

**Files:**
- Modify: `docs/API.md` (sezione endpoint SoundCloud)
- Modify: `docs/ARCHITECTURE.md` (integrazione soundcloud.py tra i provider)
- Modify: `docs/ROADMAP.md` (stato feature)
- Modify: `PROGRESS.md` (voce diario)

- [ ] **Step 1: Aggiornare i doc**

In `docs/API.md` aggiungere la sezione (adattando allo stile del file):

```markdown
## SoundCloud

- `GET /api/soundcloud/status` — yt-dlp disponibile/versione + username configurato.
- `PUT /api/soundcloud/config` — salva lo username (`{"username": "..."}`).
- `POST /api/soundcloud/import` — importa una playlist da URL (pubblica o secret
  link). Solo metadati via yt-dlp; un URL `/likes` risponde 422.
- `GET /api/soundcloud/likes/preview?limit=100` — anteprima like recenti con
  flag `already_imported`.
- `POST /api/soundcloud/import/likes` — importa i like selezionati
  (`{"track_ids": [...], "limit": 100}`) nella playlist di sistema
  "SoundCloud Likes". Additivo.
```

In `docs/ARCHITECTURE.md`: aggiungere `soundcloud.py` all'elenco delle integrazioni con una riga: fetcher yt-dlp solo-metadati per playlist/like (niente ISRC, dedup su platform_track_id + fuzzy; sync sempre additivo). In `docs/ROADMAP.md` e `PROGRESS.md`: registrare la feature secondo lo stile dei file (leggere le voci esistenti prima).

- [ ] **Step 2: Verifica finale completa**

Run: `cd backend && python -m pytest tests` e `cd frontend && npm run lint && npm run build`
Expected: tutto verde

- [ ] **Step 3: Commit**

```bash
git add docs/API.md docs/ARCHITECTURE.md docs/ROADMAP.md PROGRESS.md
git commit -m "docs(soundcloud): endpoint, integrazione e stato roadmap"
```
