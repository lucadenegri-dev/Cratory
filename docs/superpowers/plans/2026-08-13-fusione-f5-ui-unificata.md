# Fusione Sortory → Cratory — F5 (UI unificata) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un solo design system in memoria: un dizionario, un provider dei job, una barra di progresso, una pagina Impostazioni, e il gruppo Organize nella navigazione.

**Architecture:** Il `JobsProvider` di Cratory è il framework di polling e il renderer; i cinque job di Organize diventano cinque righe pollate e le sue cinque azioni entrano nella sua `JobsApi`. La riga singola prende il trattamento di Organize (fase in etichetta, `EqMeter`, `n/m · %`) dentro il contenitore multi-job di Cratory. I 439 righe di dizionario di Organize entrano sotto la chiave `organize.*`. `app/organize/layout.tsx`, che esiste solo per annidare i due provider, sparisce.

**Tech Stack:** Next 16.2.9, React 19.2.4, Tailwind v4, TypeScript, vitest, Playwright.

**Spec di riferimento:** `docs/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md`, sezione "5. Frontend" — **con le correzioni qui sotto**: quella sezione è in parte decaduta.

**Prerequisito:** F4 eseguita e mergiata su `master` (`3f6484a`). Si continua su `feat/fusione-f1`, worktree `.claude/worktrees/fusione-f1`.

## Dove la spec è decaduta (misurato 2026-08-13, non letto)

- **`globals.css` è uno solo.** F1 non ha mai portato dentro quello di Organize: le pagine `/organize` girano sui token di Cratory da settimane. Le "90 righe di differenza" erano una misura fra i due repo pre-fusione. **Niente da riconciliare.**
- **`add-source.tsx` e `source-menu.tsx` non esistono più**: cancellati da F3b insieme alla pagina e all'API. La spec li elenca ancora fra i componenti che muoiono in F5.
- **Il cluster morto è di quattro componenti, non due.** `components/organize/editorial-shell.tsx` non è importato da nessuno, e `index-nav`, `clock`, `theme-toggle` di Organize sono raggiungibili **solo** attraverso di lui. Conseguenza utile: il doppio tema (`djorganizer-theme` vs `cratory-theme`) non è mai stato un difetto reale, perché quel toggle non viene renderizzato.
- **`page-layout` non è una divergenza estetica**: Cratory ha lo slot `action` nell'header, Organize ha lo slot `guide` nella colonna marginale. Nessuno dei due è un superset — la fusione è l'unione.
- **Il vocabolario delle fasi è di quattro valori più null** (`scanning`, `linking`, `inspecting`, `deduping`), e `result.linking` può essere `null` per uno scan ristretto all'inbox.

## Decisioni prese

| | |
|---|---|
| **Barra dei job** | Contenitore di Cratory (impilamento multi-job, "+N altri") con la riga arricchita di Organize: fase in etichetta, `EqMeter` a tutta larghezza, `n/m · %` |
| **Impostazioni** | Le card di Cratory restano dove sono; sotto, una sezione intestata **Organize** con naming template, folder template e regole dedup |
| **Nav** | Gruppo **Organize** fra Scopri e Colleziona (design doc, sezione 1) |

## Global Constraints

- Worktree **`.claude/worktrees/fusione-f1`**, branch `feat/fusione-f1`. **Prima di iniziare:** leggere `frontend/CLAUDE.md`.
- **Commit senza `Co-Authored-By`.** Prima di ogni commit: `git status --porcelain` e `git branch --show-current`.
- **Ogni asserzione va accompagnata dal sabotaggio che la prova.** In F4 sono emerse sette perdite silenziose di comportamento, nessuna intercettata dalla suite; in questo progetto cinque test passavano senza verificare nulla. Un test che non si è visto fallire non è verificato, e dopo ogni sabotaggio si controlla `git diff` vuoto, non solo il verde.
- **Per ogni file che sparisce, l'inventario di cosa FORNISCE** — provider montati, side effect a import-time, comportamenti impliciti — non di cosa importa. È così che in F1 sono spariti `load_dotenv` e il montaggio di un `JobsProvider`, lasciando bottoni morti in silenzio.
- **Gli invarianti confrontano il valore col suo ricalcolo**, non con NULL.
- **Nessun import fra i due strati del frontend** finché il task che li fonde non è chiuso: `@/lib/api` e `@/lib/organize/api` restano separati fino al Task 4.

---

### Task 1: Cancellare il cluster morto

**Files:**
- Delete: `frontend/components/organize/{editorial-shell,index-nav,clock,theme-toggle}.tsx`
- Test: `frontend/tests/organize-cluster-morto.test.ts`

**Inventario di cosa forniscono** — obbligatorio prima di cancellare:

| componente | cosa fornisce | dove ricompare |
|---|---|---|
| `editorial-shell` | monta `IndexNav`; wrapper di layout | l'`EditorialShell` di Cratory, già montato dal root layout |
| `index-nav` | menu di Organize, bottone scan, `Clock`, `ThemeToggle` | il menu di Cratory (Task 5 aggiunge il gruppo Organize); il bottone scan è già unico da F4 |
| `clock` | orologio nell'header | identico a quello di Cratory (diff 0) |
| `theme-toggle` | toggle tema su chiave `djorganizer-theme` | quello di Cratory, su `cratory-theme` |

Nessuno dei quattro monta provider o ha side effect a import-time: sono componenti di presentazione. L'unico comportamento non replicato è la chiave `localStorage` del tema — e non essendo mai stato renderizzato, non esiste uno stato utente da migrare.

**Una cosa da portare via prima di cancellare**: il `theme-toggle` di Organize traduce le etichette (`t.nav.themePaper` / `t.nav.themeDark`), quello di Cratory le ha **hardcoded** (`"Paper"` / `"Dark"`). È un miglioramento, e va travasato nel Task 2 quando i dizionari si uniscono.

- [ ] **Step 1: Provare che sono morti**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
for c in editorial-shell index-nav clock theme-toggle; do
  echo "== $c"
  grep -rn "organize/$c" app components lib | grep -v "components/organize/"
done
```

Atteso: **nessun output** per tutti e quattro. I riferimenti interni al cluster (editorial-shell → index-nav → clock/theme-toggle) non contano: cadono insieme.

- [ ] **Step 2: Scrivere il test**

Crea `frontend/tests/organize-cluster-morto.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

describe("il cluster shell di Organize non esiste più", () => {
  for (const c of ["editorial-shell", "index-nav", "clock", "theme-toggle"]) {
    it(`components/organize/${c}.tsx è stato rimosso`, () => {
      expect(existsSync(resolve(__dirname, `../components/organize/${c}.tsx`))).toBe(false);
    });
  }
});
```

- [ ] **Step 3: Vederlo fallire, poi cancellare**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx vitest run tests/organize-cluster-morto.test.ts
```

Atteso: 4 failed.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git rm -q frontend/components/organize/editorial-shell.tsx \
          frontend/components/organize/index-nav.tsx \
          frontend/components/organize/clock.tsx \
          frontend/components/organize/theme-toggle.tsx
```

- [ ] **Step 4: Typecheck, build, test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx tsc --noEmit && npm run build && npm run test:unit
```

Atteso: tutti verdi, 4 test nuovi passati.

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A frontend && git commit -m "chore(f5): via il cluster shell di Organize, mai montato"
```

---

### Task 2: Un solo dizionario

**Files:**
- Modify: `frontend/lib/i18n/en.ts`, `it.ts`
- Modify: ogni file sotto `app/organize/` e `components/organize/` che importa `@/lib/organize/i18n`
- Delete: `frontend/lib/organize/i18n/`
- Modify: `frontend/components/theme-toggle.tsx` (etichette tradotte)
- Test: `frontend/tests/i18n-organize.test.ts`

**Inventario di cosa fornisce `lib/organize/i18n/`**: il dizionario (439 righe `en`, 432 `it`), `I18nProvider` annidato in `app/organize/layout.tsx`, `useT`, `runtime.ts` con `translateApiError` e la chiave `localStorage` `"sortory-lang"`. Dopo la fusione: dizionario sotto `organize.*`, provider unico di Cratory, `translateApiError` di Cratory, chiave unica `"cratory-lang"`. **La conseguenza è voluta**: le due sezioni smettono di poter avere lingua diversa.

- [ ] **Step 1: Scrivere il test**

Crea `frontend/tests/i18n-organize.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { en } from "../lib/i18n/en";
import { it as itDict } from "../lib/i18n/it";

describe("dizionario unico", () => {
  it("il dizionario di Organize non esiste più", () => {
    expect(existsSync(resolve(__dirname, "../lib/organize/i18n"))).toBe(false);
  });

  it("le chiavi di Organize vivono sotto organize.*", () => {
    expect(en.organize).toBeDefined();
    expect(itDict.organize).toBeDefined();
  });

  it("en e it hanno le stesse chiavi sotto organize (nessuna persa nel travaso)", () => {
    const chiavi = (o: object, prefisso = ""): string[] =>
      Object.entries(o).flatMap(([k, v]) =>
        v && typeof v === "object" && !Array.isArray(v)
          ? chiavi(v as object, `${prefisso}${k}.`)
          : [`${prefisso}${k}`]);
    expect(chiavi(itDict.organize).sort()).toEqual(chiavi(en.organize).sort());
  });

  it("nessun file importa più il dizionario di Organize", () => {
    const sorgenti = readFileSync(resolve(__dirname, "../lib/i18n/en.ts"), "utf8");
    expect(sorgenti).not.toContain("organize/i18n");
  });

  it("il toggle del tema non ha più etichette hardcoded", () => {
    const toggle = readFileSync(resolve(__dirname, "../components/theme-toggle.tsx"), "utf8");
    expect(toggle).not.toContain('"Paper"');
    expect(toggle).toContain("t.nav.theme");
  });
});
```

- [ ] **Step 2: Vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx vitest run tests/i18n-organize.test.ts
```

Atteso: tutti falliti tranne, forse, il quarto.

- [ ] **Step 3: Travasare il dizionario**

In `lib/i18n/en.ts`, aggiungere una chiave `organize` che contiene l'intero dizionario di `lib/organize/i18n/en.ts`. Stessa cosa in `it.ts`. `en.ts` resta la fonte di verità e `it.ts` è tipizzato su `typeof en`: **una chiave dimenticata è un errore di compilazione**, ed è la rete che rende sicuro un travaso di 439 righe.

Aggiungere `themePaper` e `themeDark` sotto `nav` (arrivano dal dizionario di Organize) e usarle in `components/theme-toggle.tsx`.

- [ ] **Step 4: Riscrivere gli import e le chiavi**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
find app/organize components/organize -name '*.tsx' -print0 | \
  xargs -0 sed -i '' -e 's|@/lib/organize/i18n|@/lib/i18n|g' && \
grep -rn "organize/i18n" app components lib | head
```

Atteso dal `grep`: nessun output.

Poi il passaggio che la sed **non** può fare: ogni `t.qualcosa` in quei file diventa `t.organize.qualcosa`. Il compilatore li elenca tutti — `npx tsc --noEmit` è la lista di lavoro.

- [ ] **Step 5: Rimuovere il dizionario vecchio**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git rm -r -q frontend/lib/organize/i18n
```

In `app/organize/layout.tsx` togliere `OrganizeI18nProvider` (il file resta finché il Task 4 non toglie anche il JobsProvider).

- [ ] **Step 6: Verde, e la prova del sabotaggio**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx tsc --noEmit && npx vitest run tests/i18n-organize.test.ts && npm run test:unit
```

Poi: cancella **una** chiave da `it.ts` sotto `organize` → il terzo test **deve fallire** (e `tsc` deve segnalarlo). Ripristina e verifica `git diff` vuoto.

- [ ] **Step 7: Build e commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npm run build && npm run lint
```

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A frontend && git commit -m "feat(f5): un solo dizionario, le chiavi di Organize sotto organize.*"
```

---

### Task 3: I tre componenti condivisi

**Files:**
- Modify: `frontend/components/page-layout.tsx` (unione degli slot), `frontend/components/ui.tsx` (+`Progress`)
- Delete: `frontend/components/organize/{page-layout,ui,path-picker-button}.tsx`
- Test: `frontend/tests/componenti-unici.test.tsx`

**Inventario:**

| componente | cosa fornisce la copia Organize | destino |
|---|---|---|
| `page-layout` | lo slot `guide` con intestazione e separatore | **si travasa**: il componente unico ha sia `action` sia `guide` |
| `ui` | `Progress` (unico export non presente in Cratory) | **si travasa** |
| `path-picker-button` | niente di più: stessa logica, import diversi | si cancella, vince Cratory (che ha anche `errText`) |

- [ ] **Step 1: Scrivere il test**

Crea `frontend/tests/componenti-unici.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { PageLayout } from "../components/page-layout";
import { Progress } from "../components/ui";

describe("componenti condivisi in una copia sola", () => {
  for (const c of ["page-layout", "ui", "path-picker-button"]) {
    it(`components/organize/${c}.tsx è stato rimosso`, () => {
      expect(existsSync(resolve(__dirname, `../components/organize/${c}.tsx`))).toBe(false);
    });
  }

  it("PageLayout rende lo slot action di Cratory", () => {
    render(<PageLayout title="T" action={<button>Azione</button>}>x</PageLayout>);
    expect(screen.getByRole("button", { name: "Azione" })).toBeTruthy();
  });

  it("PageLayout rende lo slot guide di Organize", () => {
    render(<PageLayout title="T" guide={<p>Come si usa</p>}>x</PageLayout>);
    expect(screen.getByText("Come si usa")).toBeTruthy();
  });

  it("PageLayout apre la colonna marginale anche con la sola guide", () => {
    const { container } = render(<PageLayout title="T" guide={<p>G</p>}>x</PageLayout>);
    expect(container.querySelector("aside")).not.toBeNull();
  });

  it("Progress è esportato dal ui unico", () => {
    expect(typeof Progress).toBe("function");
  });
});
```

- [ ] **Step 2: Vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx vitest run tests/componenti-unici.test.tsx
```

Atteso: falliscono i tre sull'esistenza, `guide`, la colonna marginale e `Progress`.

- [ ] **Step 3: Unire `page-layout`**

Il componente unico prende **entrambi** gli slot. Dalla copia Organize arrivano: il prop `guide`, `hasAside = marginalia != null || guide != null` (la colonna si apre anche con la sola guida), e il blocco che rende la guida con il separatore quando c'è anche `marginalia`. Da Cratory resta `action` nell'header.

Attenzione: la copia Organize è `"use client"` e usa `useT` per l'intestazione "Guida"; quella di Cratory è un server component. **Il componente unito deve restare utilizzabile da entrambe le sponde**: se `guide` richiede `useT`, marcarlo `"use client"` è accettabile (lo sono già quasi tutte le pagine), ma verificare che nessuna pagina server-only lo importi — `npm run build` lo dice.

- [ ] **Step 4: Travasare `Progress` e cancellare le copie**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
grep -n "export function Progress" -A 15 components/organize/ui.tsx
```

Copiare quell'export in `components/ui.tsx`, poi:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git rm -q frontend/components/organize/page-layout.tsx \
          frontend/components/organize/ui.tsx \
          frontend/components/organize/path-picker-button.tsx
```

E riscrivere gli import nei consumatori:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
find app/organize components/organize -name '*.tsx' -print0 | xargs -0 sed -i '' \
  -e 's|@/components/organize/page-layout|@/components/page-layout|g' \
  -e 's|@/components/organize/ui|@/components/ui|g' \
  -e 's|@/components/organize/path-picker-button|@/components/path-picker-button|g' \
  -e 's|from "\./ui"|from "@/components/ui"|g' \
  -e 's|from "\./page-layout"|from "@/components/page-layout"|g' && \
npx tsc --noEmit
```

- [ ] **Step 5: Verde, sabotaggio, build**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx vitest run tests/componenti-unici.test.tsx && npm run build && npm run test:unit
```

Poi: togli `guide` da `hasAside` (lascia `marginalia != null`) → **il test sulla colonna marginale deve fallire**. Ripristina, `git diff` vuoto.

- [ ] **Step 6: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A frontend && git commit -m "feat(f5): page-layout con action e guide, ui unico con Progress"
```

---

### Task 4: Un solo provider dei job, una sola barra

**Files:**
- Modify: `frontend/components/jobs-provider.tsx`
- Delete: `frontend/components/organize/jobs-provider.tsx`, `frontend/app/organize/layout.tsx`
- Test: `frontend/tests/jobs-provider-unico.test.tsx`

**È il punto di merge vero, ed è anche il difetto visibile:** oggi entrambi i provider renderizzano una barra `fixed inset-x-0 bottom-0 z-40`, e da F4 il job è uno solo — durante una scansione le due barre mostrano lo **stesso** job sovrapposte nello stesso punto.

**Inventario di cosa fornisce `components/organize/jobs-provider.tsx`** — obbligatorio, è un file che monta un provider:

| cosa fornisce | dove ricompare |
|---|---|
| 5 stati tipizzati (`scan`, `apply`, `rescan`, `integrity`, `genreReview`) | 5 righe pollate nella `JobsApi` di Cratory |
| 5 azioni (`startScan`, `startApply`, `startRescan`, `startIntegrity`, `startGenreReview`) | metodi sulla `JobsApi` di Cratory |
| `refresh()` | esiste già in Cratory |
| **riavvio automatico dello scan alla fine di un apply** (righe ~110-116) | **da riportare esplicitamente**: è un comportamento, non un'API, ed è il tipo di cosa che sparisce in silenzio |
| la barra `GlobalProgress` | la barra di Cratory, con la riga arricchita |

**La divisione dei ruoli.** Quello di Cratory è un framework: righe generiche con `key/label/detail/processed/total/indeterminate/href/outcome`, job client (`startClientJob`/`updateClientJob`/`endClientJob`), esiti transienti che restano `OUTCOME_MS`, errori che restano finché non li chiudi, `MAX_ROWS = 3` con "+N altri", polling in pausa a tab nascosta. Quello di Organize è un controller specifico. **Il framework vince, il controller ci entra dentro.**

- [ ] **Step 1: Scrivere il test**

Crea `frontend/tests/jobs-provider-unico.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const provider = readFileSync(resolve(__dirname, "../components/jobs-provider.tsx"), "utf8");

describe("un solo provider dei job", () => {
  it("il provider di Organize non esiste più", () => {
    expect(existsSync(resolve(__dirname, "../components/organize/jobs-provider.tsx"))).toBe(false);
  });

  it("il layout di Organize non esiste più", () => {
    expect(existsSync(resolve(__dirname, "../app/organize/layout.tsx"))).toBe(false);
  });

  it("una sola barra fissa in tutta la codebase", () => {
    const conta = (s: string) => (s.match(/fixed inset-x-0 bottom-0/g) ?? []).length;
    expect(conta(provider)).toBe(1);
  });

  it("le azioni di Organize sono sulla JobsApi unica", () => {
    for (const a of ["startScan", "startApply", "startRescan", "startIntegrity", "startGenreReview"]) {
      expect(provider).toContain(a);
    }
  });

  it("il riavvio automatico dello scan dopo un apply è stato riportato", () => {
    expect(provider).toMatch(/apply[\s\S]{0,400}startScan/);
  });

  it("la riga mostra la fase e l'EqMeter", () => {
    expect(provider).toContain("EqMeter");
    expect(provider).toContain("phase");
  });
});
```

- [ ] **Step 2: Vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx vitest run tests/jobs-provider-unico.test.tsx
```

Atteso: tutti falliti tranne, forse, il terzo.

- [ ] **Step 3: Portare i cinque job nel poller**

Nel `JobsProvider` di Cratory, aggiungere i cinque stati di Organize ai job pollati. Ognuno diventa una `Job` row: `key` stabile, `label` dal dizionario (`t.organize.jobs.*`, arrivate col Task 2), `detail` = la **fase** (`scanning | linking | inspecting | deduping`, quattro valori più `null`), `processed`/`total` dai rispettivi stati.

**Attenzione a due cose misurate in F4:**
- `result.linking` può essere `null` (scan ristretto all'inbox: solo fase 1). La riga non deve rompersi né mostrare `0/0` come se fosse un esito.
- Il progresso **non è monotono**: due `total` diversi sulla stessa callback, e una parte del lavoro non emette progresso. La riga deve tollerare `total` che cambia in corsa — `indeterminate` esiste apposta.

- [ ] **Step 4: Portare le cinque azioni e il riavvio automatico**

Le cinque `start*` diventano metodi della `JobsApi`, ognuna "chiama l'API e poi `refresh()`". Il riavvio automatico dello scan a fine apply si riporta come effetto, **con il commento che dice perché esiste**: dopo un apply i file sul disco sono cambiati e l'indice va riallineato.

- [ ] **Step 5: Arricchire la riga**

`JobRow` prende il trattamento di Organize dentro il contenitore di Cratory: etichetta con la fase in coda (`{label}{phase ? \` · ${phase}\` : ""}`), `EqMeter` a tutta larghezza al posto della barra attuale, e a destra `processed/total · pct%`. `EqMeter` è **già** in `components/ui.tsx`: nessun componente nuovo.

- [ ] **Step 6: Cancellare provider e layout**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git rm -q frontend/components/organize/jobs-provider.tsx frontend/app/organize/layout.tsx && \
cd frontend && \
find app/organize components/organize -name '*.tsx' -print0 | xargs -0 sed -i '' \
  -e 's|@/components/organize/jobs-provider|@/components/jobs-provider|g' && \
grep -rn "organize/jobs-provider" app components lib | head
```

Atteso dal `grep`: nessun output.

- [ ] **Step 7: La verifica che conta — i bottoni AGISCONO**

È la lezione di F1: le pagine caricavano e i bottoni erano morti perché il provider non era montato.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx tsc --noEmit && npm run build && npm run test:unit
```

Poi, con backend e frontend avviati:

1. Da `/organize` lancia uno **scan**: la barra deve comparire **una sola volta**, attraversare le fasi, e i conteggi devono avanzare.
2. Costruisci un piano e lancia un **apply**: a fine apply deve ripartire da solo uno scan (il comportamento riportato allo Step 4).
3. Apri il DevTools e verifica che ci sia **un solo** elemento con `fixed inset-x-0 bottom-0` nel DOM durante un job.

- [ ] **Step 8: Sabotaggio**

Commenta il riporto del riavvio automatico → **il quinto test deve fallire**. Ripristina, `git diff` vuoto.

- [ ] **Step 9: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A frontend && \
git commit -m "feat(f5): un solo JobsProvider e una sola barra, con la riga arricchita"
```

---

### Task 5: Il gruppo Organize nella navigazione

**Files:**
- Modify: `frontend/components/index-nav.tsx`
- Test: `frontend/tests/nav-organize.test.tsx`

Il menu di Cratory **non ha ancora** il gruppo Organize: oggi ha Dashboard, Scopri, Colleziona, Suona. Il design doc lo colloca fra Scopri e Colleziona.

```
Scopri      Discovery · Shazam · Download
Organize    Inbox · Duplicati · Piano · Storico     ← nuovo
Colleziona  Libreria · Playlist · Etichette
Suona       Set · Transizioni · Analisi
```

- [ ] **Step 1: Scrivere il test**

Crea `frontend/tests/nav-organize.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const nav = readFileSync(resolve(__dirname, "../components/index-nav.tsx"), "utf8");

describe("gruppo Organize nella nav", () => {
  it("le quattro voci sono presenti", () => {
    for (const href of ["/organize", "/organize/duplicates", "/organize/plan", "/organize/history"]) {
      expect(nav).toContain(`"${href}"`);
    }
  });

  it("il gruppo sta fra Scopri e Colleziona", () => {
    const i = (s: string) => nav.indexOf(s);
    expect(i("groupDiscover")).toBeLessThan(i("groupOrganize"));
    expect(i("groupOrganize")).toBeLessThan(i("groupCollect"));
  });
});
```

- [ ] **Step 2: Vederlo fallire, poi aggiungere il gruppo**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx vitest run tests/nav-organize.test.tsx
```

Atteso: 2 failed. Poi aggiungere il gruppo in `navGroups`, con `t.nav.groupOrganize` e le quattro etichette nel dizionario (`en.ts` per prima).

**Attenzione a `isActive`**: `href === "/" ? pathname === "/" : pathname.startsWith(href)` — la voce `/organize` risulterebbe attiva anche su `/organize/plan`. Se dà fastidio, la voce Inbox va confrontata esattamente; verificalo nel browser prima di decidere.

- [ ] **Step 3: Verde, sabotaggio, commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx vitest run tests/nav-organize.test.tsx && npx tsc --noEmit && npm run build
```

Sposta il gruppo dopo `groupCollect` → **il secondo test deve fallire**. Ripristina.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A frontend && git commit -m "feat(f5): il gruppo Organize entra nella navigazione"
```

---

### Task 6: Una sola pagina Impostazioni

**Files:**
- Modify: `frontend/app/settings/page.tsx`
- Delete: `frontend/app/organize/settings/page.tsx`
- Test: `frontend/tests/settings-unica.test.tsx`

Le card di Cratory restano dove sono; sotto arriva una sezione intestata **Organize** con naming template, folder template e regole dedup.

- [ ] **Step 1: Inventario di cosa fornisce la pagina che sparisce**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
grep -n "export\|useState\|useEffect\|api\.\|from \"@/lib" app/organize/settings/page.tsx | head -30
```

Elencare **ogni** chiamata API e ogni pezzo di stato: sono i comportamenti che devono ricomparire nella pagina unica. Se la pagina mostra anche il riepilogo di uno scan (`result.linking`, che può essere `null`), quel trattamento va portato con sé.

- [ ] **Step 2: Scrivere il test**

Crea `frontend/tests/settings-unica.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const page = readFileSync(resolve(__dirname, "../app/settings/page.tsx"), "utf8");

describe("Impostazioni unica", () => {
  it("la pagina Impostazioni di Organize non esiste più", () => {
    expect(existsSync(resolve(__dirname, "../app/organize/settings/page.tsx"))).toBe(false);
  });

  it("le tre impostazioni di Organize sono nella pagina unica", () => {
    for (const k of ["naming", "folder", "dedup"]) {
      expect(page.toLowerCase()).toContain(k);
    }
  });

  it("la sezione Organize è intestata", () => {
    expect(page).toContain("groupOrganize");
  });
});
```

- [ ] **Step 3: Vederlo fallire, fondere, verificare**

Dopo la fusione, la verifica che conta non è che la pagina carichi ma che **salvi**: cambia il naming template dalla pagina unica, ricarica, e controlla che il valore sia persistito.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx vitest run tests/settings-unica.test.tsx && npx tsc --noEmit && npm run build
```

- [ ] **Step 4: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A frontend && git commit -m "feat(f5): Impostazioni unica con la sezione Organize"
```

---

### Task 7: Verifica di fase

- [ ] **Step 1: Nessun duplicato residuo**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
ls components/organize/ && echo "---" && \
for f in components/organize/*.tsx; do
  b=$(basename "$f")
  [ -f "components/$b" ] && echo "ANCORA DOPPIO: $b"
done; echo "(nessuna riga sopra = nessun duplicato)"
```

Atteso: in `components/organize/` restano solo i componenti **specifici** di Organize (`files-table`, `issues-table`, `dup-group`, `plan-ops`, `apply-modal`, `file-edit-panel`, `cover-thumb`) e nessuna riga "ANCORA DOPPIO".

- [ ] **Step 2: Una sola barra, un solo dizionario, un solo provider**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
echo "barre fisse:" && grep -rc "fixed inset-x-0 bottom-0" components/*.tsx components/organize/*.tsx 2>/dev/null | grep -v ":0" && \
echo "dizionari:" && find lib -name "en.ts" && \
echo "provider i18n montati:" && grep -rn "I18nProvider" app/layout.tsx app/organize/ 2>/dev/null
```

Atteso: **una sola** occorrenza della barra, **un solo** `en.ts`, `I18nProvider` **solo** nel root layout.

- [ ] **Step 3: Suite completa**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npm run lint && npm run build && npm run test:unit && npm run test:e2e
cd ../backend && .venv/bin/python -m pytest tests -q
```

Atteso: tutti verdi. **L'e2e deve restare 22/22**: è verde per la prima volta, e questa fase tocca la nav che gli e2e attraversano.

- [ ] **Step 4: La verifica a occhio, con le due sezioni affiancate**

Con l'app avviata, percorrere `/`, `/library`, `/organize`, `/organize/plan`, `/settings` e controllare che siano **lo stesso prodotto**: stessa densità, stessa tipografia, stesso trattamento delle intestazioni. È l'unica parte di questa fase che nessun test può fare al posto tuo.

Durante uno scan: **una** barra sola, con la fase leggibile.

- [ ] **Step 5: Spuntare la spec e committare**

Nella tabella delle fasi, riga **F5**: completamento, conteggio dei test, e la nota che `globals.css` non ha richiesto riconciliazione perché ne esisteva già uno solo.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && git add -A docs && \
git commit -m "docs(f5): F5 completata — un design system solo"
```

---

## Follow-up che questa fase NON chiude

Vanno in F6 o restano aperti, dichiarati invece che dimenticati:

- `ScanSummary.linking` è un dict non tipizzato esposto in JSON con tre forme possibili: un `TypedDict` lo renderebbe verificabile.
- `linking.unchanged` somma righe di libreria invariate **e** file d'archivio invariati sotto la stessa chiave. Se finisce in UI va disambiguato — il Task 4 lo mostra solo come contatore aggregato, quindi per ora regge.
- Il progresso non è monotono (due `total` sulla stessa callback, una fase che non emette progresso). Il Task 4 lo tollera con `indeterminate`, ma la causa resta.

## Definizione di "F5 completa"

- `components/organize/` contiene **solo** componenti specifici di Organize: zero duplicati di quelli condivisi.
- Un solo dizionario, un solo `I18nProvider`, una sola chiave `localStorage` per la lingua.
- Un solo `JobsProvider` e **una sola** barra nel DOM durante un job, con la fase leggibile.
- Il riavvio automatico dello scan dopo un apply funziona ancora.
- `app/organize/layout.tsx` non esiste più.
- Il gruppo Organize è nella nav, fra Scopri e Colleziona.
- Una sola pagina Impostazioni, e il salvataggio dei template funziona.
- e2e ancora 22/22.
