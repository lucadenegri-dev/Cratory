# Guida visibile nel Set Builder + "Sorprendimi" nel dig — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendere scopribile la guida del Set Builder (link testuale + richiamo inline) e aggiungere un bottone "Sorprendimi" al dig di Discovery che pesca un seme casuale dalla libreria dell'utente.

**Architecture:** Tutto frontend. La guida è markup statico. "Sorprendimi" è una *roulette dei parametri*: una funzione pura sceglie seme+profondità e la pagina naviga aggiornando la query string; il dig parte dall'effetto esistente che reagisce all'URL. Il motore backend resta intatto e deterministico.

**Tech Stack:** Next.js 16 (App Router, `"use client"`), React 19, TypeScript, Tailwind, Vitest + Testing Library, i18n custom (`frontend/lib/i18n`), icone `lucide-react`.

## Global Constraints

- **Next 16 non è il Next noto:** leggi `frontend/CLAUDE.md` prima di toccare pagine/routing; consulta `node_modules/next/dist/docs/` per API dubbie.
- **Gotcha spazi JSX (Next 16):** uno spazio dopo un elemento inline sparisce se il testo va a capo nel sorgente → usa `{" "}` esplicito tra testo e `<Link>`.
- **Determinismo del motore:** nessuna modifica a `backend/app/services/discovery_dig.py` né al ranking. Il random vive solo nella scelta dei parametri lato client.
- **i18n bilingue obbligatorio:** ogni nuova stringa va aggiunta sia in `frontend/lib/i18n/it.ts` sia in `frontend/lib/i18n/en.ts`, con la stessa chiave.
- **Commit frequenti**, un commit per task. Stile commit: **niente** `Co-Authored-By`.
- **Verifica pre-commit:** `npm run lint` e `npm run test:unit` devono passare; per i task UI verifica anche `npm run build`.
- Comandi eseguiti da `frontend/`.

---

## File Structure

- `frontend/lib/discovery-surprise.ts` — **NEW.** Funzione pura `pickSurprise` (roulette del seme). Nessuna dipendenza da React o componenti a runtime.
- `frontend/tests/discovery-surprise.test.ts` — **NEW.** Unit test della funzione pura.
- `frontend/components/discovery-dig-bar.tsx` — **MODIFY.** Bottone "Sorprendimi" + due nuove prop.
- `frontend/tests/discovery-dig-bar.test.tsx` — **MODIFY.** Prop di default nel setup + nuovi test del bottone.
- `frontend/app/discovery/page.tsx` — **MODIFY.** Handler `runSurprise`, reroll-on-empty, prop passate alla barra.
- `frontend/app/set-builder/page.tsx` — **MODIFY.** Link guida testuale nell'header + richiamo inline nell'intro.
- `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts` — **MODIFY.** Nuove stringhe (guida + Sorprendimi).

---

## Task A: Guida visibile nel Set Builder

Markup statico: link header con testo + richiamo inline nell'intro. Nessun test unitario (è solo markup), verifica con lint/build/browser.

**Files:**
- Modify: `frontend/app/set-builder/page.tsx:199-205`
- Modify: `frontend/lib/i18n/it.ts` (blocco `setBuilder`, dopo la riga `guideLinkTitle`, ~riga 744)
- Modify: `frontend/lib/i18n/en.ts` (blocco `setBuilder`, dopo la riga `guideLinkTitle`, ~riga 741)

**Interfaces:**
- Consumes: componente `PageLayout` (prop `action`), `Link` da `next/link` (già importato in `page.tsx:5` — verifica), icona `HelpCircle` da `lucide-react` (già importata `page.tsx:7`).
- Produces: nuove chiavi i18n `t.setBuilder.guideLinkLabel`, `t.setBuilder.guidePrompt`, `t.setBuilder.guideLinkText`.

- [ ] **Step 1: Aggiungi le stringhe i18n italiane**

In `frontend/lib/i18n/it.ts`, nel blocco `setBuilder`, subito dopo la riga `guideLinkTitle: "Guida del Set Builder",` aggiungi:

```ts
    guideLinkLabel: "Guida",
    guidePrompt: "Per capire come ragiona il motore,",
    guideLinkText: "leggi la guida",
```

- [ ] **Step 2: Aggiungi le stringhe i18n inglesi**

In `frontend/lib/i18n/en.ts`, nel blocco `setBuilder`, subito dopo la riga `guideLinkTitle: "Set Builder guide",` aggiungi:

```ts
    guideLinkLabel: "Guide",
    guidePrompt: "To see how the engine reasons,",
    guideLinkText: "read the guide",
```

- [ ] **Step 3: Header — link con testo e contrasto pieno**

In `frontend/app/set-builder/page.tsx`, sostituisci il blocco `action={...}` (righe ~198-203):

```tsx
      action={
        <Link href="/set-builder/guida" title={t.setBuilder.guideLinkTitle} aria-label={t.setBuilder.guideLinkTitle}
          className="text-faint transition-colors hover:text-fg">
          <HelpCircle size={17} />
        </Link>
      }
```

con:

```tsx
      action={
        <Link href="/set-builder/guida" title={t.setBuilder.guideLinkTitle}
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted transition-colors hover:text-fg">
          <HelpCircle size={15} />
          {t.setBuilder.guideLinkLabel}
        </Link>
      }
```

- [ ] **Step 4: Intro — richiamo inline alla guida**

In `frontend/app/set-builder/page.tsx`, sostituisci la riga dell'intro (~riga 205):

```tsx
      <p className="mb-6 text-sm text-muted">{t.setBuilder.intro}</p>
```

con (nota `{" "}` espliciti per il gotcha spazi JSX di Next 16):

```tsx
      <p className="mb-6 text-sm text-muted">
        {t.setBuilder.intro}{" "}
        {t.setBuilder.guidePrompt}{" "}
        <Link href="/set-builder/guida" className="text-fg underline underline-offset-2 transition-colors hover:text-faint">
          {t.setBuilder.guideLinkText}
        </Link>
        .
      </p>
```

- [ ] **Step 5: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: PASS, nessun errore TypeScript/ESLint.

- [ ] **Step 6: Verifica visiva nel browser**

Avvia il dev server (via preview_start, config `.claude/launch.json`; NON `npm run dev` in Bash), apri `/set-builder`, conferma con read_page/screenshot che: (a) nell'header compare "? Guida" leggibile, (b) l'intro finisce con "…leggi la guida" cliccabile, (c) il click porta a `/set-builder/guida`. Se la CSS sembra stantia dopo modifiche a stili, `rm -rf frontend/.next` (gotcha cache dev noto).

- [ ] **Step 7: Commit**

```bash
cd frontend && git add app/set-builder/page.tsx lib/i18n/it.ts lib/i18n/en.ts
git commit -m "feat(set-builder): guida visibile — link testuale nell'header + richiamo inline"
```

---

## Task B1: Funzione pura `pickSurprise`

La roulette del seme, testabile in isolamento con RNG iniettabile. TDD.

**Files:**
- Create: `frontend/lib/discovery-surprise.ts`
- Test: `frontend/tests/discovery-surprise.test.ts`

**Interfaces:**
- Consumes: `type SeedType = "genre" | "label"` da `@/components/discovery-dig-bar` (import type-only, erased a build-time — nessun accoppiamento runtime lib→componente).
- Produces:
  - `type SurprisePick = { seedType: SeedType; value: string; depth: number }`
  - `function pickSurprise(pool: { genres: string[]; labels: string[] }, current: string | null, rng?: () => number): SurprisePick | null`
  - Semantica: pool = genres+labels uniti, pick uniforme; esclude `current` (case-insensitive, trim); se l'esclusione svuota il pool ma il pool grezzo no (unico seme = current), ripesca `current`; depth uniforme tra `0.0 | 0.5 | 1.0`; pool grezzo vuoto → `null`. `rng` default `Math.random`, chiamata due volte (prima per il seme, poi per la depth).

- [ ] **Step 1: Scrivi i test (falliranno)**

Crea `frontend/tests/discovery-surprise.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { pickSurprise } from "@/lib/discovery-surprise";

// RNG deterministico: restituisce in sequenza i valori dati, poi 0.
function seqRng(values: number[]): () => number {
  let i = 0;
  return () => (i < values.length ? values[i++] : 0);
}

describe("pickSurprise", () => {
  const POOL = { genres: ["Acid House", "Techno"], labels: ["Trax Records"] };

  it("pool vuoto -> null", () => {
    expect(pickSurprise({ genres: [], labels: [] }, null)).toBeNull();
  });

  it("pick uniforme deterministico con RNG fisso: primo elemento + prima depth", () => {
    // rng[0]=0 -> indice 0 del pool unito (generi prima): "Acid House".
    // rng[1]=0 -> prima depth: 0.0.
    const pick = pickSurprise(POOL, null, seqRng([0, 0]));
    expect(pick).toEqual({ seedType: "genre", value: "Acid House", depth: 0.0 });
  });

  it("il seedType segue il gruppo di provenienza (label)", () => {
    // 3 elementi uniti: [Acid House(genre), Techno(genre), Trax Records(label)].
    // rng appena sotto 1 -> ultimo indice -> la label.
    const pick = pickSurprise(POOL, null, seqRng([0.99, 0.5]));
    expect(pick).toEqual({ seedType: "label", value: "Trax Records", depth: 0.5 });
  });

  it("depth uniforme sui tre valori", () => {
    expect(pickSurprise(POOL, null, seqRng([0, 0.99]))?.depth).toBe(1.0);
    expect(pickSurprise(POOL, null, seqRng([0, 0.5]))?.depth).toBe(0.5);
  });

  it("anti-ripetizione: esclude il seme corrente (case-insensitive)", () => {
    // current = "acid house": resta [Techno, Trax Records]. rng=0 -> Techno.
    const pick = pickSurprise(POOL, "acid house", seqRng([0, 0]));
    expect(pick?.value).toBe("Techno");
  });

  it("unico seme uguale a current: ripesca quello invece di null", () => {
    const pick = pickSurprise({ genres: ["Techno"], labels: [] }, "Techno", seqRng([0, 0]));
    expect(pick).toEqual({ seedType: "genre", value: "Techno", depth: 0.0 });
  });
});
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd frontend && npx vitest run tests/discovery-surprise.test.ts`
Expected: FAIL — `Failed to resolve import "@/lib/discovery-surprise"` (modulo inesistente).

- [ ] **Step 3: Implementa la funzione**

Crea `frontend/lib/discovery-surprise.ts`:

```ts
import type { SeedType } from "@/components/discovery-dig-bar";

export type SurprisePick = { seedType: SeedType; value: string; depth: number };

// Gli stessi tre valori di DEPTHS in discovery-dig-bar (surface/mid/deep).
const DEPTH_VALUES = [0.0, 0.5, 1.0];

/**
 * Pesca un seme casuale dal gusto (libreria): generi di libreria + etichette,
 * pick uniforme, esclusi gli style curati. `current` (il seme in barra) viene
 * escluso per non ripetere il colpo appena fatto; se resta l'unico seme, lo
 * ripesca comunque. `rng` iniettabile per i test.
 */
export function pickSurprise(
  pool: { genres: string[]; labels: string[] },
  current: string | null,
  rng: () => number = Math.random,
): SurprisePick | null {
  const entries: { seedType: SeedType; value: string }[] = [
    ...pool.genres.map((value) => ({ seedType: "genre" as const, value })),
    ...pool.labels.map((value) => ({ seedType: "label" as const, value })),
  ];
  if (entries.length === 0) return null;

  const cur = current?.trim().toLowerCase() ?? null;
  const filtered = cur ? entries.filter((e) => e.value.trim().toLowerCase() !== cur) : entries;
  const chooseFrom = filtered.length > 0 ? filtered : entries;

  const idx = Math.min(Math.floor(rng() * chooseFrom.length), chooseFrom.length - 1);
  const entry = chooseFrom[idx];
  const depth = DEPTH_VALUES[Math.min(Math.floor(rng() * DEPTH_VALUES.length), DEPTH_VALUES.length - 1)];
  return { seedType: entry.seedType, value: entry.value, depth };
}
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd frontend && npx vitest run tests/discovery-surprise.test.ts`
Expected: PASS (6 test verdi).

- [ ] **Step 5: Commit**

```bash
cd frontend && git add lib/discovery-surprise.ts tests/discovery-surprise.test.ts
git commit -m "feat(discovery): pickSurprise — roulette pura del seme dal gusto"
```

---

## Task B2: Bottone "Sorprendimi" nella barra del dig

Aggiunge il bottone e due prop a `DiscoveryDigBar`. Component test.

**Files:**
- Modify: `frontend/components/discovery-dig-bar.tsx`
- Modify: `frontend/tests/discovery-dig-bar.test.tsx`
- Modify: `frontend/lib/i18n/it.ts` (blocco `discovery`, ~riga 623), `frontend/lib/i18n/en.ts` (blocco `discovery`, ~riga 621)

**Interfaces:**
- Consumes: `Button` da `@/components/ui` (variante `outline` esistente), icona `Dices` da `lucide-react`, chiavi i18n `t.discovery.surprise` e `t.discovery.surpriseEmpty`.
- Produces: due nuove prop di `DiscoveryDigBar`: `onSurprise: () => void` e `canSurprise: boolean`.

- [ ] **Step 1: Aggiungi le stringhe i18n**

In `frontend/lib/i18n/it.ts`, blocco `discovery`, dopo `dig: "Scava",`:

```ts
    surprise: "Sorprendimi",
    surpriseEmpty: "Nessun genere o etichetta in libreria da cui pescare.",
```

In `frontend/lib/i18n/en.ts`, blocco `discovery`, dopo la riga equivalente `dig: "Dig",` (verifica la stringa esatta EN):

```ts
    surprise: "Surprise me",
    surpriseEmpty: "No genre or label in your library to pick from.",
```

- [ ] **Step 2: Aggiorna il setup dei test esistenti (default delle nuove prop)**

In `frontend/tests/discovery-dig-bar.test.tsx`, nella funzione `setup`, aggiungi le due prop ai default (dentro l'oggetto `props`, dopo `busy: false, ready: true, onSubmit: vi.fn(),`):

```ts
    onSurprise: vi.fn(), canSurprise: true,
```

- [ ] **Step 3: Scrivi i nuovi test del bottone (falliranno)**

In `frontend/tests/discovery-dig-bar.test.tsx`, dentro `describe("DiscoveryDigBar", ...)`, aggiungi:

```ts
  it("il click su Sorprendimi chiama onSurprise", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Sorprendimi"));
    expect(p.onSurprise).toHaveBeenCalledTimes(1);
  });

  it("Sorprendimi e' disabilitato quando il pool e' vuoto", () => {
    setup({ canSurprise: false });
    expect(screen.getByText("Sorprendimi").closest("button")?.hasAttribute("disabled")).toBe(true);
  });
```

- [ ] **Step 4: Esegui i test e verifica che falliscano**

Run: `cd frontend && npx vitest run tests/discovery-dig-bar.test.tsx`
Expected: FAIL — `Unable to find an element with the text: Sorprendimi`.

- [ ] **Step 5: Aggiungi il bottone al componente**

In `frontend/components/discovery-dig-bar.tsx`:

5a. Estendi l'import icone (riga 4) aggiungendo `Dices`:

```tsx
import { Dices, Disc3, Shovel, Tags } from "lucide-react";
```

5b. Aggiungi le due prop alla firma del componente. Nel blocco dei parametri destrutturati (righe 20-21) e nel tipo props (dopo `onSubmit: () => void;`, ~riga 37):

Parametri destrutturati — sostituisci:

```tsx
  options, pilePages, busy, ready, onSubmit,
```

con:

```tsx
  options, pilePages, busy, ready, onSubmit, onSurprise, canSurprise,
```

Tipo props — dopo `onSubmit: () => void;` aggiungi:

```tsx
  onSurprise: () => void;
  canSurprise: boolean;
```

5c. Aggiungi il bottone subito dopo il `<Button type="submit">…Scava…</Button>` (dopo la riga ~117, dentro lo stesso `<div className="flex flex-wrap items-center gap-x-4 gap-y-3">`):

```tsx
        <Button
          type="button"
          variant="outline"
          onClick={onSurprise}
          disabled={busy || !canSurprise}
          title={canSurprise ? undefined : t.discovery.surpriseEmpty}
          className="w-full sm:w-auto"
        >
          <Dices size={15} /> {t.discovery.surprise}
        </Button>
```

- [ ] **Step 6: Esegui i test e verifica che passino**

Run: `cd frontend && npx vitest run tests/discovery-dig-bar.test.tsx`
Expected: PASS (tutti i test esistenti + i 2 nuovi).

- [ ] **Step 7: Commit**

```bash
cd frontend && git add components/discovery-dig-bar.tsx tests/discovery-dig-bar.test.tsx lib/i18n/it.ts lib/i18n/en.ts
git commit -m "feat(discovery): bottone Sorprendimi nella barra del dig"
```

---

## Task B3: Wiring in pagina — navigazione e reroll-on-empty

Collega il bottone al pick e alla navigazione; aggiunge il reroll automatico singolo sul colpo a vuoto. Logica di pagina, verifica in browser.

**Files:**
- Modify: `frontend/app/discovery/page.tsx`

**Interfaces:**
- Consumes: `pickSurprise` da `@/lib/discovery-surprise` (Task B1); prop `onSurprise`/`canSurprise` di `DiscoveryDigBar` (Task B2). Usa lo state esistente `genres`, `labels`, `subject`, `dig`, e `router`/`pathname`.
- Produces: nessuna nuova interfaccia esterna.

- [ ] **Step 1: Importa `pickSurprise` e `useRef`**

In `frontend/app/discovery/page.tsx`:

1a. Aggiungi `useRef` all'import React (riga 3):

```tsx
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
```

1b. Aggiungi l'import della funzione pura (accanto agli altri import `@/lib/...`, es. dopo la riga 21):

```tsx
import { pickSurprise } from "@/lib/discovery-surprise";
```

- [ ] **Step 2: Aggiungi i ref di stato del "Sorprendimi" e il pool**

In `frontend/app/discovery/page.tsx`, subito dopo la dichiarazione di `const [error, setError] = useState<string | null>(null);` (~riga 54):

```tsx
  // "Sorprendimi": traccia se il dig in corso nasce dal bottone (per il reroll)
  // e se il reroll singolo è già stato speso.
  const surpriseRef = useRef(false);
  const surpriseRerolledRef = useRef(false);

  const surprisePool = useMemo(
    () => ({ genres: genres?.library ?? [], labels: labels?.map((l) => l.label) ?? [] }),
    [genres, labels],
  );
  const canSurprise = surprisePool.genres.length + surprisePool.labels.length > 0;
```

- [ ] **Step 3: Aggiungi l'handler `runSurprise`**

In `frontend/app/discovery/page.tsx`, subito dopo la funzione `runDig` (finisce a ~riga 108):

```tsx
  const navigateDig = (seed: SeedType, value: string, d: number) => {
    const params = new URLSearchParams();
    params.set("seed", seed);
    params.set("value", value);
    params.set("depth", String(d));
    router.push(`${pathname}?${params.toString()}`, { scroll: false });
  };

  const runSurprise = () => {
    const pick = pickSurprise(surprisePool, subject.trim() || null);
    if (!pick) return;
    surpriseRef.current = true;        // questo dig nasce da Sorprendimi
    surpriseRerolledRef.current = false; // nuovo click: reroll di nuovo disponibile
    navigateDig(pick.seedType, pick.value, pick.depth);
  };
```

- [ ] **Step 4: Il dig manuale azzera lo stato Sorprendimi**

In `frontend/app/discovery/page.tsx`, dentro `runDig`, subito dopo `if (!value) return;` (~riga 98):

```tsx
    surpriseRef.current = false;
    surpriseRerolledRef.current = false;
```

- [ ] **Step 5: Aggiungi l'effetto di reroll-on-empty**

In `frontend/app/discovery/page.tsx`, dopo l'effetto che reagisce a `paramsKey` (finisce a ~riga 94), aggiungi:

```tsx
  // Colpo a vuoto di "Sorprendimi": un solo reroll automatico, poi l'empty state
  // normale. Vale solo per i dig nati dal bottone (surpriseRef), mai per i manuali.
  useEffect(() => {
    if (!dig) return;
    if (!surpriseRef.current) return;
    surpriseRef.current = false; // consuma il flag del dig appena risolto
    if (dig.leads.length > 0) return;
    if (surpriseRerolledRef.current) return; // reroll già speso: mostra empty state
    surpriseRerolledRef.current = true;
    const pick = pickSurprise(surprisePool, dig.value);
    if (!pick) return;
    surpriseRef.current = true; // anche il reroll nasce da Sorprendimi
    navigateDig(pick.seedType, pick.value, pick.depth);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dig]);
```

- [ ] **Step 6: Passa le nuove prop a `DiscoveryDigBar`**

In `frontend/app/discovery/page.tsx`, nel JSX `<DiscoveryDigBar … />` (~righe 131-147), aggiungi le due prop (es. dopo `onSubmit={runDig}`):

```tsx
        onSurprise={runSurprise}
        canSurprise={canSurprise}
```

- [ ] **Step 7: Verifica type-check, lint e unit**

Run: `cd frontend && npm run lint && npm run test:unit`
Expected: PASS. Nessun errore TS su prop mancanti/eccedenti di `DiscoveryDigBar`.

- [ ] **Step 8: Verifica nel browser**

Avvia il dev server (preview_start), apri `/discovery`. Conferma con read_page/screenshot: (a) il bottone "Sorprendimi" è presente accanto a "Scava"; (b) al click l'URL cambia con `seed`/`value`/`depth` e parte un dig con un seme di libreria; (c) la barra mostra il seme e la depth pescati; (d) ripremendo esce (quasi sempre) un seme diverso. Se hai una libreria di test vuota, verifica almeno che il bottone sia disabilitato con tooltip.

- [ ] **Step 9: Commit**

```bash
cd frontend && git add app/discovery/page.tsx
git commit -m "feat(discovery): Sorprendimi naviga il dig e rerolla una volta sul colpo a vuoto"
```

---

## Verifica finale

- [ ] `cd frontend && npm run lint && npm run test:unit && npm run build` — tutto verde.
- [ ] Guida del Set Builder visibile (header + intro) e cliccabile.
- [ ] "Sorprendimi" pesca semi di libreria, mostra i parametri pescati, rerolla una sola volta sul vuoto, è disabilitato con pool vuoto.

## Note di self-review

- **Copertura spec:** A (header + inline) → Task A. B pick uniforme/anti-ripetizione/style curati esclusi → B1. UI bottone/disabled → B2. Navigazione URL + reroll singolo + solo per dig-da-Sorprendimi → B3. Test unit su `pickSurprise` → B1; component test bottone → B2. Nessuna modifica backend (il payload `/genres` distingue già `library` da `styles`, e `labels` arriva separato): confermato leggendo `discovery_genres` e `page.tsx` — l'endpoint flag ipotizzato nella spec non serve.
- **Coerenza tipi:** `SeedType` è la stessa union in `discovery-dig-bar.tsx` e importata type-only in `discovery-surprise.ts`; `SurprisePick.depth` usa gli stessi valori di `DEPTHS`. `dig.value`/`dig.seed_type` esistono su `DiscoveryDigResponse` (usati già a `page.tsx:116`).
- **Reroll & loop:** su seme unico uguale a current il pick ripesca lo stesso valore → `navigateDig` produce una query identica → `paramsKey` invariato → l'effetto del dig non rilancia: nessun loop, l'empty state resta. Accettabile.
