# Set Builder solo posseduti (fetta 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** I set generati sono garantiti suonabili: il Candidate Engine filtra di default sulle tracce possedute (`has_local_file=true`), con opzione esplicita per includere i lead; il dettaglio playlist mostra "possiedi N di M".

**Architecture:** Nuovo campo `owned_only: bool = True` su `SetGenerationRequest`; filtro nel `select_candidates` deterministico; messaggio d'errore contestuale in `generate_set` quando il filtro possesso svuota le candidate. Frontend: toggle nel Set Builder (default ON) + indicatore possesso nel dettaglio playlist.

**Tech Stack:** Python/FastAPI/Pydantic, pytest; Next.js 16 + React.

## Global Constraints

- Dipende dalla **fetta 1** (`feat/disk-first-core` mergiata o come base del branch): usa `has_local_file` come filtro e i campi TS `Track.has_local_file`.
- Test backend: `cd backend && .venv/bin/python -m pytest tests -q`. Frontend: `cd frontend && npm run lint && npm run build`. **Leggere `frontend/CLAUDE.md` prima di toccare pagine (Next.js 16).**
- Copy UI e commenti in italiano. Branch: `feat/set-builder-owned` (da `feat/disk-first-core` se non ancora mergiata, altrimenti da `master`).
- Il motore resta deterministico: nessun cambiamento a scoring/ruoli/AI.

---

### Task 0: Branch

- [ ] **Step 1:**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git checkout feat/disk-first-core 2>/dev/null || git checkout master
git checkout -b feat/set-builder-owned
```

---

### Task 1: `owned_only` nello schema e nel Candidate Engine

**Files:**
- Modify: `backend/app/schemas.py` (`SetGenerationRequest`, ~riga 108)
- Modify: `backend/app/services/candidate_engine.py` (`select_candidates`)
- Test: `backend/tests/test_candidate_owned.py`

**Interfaces:**
- Produces: `SetGenerationRequest.owned_only: bool = True`; `select_candidates` esclude le tracce senza file quando `owned_only=True`.

- [ ] **Step 1: Test fallenti**

```python
# backend/tests/test_candidate_owned.py
"""Candidate Engine disk-first: di default solo tracce possedute."""
from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.candidate_engine import select_candidates


def _track(i: int, *, owned: bool) -> Track:
    return Track(
        source_type="spotify", title=f"T{i}", artist=f"A{i}",
        bpm=126.0 + i, camelot_key="8A", duration_seconds=300,
        has_local_file=owned,
    )


def test_default_solo_possedute(db):
    db.add(_track(1, owned=True))
    db.add(_track(2, owned=False))
    db.commit()

    out = select_candidates(db, SetGenerationRequest())
    assert [t.title for t in out] == ["T1"]


def test_opt_out_include_lead(db):
    db.add(_track(1, owned=True))
    db.add(_track(2, owned=False))
    db.commit()

    out = select_candidates(db, SetGenerationRequest(owned_only=False))
    assert {t.title for t in out} == {"T1", "T2"}
```

- [ ] **Step 2: Run** `cd backend && .venv/bin/python -m pytest tests/test_candidate_owned.py -q` → FAIL (le due tracce passano entrambe / campo inesistente).

- [ ] **Step 3: Implementazione**

In `backend/app/schemas.py`, dentro `SetGenerationRequest`, dopo `avoid_short_tracks: bool = True`:

```python
    # Disk-first: di default il set nasce SOLO da tracce possedute (file su disco),
    # cosi' e' garantito suonabile. False = includi anche i lead (senza file).
    owned_only: bool = True
```

In `backend/app/services/candidate_engine.py`, nel ciclo `for t in tracks:` di `select_candidates`, come PRIMO controllo del corpo del loop:

```python
        if req.owned_only and not t.has_local_file:
            continue
```

- [ ] **Step 4: Run** file di test → PASS. Poi l'intera suite: `cd backend && .venv/bin/python -m pytest tests -q`.
**Attenzione:** i test esistenti del set builder (`test_set_builder_phase_c.py`, `test_ai_agent.py`, `test_set_editing.py`…) creano tracce senza `has_local_file` e ora fallirebbero. Sistemarli aggiungendo `owned_only=False` alle `SetGenerationRequest` dei test esistenti **oppure** (meglio, dove c'è una factory come `seed_tracks` in `conftest.py`) impostando `has_local_file=True` sulle tracce sintetiche. Scegliere l'approccio col diff minore e applicarlo uniformemente.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/services/candidate_engine.py backend/tests/
git commit -m "feat(disk-first): owned_only=True di default nel Candidate Engine"
```

---

### Task 2: Errore chiaro quando il possesso svuota le candidate

**Files:**
- Modify: `backend/app/services/set_generator.py` (`generate_set`, ~riga 190)
- Test: `backend/tests/test_candidate_owned.py` (estendere)

**Interfaces:**
- Consumes: `SetGenerationError` (già mappata su HTTP 422/409 dal router `sets.py`).
- Produces: messaggio d'errore che spiega il rimedio (disattivare "solo posseduti" o indicizzare la libreria) quando `owned_only=True` e le candidate possedute sono `< 3`.

- [ ] **Step 1: Test fallente**

```python
def test_errore_contestuale_owned_only(db):
    """Con owned_only e zero possedute, l'errore spiega il rimedio."""
    import pytest
    from app.services.set_generator import SetGenerationError, generate_set

    db.add(_track(1, owned=False))
    db.add(_track(2, owned=False))
    db.add(_track(3, owned=False))
    db.commit()

    with pytest.raises(SetGenerationError, match="posseduti"):
        generate_set(db, SetGenerationRequest())
```

- [ ] **Step 2: Run** → FAIL (il messaggio attuale non contiene "posseduti").

- [ ] **Step 3: Implementazione** — in `generate_set`, sostituire il blocco `if len(candidates) < 3:` con:

```python
    if len(candidates) < 3:
        if req.owned_only:
            raise SetGenerationError(
                "Tracce candidate insufficienti tra quelle possedute: indicizza la "
                "libreria (Impostazioni → Libreria) o disattiva \"solo brani posseduti\" "
                "per includere i lead."
            )
        raise SetGenerationError(
            "Tracce candidate insufficienti: allargare i vincoli (BPM, sorgenti, durata) "
            "o importare piu' tracce."
        )
```

- [ ] **Step 4: Run** file + suite → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/set_generator.py backend/tests/test_candidate_owned.py
git commit -m "feat(disk-first): errore contestuale quando owned_only svuota le candidate"
```

---

### Task 3: Frontend — toggle "solo brani posseduti" nel Set Builder

**Files:**
- Modify: `frontend/app/set-builder/page.tsx`

**Interfaces:**
- Consumes: `owned_only` nel body di generazione (Task 1); il payload è costruito ~riga 167 (`avoid_short_tracks: avoidShort, ...`).
- Produces: checkbox nel form, default ON, accanto a "evita tracce corte" (~riga 299).

- [ ] **Step 1: Stato + payload** — aggiungere lo stato vicino ad `avoidShort`:

```typescript
  const [ownedOnly, setOwnedOnly] = useState(true);
```

e nel payload di generazione (dove c'è `avoid_short_tracks: avoidShort,`):

```typescript
        owned_only: ownedOnly,
```

- [ ] **Step 2: Checkbox** — accanto a `<Checkbox label="evita tracce corte" ...>`:

```tsx
                  <Checkbox label="solo brani posseduti" checked={ownedOnly} onChange={setOwnedOnly} />
```

- [ ] **Step 3: Verifica** `cd frontend && npm run lint && npm run build` → 0 errori. Verifica manuale consigliata: con backend attivo, generare un set con toggle ON e zero possedute → l'errore contestuale appare nell'Alert della pagina.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/set-builder/page.tsx
git commit -m "feat(disk-first): toggle 'solo brani posseduti' nel Set Builder (default ON)"
```

---

### Task 4: Frontend — "possiedi N di M" nel dettaglio playlist

**Files:**
- Modify: `frontend/app/playlists/[id]/page.tsx`

**Interfaces:**
- Consumes: `Track.has_local_file` (tipi della fetta 1); la pagina carica già le tracce della playlist (`playlistTracks(id)` in `lib/api.ts:424`).
- Produces: indicatore possesso nell'header della pagina (prop `meta` di `PageLayout`, pattern della libreria: `meta={`${total} TRACCE`}`).

- [ ] **Step 1: Conteggio** — nella pagina, dove le tracce sono in stato (es. `tracks`), calcolare:

```typescript
  const ownedCount = tracks.filter((t) => t.has_local_file).length;
```

- [ ] **Step 2: Indicatore** — estendere la prop `meta` del `PageLayout` esistente (conservando il contenuto attuale):

```tsx
  meta={`${tracks.length} TRACCE · POSSIEDI ${ownedCount} DI ${tracks.length}`}
```

(Se la pagina non usa `PageLayout`/`meta`, collocare la stessa stringa nell'header accanto al conteggio tracce esistente, uniformandosi al markup reale.)

- [ ] **Step 3: Verifica** `cd frontend && npm run lint && npm run build` → 0 errori.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/playlists/
git commit -m "feat(disk-first): indicatore 'possiedi N di M' nel dettaglio playlist"
```

---

### Task 5: Verifica finale

- [ ] **Step 1:** `cd backend && .venv/bin/python -m pytest tests -q` → tutti verdi.
- [ ] **Step 2:** `cd frontend && npm run lint && npm run build` → 0 errori.
- [ ] **Step 3: Commit di chiusura**

```bash
git add -A && git commit -m "chore(disk-first): chiusura fetta 2 — set garantiti suonabili"
```
