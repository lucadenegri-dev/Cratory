# EQ / Waveform loaders — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sostituire spinner e barre d'attesa dell'app con un linguaggio DJ: EQ a colonne (loader inline) e waveform stile rekordbox che avanza con la % reale (barre di progresso).

**Architecture:** Due nuovi componenti presentazionali in `components/ui.tsx` — `Equalizer` (loader inline, CSS-only) ed `EqMeter` (waveform determinata/indeterminata). `Spinner` diventa un alias di `Equalizer` (zero churn sui consumer). Le barre job e la generazione set passano a `EqMeter`; `Progress` resta solo per le barre-dati di copertura. Tutta l'animazione e' CSS in `globals.css`, theme-aware via variabili `--c-*`.

**Tech Stack:** Next 16, React 19, Tailwind CSS v4, CSS custom properties. Nessun audio, nessuna libreria nuova.

## Global Constraints

- **Estetica:** monospace, monocromo, squadrato (`--radius: 0px`). Un solo accento caldo: `--c-danger` (`#d8593f` dark / `#a83a22` paper). Niente palette RGB.
- **Colori solo via variabili `--c-*`** (mai hex hardcoded nei componenti) → adattamento automatico temi dark/paper.
- **Deterministico:** la pseudo-waveform di `EqMeter` e' un array calcolato a livello di modulo da sinusoidi — **vietato `Math.random`** (mismatch idratazione SSR Next).
- **`cn` si importa da `@/lib/cn`**; i componenti UI vivono in `frontend/components/ui.tsx` (file `"use client"`).
- **Next 16 ha breaking changes** (`frontend/AGENTS.md`): consultare `node_modules/next/dist/docs/` prima di toccare qualcosa di specifico Next. (Questi componenti sono React+CSS puri, nessuna API Next coinvolta.)
- **Commit:** messaggi in italiano, stile conventional, **mai** trailer `Co-Authored-By`.
- **Niente test unit frontend** nel progetto (script disponibili: `npm run lint`, `npm run build`). Gate per task: `npm run lint` + `npx tsc --noEmit`; verifica visiva + `npm run build` nel task finale.
- Tutti i comandi si lanciano da `frontend/`.

## File Structure

- `frontend/app/globals.css` — **modifica:** keyframes e classi per EQ (`.eq*`) e waveform (`.eqm*`), regole `prefers-reduced-motion`; in coda al piano rimuove `shimmer`.
- `frontend/components/ui.tsx` — **modifica:** aggiunge `Equalizer`, `EqMeter`, `WAVE`; `Spinner = Equalizer`; semplifica `Progress`.
- `frontend/components/jobs-provider.tsx` — **modifica:** `GlobalProgress` usa `EqMeter`.
- `frontend/app/set-builder/page.tsx` — **modifica:** generazione indeterminata usa `EqMeter`.
- `frontend/app/{settings,labels}/page.tsx`, `frontend/app/{playlists/[id],tracks/[id],shazam/[id],sets/[id]}/page.tsx` — **modifica:** un `Equalizer` accanto ai placeholder "Caricamento…".

---

## Task 1: CSS foundation — keyframes e classi EQ/waveform

**Files:**
- Modify: `frontend/app/globals.css` (append in coda, dopo la riga 84)

**Interfaces:**
- Consumes: variabili `--c-fg`, `--c-fg-strong`, `--c-border`, `--c-danger` (gia' definite in `:root` e `html[data-theme="paper"]`).
- Produces: classi CSS `.eq`, `.eq-bar`, `.eq-track`, `.eq-fill`, `.eq-l1/2/3/5`; `.eqm`, `.eqm-wave`, `.eqm-bar`, `.eqm-on`, `.eqm-off`, `.eqm-ph`, `.eqm-scan`; keyframes `eqA/eqB/eqC/eqK/eqmScan`. Consumate da Task 2/3.

- [ ] **Step 1: Aggiungi il blocco CSS in coda a `globals.css`**

Append (NON rimuovere ancora lo `shimmer`, serve finche' `Progress` lo usa):

```css

/* ---- DJ loaders: EQ inline (.eq*) + waveform (.eqm*) ---------------------- */

/* EQ inline: 4 colonne segmentate con tacca di picco calda */
.eq { display: inline-flex; align-items: flex-end; gap: 2px; }
.eq-bar { position: relative; flex: 1; height: 100%; min-width: 2px; }
.eq-track { position: absolute; inset: 0; background: repeating-linear-gradient(to top, var(--c-border) 0 3px, transparent 3px 5px); }
.eq-fill { position: absolute; left: 0; right: 0; bottom: 0; height: 40%; background: repeating-linear-gradient(to top, var(--c-fg) 0 3px, transparent 3px 5px); }
.eq-fill::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 2px; background: var(--c-danger); }
.eq-l1 { animation: eqA 0.90s ease-in-out infinite -0.20s; }
.eq-l2 { animation: eqB 0.75s ease-in-out infinite -0.45s; }
.eq-l3 { animation: eqC 1.05s ease-in-out infinite -0.10s; }
.eq-l5 { animation: eqK 0.60s ease-in-out infinite -0.05s; }

@keyframes eqA { 0%,100% { height: 35%; } 25% { height: 95%; } 50% { height: 55%; } 75% { height: 80%; } }
@keyframes eqB { 0%,100% { height: 70%; } 25% { height: 30%; } 50% { height: 92%; } 75% { height: 45%; } }
@keyframes eqC { 0%,100% { height: 50%; } 30% { height: 85%; } 60% { height: 25%; } 85% { height: 78%; } }
@keyframes eqK { 0%,100% { height: 22%; } 12% { height: 100%; } 30% { height: 38%; } 55% { height: 28%; } }

/* Waveform rekordbox: lo spettro si riempie sx->dx con la % reale */
.eqm { position: relative; overflow: hidden; }
.eqm-wave { position: absolute; inset: 0; display: flex; align-items: center; gap: 1px; }
.eqm-bar { flex: 1; }
.eqm-off { background: var(--c-border); }
.eqm-on { background: linear-gradient(to top, var(--c-fg), color-mix(in oklab, var(--c-danger) 60%, var(--c-fg)) 50%, var(--c-fg-strong)); }
.eqm-ph { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--c-danger); }
.eqm-scan { position: absolute; top: 0; bottom: 0; left: -14%; width: 64px; background: linear-gradient(to right, transparent, color-mix(in srgb, var(--c-fg) 42%, transparent)); border-right: 2px solid var(--c-danger); animation: eqmScan 1.5s linear infinite; }
@keyframes eqmScan { from { left: -14%; } to { left: 100%; } }

@media (prefers-reduced-motion: reduce) {
  .eq-l1, .eq-l2, .eq-l3, .eq-l5 { animation: none !important; }
  .eq-fill { height: 62% !important; }
  .eqm-scan { animation: none; left: 38%; }
}
```

- [ ] **Step 2: Lint + typecheck**

Run (da `frontend/`): `npm run lint && npx tsc --noEmit`
Expected: nessun errore (il CSS non e' typecheckato; il comando deve restare verde).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/globals.css
git commit -m "feat(ui): keyframes EQ e waveform in globals.css"
```

---

## Task 2: `Equalizer` + `EqMeter`, `Spinner` come alias

**Files:**
- Modify: `frontend/components/ui.tsx` (sostituisce la funzione `Spinner`, righe 137-141; aggiunge `WAVE` e `EqMeter`)

**Interfaces:**
- Consumes: `cn` da `@/lib/cn` (gia' importato a riga 4); classi CSS di Task 1.
- Produces:
  - `Equalizer({ className?: string }): JSX.Element`
  - `Spinner` = alias di `Equalizer` (stessa firma `{ className?: string }`)
  - `EqMeter({ value: number | null; className?: string }): JSX.Element`

- [ ] **Step 1: Sostituisci la funzione `Spinner`**

Trova (righe 137-141):

```tsx
export function Spinner({ className }: { className?: string }) {
  return (
    <span className={cn("inline-block animate-spin rounded-full border-2 border-border-strong border-t-fg", className ?? "h-4 w-4")} />
  );
}
```

Sostituisci con:

```tsx
/* Loader inline: equalizzatore a colonne con tacca di picco calda. */
export function Equalizer({ className }: { className?: string }) {
  return (
    <span role="status" aria-label="Caricamento" className={cn("eq", className ?? "h-4 w-4")}>
      <span className="eq-bar"><span className="eq-track" /><span className="eq-fill eq-l1" /></span>
      <span className="eq-bar"><span className="eq-track" /><span className="eq-fill eq-l2" /></span>
      <span className="eq-bar"><span className="eq-track" /><span className="eq-fill eq-l3" /></span>
      <span className="eq-bar"><span className="eq-track" /><span className="eq-fill eq-l5" /></span>
    </span>
  );
}

/* Alias di compatibilita': i consumer che importano Spinner restano invariati. */
export const Spinner = Equalizer;

/* Pseudo-waveform deterministica (no Math.random: stessa forma su server e client). */
const WAVE: number[] = Array.from({ length: 56 }, (_, i) => {
  const x = i / 56;
  const a =
    0.30 +
    0.32 * Math.abs(Math.sin(x * Math.PI * 7)) +
    0.22 * Math.abs(Math.sin(x * Math.PI * 23 + 1)) +
    0.16 * Math.abs(Math.sin(x * Math.PI * 3 + 0.5));
  return Math.max(0.16, Math.min(1, a));
});

/* Meter a waveform "rekordbox": value numerico -> riempimento sx->dx con testina;
   value null -> indeterminato con scan che spazza. */
export function EqMeter({ value, className }: { value: number | null; className?: string }) {
  const indeterminate = value == null;
  const v = indeterminate ? 0 : Math.min(100, Math.max(0, value));
  const lit = indeterminate ? 0 : Math.round((WAVE.length * v) / 100);
  return (
    <div
      className={cn("eqm", className ?? "h-6 w-full")}
      role={indeterminate ? "status" : "progressbar"}
      aria-label={indeterminate ? "In corso" : undefined}
      aria-valuenow={indeterminate ? undefined : Math.round(v)}
      aria-valuemin={indeterminate ? undefined : 0}
      aria-valuemax={indeterminate ? undefined : 100}
    >
      <div className="eqm-wave">
        {WAVE.map((a, i) => (
          <span
            key={i}
            className={cn("eqm-bar", !indeterminate && i < lit ? "eqm-on" : "eqm-off")}
            style={{ height: `${(a * 100).toFixed(1)}%` }}
          />
        ))}
      </div>
      {indeterminate ? (
        <span className="eqm-scan" />
      ) : (
        <span className="eqm-ph" style={{ left: `${v}%` }} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Lint + typecheck**

Run: `npm run lint && npx tsc --noEmit`
Expected: verde. Nota: `Progress` usa ancora `animate-shimmer` (ok, lo rimuoviamo in Task 4); tutti i `<Spinner/>` ora rendono l'EQ.

- [ ] **Step 3: Verifica visiva rapida (opzionale ma consigliata)**

Avvia il dev server e apri una pagina con un bottone async (es. `/discovery`): premendo "DIG" il bottone deve mostrare l'EQ a colonne al posto del cerchietto. (Verifica completa nel Task 6.)

- [ ] **Step 4: Commit**

```bash
git add frontend/components/ui.tsx
git commit -m "feat(ui): Equalizer + EqMeter, Spinner come alias EQ"
```

---

## Task 3: Barra job e generazione set usano `EqMeter`

**Files:**
- Modify: `frontend/components/jobs-provider.tsx` (import riga 5; `GlobalProgress` righe 86-102)
- Modify: `frontend/app/set-builder/page.tsx` (riga ~330; e l'import da `@/components/ui`)

**Interfaces:**
- Consumes: `EqMeter({ value: number | null })` da Task 2.
- Produces: nessuna nuova interfaccia.

- [ ] **Step 1: `jobs-provider.tsx` — aggiorna l'import (riga 5)**

Trova:

```tsx
import { Progress, Spinner } from "./ui";
```

Sostituisci con:

```tsx
import { EqMeter } from "./ui";
```

- [ ] **Step 2: `jobs-provider.tsx` — riscrivi `GlobalProgress` (righe 86-102)**

Trova:

```tsx
function GlobalProgress({ jobs }: { jobs: Job[] }) {
  const j = jobs[0];
  const pct = j.indeterminate ? null : (j.total > 0 ? Math.round((j.processed / j.total) * 100) : null);
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface px-4 py-2.5">
      <div className="mx-auto flex max-w-5xl items-center gap-4">
        <span className="flex items-center gap-2 whitespace-nowrap text-[10px] font-medium uppercase tracking-wider text-muted">
          <Spinner className="h-3 w-3" /> {j.label}{jobs.length > 1 ? ` · +${jobs.length - 1}` : ""}
        </span>
        <div className="flex-1"><Progress value={pct} /></div>
        {!j.indeterminate && (
          <span className="tnum whitespace-nowrap text-[10px] text-muted">{j.processed}/{j.total || "?"}{pct != null ? ` · ${pct}%` : ""}</span>
        )}
      </div>
    </div>
  );
}
```

Sostituisci con (la waveform e' ora l'indicatore vivo, lo Spinner inline non serve piu'):

```tsx
function GlobalProgress({ jobs }: { jobs: Job[] }) {
  const j = jobs[0];
  const pct = j.indeterminate ? null : (j.total > 0 ? Math.round((j.processed / j.total) * 100) : null);
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface px-4 py-2.5">
      <div className="mx-auto flex max-w-5xl items-center gap-4">
        <span className="whitespace-nowrap text-[10px] font-medium uppercase tracking-wider text-muted">
          {j.label}{jobs.length > 1 ? ` · +${jobs.length - 1}` : ""}
        </span>
        <div className="flex-1"><EqMeter value={pct} className="h-6 w-full" /></div>
        {!j.indeterminate && (
          <span className="tnum whitespace-nowrap text-[10px] text-muted">{j.processed}/{j.total || "?"}{pct != null ? ` · ${pct}%` : ""}</span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: `set-builder/page.tsx` — `Progress` indeterminata -> `EqMeter`**

Trova (riga ~330):

```tsx
            <Progress value={null} />
```

Sostituisci con:

```tsx
            <EqMeter value={null} className="h-6 w-full" />
```

- [ ] **Step 4: `set-builder/page.tsx` — aggiorna l'import**

Nel file, l'import da `@/components/ui` include `Progress`. Sostituisci `Progress` con `EqMeter` in quell'import (es. `import { ..., Progress, ... } from "@/components/ui";` diventa `import { ..., EqMeter, ... } from "@/components/ui";`). Se `Progress` non e' usato altrove nel file, rimuovilo del tutto dall'import.

Verifica con: `grep -n "Progress\|EqMeter" app/set-builder/page.tsx` — non deve restare alcun uso di `Progress`.

- [ ] **Step 5: Lint + typecheck**

Run: `npm run lint && npx tsc --noEmit`
Expected: verde. Dopo questo task, **nessun** chiamante passa piu' `null` a `Progress`.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/jobs-provider.tsx frontend/app/set-builder/page.tsx
git commit -m "feat(jobs,set-builder): barra job e generazione usano EqMeter"
```

---

## Task 4: `Progress` solo determinata, rimuovi `shimmer`

**Files:**
- Modify: `frontend/components/ui.tsx` (`Progress`, righe 125-135)
- Modify: `frontend/app/globals.css` (rimuove `@keyframes shimmer` righe 79-84)

**Interfaces:**
- Consumes: nessuna.
- Produces: `Progress({ value: number }): JSX.Element` (firma ristretta: non accetta piu' `null`).

- [ ] **Step 1: Pre-check — nessun chiamante passa `null`**

Run: `grep -rn "Progress value={null}\|<Progress" app components | grep -v node_modules`
Expected: solo `app/page.tsx` con `value={pct}` (numerico). Se compare un altro `value={null}`, **fermati** e mantieni la firma `number | null` rimuovendo solo lo `shimmer`.

- [ ] **Step 2: Semplifica `Progress` (righe 125-135 di `ui.tsx`)**

Trova:

```tsx
export function Progress({ value }: { value: number | null }) {
  const indeterminate = value == null;
  return (
    <div className="h-2 w-full overflow-hidden bg-elevated">
      <div
        className={cn("h-full bg-fg transition-all", indeterminate && "w-1/3 animate-shimmer")}
        style={indeterminate ? undefined : { width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}
```

Sostituisci con:

```tsx
export function Progress({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden bg-elevated">
      <div className="h-full bg-fg transition-all" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}
```

- [ ] **Step 3: Rimuovi `shimmer` da `globals.css` (righe 79-84)**

Trova ed elimina:

```css
@keyframes shimmer {
  0% { opacity: 0.55; }
  50% { opacity: 1; }
  100% { opacity: 0.55; }
}
.animate-shimmer { animation: shimmer 1.6s ease-in-out infinite; }
```

- [ ] **Step 4: Verifica nessun riferimento orfano a shimmer**

Run: `grep -rn "shimmer" app components | grep -v node_modules`
Expected: nessun risultato.

- [ ] **Step 5: Lint + typecheck**

Run: `npm run lint && npx tsc --noEmit`
Expected: verde.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/ui.tsx frontend/app/globals.css
git commit -m "refactor(ui): Progress solo determinato, rimuovi shimmer"
```

---

## Task 5: EQ accanto ai placeholder "Caricamento…"

**Files:**
- Modify: `frontend/app/settings/page.tsx:100`
- Modify: `frontend/app/playlists/[id]/page.tsx:205`
- Modify: `frontend/app/labels/page.tsx:76`
- Modify: `frontend/app/tracks/[id]/page.tsx:58`
- Modify: `frontend/app/shazam/[id]/page.tsx:25`
- Modify: `frontend/app/sets/[id]/page.tsx:117`

**Interfaces:**
- Consumes: `Equalizer` da Task 2.
- Produces: nessuna.

Per **ogni** file: assicurati che `Equalizer` sia importato da `@/components/ui` (aggiungilo all'import esistente; se il file non importa da `@/components/ui`, aggiungi `import { Equalizer } from "@/components/ui";`). Poi anteponi l'EQ al testo "Caricamento…" rendendo il contenitore un flex allineato.

- [ ] **Step 1: `settings/page.tsx:100`**

Trova:

```tsx
        {!services && !error && <div className="p-5 text-sm text-muted">Caricamento…</div>}
```

Sostituisci con:

```tsx
        {!services && !error && <div className="flex items-center gap-2 p-5 text-sm text-muted"><Equalizer className="h-3.5 w-3.5" /> Caricamento…</div>}
```

- [ ] **Step 2: `playlists/[id]/page.tsx:205`**

Trova:

```tsx
  if (!playlist) return <PageLayout title="Playlist"><p className="text-muted">Caricamento…</p></PageLayout>;
```

Sostituisci con:

```tsx
  if (!playlist) return <PageLayout title="Playlist"><p className="flex items-center gap-2 text-muted"><Equalizer className="h-3.5 w-3.5" /> Caricamento…</p></PageLayout>;
```

- [ ] **Step 3: `labels/page.tsx:76`**

Trova:

```tsx
      {labels === null && !error && <p className="text-muted">Caricamento…</p>}
```

Sostituisci con:

```tsx
      {labels === null && !error && <p className="flex items-center gap-2 text-muted"><Equalizer className="h-3.5 w-3.5" /> Caricamento…</p>}
```

- [ ] **Step 4: `tracks/[id]/page.tsx:58`**

Trova:

```tsx
  if (!track) return <PageLayout title="Traccia"><p className="text-muted">Caricamento…</p></PageLayout>;
```

Sostituisci con:

```tsx
  if (!track) return <PageLayout title="Traccia"><p className="flex items-center gap-2 text-muted"><Equalizer className="h-3.5 w-3.5" /> Caricamento…</p></PageLayout>;
```

(`tracks/[id]/page.tsx` importa gia' `Spinner` da `@/components/ui`: aggiungi `Equalizer` allo stesso import.)

- [ ] **Step 5: `shazam/[id]/page.tsx:25`**

Trova:

```tsx
  if (!set) return <PageLayout title="Identificazione"><p className="text-muted">Caricamento…</p></PageLayout>;
```

Sostituisci con:

```tsx
  if (!set) return <PageLayout title="Identificazione"><p className="flex items-center gap-2 text-muted"><Equalizer className="h-3.5 w-3.5" /> Caricamento…</p></PageLayout>;
```

- [ ] **Step 6: `sets/[id]/page.tsx:117`**

Trova:

```tsx
  if (!setlist) return <PageLayout title="Set"><p className="text-muted">Caricamento…</p></PageLayout>;
```

Sostituisci con:

```tsx
  if (!setlist) return <PageLayout title="Set"><p className="flex items-center gap-2 text-muted"><Equalizer className="h-3.5 w-3.5" /> Caricamento…</p></PageLayout>;
```

(`sets/[id]/page.tsx` importa gia' `Spinner`: aggiungi `Equalizer` allo stesso import.)

- [ ] **Step 7: Lint + typecheck**

Run: `npm run lint && npx tsc --noEmit`
Expected: verde. Controlla che ogni file modificato importi `Equalizer`:
`grep -rln "Equalizer" app/settings/page.tsx app/labels/page.tsx "app/playlists/[id]/page.tsx" "app/tracks/[id]/page.tsx" "app/shazam/[id]/page.tsx" "app/sets/[id]/page.tsx"`

- [ ] **Step 8: Commit**

```bash
git add "frontend/app/settings/page.tsx" "frontend/app/labels/page.tsx" "frontend/app/playlists/[id]/page.tsx" "frontend/app/tracks/[id]/page.tsx" "frontend/app/shazam/[id]/page.tsx" "frontend/app/sets/[id]/page.tsx"
git commit -m "feat(ui): EQ accanto ai placeholder Caricamento"
```

---

## Task 6: Verifica integrata (build + visiva)

**Files:** nessuna modifica (solo verifica; eventuali fix tornano al task pertinente).

- [ ] **Step 1: Build di produzione**

Run: `npm run build`
Expected: build completata senza errori di type o lint.

- [ ] **Step 2: Verifica visiva (dev server + preview tools)**

Avvia il dev server e controlla, catturando screenshot:
1. **EQ inline in un bottone** — `/discovery`, premi "DIG": colonne EQ animate con tacca di picco al posto del cerchietto.
2. **Waveform determinata** — avvia un arricchimento feature (da `/settings` o `/playlists/[id]`): la barra in basso mostra la waveform che si riempie sx->dx con testina arancio e conteggio `processed/total`.
3. **Waveform indeterminata** — `/set-builder`, genera un set: card con waveform + scan che spazza.
4. **Placeholder** — apri una pagina di dettaglio a freddo (es. `/tracks/<id>`): "Caricamento…" con EQ accanto.

- [ ] **Step 3: Reduced motion**

Con `prefers-reduced-motion: reduce` attivo (emulazione DevTools): le colonne EQ si congelano (≈62%), lo scan della waveform e' fermo, le barre determinate restano riempite alla %.

- [ ] **Step 4: Tema paper**

Attiva il tema "paper" (toggle in alto): EQ e waveform restano leggibili, l'accento caldo diventa `#a83a22`. Nessun colore hardcoded "scappato".

- [ ] **Step 5: Commit finale (se ci sono stati micro-fix)**

```bash
git add -A
git commit -m "fix(ui): rifiniture visive loader EQ/waveform"
```

---

## Self-Review (eseguita in fase di scrittura)

- **Copertura spec:** §3.1 Equalizer → Task 2. §3.2 Spinner alias → Task 2. §3.3 EqMeter → Task 2 (+ consumo Task 3). §3.4 Progress semplificata → Task 4. §4 mappa file → Task 2-5. §5 colori/temi → Task 1 (variabili) + verifica Task 6.4. §6 animazioni → Task 1. §7 reduced-motion/aria → Task 1 (CSS) + Task 2 (ruoli aria) + verifica Task 6.3. §8 vincoli Next → Global Constraints. §9 non-obiettivi (dashboard `Progress`, no audio, no rekordbox) → rispettati (Task 4 lascia `Progress` per i dati). §10 verifica → Task 6.
- **Placeholder:** nessun "TBD/TODO"; ogni step ha codice reale.
- **Type consistency:** `Equalizer({className})`, `Spinner = Equalizer`, `EqMeter({value:number|null, className})`, `Progress({value:number})` coerenti tra Task 2/3/4 e i punti d'uso.
