# Revisione pagina Analisi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Divergenze scartabili (snapshot che le nasconde finché l'analisi non cambia esito), analisi in-app al centro della pagina, import Rekordbox ripiegato, testi asciugati.

**Architecture:** Due colonne snapshot su `Track` (`analysis_dismissed_bpm/camelot`); il servizio `audio_analysis` guadagna `dismiss_divergence`/`is_dismissed`/`open_divergence` e il router espone le sole divergenze aperte più un `POST /dismiss`. Il frontend riordina la pagina (card Analisi in cima, Rekordbox in `<details>`) e aggiunge «Ignora» per riga e per selezione.

**Tech Stack:** FastAPI + SQLAlchemy/SQLite (migrazione automatica model-derived in `ensure_schema`), Next.js 16 + React + vitest.

**Spec:** `docs/archive/superpowers/specs/2026-08-15-pagina-analisi-revisione-design.md`

## Global Constraints

- Worktree: `/Users/lucadenegri/Develop/DJProject01/.claude/worktrees/pagina-analisi-review-bd1735` (branch `claude/pagina-analisi-review-bd1735`). Tutti i path sotto sono relativi a questa radice.
- Pytest col venv del checkout principale, cwd nel backend del worktree:
  `cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/... -v`
- Il frontend del worktree NON ha `node_modules`: prima del primo task frontend eseguire `cd frontend && npm install` (install reale, niente symlink: Turbopack si rompe coi symlink).
- Commit: MAI aggiungere `Co-Authored-By` o firme Claude nei messaggi.
- Prima di ogni commit: `git status --porcelain` e verifica del branch (sessioni parallele possibili).
- i18n: ogni chiave aggiunta o eliminata va gestita in ENTRAMBI i file `frontend/lib/i18n/it.ts` e `en.ts`.
- Niente migrazione manuale in `db.py`: `_migrate_add_model_columns` aggiunge da sola le colonne nuove presenti nei modelli (ALTER ADD model-derived, idempotente).
- Frontend Next.js 16: leggere `frontend/CLAUDE.md` prima di toccare pagine (gotcha: `{" "}` per gli spazi JSX a fine riga).
- Precisione BPM: ogni confronto a 1 decimale (`round(x, 1)`), identica a `diverges()`.

---

### Task 1: Servizio — snapshot scarto e divergenza aperta

**Files:**
- Modify: `backend/app/models.py` (dopo la riga `analysis_error`, ~117)
- Modify: `backend/app/services/audio_analysis.py`
- Test: `backend/tests/test_audio_analysis.py`

**Interfaces:**
- Consumes: `Track.analysis_bpm/analysis_camelot`, `diverges(track)` esistenti.
- Produces: colonne `Track.analysis_dismissed_bpm: float|None`, `Track.analysis_dismissed_camelot: str|None`; funzioni `dismiss_divergence(track) -> None`, `is_dismissed(track) -> bool`, `open_divergence(track) -> bool` in `app.services.audio_analysis` (Task 2 le importa con questi nomi esatti).

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi in coda a `backend/tests/test_audio_analysis.py` (e aggiorna l'import in testa):

```python
from app.services.audio_analysis import (apply_analysis, auto_apply_missing,
                                         dismiss_divergence, divergence_row,
                                         diverges, is_dismissed, open_divergence)
```

```python
def test_mai_scartata_non_e_dismissed():
    t = _t(bpm=128.0, camelot_key="8A", analysis_bpm=130.0, analysis_camelot="9A")
    assert is_dismissed(t) is False
    assert open_divergence(t) is True


def test_dismiss_nasconde_e_riappare_solo_se_il_bpm_cambia():
    t = _t(bpm=128.0, camelot_key="8A", analysis_bpm=130.0, analysis_camelot="9A")
    dismiss_divergence(t)
    assert is_dismissed(t) is True and open_divergence(t) is False
    # ri-analisi identica a 1 decimale (rumore analizzatore): resta scartata
    t.analysis_bpm = 130.04
    assert open_divergence(t) is False
    # ri-analisi con esito diverso oltre 1 decimale: riappare da sola
    t.analysis_bpm = 131.0
    assert open_divergence(t) is True


def test_dismiss_riappare_se_cambia_la_key():
    t = _t(bpm=128.0, camelot_key="8A", analysis_bpm=128.0, analysis_camelot="9A")
    dismiss_divergence(t)
    assert open_divergence(t) is False
    t.analysis_camelot = "10A"
    assert open_divergence(t) is True


def test_dismiss_con_un_solo_campo_analizzato():
    # Solo la key e' stata analizzata: lo snapshot BPM None==None deve reggere.
    t = _t(bpm=None, camelot_key="8A", analysis_bpm=None, analysis_camelot="9A")
    dismiss_divergence(t)
    assert is_dismissed(t) is True and open_divergence(t) is False
```

- [ ] **Step 2: Verifica che falliscano**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_audio_analysis.py -v
```

Atteso: FAIL/ERROR con `ImportError: cannot import name 'dismiss_divergence'`.

- [ ] **Step 3: Implementa**

In `backend/app/models.py`, subito dopo `analysis_error`:

```python
    # Scarto divergenze (pagina Analisi): snapshot dei valori analysis_* che
    # l'utente ha scelto di ignorare. La divergenza resta nascosta finche'
    # l'analisi riproduce questo esito; se cambia, riappare (is_dismissed).
    analysis_dismissed_bpm: Mapped[float | None] = mapped_column(Float)
    analysis_dismissed_camelot: Mapped[str | None] = mapped_column(String)
```

In `backend/app/services/audio_analysis.py`, dopo `diverges()`:

```python
def dismiss_divergence(track) -> None:
    """Fotografa l'esito corrente dell'analisi come «visto e ignorato»."""
    track.analysis_dismissed_bpm = track.analysis_bpm
    track.analysis_dismissed_camelot = track.analysis_camelot


def is_dismissed(track) -> bool:
    """True se lo snapshot scartato coincide con l'analisi corrente, alla
    stessa precisione di diverges(): BPM a 1 decimale (None==None), key esatta
    (vuoto==vuoto). Una nuova analisi con esito diverso lo invalida da sola."""
    bpm_same = (
        (track.analysis_bpm is None) == (track.analysis_dismissed_bpm is None)
        and (track.analysis_bpm is None
             or round(track.analysis_bpm, 1) == round(track.analysis_dismissed_bpm, 1))
    )
    key_same = (track.analysis_camelot or None) == (track.analysis_dismissed_camelot or None)
    return bpm_same and key_same


def open_divergence(track) -> bool:
    """Divergenza aperta: diverge dal canonico E non e' stata scartata."""
    return diverges(track) and not is_dismissed(track)
```

Aggiorna la docstring di modulo (primo paragrafo) aggiungendo una riga:

```text
Lo scarto (dismiss_divergence) non tocca ne' i canonici ne' analysis_*: salva
solo lo snapshot dismissed_*; is_dismissed lo confronta con l'analisi corrente.
```

- [ ] **Step 4: Verifica che passino (tutto il file, non solo i nuovi)**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_audio_analysis.py -v
```

Atteso: PASS (10 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/services/audio_analysis.py backend/tests/test_audio_analysis.py
git commit -m "feat(analysis): scarto divergenze — snapshot e is_dismissed nel servizio"
```

---

### Task 2: Router — POST /dismiss, divergenze aperte, API.md

**Files:**
- Modify: `backend/app/schemas.py` (dopo `AnalysisApplyOut`, ~714)
- Modify: `backend/app/routers/analysis.py`
- Modify: `docs/API.md` (sezione analysis, ~555-596)
- Test: `backend/tests/test_analysis_router.py`

**Interfaces:**
- Consumes: `dismiss_divergence(track)`, `open_divergence(track)` da `app.services.audio_analysis` (Task 1).
- Produces: `POST /api/analysis/dismiss` body `{track_ids: list[int]}` → `{dismissed: int}` (422 `analysis_dismiss_empty` su lista vuota); `GET /divergences`, `overview.divergent` e `apply mode='divergent'` operano solo sulle divergenze aperte. Schemi `AnalysisDismissIn`/`AnalysisDismissOut`.

- [ ] **Step 1: Scrivi i test che falliscono**

In `backend/tests/test_analysis_router.py`, aggiungi in testa (dopo `import pytest`):

```python
from datetime import datetime, timezone
```

e in coda al file:

```python
def test_dismiss_nasconde_da_divergences_e_overview(client):
    c, S = client
    _seed_divergent(S)
    r = c.post("/api/analysis/dismiss", json={"track_ids": [1]})
    assert r.status_code == 200 and r.json()["dismissed"] == 1
    assert c.get("/api/analysis/divergences").json() == []
    assert c.get("/api/analysis/overview").json()["divergent"] == 0


def test_dismiss_riappare_se_nuova_analisi_diversa(client):
    c, S = client
    _seed_divergent(S)
    c.post("/api/analysis/dismiss", json={"track_ids": [1]})
    with S() as s:
        t = s.get(Track, 1)
        t.analysis_bpm = 131.0  # nuova analisi, esito diverso dallo snapshot
        s.commit()
    rows = c.get("/api/analysis/divergences").json()
    assert len(rows) == 1 and rows[0]["analysis_bpm"] == 131.0


def test_apply_divergent_salta_le_scartate(client):
    c, S = client
    _seed_divergent(S)
    c.post("/api/analysis/dismiss", json={"track_ids": [1]})
    r = c.post("/api/analysis/apply", json={"mode": "divergent"})
    assert r.status_code == 200 and r.json() == {"applied": 0, "skipped": 0}
    with S() as s:
        assert s.get(Track, 1).bpm == 128.0  # canonico intatto


def test_force_all_riscrive_anche_le_scartate(client):
    c, S = client
    _seed_divergent(S)
    with S() as s:  # mode='all' filtra su analyzed_at
        s.get(Track, 1).analyzed_at = datetime.now(timezone.utc)
        s.commit()
    c.post("/api/analysis/dismiss", json={"track_ids": [1]})
    r = c.post("/api/analysis/apply", json={"mode": "all", "force": True})
    assert r.status_code == 200 and r.json()["applied"] == 1
    with S() as s:
        assert s.get(Track, 1).bpm == 130.0


def test_dismiss_vuoto_422(client):
    c, _ = client
    r = c.post("/api/analysis/dismiss", json={"track_ids": []})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "analysis_dismiss_empty"
```

- [ ] **Step 2: Verifica che falliscano**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_analysis_router.py -v
```

Atteso: i 5 nuovi FAIL (404 sul POST /dismiss); i 7 esistenti PASS.

- [ ] **Step 3: Implementa**

In `backend/app/schemas.py`, dopo `AnalysisApplyOut`:

```python
class AnalysisDismissIn(BaseModel):
    """Scarto divergenze: fotografa analysis_* come «visto e ignorato»."""

    model_config = ConfigDict(extra="forbid")

    track_ids: list[int]


class AnalysisDismissOut(BaseModel):
    dismissed: int
```

In `backend/app/routers/analysis.py`:

1. Import dal servizio (sostituisce la riga esistente; `diverges` non serve più qui):

```python
from app.services.audio_analysis import (apply_analysis, dismiss_divergence,
                                         divergence_row, open_divergence)
```

2. Import schemi: aggiungi `AnalysisDismissIn, AnalysisDismissOut` alla tupla.

3. In `overview()`: `divergent=sum(1 for t in owned if open_divergence(t))` (era `diverges(t)`).

4. In `divergences()`: `if open_divergence(t)` (era `diverges(t)`).

5. In `apply()`, ramo `mode == "divergent"`: `targets = [t for t in owned if open_divergence(t)]` e aggiorna la docstring: «mode='divergent' = scelta esplicita dell'utente dalle divergenze APERTE (le scartate restano fuori); mode='all' riscrive TUTTE le analizzate, scartate comprese».

6. Nuovo endpoint dopo `divergences()`:

```python
@router.post("/dismiss", response_model=AnalysisDismissOut)
def dismiss(payload: AnalysisDismissIn, db: Session = Depends(get_db)):
    """Scarta le divergenze: il canonico va bene, l'analisi e' ignorata finche'
    una nuova analisi non produce un esito diverso dallo snapshot."""
    if not payload.track_ids:
        raise api_error(422, "analysis_dismiss_empty", "Provide track_ids.")
    ids = set(payload.track_ids)
    targets = [t for t in _owned(db) if t.id in ids]
    for t in targets:
        dismiss_divergence(t)
    db.commit()
    return AnalysisDismissOut(dismissed=len(targets))
```

In `docs/API.md`: aggiungi `POST /api/analysis/dismiss` all'elenco endpoint (riga ~558, dopo `/apply`); nel paragrafo di `GET /divergences` aggiungi «Dismissed divergences are excluded.»; dopo il paragrafo di `/apply` aggiungi:

```markdown
`POST /api/analysis/dismiss` marks divergences as seen-and-ignored: body
`{track_ids}` snapshots each track's current `analysis_*` values. A dismissed
divergence disappears from `/divergences`, from the overview `divergent` count
and from `mode="divergent"` apply; it reappears only when a new analysis run
produces a different result (BPM compared at 1 decimal, key exact).
`mode="all"` + `force` still rewrites dismissed tracks. `422
analysis_dismiss_empty` on an empty list. Response `{dismissed}`.
```

- [ ] **Step 4: Verifica che passino**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_analysis_router.py tests/test_audio_analysis.py tests/test_analysis_schema.py -v
```

Atteso: PASS tutti.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/analysis.py backend/tests/test_analysis_router.py docs/API.md
git commit -m "feat(analysis): endpoint dismiss e divergenze aperte nel router"
```

---

### Task 3: Frontend — client API e bottoni «Ignora»

**Files:**
- Modify: `frontend/lib/api/analysis.ts`
- Modify: `frontend/app/analysis/page.tsx`
- Modify: `frontend/lib/i18n/it.ts` + `frontend/lib/i18n/en.ts` (sezione `analysis`)
- Test: `frontend/tests/analysis-page.test.tsx`

**Interfaces:**
- Consumes: `POST /api/analysis/dismiss` (Task 2).
- Produces: `dismissAnalysis(trackIds: number[]) -> Promise<{dismissed: number}>` in `@/lib/api`; chiavi i18n `ignoreRow`, `ignoreSelected(n)`, `ignoredSummary(n)`.

**Setup (una volta):** se `frontend/node_modules` manca: `cd frontend && npm install`.

- [ ] **Step 1: Scrivi i test che falliscono**

In `frontend/tests/analysis-page.test.tsx`:

1. Dopo `const analysisDivergences = vi.fn();` aggiungi:

```tsx
const dismissAnalysis = vi.fn();
```

2. Nel factory di `vi.mock("@/lib/api", ...)` aggiungi la riga:

```tsx
  dismissAnalysis: (...a: unknown[]) => dismissAnalysis(...a),
```

3. Nel `beforeEach` aggiungi:

```tsx
    dismissAnalysis.mockReset().mockResolvedValue({ dismissed: 1 });
```

4. In coda al `describe`:

```tsx
  it("ignora una riga senza conferma: dismiss chiamato, canonici intatti", async () => {
    mount([MIXED], { divergent: 1 });
    const row = (await screen.findByText(/Floating Points/)).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: /^ignora$/i }));
    // «Ignora» tiene il valore attuale: niente modale, niente apply.
    await waitFor(() => expect(dismissAnalysis).toHaveBeenCalledWith([1]));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(applyAnalysis).not.toHaveBeenCalled();
  });

  it("ignora selezionate manda tutti gli id scelti", async () => {
    mount([MIXED, CRATORY_ONLY], { divergent: 2 });
    await screen.findByText(/Floating Points/);
    fireEvent.click(screen.getByRole("checkbox", { name: /seleziona tutte/i }));
    fireEvent.click(screen.getByRole("button", { name: /ignora selezionate \(2\)/i }));
    await waitFor(() => expect(dismissAnalysis).toHaveBeenCalledWith([1, 2]));
  });
```

- [ ] **Step 2: Verifica che falliscano**

```bash
cd frontend && npx vitest run tests/analysis-page.test.tsx
```

Atteso: i 2 nuovi FAIL (bottone «Ignora» inesistente); gli altri PASS.

- [ ] **Step 3: Implementa**

`frontend/lib/api/analysis.ts`, in coda:

```ts
export async function dismissAnalysis(trackIds: number[]) {
  return apiPost<{ dismissed: number }>("/api/analysis/dismiss", { track_ids: trackIds });
}
```

`frontend/lib/i18n/it.ts`, sezione `analysis`, dopo `applyRow`:

```ts
    ignoreRow: "Ignora",
    ignoreSelected: (n: number) => `Ignora selezionate (${n})`,
    ignoredSummary: (n: number) => (n === 1 ? "1 divergenza ignorata" : `${n} divergenze ignorate`),
```

`frontend/lib/i18n/en.ts`, stessa posizione:

```ts
    ignoreRow: "Ignore",
    ignoreSelected: (n: number) => `Ignore selected (${n})`,
    ignoredSummary: (n: number) => (n === 1 ? "1 divergence ignored" : `${n} divergences ignored`),
```

`frontend/app/analysis/page.tsx`:

1. Import: aggiungi `dismissAnalysis` alla lista da `@/lib/api`.

2. Dopo `onApply` aggiungi:

```tsx
  // «Ignora» non sovrascrive nulla (il canonico resta): niente conferma.
  const onDismiss = async (ids: number[]) => {
    setBusy(true); setError(null);
    try {
      const r = await dismissAnalysis(ids);
      setNotice(t.analysis.ignoredSummary(r.dismissed));
      await reload();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };
```

3. Nella testata della card Divergenze, PRIMA del bottone «Applica selezionate»:

```tsx
                    <Button
                      size="sm" variant="outline"
                      disabled={busy || selected.size === 0}
                      onClick={() => onDismiss([...selected])}
                    >
                      {t.analysis.ignoreSelected(selected.size)}
                    </Button>
```

4. Nell'ultima cella di ogni riga, sostituisci il singolo bottone «Applica» con:

```tsx
                      <td className="px-4 py-2 text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            size="sm" variant="ghost"
                            disabled={busy}
                            onClick={() => onDismiss([r.track_id])}
                          >
                            {t.analysis.ignoreRow}
                          </Button>
                          <Button
                            size="sm" variant="ghost"
                            disabled={busy}
                            onClick={() => onApply({ track_ids: [r.track_id] })}
                          >
                            {t.analysis.applyRow}
                          </Button>
                        </div>
                      </td>
```

- [ ] **Step 4: Verifica che passino**

```bash
cd frontend && npx vitest run tests/analysis-page.test.tsx && npm run lint
```

Atteso: PASS tutti, lint pulito.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/analysis.ts frontend/app/analysis/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/analysis-page.test.tsx
git commit -m "feat(analysis): bottone Ignora per riga e per selezione"
```

---

### Task 4: Frontend — analisi al centro, Rekordbox ripiegato

**Files:**
- Modify: `frontend/app/analysis/page.tsx`
- Modify: `frontend/components/analysis/rekordbox-import-card.tsx`
- Modify: `frontend/lib/i18n/it.ts` + `en.ts`
- Test: `frontend/tests/analysis-page.test.tsx`

**Interfaces:**
- Consumes: nulla di nuovo dal backend.
- Produces: chiave i18n `rekordboxSummary`; rimozione chiavi `sourcesHeading`, `sourcesSubtitle`, `rekordboxHeading`, `rekordboxPrimaryTag` (verificare con grep che nessun altro file le usi prima di toglierle).

- [ ] **Step 1: Scrivi il test che fallisce**

In coda al `describe` di `frontend/tests/analysis-page.test.tsx`:

```tsx
  it("l'import Rekordbox è ripiegato: details chiuso di default", async () => {
    const { container } = mount([]);
    await screen.findByText(/nessuna divergenza/i);
    const details = container.querySelector("details");
    expect(details).toBeTruthy();
    expect(details!.open).toBe(false);
    // la card resta montata (import possibile una volta aperto il details)
    expect(screen.getByTestId("rekordbox-card")).toBeTruthy();
  });
```

- [ ] **Step 2: Verifica che fallisca**

```bash
cd frontend && npx vitest run tests/analysis-page.test.tsx
```

Atteso: FAIL (`details` è null: oggi la card Rekordbox è dentro la card Sorgenti).

- [ ] **Step 3: Implementa**

`frontend/lib/i18n/it.ts` — nella sezione `analysis`:
- elimina `sourcesHeading`, `sourcesSubtitle`, `rekordboxHeading`, `rekordboxPrimaryTag`;
- dopo `precedenceValue` aggiungi:

```ts
    rekordboxSummary: "Import Rekordbox — fonte primaria",
```

`frontend/lib/i18n/en.ts` — idem:

```ts
    rekordboxSummary: "Rekordbox import — primary source",
```

`frontend/components/analysis/rekordbox-import-card.tsx`:
- elimina il blocco `<div className="mb-2 flex items-center gap-2">…</div>` (h4 + Badge: il titolo ora lo dà il `<summary>` della pagina);
- togli `Badge` dall'import di `@/components/ui`;
- aggiorna il commento di testa: la card vive ripiegata in fondo alla pagina Analisi (uso raro), resta la sorgente primaria per autorità.

`frontend/app/analysis/page.tsx`:

1. Import: aggiungi `import { ChevronDown } from "lucide-react";`.

2. Sostituisci l'intera `<Card>` Sorgenti (da `<Card>` con `CardHeader title={t.analysis.sourcesHeading}` fino alla sua chiusura `</Card>`) con la sola card Analisi, che sale sopra le Divergenze:

```tsx
        {/* Analisi in-app: l'azione che si usa davvero, quindi in cima.
            Rekordbox resta la fonte primaria per autorità (precedenza), ma è
            un'operazione rara: vive ripiegata in fondo. */}
        <Card>
          <CardHeader title={t.analysis.analysisHeading} />
          <section className="px-5 py-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-72">
                <Field label={t.analysis.scopeLabel}>
                  <Select
                    className="h-9 w-full"
                    value={scope}
                    onChange={(e) => setScope(e.target.value as "missing" | "all")}
                  >
                    <option value="missing">{t.analysis.scopeMissing}</option>
                    <option value="all">{t.analysis.scopeAll}</option>
                  </Select>
                </Field>
              </div>
              <Button size="sm" onClick={onStart} disabled={busy}>
                {t.analysis.startButton}
              </Button>
            </div>
            {/* L'hint segue lo scope: le due voci non fanno la stessa cosa. */}
            <p className="mt-2 max-w-[68ch] text-xs text-muted">
              {scope === "missing" ? (
                <>
                  {t.analysis.scopeHintMissing(notReady)}
                  {missingHalf > 0 && t.analysis.scopeHintMissingHalf(missingHalf)}
                </>
              ) : (
                t.analysis.scopeHintAll(overview?.owned ?? 0)
              )}
            </p>
          </section>
        </Card>
```

(L'`analysisHeading` come `<h4>` e la striscia della precedenza spariscono con la vecchia card; `missingHalf` resta qui e cade nel Task 5.)

3. Dopo il blocco Divergenze (dopo la chiusura del ternario `rows.length === 0 ? … : <Card>…</Card>`), aggiungi in fondo al `<div className="space-y-5">`:

```tsx
        {/* Import Rekordbox: fonte primaria (precedenza), uso raro — ripiegato. */}
        <details className="group border border-border">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:text-fg [&::-webkit-details-marker]:hidden">
            <span>{t.analysis.rekordboxSummary}</span>
            <ChevronDown size={15} className="text-faint transition-transform duration-200 group-open:rotate-180" />
          </summary>
          <div className="border-t border-border">
            <p className="px-5 pt-3 text-[10px] uppercase tracking-wider text-muted">
              {t.analysis.precedenceLabel}{": "}
              <span className="font-semibold text-fg-strong">{t.analysis.precedenceValue}</span>
            </p>
            <RekordboxImportCard onImported={reload} />
          </div>
        </details>
```

4. Verifica con grep che le chiavi eliminate non abbiano altri usi:

```bash
cd frontend && grep -rn "sourcesHeading\|sourcesSubtitle\|rekordboxHeading\|rekordboxPrimaryTag" app components lib tests
```

Atteso: nessun risultato.

- [ ] **Step 4: Verifica che passino**

```bash
cd frontend && npx vitest run tests/analysis-page.test.tsx && npm run lint
```

Atteso: PASS tutti (compresi i test scope-hint: le chiavi hint non sono ancora cambiate), lint pulito.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/analysis/page.tsx frontend/components/analysis/rekordbox-import-card.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/analysis-page.test.tsx
git commit -m "feat(analysis): analisi al centro, import Rekordbox ripiegato"
```

---

### Task 5: Testi asciutti — via scopeHintMissingHalf, hint a una riga

**Files:**
- Modify: `frontend/lib/i18n/it.ts` + `en.ts`
- Modify: `frontend/app/analysis/page.tsx`
- Test: `frontend/tests/analysis-page.test.tsx`

**Interfaces:**
- Consumes: struttura pagina del Task 4.
- Produces: chiave `scopeHintMissingHalf` eliminata; testi accorciati (vedi sotto). Nessun altro file ne dipende.

- [ ] **Step 1: Adegua i test (prima dei testi: sono la spec del comportamento)**

In `frontend/tests/analysis-page.test.tsx`:

1. ELIMINA i due test `"tace sulle divergenze da scope=missing quando non possono nascere"` e `"avverte delle divergenze da scope=missing quando una traccia ha già l'altro campo"` (la distinzione sparisce con la chiave).

2. Il test `"la descrizione dell'analisi segue lo scope..."` NON va modificato: le sue due attese (`/analizza l'unica traccia senza BPM o tonalità/i` e `/rianalizza tutte le 412 tracce possedute/i`) restano vere anche coi testi nuovi — `scopeHintMissing` non cambia e il nuovo `scopeHintAll` contiene ancora «Rianalizza tutte le 412 tracce possedute». Verificare solo che resti verde allo Step 4.

- [ ] **Step 2: Verifica lo stato (i test eliminati non girano più)**

```bash
cd frontend && npx vitest run tests/analysis-page.test.tsx
```

Atteso: PASS (2 test in meno di prima).

- [ ] **Step 3: Asciuga i testi**

`frontend/lib/i18n/it.ts`, sezione `analysis` — sostituisci queste chiavi (e SOLO queste):

```ts
    ledeHint: "Pronta = BPM + tonalità presenti.",
    scopeHintAll: (n: number) =>
      `Rianalizza tutte le ${n} tracce possedute; le differenze finiscono in Divergenze.`,
    startedNote: "Analisi avviata: progresso nella barra in basso.",
    divergencesEmpty: "Nessuna divergenza.",
```

ed ELIMINA `scopeHintMissingHalf` (con i suoi commenti).

`frontend/lib/i18n/en.ts` — idem:

```ts
    ledeHint: "Ready = BPM + key present.",
    scopeHintAll: (n: number) =>
      `Re-analyzes all ${n} owned tracks; differences land under Divergences.`,
    startedNote: "Analysis started: progress in the bottom bar.",
    divergencesEmpty: "No divergences.",
```

`frontend/app/analysis/page.tsx`:

1. Elimina il calcolo `missingHalf` (blocco commento + `const missingHalf = ...`).
2. L'hint della card Analisi diventa:

```tsx
            <p className="mt-2 max-w-[68ch] text-xs text-muted">
              {scope === "missing"
                ? t.analysis.scopeHintMissing(notReady)
                : t.analysis.scopeHintAll(overview?.owned ?? 0)}
            </p>
```

- [ ] **Step 4: Verifica che passino**

```bash
cd frontend && npx vitest run && npm run lint
```

Atteso: PASS tutta la suite vitest (anche gli altri file di test), lint pulito. Se un altro test cercasse i vecchi testi, adeguarlo qui.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/analysis/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/analysis-page.test.tsx
git commit -m "refactor(analysis): testi asciutti, via scopeHintMissingHalf"
```

---

### Task 6: Verifica finale

**Files:** nessuno nuovo (solo esecuzione; eventuali fix minimi restano nei file dei task precedenti).

- [ ] **Step 1: Suite backend completa**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests
```

Atteso: PASS tutti (nessuna regressione fuori da analysis).

- [ ] **Step 2: Frontend completo**

```bash
cd frontend && npm run lint && npx vitest run && npm run build
```

Atteso: lint pulito, vitest PASS, build Turbopack ok (richiede `node_modules` reale nel worktree).

- [ ] **Step 3: Verifica migrazione su DB esistente (idempotenza ALTER ADD)**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -c "
from sqlalchemy import create_engine, text
import app.db as d
e = create_engine('sqlite:///:memory:')
d.ensure_schema(e); d.ensure_schema(e)  # due volte: deve essere no-op
cols = [r[1] for r in e.connect().execute(text('PRAGMA table_info(tracks)')).fetchall()]
assert 'analysis_dismissed_bpm' in cols and 'analysis_dismissed_camelot' in cols
print('OK colonne:', [c for c in cols if c.startswith('analysis_dismissed')])
"
```

Atteso: `OK colonne: ['analysis_dismissed_bpm', 'analysis_dismissed_camelot']`.

- [ ] **Step 4: Commit finale (solo se ci sono stati fix)**

```bash
git status --porcelain
```

Se pulito: fine. Altrimenti commit dei fix con messaggio `fix(analysis): <cosa>`.
