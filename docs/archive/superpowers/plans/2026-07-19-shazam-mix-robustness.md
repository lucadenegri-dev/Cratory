# Riconoscimento mix piu' robusto (Shazam) — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** eliminare tracce fantasma e doppioni nell'identificazione dei mix: conferma dei match singoli, retry sui buchi, dedup con finestra, confidence reale (90/45) e badge "Dubbia" in UI.

**Architecture:** tutto il nuovo comportamento vive nel cuore puro di `backend/app/services/mix_identify.py` (testabile con recognizer finto, zero rete): una passata di campionamento con retry sui buchi, raggruppamento in serie con conteggio dei hit e finestra sui buchi, poi una passata di conferma per le serie singole, con un budget di chiamate extra. Il frontend aggiunge solo un badge condizionale sulla confidence.

**Tech Stack:** Python 3 + pytest (backend), Next.js 16 + vitest/@testing-library (frontend).

**Spec:** `docs/superpowers/specs/2026-07-19-shazam-mix-robustness-design.md`

## Global Constraints

- Le tracce identificate NON entrano in libreria (corpus separato `DjSet`/`DjSetTrack`).
- Nessuna modifica a DB, schema o API: `confidence` esiste gia' su `DjSetTrack`.
- Budget chiamate extra: **50** per mix (retry prima, conferme poi); tetto totale 150.
- Confidence: `hits >= 2` → **90**; `hits == 1` non confermata → **45**; soglia UI "dubbia": **< 60**. I set gia' analizzati restano a 80 (nessuna migrazione).
- Finestra di dedup: fino a **2 buchi consecutivi** sugli offset pianificati (un retry fallito NON e' un secondo buco).
- Commit message in italiano, stile `feat(scope): …` del repo, **senza** Co-Authored-By.
- Comandi test: backend `cd backend && .venv/bin/python -m pytest tests -q`; frontend `cd frontend && npm run test:unit`.
- Fuori scope: retry pitch-compensato, raffinamento dei confini di inizio traccia.

---

### Task 1: dedup a finestra + confidence dai hit (cuore puro)

Sostituisce il collasso secco `dedup_consecutive` con `group_samples` (serie con
conteggio dei hit e finestra sui buchi) + `build_tracks` (confidence 90/45 dai hit).
`parse_shazam` smette di inventare la confidence fissa 80.

**Files:**
- Modify: `backend/app/services/mix_identify.py`
- Modify: `backend/app/integrations/shazam.py`
- Test: `backend/tests/test_mix_identify.py`

**Interfaces:**
- Consumes: `_match_key(match) -> tuple` (esistente, invariato); `IdentifiedTrack` (esistente, invariato).
- Produces:
  - `MatchRun` dataclass: `key: tuple`, `offset: int`, `match: dict[str, Any]`, `hits: int = 1`
  - `group_samples(samples: list[tuple[int, dict | None]]) -> list[MatchRun]`
  - `build_tracks(runs: list[MatchRun]) -> list[IdentifiedTrack]`
  - Costanti: `MERGE_MAX_GAPS = 2`, `CONFIDENCE_CONFIRMED = 90`, `CONFIDENCE_DUBIOUS = 45`
  - `dedup_consecutive` **rimossa** (era usata solo da `identify_from_recognizer` e dai test).
  - `parse_shazam` non include piu' la chiave `confidence` nel match.

- [ ] **Step 1: riscrivi i test del raggruppamento**

In `backend/tests/test_mix_identify.py` sostituisci l'import e l'intera sezione
`--- dedup_consecutive ---` (funzione `_m` compresa) con:

```python
from app.integrations.shazam import parse_shazam
from app.services.mix_identify import (
    CONFIDENCE_CONFIRMED,
    CONFIDENCE_DUBIOUS,
    build_tracks,
    group_samples,
    identify_from_recognizer,
    plan_offsets,
)


# --- group_samples / build_tracks -------------------------------------------


def _m(artist, title, isrc=None):
    return {"artist": artist, "title": title, "isrc": isrc}


def test_group_collapses_consecutive_same_track_counting_hits():
    samples = [
        (0, _m("A", "One")),
        (12, _m("A", "One")),       # stesso brano campionato di nuovo -> stessa serie
        (24, _m("B", "Two")),
        (36, None),                  # buco
        (48, _m("C", "Three")),
    ]
    runs = group_samples(samples)
    assert [(r.match["artist"], r.match["title"], r.hits) for r in runs] == [
        ("A", "One", 2), ("B", "Two", 1), ("C", "Three", 1),
    ]
    assert runs[0].offset == 0  # tiene il primo offset della serie


def test_group_merges_same_track_across_small_gaps():
    # 1-2 buchi con la stessa traccia ai due lati: e' la stessa voce, non un doppione
    samples = [(0, _m("A", "One")), (12, None), (24, None), (36, _m("A", "One"))]
    runs = group_samples(samples)
    assert len(runs) == 1
    assert runs[0].hits == 2


def test_group_three_gaps_break_the_window():
    samples = [(0, _m("A", "One")), (12, None), (24, None), (36, None), (48, _m("A", "One"))]
    assert len(group_samples(samples)) == 2  # 3+ buchi: il DJ l'ha rimessa davvero


def test_group_other_track_between_breaks_the_window():
    samples = [(0, _m("A", "One")), (12, _m("B", "Two")), (24, _m("A", "One"))]
    assert len(group_samples(samples)) == 3  # A torna dopo B: voce nuova


def test_group_uses_isrc_when_present():
    # stesso ISRC ma titolo scritto diversamente -> stesso brano
    samples = [(0, _m("A", "One", isrc="X1")), (12, _m("A", "One (Extended)", isrc="X1"))]
    runs = group_samples(samples)
    assert len(runs) == 1 and runs[0].hits == 2


def test_build_tracks_confidence_from_hits():
    runs = group_samples([(0, _m("A", "One")), (12, _m("A", "One")), (24, _m("B", "Two"))])
    out = build_tracks(runs)
    assert [t.position for t in out] == [1, 2]
    assert out[0].confidence == CONFIDENCE_CONFIRMED   # 2 campioni concordi
    assert out[1].confidence == CONFIDENCE_DUBIOUS     # campione singolo
    assert out[0].start_offset_seconds == 0 and out[1].start_offset_seconds == 24
```

Nella sezione `--- parsing payload Shazam ---` sostituisci l'assert sulla
confidence in `test_parse_shazam_extracts_fields`:

```python
    assert "confidence" not in out  # la confidence e' un derivato dei hit, non del parse
```

- [ ] **Step 2: verifica che i test falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mix_identify.py -q`
Expected: FAIL/ERROR con `ImportError: cannot import name 'group_samples'`.

- [ ] **Step 3: implementa group_samples/build_tracks e rimuovi dedup_consecutive**

In `backend/app/services/mix_identify.py`:

Aggiungi le costanti sotto quelle esistenti (dopo `MAX_CONSECUTIVE_ERRORS`):

```python
MERGE_MAX_GAPS = 2       # buchi consecutivi oltre i quali la stessa traccia e' una voce nuova
CONFIDENCE_CONFIRMED = 90  # 2+ campioni concordi
CONFIDENCE_DUBIOUS = 45    # campione singolo mai confermato
```

Sostituisci l'intera funzione `dedup_consecutive` (righe 74-98) con:

```python
@dataclass
class MatchRun:
    """Serie di campioni concordi sulla stessa traccia."""
    key: tuple
    offset: int  # offset del primo campione della serie
    match: dict[str, Any]
    hits: int = 1


def group_samples(samples: list[tuple[int, dict[str, Any] | None]]) -> list[MatchRun]:
    """Raggruppa i campioni in serie per traccia, con finestra sui buchi.

    `samples` = [(offset, match|None), ...] in ordine di offset. Campioni consecutivi
    con la stessa chiave si sommano (`hits`). La stessa chiave che ricompare dopo
    soli buchi (fino a MERGE_MAX_GAPS consecutivi) si fonde con la serie precedente;
    con piu' buchi, o un'altra traccia in mezzo, e' una serie nuova (il DJ l'ha
    rimessa davvero)."""
    runs: list[MatchRun] = []
    gap_count = 0
    for offset, match in samples:
        if not match:
            gap_count += 1
            continue
        key = _match_key(match)
        if runs and runs[-1].key == key and gap_count <= MERGE_MAX_GAPS:
            runs[-1].hits += 1
        else:
            runs.append(MatchRun(key=key, offset=offset, match=match))
        gap_count = 0
    return runs


def build_tracks(runs: list[MatchRun]) -> list[IdentifiedTrack]:
    """Serie -> tracklist. La confidence deriva dai campioni concordi: 2+ =
    confermata, 1 = dubbia (resta in lista, la UI la marca)."""
    return [
        IdentifiedTrack(
            position=i,
            start_offset_seconds=run.offset,
            artist=run.match["artist"],
            title=run.match["title"],
            isrc=run.match.get("isrc"),
            apple_id=run.match.get("apple_id"),
            confidence=CONFIDENCE_CONFIRMED if run.hits >= 2 else CONFIDENCE_DUBIOUS,
        )
        for i, run in enumerate(runs, start=1)
    ]
```

In `identify_from_recognizer` sostituisci l'ultima riga `return dedup_consecutive(samples)` con:

```python
    return build_tracks(group_samples(samples))
```

Aggiorna la riga della docstring di modulo che cita il cuore puro: sostituisci
`` `dedup_consecutive` `` con `` `group_samples`/`build_tracks` ``.

In `backend/app/integrations/shazam.py` togli da `parse_shazam` la riga:

```python
        "confidence": 80,  # Shazam non da' uno score: match = confidenza alta ma non certa
```

e aggiorna la docstring dell'ABC `AudioRecognizer`: il match normalizzato e'
`{"artist": str, "title": str, "isrc": str|None, "apple_id": str|None}` (la
confidence la calcola `mix_identify` dai campioni concordi).

- [ ] **Step 4: verifica che i test passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mix_identify.py -q`
Expected: PASS (tutti). Poi l'intera suite: `.venv/bin/python -m pytest tests -q` → PASS.

- [ ] **Step 5: commit**

```bash
git add backend/app/services/mix_identify.py backend/app/integrations/shazam.py backend/tests/test_mix_identify.py
git commit -m "feat(shazam): dedup a finestra sui buchi e confidence derivata dai campioni concordi"
```

---

### Task 2: retry sui buchi + conferma dei singoli + budget

`identify_from_recognizer` ritenta una volta i buchi a un offset vicino, poi
conferma le serie con un solo hit con un campione a ±4s. Tutto dentro un budget
di 50 chiamate extra. La firma resta compatibile (nuovo kwarg con default).

**Files:**
- Modify: `backend/app/services/mix_identify.py`
- Test: `backend/tests/test_mix_identify.py`

**Interfaces:**
- Consumes: `group_samples`, `build_tracks`, `MatchRun`, `_match_key`, `CONFIDENCE_*` (Task 1); `plan_offsets`, `RecognizerError`, `SEGMENT_LENGTH` (esistenti).
- Produces:
  - `identify_from_recognizer(duration_seconds, recognize_at, *, on_progress=None, max_extra_calls=MAX_EXTRA_CALLS) -> list[IdentifiedTrack]`
  - Costanti: `MAX_EXTRA_CALLS = 50`, `CONFIRM_DELTA = 4`
  - `_retry_delta(step: int) -> int` (interna)
  - Nessun cambiamento per i chiamanti: `identify_set` e `mix_identify_job` restano invariati.

- [ ] **Step 1: scrivi i test del nuovo comportamento**

In `backend/tests/test_mix_identify.py` sostituisci la sezione
`--- identify_from_recognizer ---` (il solo `test_identify_from_recognizer_end_to_end`) con:

```python
# --- identify_from_recognizer (recognizer finto) -----------------------------
# Con durata 60: offsets pianificati [0, 12, 24, 36, 48], passo 12, retry a +6s.


def _tracker(table):
    calls: list[int] = []

    def recognize_at(offset: int):
        calls.append(offset)
        return table.get(offset)

    return calls, recognize_at


def test_identify_retry_fills_hole_and_confirms_singles():
    # buco a 12 -> il retry a 18 becca A (stessa serie di 0: hit 2, confermata);
    # B ha un solo hit -> campione di conferma a 24+4=28 (buco: resta dubbia).
    table = {0: _m("A", "One"), 18: _m("A", "One"), 24: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out = identify_from_recognizer(60, recognize_at)
    # 36 -> retry a 42; 48 -> il retry (54) sforerebbe la durata: clampato a 48, saltato
    assert calls == [0, 12, 18, 24, 36, 42, 48, 28]
    assert [(t.artist, t.title, t.confidence) for t in out] == [
        ("A", "One", CONFIDENCE_CONFIRMED), ("B", "Two", CONFIDENCE_DUBIOUS),
    ]


def test_identify_confirmation_promotes_single_to_confirmed():
    # durata 36 -> offsets [0, 12, 24]. B singola a 12, la conferma a 16 concorda.
    table = {0: _m("A", "One"), 12: _m("B", "Two"), 16: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out = identify_from_recognizer(36, recognize_at)
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_DUBIOUS),      # conferma a 0+4=4: buco -> dubbia
        ("B", CONFIDENCE_CONFIRMED),    # conferma a 16 concorde -> 90
    ]
    assert 4 in calls and 16 in calls


def test_identify_budget_zero_disables_retry_and_confirm():
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two")}
    calls, recognize_at = _tracker(table)
    out = identify_from_recognizer(60, recognize_at, max_extra_calls=0)
    assert calls == plan_offsets(60)  # solo la griglia pianificata
    assert [(t.artist, t.confidence) for t in out] == [
        ("A", CONFIDENCE_CONFIRMED), ("B", CONFIDENCE_DUBIOUS),
    ]


def test_identify_error_on_grid_recovered_by_retry():
    # errore sull'offset pianificato, il retry riconosce: la serie non si spezza
    table = {6: _m("A", "One"), 12: _m("A", "One")}

    def recognize_at(offset: int):
        if offset == 0:
            raise RecognizerError("boom")
        return table.get(offset)

    out = identify_from_recognizer(24, recognize_at)  # offsets [0, 12]
    assert [(t.artist, t.confidence) for t in out] == [("A", CONFIDENCE_CONFIRMED)]


def test_identify_stops_after_max_consecutive_errors():
    calls: list[int] = []

    def recognize_at(offset: int):
        calls.append(offset)
        raise RecognizerError("down")

    out = identify_from_recognizer(7200, recognize_at)
    assert out == []
    assert len(calls) == 8  # MAX_CONSECUTIVE_ERRORS, retry compresi


def test_identify_progress_extends_total_with_confirmations():
    table = {0: _m("A", "One"), 12: _m("A", "One"), 24: _m("B", "Two")}
    progress: list[tuple[int, int]] = []
    _, recognize_at = _tracker(table)
    identify_from_recognizer(60, recognize_at, on_progress=lambda i, n: progress.append((i, n)))
    assert progress[:5] == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]  # passata principale
    assert progress[-1] == (6, 6)  # la conferma di B estende il totale
```

Aggiungi in testa al file l'import di `RecognizerError`:

```python
from app.integrations.shazam import RecognizerError, parse_shazam
```

- [ ] **Step 2: verifica che i test falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mix_identify.py -q`
Expected: FAIL (retry/conferme inesistenti: liste `calls` diverse, confidence sbagliate,
`TypeError` su `max_extra_calls`).

- [ ] **Step 3: implementa retry + conferme + budget**

In `backend/app/services/mix_identify.py` aggiungi le costanti (accanto alle altre):

```python
MAX_EXTRA_CALLS = 50  # budget per retry sui buchi + conferme dei singoli (per mix)
CONFIRM_DELTA = 4     # secondi di scarto del campione di conferma
```

Aggiungi sopra `identify_from_recognizer`:

```python
def _retry_delta(step: int) -> int:
    """Spostamento del retry su un buco: mezzo passo, tra 6 e 20 secondi."""
    return max(6, min(step // 2, 20))
```

Sostituisci l'intera `identify_from_recognizer` con:

```python
def identify_from_recognizer(
    duration_seconds: int,
    recognize_at: Callable[[int], dict[str, Any] | None],
    *,
    on_progress: ProgressFn | None = None,
    max_extra_calls: int = MAX_EXTRA_CALLS,
) -> list[IdentifiedTrack]:
    """Campiona gli offset, riconosce, conferma e deduplica.

    `recognize_at(offset)->match|None` isola l'I/O: i test passano una funzione
    finta. Robustezza (tutto entro `max_extra_calls` chiamate oltre la griglia):
    un buco viene ritentato una volta a offset spostato (le transizioni sono la
    causa principale); le serie con un solo campione ricevono un campione di
    conferma a +-CONFIRM_DELTA, e restano in lista come dubbie se non confermate.
    Il campione di un retry riuscito resta registrato all'offset pianificato."""
    offsets = plan_offsets(duration_seconds)
    step = offsets[1] - offsets[0] if len(offsets) > 1 else SEGMENT_LENGTH
    budget = max_extra_calls
    consecutive_errors = 0

    def try_recognize(offset: int) -> dict[str, Any] | None:
        nonlocal consecutive_errors
        try:
            match = recognize_at(offset)
            consecutive_errors = 0
            return match
        except RecognizerError as exc:
            logger.warning("Riconoscimento fallito a %ss: %s", offset, exc)
            consecutive_errors += 1
            return None

    samples: list[tuple[int, dict[str, Any] | None]] = []
    for i, offset in enumerate(offsets, start=1):
        match = try_recognize(offset)
        if match is None and budget > 0 and consecutive_errors < MAX_CONSECUTIVE_ERRORS:
            retry_at = offset + _retry_delta(step)
            if duration_seconds > 0:
                retry_at = min(retry_at, max(0, duration_seconds - SEGMENT_LENGTH))
            if retry_at > offset:
                budget -= 1
                match = try_recognize(retry_at)
        samples.append((offset, match))
        if on_progress:
            on_progress(i, len(offsets))
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            logger.error("Troppi errori di riconoscimento consecutivi: interrompo.")
            break

    runs = group_samples(samples)

    to_confirm = [r for r in runs if r.hits == 1]
    total = len(offsets) + len(to_confirm)
    done = len(offsets)
    for run in to_confirm:
        if budget <= 0:
            break  # budget esaurito: i singoli restano dubbi
        budget -= 1
        confirm_at = run.offset + CONFIRM_DELTA
        if duration_seconds > 0 and confirm_at + SEGMENT_LENGTH > duration_seconds:
            confirm_at = max(0, run.offset - CONFIRM_DELTA)
        match = try_recognize(confirm_at)
        if match is not None and _match_key(match) == run.key:
            run.hits += 1
        done += 1
        if on_progress:
            on_progress(done, total)

    return build_tracks(runs)
```

Aggiorna la docstring di modulo (righe 1-12): il punto 3 della pipeline diventa
"3. riconoscimento di ogni segmento con retry sui buchi (AudioRecognizer, iniettato);"
e il punto 4 "4. conferma dei match singoli e dedup con finestra sui buchi
(gestisce le transizioni del DJ).".

- [ ] **Step 4: verifica che i test passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mix_identify.py -q`
Expected: PASS. Poi l'intera suite: `.venv/bin/python -m pytest tests -q` → PASS
(in particolare `test_mix_identify_job.py` e `test_mix_probe_duration.py`, che
monkeypatchano `identify_set`/`identify_from_recognizer` e non devono rompersi).

- [ ] **Step 5: commit**

```bash
git add backend/app/services/mix_identify.py backend/tests/test_mix_identify.py
git commit -m "feat(shazam): retry sui buchi e conferma dei match singoli, con budget di chiamate"
```

---

### Task 3: badge "Dubbia" in UI

Le voci con `confidence < 60` mostrano un badge nella pagina del set. Componente
minimo riusabile + chiavi i18n IT/EN + test vitest.

**Files:**
- Create: `frontend/components/confidence-badge.tsx`
- Modify: `frontend/app/shazam/[id]/page.tsx` (riga ~191, dentro il `<li>` della tracklist)
- Modify: `frontend/lib/i18n/it.ts` (sezione `shazam.detail`, vicino a `ownedBadge`)
- Modify: `frontend/lib/i18n/en.ts` (stessa posizione)
- Test: `frontend/tests/confidence-badge.test.tsx`

**Interfaces:**
- Consumes: `Badge` da `@/components/ui` (tone `"warning"`), `useT` da `@/lib/i18n` (fuori provider usa il dizionario IT di default), `DjSetTrack.confidence: number | null` (esistente).
- Produces: `ConfidenceBadge({ confidence }: { confidence: number | null })` — rende `null` se `confidence` e' null o >= 60; `DUBIOUS_CONFIDENCE_THRESHOLD = 60`.

- [ ] **Step 1: scrivi il test del badge**

Create `frontend/tests/confidence-badge.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ConfidenceBadge } from "@/components/confidence-badge";

describe("confidence badge", () => {
  afterEach(cleanup);

  it("marca come dubbia una voce sotto la soglia", () => {
    render(<ConfidenceBadge confidence={45} />);
    expect(screen.getByText("DUBBIA")).toBeTruthy();
  });

  it("niente badge con confidence alta, legacy o assente", () => {
    render(
      <>
        <ConfidenceBadge confidence={90} />
        <ConfidenceBadge confidence={80} />
        <ConfidenceBadge confidence={null} />
      </>,
    );
    expect(screen.queryByText("DUBBIA")).toBeNull();
  });
});
```

- [ ] **Step 2: verifica che il test fallisca**

Run: `cd frontend && npm run test:unit -- tests/confidence-badge.test.tsx`
Expected: FAIL (modulo `@/components/confidence-badge` inesistente).

- [ ] **Step 3: implementa componente, i18n e wiring**

Create `frontend/components/confidence-badge.tsx`:

```tsx
"use client";

import { Badge } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Sotto questa confidence il match Shazam e' dubbio (un solo campione concorde). */
export const DUBIOUS_CONFIDENCE_THRESHOLD = 60;

/** Badge "Dubbia" per le tracce identificate con un solo campione mai confermato.
 *  I set analizzati prima della confidence reale (80 fisso) non lo mostrano. */
export function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  const t = useT();
  if (confidence == null || confidence >= DUBIOUS_CONFIDENCE_THRESHOLD) return null;
  return (
    <span title={t.shazam.detail.dubiousBadgeTitle} className="shrink-0">
      <Badge tone="warning">{t.shazam.detail.dubiousBadge}</Badge>
    </span>
  );
}
```

In `frontend/lib/i18n/it.ts`, dentro `shazam.detail` dopo `inLibraryBadge`:

```ts
      dubiousBadge: "DUBBIA",
      dubiousBadgeTitle: "Riconosciuta in un solo campione: potrebbe non essere nel mix",
```

In `frontend/lib/i18n/en.ts`, stessa posizione:

```ts
      dubiousBadge: "UNCERTAIN",
      dubiousBadgeTitle: "Recognized in a single sample: it may not be in the mix",
```

In `frontend/app/shazam/[id]/page.tsx`: aggiungi l'import

```tsx
import { ConfidenceBadge } from "@/components/confidence-badge";
```

e nel `<li>` della tracklist, tra il badge ISRC e `TrackLibraryAction`:

```tsx
                {trk.isrc && <Badge tone="neutral" className="tnum shrink-0">{trk.isrc}</Badge>}
                <ConfidenceBadge confidence={trk.confidence} />
                <TrackLibraryAction track={trk} onSaved={(track) => patchTrackSaved(trk.position, track)} />
```

- [ ] **Step 4: verifica test, lint e build**

Run: `cd frontend && npm run test:unit` → PASS (tutti, non solo il nuovo).
Run: `npm run lint` → nessun errore nuovo.
Run: `npm run build` → build OK (Next 16: leggere `frontend/CLAUDE.md` se qualcosa sorprende).

- [ ] **Step 5: commit**

```bash
git add frontend/components/confidence-badge.tsx "frontend/app/shazam/[id]/page.tsx" frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/confidence-badge.test.tsx
git commit -m "feat(shazam-ui): badge Dubbia sulle tracce riconosciute da un solo campione"
```

---

### Task 4: documentazione

Allinea `docs/API.md` (semantica della confidence) e `PROGRESS.md` (diario).

**Files:**
- Modify: `docs/API.md` (sezione Shazam, dopo il paragrafo "Requires `ffmpeg`, `yt-dlp` and `shazamio`…")
- Modify: `PROGRESS.md` (nuova milestone in cima alla lista delle milestone, aggiorna "Last updated")

**Interfaces:** nessuna (solo documentazione).

- [ ] **Step 1: aggiorna API.md**

In `docs/API.md`, nel paragrafo della sezione Shazam che descrive il job
(righe ~450-453), dopo la frase "The tracks do not enter the main library."
aggiungi:

```markdown
Sampling is resilient: an unrecognized segment is retried once at a nearby
offset, and tracks recognized in a single sample get one confirmation sample
(all within a budget of 50 extra calls per mix). `DjSetTrack.confidence`
reflects the outcome: `90` = confirmed by 2+ agreeing samples, `45` = single
unconfirmed sample (the UI marks these as uncertain; sets analyzed before this
change keep the legacy fixed `80`).
```

- [ ] **Step 2: aggiorna PROGRESS.md**

In `PROGRESS.md`: cambia `**Last updated:** 2026-07-16` in `**Last updated:** 2026-07-19`
e inserisci sopra la milestone `## Milestone 2026-07-16 - Discovery…`:

```markdown
## Milestone 2026-07-19 - Shazam: riconoscimento mix piu' robusto

Il cuore di `mix_identify` non si fida piu' del singolo campione: i buchi vengono
ritentati una volta a offset vicino, le tracce viste in un solo campione ricevono
un campione di conferma (budget: 50 chiamate extra per mix) e il dedup fonde la
stessa traccia attraverso 1-2 buchi consecutivi invece di duplicarla. La
confidence ora e' reale — 90 confermata, 45 dubbia (l'80 fisso resta solo nei set
gia' analizzati) — e la pagina del set marca le voci dubbie con un badge.
Spec: `docs/superpowers/specs/2026-07-19-shazam-mix-robustness-design.md`.
```

- [ ] **Step 3: commit**

```bash
git add docs/API.md PROGRESS.md
git commit -m "docs(shazam): semantica della confidence e milestone del riconoscimento robusto"
```
