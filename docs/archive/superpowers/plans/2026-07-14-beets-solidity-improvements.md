# Beets Solidity Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere a Sortory due miglioramenti di solidità ispirati a beets — confidenza graduata `strong`/`medium`/`weak` sui match provider (Parte 1) e un controllo di integrità file con ffmpeg che manda i corrotti in quarantena (Parte 2).

**Architecture:** Parte 1 introduce un modulo puro `services/match_distance.py` che calcola una distanza pesata locale (difflib) tra i tag del file e il candidato MusicBrainz, sostituendo il binario `high`/`text` in `text_providers.resolve`; i consumatori (contatori, endpoint accept di massa, badge UI) passano a 3 gradi. Parte 2 aggiunge un adapter `integrations/integrity.py` (decode ffmpeg), un servizio+job on-demand con cache incrementale su `content_hash`, un nuovo tipo di Issue `corrupt_file` che confluisce nei `removals` esistenti → quarantena, e una riorganizzazione della zona azioni di Issues con un toggle `Arricchisci`/`Manutenzione`. Le due parti sono indipendenti.

**Tech Stack:** Backend FastAPI + SQLAlchemy + SQLite (Python 3.11, venv in `backend/.venv`); frontend Next.js 16 + React 19 + Tailwind v4 + TypeScript; `difflib` (stdlib) per la distanza; `ffmpeg` (opzionale, già installato) per l'integrità.

## Global Constraints

- **Test sempre col venv del progetto:** `backend/.venv/bin/python -m pytest backend/tests -q` (il system Python 3.9 rompe sulla sintassi `X | None`).
- **`pytest.ini` ha `filterwarnings = error`:** un warning nuovo fa fallire la suite. Non introdurre warning.
- **Nessuna nuova dipendenza Python:** la distanza usa `difflib` della stdlib, non `jellyfish`.
- **ffmpeg è opzionale e deve degradare pulito:** assente dal PATH → feature inattiva, nessun crash (come le chiavi provider / `fpcalc`).
- **Nessuna migrazione Alembic:** le colonne nuove si aggiungono via `ensure_schema` in `backend/app/db.py` (ALTER TABLE idempotente).
- **Commenti/docstring backend in italiano** (stile esistente del file che tocchi).
- **i18n:** aggiungere le chiavi prima in `frontend/lib/i18n/en.ts` (source of truth), poi tradurre in `it.ts`.
- **~322 test esistenti devono restare verdi.**

---

# PARTE 1 — Confidenza graduata via distanza pesata

### Task 1: Modulo `match_distance` (distanza pesata → grado)

**Files:**
- Create: `backend/app/services/match_distance.py`
- Test: `backend/tests/test_match_distance.py`

**Interfaces:**
- Produces:
  - `grade_confidence(file, canonical: dict, *, exact: bool) -> str` → `"strong" | "medium" | "weak"`
  - `weighted_distance(file, canonical: dict) -> float | None` (0..1, `None` se nessun campo comparabile)
  - `file` è un oggetto con attributi `artist`, `title`, `album`, `year`, `label` (es. `AudioFile`, o un semplice stub nei test).
  - `canonical` è il dict tornato da MusicBrainz con chiavi `canonical_artist`, `canonical_title`, `canonical_album`, `label`, `release_date`, `confidence`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_match_distance.py`:

```python
from dataclasses import dataclass

from app.services.match_distance import grade_confidence, weighted_distance


@dataclass
class FileStub:
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    year: int | None = None
    label: str | None = None


def _canon(**kw):
    # chiavi come le produce integrations/musicbrainz._parse_recording
    out = {}
    if "artist" in kw: out["canonical_artist"] = kw["artist"]
    if "title" in kw: out["canonical_title"] = kw["title"]
    if "album" in kw: out["canonical_album"] = kw["album"]
    if "label" in kw: out["label"] = kw["label"]
    if "release_date" in kw: out["release_date"] = kw["release_date"]
    return out


def test_exact_is_strong_even_with_divergent_tags():
    f = FileStub(artist="wrong", title="totally different")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=True) == "strong"


def test_text_perfect_match_is_strong():
    f = FileStub(artist="Daft Punk", title="Around the World")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=False) == "strong"


def test_text_strong_divergence_is_weak():
    f = FileStub(artist="Someone Else", title="A Completely Other Song")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=False) == "weak"


def test_the_article_and_feat_do_not_penalize():
    f = FileStub(artist="The Prodigy feat. Someone", title="Firestarter")
    c = _canon(artist="Prodigy", title="Firestarter")
    assert grade_confidence(f, c, exact=False) == "strong"


def test_case_and_punctuation_are_ignored():
    f = FileStub(artist="DAFT PUNK!!!", title="around, the world")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=False) == "strong"


def test_missing_secondary_fields_are_not_penalized():
    # file senza album/year/label: contano solo artist+title (ancore)
    f = FileStub(artist="Daft Punk", title="Around the World")
    c = _canon(artist="Daft Punk", title="Around the World",
               album="Homework", release_date="1997", label="Virgin")
    assert grade_confidence(f, c, exact=False) == "strong"


def test_no_comparable_fields_is_weak():
    f = FileStub()  # nessun tag
    c = _canon(artist="Daft Punk", title="Around the World")
    assert weighted_distance(f, c) is None
    assert grade_confidence(f, c, exact=False) == "weak"


def test_moderate_divergence_is_medium():
    # title giusto, artist con un errore di battitura moderato
    f = FileStub(artist="Daft Bunk", title="Around the World")
    c = _canon(artist="Daft Punk", title="Around the World")
    assert grade_confidence(f, c, exact=False) == "medium"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_match_distance.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.match_distance'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/match_distance.py`:

```python
"""Confidenza graduata di un match provider via distanza pesata locale.
Puro e deterministico (niente I/O), stile dedup.py. Ispirato a beets
autotag/distance.py, adattato al modello per-traccia di Sortory: si
confrontano i tag che il file GIA' dichiara con i valori canonici del
candidato MusicBrainz."""

import difflib
import re

# Pesi per campo per il match TESTUALE. Ispirati a beets, ridotti ai campi
# che Sortory risolve davvero. artist/title sono le ancore.
_WEIGHTS = {"artist": 3.0, "title": 3.0, "album": 3.0, "year": 1.0, "label": 0.5}

# Soglie distanza -> grado. PROVVISORIE: calibrate dai test (il metrico
# difflib differisce da beets, i suoi 0.04/0.25 non si trasferiscono).
_STRONG_MAX = 0.15
_MEDIUM_MAX = 0.40

_FEAT_RE = re.compile(r"\b(feat|ft|featuring)\b.*$", re.IGNORECASE)
_THE_RE = re.compile(r"^the\s+", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")

# campo file -> chiave nel dict canonical del provider
_CANON_KEY = {"artist": "canonical_artist", "title": "canonical_title",
              "album": "canonical_album", "label": "label"}


def _normalize(s: str) -> str:
    """Minuscole, via feat./the/punteggiatura, spazi compattati."""
    s = s.casefold()
    s = _FEAT_RE.sub("", s)
    s = _THE_RE.sub("", s)
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def _string_dist(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na and not nb:
        return 0.0
    return 1.0 - difflib.SequenceMatcher(None, na, nb).ratio()


def _present(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    return True


def _canonical_value(canonical: dict, field: str):
    if field == "year":
        rd = canonical.get("release_date")
        if isinstance(rd, str) and len(rd) >= 4 and rd[:4].isdigit():
            return int(rd[:4])
        return None
    return canonical.get(_CANON_KEY[field])


def weighted_distance(file, canonical: dict) -> float | None:
    """Distanza pesata 0..1 sui soli campi comparabili (presenti su entrambi).
    None se nessun campo e' comparabile (es. file senza artist ne' title)."""
    num = 0.0
    den = 0.0
    for field, weight in _WEIGHTS.items():
        fv = getattr(file, field, None)
        cv = _canonical_value(canonical, field)
        if not _present(fv) or not _present(cv):
            continue
        if field == "year":
            d = 0.0 if int(fv) == int(cv) else 1.0
        else:
            d = _string_dist(str(fv), str(cv))
        num += weight * d
        den += weight
    if den == 0:
        return None
    return num / den


def grade_confidence(file, canonical: dict, *, exact: bool) -> str:
    """Grado di confidenza: "strong" | "medium" | "weak".
    exact=True (match per MBID/ISRC) -> strong a prescindere dai tag."""
    if exact:
        return "strong"
    d = weighted_distance(file, canonical)
    if d is None:
        return "weak"
    if d <= _STRONG_MAX:
        return "strong"
    if d <= _MEDIUM_MAX:
        return "medium"
    return "weak"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_match_distance.py -q`
Expected: PASS (8 passed). Se `test_moderate_divergence_is_medium` non cade in `medium`, **calibra le soglie**: stampa `weighted_distance(f, c)` per i tre casi (perfect/moderate/strong-divergence) e regola `_STRONG_MAX`/`_MEDIUM_MAX` così che perfect→strong, "Daft Bunk"→medium, "Someone Else"+"A Completely Other Song"→weak. Le soglie sono esplicitamente provvisorie: questo step le fissa.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/match_distance.py backend/tests/test_match_distance.py
git commit -m "feat(match): distanza pesata locale -> confidenza strong/medium/weak"
```

---

### Task 2: Innesto in `text_providers.resolve`

**Files:**
- Modify: `backend/app/services/text_providers.py` (import + riga confidenza MB + rami Discogs)
- Test: `backend/tests/test_text_providers.py` (esiste già; aggiungere/adeguare)

**Interfaces:**
- Consumes: `grade_confidence` da Task 1.
- Produces: `resolve(file, mb, discogs)` ora mette in `fields[campo] = (valore, grado)` con `grado ∈ {strong, medium, weak}`; `ResolvedText.confidence` (overall) idem. I campi da Discogs sono sempre `"weak"`.

- [ ] **Step 1: Write the failing test**

Individua il file di test dei provider testuali:

Run: `ls backend/tests | grep -i "text_provider\|provider"`

Aggiungi in `backend/tests/test_text_providers.py` (adatta l'import degli stub/fake MB già presenti nel file; se il file non esiste, crealo con un fake MB minimale sullo stile degli altri test del repo):

```python
def test_resolve_exact_match_is_strong():
    # fake MB che ritorna confidence>=95 (match per mbid/isrc) e canonici
    class FakeMB:
        def lookup(self, **kw):
            return {"canonical_artist": "Daft Punk", "canonical_title": "Da Funk",
                    "confidence": 95, "release_mbids": []}

    from app.services.text_providers import resolve

    class F:
        artist = "daft punk"; title = "da funk"; album = None; year = None
        label = None; isrc = None; mbid = "x"
    r = resolve(F(), mb=FakeMB(), discogs=None)
    assert r.fields["artist"][1] == "strong"
    assert r.confidence == "strong"


def test_resolve_text_divergent_is_weak():
    class FakeMB:
        def lookup(self, **kw):
            return {"canonical_artist": "Daft Punk", "canonical_title": "Da Funk",
                    "confidence": 70, "release_mbids": []}

    from app.services.text_providers import resolve

    class F:
        artist = "qualcun altro"; title = "un brano completamente diverso"
        album = None; year = None; label = None; isrc = None; mbid = None
    r = resolve(F(), mb=FakeMB(), discogs=None)
    assert r.fields["artist"][1] == "weak"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_text_providers.py -q -k "strong or weak"`
Expected: FAIL (oggi la confidenza è `high`/`text`, non `strong`/`weak`).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/text_providers.py`:

1. Aggiungi l'import in cima (dopo gli altri import `app.services`):
```python
from app.services.match_distance import grade_confidence
```

2. Sostituisci la riga della confidenza MB (attuale `conf = "high" if (mb_res.get("confidence") or 0) >= 95 else "text"`):
```python
        conf = grade_confidence(
            file, mb_res, exact=(mb_res.get("confidence") or 0) >= 95)
```

3. Nei rami Discogs (gap-fill), cambia i marcatori `"text"` → `"weak"`. Ci sono tre assegnazioni tipo `out["label"] = (dg_res["label"], "text")`, `out["genre"] = (g, "text")`, `out["year"] = (y, "text")`: metti `"weak"` al posto di `"text"` in tutte e tre.

4. **Verifica `covers.py`** (usa `resolved.confidence`, ora graduato): `grep -n "confidence\|== .high\|'high'\|\"high\"" backend/app/services/covers.py`. Se trova un confronto `== "high"` sulla confidenza del match (non della cover), sostituiscilo con `== "strong"` (+ tollera `"high"` legacy). Se `resolved.confidence` viene solo passato avanti come stringa, nessuna modifica necessaria.

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_text_providers.py -q`
Expected: PASS. Aggiorna eventuali asserzioni preesistenti che si aspettano `"high"`/`"text"` → `"strong"`/`"weak"` (un match esatto era `high`→ora `strong`; Discogs era `text`→ora `weak`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/text_providers.py backend/tests/test_text_providers.py
git commit -m "feat(providers): confidenza graduata nel resolve (strong/medium/weak)"
```

---

### Task 3: Consumatori backend — contatori rescan + endpoint accept-strong

**Files:**
- Modify: `backend/app/services/provider_rescan.py` (dict risultato + conteggio per grado)
- Modify: `backend/app/routers/issues.py` (rinomina endpoint + tolleranza legacy)
- Test: `backend/tests/test_provider_rescan.py`, `backend/tests/test_issues*.py` (adeguare)

**Interfaces:**
- Consumes: la confidenza graduata da Task 2 (in `suggested_fix_json["confidence"]`).
- Produces:
  - dict rescan con chiavi `proposed_strong`, `proposed_medium`, `proposed_weak` (al posto di `proposed_high`/`proposed_text`).
  - endpoint `POST /api/issues/provider-override/accept-strong` che accetta gli override con `confidence in ("strong", "high")`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_provider_rescan.py` adegua/aggiungi un test che verifica le chiavi del risultato:

```python
def test_rescan_result_has_graded_counters(...):
    # ... setup esistente che lancia rescan con un fake MB ...
    res = provider_rescan.rescan(db, fields=["artist"], mb=fake_mb, discogs=None)
    assert "proposed_strong" in res
    assert "proposed_medium" in res
    assert "proposed_weak" in res
    assert "proposed_high" not in res
```

E in `backend/tests/test_issues*.py` (dove si testano gli override) un test per il nuovo endpoint:

```python
def test_accept_strong_accepts_strong_and_legacy_high(client, db):
    # crea due override open: uno confidence="strong", uno legacy "high",
    # uno "weak" (che NON deve essere accettato)
    # ... crea gli Issue con suggested_fix_json["confidence"] ...
    r = client.post("/api/issues/provider-override/accept-strong")
    assert r.status_code == 200
    # gli strong e high diventano accepted, i weak restano open
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_provider_rescan.py -q -k graded`
Expected: FAIL (`proposed_strong` non esiste; endpoint 404).

- [ ] **Step 3: Write minimal implementation**

1. In `backend/app/services/provider_rescan.py`, nel dict `res` iniziale (dentro `rescan`), sostituisci le due chiavi:
```python
           "proposed_strong": 0, "proposed_medium": 0, "proposed_weak": 0,
```
(al posto di `"proposed_high": 0, "proposed_text": 0,`).

2. Sostituisci la riga di conteggio (attuale `res["proposed_high" if conf == "high" else "proposed_text"] += 1`) con:
```python
                key = f"proposed_{conf}" if conf in ("strong", "medium", "weak") else "proposed_weak"
                res[key] += 1
```

3. In `backend/app/routers/issues.py`, rinomina la rotta e amplia la condizione:
```python
@router.post("/provider-override/accept-strong", response_model=dict)
def accept_strong_overrides(db: Session = Depends(get_db)):
    rows = db.scalars(select(Issue).where(
        Issue.type == "provider_override", Issue.status == "open")).all()
    updated = 0
    for issue in rows:
        # tollera il legacy "high" nei dati non ancora ri-scansionati
        if (issue.suggested_fix_json or {}).get("confidence") in ("strong", "high"):
            issue.status = "accepted"
            issue.updated_at = utcnow()
            updated += 1
    db.commit()
    return {"updated": updated}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_provider_rescan.py backend/tests/test_issues*.py -q`
Expected: PASS. Aggiorna eventuali test preesistenti che referenziano `proposed_high`/`proposed_text` o la rotta `accept-high`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/provider_rescan.py backend/app/routers/issues.py backend/tests/
git commit -m "feat(issues): contatori a 3 gradi + endpoint accept-strong (tollera legacy high)"
```

---

### Task 4: Frontend Parte 1 — badge a 3 stati, tipi, i18n

**Files:**
- Modify: `frontend/components/issues-table.tsx` (`ConfBadge`)
- Modify: `frontend/lib/api.ts` (`ProviderRescanResult`, `acceptHighOverrides`)
- Modify: `frontend/lib/i18n/en.ts` e `frontend/lib/i18n/it.ts` (chiavi conf + rescanNote)
- Modify: `frontend/app/issues/page.tsx` (chiamata rescanNote con 3 numeri, chiamata accept)

**Interfaces:**
- Consumes: `confidence ∈ {strong, medium, weak}` (o legacy `high`/`text`) e i contatori `proposed_strong/medium/weak` dal backend.

- [ ] **Step 1: Badge a 3 stati**

In `frontend/components/issues-table.tsx`, sostituisci `ConfBadge`:

```tsx
function ConfBadge({ conf }: { conf: unknown }) {
  const t = useT();
  // normalizza legacy: high->strong, text->weak
  const g = conf === "high" ? "strong" : conf === "text" ? "weak" : conf;
  if (g !== "strong" && g !== "medium" && g !== "weak") return null;
  const cls =
    g === "strong" ? "border-ok text-ok"
    : g === "medium" ? "border-warning text-warning"
    : "border-faint text-faint";
  const label = g === "strong" ? t.issues.confStrong
    : g === "medium" ? t.issues.confMedium : t.issues.confWeak;
  return (
    <span className={cn("border px-1 py-0.5 text-[9px] uppercase tracking-wider", cls)}>
      {label}
    </span>
  );
}
```

- [ ] **Step 2: i18n**

In `frontend/lib/i18n/en.ts` sostituisci `confHigh`/`confText` con tre chiavi e aggiorna `rescanNote` a 3 numeri:

```ts
    confStrong: "strong",
    confMedium: "medium",
    confWeak: "weak",
    rescanNote: (strong: number, medium: number, weak: number, scanned: number, acoustid: boolean, covers: number) =>
      `Rescan: ${strong} strong, ${medium} medium, ${weak} weak${covers > 0 ? `, ${covers} covers` : ""} over ${scanned} tracks${acoustid ? "" : " (fingerprint off: no strong via ID)"}.`,
```

In `frontend/lib/i18n/it.ts` gli equivalenti:

```ts
    confStrong: "alta",
    confMedium: "media",
    confWeak: "bassa",
    rescanNote: (strong, medium, weak, scanned, acoustid, covers) =>
      `Rescan: ${strong} alta, ${medium} media, ${weak} bassa${covers > 0 ? `, ${covers} copertine` : ""} su ${scanned} tracce${acoustid ? "" : " (fingerprint off: nessuna alta via ID)"}.`,
```

- [ ] **Step 3: Tipi api.ts + chiamata**

In `frontend/lib/api.ts`, in `ProviderRescanResult` sostituisci `proposed_high`/`proposed_text` con:

```ts
  proposed_strong: number;
  proposed_medium: number;
  proposed_weak: number;
```

e cambia la funzione accept (rinomina + path):

```ts
export function acceptStrongOverrides() {
  return apiSend<{ updated: number }>("POST", "/api/issues/provider-override/accept-strong");
}
```

In `frontend/app/issues/page.tsx`: aggiorna l'import e le due call-site — `acceptHighOverrides()` → `acceptStrongOverrides()`, e la `rescanNote(...)` per passare `r.proposed_strong, r.proposed_medium, r.proposed_weak, r.scanned, r.acoustid_available, r.covers`.

- [ ] **Step 4: Verifica tipi + browser**

Run: `cd frontend && npx tsc --noEmit`
Expected: nessun errore di tipo (se restano riferimenti a `confHigh`/`proposed_high`/`acceptHighOverrides`, correggili — il compilatore li elenca).

Poi verifica visiva: avvia il preview (`preview_start` con la config `frontend` di `.claude/launch.json`, o creala per `npm run dev`), apri la pagina Issues, lancia un "IMPORT MISSING METADATA FROM PROVIDER" e controlla che i badge mostrino strong/medium/weak con i tre colori. Screenshot come prova.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(ui): badge confidenza a 3 gradi + accept-strong + rescanNote"
```

---

# PARTE 2 — Controllo integrità file (badfiles)

### Task 5: Adapter `integrations/integrity.py` (decode ffmpeg)

**Files:**
- Create: `backend/app/integrations/integrity.py`
- Test: `backend/tests/test_integrity_adapter.py`

**Interfaces:**
- Produces:
  - `IntegrityResult` (dataclass: `ok: bool`, `detail: str | None`)
  - `ffmpeg_available() -> bool`
  - `check_file(path: str, *, runner=None, timeout: int = 60) -> IntegrityResult` — `runner` è iniettabile per i test (default: subprocess reale); ritorna `ok=True` se decode pulito, altrimenti `ok=False` con `detail` = snippet stderr o `"timeout"`.
  - `parse_result(returncode: int, stderr: str) -> IntegrityResult` — logica pura testabile.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_integrity_adapter.py`:

```python
from app.integrations.integrity import parse_result, check_file, IntegrityResult


def test_parse_clean_decode_is_ok():
    r = parse_result(0, "")
    assert r.ok is True
    assert r.detail is None


def test_parse_nonzero_exit_is_corrupt():
    r = parse_result(1, "")
    assert r.ok is False


def test_parse_stderr_errors_is_corrupt_with_detail():
    r = parse_result(0, "[flac @ 0x..] Invalid data found when processing input")
    assert r.ok is False
    assert "Invalid data" in r.detail


def test_check_file_uses_injected_runner():
    def fake_runner(path, timeout):
        return (0, "")  # (returncode, stderr)
    r = check_file("/whatever.flac", runner=fake_runner)
    assert r == IntegrityResult(ok=True, detail=None)


def test_check_file_timeout_is_corrupt():
    def fake_runner(path, timeout):
        raise TimeoutError()
    r = check_file("/whatever.flac", runner=fake_runner)
    assert r.ok is False
    assert r.detail == "timeout"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_integrity_adapter.py -q`
Expected: FAIL (`ModuleNotFoundError: app.integrations.integrity`).

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/integrations/integrity.py`:

```python
"""Controllo integrita' del contenuto audio via ffmpeg (stile plugin badfiles
di beets). Decodifica l'intero stream: cattura header rotti E corruzione a
meta' file. Opzionale: senza ffmpeg nel PATH degrada pulito (non disponibile)."""

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    detail: str | None = None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def parse_result(returncode: int, stderr: str) -> IntegrityResult:
    """returncode!=0 oppure stderr non vuoto (con -v error) => corrotto."""
    stderr = (stderr or "").strip()
    if returncode == 0 and not stderr:
        return IntegrityResult(ok=True, detail=None)
    detail = stderr[:200] if stderr else f"ffmpeg exit {returncode}"
    return IntegrityResult(ok=False, detail=detail)


def _subprocess_runner(path: str, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", path, "-f", "null", "-"],
        capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stderr


def check_file(path: str, *, runner=None, timeout: int = 60) -> IntegrityResult:
    """Decodifica il file e ritorna l'esito. runner iniettabile per i test."""
    runner = runner or _subprocess_runner
    try:
        rc, stderr = runner(path, timeout)
    except (subprocess.TimeoutExpired, TimeoutError):
        return IntegrityResult(ok=False, detail="timeout")
    return parse_result(rc, stderr)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_integrity_adapter.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/integrity.py backend/tests/test_integrity_adapter.py
git commit -m "feat(integrity): adapter ffmpeg per il controllo integrita' file"
```

---

### Task 6: Colonne DB + servizio orchestrazione incrementale

**Files:**
- Modify: `backend/app/models.py` (3 colonne su `AudioFile`)
- Modify: `backend/app/db.py` (`ensure_schema`: 3 ALTER idempotenti)
- Create: `backend/app/services/integrity.py`
- Test: `backend/tests/test_integrity_service.py`

**Interfaces:**
- Consumes: `check_file` / `IntegrityResult` da Task 5.
- Produces: `run_integrity(db, *, checker=None, force: bool = False, on_progress=None) -> dict` con contatori `{"scanned", "checked", "skipped", "corrupt"}`. `checker` iniettabile (`callable(path) -> IntegrityResult`); scrive `integrity_ok`, `integrity_checked_hash`, `integrity_detail` su ogni file processato; salta i file con `integrity_checked_hash == content_hash` salvo `force`.
- Nuovi campi su `AudioFile`: `integrity_ok: bool | None`, `integrity_checked_hash: str | None`, `integrity_detail: str | None`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_integrity_service.py` (usa le fixture DB già presenti negli altri test del repo — replica il pattern di `test_provider_rescan.py` per creare `ScanRoot` + `AudioFile`):

```python
from app.integrations.integrity import IntegrityResult
from app.services.integrity import run_integrity


def _ok(path): return IntegrityResult(ok=True, detail=None)
def _bad(path): return IntegrityResult(ok=False, detail="Invalid data found")


def test_marks_corrupt_and_ok(db, make_file):
    good = make_file(path="/a.flac", content_hash="h1", status="present")
    bad = make_file(path="/b.flac", content_hash="h2", status="present")
    seen = {"/a.flac": _ok, "/b.flac": _bad}
    res = run_integrity(db, checker=lambda p: seen[p](p))
    db.refresh(good); db.refresh(bad)
    assert good.integrity_ok is True
    assert bad.integrity_ok is False
    assert bad.integrity_detail == "Invalid data found"
    assert res["corrupt"] == 1 and res["checked"] == 2


def test_incremental_skips_unchanged(db, make_file):
    f = make_file(path="/a.flac", content_hash="h1", status="present")
    run_integrity(db, checker=_ok)          # prima passata -> checked
    calls = {"n": 0}
    def counting(p):
        calls["n"] += 1
        return IntegrityResult(ok=True)
    res = run_integrity(db, checker=counting)   # seconda: hash invariato -> skip
    assert calls["n"] == 0
    assert res["skipped"] == 1 and res["checked"] == 0


def test_force_rechecks(db, make_file):
    make_file(path="/a.flac", content_hash="h1", status="present")
    run_integrity(db, checker=_ok)
    calls = {"n": 0}
    def counting(p):
        calls["n"] += 1
        return IntegrityResult(ok=True)
    run_integrity(db, checker=counting, force=True)
    assert calls["n"] == 1


def test_only_present_files(db, make_file):
    make_file(path="/gone.flac", content_hash="h9", status="missing")
    res = run_integrity(db, checker=_ok)
    assert res["checked"] == 0
```

Se nel repo non esiste una fixture `make_file`, aggiungila in `backend/tests/conftest.py` sullo stile della creazione di `AudioFile` già usata negli altri test (campi minimi: `root_id`, `path`, `ext`, `size_bytes`, `hash_method`, `content_hash`, `status`).

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_integrity_service.py -q`
Expected: FAIL (modulo `app.services.integrity` assente; e/o colonne mancanti).

- [ ] **Step 3: Write minimal implementation**

1. In `backend/app/models.py`, dentro `class AudioFile`, dopo `scan_error`, aggiungi:
```python
    integrity_ok: Mapped[bool | None] = mapped_column(Boolean)
    integrity_checked_hash: Mapped[str | None] = mapped_column(String)
    integrity_detail: Mapped[str | None] = mapped_column(Text)
```

2. In `backend/app/db.py`, dentro `ensure_schema`, nel blocco `if "audio_file" in inspector.get_table_names():` (dove già si aggiungono `isrc`/`mbid`/`has_rating`), aggiungi:
```python
        if "integrity_ok" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE audio_file ADD COLUMN integrity_ok BOOLEAN"))
        if "integrity_checked_hash" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE audio_file ADD COLUMN integrity_checked_hash VARCHAR"))
        if "integrity_detail" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE audio_file ADD COLUMN integrity_detail TEXT"))
```

3. Create `backend/app/services/integrity.py`:
```python
"""Orchestrazione del controllo integrita': itera i file present, salta gli
invariati gia' controllati (cache su content_hash), delega il decode a un
checker iniettabile. Puro rispetto all'I/O ffmpeg (che sta nell'adapter)."""

from sqlalchemy import select

from app.integrations.integrity import check_file
from app.models import AudioFile


def run_integrity(db, *, checker=None, force: bool = False, on_progress=None) -> dict:
    checker = checker or check_file
    files = db.scalars(
        select(AudioFile).where(AudioFile.status == "present")).all()
    total = len(files)
    res = {"scanned": total, "checked": 0, "skipped": 0, "corrupt": 0}
    for idx, f in enumerate(files):
        if on_progress is not None:
            on_progress(idx, total, "checking")
        if not force and f.content_hash is not None \
                and f.integrity_checked_hash == f.content_hash:
            res["skipped"] += 1
            continue
        result = checker(f.path)
        f.integrity_ok = result.ok
        f.integrity_detail = result.detail
        f.integrity_checked_hash = f.content_hash
        res["checked"] += 1
        if not result.ok:
            res["corrupt"] += 1
        db.commit()
    if on_progress is not None:
        on_progress(total, total, "checking")
    return res
```
(Se `utcnow` non serve, non importarlo — evita warning/lint.)

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_integrity_service.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/app/services/integrity.py backend/tests/
git commit -m "feat(integrity): colonne DB + servizio incrementale (cache su content_hash)"
```

---

### Task 7: Job in background + endpoint

**Files:**
- Create: `backend/app/services/integrity_job.py`
- Modify: `backend/app/routers/issues.py` (endpoint start + status)
- Test: `backend/tests/test_integrity_endpoint.py`

**Interfaces:**
- Consumes: `run_integrity` da Task 6, `ffmpeg_available` da Task 5.
- Produces:
  - `integrity_job.start(force: bool) -> dict` (job_state), `integrity_job.job_state() -> dict`, `integrity_job.is_running() -> bool`.
  - `POST /api/issues/integrity-check` (body opzionale `{force: bool}`) → job_state; `GET /api/issues/integrity-check/status` → job_state. Se ffmpeg manca: risposta con `status="error"` / `available=False` e nessun job avviato.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_integrity_endpoint.py`:

```python
def test_integrity_check_reports_unavailable_without_ffmpeg(client, monkeypatch):
    import app.services.integrity_job as job
    monkeypatch.setattr(job, "ffmpeg_available", lambda: False)
    r = client.post("/api/issues/integrity-check", json={"force": False})
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_integrity_status_shape(client):
    r = client.get("/api/issues/integrity-check/status")
    assert r.status_code == 200
    assert "status" in r.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_integrity_endpoint.py -q`
Expected: FAIL (endpoint 404 / modulo job assente).

- [ ] **Step 3: Write minimal implementation**

1. Create `backend/app/services/integrity_job.py` (ricalca `provider_rescan_job.py`):
```python
"""Job integrita' in background. Mono-job con stato in memoria (come
provider_rescan_job): la UI lancia e fa polling di job_state()."""

import logging
import threading

from app.db import SessionLocal
from app.integrations.integrity import ffmpeg_available
from app.models import utcnow
from app.services import integrity

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle", "phase": None, "processed": 0, "total": 0,
    "result": None, "error": None, "available": True,
    "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run(force: bool) -> None:
    db = SessionLocal()

    def on_progress(processed, total, phase):
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        result = integrity.run_integrity(db, force=force, on_progress=on_progress)
        with _lock:
            _state.update(status="done", phase=None, result=result,
                          finished_at=utcnow().isoformat())
    except Exception as exc:  # noqa: BLE001
        logger.exception("integrity job fallito")
        with _lock:
            _state.update(status="error", error=str(exc),
                          finished_at=utcnow().isoformat())
    finally:
        db.close()


def start(force: bool = False) -> dict:
    if not ffmpeg_available():
        with _lock:
            _state.update(status="error", available=False,
                          error="ffmpeg non disponibile")
            return dict(_state)
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(status="running", phase="checking", processed=0, total=0,
                      result=None, error=None, available=True,
                      started_at=utcnow().isoformat(), finished_at=None)
    threading.Thread(target=_run, args=(force,), daemon=True).start()
    with _lock:
        return dict(_state)
```

2. In `backend/app/routers/issues.py` aggiungi gli endpoint (vicino a quelli di provider-rescan) e l'import `from app.services import integrity_job`:
```python
@router.post("/integrity-check", response_model=dict)
def integrity_check_start(body: IntegrityCheckBody | None = None):
    force = bool(body.force) if body else False
    return integrity_job.start(force=force)


@router.get("/integrity-check/status", response_model=dict)
def integrity_check_status():
    return integrity_job.job_state()
```

3. In `backend/app/schemas.py` aggiungi:
```python
class IntegrityCheckBody(BaseModel):
    force: bool = False
```
e importalo in `routers/issues.py` insieme agli altri schemi.

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_integrity_endpoint.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/integrity_job.py backend/app/routers/issues.py backend/app/schemas.py backend/tests/test_integrity_endpoint.py
git commit -m "feat(integrity): job in background + endpoint integrity-check"
```

---

### Task 8: Issue `corrupt_file` + confluenza nei removals (quarantena)

**Files:**
- Modify: `backend/app/services/inspector.py` (emissione `corrupt_file`)
- Modify: `backend/app/services/planning.py` (`_inputs`: union removals)
- Test: `backend/tests/test_inspector.py`, `backend/tests/test_planning*.py`

**Interfaces:**
- Consumes: `AudioFile.integrity_ok` / `integrity_detail` da Task 6.
- Produces: `_inspect_one` emette un `IssueComputed(type="corrupt_file", severity="error", suggested_fix={"action": "quarantine"})` quando `integrity_ok is False`; `planning._inputs` include i `file_id` delle issue `corrupt_file` accettate nel set `removals`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_inspector.py`:
```python
def test_corrupt_file_emits_error_issue():
    from app.services.inspector import _inspect_one

    class F:
        id = 1; scan_error = None; artist = "A"; title = "T"; album = "Al"
        genre = "House"; year = 2020; label = "L"; comment = None
        path = "/x.flac"; ext = ".flac"; bitrate = None; duration_s = 200.0
        has_cover = True; has_rating = False
        integrity_ok = False; integrity_detail = "Invalid data found"

    issues = _inspect_one(F())
    corrupt = [i for i in issues if i.type == "corrupt_file"]
    assert len(corrupt) == 1
    assert corrupt[0].severity == "error"
    assert corrupt[0].suggested_fix == {"action": "quarantine"}


def test_unchecked_file_emits_no_corrupt_issue():
    from app.services.inspector import _inspect_one

    class F:
        id = 1; scan_error = None; artist = "A"; title = "T"; album = "Al"
        genre = "House"; year = 2020; label = "L"; comment = None
        path = "/x.flac"; ext = ".flac"; bitrate = None; duration_s = 200.0
        has_cover = True; has_rating = False
        integrity_ok = None; integrity_detail = None

    issues = _inspect_one(F())
    assert not [i for i in issues if i.type == "corrupt_file"]
```

In `backend/tests/test_planning*.py` (adatta al pattern esistente):
```python
def test_accepted_corrupt_file_enters_removals(db, make_file):
    f = make_file(path="/bad.flac", content_hash="h", status="present")
    # crea Issue corrupt_file accettata
    from app.models import Issue
    db.add(Issue(file_id=f.id, type="corrupt_file", field=None, severity="error",
                 detail="corrotto", suggested_fix_json={"action": "quarantine"},
                 status="accepted"))
    db.commit()
    from app.services.planning import _inputs
    _files, _accepted, removals, _snap, _targets = _inputs(db)
    assert f.id in removals
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_inspector.py backend/tests/test_planning*.py -q -k "corrupt or removals"`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

1. In `backend/app/services/inspector.py`, in fondo a `_inspect_one` (prima di `return out`), aggiungi:
```python
    if getattr(f, "integrity_ok", None) is False:
        out.append(IssueComputed(f.id, "corrupt_file", None, "error",
                                 f.integrity_detail or "file corrotto",
                                 {"action": "quarantine"}))
```

2. In `backend/app/services/planning.py`, dentro `_inputs`, dopo il calcolo di `removals` dai duplicati, aggiungi l'unione con le corrupt_file accettate (la lista `accepted` è già disponibile lì):
```python
    removals |= {i.file_id for i in accepted
                 if i.type == "corrupt_file"
                 and (i.suggested_fix_json or {}).get("action") == "quarantine"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_inspector.py backend/tests/test_planning*.py -q`
Expected: PASS. Verifica che l'analisi (`analysis.recompute`) faccia il merge dell'issue `corrupt_file` come per gli altri tipi (nessuna modifica attesa: `inspect()` le raccoglie già).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/inspector.py backend/app/services/planning.py backend/tests/
git commit -m "feat(integrity): issue corrupt_file -> removals -> quarantena"
```

---

### Task 9: Frontend Parte 2 — toggle Arricchisci/Manutenzione + bottone integrità

**Files:**
- Modify: `frontend/app/issues/page.tsx` (toggle + gruppi + call integrity)
- Modify: `frontend/lib/api.ts` (client integrity-check + status)
- Modify: `frontend/components/issues-table.tsx` (rendering FIX per action `quarantine`)
- Modify: `frontend/lib/i18n/en.ts` e `it.ts` (chiavi toggle + bottone integrità)

**Interfaces:**
- Consumes: endpoint `POST /api/issues/integrity-check` (+ `/status`) da Task 7; issue `corrupt_file` con `suggested_fix.action == "quarantine"`.

- [ ] **Step 1: Client API**

In `frontend/lib/api.ts` aggiungi:
```ts
export interface IntegrityResult {
  scanned: number; checked: number; skipped: number; corrupt: number;
}
export interface IntegrityJobState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null; processed: number; total: number;
  result: IntegrityResult | null; error: string | null; available: boolean;
  started_at: string | null; finished_at: string | null;
}
export function integrityCheck(force = false) {
  return apiSend<IntegrityJobState>("POST", "/api/issues/integrity-check", { force });
}
export function integrityStatus() {
  return apiGet<IntegrityJobState>("/api/issues/integrity-check/status");
}
```

- [ ] **Step 2: i18n**

In `frontend/lib/i18n/en.ts` (poi tradurre in `it.ts`):
```ts
    modeEnrich: "Enrich",
    modeMaintenance: "Maintenance",
    integrityBtn: "CHECK INTEGRITY",
    integrityDesc: "Decode every file with ffmpeg to find corrupt/truncated ones — corrupt files are proposed for quarantine.",
    integrityTag: "FFMPEG",
    integrityUnavailable: "ffmpeg not found — install it to enable this check.",
    integrityNote: (corrupt: number, checked: number) =>
      `Integrity: ${corrupt} corrupt over ${checked} checked.`,
    fixQuarantine: "→ quarantine",
```
`it.ts`:
```ts
    modeEnrich: "Arricchisci",
    modeMaintenance: "Manutenzione",
    integrityBtn: "CONTROLLA INTEGRITÀ",
    integrityDesc: "Decodifica ogni file con ffmpeg per trovare i corrotti/troncati — i corrotti si propongono per la quarantena.",
    integrityTag: "FFMPEG",
    integrityUnavailable: "ffmpeg non trovato — installalo per abilitare il controllo.",
    integrityNote: (corrupt, checked) =>
      `Integrità: ${corrupt} corrotti su ${checked} controllati.`,
    fixQuarantine: "→ quarantena",
```

- [ ] **Step 3: Toggle + gruppi nella pagina**

In `frontend/app/issues/page.tsx`:

1. Aggiungi lo stato del toggle (default `enrich`, non persistente):
```tsx
  const [enrichMode, setEnrichMode] = useState<"enrich" | "maintenance">("enrich");
```

2. L'array `enrichSources` (indici 0–4) ha 5 voci: 0=AI artist/title, 1=AI genre, 2=import missing, 3=covers, 4=ratings. Marca ogni voce con un gruppo (aggiungi `group: "enrich" | "maintenance"`): 0,1,2 → `"enrich"`; 3,4 → `"maintenance"`. Aggiungi in coda una 6ª voce per l'integrità con `group: "maintenance"` che chiama `integrityCheck()` (con lo stesso handler/spinner delle altre azioni; a fine job mostra `t.issues.integrityNote(result.corrupt, result.checked)`, e se `available === false` mostra `t.issues.integrityUnavailable` e disabilita il bottone).

3. Il segmented control sopra la lista dei bottoni:
```tsx
  <div className="mb-2 flex gap-1 text-[10px] uppercase tracking-wider">
    {(["enrich", "maintenance"] as const).map((m) => (
      <button key={m} type="button" onClick={() => setEnrichMode(m)}
        className={cn("border px-2 py-0.5",
          enrichMode === m ? "border-fg text-fg" : "border-faint text-faint")}>
        {m === "enrich" ? t.issues.modeEnrich : t.issues.modeMaintenance}
      </button>
    ))}
  </div>
```

4. Filtra il render: `enrichSources.filter(s => s.group === enrichMode).map(...)`. La sezione `FORCE PROVIDER LOOKUP` (il blocco `forceOpen`) va mostrata **solo** quando `enrichMode === "maintenance"`.

- [ ] **Step 4: Rendering FIX per quarantena**

In `frontend/components/issues-table.tsx`, dove si renderizza la colonna FIX di una issue: se `issue.suggested_fix_json?.action === "quarantine"`, mostra `t.issues.fixQuarantine` (etichetta "→ quarantena") invece del valore `to`. Individua il punto con:

Run: `grep -n "suggested_fix_json\|\.to\b\|FIX\|fix" frontend/components/issues-table.tsx`

e aggiungi il ramo `action === "quarantine"` prima del rendering generico del valore.

- [ ] **Step 5: Verifica tipi + browser + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: nessun errore.

Verifica nel preview: la pagina Issues mostra il toggle `Arricchisci`/`Manutenzione`; in `Manutenzione` compaiono covers, ratings, `CONTROLLA INTEGRITÀ` (+ force); lancia il controllo integrità e verifica la nota. Screenshot come prova.

```bash
git add frontend/
git commit -m "feat(ui): toggle Arricchisci/Manutenzione + bottone controllo integrita'"
```

---

### Task 10: Documentazione dipendenza + suite completa

**Files:**
- Modify: `DEPENDENCIES.md`

- [ ] **Step 1: Documenta ffmpeg**

In `DEPENDENCIES.md`, nella sezione dei binari opzionali (dove è documentato `fpcalc`), aggiungi una riga per `ffmpeg`: usato dal controllo integrità file; opzionale; senza di esso il controllo è inattivo (degrada pulito). Su macOS: `brew install ffmpeg`.

- [ ] **Step 2: Suite backend completa**

Run: `backend/.venv/bin/python -m pytest backend/tests -q`
Expected: tutti verdi (i ~322 preesistenti + i nuovi). Se qualche test preesistente asseriva `"high"`/`"text"`, `proposed_high`/`proposed_text` o la rotta `accept-high`, aggiornalo al nuovo vocabolario/rotta.

- [ ] **Step 3: Typecheck frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: nessun errore.

- [ ] **Step 4: Commit**

```bash
git add DEPENDENCIES.md
git commit -m "docs(deps): ffmpeg opzionale per il controllo integrita' file"
```

---

## Note di verifica finale

- **Parte 1 e Parte 2 sono indipendenti:** si possono implementare/rivedere come due tracce. Se vuoi spezzare in due PR, Task 1–4 = Parte 1, Task 5–10 = Parte 2.
- **Retrocompatibilità Parte 1:** nessuna migrazione; i badge e l'endpoint accept tollerano i vecchi `high`/`text`, che si auto-guariscono al primo rescan.
- **Sicurezza Parte 2:** un file corrotto non viene mai toccato senza passare da Plan approvato + Apply; la quarantena è reversibile via undo journal.
