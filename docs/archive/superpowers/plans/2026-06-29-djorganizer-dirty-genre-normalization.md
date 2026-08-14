# DjOrganizer — Normalizzazione AI dei generi sporchi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) — scelta utente. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Segnalare i generi *presenti ma sporchi* come issue `dirty_genre` e farli normalizzare dal bottone "Suggerisci genere" (Haiku propone un genere pulito usando il genere attuale come contesto), da accettare → retag → re-apply.

**Architecture:** Inspector aggiunge `_is_dirty_genre` + l'emissione dell'issue `dirty_genre`. L'endpoint `POST /api/issues/ai-suggest-genre` estende la select a `dirty_genre` e arricchisce la descrizione col genere attuale. Frontend: solo ritocco alla nota. Riusa accettazione/plan/apply esistenti.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic v2, `anthropic`, pytest · Next 16 / React 19 / TS.

## Global Constraints

- Regola "sporco" (`_is_dirty_genre`): genere presente e non vuoto, ed uno tra: separatore `,` `/` `;` (NON `&`, NON ` - `, NON `-`); URL (`http`/`://`/`www.`); junk-word ∈ `{unbekannt, unknown, sconosciuto, music, other, various, n/a, none}`. Esiti genere: assente → `missing_metadata/genre` (invariato); sporco → `dirty_genre`; pulito → nulla.
- Endpoint immutato per forma: imposta `suggested_fix_json = {"field":"genre","action":"retag","to":<pulito>}` su issue `open`, JSON-null filtrato **in Python**, no-key → `{configured:false}`. `genre` ∈ `_RETAGGABLE`.
- Test backend **pristine** (`filterwarnings = error`), Haiku mockato. Frontend = `npm run lint` + `npm run build`.

---

## Task 1: Backend — Inspector `dirty_genre` + endpoint esteso

**Files:**
- Modify: `backend/app/services/inspector.py`
- Modify: `backend/app/routers/issues.py` (endpoint `ai_suggest_genre`)
- Test: `backend/tests/test_inspector.py`, `backend/tests/test_ai_suggest_genre_api.py`

**Interfaces:**
- Produces: `inspector._is_dirty_genre(value: str) -> bool`; nuova issue `("dirty_genre", "genre")`. Endpoint `POST /api/issues/ai-suggest-genre` ora copre anche `dirty_genre`.

- [ ] **Step 1: Test Inspector che falliscono**

In `backend/tests/test_inspector.py`, aggiungi in fondo:
```python
def test_dirty_genre_flagged():
    base = dict(artist="A", title="T", year=2020, label="X",
                duration_s=200.0, bitrate=320000, ext="mp3")
    for bad in ["Techno, House, Acid", "Acid/Techno", "http://vk.com/x",
                "https://djsoundtop.com", "Unbekannt", "Music", "Other"]:
        issues = inspect([make_audio_file(1, genre=bad, **base)])
        assert ("dirty_genre", "genre") in _types(issues), bad
        assert ("missing_metadata", "genre") not in _types(issues), bad


def test_clean_genre_not_flagged():
    base = dict(artist="A", title="T", year=2020, label="X",
                duration_s=200.0, bitrate=320000, ext="mp3")
    for ok in ["Techno", "Tech House", "Drum & Bass", "Acid Techno", "Electro - Dance"]:
        issues = inspect([make_audio_file(1, genre=ok, **base)])
        assert ("dirty_genre", "genre") not in _types(issues), ok
        assert ("missing_metadata", "genre") not in _types(issues), ok


def test_missing_genre_still_missing_not_dirty():
    f = make_audio_file(1, artist="A", title="T", genre=None, year=2020, label="X",
                        duration_s=200.0, bitrate=320000, ext="mp3")
    issues = inspect([f])
    assert ("missing_metadata", "genre") in _types(issues)
    assert ("dirty_genre", "genre") not in _types(issues)
```

- [ ] **Step 2: Lancia, verifica FAIL**

Run: `cd backend && .venv/bin/python -m pytest tests/test_inspector.py -q`
Expected: FAIL (dirty_genre non emesso).

- [ ] **Step 3: Implementa in `backend/app/services/inspector.py`**

Dopo `_SPAM_RE` (riga ~12) aggiungi:
```python
_GENRE_SEP_RE = re.compile(r"[,/;]")
_GENRE_JUNK = {"unbekannt", "unknown", "sconosciuto", "music", "other",
               "various", "n/a", "none"}


def _is_dirty_genre(value: str) -> bool:
    s = (value or "").strip()
    if not s:
        return False
    low = s.lower()
    if _GENRE_SEP_RE.search(s):
        return True
    if "http" in low or "://" in s or "www." in low:
        return True
    return low in _GENRE_JUNK
```

In `_inspect_one`, subito dopo il loop `for field in ("genre", "year", "label"):` (quello
che emette `missing_metadata`), aggiungi:
```python
    if _present(f.genre) and _is_dirty_genre(f.genre):
        out.append(IssueComputed(f.id, "dirty_genre", "genre", "warning",
                                 "genere da normalizzare", None))
```

- [ ] **Step 4: Lancia, verifica PASS**

Run: `cd backend && .venv/bin/python -m pytest tests/test_inspector.py -q`
Expected: PASS.

- [ ] **Step 5: Test endpoint che fallisce**

In `backend/tests/test_ai_suggest_genre_api.py`, aggiungi in fondo:
```python
def test_genre_normalizes_dirty(db, monkeypatch):
    db.add(AudioFile(id=9, root_id=1, path="/m/x.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="Plastikman", title="Spastik", genre="Techno, House, Acid"))
    db.add(Issue(file_id=9, type="dirty_genre", field="genre", severity="warning",
                 detail="genere da normalizzare", suggested_fix_json=None, status="open"))
    db.commit()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    captured = {}

    def fake(descriptions):
        captured["descs"] = descriptions
        return ["Techno"]

    monkeypatch.setattr(ai_tags, "suggest_genres", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest-genre").json()
        assert r == {"configured": True, "files": 1, "suggested": 1, "unresolved": 0}
        assert captured["descs"] == ["Plastikman - Spastik [genere attuale: Techno, House, Acid]"]
        rows = client.get("/api/issues", params={"type": "dirty_genre"}).json()
        assert rows[0]["suggested_fix_json"] == {"field": "genre", "action": "retag",
                                                 "to": "Techno"}
        assert rows[0]["status"] == "open"
```

- [ ] **Step 6: Lancia, verifica FAIL**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ai_suggest_genre_api.py::test_genre_normalizes_dirty -q`
Expected: FAIL (l'endpoint non seleziona `dirty_genre`).

- [ ] **Step 7: Estendi l'endpoint in `backend/app/routers/issues.py`**

Nella funzione `ai_suggest_genre`, cambia la `where` della select:
```python
        .where(Issue.status == "open", Issue.field == "genre",
               Issue.type.in_(("missing_metadata", "dirty_genre")))
```
e arricchisci `_describe` col genere attuale (sostituisci la funzione interna):
```python
    def _describe(f) -> str:
        artist = f.artist or sugg.get(f.id, {}).get("artist")
        title = f.title or sugg.get(f.id, {}).get("title")
        if artist and title:
            base = f"{artist} - {title}"
        elif artist or title:
            base = artist or title
        else:
            base = os.path.splitext(os.path.basename(f.path))[0]
        if f.genre and f.genre.strip():
            base = f"{base} [genere attuale: {f.genre.strip()}]"
        return base
```

- [ ] **Step 8: Lancia i test del modulo + suite intera**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ai_suggest_genre_api.py tests/test_inspector.py -q`
Expected: PASS.
Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: tutti verdi, zero warning.

- [ ] **Step 9: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/services/inspector.py backend/app/routers/issues.py backend/tests/test_inspector.py backend/tests/test_ai_suggest_genre_api.py
git commit -m "feat(api): issue dirty_genre + 'Suggerisci genere' normalizza i generi sporchi"
```

---

## Task 2: Frontend — nota "mancanti + sporchi"

**Files:**
- Modify: `frontend/app/issues/page.tsx`

- [ ] **Step 1: Aggiorna la nota in `onAiGenres`**

Sostituisci la stringa della nota:
```tsx
        setAiNote(
          `${r.suggested} generi suggeriti — mancanti + sporchi (bassa confidenza, rivedi)${r.unresolved > 0 ? `, ${r.unresolved} non ricavabili` : ""} — accetta col ✓.`,
        );
```

- [ ] **Step 2: lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 3: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/app/issues/page.tsx
git commit -m "feat(fe): nota 'Suggerisci genere' include i generi sporchi"
```

---

## Self-Review

**1. Spec coverage:**
- Regola `_is_dirty_genre` (separatori/URL/junk, NON `&`/` - `) → Task 1 Step 3 + test Step 1 ✓
- Issue `dirty_genre` (warning, field genre, suggested_fix None) → Task 1 Step 3 ✓
- `missing_metadata` invariato per genere assente → test `test_missing_genre_still_missing_not_dirty` ✓
- Endpoint copre `dirty_genre` + descrizione col genere attuale → Task 1 Step 7 + test Step 5 ✓
- Retag via `_RETAGGABLE`/`✓` → invariato (l'endpoint setta solo suggested_fix) ✓
- Frontend nota → Task 2 ✓

**2. Placeholder scan:** nessun TBD/TODO; codice completo.

**3. Type consistency:**
- `_is_dirty_genre(str) -> bool` ✓
- issue tuple `("dirty_genre", "genre")` coerente tra inspector e test ✓
- `Issue.type.in_(("missing_metadata", "dirty_genre"))` ✓
- descrizione `"{artist} - {title} [genere attuale: {genre}]"` ↔ assert del test ✓
- `suggested_fix_json = {"field":"genre","action":"retag","to":…}` ↔ planner/`_RETAGGABLE` ✓

---

## Execution Handoff
Esecuzione **inline** (scelta utente) via superpowers:executing-plans.
