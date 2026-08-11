# Revisione generi AI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Job in background che rivede il genere di tutta la library (provider + web search AI) e propone correzioni come issue; il vecchio "Suggerisci generi" viene rimosso.

**Architecture:** Pattern mono-job esistente (`provider_rescan_job`): service sincrono testabile con dipendenze iniettate (`mb`, `discogs`, `ai_fn`), wrapper thread con stato in memoria, router sottile start/status/preview, polling dalla jobs bar del frontend. Le proposte diventano issue `genre_review` (o riempiono le issue genre già aperte) e confluiscono nel flusso ISSUES → PLAN → APPLY.

**Tech Stack:** FastAPI + SQLAlchemy + SQLite (Python 3.11), Anthropic SDK (Haiku 4.5 + server tool `web_search_20250305`), Next.js 16 + React 19 + TypeScript.

**Spec:** `docs/superpowers/specs/2026-08-10-genre-review-ai-design.md`

## Global Constraints

- Test SEMPRE con il venv del progetto: `backend/.venv/bin/python -m pytest ...` (il python di sistema è 3.9 e rompe su `X | None`).
- `pytest.ini` ha `filterwarnings = error`: un warning nuovo fa fallire la suite.
- Commenti/docstring backend in **italiano** (stile esistente).
- i18n: prima la chiave in `frontend/lib/i18n/en.ts`, poi la traduzione in `it.ts` (tipizzato `typeof en`: chiave mancante = errore di compilazione).
- Modello AI: `claude-haiku-4-5`; tool `{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}`; batch AI da 10 tracce.
- Niente Alembic: nuove colonne via `ensure_schema()` in `backend/app/db.py`.
- Nessuna scrittura diretta dei tag: solo issue con `suggested_fix_json`.

---

### Task 1: Colonna `AudioFile.genre_reviewed_at`

**Files:**
- Modify: `backend/app/models.py` (classe `AudioFile`, dopo `integrity_detail`)
- Modify: `backend/app/db.py` (`ensure_schema`, blocco `audio_file`)
- Test: `backend/tests/test_genre_review_service.py` (nuovo file, primo test)

**Interfaces:**
- Produces: `AudioFile.genre_reviewed_at: datetime | None` (nullable, default None), usata dai Task 4-5.

- [ ] **Step 1: Write the failing test**

Crea `backend/tests/test_genre_review_service.py`:

```python
"""Test del service di revisione generi (Task 1: colonna; Task 4: logica)."""

from app.models import AudioFile


def _file(db, fid, *, artist=None, title=None, genre=None, album=None,
          label=None, reviewed=None, path=None):
    f = AudioFile(id=fid, root_id=1, path=path or f"/m/{fid}.mp3", ext="mp3",
                  size_bytes=1, hash_method="file", status="present",
                  has_cover=False, artist=artist, title=title, genre=genre,
                  album=album, label=label, genre_reviewed_at=reviewed)
    db.add(f)
    db.commit()
    return f


def test_genre_reviewed_at_column_defaults_none(db):
    f = _file(db, 1, artist="ANNA", title="Hidden Beauties")
    assert f.genre_reviewed_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_genre_review_service.py -v`
Expected: FAIL con `TypeError: 'genre_reviewed_at' is an invalid keyword argument for AudioFile`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/models.py`, nella classe `AudioFile`, subito dopo la riga
`integrity_detail: Mapped[str | None] = mapped_column(Text)`:

```python
    genre_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
```

(`datetime` e `DateTime` sono già importati nel modulo.)

In `backend/app/db.py`, dentro `ensure_schema`, nel blocco
`if "audio_file" in inspector.get_table_names():`, dopo il ramo
`integrity_detail`:

```python
        if "genre_reviewed_at" not in cols:
            with eng.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE audio_file ADD COLUMN genre_reviewed_at DATETIME"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_genre_review_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/tests/test_genre_review_service.py
git commit -m "feat(genre-review): colonna AudioFile.genre_reviewed_at"
```

---

### Task 2: `genre_candidates` dagli adapter provider

**Files:**
- Modify: `backend/app/integrations/musicbrainz.py` (`_top_tag` area + `_parse_recording`)
- Modify: `backend/app/integrations/discogs_meta.py` (`lookup`)
- Test: `backend/tests/test_musicbrainz.py` o (se non esiste) i test adapter esistenti — verificare con `ls backend/tests | grep -i musicbrainz`; in mancanza aggiungere i test a `backend/tests/test_discogs_meta.py` (esiste) e creare `backend/tests/test_musicbrainz_candidates.py`

**Interfaces:**
- Produces: nei dict di ritorno di `MusicBrainzProvider.lookup(...)` e `DiscogsMetaClient.lookup(...)` la chiave opzionale `genre_candidates: list[str]` (grezzi, non normalizzati — la normalizzazione è del service).

- [ ] **Step 1: Write the failing tests**

Crea `backend/tests/test_musicbrainz_candidates.py`:

```python
"""_parse_recording espone tutti i tag come candidati genere (ordinati per count)."""

from app.integrations.musicbrainz import MusicBrainzProvider


def test_parse_recording_exposes_genre_candidates():
    p = MusicBrainzProvider(user_agent="test/1.0")
    rec = {"id": "mbid-1", "title": "Spastik",
           "artist-credit": [{"name": "Plastikman"}],
           "tags": [{"name": "techno", "count": 5},
                    {"name": "acid techno", "count": 2},
                    {"name": "electronic", "count": 7}]}
    out = p._parse_recording(rec, isrc=None, exact=True)
    assert out["genre_primary"] == "electronic"
    assert out["genre_candidates"] == ["electronic", "techno", "acid techno"]


def test_parse_recording_no_tags_no_candidates():
    p = MusicBrainzProvider(user_agent="test/1.0")
    rec = {"id": "mbid-2", "title": "X", "artist-credit": [{"name": "Y"}]}
    out = p._parse_recording(rec, isrc=None, exact=False)
    assert "genre_candidates" not in out
```

In `backend/tests/test_discogs_meta.py` aggiungi in coda (usando il pattern di
mock httpx già presente nel file — un `httpx.Client` con `transport=httpx.MockTransport(...)`
o l'helper esistente; adattare al fixture del file):

```python
def test_lookup_exposes_genre_candidates_styles_first():
    payload = {"results": [{"style": ["Tech House", "Minimal"],
                            "genre": ["Electronic"], "label": ["Drumcode"],
                            "year": 2020}]}
    client = _client_returning(payload)  # usare/creare l'helper di mock del file
    out = client.lookup(artist="A", title="B")
    assert out["genre_primary"] == "Tech House"
    assert out["genre_candidates"] == ["Tech House", "Minimal", "Electronic"]
```

Nota per l'esecutore: se `test_discogs_meta.py` non ha un helper riusabile,
costruire il client così:

```python
import httpx
from app.integrations.discogs_meta import DiscogsMetaClient

def _client_returning(payload):
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    return DiscogsMetaClient(token="", http=httpx.Client(transport=transport))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_musicbrainz_candidates.py backend/tests/test_discogs_meta.py -v`
Expected: FAIL (`genre_candidates` assente / KeyError)

- [ ] **Step 3: Write minimal implementation**

`backend/app/integrations/musicbrainz.py` — accanto a `_top_tag` aggiungi:

```python
    @staticmethod
    def _all_tags(rec):
        """Tutti i tag con nome, ordinati per popolarità decrescente."""
        tags = [t for t in (rec.get("tags") or []) if t.get("name")]
        return [t["name"] for t in
                sorted(tags, key=lambda t: t.get("count", 0), reverse=True)]
```

In `_parse_recording`, subito dopo il ramo `if genre := self._top_tag(rec): ...`:

```python
        if cands := self._all_tags(rec):
            out["genre_candidates"] = cands
```

`backend/app/integrations/discogs_meta.py` — in `lookup`, dopo il blocco che
imposta `genre_primary`:

```python
        # Tutti gli stili + generi (senza duplicati) come candidati per l'AI.
        cands = styles + [g for g in genres if g not in styles]
        if cands:
            out["genre_candidates"] = cands
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_musicbrainz_candidates.py backend/tests/test_discogs_meta.py -v`
Expected: PASS (tutti, inclusi quelli preesistenti del file Discogs)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/musicbrainz.py backend/app/integrations/discogs_meta.py backend/tests/test_musicbrainz_candidates.py backend/tests/test_discogs_meta.py
git commit -m "feat(providers): genre_candidates da MusicBrainz e Discogs"
```

---

### Task 3: `ai_tags.review_genres` (Haiku + web search)

**Files:**
- Modify: `backend/app/services/ai_tags.py` (aggiunta in coda)
- Test: `backend/tests/test_ai_review_genres.py` (nuovo)

**Interfaces:**
- Consumes: niente dal progetto (solo SDK `anthropic`, import lazy).
- Produces: `ai_tags.review_genres(items: list[dict]) -> list[dict]`.
  Input per item: `{"artist": str|None, "title": str|None, "album": str|None,
  "label": str|None, "current_genre": str|None, "candidates": list[str]}`.
  Output allineato per indice: `{"genre": str|None, "confidence": "high"|"low"}`.

- [ ] **Step 1: Write the failing test**

Crea `backend/tests/test_ai_review_genres.py`. L'import di `Anthropic` è lazy
(`from anthropic import Anthropic` dentro la funzione): si intercetta con un
modulo finto in `sys.modules`.

```python
"""review_genres: formato del prompt, tool web_search, allineamento output."""

import sys
import types

from app.services import ai_tags


class _FakeParsed:
    def __init__(self, items):
        self.items = items


class _FakeResp:
    def __init__(self, items):
        self.parsed_output = _FakeParsed(items)


def _install_fake_anthropic(monkeypatch, captured, items_out):
    class _FakeMessages:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return _FakeResp(items_out)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = _FakeMessages()

    mod = types.ModuleType("anthropic")
    mod.Anthropic = _FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def test_review_genres_empty_input_no_call():
    assert ai_tags.review_genres([]) == []


def test_review_genres_prompt_tools_and_alignment(monkeypatch):
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured,
        [ai_tags._Review(genre="Tech House", confidence="high")])
    items = [{"artist": "ANNA", "title": "Hidden Beauties", "album": "EP1",
              "label": "Drumcode", "current_genre": "House",
              "candidates": ["Tech House", "Techno"]},
             {"artist": None, "title": None, "album": None, "label": None,
              "current_genre": None, "candidates": []}]
    out = ai_tags.review_genres(items)
    # tool web_search presente con max_uses limitato
    assert captured["tools"] == [{"type": "web_search_20250305",
                                  "name": "web_search", "max_uses": 3}]
    assert captured["model"] == "claude-haiku-4-5"
    # il listato contiene i metadati e i candidati
    text = captured["messages"][0]["content"]
    assert "ANNA - Hidden Beauties" in text
    assert "genere attuale: House" in text
    assert "Tech House; Techno" in text
    # output allineato: il secondo item (mancante nella risposta) è None/low
    assert out == [{"genre": "Tech House", "confidence": "high"},
                   {"genre": None, "confidence": "low"}]


def test_review_genres_weird_confidence_becomes_low(monkeypatch):
    captured = {}
    _install_fake_anthropic(
        monkeypatch, captured, [ai_tags._Review(genre="Acid", confidence="boh")])
    out = ai_tags.review_genres([{"artist": "A", "title": "B", "album": None,
                                  "label": None, "current_genre": None,
                                  "candidates": []}])
    assert out == [{"genre": "Acid", "confidence": "low"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_ai_review_genres.py -v`
Expected: FAIL con `AttributeError: ... has no attribute 'review_genres'`

- [ ] **Step 3: Write minimal implementation**

In coda a `backend/app/services/ai_tags.py`:

```python
_REVIEW_PROMPT = (
    "Sei un esperto di musica da DJ (prevalentemente elettronica) che verifica "
    "il GENERE di tracce. Per ogni traccia numerata qui sotto scegli il genere "
    "primario più accurato e specifico, UNO solo, con casing canonico (es. "
    "'Tech House', 'Acid Techno', 'Drum & Bass'). I candidati dei provider "
    "(MusicBrainz/Discogs) sono evidenza forte: preferiscili quando plausibili. "
    "Usa la ricerca web SOLO quando l'evidenza disponibile non basta a decidere. "
    "Mantieni lo STESSO ordine, un elemento per traccia. Imposta "
    "confidence='high' se sei sicuro, 'low' se incerto. Se non riesci a "
    "determinare il genere metti genre a null; non inventare valori spazzatura."
)


class _Review(BaseModel):
    genre: str | None = None
    confidence: str = "low"


class _Reviews(BaseModel):
    items: list[_Review]


def review_genres(items: list[dict]) -> list[dict]:
    """Rivede il genere di un batch di tracce con contesto provider e web search.
    items: [{'artist','title','album','label','current_genre','candidates'}];
    ritorna [{'genre': str|None, 'confidence': 'high'|'low'}] allineato per indice."""
    if not items:
        return []
    from anthropic import Anthropic  # import lazy

    client = Anthropic()
    lines = []
    for j, it in enumerate(items):
        parts = [f"{it.get('artist') or '?'} - {it.get('title') or '?'}"]
        if it.get("album"):
            parts.append(f"album: {it['album']}")
        if it.get("label"):
            parts.append(f"label: {it['label']}")
        if it.get("current_genre"):
            parts.append(f"genere attuale: {it['current_genre']}")
        if it.get("candidates"):
            parts.append("candidati provider: " + "; ".join(it["candidates"]))
        lines.append(f"{j}. " + " | ".join(parts))
    resp = client.messages.parse(
        model=_MODEL,
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search",
                "max_uses": 3}],
        messages=[{"role": "user",
                   "content": f"{_REVIEW_PROMPT}\n\n" + "\n".join(lines)}],
        output_format=_Reviews,
    )
    parsed = resp.parsed_output.items if resp.parsed_output else []
    out: list[dict] = []
    for k in range(len(items)):
        r = parsed[k] if k < len(parsed) else _Review()
        conf = "high" if r.confidence == "high" else "low"
        out.append({"genre": r.genre or None, "confidence": conf})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_ai_review_genres.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai_tags.py backend/tests/test_ai_review_genres.py
git commit -m "feat(ai): review_genres con Haiku + server tool web_search"
```

---

### Task 4: Service `genre_review.py` (core)

**Files:**
- Create: `backend/app/services/genre_review.py`
- Test: `backend/tests/test_genre_review_service.py` (estende il file del Task 1)

**Interfaces:**
- Consumes: `AudioFile.genre_reviewed_at` (Task 1), chiave `genre_candidates`
  dai lookup provider (Task 2), la forma input/output di `review_genres` (Task 3
  — qui iniettata come `ai_fn`).
- Produces:
  - `GENRE_REVIEW_TYPE = "genre_review"`
  - `count_candidates(db, *, folder=None, genre=None, redo=False) -> int`
  - `review(db, *, mb, discogs, ai_fn, folder=None, genre=None, redo=False,
    batch_size=10, on_progress=None) -> dict` con chiavi
    `{"configured": True, "files", "proposed", "confirmed", "unresolved", "skipped"}`.
  - `on_progress(processed: int, total: int, phase: str)` con fasi
    `"looking_up"` e `"reviewing"` (stessa firma del rescan provider).

- [ ] **Step 1: Write the failing tests**

Aggiungi in coda a `backend/tests/test_genre_review_service.py`:

```python
from sqlalchemy import select

from app.models import Issue
from app.services import genre_review


class _MB:
    """MusicBrainz finto: risponde con candidati fissi (o None)."""
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def lookup(self, **kw):
        self.calls.append(kw)
        return self.result


class _DG:
    def __init__(self, result=None):
        self.result = result

    def lookup(self, **kw):
        return self.result


def _ai_returning(*proposals):
    """ai_fn finto: risponde con le proposte date, allineate all'input."""
    def fn(items):
        assert len(items) == len(proposals)
        return list(proposals)
    return fn


def _issues(db, fid):
    return db.scalars(select(Issue).where(Issue.file_id == fid)).all()


def test_count_candidates_skips_reviewed_unless_redo(db):
    from app.models import utcnow
    _file(db, 1, artist="A", title="T1")
    _file(db, 2, artist="B", title="T2", reviewed=utcnow())
    assert genre_review.count_candidates(db) == 1
    assert genre_review.count_candidates(db, redo=True) == 2


def test_review_proposes_genre_review_issue_when_differs(db):
    f = _file(db, 1, artist="ANNA", title="Hidden Beauties", genre="House")
    res = genre_review.review(
        db, mb=_MB({"genre_candidates": ["Techno"]}), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["proposed"] == 1 and res["confirmed"] == 0
    (issue,) = _issues(db, 1)
    assert issue.type == "genre_review" and issue.field == "genre"
    assert issue.status == "open"
    assert issue.suggested_fix_json == {
        "field": "genre", "action": "retag", "to": "Techno",
        "source": "ai", "confidence": "high"}
    assert f.genre_reviewed_at is not None


def test_review_confirm_same_genre_no_issue_and_closes_stale(db):
    _file(db, 1, artist="A", title="T", genre="tech house")  # casing diverso
    db.add(Issue(file_id=1, type="genre_review", field="genre", severity="info",
                 detail="vecchia proposta", status="open",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "ai"}))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Tech House", "confidence": "high"}))
    assert res["confirmed"] == 1 and res["proposed"] == 0
    assert _issues(db, 1) == []  # la genre_review aperta e ora inutile sparisce


def test_review_fills_open_missing_metadata_issue(db):
    _file(db, 1, artist="A", title="T", genre=None)
    db.add(Issue(file_id=1, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=None, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Dub Techno", "confidence": "low"}))
    assert res["proposed"] == 1
    (issue,) = _issues(db, 1)  # nessuna issue duplicata
    assert issue.type == "missing_metadata"
    assert issue.suggested_fix_json["to"] == "Dub Techno"
    assert issue.suggested_fix_json["source"] == "ai"


def test_review_never_overwrites_provider_suggestion(db):
    _file(db, 1, artist="A", title="T", genre=None)
    provider_fix = {"field": "genre", "action": "retag", "to": "House",
                    "source": "provider", "confidence": "high"}
    db.add(Issue(file_id=1, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=provider_fix, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["skipped"] == 1 and res["proposed"] == 0
    (issue,) = _issues(db, 1)
    assert issue.suggested_fix_json == provider_fix  # intatto


def test_review_skips_when_provider_override_open(db):
    _file(db, 1, artist="A", title="T", genre="House")
    db.add(Issue(file_id=1, type="provider_override", field="genre",
                 severity="info", detail="provider: genre → Techno",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "provider",
                                     "confidence": "strong"}, status="open"))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Minimal", "confidence": "low"}))
    assert res["skipped"] == 1
    assert len(_issues(db, 1)) == 1  # nessuna seconda issue sul campo genre


def test_review_none_is_unresolved_but_marks_reviewed(db):
    f = _file(db, 1, artist="A", title="T", genre="House")
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": None, "confidence": "low"}))
    assert res["unresolved"] == 1
    assert _issues(db, 1) == []
    assert f.genre_reviewed_at is not None


def test_review_respects_user_decision_on_genre_review(db):
    _file(db, 1, artist="A", title="T", genre="House")
    db.add(Issue(file_id=1, type="genre_review", field="genre", severity="info",
                 detail="AI: genre → Techno", status="dismissed",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Techno", "source": "ai"}))
    db.commit()
    res = genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": "Techno", "confidence": "high"}))
    assert res["skipped"] == 1
    (issue,) = _issues(db, 1)
    assert issue.status == "dismissed"  # decisione utente intoccata


def test_review_ai_failure_counts_unresolved_and_continues(db):
    _file(db, 1, artist="A", title="T")
    _file(db, 2, artist="B", title="U")

    def boom(items):
        raise RuntimeError("api down")

    res = genre_review.review(db, mb=_MB(None), discogs=_DG(None), ai_fn=boom)
    assert res["unresolved"] == 2
    assert res["files"] == 2


def test_review_candidates_merged_normalized_deduped(db):
    _file(db, 1, artist="A", title="T")
    captured = {}

    def fn(items):
        captured["items"] = items
        return [{"genre": None, "confidence": "low"}]

    genre_review.review(
        db,
        mb=_MB({"genre_candidates": ["tech house", "techno"],
                "genre_primary": "tech house"}),
        discogs=_DG({"genre_candidates": ["Tech House", "Electronic"]}),
        ai_fn=fn)
    assert captured["items"][0]["candidates"] == \
        ["Tech House", "Techno", "Electronic"]


def test_review_progress_phases(db):
    _file(db, 1, artist="A", title="T")
    seen = []
    genre_review.review(
        db, mb=_MB(None), discogs=_DG(None),
        ai_fn=_ai_returning({"genre": None, "confidence": "low"}),
        on_progress=lambda p, t, ph: seen.append((p, t, ph)))
    assert ("looking_up" in {ph for _, _, ph in seen})
    assert seen[-1] == (1, 1, "reviewing")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_genre_review_service.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.genre_review'` (il test del Task 1 resta verde)

- [ ] **Step 3: Write the implementation**

Crea `backend/app/services/genre_review.py`:

```python
"""Revisione generi su tutta la libreria: candidati dai provider come evidenza,
AI (con web search) per decidere, proposte come issue 'genre_review' oppure
riempimento delle issue genre già aperte. Sincrono e testabile: mb/discogs/ai_fn
sono iniettati (il job li costruisce). Mai due proposte aperte sullo stesso
campo di uno stesso file; i fix di origine provider e le decisioni utente
(accepted/dismissed) non si toccano."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AudioFile, Issue, utcnow
from app.services.genre_norm import normalize_genre

GENRE_REVIEW_TYPE = "genre_review"
# Issue "da inspector" che il job può riempire invece di crearne una nuova.
_FILLABLE_TYPES = ("missing_metadata", "dirty_genre")
_BATCH = 10


def _candidates_stmt(folder: str | None, genre: str | None, redo: bool):
    stmt = select(AudioFile).where(AudioFile.status == "present")
    if folder:
        stmt = stmt.where(AudioFile.path.ilike(f"%{folder}%"))
    if genre:
        stmt = stmt.where(AudioFile.genre == genre)
    if not redo:
        stmt = stmt.where(AudioFile.genre_reviewed_at.is_(None))
    return stmt


def count_candidates(db: Session, *, folder: str | None = None,
                     genre: str | None = None, redo: bool = False) -> int:
    stmt = _candidates_stmt(folder, genre, redo)
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def _provider_candidates(f: AudioFile, *, mb, discogs) -> list[str]:
    """Candidati genere dai provider, normalizzati e deduplicati (ordine: MB
    per popolarità, poi Discogs). Gli errori/None dei provider sono tollerati."""
    raw: list[str] = []
    mb_res = mb.lookup(title=f.title, artist=f.artist,
                       isrc=(f.isrc.strip() or None) if f.isrc else None,
                       mbid=f.mbid) if mb is not None else None
    if mb_res:
        raw += mb_res.get("genre_candidates") or []
        if mb_res.get("genre_primary"):
            raw.append(mb_res["genre_primary"])
    dg_res = discogs.lookup(artist=f.artist, title=f.title) \
        if discogs is not None else None
    if dg_res:
        raw += dg_res.get("genre_candidates") or []
    out: list[str] = []
    for g in raw:
        n = normalize_genre(g)
        if n and n not in out:
            out.append(n)
    return out


def _apply_proposal(db: Session, f: AudioFile, proposal: dict) -> str:
    """Applica l'esito AI a un file. Ritorna la categoria per i contatori:
    'proposed' | 'confirmed' | 'unresolved' | 'skipped'."""
    value = normalize_genre(proposal.get("genre"))
    review_row = db.scalar(select(Issue).where(
        Issue.file_id == f.id, Issue.type == GENRE_REVIEW_TYPE,
        Issue.field == "genre"))
    if value is None:
        return "unresolved"
    current = normalize_genre(f.genre)
    if current is not None and value.lower() == current.lower():
        # Genere confermato: una genre_review aperta non ha più ragione d'essere.
        if review_row is not None and review_row.status == "open":
            db.delete(review_row)
        return "confirmed"

    fix = {"field": "genre", "action": "retag", "to": value,
           "source": "ai", "confidence": proposal.get("confidence", "low")}
    detail = f"AI: genre → {value}"
    open_rows = db.scalars(select(Issue).where(
        Issue.file_id == f.id, Issue.field == "genre",
        Issue.status == "open")).all()
    by_type = {r.type: r for r in open_rows}

    fillable = next((by_type[t] for t in _FILLABLE_TYPES if t in by_type), None)
    if fillable is not None:
        if (fillable.suggested_fix_json or {}).get("source") == "provider":
            return "skipped"  # provider > AI, mai sovrascrivere
        fillable.suggested_fix_json = fix
        fillable.updated_at = utcnow()
        return "proposed"
    if any(r.type != GENRE_REVIEW_TYPE for r in open_rows):
        return "skipped"  # es. provider_override aperto: niente doppioni
    if review_row is None:
        db.add(Issue(file_id=f.id, type=GENRE_REVIEW_TYPE, field="genre",
                     severity="info", detail=detail, suggested_fix_json=fix,
                     status="open"))
        return "proposed"
    if review_row.status == "open":
        review_row.suggested_fix_json = fix
        review_row.detail = detail
        review_row.updated_at = utcnow()
        return "proposed"
    return "skipped"  # accepted/dismissed: decisione utente


def review(db: Session, *, mb, discogs, ai_fn, folder: str | None = None,
           genre: str | None = None, redo: bool = False,
           batch_size: int = _BATCH, on_progress=None) -> dict:
    """Loop principale: batch di file → lookup provider → una chiamata AI →
    applicazione esiti + commit. Un batch AI fallito conta come unresolved e il
    job prosegue col successivo."""
    files = db.scalars(_candidates_stmt(folder, genre, redo)).all()
    total = len(files)
    res = {"configured": True, "files": total, "proposed": 0, "confirmed": 0,
           "unresolved": 0, "skipped": 0}
    done = 0
    for start in range(0, total, batch_size):
        batch = files[start:start + batch_size]
        items = []
        for f in batch:
            if on_progress is not None:
                on_progress(done + len(items), total, "looking_up")
            items.append({
                "artist": f.artist, "title": f.title, "album": f.album,
                "label": f.label, "current_genre": f.genre,
                "candidates": _provider_candidates(f, mb=mb, discogs=discogs),
            })
        if on_progress is not None:
            on_progress(done, total, "reviewing")
        try:
            results = ai_fn(items)
        except Exception:  # noqa: BLE001 — un batch fallito non ferma il job
            results = [None] * len(batch)
        for f, proposal in zip(batch, results):
            res[_apply_proposal(db, f, proposal or {})] += 1
            f.genre_reviewed_at = utcnow()
        done += len(batch)
        db.commit()
        if on_progress is not None:
            on_progress(done, total, "reviewing")
    return res
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_genre_review_service.py -v`
Expected: PASS (tutti)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/genre_review.py backend/tests/test_genre_review_service.py
git commit -m "feat(genre-review): service core con provider, AI e issue genre_review"
```

---

### Task 5: Job in background + router + wiring

**Files:**
- Create: `backend/app/services/genre_review_job.py`
- Create: `backend/app/routers/genre_review.py`
- Modify: `backend/app/schemas.py` (dopo `ProviderRescanBody`)
- Modify: `backend/app/main.py` (import + include_router)
- Test: `backend/tests/test_genre_review_api.py` (nuovo)

**Interfaces:**
- Consumes: `genre_review.review` / `count_candidates` (Task 4), `ai_tags.is_configured` (esistente).
- Produces:
  - `POST /api/genre-review` (body `{redo, folder, genre}`) → snapshot job o `{"configured": false, "status": "idle"}`
  - `GET /api/genre-review/status` → `{status, phase, processed, total, result, error, started_at, finished_at}`
  - `GET /api/genre-review/preview?redo=&folder=&genre=` → `{"configured": bool, "files": int}`

- [ ] **Step 1: Write the failing tests**

Crea `backend/tests/test_genre_review_api.py`:

```python
"""Router del job revisione generi: start/status/preview."""

import time

from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile
from app.services import genre_review_job


def _seed(db, fid, **kw):
    db.add(AudioFile(id=fid, root_id=1, path=f"/m/{fid}.mp3", ext="mp3",
                     size_bytes=1, hash_method="file", status="present",
                     has_cover=False, **kw))
    db.commit()


def test_start_without_key_not_configured(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as client:
        r = client.post("/api/genre-review").json()
        assert r["configured"] is False


def test_start_passes_body_to_job(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    captured = {}

    def fake_start(folder=None, genre=None, redo=False):
        captured.update(folder=folder, genre=genre, redo=redo)
        return {"status": "running"}

    monkeypatch.setattr(genre_review_job, "start_job", fake_start)
    with TestClient(app) as client:
        r = client.post("/api/genre-review",
                        json={"folder": "House", "redo": True}).json()
        assert r["status"] == "running"
        assert captured == {"folder": "House", "genre": None, "redo": True}


def test_status_returns_job_state(db):
    with TestClient(app) as client:
        r = client.get("/api/genre-review/status").json()
        assert r["status"] in ("idle", "running", "done", "error")


def test_preview_counts_candidates(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    _seed(db, 1, artist="A", title="T")
    with TestClient(app) as client:
        r = client.get("/api/genre-review/preview").json()
        assert r == {"configured": True, "files": 1}


def test_job_runs_review_and_finishes(db, monkeypatch):
    """start_job → thread → review mockata → stato done col risultato."""
    from app.services import genre_review as gr_service

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    result = {"configured": True, "files": 0, "proposed": 0, "confirmed": 0,
              "unresolved": 0, "skipped": 0}
    monkeypatch.setattr(gr_service, "review", lambda *a, **k: result)
    state = genre_review_job.start_job()
    assert state["status"] == "running"
    for _ in range(100):  # max ~5s
        if genre_review_job.job_state()["status"] != "running":
            break
        time.sleep(0.05)
    final = genre_review_job.job_state()
    assert final["status"] == "done"
    assert final["result"] == result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_genre_review_api.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.genre_review_job'`

- [ ] **Step 3: Write the implementation**

Crea `backend/app/services/genre_review_job.py`:

```python
"""Job di revisione generi in background. Mono-job con stato in memoria (come
provider_rescan_job): la UI lancia e poi fa polling di job_state()."""

import logging
import threading

from app.core.config import settings
from app.db import SessionLocal
from app.models import utcnow
from app.services import ai_tags, genre_review

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle", "phase": None, "processed": 0, "total": 0,
    "result": None, "error": None, "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run(folder, genre, redo) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        from app.integrations.discogs_meta import DiscogsMetaClient
        from app.integrations.musicbrainz import MusicBrainzProvider

        mb = MusicBrainzProvider(user_agent=settings.musicbrainz_user_agent)
        discogs = DiscogsMetaClient()
        result = genre_review.review(
            db, mb=mb, discogs=discogs, ai_fn=ai_tags.review_genres,
            folder=folder, genre=genre, redo=redo, on_progress=on_progress)
        with _lock:
            _state.update(status="done", phase=None, result=result,
                          finished_at=utcnow().isoformat())
        logger.info("Revisione generi completata: %s", result)
    except Exception as exc:  # noqa: BLE001 — il job non deve propagare
        logger.exception("Revisione generi fallita")
        with _lock:
            _state.update(status="error", error=str(exc),
                          finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job(folder=None, genre=None, redo=False) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(
            status="running", phase="looking_up", processed=0, total=0,
            result=None, error=None, started_at=utcnow().isoformat(),
            finished_at=None,
        )
        snapshot = dict(_state)
    threading.Thread(target=_run, args=(folder, genre, redo),
                     daemon=True).start()
    return snapshot
```

In `backend/app/schemas.py`, dopo `ProviderRescanBody`:

```python
class GenreReviewBody(BaseModel):
    folder: str | None = None
    genre: str | None = None
    redo: bool = False
```

Crea `backend/app/routers/genre_review.py`:

```python
"""Router del job 'Revisione generi AI': start/status/preview. Sottile."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.schemas import GenreReviewBody
from app.services import ai_tags, apply_job, genre_review, genre_review_job, scan_job

router = APIRouter(prefix="/api/genre-review", tags=["genre-review"])


@router.post("", response_model=dict)
def genre_review_start(body: GenreReviewBody | None = None):
    if not ai_tags.is_configured():
        return {"configured": False, "status": "idle"}
    if scan_job.is_running() or apply_job.is_running():
        raise api_error(409, "scan_or_apply_running", "Scan or apply in progress")
    b = body or GenreReviewBody()
    return genre_review_job.start_job(folder=b.folder, genre=b.genre, redo=b.redo)


@router.get("/status", response_model=dict)
def genre_review_status():
    return genre_review_job.job_state()


@router.get("/preview", response_model=dict)
def genre_review_preview(redo: bool = False, folder: str | None = None,
                         genre: str | None = None,
                         db: Session = Depends(get_db)):
    return {"configured": ai_tags.is_configured(),
            "files": genre_review.count_candidates(
                db, folder=folder, genre=genre, redo=redo)}
```

In `backend/app/main.py`: aggiungi `genre_review` all'import
`from app.routers import (...)` (in ordine alfabetico) e, accanto agli altri:

```python
app.include_router(genre_review.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_genre_review_api.py -v`
Expected: PASS (tutti e 5)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/genre_review_job.py backend/app/routers/genre_review.py backend/app/schemas.py backend/app/main.py backend/tests/test_genre_review_api.py
git commit -m "feat(genre-review): job in background + endpoints start/status/preview"
```

---

### Task 6: Rimozione del vecchio "Suggerisci generi" (backend)

**Files:**
- Modify: `backend/app/routers/issues.py` (rimuovere l'endpoint `ai_suggest_genre`, righe ~176-232)
- Modify: `backend/app/services/ai_tags.py` (rimuovere `_GENRE_PROMPT`, `_GenreGuess`, `_GenreGuesses`, `suggest_genres`)
- Delete: `backend/tests/test_ai_suggest_genre_api.py`

**Interfaces:**
- Consumes: nulla. Il Task 5 deve essere già committato (il job sostituisce l'endpoint).
- Produces: `POST /api/issues/ai-suggest-genre` non esiste più (404).

- [ ] **Step 1: Remove the endpoint and helpers**

In `backend/app/routers/issues.py` elimina l'intera funzione decorata
`@router.post("/ai-suggest-genre", ...)` (da `@router.post("/ai-suggest-genre"...`
fino al `return {...}` compreso, prima di `_PROVIDER_TYPES`). Attenzione: la
funzione `_describe` interna va via con lei. L'endpoint `/ai-suggest` (artist/
title) resta.

In `backend/app/services/ai_tags.py` elimina il blocco da `_GENRE_PROMPT = (`
fino alla fine di `suggest_genres` (tutto ciò che segue la funzione `suggest`).

Elimina il file di test:

```bash
git rm backend/tests/test_ai_suggest_genre_api.py
```

- [ ] **Step 2: Verify no stale references**

```bash
grep -rn "suggest_genres\|ai-suggest-genre\|_GenreGuess\|_GENRE_PROMPT" backend/app backend/tests
```

Expected: nessun risultato.

- [ ] **Step 3: Run the full backend suite**

Run: `backend/.venv/bin/python -m pytest backend/tests -q`
Expected: PASS (nessun test residuo dipende dal vecchio endpoint)

- [ ] **Step 4: Commit**

```bash
git add -A backend
git commit -m "refactor(issues): rimosso ai-suggest-genre, sostituito dal job genre-review"
```

---

### Task 7: Frontend — client API, i18n, jobs bar

**Files:**
- Modify: `frontend/lib/api.ts` (rimuovere `aiSuggestGenres`; aggiungere client genre-review)
- Modify: `frontend/lib/i18n/en.ts` e `frontend/lib/i18n/it.ts`
- Modify: `frontend/components/jobs-provider.tsx`

**Interfaces:**
- Consumes: endpoints del Task 5.
- Produces (usati dal Task 8):
  - `genreReview(body?: GenreReviewBody): Promise<GenreReviewJobState>`
  - `genreReviewStatus(): Promise<GenreReviewJobState>`
  - `genreReviewPreview(): Promise<{ configured: boolean; files: number }>`
  - `useJobs()` espone `genreReviewJob: GenreReviewJobState` e `startGenreReview(body?)`
  - chiavi i18n: `jobs.genreReview`, `issues.genreReviewBtn`, `issues.genreReviewDesc`, `issues.genreReviewConfirm(files)`, `issues.genreReviewNote(proposed, confirmed, unresolved)`, `issues.genreReviewFailed`, label tipo issue `genre_review`.

- [ ] **Step 1: api.ts**

In `frontend/lib/api.ts`: elimina la funzione `aiSuggestGenres` (l'interfaccia
`AiSuggestResult` resta: la usa `aiSuggestTags`). Dopo il blocco
`providerRescanStatus` aggiungi (stesso stile di `ProviderRescanJobState`):

```ts
export interface GenreReviewResult {
  configured: boolean;
  files: number;
  proposed: number;
  confirmed: number;
  unresolved: number;
  skipped: number;
}
export interface GenreReviewJobState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  result: GenreReviewResult | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}
export interface GenreReviewBody {
  folder?: string | null;
  genre?: string | null;
  redo?: boolean;
}
export function genreReview(body: GenreReviewBody = {}) {
  return apiSend<GenreReviewJobState>("POST", "/api/genre-review", body);
}
export function genreReviewStatus() {
  return apiGet<GenreReviewJobState>("/api/genre-review/status");
}
export function genreReviewPreview() {
  return apiGet<{ configured: boolean; files: number }>("/api/genre-review/preview");
}
```

(Se le helper si chiamano diversamente da `apiGet`/`apiSend`, usare quelle del
file — vedi `providerRescan` come riferimento.)

- [ ] **Step 2: i18n**

`frontend/lib/i18n/en.ts`:

- In `ISSUE_TYPE_LABELS_EN` aggiungi: `genre_review: "Genre to review",`
- In `jobs` aggiungi: `genreReview: "Genre review",`
- Nella sezione `issues`: **rimuovi** `aiGenresBtn`, `aiGenresNote`,
  `enrichAiGenresDesc`; **aggiungi**:

```ts
    genreReviewBtn: "Review genres with AI",
    genreReviewDesc: "Reviews every genre in the library (providers + web search) and proposes corrections.",
    genreReviewConfirm: (files: number) =>
      `The AI will review ${files} tracks using the providers and paid web searches (a few dollars per thousand tracks at most). Proceed?`,
    genreReviewNote: (proposed: number, confirmed: number, unresolved: number) =>
      `Genre review: ${proposed} change proposals, ${confirmed} confirmed${unresolved > 0 ? `, ${unresolved} unresolved` : ""} — review and accept with ✓.`,
    genreReviewFailed: "Genre review failed",
```

`frontend/lib/i18n/it.ts` (speculare — stesse chiavi, tradotte):

- label tipo issue: `genre_review: "Genere da rivedere",`
- `jobs`: `genreReview: "Revisione generi",`
- `issues`: rimuovi le tre chiavi vecchie; aggiungi:

```ts
    genreReviewBtn: "Rivedi generi con AI",
    genreReviewDesc: "Rivede tutti i generi della libreria (provider + ricerca web) e propone correzioni.",
    genreReviewConfirm: (files) =>
      `L'AI rivedrà ${files} tracce usando i provider e ricerche web a pagamento (al massimo pochi euro per migliaia di tracce). Procedere?`,
    genreReviewNote: (proposed, confirmed, unresolved) =>
      `Revisione generi: ${proposed} proposte di modifica, ${confirmed} confermati${unresolved > 0 ? `, ${unresolved} non risolti` : ""} — rivedi e accetta con ✓.`,
    genreReviewFailed: "Revisione generi fallita",
```

Nota: in `it.ts` i tipi dei parametri sono inferiti da `typeof en` — niente
annotazioni. Se `it.ts` mappa le label dei tipi issue in una struttura propria,
aggiungere `genre_review` lì nello stesso punto in cui compare `dirty_genre`.

- [ ] **Step 3: jobs-provider.tsx**

In `frontend/components/jobs-provider.tsx`, sul modello di `rescan`:

- import: aggiungi `genreReviewStatus, genreReview as apiGenreReview, type GenreReviewJobState, type GenreReviewBody` a quelli da `@/lib/api`.
- Stato: `const [genreReviewJob, setGenreReviewJob] = useState<GenreReviewJobState>(IDLE);`
- In `JobsApi`: `genreReviewJob: GenreReviewJobState;` e
  `startGenreReview: (body?: GenreReviewBody) => Promise<void>;` (+ default nel
  `createContext`: `genreReviewJob: IDLE, startGenreReview: async () => {}`).
- In `pollOnce`, dopo il blocco integrity:

```ts
    try {
      const gr = await genreReviewStatus();
      if (alive.current) setGenreReviewJob(gr);
    } catch { /* backend offline */ }
```

- Starter:

```ts
  const startGenreReview = useCallback(async (body: GenreReviewBody = {}) => {
    const gr = await apiGenreReview(body);
    setGenreReviewJob(gr);
  }, []);
```

- Aggiungi `genreReviewJob`/`startGenreReview` all'oggetto `useMemo` e alle sue deps.
- In `active`, dopo il ramo `integrity`:

```ts
    : genreReviewJob.status === "running"
    ? { label: t.jobs.genreReview, job: genreReviewJob }
```

- [ ] **Step 4: Typecheck/build**

```bash
cd frontend && npm run build
```

Expected: la build fallisce SOLO in `app/issues/page.tsx` (usa ancora
`aiSuggestGenres` / `t.issues.aiGenresBtn`, rimossi qui e sistemati nel Task 8).
Se fallisce altrove, correggere prima di procedere. (In alternativa eseguire
Task 7+8 e buildare una volta sola alla fine del Task 8 — ma committare comunque
separatamente.)

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts frontend/components/jobs-provider.tsx
git commit -m "feat(frontend): client e jobs bar per la revisione generi AI"
```

---

### Task 8: Frontend — pagina ISSUES (bottone + conferma + esito)

**Files:**
- Modify: `frontend/app/issues/page.tsx`

**Interfaces:**
- Consumes: `genreReviewPreview`, `useJobs().genreReviewJob` / `startGenreReview`, chiavi i18n del Task 7.

- [ ] **Step 1: Imports e stato**

In `frontend/app/issues/page.tsx`:

- Import da `@/lib/api`: togli `aiSuggestGenres`, aggiungi `genreReviewPreview`.
- Destruttura da `useJobs()`: aggiungi `genreReviewJob, startGenreReview`.
- Sostituisci lo stato `genreBusy` (che resta, riusato per il fetch preview) e
  aggiungi:

```tsx
  const [genreModal, setGenreModal] = useState<{ files: number } | null>(null);
  const genreReviewRunning = genreReviewJob.status === "running";
```

- [ ] **Step 2: Sostituisci `onAiGenres` con il flusso preview → conferma → start**

Elimina la funzione `onAiGenres` e aggiungi al suo posto:

```tsx
  const onGenreReviewClick = async () => {
    setActionError(null);
    setAiNote(null);
    setGenreBusy(true);
    try {
      const p = await genreReviewPreview();
      if (!p.configured) setActionError(t.issues.aiNotConfigured);
      else setGenreModal({ files: p.files });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.common.error);
    } finally {
      setGenreBusy(false);
    }
  };

  const onGenreReviewStart = async () => {
    setGenreModal(null);
    try {
      await startGenreReview({});
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.common.error);
    }
  };
```

- [ ] **Step 3: Esito del job (running→done/error)**

Accanto all'effetto `prevRescan` (stesso pattern) aggiungi:

```tsx
  // La revisione generi gira nel job globale: al fronte running→done ricarico
  // le issue e mostro il riepilogo; su errore lo segnalo.
  const prevGenreReview = useRef(genreReviewJob.status);
  useEffect(() => {
    if (prevGenreReview.current === "running" && genreReviewJob.status === "done") {
      load();
      const r = genreReviewJob.result;
      if (r) setAiNote(t.issues.genreReviewNote(r.proposed, r.confirmed, r.unresolved));
    }
    if (prevGenreReview.current === "running" && genreReviewJob.status === "error") {
      setActionError(genreReviewJob.error || t.issues.genreReviewFailed);
    }
    prevGenreReview.current = genreReviewJob.status;
  }, [genreReviewJob.status, genreReviewJob.result, genreReviewJob.error, load, t]);
```

- [ ] **Step 4: Voce in `enrichSources` e modal di conferma**

In `enrichSources` sostituisci la voce `onAiGenres` con:

```tsx
    { group: "enrich", onClick: onGenreReviewClick, busy: genreBusy || genreReviewRunning,
      label: genreBusy || genreReviewRunning ? t.issues.aiBusy : t.issues.genreReviewBtn,
      desc: t.issues.genreReviewDesc, tag: t.issues.enrichAi },
```

Dopo il `<Modal>` del rescan provider aggiungi:

```tsx
        <Modal
          open={genreModal !== null}
          onClose={() => setGenreModal(null)}
          title={t.issues.genreReviewBtn}
          footer={<>
            <Button variant="ghost" size="sm" onClick={() => setGenreModal(null)}>{t.common.cancel}</Button>
            <Button variant="primary" size="sm" onClick={onGenreReviewStart}>{t.issues.modalStart}</Button>
          </>}
        >
          <p className="text-sm text-muted">{t.issues.genreReviewConfirm(genreModal?.files ?? 0)}</p>
        </Modal>
```

- [ ] **Step 5: Build e verifica residui**

```bash
cd frontend && npm run build
grep -rn "aiSuggestGenres\|aiGenresBtn\|aiGenresNote\|enrichAiGenresDesc" frontend
```

Expected: build PASS; grep senza risultati.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/issues/page.tsx
git commit -m "feat(frontend): bottone Revisione generi AI con conferma, via il vecchio Suggerisci generi"
```

---

### Task 9: Verifica finale end-to-end

**Files:** nessuna modifica prevista (solo fix eventuali).

- [ ] **Step 1: Suite backend completa**

Run: `backend/.venv/bin/python -m pytest backend/tests -q`
Expected: tutti PASS, nessun warning nuovo (`filterwarnings = error`).

- [ ] **Step 2: Lint + build frontend**

```bash
cd frontend && npm run lint && npm run build
```

Expected: PASS.

- [ ] **Step 3: Smoke test manuale (facoltativo ma consigliato)**

Con backend (`.venv/bin/uvicorn app.main:app --reload --port 8010` da
`backend/`) e frontend (`npm run dev`) avviati e `ANTHROPIC_API_KEY` nel
`.env`: in ISSUES cliccare "Rivedi generi con AI", confermare su una library
piccola (o con filtro cartella), verificare barra di progresso, issue
`genre_review` in tabella, nota di riepilogo a fine job.

- [ ] **Step 4: Commit finale (solo se ci sono fix)**

```bash
git add -A && git commit -m "fix(genre-review): sistemazioni post-verifica"
```
