# Dashboard «La Cabina» + /statistics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard ridotta a frontespizio + pipeline + DJ ASCII animato con link a una nuova pagina `/statistics` che raccoglie tutti i grafici della libreria.

**Architecture:** L'animazione è divisa in core puro (`djFrame(tick): string[]`, deterministico e testato) e guscio React (`AsciiDj`, timer + reduced-motion). La pagina statistiche è una vista presentazionale testata (`StatisticsView`) sotto una route thin. La dashboard perde banco/colophon/polling (pulizia del Registro).

**Tech Stack:** Next.js 16 App Router, React, Tailwind coi token del sistema, vitest + @testing-library/react.

**Spec:** `docs/archive/superpowers/specs/2026-08-15-dashboard-cabina-statistiche-design.md`

## Global Constraints

Invariati dal piano del Registro: design system al massimo (monospace, monocromo + accento danger solo sui picchi EQ citando i DJ loader, filetti 1px, quadrato, `tnum`); entrambi i temi; hunk della sessione parallela intoccati (`git add` per path espliciti); i18n in entrambe le lingue; commit italiani senza Co-Authored-By; comandi da `frontend/`. **I test del DJ pinnano invarianti, non glifi**: il raffinamento estetico dell'arte non deve richiedere modifiche ai test.

---

### Task A: AsciiDj — core puro + guscio animato

**Files:**
- Create: `frontend/components/dashboard/ascii-dj.tsx`
- Test: `frontend/tests/ascii-dj.test.tsx`

**Interfaces:**
- Produces: `djFrame(tick: number): string[]` (esportata per i test); costanti `DJ_ROWS`, `DJ_COLS`, `DJ_AIR_ROWS`, `DJ_EQ_TOP_ROW`; componente `AsciiDj()` senza prop obbligatorie.

- [ ] **Step 1: test che fallisce** — invarianti del core:

```tsx
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AsciiDj, djFrame, DJ_ROWS, DJ_COLS, DJ_AIR_ROWS } from "@/components/dashboard/ascii-dj";

describe("djFrame (core puro)", () => {
  it("dimensioni fisse su molti tick: mai un salto di layout", () => {
    for (let t = 0; t < 200; t++) {
      const f = djFrame(t);
      expect(f.length).toBe(DJ_ROWS);
      for (const line of f) expect(line.length).toBe(DJ_COLS);
    }
  });

  it("è deterministica: stesso tick, stesso fotogramma", () => {
    expect(djFrame(42)).toEqual(djFrame(42));
  });

  it("i piatti girano: il fotogramma cambia da un tick al successivo", () => {
    expect(djFrame(0)).not.toEqual(djFrame(1));
  });

  it("il ciclo dei piatti è periodico (4 fasi)", () => {
    const deckRows = (t: number) => djFrame(t).slice(DJ_AIR_ROWS).join("\n");
    // Le sole righe console coincidono ogni 4 tick a parità di EQ? No: l'EQ è
    // pseudo-casuale. Si isola il marcatore del piatto sinistro via char noto.
    // Invariante robusto: su 8 tick consecutivi compaiono tutti e 4 i glifi.
    const glyphs = new Set<string>();
    for (let t = 0; t < 8; t++) {
      const m = deckRows(t).match(/\(\s*([|/\\-])\s*\)/);
      if (m) glyphs.add(m[1]);
    }
    expect(glyphs.size).toBe(4);
  });
});

describe("AsciiDj (guscio)", () => {
  afterEach(cleanup);
  it("renderizza il fotogramma in pre monospace, decorativo per gli screen reader", () => {
    const { container } = render(<AsciiDj />);
    const art = container.querySelector('[aria-hidden="true"]');
    expect(art).toBeTruthy();
    expect(art!.querySelectorAll("pre").length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: verifica FAIL** — `npx vitest run tests/ascii-dj.test.tsx` → modulo inesistente.
- [ ] **Step 3: implementazione** — core: LCG seedato dal tick (mai `Math.random`/`Date.now`), zone (aria con note che salgono, corpo con blink, console con piatti `| / - \` sfalsati, EQ 7 barre h∈0..2 su due righe, crossfader triangolare). Guscio: `useState(tick)` + `setInterval` 500ms con cleanup, `matchMedia("(prefers-reduced-motion: reduce)")` → statico a tick 0, tre blocchi `<pre>` per zona (aria `text-faint`, corpo `text-muted`, console `text-fg`) e picchi EQ (barre della riga alta) in `text-danger` via span per carattere.
- [ ] **Step 4: verifica PASS** e prova di discriminazione (rompere determinismo o dimensioni → il test cade).
- [ ] **Step 5: commit** — `feat(dashboard): AsciiDj, il DJ in ascii animato (core puro + guscio)`.

### Task B: StatisticsView + route /statistics

**Files:**
- Create: `frontend/components/statistics/statistics-view.tsx`, `frontend/app/statistics/page.tsx`
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts` (nuova sezione `stats`)
- Test: `frontend/tests/statistics-view.test.tsx`

**Interfaces:**
- Consumes: `LibraryStats`, `LabelStats`, `Histogram` (full), `MiniBars`, `EqMeter`.
- Produces: `StatisticsView({ stats, labels })`; route `/statistics` thin (fetch `/api/stats` + `getLabels`, `Loading`/`Alert`, poi la vista). i18n: `stats.title`, `stats.bpm`, `stats.keys`, `stats.genres`, `stats.labels`, `stats.energy`, `stats.sources`, `stats.coverage`, `stats.coverageBpm`, `stats.coverageKey`, `stats.coverageReady`, `dashboard.statsLink`.

- [ ] **Step 1: i18n** (it: "Statistiche", "Istogramma BPM", "Tonalità", "Generi", "Label", "Energia", "Fonti", "Copertura", "Con BPM", "Con tonalità", "Pronte per un set", statsLink "Statistiche"; en equivalenti).
- [ ] **Step 2: test che fallisce** — con stats piene: 7 sezioni presenti, link genere `/library?genre=…` e label `/labels/…`, copertura col valore `%` tabulare; con distribuzioni vuote: sezioni omesse (grammatica no-segnaposto); `energy_distribution` etichettata `from–to`.
- [ ] **Step 3: implementazione** — griglia `sm:grid-cols-2` con celle divise da filetti; ogni sezione `ColHead` locale (stesso stile 10px uppercase); copertura con `EqMeter calm value={pct}` + `%` in `tnum`.
- [ ] **Step 4: PASS** + route manuale nel browser.
- [ ] **Step 5: commit** — `feat(stats): pagina /statistics — il ritratto completo della libreria`.

### Task C: Dashboard finale + pulizia Registro

**Files:**
- Modify: `frontend/app/page.tsx` (griglie + DJ + link, via banco/colophon/polling), `frontend/lib/i18n/*.ts` (via `ow*`/`colophon*`), `frontend/components/dashboard/histogram.tsx` (via variante spark)
- Delete: `frontend/components/dashboard/open-work.tsx`, `colophon.tsx`, `frontend/tests/open-work.test.tsx`, `colophon.test.tsx`, `histogram-spark.test.tsx`
- Test: suite completa + lint + `tsc --noEmit`

- [ ] **Step 1:** page.tsx: fetch ridotti (stats, pipeline, labels→via, sets); link `STATISTICHE →` right-aligned sopra il frontespizio (`Link` uppercase 10px tracked); `<AsciiDj />` centrato sotto la pipeline (`mt-10 flex justify-center`), solo a libreria non vuota.
- [ ] **Step 2:** rimozioni file e chiavi; verificare con grep che spark/colophon/open-work non abbiano altri consumer.
- [ ] **Step 3:** `npx vitest run && npm run lint && npx tsc --noEmit` verdi.
- [ ] **Step 4: commit** — `feat(dashboard): «La Cabina» — griglie, DJ animato, link statistiche; via banco e colophon`.

### Task D: Verifica finale e raffinamento visivo del DJ

- [ ] **Step 1:** `npm run build` verde.
- [ ] **Step 2:** Browser: dashboard nei due temi + mobile; **iterazione estetica sull'arte del DJ** (proporzioni, glifi, ritmo dell'animazione, tonalità delle zone) fino a resa convincente — è il cuore della richiesta. I test non vincolano i glifi: si può iterare liberamente sull'arte dentro `djFrame`.
- [ ] **Step 3:** `/statistics` nei due temi.
- [ ] **Step 4:** screenshot per l'utente; commit di eventuali ritocchi.
