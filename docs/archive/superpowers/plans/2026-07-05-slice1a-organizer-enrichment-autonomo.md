# Slice 1A — DJOrganizer: motore enrichment autonomo + ritiro bridge

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendere DJOrganizer l'unico owner dei metadati testuali (Titolo/Artista/Album/Label/Genere) con provider testuali (MusicBrainz + Discogs) e identità AcoustID/MBID, e ritirare il bridge verso Cratory.

**Architecture:** DJOrganizer lavora su file (`AudioFile`) e propone correzioni via `Issue.suggested_fix_json`. I provider testuali si innestano come un nuovo endpoint `POST /api/issues/provider-suggest` — stesso schema di `bridge-suggest` che sostituisce — che riempie i suggerimenti sulle issue aperte con precedenza `manuale > tag pulito > provider > AI`. Il fingerprint AcoustID popola `AudioFile.mbid`, che dà a MusicBrainz un lookup diretto e certo.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (SQLite, niente Alembic), Pydantic, httpx, pytest. Anthropic (già presente, AI di genere via `ai_tags`). `pyacoustid` + `fpcalc` (Chromaprint) per il fingerprint.

## Global Constraints

- **Niente Alembic:** lo schema si crea con `Base.metadata.create_all` + ALTER idempotenti in `app/db.py::ensure_schema` (pattern esistente).
- **Env prefix `DJORG_`:** ogni nuovo setting in `core/config.py` si legge da `DJORG_<NOME>`.
- **Provider iniettabili:** ogni client HTTP accetta un `httpx.Client` opzionale → test senza rete. Nessun test tocca la rete reale.
- **Precedenza valori (spec ecosistema):** `fix manuale > tag pulito nel file > provider (MusicBrainz/Discogs) > AI-da-filename`. Il provider tocca SOLO issue aperte (`status="open"`); mai auto-accetta (status resta `open`); un tag pulito non ha issue, un fix manuale ha `status != "open"`.
- **Degradazione pulita:** provider irraggiungibile o non configurato → `db.rollback()` e risposta `{"configured": False, ...}`, stessa UX di `ai-suggest` senza chiave (nessuna modifica parziale).
- **Genere normalizzato** sempre con `services/genre_norm.normalize_genre` prima di salvarlo in un suggerimento.

---

## File Structure

**Creati:**
- `backend/app/integrations/_http.py` — helper retry/TLS condiviso (copia da Cratory).
- `backend/app/integrations/musicbrainz.py` — client MusicBrainz standalone (metadati testuali).
- `backend/app/integrations/discogs_meta.py` — lookup Discogs per Label/genere/anno di una release.
- `backend/app/integrations/acoustid.py` — client AcoustID (copia adattata da Cratory).
- `backend/app/services/genre_norm.py` — normalizzazione genere (copia da Cratory).
- `backend/app/services/text_providers.py` — catena provider testuali → dict normalizzato per file.
- `backend/app/services/fingerprint.py` — job fingerprint: popola `AudioFile.mbid`.
- `backend/app/routers/fingerprint.py` — `POST /api/fingerprint`.
- Test corrispondenti in `backend/tests/`.

**Modificati:**
- `backend/app/core/config.py` — `discogs_token`, `acoustid_api_key`, `musicbrainz_user_agent`.
- `backend/app/models.py` — colonna `AudioFile.mbid`; via `Settings.cratory_base_url`.
- `backend/app/db.py` — ALTER idempotente per `mbid`.
- `backend/app/routers/issues.py` — nuovo `provider-suggest`; rimozione `bridge-suggest` + `bridge_mismatch`.
- `backend/app/routers/settings.py`, `backend/app/schemas.py`, `backend/app/services/planning.py` — via `cratory_base_url`.
- `backend/app/main.py` — registrare il router `fingerprint`.

**Eliminati:**
- `backend/app/services/cratory_bridge.py`
- `backend/tests/test_cratory_bridge.py`, `backend/tests/test_bridge_suggest_api.py`

---

## Task 1: Config — chiavi provider e fingerprint

**Files:**
- Modify: `backend/app/core/config.py:6-18`
- Test: `backend/tests/test_config_providers.py`

**Interfaces:**
- Produces: `settings.discogs_token: str | None`, `settings.acoustid_api_key: str | None`, `settings.musicbrainz_user_agent: str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config_providers.py
from app.core.config import Settings


def test_provider_settings_default_and_env(monkeypatch):
    s = Settings()
    assert s.discogs_token is None
    assert s.acoustid_api_key is None
    assert s.musicbrainz_user_agent.startswith("DjOrganizer")

    monkeypatch.setenv("DJORG_DISCOGS_TOKEN", "tok")
    monkeypatch.setenv("DJORG_ACOUSTID_API_KEY", "key")
    s2 = Settings()
    assert s2.discogs_token == "tok"
    assert s2.acoustid_api_key == "key"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_config_providers.py -v`
Expected: FAIL (`AttributeError: 'Settings' object has no attribute 'discogs_token'`).

- [ ] **Step 3: Add fields to Settings**

In `backend/app/core/config.py`, inside `class Settings`, after `fuzzy_dur_tol_s`:

```python
    # Provider testuali (enrichment) e fingerprint. Chiavi opzionali: senza
    # chiave il provider è semplicemente inattivo (degradazione pulita).
    discogs_token: str | None = None
    acoustid_api_key: str | None = None
    musicbrainz_user_agent: str = "DjOrganizer/0.1 (+http://localhost)"
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && python -m pytest tests/test_config_providers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_config_providers.py
git commit -m "feat(config): chiavi provider testuali e AcoustID"
```

---

## Task 2: Helper HTTP condiviso

**Files:**
- Create: `backend/app/integrations/_http.py`
- Test: `backend/tests/test_http_retries.py`

**Interfaces:**
- Produces: `get_with_retries(client, url, *, error_cls, params=None) -> httpx.Response`, `post_with_retries(client, url, *, error_cls, data=None) -> httpx.Response`, `tls12_context() -> ssl.SSLContext`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_http_retries.py
import httpx
import pytest

from app.integrations._http import get_with_retries


class _Boom(Exception):
    pass


def test_get_with_retries_raises_after_transport_errors():
    class FailingClient:
        def get(self, url, params=None):
            raise httpx.ConnectError("boom")

    with pytest.raises(_Boom):
        get_with_retries(FailingClient(), "http://x", error_cls=_Boom, retries=1, backoff=0)


def test_get_with_retries_returns_response_on_success():
    resp = httpx.Response(200, text="ok")

    class OkClient:
        def get(self, url, params=None):
            return resp

    assert get_with_retries(OkClient(), "http://x", error_cls=_Boom).status_code == 200
```

- [ ] **Step 2: Run test — expect FAIL** (`ModuleNotFoundError: app.integrations._http`).

Run: `cd backend && python -m pytest tests/test_http_retries.py -v`

- [ ] **Step 3: Create the helper (copia verbatim da Cratory)**

Copia il contenuto di `DJProject01/backend/app/integrations/_http.py` in `backend/app/integrations/_http.py` senza modifiche (è già standalone: dipende solo da `httpx`, `ssl`, `time`, `logging`). Il file completo:

```python
"""Helper HTTP condiviso dai provider esterni: retry sugli errori di trasporto."""

import logging
import ssl
import time

import httpx

logger = logging.getLogger(__name__)

DEFAULT_RETRIES = 2
DEFAULT_BACKOFF = 0.6


def tls12_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def get_with_retries(client, url, *, error_cls, params=None,
                     retries=DEFAULT_RETRIES, backoff=DEFAULT_BACKOFF):
    return _request_with_retries(
        lambda: client.get(url, params=params), "GET", url,
        error_cls=error_cls, retries=retries, backoff=backoff)


def post_with_retries(client, url, *, error_cls, data=None,
                      retries=DEFAULT_RETRIES, backoff=DEFAULT_BACKOFF):
    return _request_with_retries(
        lambda: client.post(url, data=data), "POST", url,
        error_cls=error_cls, retries=retries, backoff=backoff)


def _request_with_retries(send, method, url, *, error_cls, retries, backoff):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return send()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise error_cls(f"connessione fallita dopo {retries + 1} tentativi ({last_exc})")
```

- [ ] **Step 4: Run test — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/_http.py backend/tests/test_http_retries.py
git commit -m "feat(integrations): helper HTTP retry/TLS condiviso"
```

---

## Task 3: Normalizzazione genere

**Files:**
- Create: `backend/app/services/genre_norm.py`
- Test: `backend/tests/test_genre_norm.py`

**Interfaces:**
- Produces: `normalize_genre(raw: str | None) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_genre_norm.py
from app.services.genre_norm import normalize_genre


def test_normalize_genre_alias_and_casing():
    assert normalize_genre("dnb") == "Drum & Bass"
    assert normalize_genre("tech-house") == "Tech House"
    assert normalize_genre("  IDM ") == "IDM"
    assert normalize_genre("") is None
    assert normalize_genre(None) is None
```

- [ ] **Step 2: Run test — expect FAIL.**

- [ ] **Step 3: Create `services/genre_norm.py`** — copia verbatim il file `DJProject01/backend/app/services/genre_norm.py` (37 righe, nessuna dipendenza esterna: solo `re`).

- [ ] **Step 4: Run test — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/genre_norm.py backend/tests/test_genre_norm.py
git commit -m "feat(services): normalizzazione genere (da Cratory)"
```

---

## Task 4: Client MusicBrainz standalone

**Files:**
- Create: `backend/app/integrations/musicbrainz.py`
- Test: `backend/tests/test_musicbrainz.py`

**Interfaces:**
- Consumes: `_http.get_with_retries`, `_http.tls12_context`.
- Produces: `class MusicBrainzError(Exception)`; `class MusicBrainzProvider` con `lookup(*, title, artist, isrc=None, mbid=None) -> dict | None`. Dict con chiavi opzionali: `canonical_title`, `canonical_artist`, `label`, `release_date`, `genre_primary`, `mbid`, `isrc`, `confidence` (int).

- [ ] **Step 1: Write the failing test (solo parsing, niente rete)**

```python
# backend/tests/test_musicbrainz.py
from app.integrations.musicbrainz import MusicBrainzProvider


def test_parse_recording_extracts_label_genre_date():
    p = MusicBrainzProvider(user_agent="test/0.1")
    rec = {
        "id": "mbid-1", "title": "Dreamscapes",
        "artist-credit": [{"name": "SLV"}],
        "releases": [{"date": "2019-05-01",
                      "label-info": [{"label": {"name": "Drumcode"}}]}],
        "tags": [{"name": "techno", "count": 5}, {"name": "acid", "count": 2}],
    }
    out = p._parse_recording(rec, isrc="ITX", exact=True)
    assert out["label"] == "Drumcode"
    assert out["genre_primary"] == "techno"
    assert out["release_date"] == "2019-05-01"
    assert out["canonical_artist"] == "SLV"
    assert out["mbid"] == "mbid-1"
    assert out["confidence"] == 95


def test_best_recording_prefers_title_match():
    p = MusicBrainzProvider(user_agent="test/0.1")
    recs = [
        {"title": "Other", "score": 50, "artist-credit": [{"name": "SLV"}]},
        {"title": "Dreamscapes", "score": 50, "artist-credit": [{"name": "SLV"}]},
    ]
    best = p._best_recording(recs, "Dreamscapes", "SLV")
    assert best["title"] == "Dreamscapes"
```

- [ ] **Step 2: Run test — expect FAIL.**

- [ ] **Step 3: Create `integrations/musicbrainz.py`**

Adatta il file di Cratory rendendolo standalone: **rimuovi** l'ereditarietà da `MusicFeatureProvider` e l'import `from app.integrations.getsongbpm import FeatureProviderError`; definisci una `MusicBrainzError` locale; cambia la firma `lookup` per accettare `mbid` esplicito (non più via `context`). Mantieni identici i metodi di parsing (`_parse_recording`, `_best_recording`, `_label`, `_release_date`, `_top_tag`, `_artist_credit`) e il throttling.

```python
"""Provider MusicBrainz: identità + metadati testuali (label, data, genere via tag).
NON fornisce BPM/key. Standalone (nessuna ABC): usato dalla catena text_providers.
Rate limit ~1 req/s (throttle interno) + breaker sulle connessioni troncate."""

import logging
import time
from difflib import SequenceMatcher
from typing import Any

import httpx

from app.integrations._http import get_with_retries, tls12_context

logger = logging.getLogger(__name__)
BASE = "https://musicbrainz.org/ws/2"


class MusicBrainzError(Exception):
    pass


class MusicBrainzProvider:
    name = "musicbrainz"
    _MIN_INTERVAL = 1.1
    _BREAKER_AFTER = 2

    def __init__(self, user_agent: str, http: httpx.Client | None = None):
        self.user_agent = user_agent
        self.http = http or httpx.Client(
            timeout=15, headers={"User-Agent": user_agent}, verify=tls12_context())
        self._last_request = 0.0
        self._conn_failures = 0
        self._suspended = False

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        wait = self._MIN_INTERVAL - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
        try:
            r = get_with_retries(self.http, f"{BASE}{path}",
                                 params={**params, "fmt": "json"}, error_cls=MusicBrainzError)
        except MusicBrainzError:
            self._conn_failures += 1
            if self._conn_failures >= self._BREAKER_AFTER and not self._suspended:
                self._suspended = True
                logger.warning("MusicBrainz: connessioni troncate — provider sospeso per il run.")
            raise
        self._conn_failures = 0
        if r.status_code == 503:
            raise MusicBrainzError("MusicBrainz: rate limit.")
        if r.status_code >= 400:
            raise MusicBrainzError(f"MusicBrainz {r.status_code}: {r.text[:160]}")
        try:
            return r.json()
        except ValueError as exc:
            raise MusicBrainzError("MusicBrainz: risposta non JSON") from exc

    def lookup(self, *, title, artist, isrc=None, mbid=None):
        if self._suspended:
            return None
        if mbid:
            try:
                rec = self._get(f"/recording/{mbid}", {"inc": "releases+tags"})
                parsed = self._parse_recording(rec, isrc=isrc, exact=True) if rec else None
                if parsed:
                    return parsed
            except MusicBrainzError as exc:
                logger.warning("MusicBrainz recording %s fallito: %s", mbid, exc)
        rec, exact = None, False
        if isrc:
            try:
                data = self._get(f"/isrc/{isrc}", {"inc": "releases+tags"})
                recs = data.get("recordings") or []
                rec, exact = (recs[0] if recs else None), bool(recs)
            except MusicBrainzError as exc:
                logger.warning("MusicBrainz ISRC %s fallito: %s", isrc, exc)
        if rec is None and title:
            query = f'recording:"{title}"' + (f' AND artist:"{artist}"' if artist else "")
            try:
                data = self._get("/recording", {"query": query, "limit": 5, "inc": "releases+tags"})
            except MusicBrainzError as exc:
                logger.warning("MusicBrainz search '%s' fallito: %s", title, exc)
                return None
            rec = self._best_recording(data.get("recordings") or [], title, artist)
        return self._parse_recording(rec, isrc=isrc, exact=exact) if rec else None

    @staticmethod
    def _best_recording(recordings, title, artist):
        title_l, artist_l = (title or "").lower(), (artist or "").lower()

        def score(rec):
            s = float(rec.get("score") or 0)
            s += SequenceMatcher(None, title_l, (rec.get("title") or "").lower()).ratio() * 20
            credit = " ".join((c.get("name") or (c.get("artist") or {}).get("name") or "")
                              for c in (rec.get("artist-credit") or [])).lower()
            if artist_l and credit:
                s += SequenceMatcher(None, artist_l, credit).ratio() * 20
            return s

        return max(recordings, key=score, default=None)

    @staticmethod
    def _release_date(rec):
        for rel in rec.get("releases") or []:
            date = rel.get("date") or (rel.get("release-group") or {}).get("first-release-date")
            if date:
                return date
        return None

    @staticmethod
    def _label(rec):
        for rel in rec.get("releases") or []:
            for li in rel.get("label-info") or []:
                name = (li.get("label") or {}).get("name")
                if name:
                    return name
        return None

    @staticmethod
    def _top_tag(rec):
        tags = [t for t in (rec.get("tags") or []) if t.get("name")]
        return max(tags, key=lambda t: t.get("count", 0))["name"] if tags else None

    @staticmethod
    def _artist_credit(rec):
        for credit in rec.get("artist-credit") or []:
            name = credit.get("name") or (credit.get("artist") or {}).get("name")
            if name:
                return name
        return None

    def _parse_recording(self, rec, *, isrc, exact):
        out: dict[str, Any] = {}
        if rec.get("id"):
            out["mbid"] = rec["id"]
        if rec.get("title"):
            out["canonical_title"] = rec["title"]
        if artist := self._artist_credit(rec):
            out["canonical_artist"] = artist
        if label := self._label(rec):
            out["label"] = label
        if rd := self._release_date(rec):
            out["release_date"] = rd
        if genre := self._top_tag(rec):
            out["genre_primary"] = genre
        if isrc:
            out["isrc"] = isrc
        if not out:
            return None
        out["confidence"] = 95 if exact else min(90, int(rec.get("score") or 60))
        return out
```

- [ ] **Step 4: Run test — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/musicbrainz.py backend/tests/test_musicbrainz.py
git commit -m "feat(integrations): client MusicBrainz standalone per metadati testuali"
```

---

## Task 5: Lookup metadati Discogs

**Files:**
- Create: `backend/app/integrations/discogs_meta.py`
- Test: `backend/tests/test_discogs_meta.py`

**Interfaces:**
- Consumes: `_http.get_with_retries`, `settings.discogs_token`.
- Produces: `class DiscogsError(Exception)`; `class DiscogsMetaClient(token=None, http=None)` con `lookup(*, artist, title) -> dict | None`. Dict con chiavi opzionali `label`, `genre_primary`, `release_date` (anno).

Nota: diverso dal `discogs.py` di Cratory (che fa `search_releases` per la discovery). Qui serve il *miglior match* per una singola traccia → i suoi campi editoriali.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_discogs_meta.py
import httpx

from app.integrations.discogs_meta import DiscogsMetaClient


def _client(payload):
    def handler(request):
        return httpx.Response(200, json=payload)
    transport = httpx.MockTransport(handler)
    return DiscogsMetaClient(token="t", http=httpx.Client(transport=transport))


def test_lookup_returns_label_genre_year():
    c = _client({"results": [
        {"title": "SLV - Dreamscapes", "label": ["Drumcode"],
         "style": ["Techno"], "genre": ["Electronic"], "year": "2019"},
    ]})
    out = c.lookup(artist="SLV", title="Dreamscapes")
    assert out["label"] == "Drumcode"
    assert out["genre_primary"] == "Techno"   # style batte genre (più specifico)
    assert out["release_date"] == "2019"


def test_lookup_empty_results_returns_none():
    c = _client({"results": []})
    assert c.lookup(artist="X", title="Y") is None
```

- [ ] **Step 2: Run test — expect FAIL.**

- [ ] **Step 3: Create `integrations/discogs_meta.py`**

```python
"""Discogs come provider di metadati TESTUALI per una singola traccia.
Cerca la miglior release per 'Artista Titolo' e ne estrae label/stile/anno.
Distinto da un eventuale uso discovery (search per genere/etichetta) di Cratory.
Senza token ~25/min; con DISCOGS_TOKEN ~60/min. httpx iniettabile → test senza rete."""

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.integrations._http import get_with_retries

logger = logging.getLogger(__name__)
BASE = "https://api.discogs.com"
_USER_AGENT = "DjOrganizer/0.1 (+http://localhost)"


class DiscogsError(Exception):
    pass


class DiscogsMetaClient:
    def __init__(self, token: str | None = None, http: httpx.Client | None = None):
        self.token = token if token is not None else (settings.discogs_token or None)
        headers = {"User-Agent": _USER_AGENT}
        if self.token:
            headers["Authorization"] = f"Discogs token={self.token}"
        self.http = http or httpx.Client(timeout=15, follow_redirects=True, headers=headers)

    def lookup(self, *, artist: str | None, title: str | None) -> dict[str, Any] | None:
        if not title:
            return None
        q = f"{artist} {title}".strip() if artist else title
        try:
            r = get_with_retries(self.http, f"{BASE}/database/search",
                                 params={"type": "release", "q": q, "per_page": 5},
                                 error_cls=DiscogsError)
        except DiscogsError as exc:
            logger.warning("Discogs lookup '%s' fallito: %s", q, exc)
            return None
        if r.status_code >= 400:
            logger.warning("Discogs %s per '%s'", r.status_code, q)
            return None
        try:
            results = (r.json() or {}).get("results") or []
        except ValueError:
            return None
        if not results:
            return None
        top = results[0]
        out: dict[str, Any] = {}
        labels = top.get("label") or []
        if labels:
            out["label"] = labels[0]
        # style è più specifico del genre generico Discogs ("Electronic"): preferiscilo.
        styles, genres = top.get("style") or [], top.get("genre") or []
        if styles:
            out["genre_primary"] = styles[0]
        elif genres:
            out["genre_primary"] = genres[0]
        if top.get("year"):
            out["release_date"] = str(top["year"])
        return out or None
```

- [ ] **Step 4: Run test — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/discogs_meta.py backend/tests/test_discogs_meta.py
git commit -m "feat(integrations): lookup metadati Discogs (label/stile/anno)"
```

---

## Task 6: Catena provider testuali

**Files:**
- Create: `backend/app/services/text_providers.py`
- Test: `backend/tests/test_text_providers.py`

**Interfaces:**
- Consumes: `MusicBrainzProvider`, `DiscogsMetaClient`, `genre_norm.normalize_genre`, `AudioFile`.
- Produces: `lookup(file, *, mb=None, discogs=None) -> dict`. Ritorna un dict con SOLO le chiavi risolte tra `artist`, `title`, `album`, `label`, `genre`, `year` (genere già normalizzato, year come `int`). MusicBrainz per primo (mbid > isrc > artist+title); Discogs riempie i buchi su `label`/`genre`. Dict vuoto se nulla.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_text_providers.py
from app.services import text_providers
from tests.conftest import make_audio_file


class _MB:
    def __init__(self, res): self.res = res
    def lookup(self, **kw): return self.res


class _Discogs:
    def __init__(self, res): self.res = res
    def lookup(self, **kw): return self.res


def test_musicbrainz_fills_then_discogs_fills_gaps():
    f = make_audio_file(1, artist="SLV", title="Dreamscapes")
    mb = _MB({"canonical_artist": "SLV", "label": "Drumcode",
              "genre_primary": "techno", "release_date": "2019-05-01"})
    dg = _Discogs({"label": "IGNORED", "genre_primary": "Acid Techno"})
    out = text_providers.lookup(f, mb=mb, discogs=dg)
    assert out["label"] == "Drumcode"        # MB vince, Discogs non sovrascrive
    assert out["genre"] == "Techno"          # normalizzato
    assert out["year"] == 2019
    assert out["artist"] == "SLV"


def test_discogs_fills_when_musicbrainz_missing_label():
    f = make_audio_file(2, artist="A", title="B")
    mb = _MB({"genre_primary": "house"})     # niente label
    dg = _Discogs({"label": "Trax", "genre_primary": "Chicago House"})
    out = text_providers.lookup(f, mb=mb, discogs=dg)
    assert out["label"] == "Trax"
    assert out["genre"] == "House"           # MB aveva già il genere → resta MB


def test_no_data_returns_empty():
    f = make_audio_file(3, artist="A", title="B")
    out = text_providers.lookup(f, mb=_MB(None), discogs=_Discogs(None))
    assert out == {}
```

- [ ] **Step 2: Run test — expect FAIL.**

- [ ] **Step 3: Create `services/text_providers.py`**

```python
"""Catena provider testuali: MusicBrainz (identità/label/genere/anno) poi Discogs
(riempie label/genere mancanti). Ritorna solo i campi risolti, genere normalizzato.
I provider sono iniettabili → test senza rete; in produzione li costruisce il router."""

from typing import Any

from app.integrations.discogs_meta import DiscogsMetaClient
from app.integrations.musicbrainz import MusicBrainzProvider
from app.services.genre_norm import normalize_genre


def _year(value) -> int | None:
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    return None


def lookup(file, *, mb=None, discogs=None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    mb_res = mb.lookup(title=file.title, artist=file.artist,
                       isrc=(file.isrc or None), mbid=getattr(file, "mbid", None)) if mb else None
    if mb_res:
        if mb_res.get("canonical_artist"):
            out["artist"] = mb_res["canonical_artist"]
        if mb_res.get("canonical_title"):
            out["title"] = mb_res["canonical_title"]
        if mb_res.get("label"):
            out["label"] = mb_res["label"]
        if mb_res.get("genre_primary"):
            out["genre"] = normalize_genre(mb_res["genre_primary"])
        if (y := _year(mb_res.get("release_date"))) is not None:
            out["year"] = y

    # Discogs riempie SOLO i buchi (MusicBrainz ha precedenza).
    needs = "label" not in out or "genre" not in out
    if discogs and needs:
        dg_res = discogs.lookup(artist=file.artist, title=file.title)
        if dg_res:
            if "label" not in out and dg_res.get("label"):
                out["label"] = dg_res["label"]
            if "genre" not in out and dg_res.get("genre_primary"):
                out["genre"] = normalize_genre(dg_res["genre_primary"])
            if "year" not in out and (y := _year(dg_res.get("release_date"))) is not None:
                out["year"] = y
    return out
```

- [ ] **Step 4: Run test — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/text_providers.py backend/tests/test_text_providers.py
git commit -m "feat(services): catena provider testuali MusicBrainz→Discogs"
```

---

## Task 7: Endpoint `provider-suggest`

**Files:**
- Modify: `backend/app/routers/issues.py:101-197` (aggiungi dopo `ai_suggest_genre`, prima del blocco bridge)
- Test: `backend/tests/test_provider_suggest_api.py`

**Interfaces:**
- Consumes: `text_providers.lookup`, `settings.discogs_token`/`musicbrainz_user_agent`.
- Produces: `POST /api/issues/provider-suggest` → `{"configured": bool, "files": int, "suggested": int, "unresolved": int}`.

Regole (identiche allo spirito del vecchio bridge): tocca solo issue `status="open"` di tipo `missing_required_tag|missing_metadata|dirty_genre` e campo in `{artist,title,genre,year,label,album}`; riempie `suggested_fix_json` solo se il provider dà un valore; una lookup per file (cache in-memory); mai auto-accetta.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_provider_suggest_api.py
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", artist="SLV", title="Dreamscapes", status="present")
    db.add(f); db.flush()
    db.add(Issue(file_id=f.id, type="missing_metadata", field="label",
                 severity="info", detail="manca label", status="open"))
    db.commit()
    return f


def test_provider_suggest_fills_label(db, monkeypatch):
    _seed(db)
    monkeypatch.setattr("app.core.config.settings.musicbrainz_user_agent", "t/0.1")
    monkeypatch.setattr("app.routers.issues.text_providers.lookup",
                        lambda file, **kw: {"label": "Drumcode"})
    r = client.post("/api/issues/provider-suggest")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True and body["suggested"] == 1
    iss = db.query(Issue).filter_by(field="label").one()
    assert iss.suggested_fix_json == {"field": "label", "action": "retag", "to": "Drumcode"}
    assert iss.status == "open"
```

- [ ] **Step 2: Run test — expect FAIL** (endpoint 404).

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routers/issues.py`: aggiungi l'import `from app.services import text_providers` e (in cima) `from app.core.config import settings`; aggiungi la costante e l'endpoint:

```python
_PROVIDER_TYPES = ("missing_required_tag", "missing_metadata", "dirty_genre")
_PROVIDER_FIELDS = ("artist", "title", "genre", "year", "label", "album")


@router.post("/provider-suggest", response_model=dict)
def provider_suggest(db: Session = Depends(get_db)):
    """Riempie i suggested_fix delle issue aperte dai provider testuali
    (MusicBrainz→Discogs). Precedenza manuale > tag pulito > provider > AI:
    tocca solo issue open (i tag puliti non hanno issue; i fix manuali sono
    accepted). Provider prima dell'AI (gli endpoint AI saltano le issue già
    suggerite). Una lookup per file, con cache in-memory."""
    from app.integrations.discogs_meta import DiscogsMetaClient
    from app.integrations.musicbrainz import MusicBrainzProvider

    mb = MusicBrainzProvider(user_agent=settings.musicbrainz_user_agent)
    discogs = DiscogsMetaClient()

    rows = db.execute(
        select(Issue, AudioFile).join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.type.in_(_PROVIDER_TYPES),
               Issue.field.in_(_PROVIDER_FIELDS))
    ).all()
    todo = [(i, f) for i, f in rows if i.suggested_fix_json is None]
    if not todo:
        return {"configured": True, "files": 0, "suggested": 0, "unresolved": 0}

    cache: dict[int, dict] = {}

    def _lookup(f: AudioFile) -> dict:
        if f.id not in cache:
            cache[f.id] = text_providers.lookup(f, mb=mb, discogs=discogs) or {}
        return cache[f.id]

    suggested = unresolved = 0
    files_seen: set[int] = set()
    for issue, f in todo:
        files_seen.add(f.id)
        res = _lookup(f)
        value = res.get(issue.field)
        if value is not None:
            issue.suggested_fix_json = {"field": issue.field, "action": "retag",
                                        "to": str(value)}
            issue.updated_at = utcnow()
            suggested += 1
        else:
            unresolved += 1
    db.commit()
    return {"configured": True, "files": len(files_seen),
            "suggested": suggested, "unresolved": unresolved}
```

- [ ] **Step 4: Run test — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/issues.py backend/tests/test_provider_suggest_api.py
git commit -m "feat(issues): endpoint provider-suggest (MusicBrainz/Discogs)"
```

---

## Task 8: Fingerprint AcoustID → colonna `mbid`

**Files:**
- Modify: `backend/app/models.py:55` (dopo `isrc`)
- Modify: `backend/app/db.py:41-45` (ALTER idempotente)
- Create: `backend/app/integrations/acoustid.py`
- Create: `backend/app/services/fingerprint.py`
- Create: `backend/app/routers/fingerprint.py`
- Modify: `backend/app/main.py` (registra il router)
- Test: `backend/tests/test_fingerprint.py`

**Interfaces:**
- Produces: `AudioFile.mbid: str | None`; `class AcoustIDClient` con `identify(path) -> list[{"mbid","score"}]`; `fingerprint_files(db, client, *, threshold=0.5) -> dict`; `POST /api/fingerprint`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_fingerprint.py
from app.models import AudioFile, ScanRoot
from app.services.fingerprint import fingerprint_files


class _FakeAcoustID:
    def __init__(self, mapping): self.mapping = mapping
    def identify(self, path): return self.mapping.get(path, [])


def test_fingerprint_sets_mbid_above_threshold(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present")
    db.add(f); db.commit()
    client = _FakeAcoustID({"/m/a.mp3": [{"mbid": "MB1", "score": 0.9}]})
    report = fingerprint_files(db, client, threshold=0.5)
    db.refresh(f)
    assert f.mbid == "MB1"
    assert report["identified"] == 1


def test_low_score_leaves_mbid_none(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/b.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present")
    db.add(f); db.commit()
    client = _FakeAcoustID({"/m/b.mp3": [{"mbid": "MB2", "score": 0.2}]})
    report = fingerprint_files(db, client, threshold=0.5)
    db.refresh(f)
    assert f.mbid is None
    assert report["below_threshold"] == 1
```

- [ ] **Step 2: Run test — expect FAIL** (`mbid` non esiste / `fingerprint_files` mancante).

- [ ] **Step 3a: Aggiungi la colonna `mbid`**

In `backend/app/models.py`, dentro `AudioFile`, subito dopo `isrc`:

```python
    mbid: Mapped[str | None] = mapped_column(String, index=True)
```

In `backend/app/db.py::ensure_schema`, nel blocco `if "audio_file" in ...`, dopo l'ALTER di `isrc`:

```python
        if "mbid" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE audio_file ADD COLUMN mbid VARCHAR"))
```

- [ ] **Step 3b: Crea `integrations/acoustid.py`** — copia adattata dal file Cratory (`DJProject01/backend/app/integrations/acoustid.py`), sostituendo `from app.core.config import settings` con quello di Organizer (già `app.core.config`) e `from app.integrations._http import post_with_retries` (creato in Task 2). Mantieni `AcoustIDClient`, `parse_lookup`, `fpcalc_available`, `get_acoustid_client`, e cambia `_USER_AGENT = "DjOrganizer/0.1 (+http://localhost)"`. `acoustid_configured()` usa `settings.acoustid_api_key`.

- [ ] **Step 3c: Crea `services/fingerprint.py`**

```python
"""Job di fingerprinting: per ogni file presente senza mbid, interroga AcoustID
e salva il miglior candidato sopra soglia in AudioFile.mbid. Il client è
iniettabile → test senza fpcalc né rete."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AudioFile

logger = logging.getLogger(__name__)


def fingerprint_files(db: Session, client, *, threshold: float = 0.5) -> dict:
    files = db.scalars(
        select(AudioFile).where(AudioFile.status == "present", AudioFile.mbid.is_(None))
    ).all()
    identified = below = not_found = errors = 0
    from app.integrations.acoustid import AcoustIDError
    for f in files:
        try:
            candidates = client.identify(f.path)
        except AcoustIDError as exc:
            errors += 1
            logger.warning("Fingerprint %s fallito: %s", f.path, exc)
            continue
        if not candidates:
            not_found += 1
            continue
        best = candidates[0]
        if best.get("score", 0) >= threshold and best.get("mbid"):
            f.mbid = best["mbid"]
            identified += 1
        else:
            below += 1
    db.commit()
    return {"identified": identified, "below_threshold": below,
            "not_found": not_found, "errors": errors, "total": len(files)}
```

- [ ] **Step 3d: Crea `routers/fingerprint.py`**

```python
"""Router FINGERPRINT: identità acustica AcoustID → AudioFile.mbid."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations import acoustid
from app.services.fingerprint import fingerprint_files

router = APIRouter(prefix="/api/fingerprint", tags=["fingerprint"])


@router.get("/status", response_model=dict)
def status():
    return {"configured": acoustid.acoustid_configured(),
            "fpcalc": acoustid.fpcalc_available()}


@router.post("", response_model=dict)
def run(db: Session = Depends(get_db)):
    if not acoustid.acoustid_configured() or not acoustid.fpcalc_available():
        return {"configured": False, "identified": 0, "below_threshold": 0,
                "not_found": 0, "errors": 0, "total": 0}
    return {"configured": True, **fingerprint_files(db, acoustid.get_acoustid_client())}
```

Registra in `backend/app/main.py`: importa `from app.routers import fingerprint` e aggiungi `app.include_router(fingerprint.router)` accanto agli altri `include_router`.

- [ ] **Step 4: Run test — expect PASS.**

Run: `cd backend && python -m pytest tests/test_fingerprint.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/app/integrations/acoustid.py \
        backend/app/services/fingerprint.py backend/app/routers/fingerprint.py \
        backend/app/main.py backend/tests/test_fingerprint.py
git commit -m "feat(fingerprint): AcoustID/MBID → AudioFile.mbid"
```

---

## Task 9: Ritiro bridge Cratory (backend)

**Files:**
- Delete: `backend/app/services/cratory_bridge.py`, `backend/tests/test_cratory_bridge.py`, `backend/tests/test_bridge_suggest_api.py`
- Modify: `backend/app/routers/issues.py:200-331` (rimuovi blocco bridge + `bridge_mismatch`), `:13` (import)
- Modify: `backend/app/models.py:116` (via `Settings.cratory_base_url`)
- Modify: `backend/app/schemas.py` (via `cratory_base_url` da `SettingsRead`/`SettingsUpdate`)
- Modify: `backend/app/routers/settings.py:17-36`, `backend/app/services/planning.py` (firma `update_settings`)
- Test: nessuno nuovo; la suite esistente deve restare verde.

**Interfaces:**
- Produces: `bridge-suggest` e `bridge_mismatch` non esistono più; `Settings` senza `cratory_base_url`.

- [ ] **Step 1: Rimuovi il codice bridge da `issues.py`**

Cancella dall'`import` di riga 13 `cratory_bridge` e `planning` se non più usati (verifica: `planning` era usato solo per `get_settings(db).cratory_base_url` nel bridge). Cancella l'intero blocco `# --- Bridge Cratory ---` (costanti `_BRIDGE_TYPES/_BRIDGE_FIELDS/_NOT_CONFIGURED`, `_norm`, `bridge_suggest`).

- [ ] **Step 2: Rimuovi `cratory_base_url`**

- `models.py`: elimina la riga `cratory_base_url: Mapped[str | None] = mapped_column(String)`.
- `schemas.py`: togli `cratory_base_url` da `SettingsRead` e `SettingsUpdate` (grep per confermare i punti).
- `routers/settings.py`: togli `cratory_base_url=s.cratory_base_url` da `_read` e `cratory_base_url=body.cratory_base_url` da `put_settings`.
- `services/planning.py`: togli il parametro `cratory_base_url` da `update_settings` e il relativo assegnamento (grep `cratory_base_url`).

- [ ] **Step 3: Elimina i file bridge**

```bash
git rm backend/app/services/cratory_bridge.py \
       backend/tests/test_cratory_bridge.py \
       backend/tests/test_bridge_suggest_api.py
```

- [ ] **Step 4: Verifica nessun riferimento orfano**

Run: `cd backend && grep -rn "cratory_bridge\|bridge_mismatch\|cratory_base_url\|bridge_suggest" app tests`
Expected: nessun risultato.

- [ ] **Step 5: Suite completa verde**

Run: `cd backend && python -m pytest -q`
Expected: PASS (nessun test rotto; i tre file bridge non esistono più).

- [ ] **Step 6: Commit**

```bash
git add -A backend
git commit -m "refactor: ritiro bridge Cratory (endpoint, mismatch, cratory_base_url)"
```

---

## Task 10: Frontend — card Impostazioni (provider + fingerprint) e pulsante provider-suggest

**Files:**
- Read first: `frontend/app/settings/page.tsx`, `frontend/app/issues/*` (o pagina che elenca le issue), `frontend/lib/api.ts`.
- Modify: pagina settings (nuova card stato provider/fingerprint + pulsante "Identifica ora"), pagina issues (pulsante "Suggerisci da provider"), `lib/api.ts` (nuove chiamate), rimozione UI `cratory_base_url`.

**Interfaces:**
- Consuma: `GET /api/fingerprint/status`, `POST /api/fingerprint`, `POST /api/issues/provider-suggest`.

- [ ] **Step 1: Leggi i file frontend elencati** per replicare i pattern esistenti (fetch helper, componenti Button/Alert, come `ai-suggest` è cablato nella pagina issues e come le card status sono rese in settings).

- [ ] **Step 2: `lib/api.ts`** — aggiungi:

```ts
export const providerSuggest = () => apiPost<{configured: boolean; files: number; suggested: number; unresolved: number}>("/api/issues/provider-suggest");
export const fingerprintStatus = () => apiGet<{configured: boolean; fpcalc: boolean}>("/api/fingerprint/status");
export const runFingerprint = () => apiPost<{configured: boolean; identified: number; below_threshold: number; not_found: number; errors: number; total: number}>("/api/fingerprint");
```

(Adatta i nomi `apiGet/apiPost` a quelli reali del file.)

- [ ] **Step 3: Settings page** — rimuovi il campo `cratory_base_url`; aggiungi una card "Provider testuali & Fingerprint" che mostra `fingerprintStatus()` (configurato + fpcalc) e un pulsante "Identifica ora" → `runFingerprint()`, con riepilogo `identified/below_threshold/not_found`.

- [ ] **Step 4: Issues page** — accanto al pulsante AI aggiungi "Suggerisci da provider" → `providerSuggest()`, con refresh della lista dopo la risposta (stesso pattern del pulsante AI esistente).

- [ ] **Step 5: Build + lint**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore; nessun riferimento residuo a `cratory_base_url`.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(ui): card provider/fingerprint + pulsante provider-suggest; via cratory_base_url"
```

---

## Self-Review (svolta)

- **Copertura spec (slice 1 lato Organizer):** enrichment testuale completo (Task 4-7), precedenza `manuale > tag pulito > provider > AI` (Task 7), Fingerprint AcoustID/MBID (Task 8), rimozione bridge (Task 9), `genre_norm` migrato (Task 3), chiavi in Organizer (Task 1). ✔
- **Fuori scope (lato Cratory):** slim-down, migrazione DB drop colonne, rimozione provider audio, settings Cratory → **piano separato slice 1B** (repo DJProject01).
- **Placeholder:** nessuno nei task backend (1-9). Task 10 (frontend) richiede lettura preliminare dei file reali — esplicitato come primo step, non un placeholder di logica.
- **Type consistency:** `text_providers.lookup(file, *, mb, discogs)` usato coerentemente in Task 6 e 7; dict provider con chiavi `label/genre_primary/release_date/canonical_*` coerenti tra Task 4/5/6; `fingerprint_files(db, client, *, threshold)` coerente Task 8.

## Note per l'esecuzione

- Dipendenze nuove: `pyacoustid` (pip) e `fpcalc` (Chromaprint, `brew install chromaprint`) servono SOLO a runtime del fingerprint; i test usano client iniettati e non li richiedono. Aggiungere `pyacoustid` a `backend/requirements.txt` nel Task 8.
- `httpx.MockTransport` (Task 5) è già disponibile con httpx installato.
