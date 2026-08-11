# DjOrganizer — "Risolvi con AI" (artist/title da nome file) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) — l'utente ha scelto l'esecuzione inline. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Aggiungere un'azione on-demand in ISSUES che usa Claude Haiku per ricavare artist/title dai nomi file e metterli nei `suggested_fix` delle issue (status `open`), così l'utente li rivede e accetta col flusso esistente.

**Architecture:** Backend: servizio `ai_tags` (import `anthropic` **lazy**, structured output Pydantic, mockabile) + endpoint sottile `POST /api/issues/ai-suggest` che imposta i `suggested_fix`. Frontend: funzione `aiSuggestTags()` + bottone "✨ Risolvi con AI" in ISSUES che ricarica le issue (campi inline pre-riempiti). Riusa il `✓ accetta` esistente → `/fix` → PLAN.

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2.0, Pydantic v2, `anthropic` SDK, pytest. Frontend — Next 16 / React 19 / TS.

## Global Constraints

- Modello: **`claude-haiku-4-5`**. API key da env **`ANTHROPIC_API_KEY`** (default dell'SDK; NON sotto `DJORG_`). Se assente → `{"configured": false, ...}`, niente crash.
- L'AI imposta `suggested_fix_json = {"field", "action":"retag", "to":value}` lasciando `status="open"` (riempitore di suggerimenti; **non** accetta, **non** scrive su disco). Forma compatibile col planner.
- Scope: solo issue `missing_required_tag` con `field ∈ {artist,title}` e `suggested_fix_json is None`. Niente genere/anno/label.
- `import anthropic` **lazy** dentro `suggest()` → il modulo importa senza la dipendenza; i test monkeypatchano `ai_tags.suggest` e non toccano la rete. Manda **solo i nomi file** (stem).
- Backend test **pristine** (`filterwarnings = error`); pattern: fixture `db` semina + `with TestClient(app) as client`. Frontend test = `npm run lint` + `npm run build`.

---

## Task 1: Backend — servizio `ai_tags` + endpoint `POST /api/issues/ai-suggest`

**Files:**
- Modify: `backend/requirements.txt` (aggiunge `anthropic`)
- Create: `backend/app/services/ai_tags.py`
- Modify: `backend/app/routers/issues.py` (endpoint `/ai-suggest`)
- Test: `backend/tests/test_ai_suggest_api.py`

**Interfaces:**
- Produces: `ai_tags.is_configured() -> bool`; `ai_tags.suggest(filenames: list[str]) -> list[dict]` (ogni dict `{"artist": str|None, "title": str|None}`, allineato per indice). `POST /api/issues/ai-suggest` → `{configured: bool, files: int, suggested: int, unresolved: int}`.

- [ ] **Step 1: Aggiungi `anthropic` a requirements e installalo**

In `backend/requirements.txt`, aggiungi una riga `anthropic`. Poi:
```bash
cd ~/Develop/DjOrganizer01/backend && .venv/bin/pip install anthropic
```

- [ ] **Step 2: Crea il servizio `backend/app/services/ai_tags.py`**

```python
"""Estrazione AI di artist/title dai nomi file (Claude Haiku). Import lazy: il
modulo si carica senza il pacchetto `anthropic`; solo suggest() lo richiede.
Mockabile nei test (monkeypatch su ai_tags.suggest)."""

import os

from pydantic import BaseModel

_MODEL = "claude-haiku-4-5"
_CHUNK = 80
_PROMPT = (
    "Sei un assistente che estrae ARTISTA e TITOLO dai nomi di file di tracce "
    "musicali. Il formato tipico è 'Artista - Titolo'. Gestisci prefissi di "
    "numero traccia (es. '01 - ', '1. '), separatori multipli, e suffissi come "
    "'(Original Mix)'. Per ogni nome file numerato qui sotto restituisci un "
    "elemento con artist e title; mantieni lo STESSO ordine, un elemento per "
    "nome file. Se non riesci a determinare un campo con ragionevole certezza, "
    "mettilo a null. Non inventare."
)


class _Guess(BaseModel):
    artist: str | None = None
    title: str | None = None


class _Guesses(BaseModel):
    items: list[_Guess]


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def suggest(filenames: list[str]) -> list[dict]:
    """Ritorna [{'artist': str|None, 'title': str|None}] allineato a `filenames`."""
    if not filenames:
        return []
    from anthropic import Anthropic  # import lazy

    client = Anthropic()
    out: list[dict] = []
    for i in range(0, len(filenames), _CHUNK):
        chunk = filenames[i:i + _CHUNK]
        listing = "\n".join(f"{j}. {name}" for j, name in enumerate(chunk))
        resp = client.messages.parse(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": f"{_PROMPT}\n\n{listing}"}],
            output_format=_Guesses,
        )
        items = resp.parsed_output.items if resp.parsed_output else []
        for k in range(len(chunk)):
            g = items[k] if k < len(items) else _Guess()
            out.append({"artist": g.artist or None, "title": g.title or None})
    return out
```

- [ ] **Step 3: Scrivi i test che falliscono**

Crea `backend/tests/test_ai_suggest_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue
from app.services import ai_tags


def _seed_missing(db, file_id, path, fields):
    db.add(AudioFile(id=file_id, root_id=1, path=path, ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist=None, title=None))
    for field in fields:
        db.add(Issue(file_id=file_id, type="missing_required_tag", field=field,
                     severity="error", detail=f"{field} mancante",
                     suggested_fix_json=None, status="open"))
    db.commit()


def test_ai_suggest_sets_fixes_without_accepting(db, monkeypatch):
    _seed_missing(db, 1, "/m/rataxes - acid face.mp3", ("artist", "title"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(ai_tags, "suggest",
                        lambda names: [{"artist": "rataxes", "title": "acid face"}])
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest").json()
        assert r == {"configured": True, "files": 1, "suggested": 2, "unresolved": 0}
        rows = client.get("/api/issues", params={"type": "missing_required_tag"}).json()
        by_field = {i["field"]: i for i in rows}
        assert by_field["artist"]["suggested_fix_json"] == {
            "field": "artist", "action": "retag", "to": "rataxes"}
        assert by_field["artist"]["status"] == "open"  # NON accettata
        assert by_field["title"]["suggested_fix_json"]["to"] == "acid face"


def test_ai_suggest_no_key(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest").json()
        assert r["configured"] is False
        assert r["suggested"] == 0


def test_ai_suggest_unresolved(db, monkeypatch):
    _seed_missing(db, 2, "/m/codice_strano.mp3", ("artist",))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(ai_tags, "suggest", lambda names: [{"artist": None, "title": None}])
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest").json()
        assert r["suggested"] == 0 and r["unresolved"] == 1


def test_ai_suggest_skips_already_suggested(db, monkeypatch):
    db.add(AudioFile(id=3, root_id=1, path="/m/x - y.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False))
    db.add(Issue(file_id=3, type="missing_required_tag", field="artist", severity="error",
                 detail="artist mancante",
                 suggested_fix_json={"field": "artist", "action": "retag", "to": "Z"},
                 status="open"))
    db.commit()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    called = {"n": 0}
    def _fake(names):
        called["n"] += 1
        return [{"artist": "x", "title": "y"} for _ in names]
    monkeypatch.setattr(ai_tags, "suggest", _fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/ai-suggest").json()
        assert r["files"] == 0 and r["suggested"] == 0  # niente da suggerire
        assert called["n"] == 0  # suggest non chiamato se non ci sono file
```

- [ ] **Step 4: Lancia i test, verifica che falliscono**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ai_suggest_api.py -v`
Expected: FAIL (404 sull'endpoint inesistente).

- [ ] **Step 5: Aggiungi l'endpoint in `backend/app/routers/issues.py`**

Aggiorna gli import in testa:
```python
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, Issue, utcnow
from app.schemas import IssueBulkBody, IssueFixBody, IssueRead, IssueStatusBody
from app.services import ai_tags
```

Aggiungi in fondo al file:
```python
@router.post("/ai-suggest", response_model=dict)
def ai_suggest(db: Session = Depends(get_db)):
    if not ai_tags.is_configured():
        return {"configured": False, "files": 0, "suggested": 0, "unresolved": 0}
    rows = db.execute(
        select(Issue, AudioFile)
        .join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.type == "missing_required_tag",
               Issue.field.in_(("artist", "title")))
    ).all()
    # JSON null si filtra in Python: la colonna JSON serializza None come 'null'
    # (convenzione del codebase, vedi bulk()/set_status()).
    todo = [(issue, f) for issue, f in rows if issue.suggested_fix_json is None]
    if not todo:
        return {"configured": True, "files": 0, "suggested": 0, "unresolved": 0}

    by_file: dict[int, str] = {}
    for issue, f in todo:
        by_file.setdefault(issue.file_id,
                           os.path.splitext(os.path.basename(f.path))[0])
    file_ids = list(by_file.keys())
    guesses = ai_tags.suggest([by_file[fid] for fid in file_ids])
    guess_by_file = {fid: guesses[k] for k, fid in enumerate(file_ids)
                     if k < len(guesses)}

    suggested = 0
    unresolved = 0
    for issue, f in todo:
        g = guess_by_file.get(issue.file_id) or {}
        value = (g.get(issue.field) or "").strip()
        if value:
            issue.suggested_fix_json = {"field": issue.field, "action": "retag", "to": value}
            issue.updated_at = utcnow()
            suggested += 1
        else:
            unresolved += 1
    db.commit()
    return {"configured": True, "files": len(file_ids),
            "suggested": suggested, "unresolved": unresolved}
```

- [ ] **Step 6: Lancia i test, verifica che passano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ai_suggest_api.py -v`
Expected: PASS (4 test).

- [ ] **Step 7: Suite intera (no regressioni, pristine)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: tutti verdi, zero warning.

- [ ] **Step 8: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/requirements.txt backend/app/services/ai_tags.py backend/app/routers/issues.py backend/tests/test_ai_suggest_api.py
git commit -m "feat(api): POST /api/issues/ai-suggest — Haiku ricava artist/title dai nomi file nei suggested_fix"
```

---

## Task 2: Frontend — `aiSuggestTags()` + bottone "✨ Risolvi con AI" in ISSUES

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/issues/page.tsx`

**Interfaces:**
- Consumes: `apiSend` (esistente); `aiSuggestTags()` → `{configured, files, suggested, unresolved}`.

- [ ] **Step 1: Aggiungi `aiSuggestTags()` in `frontend/lib/api.ts`**

Nella sezione `// --- ISSUES`, dopo `bulkIssues`, aggiungi:
```ts
export interface AiSuggestResult {
  configured: boolean;
  files: number;
  suggested: number;
  unresolved: number;
}
export function aiSuggestTags() {
  return apiSend<AiSuggestResult>("POST", "/api/issues/ai-suggest");
}
```

- [ ] **Step 2: Aggiungi il bottone + handler in `frontend/app/issues/page.tsx`**

Aggiorna l'import da `@/lib/api` per includere `aiSuggestTags`:
```tsx
import {
  listIssues, listSources, setIssueStatus, fixIssue, bulkIssues, aiSuggestTags,
  type Issue, type ScanRoot,
} from "@/lib/api";
```

Nel componente `IssuesPage`, aggiungi due stati accanto agli altri `useState` e l'handler accanto a `act`:
```tsx
  const [aiBusy, setAiBusy] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);

  const onAiSuggest = async () => {
    setActionError(null);
    setAiNote(null);
    setAiBusy(true);
    try {
      const r = await aiSuggestTags();
      if (!r.configured) {
        setActionError("Imposta ANTHROPIC_API_KEY nel backend per usare l'AI.");
      } else {
        load();
        setAiNote(
          `${r.suggested} suggerimenti pronti${r.unresolved > 0 ? `, ${r.unresolved} non ricavabili dal nome file` : ""} — rivedi e accetta col ✓.`,
        );
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Errore");
    } finally {
      setAiBusy(false);
    }
  };
```

Nel JSX, renderizza la nota dopo `{actionError && <Alert>{actionError}</Alert>}`:
```tsx
        {aiNote && <Alert tone="info">{aiNote}</Alert>}
```

Passa il bottone alla marginalia: nel `<Marginalia ... />` aggiungi le prop `onAiSuggest={onAiSuggest}` e `aiBusy={aiBusy}`, e aggiorna la firma + il corpo di `Marginalia`:
```tsx
function Marginalia({ total, bySev, byType, accepted, onAcceptFixable, onDismissInfo, onAiSuggest, aiBusy }: {
  total: number;
  bySev: Record<string, number>;
  byType: Record<string, number>;
  accepted: number;
  onAcceptFixable: () => void;
  onDismissInfo: () => void;
  onAiSuggest: () => void;
  aiBusy: boolean;
}) {
```
e nel blocco dei bottoni in fondo a `Marginalia`, prima dei due bottoni bulk esistenti, aggiungi:
```tsx
        <Button variant="primary" size="sm" onClick={onAiSuggest} disabled={aiBusy}>
          {aiBusy ? "AI in corso…" : "✨ Risolvi con AI"}
        </Button>
```

- [ ] **Step 3: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 4: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/lib/api.ts frontend/app/issues/page.tsx
git commit -m "feat(fe): ISSUES — bottone 'Risolvi con AI' (pre-riempie artist/title dai suggerimenti)"
```

---

## Self-Review

**1. Spec coverage:**
- Endpoint `POST /api/issues/ai-suggest` (set suggested_fix, status open, no-key handling, unresolved) → Task 1 ✓
- Servizio `ai_tags` mockabile, Haiku, structured output, solo nomi file → Task 1 ✓
- Bottone "Risolvi con AI" in ISSUES, ricarica + messaggio, key-mancante Alert → Task 2 ✓
- Riuso del campo inline + `✓` esistenti (nessun nuovo percorso) → garantito: l'endpoint setta solo `suggested_fix_json`, la UI 6b fa il resto ✓
- Solo artist/title; niente scrittura su disco; niente auto-accept → endpoint scope + `status` invariato ✓
- Test: pytest mockato (Task 1); lint+build (Task 2) ✓

**2. Placeholder scan:** nessun TBD/TODO; codice completo.

**3. Type consistency:**
- `ai_tags.suggest` ritorna `list[{artist,title}]` allineato; l'endpoint mappa per indice ✓
- `suggested_fix_json = {field, action:"retag", to}` ↔ forma consumata dal planner ✓
- `AiSuggestResult` (TS) ↔ dict di ritorno backend (configured, files, suggested, unresolved) ✓
- `Alert tone="info"` esiste in `ui.tsx` (tone ∈ danger|warning|info|success) ✓
- `Button variant="primary" size="sm"` esiste ✓

---

## Execution Handoff
Esecuzione **inline** (scelta utente) via superpowers:executing-plans.
