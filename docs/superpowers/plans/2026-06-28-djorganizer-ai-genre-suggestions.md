# DjOrganizer — "Suggerisci generi (AI)" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) — scelta utente. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Secondo bottone in ISSUES che usa Claude Haiku per proporre un genere (da artista+titolo) nelle issue `missing_metadata`/`genre`, da rivedere e accettare col flusso esistente.

**Architecture:** Backend: funzione `ai_tags.suggest_genres()` (structured output, mockabile) + endpoint sottile `POST /api/issues/ai-suggest-genre` che costruisce per ogni file la descrizione "artista – titolo" effettiva (tag o `suggested_fix`) e imposta i `suggested_fix` delle issue genere (status `open`). Frontend: `aiSuggestGenres()` + bottone "✨ Suggerisci generi". Riusa il `✓ accetta` esistente → `/fix` → PLAN.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic v2, `anthropic` SDK, pytest · Next 16 / React 19 / TS.

## Global Constraints

- Modello **`claude-haiku-4-5`**, key da env **`ANTHROPIC_API_KEY`** (caricata da `app/main.py` via `load_dotenv`). Senza key → `{"configured": false, ...}`.
- L'AI imposta `suggested_fix_json = {"field": "genre", "action": "retag", "to": value}` lasciando `status="open"` (genere è in `_RETAGGABLE` → accettabile col `/fix`). Niente disco, niente auto-accept.
- Scope: solo issue `open`, `type=="missing_metadata"`, `field=="genre"`, `suggested_fix_json is None`. **Un solo genere**, normalizzato. Niente anno/label.
- JSON-null filtrato **in Python** (la colonna JSON serializza None come `'null'`). Import `anthropic` **lazy**. Manda **artista+titolo** (o nome file in fallback), mai l'audio.
- Backend test **pristine** (`filterwarnings = error`), `ai_tags.suggest_genres` mockato (niente rete). Frontend test = `npm run lint` + `npm run build`.

---

## Task 1: Backend — `ai_tags.suggest_genres` + endpoint `POST /api/issues/ai-suggest-genre`

**Files:**
- Modify: `backend/app/services/ai_tags.py` (aggiunge `suggest_genres`)
- Modify: `backend/app/routers/issues.py` (endpoint `/ai-suggest-genre`)
- Test: `backend/tests/test_ai_suggest_genre_api.py`

**Interfaces:**
- Consumes: `ai_tags.is_configured()` (esistente).
- Produces: `ai_tags.suggest_genres(descriptions: list[str]) -> list[str | None]` (allineato per indice); `POST /api/issues/ai-suggest-genre` → `{configured, files, suggested, unresolved}`.

- [ ] **Step 1: Aggiungi `suggest_genres` in `backend/app/services/ai_tags.py`**

Aggiungi dopo `suggest()`:
```python
_GENRE_PROMPT = (
    "Sei un assistente che assegna il GENERE musicale a tracce da DJ "
    "(prevalentemente musica elettronica). Per ogni traccia numerata qui sotto "
    "(formato 'Artista - Titolo') restituisci il genere principale più probabile, "
    "UNO solo (non una lista), normalizzato con casing canonico (es. 'Tech House', "
    "'Acid Techno', 'Drum & Bass'). Mantieni lo STESSO ordine, un elemento per "
    "traccia. Se non sei ragionevolmente sicuro mettilo a null; non inventare "
    "valori spazzatura (niente URL, niente 'Unbekannt', niente 'Music')."
)


class _GenreGuess(BaseModel):
    genre: str | None = None


class _GenreGuesses(BaseModel):
    items: list[_GenreGuess]


def suggest_genres(descriptions: list[str]) -> list[str | None]:
    """Ritorna un genere (o None) per ciascuna descrizione, allineato per indice."""
    if not descriptions:
        return []
    from anthropic import Anthropic  # import lazy

    client = Anthropic()
    out: list[str | None] = []
    for i in range(0, len(descriptions), _CHUNK):
        chunk = descriptions[i:i + _CHUNK]
        listing = "\n".join(f"{j}. {d}" for j, d in enumerate(chunk))
        resp = client.messages.parse(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": f"{_GENRE_PROMPT}\n\n{listing}"}],
            output_format=_GenreGuesses,
        )
        items = resp.parsed_output.items if resp.parsed_output else []
        for k in range(len(chunk)):
            g = items[k] if k < len(items) else _GenreGuess()
            out.append(g.genre or None)
    return out
```

- [ ] **Step 2: Scrivi i test che falliscono**

Crea `backend/tests/test_ai_suggest_genre_api.py`:
```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue
from app.services import ai_tags


def _seed_genre(db, file_id, path, *, artist=None, title=None,
                artist_fix=None, title_fix=None):
    db.add(AudioFile(id=file_id, root_id=1, path=path, ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist=artist, title=title))
    db.add(Issue(file_id=file_id, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=None, status="open"))
    for field, fixval in (("artist", artist_fix), ("title", title_fix)):
        if fixval is not None:
            db.add(Issue(file_id=file_id, type="missing_required_tag", field=field,
                         severity="error", detail=f"{field} mancante",
                         suggested_fix_json={"field": field, "action": "retag",
                                             "to": fixval}, status="open"))
    db.commit()


def test_genre_uses_effective_artist_title(db, monkeypatch):
    # tag vuoti, ma artista/titolo presenti nei suggested_fix (feature precedente)
    _seed_genre(db, 1, "/m/x.mp3", artist_fix="ANNA", title_fix="Hidden Beauties")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    captured = {}

    def fake(descriptions):
        captured["descs"] = descriptions
        return ["Tech House"]

    monkeypatch.setattr(ai_tags, "suggest_genres", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest-genre").json()
        assert r == {"configured": True, "files": 1, "suggested": 1, "unresolved": 0}
        assert captured["descs"] == ["ANNA - Hidden Beauties"]
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        genre = next(i for i in rows if i["field"] == "genre")
        assert genre["suggested_fix_json"] == {"field": "genre", "action": "retag",
                                               "to": "Tech House"}
        assert genre["status"] == "open"


def test_genre_falls_back_to_filename(db, monkeypatch):
    _seed_genre(db, 2, "/m/Some Artist - Some Track.mp3")  # nessun artista/titolo noto
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    captured = {}

    def fake(descriptions):
        captured["descs"] = descriptions
        return ["Acid"]

    monkeypatch.setattr(ai_tags, "suggest_genres", fake)
    with TestClient(app) as client:
        client.post("/api/issues/ai-suggest-genre")
        assert captured["descs"] == ["Some Artist - Some Track"]


def test_genre_no_key(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest-genre").json()
        assert r["configured"] is False and r["suggested"] == 0


def test_genre_unresolved(db, monkeypatch):
    _seed_genre(db, 3, "/m/y.mp3", artist="Live", title="Set")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(ai_tags, "suggest_genres", lambda d: [None])
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest-genre").json()
        assert r["suggested"] == 0 and r["unresolved"] == 1


def test_genre_skips_already_suggested(db, monkeypatch):
    db.add(AudioFile(id=4, root_id=1, path="/m/z.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(Issue(file_id=4, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante",
                 suggested_fix_json={"field": "genre", "action": "retag", "to": "House"},
                 status="open"))
    db.commit()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    called = {"n": 0}

    def fake(d):
        called["n"] += 1
        return ["X" for _ in d]

    monkeypatch.setattr(ai_tags, "suggest_genres", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest-genre").json()
        assert r["files"] == 0 and r["suggested"] == 0
        assert called["n"] == 0
```

- [ ] **Step 3: Lancia i test, verifica FAIL**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ai_suggest_genre_api.py -q`
Expected: FAIL (404 sull'endpoint inesistente).

- [ ] **Step 4: Aggiungi l'endpoint in `backend/app/routers/issues.py`**

In fondo al file (gli import `os`, `select`, `ai_tags` ci sono già dalla feature precedente):
```python
@router.post("/ai-suggest-genre", response_model=dict)
def ai_suggest_genre(db: Session = Depends(get_db)):
    if not ai_tags.is_configured():
        return {"configured": False, "files": 0, "suggested": 0, "unresolved": 0}
    rows = db.execute(
        select(Issue, AudioFile)
        .join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.type == "missing_metadata",
               Issue.field == "genre")
    ).all()
    todo = [(issue, f) for issue, f in rows if issue.suggested_fix_json is None]
    if not todo:
        return {"configured": True, "files": 0, "suggested": 0, "unresolved": 0}

    file_ids = [f.id for _, f in todo]
    # artista/titolo "effettivi" dai suggested_fix delle issue artist/title
    at_issues = db.scalars(
        select(Issue).where(Issue.file_id.in_(file_ids),
                            Issue.field.in_(("artist", "title")))
    ).all()
    sugg: dict[int, dict[str, str]] = {}
    for iss in at_issues:
        fix = iss.suggested_fix_json
        if fix and fix.get("to"):
            sugg.setdefault(iss.file_id, {})[iss.field] = fix["to"]

    def _describe(f) -> str:
        artist = f.artist or sugg.get(f.id, {}).get("artist")
        title = f.title or sugg.get(f.id, {}).get("title")
        if artist and title:
            return f"{artist} - {title}"
        if artist or title:
            return artist or title
        return os.path.splitext(os.path.basename(f.path))[0]

    genres = ai_tags.suggest_genres([_describe(f) for _, f in todo])

    suggested = 0
    unresolved = 0
    for (issue, _f), genre in zip(todo, genres):
        value = (genre or "").strip()
        if value:
            issue.suggested_fix_json = {"field": "genre", "action": "retag", "to": value}
            issue.updated_at = utcnow()
            suggested += 1
        else:
            unresolved += 1
    db.commit()
    return {"configured": True, "files": len(todo),
            "suggested": suggested, "unresolved": unresolved}
```

- [ ] **Step 5: Lancia i test, verifica PASS**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ai_suggest_genre_api.py -q`
Expected: PASS (5 test).

- [ ] **Step 6: Suite intera (no regressioni, pristine)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: tutti verdi, zero warning.

- [ ] **Step 7: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/services/ai_tags.py backend/app/routers/issues.py backend/tests/test_ai_suggest_genre_api.py
git commit -m "feat(api): POST /api/issues/ai-suggest-genre — Haiku propone il genere da artista+titolo"
```

---

## Task 2: Frontend — `aiSuggestGenres()` + bottone "✨ Suggerisci generi"

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/issues/page.tsx`

**Interfaces:**
- Consumes: `apiSend`, `AiSuggestResult` (esistenti).

- [ ] **Step 1: Aggiungi `aiSuggestGenres()` in `frontend/lib/api.ts`**

Dopo `aiSuggestTags()`:
```ts
export function aiSuggestGenres() {
  return apiSend<AiSuggestResult>("POST", "/api/issues/ai-suggest-genre");
}
```

- [ ] **Step 2: Aggiungi stato, handler, bottone in `frontend/app/issues/page.tsx`**

Aggiorna l'import da `@/lib/api` per includere `aiSuggestGenres`:
```tsx
import {
  listIssues, listSources, setIssueStatus, fixIssue, bulkIssues, aiSuggestTags, aiSuggestGenres,
  type Issue, type ScanRoot,
} from "@/lib/api";
```

Accanto a `aiBusy` aggiungi lo stato del genere:
```tsx
  const [genreBusy, setGenreBusy] = useState(false);
```

Dopo `onAiSuggest`, aggiungi l'handler gemello (riusa `aiNote`):
```tsx
  const onAiGenres = async () => {
    setActionError(null);
    setAiNote(null);
    setGenreBusy(true);
    try {
      const r = await aiSuggestGenres();
      if (!r.configured) {
        setActionError("Imposta ANTHROPIC_API_KEY nel backend per usare l'AI.");
      } else {
        load();
        setAiNote(
          `${r.suggested} generi suggeriti (bassa confidenza, rivedi)${r.unresolved > 0 ? `, ${r.unresolved} non ricavabili` : ""} — accetta col ✓.`,
        );
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Errore");
    } finally {
      setGenreBusy(false);
    }
  };
```

Passa le prop alla `Marginalia` (accanto a `onAiSuggest`/`aiBusy`):
```tsx
          onAiSuggest={onAiSuggest} aiBusy={aiBusy}
          onAiGenres={onAiGenres} genreBusy={genreBusy}
```

Aggiorna firma e tipi di `Marginalia`:
```tsx
function Marginalia({ total, bySev, byType, accepted, onAcceptFixable, onDismissInfo, onAiSuggest, aiBusy, onAiGenres, genreBusy }: {
  total: number;
  bySev: Record<string, number>;
  byType: Record<string, number>;
  accepted: number;
  onAcceptFixable: () => void;
  onDismissInfo: () => void;
  onAiSuggest: () => void;
  aiBusy: boolean;
  onAiGenres: () => void;
  genreBusy: boolean;
}) {
```

Nel blocco bottoni, sotto "✨ Risolvi con AI", aggiungi il secondo bottone:
```tsx
        <Button variant="primary" size="sm" onClick={onAiGenres} disabled={genreBusy}>
          {genreBusy ? "AI in corso…" : "✨ Suggerisci generi"}
        </Button>
```

- [ ] **Step 3: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 4: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/lib/api.ts frontend/app/issues/page.tsx
git commit -m "feat(fe): ISSUES — bottone 'Suggerisci generi' (AI, bassa confidenza)"
```

---

## Self-Review

**1. Spec coverage:**
- Endpoint `/ai-suggest-genre` (set suggested_fix su genere, status open, no-key, unresolved, skip già-suggeriti) → Task 1 ✓
- Descrizione effettiva artista+titolo (tag → suggested_fix → filename) → Task 1 `_describe` + test `uses_effective_artist_title` / `falls_back_to_filename` ✓
- `ai_tags.suggest_genres` mockabile, Haiku, structured output, un genere normalizzato → Task 1 ✓
- Bottone separato "Suggerisci generi", busy proprio, nota bassa-confidenza, key-mancante Alert → Task 2 ✓
- Riuso `✓`/`fixIssue` (genere ∈ `_RETAGGABLE`) → garantito (l'endpoint setta solo `suggested_fix_json`) ✓
- Niente anno/label, niente disco, niente auto-accept → scope endpoint + `status` invariato ✓

**2. Placeholder scan:** nessun TBD/TODO; codice completo.

**3. Type consistency:**
- `suggest_genres(list[str]) -> list[str|None]`, l'endpoint mappa con `zip(todo, genres)` (servizio allinea per indice) ✓
- `suggested_fix_json = {field:"genre", action:"retag", to}` ↔ planner + `_RETAGGABLE` ✓
- `aiSuggestGenres()` → `AiSuggestResult` (riusato) ✓
- `Button variant="primary" size="sm"` + `aiNote`/`Alert` esistenti ✓

---

## Execution Handoff
Esecuzione **inline** (scelta utente) via superpowers:executing-plans.
