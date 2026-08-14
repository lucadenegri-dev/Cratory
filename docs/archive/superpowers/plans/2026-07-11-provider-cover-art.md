# Provider Cover Art — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Durante l'arricchimento da provider, trovare la copertina (Cover Art Archive su match "alta", Discogs su match "testuale") e embeddarla nei tag del file passando per il flusso ISSUES → PLAN → apply.

**Architecture:** Nuovo modulo `cover_art.py` (client CAA + orchestratore) affianca la catena testuale esistente. La thumbnail si cacha su disco alla proposta; la full-res si scarica solo all'apply per le cover accettate. Un nuovo tipo di issue `missing_cover` stagia la proposta in `Issue.suggested_fix_json`; un nuovo `PlanOp` di tipo `COVER` la applica via `tagio.write_cover`; l'undo la rimuove via `tagio.remove_cover`.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, mutagen, httpx; Next.js/React + TypeScript per il frontend.

## Global Constraints

- **Test backend:** girano con `backend/.venv/bin/python` (Python 3.11). MAI col python3 di sistema (3.9, rompe su `X | None`).
- **Ambito cover:** solo file con `has_cover = false`; non si sostituiscono cover esistenti.
- **Fonte:** Cover Art Archive (via release-MBID) solo su confidenza `"high"`; Discogs `cover_image` come fallback su `"text"`. CAA ha precedenza.
- **Timing byte:** thumbnail cachata alla proposta; full-res scaricata all'apply. Download full-res fallito → op **skippata** (non fa fallire il batch).
- **Provider iniettabili:** i client (httpx / CAA / Discogs) devono essere iniettabili per testare senza rete, come già fanno `musicbrainz.py` / `discogs_meta.py`.
- **Nessun Alembic:** niente colonne nuove necessarie; il tipo issue è una stringa, la cache è su disco.
- **Marcatori proposta:** ogni cover proposta porta `source` (`caa`|`discogs`) e `confidence` (`high`|`text`), come le proposte testuali — così il `ConfBadge` "alta"/"testuale" funziona già.

---

### Task 1: Client Cover Art Archive

**Files:**
- Create: `backend/app/integrations/cover_art.py`
- Test: `backend/tests/test_cover_art.py`

**Interfaces:**
- Produces:
  - `class CoverArtError(Exception)`
  - `class CoverArtArchiveClient(http: httpx.Client | None = None)` con `.front_thumb(mbid: str) -> bytes | None` (thumbnail 250px, `None` se 404/errore) e `.front_url(mbid: str) -> str` (URL full-res stabile).
  - `fetch_image(url: str, http: httpx.Client | None = None) -> bytes` — scarica i byte di un'immagine; solleva `CoverArtError` se fallisce (usato all'apply).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cover_art.py
import httpx

from app.integrations import cover_art


class _FakeResp:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class _FakeHttp:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def get(self, url, params=None):
        self.calls.append(url)
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def test_front_thumb_returns_bytes_on_200():
    http = _FakeHttp(_FakeResp(200, b"\xff\xd8jpgbytes"))
    client = cover_art.CoverArtArchiveClient(http=http)
    assert client.front_thumb("REL-MBID") == b"\xff\xd8jpgbytes"
    assert "release/REL-MBID/front-250" in http.calls[0]


def test_front_thumb_none_on_404():
    http = _FakeHttp(_FakeResp(404))
    client = cover_art.CoverArtArchiveClient(http=http)
    assert client.front_thumb("REL-MBID") is None


def test_front_thumb_none_on_transport_error():
    http = _FakeHttp(httpx.ConnectError("boom"))
    client = cover_art.CoverArtArchiveClient(http=http)
    assert client.front_thumb("REL-MBID") is None


def test_front_url_is_stable():
    client = cover_art.CoverArtArchiveClient(http=_FakeHttp(_FakeResp(200)))
    assert client.front_url("REL-MBID").endswith("/release/REL-MBID/front")


def test_fetch_image_returns_bytes():
    http = _FakeHttp(_FakeResp(200, b"IMG"))
    assert cover_art.fetch_image("http://x/y.jpg", http=http) == b"IMG"


def test_fetch_image_raises_on_error():
    http = _FakeHttp(_FakeResp(500))
    try:
        cover_art.fetch_image("http://x/y.jpg", http=http)
        assert False, "attesa CoverArtError"
    except cover_art.CoverArtError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cover_art.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.integrations.cover_art'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/integrations/cover_art.py
"""Cover art dai provider: Cover Art Archive (via release-MBID) + download immagini.
L'orchestratore lookup_cover (Task 3) combina CAA con il fallback Discogs.
http iniettabile → test senza rete, come musicbrainz/discogs_meta."""

import logging

import httpx

from app.integrations._http import get_with_retries

logger = logging.getLogger(__name__)
CAA = "https://coverartarchive.org"
_USER_AGENT = "Sortory/0.1 (+http://localhost)"


class CoverArtError(Exception):
    pass


def _client(http: httpx.Client | None) -> httpx.Client:
    return http or httpx.Client(timeout=15, follow_redirects=True,
                                headers={"User-Agent": _USER_AGENT})


def fetch_image(url: str, http: httpx.Client | None = None) -> bytes:
    """Scarica i byte di un'immagine. Solleva CoverArtError su qualunque errore."""
    cli = _client(http)
    try:
        r = get_with_retries(cli, url, error_cls=CoverArtError)
    except CoverArtError:
        raise
    if r.status_code >= 400:
        raise CoverArtError(f"immagine {r.status_code}: {url}")
    return r.content


class CoverArtArchiveClient:
    def __init__(self, http: httpx.Client | None = None):
        self.http = _client(http)

    def front_thumb(self, mbid: str) -> bytes | None:
        """Thumbnail 250px del fronte per un release-MBID. None se assente/errore."""
        try:
            r = get_with_retries(self.http, f"{CAA}/release/{mbid}/front-250",
                                 error_cls=CoverArtError)
        except CoverArtError as exc:
            logger.warning("CAA thumb %s fallito: %s", mbid, exc)
            return None
        if r.status_code >= 400:
            return None
        return r.content

    def front_url(self, mbid: str) -> str:
        return f"{CAA}/release/{mbid}/front"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cover_art.py -v`
Expected: PASS (6 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/cover_art.py backend/tests/test_cover_art.py
git commit -m "feat(cover): client Cover Art Archive + download immagini"
```

---

### Task 2: Metodo cover su Discogs

**Files:**
- Modify: `backend/app/integrations/discogs_meta.py`
- Test: `backend/tests/test_discogs_cover.py`

**Interfaces:**
- Consumes: `DiscogsMetaClient` esistente (Task 0 del codebase).
- Produces: `DiscogsMetaClient.cover(*, artist, title) -> dict | None` con `{"full_url": str, "thumb_url": str}` dalla miglior release (`cover_image` / `thumb`). `None` se nessun risultato o nessuna immagine.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_discogs_cover.py
from app.integrations.discogs_meta import DiscogsMetaClient


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _Http:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url, params=None):
        return self._resp


def test_cover_extracts_urls():
    resp = _Resp({"results": [
        {"cover_image": "http://img/full.jpg", "thumb": "http://img/thumb.jpg"}]})
    client = DiscogsMetaClient(token=None, http=_Http(resp))
    cov = client.cover(artist="Kai Tracid", title="Tracid Theme")
    assert cov == {"full_url": "http://img/full.jpg", "thumb_url": "http://img/thumb.jpg"}


def test_cover_none_when_no_results():
    client = DiscogsMetaClient(token=None, http=_Http(_Resp({"results": []})))
    assert client.cover(artist="X", title="Y") is None


def test_cover_none_when_no_image():
    resp = _Resp({"results": [{"title": "no image here"}]})
    client = DiscogsMetaClient(token=None, http=_Http(resp))
    assert client.cover(artist="X", title="Y") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_discogs_cover.py -v`
Expected: FAIL con `AttributeError: 'DiscogsMetaClient' object has no attribute 'cover'`

- [ ] **Step 3: Write minimal implementation**

Aggiungi in fondo alla classe `DiscogsMetaClient` in `backend/app/integrations/discogs_meta.py`:

```python
    def cover(self, *, artist: str | None, title: str | None) -> dict[str, Any] | None:
        """Copertina (full + thumb) della miglior release per 'Artista Titolo'.
        None se nessun risultato o nessuna immagine. Match TESTUALE → confidenza 'text'."""
        if not title:
            return None
        q = f"{artist} {title}".strip() if artist else title
        try:
            r = get_with_retries(self.http, f"{BASE}/database/search",
                                 params={"type": "release", "q": q, "per_page": 5},
                                 error_cls=DiscogsError)
        except DiscogsError as exc:
            logger.warning("Discogs cover '%s' fallito: %s", q, exc)
            return None
        if r.status_code >= 400:
            return None
        try:
            results = (r.json() or {}).get("results") or []
        except ValueError:
            return None
        for top in results:
            full = top.get("cover_image")
            thumb = top.get("thumb") or full
            if full:
                return {"full_url": full, "thumb_url": thumb}
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_discogs_cover.py -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/discogs_meta.py backend/tests/test_discogs_cover.py
git commit -m "feat(cover): metodo cover() su Discogs (full + thumb)"
```

---

### Task 3: Orchestratore lookup_cover

**Files:**
- Modify: `backend/app/integrations/cover_art.py`
- Test: `backend/tests/test_cover_lookup.py`

**Interfaces:**
- Consumes: `CoverArtArchiveClient` (Task 1), `DiscogsMetaClient.cover` (Task 2), `fetch_image` (Task 1).
- Produces:
  - `@dataclass CoverResult(thumb_bytes: bytes, full_url: str, source: str, confidence: str)`
  - `lookup_cover(*, release_mbids: list[str], confidence: str | None, artist, title, caa=None, discogs=None, fetch=None) -> CoverResult | None`. CAA solo se `confidence == "high"`; poi fallback Discogs (`text`). `fetch` è iniettabile (default `fetch_image`) per scaricare la thumb Discogs.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cover_lookup.py
from app.integrations import cover_art


class _Caa:
    def __init__(self, thumb):
        self._thumb = thumb
        self.seen = []

    def front_thumb(self, mbid):
        self.seen.append(mbid)
        return self._thumb

    def front_url(self, mbid):
        return f"https://caa/release/{mbid}/front"


class _Discogs:
    def __init__(self, cov):
        self._cov = cov

    def cover(self, *, artist, title):
        return self._cov


def test_caa_used_on_high():
    caa = _Caa(b"CAAJPG")
    res = cover_art.lookup_cover(release_mbids=["R1"], confidence="high",
                                 artist="A", title="T", caa=caa, discogs=_Discogs(None))
    assert res.source == "caa" and res.confidence == "high"
    assert res.thumb_bytes == b"CAAJPG"
    assert res.full_url.endswith("/release/R1/front")


def test_discogs_fallback_on_text():
    caa = _Caa(None)  # non consultato su text comunque
    discogs = _Discogs({"full_url": "http://f.jpg", "thumb_url": "http://t.jpg"})
    res = cover_art.lookup_cover(release_mbids=[], confidence="text",
                                 artist="A", title="T", caa=caa, discogs=discogs,
                                 fetch=lambda url, http=None: b"DGJPG")
    assert res.source == "discogs" and res.confidence == "text"
    assert res.thumb_bytes == b"DGJPG" and res.full_url == "http://f.jpg"


def test_caa_miss_then_discogs_on_high():
    caa = _Caa(None)  # CAA non trova nulla
    discogs = _Discogs({"full_url": "http://f.jpg", "thumb_url": "http://t.jpg"})
    res = cover_art.lookup_cover(release_mbids=["R1"], confidence="high",
                                 artist="A", title="T", caa=caa, discogs=discogs,
                                 fetch=lambda url, http=None: b"DGJPG")
    assert res.source == "discogs"


def test_none_when_nothing_found():
    res = cover_art.lookup_cover(release_mbids=[], confidence="text",
                                 artist="A", title="T", caa=_Caa(None),
                                 discogs=_Discogs(None))
    assert res is None


def test_discogs_download_failure_is_none():
    def _boom(url, http=None):
        raise cover_art.CoverArtError("dead")
    discogs = _Discogs({"full_url": "http://f.jpg", "thumb_url": "http://t.jpg"})
    res = cover_art.lookup_cover(release_mbids=[], confidence="text",
                                 artist="A", title="T", caa=_Caa(None),
                                 discogs=discogs, fetch=_boom)
    assert res is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cover_lookup.py -v`
Expected: FAIL con `AttributeError: module 'app.integrations.cover_art' has no attribute 'lookup_cover'`

- [ ] **Step 3: Write minimal implementation**

Aggiungi in `backend/app/integrations/cover_art.py` (import `dataclass` in testa: `from dataclasses import dataclass`):

```python
@dataclass
class CoverResult:
    thumb_bytes: bytes
    full_url: str
    source: str       # 'caa' | 'discogs'
    confidence: str   # 'high' | 'text'


def lookup_cover(*, release_mbids, confidence, artist, title,
                 caa=None, discogs=None, fetch=None) -> CoverResult | None:
    """CAA (release-MBID) su match 'high'; Discogs cover come fallback (sempre 'text').
    Ritorna None se nessuna immagine trovata o scaricabile."""
    if confidence == "high" and caa is not None:
        for mbid in release_mbids or []:
            thumb = caa.front_thumb(mbid)
            if thumb:
                return CoverResult(thumb, caa.front_url(mbid), "caa", "high")
    if discogs is not None:
        cov = discogs.cover(artist=artist, title=title)
        if cov:
            fetcher = fetch or fetch_image
            try:
                thumb = fetcher(cov.get("thumb_url") or cov.get("full_url"))
            except CoverArtError:
                return None
            if thumb:
                full = cov.get("full_url") or cov.get("thumb_url")
                return CoverResult(thumb, full, "discogs", "text")
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cover_lookup.py -v`
Expected: PASS (5 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/cover_art.py backend/tests/test_cover_lookup.py
git commit -m "feat(cover): orchestratore lookup_cover (CAA high + Discogs fallback)"
```

---

### Task 4: Release-MBID dalla catena testuale

**Files:**
- Modify: `backend/app/integrations/musicbrainz.py`
- Modify: `backend/app/services/text_providers.py`
- Test: `backend/tests/test_resolve_release_mbids.py`

**Interfaces:**
- Consumes: `MusicBrainzProvider.lookup` esistente.
- Produces:
  - `musicbrainz._parse_recording` aggiunge `out["release_mbids"]: list[str]` (release non-VA prima delle VA/compilation).
  - `@dataclass text_providers.ResolvedText(fields: dict, release_mbids: list[str], confidence: str | None)` dove `confidence` è il livello MB (`"high"` se match esatto conf≥95, `"text"` se match testuale, `None` se nessun match MB).
  - `text_providers.resolve(file, *, mb=None, discogs=None) -> ResolvedText`.
  - `text_providers.lookup_with_conf(...)` invariato nel contratto: ora è `resolve(...).fields`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_resolve_release_mbids.py
from types import SimpleNamespace

from app.services import text_providers


class _MB:
    def __init__(self, res):
        self._res = res

    def lookup(self, *, title, artist, isrc=None, mbid=None):
        return self._res


def _file(**kw):
    base = dict(title="T", artist="A", isrc=None, mbid=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_resolve_exposes_release_mbids_and_high_confidence():
    mb = _MB({"canonical_title": "T", "confidence": 95,
              "release_mbids": ["REL-1", "REL-2"]})
    r = text_providers.resolve(_file(), mb=mb, discogs=None)
    assert r.confidence == "high"
    assert r.release_mbids == ["REL-1", "REL-2"]
    assert r.fields["title"][0] == "T"


def test_resolve_text_confidence_when_low_score():
    mb = _MB({"canonical_title": "T", "confidence": 70, "release_mbids": ["REL-1"]})
    r = text_providers.resolve(_file(), mb=mb, discogs=None)
    assert r.confidence == "text"


def test_resolve_none_confidence_without_mb_match():
    r = text_providers.resolve(_file(), mb=_MB(None), discogs=None)
    assert r.confidence is None and r.release_mbids == []


def test_lookup_with_conf_still_returns_fields_only():
    mb = _MB({"canonical_title": "T", "confidence": 95, "release_mbids": ["R"]})
    fields = text_providers.lookup_with_conf(_file(), mb=mb, discogs=None)
    assert fields["title"] == ("T", "high")
    assert "release_mbids" not in fields
```

E per MusicBrainz, aggiungi a `backend/tests/test_musicbrainz.py` (in coda) un test sul parse:

```python
def test_parse_exposes_release_mbids_non_va_first():
    from app.integrations.musicbrainz import MusicBrainzProvider
    mb = MusicBrainzProvider(user_agent="test")
    rec = {
        "id": "REC-1", "title": "T", "score": 100,
        "artist-credit": [{"name": "A"}],
        "releases": [
            {"id": "VA", "artist-credit": [{"name": "Various Artists"}]},
            {"id": "SINGLE", "artist-credit": [{"name": "A"}]},
        ],
    }
    out = mb._parse_recording(rec, isrc=None, exact=True)
    assert out["release_mbids"] == ["SINGLE", "VA"]  # non-VA prima
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_resolve_release_mbids.py tests/test_musicbrainz.py::test_parse_exposes_release_mbids_non_va_first -v`
Expected: FAIL (`resolve` inesistente; `release_mbids` non presente nel parse)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/integrations/musicbrainz.py` aggiungi il metodo statico e la riga nel parse:

```python
    @staticmethod
    def _release_mbids(rec):
        prio, rest = [], []
        for rel in rec.get("releases") or []:
            rid = rel.get("id")
            if not rid:
                continue
            (rest if MusicBrainzProvider._is_va_comp(rel) else prio).append(rid)
        return prio + rest
```

In `_parse_recording`, subito prima di `if not out:`:

```python
        if rels := self._release_mbids(rec):
            out["release_mbids"] = rels
```

In `backend/app/services/text_providers.py`, rifattorizza (import `dataclass` in testa: `from dataclasses import dataclass, field`):

```python
@dataclass
class ResolvedText:
    fields: dict[str, tuple[Any, str]] = field(default_factory=dict)
    release_mbids: list[str] = field(default_factory=list)
    confidence: str | None = None


def resolve(file, *, mb=None, discogs=None) -> ResolvedText:
    """Come lookup_with_conf, ma espone anche i release-MBID e la confidenza MB
    complessiva (per la ricerca cover). fields ha lo stesso contenuto di prima."""
    out: dict[str, tuple[Any, str]] = {}
    release_mbids: list[str] = []
    overall: str | None = None
    mb_res = mb.lookup(title=file.title, artist=file.artist,
                       isrc=(file.isrc.strip() or None) if file.isrc else None,
                       mbid=getattr(file, "mbid", None)) if mb else None
    if mb_res:
        conf = "high" if (mb_res.get("confidence") or 0) >= 95 else "text"
        overall = conf
        release_mbids = mb_res.get("release_mbids") or []
        if mb_res.get("canonical_artist"):
            out["artist"] = (mb_res["canonical_artist"], conf)
        if mb_res.get("canonical_title"):
            out["title"] = (mb_res["canonical_title"], conf)
        if mb_res.get("canonical_album"):
            out["album"] = (mb_res["canonical_album"], conf)
        if mb_res.get("label"):
            out["label"] = (mb_res["label"], conf)
        if mb_res.get("genre_primary") and (g := normalize_genre(mb_res["genre_primary"])) is not None:
            out["genre"] = (g, conf)
        if (y := _year(mb_res.get("release_date"))) is not None:
            out["year"] = (y, conf)

    needs = "label" not in out or "genre" not in out
    if discogs and needs:
        dg_res = discogs.lookup(artist=file.artist, title=file.title)
        if dg_res:
            if "label" not in out and dg_res.get("label"):
                out["label"] = (dg_res["label"], "text")
            if "genre" not in out and dg_res.get("genre_primary") \
                    and (g := normalize_genre(dg_res["genre_primary"])) is not None:
                out["genre"] = (g, "text")
            if "year" not in out and (y := _year(dg_res.get("release_date"))) is not None:
                out["year"] = (y, "text")
    return ResolvedText(fields=out, release_mbids=release_mbids, confidence=overall)


def lookup_with_conf(file, *, mb=None, discogs=None) -> dict[str, tuple[Any, str]]:
    return resolve(file, mb=mb, discogs=discogs).fields
```

Rimuovi il vecchio corpo di `lookup_with_conf` (ora delega a `resolve`). `lookup()` resta invariato (delega già a `lookup_with_conf`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_resolve_release_mbids.py tests/test_musicbrainz.py tests/test_text_providers.py tests/test_text_providers_conf.py -v`
Expected: PASS (nuovi + regressione dei text_providers esistenti verde)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/musicbrainz.py backend/app/services/text_providers.py backend/tests/test_resolve_release_mbids.py backend/tests/test_musicbrainz.py
git commit -m "feat(cover): espone release-MBID e confidenza MB (text_providers.resolve)"
```

---

### Task 5: Cache thumbnail su disco

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/services/cover_cache.py`
- Test: `backend/tests/test_cover_cache.py`

**Interfaces:**
- Produces:
  - `settings.cover_cache_dir: str = "./data/cover_cache"` (env `DJORG_COVER_CACHE_DIR`).
  - `cover_cache.save_thumb(file_id: int, data: bytes) -> str` — scrive `<dir>/<file_id>.jpg`, ritorna il ref relativo `"cover_cache/<file_id>.jpg"`.
  - `cover_cache.thumb_path(file_id: int) -> str` — path assoluto del jpg.
  - `cover_cache.read_thumb(file_id: int) -> bytes | None` — byte o None se assente.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cover_cache.py
from app.services import cover_cache


def test_save_read_roundtrip(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    ref = cover_cache.save_thumb(42, b"\xff\xd8jpg")
    assert ref == "cover_cache/42.jpg"
    assert cover_cache.read_thumb(42) == b"\xff\xd8jpg"


def test_read_missing_is_none(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    assert cover_cache.read_thumb(999) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cover_cache.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.cover_cache'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/core/config.py`, dentro `class Settings`, dopo `musicbrainz_user_agent`:

```python
    # Cache thumbnail delle cover proposte (git-ignored, come ./data).
    cover_cache_dir: str = "./data/cover_cache"
```

Crea `backend/app/services/cover_cache.py`:

```python
"""Cache su disco delle thumbnail cover proposte. Byte fuori dal DB → DB leggero,
servibili come file statico. La full-res NON passa di qui (scaricata all'apply)."""

import os

from app.core.config import settings


def _dir() -> str:
    os.makedirs(settings.cover_cache_dir, exist_ok=True)
    return settings.cover_cache_dir


def thumb_path(file_id: int) -> str:
    return os.path.join(_dir(), f"{file_id}.jpg")


def save_thumb(file_id: int, data: bytes) -> str:
    with open(thumb_path(file_id), "wb") as fh:
        fh.write(data)
    return f"cover_cache/{file_id}.jpg"


def read_thumb(file_id: int) -> bytes | None:
    path = thumb_path(file_id)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cover_cache.py -v`
Expected: PASS (2 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/services/cover_cache.py backend/tests/test_cover_cache.py
git commit -m "feat(cover): cache su disco delle thumbnail proposte"
```

---

### Task 6: write_cover / remove_cover in tagio

**Files:**
- Modify: `backend/app/integrations/tagio.py`
- Test: `backend/tests/test_tagio_cover.py`

**Interfaces:**
- Consumes: `_detect_cover` esistente (per i round-trip di test).
- Produces:
  - `tagio.write_cover(path: str, data: bytes, mime: str = "image/jpeg") -> None` — embed cover (FLAC `Picture`, ID3 `APIC` per mp3/wav/aiff, MP4 `covr`). Solleva `TagWriteError` su errore.
  - `tagio.remove_cover(path: str) -> None` — rimuove ogni cover embeddata.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tagio_cover.py
import pytest

from app.integrations import tagio

# JPEG minimale valido (header + EOI); mutagen non lo valida, basta come payload.
_JPG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff"])
def test_write_then_detect_cover(copy_fixture, tmp_path, fmt):
    f = copy_fixture(fmt, tmp_path / f"a.{fmt}")
    assert tagio.read_tags(f).has_cover is False
    tagio.write_cover(f, _JPG)
    assert tagio.read_tags(f).has_cover is True


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff"])
def test_remove_cover(copy_fixture, tmp_path, fmt):
    f = copy_fixture(fmt, tmp_path / f"a.{fmt}")
    tagio.write_cover(f, _JPG)
    assert tagio.read_tags(f).has_cover is True
    tagio.remove_cover(f)
    assert tagio.read_tags(f).has_cover is False


def test_write_cover_preserves_text_tags(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_tags(f, {"artist": "Pinco", "title": "Titolo"})
    tagio.write_cover(f, _JPG)
    tags = tagio.read_tags(f)
    assert tags.artist == "Pinco" and tags.title == "Titolo" and tags.has_cover
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_tagio_cover.py -v`
Expected: FAIL con `AttributeError: module 'app.integrations.tagio' has no attribute 'write_cover'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/integrations/tagio.py`, aggiungi agli import in testa:

```python
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC
from mutagen.mp4 import MP4, MP4Cover
```

E aggiungi le funzioni (dopo `write_tags`):

```python
def write_cover(path: str, data: bytes, mime: str = "image/jpeg") -> None:
    """Embed della cover (type 3 = front). FLAC Picture, ID3 APIC (mp3/wav/aiff),
    MP4 covr. Sostituisce eventuali cover esistenti."""
    try:
        raw = MutagenFile(path)
        if raw is None:
            raise TagWriteError(f"formato non scrivibile: {path}")
        if isinstance(raw, FLAC):
            pic = Picture()
            pic.type = 3
            pic.mime = mime
            pic.data = data
            raw.clear_pictures()
            raw.add_picture(pic)
        elif isinstance(raw, MP4):
            fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            raw["covr"] = [MP4Cover(data, imageformat=fmt)]
        else:  # ID3-based: mp3, wav, aiff
            if raw.tags is None:
                raw.add_tags()
            raw.tags.delall("APIC")
            raw.tags.add(APIC(encoding=3, mime=mime, type=3, desc="", data=data))
        raw.save()
    except MutagenError as exc:
        raise TagWriteError(str(exc)) from exc


def remove_cover(path: str) -> None:
    """Rimuove ogni cover embeddata (usato dall'undo)."""
    try:
        raw = MutagenFile(path)
        if raw is None:
            return
        if isinstance(raw, FLAC):
            raw.clear_pictures()
        elif isinstance(raw, MP4):
            if "covr" in raw:
                del raw["covr"]
        elif raw.tags is not None and hasattr(raw.tags, "delall"):
            raw.tags.delall("APIC")
        raw.save()
    except MutagenError as exc:
        raise TagWriteError(str(exc)) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_tagio_cover.py -v`
Expected: PASS (9 test: 4+4 parametrizzati + 1)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/tagio.py backend/tests/test_tagio_cover.py
git commit -m "feat(cover): write_cover/remove_cover (FLAC/MP3/M4A/AIFF)"
```

---

### Task 7: provider-suggest cerca cover + endpoint thumbnail

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/issues.py`
- Test: `backend/tests/test_provider_cover_api.py`

**Interfaces:**
- Consumes: `text_providers.resolve` (Task 4), `cover_art.lookup_cover` + `CoverArtArchiveClient` (Task 1/3), `DiscogsMetaClient.cover` (Task 2), `cover_cache.save_thumb/read_thumb` (Task 5).
- Produces:
  - `schemas.ProviderSuggestBody(covers: bool = True)`.
  - `POST /api/issues/provider-suggest` accetta il body opzionale; crea/aggiorna issue `missing_cover` (field `"cover"`, severity `"info"`) con `suggested_fix_json = {"field":"cover","source":..,"confidence":..,"full_url":..,"thumb_ref":..}` per i file **con `has_cover = false`** tra quelli risolti in questa passata. Risposta con nuovo contatore `"covers"`.
  - `GET /api/issues/cover-thumb/{file_id}` → `image/jpeg` (404 se assente).

Il flusso interno riusa la lookup MB già fatta (nessuna chiamata MB extra per la cover): `_lookup` passa a `resolve()` e mette in cache la `ResolvedText`; il testo usa `.fields`, la cover usa `.release_mbids` + `.confidence`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_provider_cover_api.py
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db, has_cover=False):
    root = ScanRoot(path="/music")
    db.add(root)
    db.flush()
    f = AudioFile(root_id=root.id, path="/music/a.flac", ext="flac", size_bytes=1,
                  hash_method="full", artist="A", title="T", has_cover=has_cover,
                  status="present")
    db.add(f)
    db.flush()
    # una issue testuale aperta → il file entra nella passata provider
    db.add(Issue(file_id=f.id, type="missing_metadata", field="genre",
                 severity="info", detail="genere mancante", status="open"))
    db.commit()
    return f.id


class _Resolved:
    fields = {}
    release_mbids = ["REL-1"]
    confidence = "high"


def test_provider_suggest_creates_missing_cover_issue(db, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    fid = _seed(db)
    fake_cover = __import__("app.integrations.cover_art", fromlist=["CoverResult"]).CoverResult(
        thumb_bytes=b"\xff\xd8T", full_url="http://f.jpg", source="caa", confidence="high")
    with patch("app.routers.issues.text_providers.resolve", return_value=_Resolved()), \
         patch("app.routers.issues.acoustid.acoustid_configured", return_value=False), \
         patch("app.integrations.cover_art.lookup_cover", return_value=fake_cover):
        r = client.post("/api/issues/provider-suggest", json={"covers": True})
    assert r.status_code == 200
    assert r.json()["covers"] == 1
    iss = db.query(Issue).filter(Issue.type == "missing_cover").one()
    assert iss.field == "cover"
    assert iss.suggested_fix_json["source"] == "caa"
    assert iss.suggested_fix_json["confidence"] == "high"
    assert iss.suggested_fix_json["thumb_ref"] == f"cover_cache/{fid}.jpg"


def test_cover_thumb_endpoint_serves_bytes(db, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.services import cover_cache
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    cover_cache.save_thumb(7, b"\xff\xd8IMG")
    r = client.get("/api/issues/cover-thumb/7")
    assert r.status_code == 200 and r.content == b"\xff\xd8IMG"
    assert r.headers["content-type"].startswith("image/jpeg")


def test_cover_thumb_404_when_missing(db, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    assert client.get("/api/issues/cover-thumb/12345").status_code == 404


def test_covers_skipped_when_flag_false(db, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cover_cache_dir", str(tmp_path / "cc"))
    _seed(db)
    with patch("app.routers.issues.text_providers.resolve", return_value=_Resolved()), \
         patch("app.routers.issues.acoustid.acoustid_configured", return_value=False):
        r = client.post("/api/issues/provider-suggest", json={"covers": False})
    assert r.json()["covers"] == 0
    assert db.query(Issue).filter(Issue.type == "missing_cover").count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_provider_cover_api.py -v`
Expected: FAIL (body `covers` non gestito, nessuna issue `missing_cover`, endpoint thumb 404 non definito)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas.py`, dopo `IssueFixBody`:

```python
class ProviderSuggestBody(BaseModel):
    covers: bool = True
```

In `backend/app/routers/issues.py`:

1. Import in testa:
```python
from fastapi.responses import Response
from app.integrations import acoustid, cover_art
from app.services import cover_cache
```
(Nota: `acoustid` era importato dentro la funzione; portalo pure in testa oppure lascialo locale ma assicurati che `app.routers.issues.acoustid` esista per il patch del test — importalo in testa.)

2. Aggiorna la firma e la logica di `provider_suggest`:
```python
@router.post("/provider-suggest", response_model=dict)
def provider_suggest(body: ProviderSuggestBody | None = None, db: Session = Depends(get_db)):
    from app.integrations.discogs_meta import DiscogsMetaClient
    from app.integrations.musicbrainz import MusicBrainzProvider
    from app.services.fingerprint import fingerprint_one

    want_covers = (body or ProviderSuggestBody()).covers
    mb = MusicBrainzProvider(user_agent=settings.musicbrainz_user_agent)
    discogs = DiscogsMetaClient()
    caa = cover_art.CoverArtArchiveClient() if want_covers else None
    ac_client = None
    if acoustid.acoustid_configured() and acoustid.fpcalc_available():
        try:
            ac_client = acoustid.get_acoustid_client()
        except acoustid.AcoustIDError:
            ac_client = None

    rows = db.execute(
        select(Issue, AudioFile).join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.type.in_(_PROVIDER_TYPES),
               Issue.field.in_(_PROVIDER_FIELDS))
    ).all()
    todo = [(i, f) for i, f in rows
            if i.suggested_fix_json is None
            or i.suggested_fix_json.get("source") != "provider"]
    if not todo:
        return {"configured": True, "acoustid_available": ac_client is not None,
                "files": 0, "suggested": 0, "unresolved": 0, "fingerprinted": 0,
                "covers": 0}

    cache: dict[int, "text_providers.ResolvedText"] = {}
    files_by_id: dict[int, AudioFile] = {}
    fingerprinted = 0

    def _lookup(f: AudioFile):
        nonlocal fingerprinted
        files_by_id[f.id] = f
        if f.id not in cache:
            if not f.mbid and ac_client is not None and fingerprint_one(f, ac_client):
                fingerprinted += 1
            cache[f.id] = text_providers.resolve(f, mb=mb, discogs=discogs)
        return cache[f.id]

    suggested = unresolved = 0
    files_seen: set[int] = set()
    for issue, f in todo:
        files_seen.add(f.id)
        res = _lookup(f)
        pair = res.fields.get(issue.field)
        if pair is not None:
            value, conf = pair
            issue.suggested_fix_json = {"field": issue.field, "action": "retag",
                                        "to": str(value), "source": "provider",
                                        "confidence": conf}
            issue.updated_at = utcnow()
            suggested += 1
        else:
            unresolved += 1

    covers = 0
    if want_covers:
        for fid, res in cache.items():
            f = files_by_id[fid]
            if f.has_cover:
                continue
            cover = cover_art.lookup_cover(
                release_mbids=res.release_mbids, confidence=res.confidence,
                artist=f.artist, title=f.title, caa=caa, discogs=discogs)
            if cover is None:
                continue
            ref = cover_cache.save_thumb(fid, cover.thumb_bytes)
            _upsert_cover_issue(db, fid, cover, ref)
            covers += 1

    db.commit()
    return {"configured": True, "acoustid_available": ac_client is not None,
            "files": len(files_seen), "suggested": suggested,
            "unresolved": unresolved, "fingerprinted": fingerprinted, "covers": covers}
```

3. Aggiungi l'helper di upsert (sopra `provider_suggest`) e l'endpoint thumb:
```python
def _upsert_cover_issue(db: Session, file_id: int, cover, thumb_ref: str) -> None:
    """Crea/aggiorna l'issue missing_cover. Non tocca le proposte già accettate."""
    issue = db.scalar(select(Issue).where(
        Issue.file_id == file_id, Issue.type == "missing_cover", Issue.field == "cover"))
    if issue is not None and issue.status == "accepted":
        return
    if issue is None:
        issue = Issue(file_id=file_id, type="missing_cover", field="cover",
                      severity="info", detail="copertina mancante", status="open")
        db.add(issue)
    issue.suggested_fix_json = {"field": "cover", "source": cover.source,
                                "confidence": cover.confidence,
                                "full_url": cover.full_url, "thumb_ref": thumb_ref}
    issue.status = "open"
    issue.updated_at = utcnow()


@router.get("/cover-thumb/{file_id}")
def cover_thumb(file_id: int):
    data = cover_cache.read_thumb(file_id)
    if data is None:
        raise HTTPException(status_code=404, detail="nessuna thumbnail")
    return Response(content=data, media_type="image/jpeg")
```

4. Aggiorna gli import degli schemi in testa al file:
```python
from app.schemas import (IssueBulkBody, IssueFixBody, IssueRead, IssueStatusBody,
                         ProviderRescanBody, ProviderSuggestBody)
```

E rimuovi il vecchio `from app.integrations import acoustid` locale dentro la funzione (ora è in testa).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_provider_cover_api.py tests/test_provider_suggest_api.py -v`
Expected: PASS (nuovi + regressione provider_suggest esistente verde)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/issues.py backend/tests/test_provider_cover_api.py
git commit -m "feat(cover): provider-suggest cerca cover + endpoint thumbnail"
```

---

### Task 8: Planner emette op COVER

**Files:**
- Modify: `backend/app/services/planner.py`
- Test: `backend/tests/test_planner_cover.py`

**Interfaces:**
- Consumes: `accepted_issues` (include le `missing_cover` accettate), `PlanOpComputed`.
- Produces: `build_plan` emette `PlanOpComputed("COVER", file_id, {"has_cover": False}, {"full_url": .., "source": .., "confidence": ..})` per ogni issue `missing_cover` accettata su file presente, non in `removals`, con `has_cover = False`. Ordine di ritorno: `retag_ops + cover_ops + move_ops + del_ops`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_planner_cover.py
from types import SimpleNamespace

from app.services.planner import build_plan


def _file(fid, has_cover=False):
    return SimpleNamespace(
        id=fid, root_id=1, path=f"/music/{fid}.flac", ext="flac",
        artist="A", title="T", album=None, album_artist=None, genre="House",
        year=None, label=None, track_no=None, comment=None, has_cover=has_cover)


def _cover_issue(fid, status="accepted"):
    return SimpleNamespace(
        file_id=fid, type="missing_cover", field="cover", status=status,
        suggested_fix_json={"field": "cover", "source": "caa", "confidence": "high",
                            "full_url": "http://f.jpg", "thumb_ref": f"cover_cache/{fid}.jpg"})


_SNAP = {"naming_template": "{artist} - {title}", "folder_template": ""}


def test_cover_op_emitted_for_accepted_missing_cover():
    files = [_file(1, has_cover=False)]
    ops = build_plan(files, [_cover_issue(1)], set(), _SNAP, {1: "/music"})
    cover = [o for o in ops if o.kind == "COVER"]
    assert len(cover) == 1
    assert cover[0].file_id == 1
    assert cover[0].after["full_url"] == "http://f.jpg"
    assert cover[0].after["source"] == "caa"


def test_no_cover_op_when_file_already_has_cover():
    files = [_file(1, has_cover=True)]
    ops = build_plan(files, [_cover_issue(1)], set(), _SNAP, {1: "/music"})
    assert [o for o in ops if o.kind == "COVER"] == []


def test_no_cover_op_when_file_in_removals():
    files = [_file(1, has_cover=False)]
    ops = build_plan(files, [_cover_issue(1)], {1}, _SNAP, {1: "/music"})
    assert [o for o in ops if o.kind == "COVER"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_planner_cover.py -v`
Expected: FAIL (nessun op COVER emesso)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/planner.py`, dentro `build_plan`, aggiungi `files_by_id` in testa alla funzione e la costruzione dei `cover_ops`, poi modifica il return:

```python
def build_plan(files, accepted_issues, removals, settings_snapshot,
               root_targets) -> list[PlanOpComputed]:
    removals = set(removals)
    by_file = fixes_by_file(accepted_issues)
    files_by_id = {f.id: f for f in files}
    retag_ops: list[PlanOpComputed] = []
    move_ops: list[PlanOpComputed] = []
    del_ops: list[PlanOpComputed] = []

    # ... (corpo esistente del for invariato) ...

    cover_ops: list[PlanOpComputed] = []
    for issue in accepted_issues:
        if issue.type != "missing_cover" or not issue.suggested_fix_json:
            continue
        f = files_by_id.get(issue.file_id)
        if f is None or f.id in removals or f.has_cover:
            continue
        fix = issue.suggested_fix_json
        cover_ops.append(PlanOpComputed(
            "COVER", f.id, {"has_cover": False},
            {"full_url": fix.get("full_url"), "source": fix.get("source"),
             "confidence": fix.get("confidence")}))

    return retag_ops + cover_ops + move_ops + del_ops
```

(Mantieni identico il `for f in sorted(files, ...)` esistente; aggiungi solo `files_by_id`, il blocco `cover_ops` e il nuovo `return`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_planner_cover.py tests/test_planner.py -v`
Expected: PASS (nuovi + regressione planner esistente verde)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/planner.py backend/tests/test_planner_cover.py
git commit -m "feat(cover): planner emette op COVER per le cover accettate"
```

---

### Task 9: Apply e Undo dell'op COVER

**Files:**
- Modify: `backend/app/services/apply.py`
- Modify: `backend/app/services/undo.py`
- Modify: `backend/app/schemas.py` (PlanStats.n_cover)
- Modify: `backend/app/services/planning.py` (conteggio n_cover)
- Test: `backend/tests/test_apply_cover.py`

**Interfaces:**
- Consumes: `cover_art.fetch_image` (Task 1), `tagio.write_cover`/`remove_cover` (Task 6), op `COVER` dal planner (Task 8).
- Produces:
  - `apply.apply_plan` esegue gli op `COVER` (tra i RETAG e i MOVE): scarica `after_json["full_url"]`, embed via `write_cover`, imposta `file.has_cover = True`, journala kind `COVER` (prior = nessuna cover). Download fallito → op `status="skipped"`, conteggiato in `skipped_ops`, batch prosegue.
  - `undo.undo_run` gestisce kind `COVER`: `tagio.remove_cover(from_path)` se il file esiste.
  - `schemas.PlanStats.n_cover: int = 0`; `planning.load_plan` popola `n_cover`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_apply_cover.py
from unittest.mock import patch

from app.integrations import tagio
from app.models import AudioFile, Plan, PlanOp, ScanRoot, UndoJournal
from app.services import apply as apply_svc
from app.services import undo as undo_svc

_JPG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


def _seed_cover_plan(db, copy_fixture, tmp_path):
    root = ScanRoot(path=str(tmp_path))
    db.add(root)
    db.flush()
    fpath = copy_fixture("flac", tmp_path / "a.flac")
    f = AudioFile(root_id=root.id, path=fpath, ext="flac", size_bytes=1,
                  hash_method="full", artist="A", title="T", has_cover=False,
                  status="present")
    db.add(f)
    db.flush()
    plan = Plan(status="draft", rules_json={
        "naming_template": "{artist} - {title}", "folder_template": "", "targets": {}})
    db.add(plan)
    db.flush()
    db.add(PlanOp(plan_id=plan.id, seq=0, kind="COVER", file_id=f.id,
                  before_json={"has_cover": False},
                  after_json={"full_url": "http://f.jpg", "source": "caa",
                              "confidence": "high"}, status="pending"))
    db.commit()
    return plan, f, fpath


def test_apply_cover_embeds_and_sets_flag(db, copy_fixture, tmp_path):
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    with patch("app.services.apply.cover_art.fetch_image", return_value=_JPG):
        res = apply_svc.apply_plan(db, plan)
    assert res.applied_ops == 1
    assert tagio.read_tags(fpath).has_cover is True
    db.refresh(f)
    assert f.has_cover is True


def test_apply_cover_skips_on_download_failure(db, copy_fixture, tmp_path):
    from app.integrations.cover_art import CoverArtError
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    with patch("app.services.apply.cover_art.fetch_image", side_effect=CoverArtError("dead")):
        res = apply_svc.apply_plan(db, plan)
    assert res.applied_ops == 0
    assert res.skipped_ops == 1
    assert tagio.read_tags(fpath).has_cover is False


def test_undo_cover_removes_embedded_art(db, copy_fixture, tmp_path):
    plan, f, fpath = _seed_cover_plan(db, copy_fixture, tmp_path)
    with patch("app.services.apply.cover_art.fetch_image", return_value=_JPG):
        apply_svc.apply_plan(db, plan)
    assert tagio.read_tags(fpath).has_cover is True
    undo_svc.undo_run(db, plan)
    assert tagio.read_tags(fpath).has_cover is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_apply_cover.py -v`
Expected: FAIL (op COVER non gestito nell'apply)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/apply.py`:

1. Import in testa: `from app.integrations import cover_art, fsops, tagio`.

2. Aggiungi il partizionamento e il loop COVER (dopo `retag_ops`/`move_ops`/`del_ops`, e un contatore skip):
```python
    retag_ops = [o for o in ops if o.kind == "RETAG"]
    cover_ops = [o for o in ops if o.kind == "COVER"]
    move_ops = [o for o in ops if o.kind in ("RENAME", "MOVE")]
    del_ops = [o for o in ops if o.kind == "DELETE"]
```
E un contatore prima del `try:`:
```python
    cover_skipped = 0
```

3. Dentro il `try:`, subito dopo il loop `for o in retag_ops:` e prima di `for o in move_ops:`:
```python
        for o in cover_ops:
            current["seq"] = o.seq
            f = files[o.file_id]
            try:
                data = cover_art.fetch_image(o.after_json["full_url"])
            except cover_art.CoverArtError:
                o.status = "skipped"
                db.commit()
                cover_skipped += 1
                continue
            _journal("COVER", o.file_id, from_path=f.path)   # prior = nessuna cover
            tagio.write_cover(f.path, data)
            f.has_cover = True
            o.status = "applied"
            db.commit()
            _progress()
```

4. Somma `cover_skipped` a `skipped_ops` in TUTTI i return di `apply_plan` (i tre: stale, partial nel `except`, finale). Es. finale:
```python
    return ApplyResult(run_id=plan.id, applied_ops=state["applied"],
                       skipped_ops=len(skipped) + cover_skipped,
                       started_at=started, finished_at=utcnow())
```
(Applica la stessa somma `len(skipped) + cover_skipped` anche nel return `stale` e nel return del blocco `except`.)

In `backend/app/services/undo.py`, dentro il `for r in rows:` aggiungi il ramo prima dell'`else`:
```python
            elif r.kind == "COVER":
                if os.path.exists(r.from_path):
                    tagio.remove_cover(r.from_path)
```

In `backend/app/schemas.py`, in `class PlanStats` aggiungi:
```python
    n_cover: int = 0
```

In `backend/app/services/planning.py`, in `load_plan`:
- inizializza i counts includendo COVER:
```python
    counts = {"RETAG": 0, "COVER": 0, "RENAME": 0, "MOVE": 0, "DELETE": 0}
```
- passa `n_cover` a `PlanStats`:
```python
    stats = PlanStats(n_retag=counts["RETAG"], n_cover=counts["COVER"],
                      n_rename=counts["RENAME"], n_move=counts["MOVE"],
                      n_delete=counts["DELETE"], space_freed_bytes=space,
                      n_conflicts=len(conflicts), n_skipped=n_skipped,
                      blocking=len(ops) > 0 and n_skipped == len(ops))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_apply_cover.py tests/test_apply_exec.py tests/test_apply_undo_invariant.py tests/test_undo.py tests/test_planning.py -v`
Expected: PASS (nuovi + regressione apply/undo/planning esistente verde)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/apply.py backend/app/services/undo.py backend/app/schemas.py backend/app/services/planning.py backend/tests/test_apply_cover.py
git commit -m "feat(cover): apply embedda la cover (skip su download fallito) + undo la rimuove"
```

---

### Task 10: Frontend — anteprima cover nella ISSUES table

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/issues-table.tsx`
- Modify: `frontend/app/issues/page.tsx`

**Interfaces:**
- Consumes: endpoint `GET /api/issues/cover-thumb/{file_id}` (Task 7), campo `covers` nella risposta provider-suggest (Task 7).
- Produces:
  - `coverThumbUrl(fileId: number): string` in `lib/api.ts`.
  - `ProviderSuggestResult.covers: number`; `providerSuggest(covers = true)` invia `{covers}` nel body.
  - `IssuesTable`/`IssueRow` accettano `onAccept(id: number): Promise<void>` e, per le righe `type === "missing_cover"`, mostrano la thumbnail (click → ingrandimento) + `✓ accetta` (usa `onAccept`) / `✕ ignora`.
  - `issues/page.tsx` definisce `onAccept` (= `setIssueStatus(id, "accepted")`), lo passa alla tabella, e mostra i `covers` nella nota provider.

- [ ] **Step 1: Aggiorna `lib/api.ts`**

Aggiungi l'helper URL (in fondo alla sezione ISSUES, vicino a `providerSuggest`):
```typescript
export function coverThumbUrl(fileId: number): string {
  return `${API}/api/issues/cover-thumb/${fileId}`;
}
```

Estendi il tipo e la funzione provider-suggest:
```typescript
export interface ProviderSuggestResult {
  configured: boolean;
  acoustid_available: boolean;
  files: number;
  suggested: number;
  unresolved: number;
  fingerprinted: number;
  covers: number;
}
export function providerSuggest(covers = true) {
  return apiSend<ProviderSuggestResult>("POST", "/api/issues/provider-suggest", { covers });
}
```

- [ ] **Step 2: Aggiorna `components/issues-table.tsx`**

Importa l'helper URL e `useState` (già presente). In testa:
```typescript
import { coverThumbUrl, type Issue } from "@/lib/api";
```
Aggiungi `onAccept` alla firma di `IssueRow` e `IssuesTable`, e rendi la cella "Correzione" e "Azioni" consapevoli del tipo cover.

In `IssueRow`, aggiungi in cima al componente:
```typescript
  const isCover = issue.type === "missing_cover";
  const [zoom, setZoom] = useState(false);
```

Sostituisci il contenuto della cella "Correzione" (`<td className="px-3 py-2">…`) aggiungendo il ramo cover PRIMA del ramo `fixable` esistente:
```tsx
      <td className="px-3 py-2">
        {isCover ? (
          issue.status === "dismissed" ? (
            <span className="text-faint">copertina · non applicata</span>
          ) : (
            <button type="button" onClick={() => setZoom(true)}
              className="block h-11 w-11 overflow-hidden border border-border hover:border-border-strong"
              title="ingrandisci">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={coverThumbUrl(issue.file_id)} alt="cover"
                   className="h-full w-full object-cover" />
            </button>
          )
        ) : issue.status === "open" ? (
          fixable ? (
            /* …blocco input esistente invariato… */
          ) : (
            <span className="text-faint">— non correggibile</span>
          )
        ) : issue.status === "accepted" ? (
          <span className="text-fg">{suggested || "—"}</span>
        ) : (
          <span className="text-faint" title="ignorata: il tag resta invariato">
            {issue.current_value ? `${issue.current_value} · invariato` : "—"}
          </span>
        )}
      </td>
```

Nella cella "Azioni", per le cover aperte l'accetta usa `onAccept` (non `onFix`, che richiede un valore). Sostituisci il ramo `issue.status === "open"`:
```tsx
        {issue.status === "open" ? (
          <span className="flex gap-1">
            {isCover ? (
              <button disabled={busy}
                onClick={() => run(() => onAccept(issue.id))}
                className="border border-border px-2 py-0.5 text-[10px] text-ok hover:bg-elevated disabled:opacity-40"
              >✓ accetta</button>
            ) : fixable && (
              <button
                disabled={busy || !value.trim()}
                onClick={() => run(() => onFix(issue.id, value.trim()))}
                className="border border-border px-2 py-0.5 text-[10px] text-ok hover:bg-elevated disabled:opacity-40"
              >✓ accetta</button>
            )}
            <button disabled={busy} onClick={() => run(() => onDismiss(issue.id))}
              className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
            >✕ ignora</button>
          </span>
        ) : ( /* …ramo non-open invariato… */ )}
```

Aggiungi il lightbox in fondo al `return` di `IssueRow`, dopo la `</tr>` non è valido; invece rendi lo zoom come overlay fixed dentro l'ultima cella. Metti subito prima della chiusura dell'ultima `</td>` delle Azioni, oppure — più semplice — aggiungi un frammento accanto alla riga usando un portale-less overlay dentro la cella cover. Implementazione semplice: dentro la cella "Correzione", dopo il `<button>` della thumbnail, aggiungi:
```tsx
        {zoom && (
          <div onClick={() => setZoom(false)}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-8">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={coverThumbUrl(issue.file_id)} alt="cover"
                 className="max-h-[80vh] max-w-[80vw] border border-border" />
          </div>
        )}
```

Aggiorna le firme:
```tsx
function IssueRow({ issue, onFix, onAccept, onDismiss, onReopen }: {
  issue: Issue;
  onFix: (id: number, value: string) => Promise<void>;
  onAccept: (id: number) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
}) { … }

export function IssuesTable({ issues, onFix, onAccept, onDismiss, onReopen }: {
  issues: Issue[];
  onFix: (id: number, value: string) => Promise<void>;
  onAccept: (id: number) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
}) { … <IssueRow key={…} issue={i} onFix={onFix} onAccept={onAccept} onDismiss={onDismiss} onReopen={onReopen} /> … }
```

- [ ] **Step 3: Aggiorna `app/issues/page.tsx`**

Aggiungi il callback e passalo alla tabella:
```tsx
  const onAccept = (id: number) => act(() => setIssueStatus(id, "accepted"));
```
```tsx
  <IssuesTable issues={filtered} onFix={onFix} onAccept={onAccept} onDismiss={onDismiss} onReopen={onReopen} />
```
Nella nota di `onProviderSuggest`, includi le cover:
```tsx
        setAiNote(
          `${r.suggested} suggerimenti da provider${r.covers > 0 ? `, ${r.covers} copertine trovate` : ""}${r.fingerprinted > 0 ? ` (${r.fingerprinted} via fingerprint)` : ""}${r.unresolved > 0 ? `, ${r.unresolved} non trovati` : ""}${r.acoustid_available ? "" : " — fingerprint off, solo match testuale"} — rivedi e accetta col ✓.`,
        );
```

- [ ] **Step 4: Verifica build/type-check frontend**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: nessun errore TypeScript/lint.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/components/issues-table.tsx frontend/app/issues/page.tsx
git commit -m "feat(cover): anteprima thumbnail + accetta cover nella ISSUES table"
```

---

### Task 11: Frontend — gruppo COVER nel PLAN

**Files:**
- Modify: `frontend/lib/api.ts` (PlanStats.n_cover)
- Modify: `frontend/components/plan-ops.tsx`

**Interfaces:**
- Consumes: op con `kind === "COVER"` dal piano (Task 9), `coverThumbUrl` (Task 10).
- Produces: gruppo "Copertina" in `PlanOps` con miniatura per riconoscere l'op; `PlanStats.n_cover` nel tipo TS.

- [ ] **Step 1: Aggiorna `lib/api.ts`**

In `interface PlanStats` aggiungi:
```typescript
  n_cover: number;
```

- [ ] **Step 2: Aggiorna `components/plan-ops.tsx`**

Importa l'helper:
```typescript
import { coverThumbUrl, type PlanOp } from "@/lib/api";
```
Aggiungi il gruppo COVER (dopo RETAG):
```typescript
const GROUPS: { kind: string; label: string }[] = [
  { kind: "RETAG", label: "Retag" },
  { kind: "COVER", label: "Copertina" },
  { kind: "RENAME", label: "Rinomina" },
  { kind: "MOVE", label: "Sposta" },
  { kind: "DELETE", label: "Elimina" },
];
```
In `OpRow`, gestisci il rendering cover. Aggiungi un ramo prima degli altri nel blocco `<span className="text-[11px]">`:
```tsx
      <span className="flex items-center gap-2 text-[11px]">
        {op.kind === "COVER" ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={coverThumbUrl(op.file_id)} alt="cover"
                 className="h-8 w-8 border border-border object-cover" />
            <span className="text-fg-strong">embed copertina</span>
            <span className="text-faint">({String(op.after.source ?? "")})</span>
          </>
        ) : op.kind === "RETAG" ? (
          /* …blocco RETAG esistente… */
        ) : isDelete ? (
          /* …blocco DELETE esistente… */
        ) : (
          /* …blocco MOVE/RENAME esistente… */
        )}
      </span>
```
(Il contenitore esterno `<span>` diventa `flex items-center gap-2`; gli altri rami restano invariati.)

- [ ] **Step 3: Verifica build/type-check frontend**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: nessun errore.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/components/plan-ops.tsx
git commit -m "feat(cover): gruppo Copertina nel PLAN con miniatura"
```

---

### Task 12: Suite completa + verifica end-to-end

**Files:** nessuna modifica (gate di verifica).

- [ ] **Step 1: Suite backend completa**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: tutti verdi (197 preesistenti + i nuovi).

- [ ] **Step 2: Type-check + lint frontend**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: nessun errore.

- [ ] **Step 3: Smoke test end-to-end (manuale, guidato)**

Avvia backend + frontend, poi su una traccia senza cover ma identificata:
1. ISSUES → "Importa metadati mancanti da Provider" → compare la thumbnail nella riga `missing_cover` con badge "alta"/"testuale".
2. Click sulla thumbnail → ingrandimento.
3. `✓ accetta` → PLAN mostra il gruppo "Copertina" con miniatura.
4. Apply → il file ha la cover embeddata (`has_cover` true dopo re-scan).
5. History → Undo → la cover viene rimossa.

- [ ] **Step 4: Commit finale (se necessario)**

Nessun commit se non ci sono modifiche; altrimenti correggi e ripeti gli step precedenti.

---

## Self-Review

**Spec coverage:**
- Fonte CAA(high)+Discogs(text) → Task 1/2/3. ✓
- Release-MBID per CAA → Task 4. ✓
- `missing_cover` in `suggested_fix_json`, thumb su disco → Task 5/7. ✓
- provider-suggest esteso + endpoint thumb → Task 7. ✓
- Apply embed (skip su fail) + undo rimuove → Task 8/9. ✓
- Solo file `has_cover = false`, no sostituzione → Task 7 (upsert) + Task 8 (guard `f.has_cover`). ✓
- Thumbnail inline + lightbox in ISSUES → Task 10. ✓
- Miniatura in PLAN → Task 11. ✓
- Test backend con `.venv` 3.11, HTTP mockato → tutti i task. ✓

**Nota di scope (esplicita):** le cover si cercano per i file che ricevono una lookup provider in questa passata (quelli con issue testuali aperte). Un file già perfettamente taggato ma senza copertina verrà servito quando avrà una qualsiasi issue aperta. Questo evita centinaia di chiamate MB extra in un endpoint sincrono e riusa la lookup già fatta (zero chiamate MB aggiuntive per la cover; solo le chiamate immagine CAA/Discogs).

**Type consistency:** `CoverResult(thumb_bytes, full_url, source, confidence)` usato identico in Task 3/7. `ResolvedText(fields, release_mbids, confidence)` in Task 4/7. Op `COVER` con `after={full_url, source, confidence}` in Task 8 → letto in Task 9 (`after_json["full_url"]`) e Task 11 (`op.after.source`). `covers` nel result in Task 7/10. `n_cover` in Task 9 (schema) / Task 11 (TS). Coerenti.
