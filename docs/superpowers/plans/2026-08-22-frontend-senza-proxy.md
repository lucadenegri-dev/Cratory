# ② Frontend senza il proxy di Next — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il frontend si esporta staticamente e parla col backend senza il proxy `rewrites()` di Next, restando identico a oggi quando lo si usa in sviluppo.

**Architecture:** `output: "export"` si accende con una variabile d'ambiente al momento del build, e in quel modo `rewrites()` viene omesso. Le cinque rotte dinamiche, non esportabili staticamente, passano da segmento di path a query string. I due client HTTP derivano la base URL da un unico punto condiviso.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript, vitest + @testing-library/react, Playwright.

Spec: `docs/superpowers/specs/2026-08-22-frontend-senza-proxy-design.md`.
Contesto d'insieme: `docs/superpowers/specs/2026-08-22-tauri-decomposizione-design.md`.

## Global Constraints

- **Nessuna dipendenza nuova.** Non aggiungere righe a `frontend/package.json`.
- **Senza `CRATORY_STATIC_EXPORT`, tutto si comporta come oggi**: `npm run dev`, l'HMR, il proxy `/api/*`, la suite E2E su `:3211` col suo `distDir` separato. È l'invariante gemella di quella del ①.
- **Lingua:** commenti e nomi dei test in italiano nel frontend, come il resto del codice; l'inglese solo in `docs/*.md` e `PROGRESS.md`.
- **Non ri-decodificare i valori di `useSearchParams()`.** Li restituisce già decodificati una volta: una `decodeURIComponent` in più corrompe ogni valore che contenga `%`, `&` o `#`. `lib/back-link.ts` documenta già questa trappola per il parametro `from`; vale identica per `id` e `label`.
- **Comandi** (dalla cartella `frontend/`):
  - `npm run lint` — baseline: 0 errori, 4 warning preesistenti
  - `npm run test:unit` — baseline: **375 test su 63 file, tutti verdi**
  - `npm run build` — build normale
  - `CRATORY_STATIC_EXPORT=1 npm run build` — build statico (esiste solo dal Task 6)
- **Il backend non si tocca**, tranne la riga del CORS nel Task 7.

## Struttura dei file

| File | Responsabilità | Task |
|---|---|---|
| `frontend/lib/back-link.ts` | `withFrom` deve reggere un href che ha già una query | 1 |
| `frontend/lib/api/base.ts` (nuovo) | L'unico punto che decide la base URL del backend | 2 |
| `frontend/lib/api/client.ts`, `frontend/lib/organize/api.ts` | Entrambi derivano da `base.ts` | 2 |
| `frontend/app/tracks/`, `app/playlists/` | Da `[id]/page.tsx` a `page.tsx` con `?id=` | 3 |
| `frontend/app/sets/`, `app/labels/`, `app/shazam/` | Idem, più il confine `<Suspense>` che non hanno | 4 |
| I 18 siti che costruiscono link | Path → query string | 3, 4 |
| `frontend/next.config.ts` | Il modo di build statico | 5 |
| `backend/app/core/config.py` | L'origin del webview nel CORS | 6 |

---

### Task 1: `withFrom` con un href che ha già una query

**Files:**
- Modify: `frontend/lib/back-link.ts` (funzione `withFrom`, in fondo al file)
- Test: `frontend/tests/back-link.test.ts`

**Interfaces:**
- Consumes: niente.
- Produces: `withFrom(href: string, from: string): string` — firma invariata, ora corretta anche quando `href` contiene già `?`.

**Perché è il primo task.** Oggi `withFrom` fa `${href}?from=...` e il suo docstring dice esplicitamente «`href` non deve avere già una query (i link verso i dettagli non ne hanno)». Dal Task 3 in poi ce l'avranno tutti: `/tracks?id=42`. Senza questa correzione ogni link di dettaglio diventerebbe `/tracks?id=42?from=...`, che è un URL rotto in cui `id` vale letteralmente `42?from=%2Flibrary`.

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere in coda a `frontend/tests/back-link.test.ts`:

```ts
describe("withFrom con un href che ha già una query", () => {
  it("usa & invece di ? quando la query c'è già", () => {
    expect(withFrom("/tracks?id=42", "/library")).toBe("/tracks?id=42&from=%2Flibrary");
  });

  it("usa ancora ? quando la query non c'è", () => {
    expect(withFrom("/library", "/")).toBe("/library?from=%2F");
  });

  it("non ri-codifica un href che contiene già un valore percent-encoded", () => {
    // /labels?label=Ostgut%20Ton: il valore è già codificato dal chiamante e
    // withFrom non deve toccarlo, solo appendere il proprio parametro.
    expect(withFrom("/labels?label=Ostgut%20Ton", "/labels")).toBe(
      "/labels?label=Ostgut%20Ton&from=%2Flabels",
    );
  });
});
```

- [ ] **Step 2: Eseguirli per vederli fallire**

```bash
npm run test:unit -- back-link
```

Atteso: 3 FAIL, con `"/tracks?id=42?from=%2Flibrary"` ricevuto al posto di `"/tracks?id=42&from=%2Flibrary"`.

- [ ] **Step 3: Correggere `withFrom`**

In `frontend/lib/back-link.ts`, sostituire:

```ts
/** Appende `?from=<origine>` a un link verso una pagina di dettaglio.
 *  `href` non deve avere già una query (i link verso i dettagli non ne hanno). */
export function withFrom(href: string, from: string): string {
  return `${href}?from=${encodeURIComponent(from)}`;
}
```

con:

```ts
/** Appende `from=<origine>` a un link verso una pagina di dettaglio.
 *  Il separatore dipende da `href`: dopo il passaggio delle rotte di dettaglio
 *  alla query string (`/tracks?id=42`) un `?` fisso produrrebbe un secondo
 *  punto interrogativo, e `id` varrebbe letteralmente "42?from=%2Flibrary". */
export function withFrom(href: string, from: string): string {
  const separatore = href.includes("?") ? "&" : "?";
  return `${href}${separatore}from=${encodeURIComponent(from)}`;
}
```

- [ ] **Step 4: Eseguire i test**

```bash
npm run test:unit -- back-link
```

Atteso: tutti verdi, compresi i test preesistenti su `resolveBackLink` e `sectionOf`.

- [ ] **Step 5: Provare l'asserzione rompendo il codice**

Rimettere `const separatore = "?"` fisso e rieseguire: deve fallire il primo dei tre test nuovi. Se passa, il test non serve a niente. Ripristinare e rieseguire.

- [ ] **Step 6: Suite completa e commit**

```bash
npm run test:unit && npm run lint
```

```bash
git add frontend/lib/back-link.ts frontend/tests/back-link.test.ts
git commit -m "fix(back-link): withFrom regge un href che ha gia' una query

Le rotte di dettaglio stanno per passare alla query string: con un ? fisso
/tracks?id=42 diventerebbe /tracks?id=42?from=..., e id varrebbe '42?from=...'."
```

---

### Task 2: Una base URL sola per i due client

**Files:**
- Create: `frontend/lib/api/base.ts`
- Modify: `frontend/lib/api/client.ts` (riga 7), `frontend/lib/organize/api.ts` (riga 8)
- Test: `frontend/tests/organize-api-base.test.ts` (esistente, va aggiornato), `frontend/tests/api-base.test.ts` (nuovo)

**Interfaces:**
- Consumes: niente.
- Produces: `API_BASE: string` esportata da `lib/api/base.ts` — `""` di default (stesso host della pagina), sovrascritta da `NEXT_PUBLIC_API_URL`.

**Attenzione al test esistente.** `frontend/tests/organize-api-base.test.ts` legge il *sorgente* di `lib/organize/api.ts` come testo e asserisce `expect(source).toContain('const API = "/api/organize"')`. Dopo questo task quella riga non esiste più e il test fallisce. Non è un test da cancellare: il suo scopo — impedire che il client Organize si porti dentro un URL assoluto — resta valido, e va riscritto sul nuovo assetto.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `frontend/tests/api-base.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const base = readFileSync(resolve(__dirname, "../lib/api/base.ts"), "utf8");
const core = readFileSync(resolve(__dirname, "../lib/api/client.ts"), "utf8");
const organize = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");

describe("base URL del backend", () => {
  it("un solo punto la decide", () => {
    expect(base).toContain("NEXT_PUBLIC_API_URL");
    // Nessuno degli altri due la ricalcola per conto proprio: due punti che
    // decidono la stessa cosa divergono, ed e' il difetto che questo task chiude.
    expect(core).not.toContain("NEXT_PUBLIC_API_URL");
    expect(organize).not.toContain("NEXT_PUBLIC_API_URL");
  });

  it("entrambi i client la importano da li'", () => {
    expect(core).toContain("API_BASE");
    expect(organize).toContain("API_BASE");
  });

  it("il default resta il path relativo, cioe' il comportamento di oggi", () => {
    expect(base).toMatch(/\?\?\s*""/);
  });
});
```

Poi sostituire il primo `it` di `frontend/tests/organize-api-base.test.ts` con:

```ts
  it("non contiene un URL assoluto verso il backend", () => {
    expect(source).not.toContain("8010");
    expect(source).not.toContain("localhost:8000");
    expect(source).not.toMatch(/https?:\/\//);
    // La base non e' piu' un letterale qui: la decide lib/api/base.ts, e il
    // prefisso /api/organize ci si compone sopra.
    expect(source).toContain("API_BASE");
    expect(source).toContain("/api/organize");
  });
```

- [ ] **Step 2: Eseguirli per vederli fallire**

```bash
npm run test:unit -- api-base
```

Atteso: `tests/api-base.test.ts` fallisce in lettura del file (`ENOENT`, `lib/api/base.ts` non esiste); `tests/organize-api-base.test.ts` fallisce sull'asserzione `API_BASE`.

- [ ] **Step 3: Creare il modulo**

Creare `frontend/lib/api/base.ts`:

```ts
/** L'unico punto che decide dove sta il backend.
 *
 *  Vuota = stesso host della pagina: le chiamate `/api/*` passano dal rewrite
 *  di `next.config.ts`, e l'app funziona anche aperta da un altro dispositivo
 *  in LAN. In un build statico quel rewrite non esiste — non c'e' nessun
 *  server Next — e la variabile punta il client direttamente al backend.
 *
 *  Sta qui e non nei due client perche' erano due: `lib/api/client.ts` aveva
 *  l'override, `lib/organize/api.ts` no, e meta' app avrebbe perso le chiamate. */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
```

- [ ] **Step 4: Far derivare i due client**

In `frontend/lib/api/client.ts`, sostituire le righe 1-7 (il commento e la costante `API`):

```ts
import { translateApiError } from "@/lib/i18n/runtime";

// Base API vuota = stesso host della pagina: le chiamate /api/* passano dal
// rewrite di next.config.ts verso il backend, quindi l'app funziona anche
// aperta da un altro dispositivo in LAN. NEXT_PUBLIC_API_URL resta come
// override opzionale solo per setup particolari (backend su origin diverso).
export const API = process.env.NEXT_PUBLIC_API_URL ?? "";
```

con:

```ts
import { API_BASE } from "@/lib/api/base";
import { translateApiError } from "@/lib/i18n/runtime";

// La base la decide lib/api/base.ts, per tutti e due i client HTTP.
export const API = API_BASE;
```

In `frontend/lib/organize/api.ts`, sostituire il commento e la costante alla riga 8:

```ts
const API = "/api/organize";
```

con:

```ts
const API = `${API_BASE}/api/organize`;
```

e aggiungere `import { API_BASE } from "@/lib/api/base";` fra gli import in testa al file. Aggiornare il commento sopra la costante perché descriva il nuovo assetto invece del vecchio.

- [ ] **Step 5: Eseguire i test**

```bash
npm run test:unit -- api-base && npm run test:unit -- organize
```

Atteso: tutti verdi.

- [ ] **Step 6: Suite completa, lint, build, commit**

```bash
npm run test:unit && npm run lint && npm run build
```

Atteso: 375+ test verdi, 0 errori di lint, build riuscito.

```bash
git add frontend/lib/api/base.ts frontend/lib/api/client.ts frontend/lib/organize/api.ts frontend/tests/api-base.test.ts frontend/tests/organize-api-base.test.ts
git commit -m "refactor(api): un solo punto decide la base URL del backend

Erano due: client.ts aveva l'override NEXT_PUBLIC_API_URL, organize/api.ts
fissava /api/organize. Senza il rewrite di Next meta' app perderebbe le chiamate."
```

---

### Task 3: `tracks` e `playlists` in query string

**Files:**
- Move: `frontend/app/tracks/[id]/page.tsx` → `frontend/app/tracks/page.tsx`
- Move: `frontend/app/playlists/[id]/page.tsx` → `frontend/app/playlists/detail/page.tsx` (perché `/playlists` è già la lista — vedi la nota sotto)
- Modify: i 14 siti che costruiscono i link, elencati sotto con file e riga
- Test: `frontend/tests/rotte-query-string.test.ts` (nuovo)

**Interfaces:**
- Consumes: `withFrom` corretta nel Task 1.
- Produces: le rotte `/tracks?id=<n>` e `/playlists/detail?id=<n>`.

**Nota sulla rotta playlists, da leggere prima di muovere qualcosa.** `app/playlists/page.tsx` esiste già ed è la lista. La pagina di dettaglio non può quindi diventare `app/playlists/page.tsx`: collidereb­be. Diventa `app/playlists/detail/page.tsx`, cioè `/playlists/detail?id=7`. `tracks` non ha questo problema — non esiste `app/tracks/page.tsx` — e diventa `/tracks?id=42`.

Verificare l'assunzione prima di procedere:

```bash
ls frontend/app/tracks/ frontend/app/playlists/
```

Se esiste un `frontend/app/tracks/page.tsx`, fermarsi e segnalarlo: servirebbe lo stesso trattamento di `playlists`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `frontend/tests/rotte-query-string.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

/* Asserzioni sul sorgente, non sul rendering: queste pagine sono grosse,
   montano provider e chiamano il backend al mount, quindi un render in vitest
   fallirebbe per ragioni estranee a cio' che va provato. Il vero cancello
   comportamentale e' `CRATORY_STATIC_EXPORT=1 npm run build` nel Task 5 — che
   oggi fallisce ed e' esattamente cio' che questa conversione ripara — piu' la
   verifica manuale in fondo a questo task. Stesso pattern di
   tests/organize-api-base.test.ts. */
const leggi = (p: string) => readFileSync(resolve(__dirname, "..", p), "utf8");

describe("le rotte di dettaglio leggono l'id dalla query", () => {
  it("tracks non e' piu' un segmento dinamico", () => {
    expect(existsSync(resolve(__dirname, "../app/tracks/[id]"))).toBe(false);
    expect(existsSync(resolve(__dirname, "../app/tracks/page.tsx"))).toBe(true);
  });

  it("playlists sta sotto detail, perche' /playlists e' gia' la lista", () => {
    expect(existsSync(resolve(__dirname, "../app/playlists/[id]"))).toBe(false);
    expect(existsSync(resolve(__dirname, "../app/playlists/detail/page.tsx"))).toBe(true);
  });

  it("nessuna delle due prende piu' l'id da `params`", () => {
    for (const p of ["app/tracks/page.tsx", "app/playlists/detail/page.tsx"]) {
      const src = leggi(p);
      expect(src, p).toContain("useSearchParams");
      expect(src, p).not.toContain("Promise<{ id: string }>");
      expect(src, p).not.toMatch(/use\(params\)/);
    }
  });

  it("nessun link punta piu' a un segmento dinamico", () => {
    const sorgenti = ["app/library/page.tsx", "app/transitions/page.tsx",
                      "components/wishlist-row.tsx", "components/library-track-grid.tsx",
                      "components/organize/files-table.tsx", "app/playlists/page.tsx"];
    for (const p of sorgenti) {
      // Il template `/tracks/${...}` e `/playlists/${...}`: le rotte statiche
      // /playlists/import-* non hanno interpolazione e non combaciano.
      expect(leggi(p), p).not.toMatch(/["`]\/(?:tracks|playlists)\/\$\{/);
    }
  });
});
```

- [ ] **Step 2: Eseguirlo per vederlo fallire**

```bash
npm run test:unit -- rotte-query-string
```

Atteso: FAIL su `Cannot find module '@/app/tracks/page'`.

- [ ] **Step 3: Spostare `tracks` e cambiarne l'ingresso**

```bash
cd frontend && git mv "app/tracks/[id]/page.tsx" app/tracks/page.tsx && rmdir "app/tracks/[id]"
```

In `app/tracks/page.tsx`, sostituire l'ingresso:

```tsx
export default function TrackPage(props: { params: Promise<{ id: string }> }) {
  return <Suspense><TrackPageInner {...props} /></Suspense>;
}
```

con:

```tsx
export default function TrackPage() {
  return <Suspense><TrackPageInner /></Suspense>;
}
```

e la firma dell'inner, da:

```tsx
function TrackPageInner({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
```

a:

```tsx
function TrackPageInner() {
  // useSearchParams restituisce il valore GIA' decodificato una volta: non
  // ri-decodificarlo. Con la rotta a segmento l'id non poteva mancare; ora
  // /tracks senza id e' raggiungibile, e "" percorre lo stesso ramo di un id
  // inesistente invece di propagare undefined.
  const id = useSearchParams().get("id") ?? "";
```

Rimuovere `use` dall'import di `react` se non è più usato altrove nel file, e aggiungere `useSearchParams` all'import da `next/navigation` (se il file non importa già da lì, aggiungere l'import).

- [ ] **Step 4: Spostare `playlists` e cambiarne l'ingresso**

```bash
cd frontend && mkdir -p app/playlists/detail && git mv "app/playlists/[id]/page.tsx" app/playlists/detail/page.tsx && rmdir "app/playlists/[id]"
```

Stessa trasformazione: l'ingresso

```tsx
export default function PlaylistDetail(props: { params: Promise<{ id: string }> }) {
  return <Suspense><PlaylistDetailInner {...props} /></Suspense>;
}
```

diventa

```tsx
export default function PlaylistDetail() {
  return <Suspense><PlaylistDetailInner /></Suspense>;
}
```

e l'inner, da `function PlaylistDetailInner({ params }: { params: Promise<{ id: string }> }) {` seguito da `const { id } = use(params);`, diventa:

```tsx
function PlaylistDetailInner() {
  // Vedi app/tracks/page.tsx: valore gia' decodificato, "" invece di undefined.
  const id = useSearchParams().get("id") ?? "";
```

- [ ] **Step 5: Aggiornare i siti che costruiscono i link**

Nove siti verso `/tracks/`, quattro verso `/playlists/`. L'elenco e' stato
verificato eseguendolo: il sito in `components/docked-player.tsx` era sfuggito
al grep iniziale perche' non usa `href=` ne' `push(`. Percorso e riga esatti:

| File e riga | Da | A |
|---|---|---|
| `app/playlists/detail/page.tsx:723` | `withFrom(`/tracks/${tr.id}`, from)` | `withFrom(`/tracks?id=${tr.id}`, from)` |
| `app/labels/[label]/page.tsx:111` | `withFrom(`/tracks/${tr.id}`, from)` | `withFrom(`/tracks?id=${tr.id}`, from)` |
| `app/tracks/page.tsx:48` | `` `/tracks/${track.id}` `` | `` `/tracks?id=${track.id}` `` |
| `app/library/page.tsx:293` | `` `/tracks/${tr.id}${trackLinkQuery}` `` | vedi sotto |
| `app/shazam/[id]/page.tsx:34` | `withFrom(`/tracks/${track.library_track_id}`, from)` | `withFrom(`/tracks?id=${track.library_track_id}`, from)` |
| `app/sets/[id]/page.tsx:390` | `withFrom(`/tracks/${st.track.id}`, from)` | `withFrom(`/tracks?id=${st.track.id}`, from)` |
| `app/transitions/page.tsx:168` | `withFrom(`/tracks/${track.id}`, from)` | `withFrom(`/tracks?id=${track.id}`, from)` |
| `components/wishlist-row.tsx:65` | `withFrom(`/tracks/${track.id}`, from)` | `withFrom(`/tracks?id=${track.id}`, from)` |
| `components/organize/files-table.tsx:115` | `` `/tracks/${r.track_id}` `` | `` `/tracks?id=${r.track_id}` `` |
| `components/docked-player.tsx` | `` `/tracks/${...}` `` | `` `/tracks?id=${...}` `` |
| `components/library-track-grid.tsx:42` | `` `/tracks/${track.id}${trackLinkQuery}` `` | vedi sotto |
| `app/playlists/page.tsx:144` e `:156` | `withFrom(`/playlists/${p.id}`, from)` | `withFrom(`/playlists/detail?id=${p.id}`, from)` |
| `app/playlists/detail/page.tsx:400` | `router.push(`/playlists/${copy.id}`)` | `router.push(`/playlists/detail?id=${copy.id}`)` |
| `app/shazam/[id]/page.tsx:148` | `withFrom(`/playlists/${importedPlaylistId}`, from)` | `withFrom(`/playlists/detail?id=${importedPlaylistId}`, from)` |
| `components/wishlist-row.tsx:150` | `withFrom(`/playlists/${p.id}`, from)` | `withFrom(`/playlists/detail?id=${p.id}`, from)` |

**Non toccare** `app/playlists/page.tsx:172-174` (`/playlists/import-spotify`, `/playlists/import-soundcloud`, `/playlists/import-manual`) né `app/playlists/import-*/**`: sono rotte statiche, non dinamiche, e restano com'erano.

**I due siti `trackLinkQuery`.** `app/library/page.tsx:105` costruisce a mano `` `?from=${encodeURIComponent(...)}` `` e lo concatena. Ora che l'href ha già una query, questa concatenazione produce due `?`. Sostituire l'uso con `withFrom`, che dal Task 1 sceglie il separatore giusto:

- `app/library/page.tsx:105`: la costante diventa il solo valore di origine, non più una query string pronta:
  ```ts
  const trackLinkFrom = queryString ? `${pathname}?${queryString}` : pathname;
  ```
- `app/library/page.tsx:293`: `` href={withFrom(`/tracks?id=${tr.id}`, trackLinkFrom)} ``
- `app/library/page.tsx:324`: passare `trackLinkFrom={trackLinkFrom}` invece di `trackLinkQuery={trackLinkQuery}`
- `components/library-track-grid.tsx`: rinominare la prop `trackLinkQuery` in `trackLinkFrom` alle righe 16, 22, 27, 33, e alla riga 42 usare `` href={withFrom(`/tracks?id=${track.id}`, trackLinkFrom)} ``, importando `withFrom` da `@/lib/back-link`. Il default della prop diventa `""`; con origine vuota `withFrom` produce `from=`, che `resolveBackLink` scarta già oggi tornando al fallback.

- [ ] **Step 6: Eseguire i test**

```bash
npm run test:unit -- rotte-query-string && npm run test:unit && npm run lint
```

Atteso: tutti verdi. Se `tests/back-link.test.ts` fallisce sui letterali `/tracks/42`, sono asserzioni sul comportamento di `withFrom` con un path qualunque, non sulle rotte reali: lasciarle come sono.

- [ ] **Step 7: Verificare a mano nel browser**

Avviare `npm run dev` e controllare, cliccando invece che leggendo il codice:

1. Da `/library`, cliccare una traccia → arriva su `/tracks?id=<n>&from=...`, la traccia è quella giusta, e il link "indietro" torna a `/library` coi filtri.
2. Da `/playlists`, aprire una playlist → `/playlists/detail?id=<n>`, contenuto giusto.
3. Aprire `/tracks` senza `id` a mano → non è una pagina bianca né un errore in console: mostra lo stesso stato di una traccia inesistente.

Riportare cosa si è visto davvero, non cosa ci si aspettava.

- [ ] **Step 8: Commit**

```bash
git add -A frontend
git commit -m "refactor(rotte): tracks e playlists leggono l'id dalla query, non dal path

Un segmento dinamico non e' staticamente esportabile: generateStaticParams su
id arbitrari non esiste. Il dettaglio playlist va sotto /playlists/detail
perche' /playlists e' gia' la lista."
```

---

### Task 4: `sets`, `labels` e `shazam` in query string

**Files:**
- Move: `frontend/app/sets/[id]/page.tsx` → `frontend/app/sets/detail/page.tsx`; `frontend/app/labels/[label]/page.tsx` → `frontend/app/labels/detail/page.tsx`; `frontend/app/shazam/[id]/page.tsx` → `frontend/app/shazam/detail/page.tsx`
- Modify: `frontend/app/sets/page.tsx:44`, `frontend/app/labels/page.tsx:87`, `frontend/app/shazam/page.tsx:144` e `:156`, `frontend/app/set-builder/page.tsx:127`, `frontend/components/statistics/statistics-view.tsx:163`
- Test: `frontend/tests/statistics-view.test.tsx` (esistente, va aggiornato)

**Interfaces:**
- Consumes: `withFrom` (Task 1), il pattern stabilito nel Task 3.
- Produces: `/sets/detail?id=<n>`, `/labels/detail?label=<testo>`, `/shazam/detail?id=<n>`.

**La differenza rispetto al Task 3.** Tutte e tre queste pagine hanno una pagina lista omonima (`app/sets/page.tsx`, `app/labels/page.tsx`, `app/shazam/page.tsx`), quindi vanno tutte sotto `detail/`. E nessuna delle tre ha un confine `<Suspense>`: `useSearchParams()` lo richiede, e senza il build statico fallisce. Vanno quindi ristrutturate nella forma che `tracks` e `playlists` hanno già.

**La trappola di `labels`.** Oggi fa `const label = decodeURIComponent(raw)` perché il segmento di path arriva codificato. `useSearchParams().get("label")` restituisce il valore **già decodificato**: lasciare quella chiamata corrompe ogni etichetta che contenga `%`, e un'etichetta come `Ostgut Ton` con uno spazio smetterebbe di combaciare. La `decodeURIComponent` va tolta.

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere a `frontend/tests/rotte-query-string.test.ts`:

```ts
describe("sets, labels e shazam", () => {
  it("nessuno e' piu' un segmento dinamico", () => {
    for (const vecchia of ["app/sets/[id]", "app/labels/[label]", "app/shazam/[id]"]) {
      expect(existsSync(resolve(__dirname, "..", vecchia)), vecchia).toBe(false);
    }
    for (const nuova of ["app/sets/detail/page.tsx", "app/labels/detail/page.tsx",
                         "app/shazam/detail/page.tsx"]) {
      expect(existsSync(resolve(__dirname, "..", nuova)), nuova).toBe(true);
    }
  });

  it("hanno il confine Suspense che useSearchParams richiede", () => {
    for (const p of ["app/sets/detail/page.tsx", "app/labels/detail/page.tsx",
                     "app/shazam/detail/page.tsx"]) {
      expect(leggi(p), p).toContain("<Suspense>");
    }
  });

  it("labels non ri-decodifica il valore", () => {
    // useSearchParams ha gia' decodificato una volta: una seconda passata
    // corrompe le etichette con % e rompe quelle con gli spazi.
    expect(leggi("app/labels/detail/page.tsx")).not.toContain("decodeURIComponent");
  });
});
```

E aggiornare `frontend/tests/statistics-view.test.tsx`, righe 45, 84 e 85, ai nuovi href:

```ts
expect(screen.getByText("Ostgut Ton").closest("a")?.getAttribute("href")).toBe("/labels/detail?label=Ostgut%20Ton");
```

```ts
const first = container.querySelector('a[href="/labels/detail?label=L0"] span span') as HTMLElement;
const sixth = container.querySelector('a[href="/labels/detail?label=L5"] span span') as HTMLElement;
```

- [ ] **Step 2: Eseguirli per vederli fallire**

```bash
npm run test:unit -- rotte-query-string statistics-view
```

Atteso: FAIL su `Cannot find module '@/app/labels/detail/page'` e sugli href vecchi.

- [ ] **Step 3: Spostare le tre pagine**

```bash
cd frontend
mkdir -p app/sets/detail app/labels/detail app/shazam/detail
git mv "app/sets/[id]/page.tsx" app/sets/detail/page.tsx && rmdir "app/sets/[id]"
git mv "app/labels/[label]/page.tsx" app/labels/detail/page.tsx && rmdir "app/labels/[label]"
git mv "app/shazam/[id]/page.tsx" app/shazam/detail/page.tsx && rmdir "app/shazam/[id]"
```

- [ ] **Step 4: Dare a ognuna il confine `<Suspense>` e la lettura dalla query**

In `app/sets/detail/page.tsx`, sostituire:

```tsx
export default function SetDetail({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const { id } = use(params);
```

con:

```tsx
export default function SetDetail() {
  // useSearchParams obbliga a un confine Suspense, altrimenti il build statico
  // fallisce: da qui la coppia wrapper + Inner, come in app/tracks/page.tsx.
  return <Suspense><SetDetailInner /></Suspense>;
}

function SetDetailInner() {
  const t = useT();
  const id = useSearchParams().get("id") ?? "";
```

Aggiungere `Suspense` all'import da `react` e `useSearchParams` a quello da `next/navigation`; togliere `use` se non serve più.

In `app/shazam/detail/page.tsx`, la stessa trasformazione su:

```tsx
export default function DjSetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const { id } = use(params);
```

che diventa:

```tsx
export default function DjSetDetailPage() {
  return <Suspense><DjSetDetailPageInner /></Suspense>;
}

function DjSetDetailPageInner() {
  const t = useT();
  const id = useSearchParams().get("id") ?? "";
```

In `app/labels/detail/page.tsx`, sostituire:

```tsx
export default function LabelDetail({ params }: { params: Promise<{ label: string }> }) {
  const t = useT();
  const { label: raw } = use(params);
  const label = decodeURIComponent(raw);
```

con:

```tsx
export default function LabelDetail() {
  return <Suspense><LabelDetailInner /></Suspense>;
}

function LabelDetailInner() {
  const t = useT();
  // Niente decodeURIComponent: useSearchParams ha gia' decodificato una volta,
  // e una seconda passata corrompe le etichette con % e rompe quelle con spazi.
  const label = useSearchParams().get("label") ?? "";
```

In tutte e tre, la chiusura della funzione originale diventa la chiusura dell'`Inner`: verificare che le graffe restino bilanciate dopo lo spostamento della riga `export default`.

- [ ] **Step 5: Aggiornare i cinque siti che costruiscono i link**

| File e riga | Da | A |
|---|---|---|
| `app/sets/page.tsx:44` | `` href={`/sets/${s.id}`} `` | `` href={`/sets/detail?id=${s.id}`} `` |
| `app/set-builder/page.tsx:127` | `` router.push(`/sets/${generation.setlist_id}`) `` | `` router.push(`/sets/detail?id=${generation.setlist_id}`) `` |
| `app/labels/page.tsx:87` | `` href={`/labels/${encodeURIComponent(l.label)}`} `` | `` href={`/labels/detail?label=${encodeURIComponent(l.label)}`} `` |
| `app/shazam/page.tsx:144` e `:156` | `` href={`/shazam/${s.id}`} `` | `` href={`/shazam/detail?id=${s.id}`} `` |
| `components/statistics/statistics-view.tsx:163` | `` href: `/labels/${encodeURIComponent(l.label)}` `` | `` href: `/labels/detail?label=${encodeURIComponent(l.label)}` `` |

`encodeURIComponent` resta in fase di **costruzione** del link — serve, perché un'etichetta può contenere `&` o `#`. È solo la decodifica in lettura che sparisce, perché `useSearchParams` la fa già.

- [ ] **Step 6: Aggiornare `sectionOf`**

`frontend/lib/back-link.ts` elenca le sezioni per prefisso e confronta per segmento (`route === prefix || route.startsWith(prefix + "/")`). `/sets/detail` combacia ancora con `/sets`, e `/labels/detail` con `/labels`: **l'elenco non va toccato.** Verificarlo eseguendo:

```bash
npm run test:unit -- back-link
```

Atteso: verde senza modifiche. Se fallisce, riportare cosa: significa che l'assunzione qui sopra è sbagliata.

- [ ] **Step 7: Test, lint e verifica manuale**

```bash
npm run test:unit && npm run lint && npm run build
```

Poi con `npm run dev`, cliccando: da `/sets` aprire un set; da `/labels` aprire un'etichetta **che contenga uno spazio** (è il caso che la doppia decodifica romperebbe); da `/shazam` aprire un set identificato. In tutti e tre il link "indietro" deve tornare alla lista giusta. Riportare cosa si è visto.

- [ ] **Step 8: Commit**

```bash
git add -A frontend
git commit -m "refactor(rotte): sets, labels e shazam leggono la query, con il confine Suspense

labels perde la decodeURIComponent: useSearchParams decodifica gia' una volta,
e la seconda corrompe le etichette con % e spazi."
```

---

### Task 5: Il modo di build statico

**Files:**
- Modify: `frontend/next.config.ts`
- Test: `frontend/tests/next-config-export.test.ts` (nuovo)

**Interfaces:**
- Consumes: le rotte convertite nei Task 3 e 4.
- Produces: `CRATORY_STATIC_EXPORT=1 npm run build` produce `frontend/out/`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `frontend/tests/next-config-export.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(__dirname, "../next.config.ts"), "utf8");

describe("modo di build statico", () => {
  it("l'export si accende da variabile d'ambiente, non e' sempre attivo", () => {
    expect(source).toContain("CRATORY_STATIC_EXPORT");
    // Sempre attivo romperebbe `npm run dev`, l'HMR e la suite E2E.
    expect(source).not.toMatch(/output:\s*"export"\s*,?\s*\n\s*(async rewrites|allowedDevOrigins)/);
  });

  it("in export i rewrites non ci sono: Next non li applicherebbe comunque", () => {
    expect(source).toContain("rewrites");
    expect(source).toMatch(/ESPORTA|esporta|statico/);
  });
});
```

- [ ] **Step 2: Eseguirlo per vederlo fallire**

```bash
npm run test:unit -- next-config-export
```

Atteso: FAIL, `CRATORY_STATIC_EXPORT` non compare in `next.config.ts`.

- [ ] **Step 3: Modificare `next.config.ts`**

Sostituire l'inizio del file, da `const BACKEND = ...` fino alla riga `const nextConfig: NextConfig = {`, aggiungendo la costante e cambiando la forma dell'oggetto:

```ts
// Origin del backend FastAPI, risolto LATO SERVER Next (non NEXT_PUBLIC: il
// browser non lo vede mai). Override con BACKEND_URL solo per setup particolari.
const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

// Build statico per il bundle desktop: niente server Next, quindi niente
// rewrites — Next non li applicherebbe, e lasciarli qui direbbe il falso a chi
// legge. Il client punta al backend con NEXT_PUBLIC_API_URL (lib/api/base.ts).
// Senza questa variabile non cambia niente: dev, HMR, proxy e suite E2E come prima.
const ESPORTA_STATICO = process.env.CRATORY_STATIC_EXPORT === "1";
```

e poi, in fondo all'oggetto `nextConfig`, sostituire il blocco `async rewrites() { ... },` con:

```ts
  ...(ESPORTA_STATICO ? { output: "export" as const } : {
    async rewrites() {
      return [
        {
          // Proxy verso il backend: il browser chiama /api/* sullo stesso host
          // della pagina (funziona anche da altri dispositivi in LAN) e Next
          // inoltra al backend. Non ci sono route app/api/ da preservare.
          source: "/api/:path*",
          destination: `${BACKEND}/api/:path*`,
        },
      ];
    },
  }),
```

- [ ] **Step 4: Eseguire il test e i due build**

```bash
npm run test:unit -- next-config-export
npm run build
CRATORY_STATIC_EXPORT=1 npm run build && ls out/
```

Atteso: test verde; build normale riuscito; build statico riuscito con una cartella `out/` che contiene `index.html`, `tracks.html`, `playlists/detail.html`, `sets/detail.html`, `labels/detail.html`, `shazam/detail.html`.

**Se il build statico fallisce lamentando `useSearchParams`**, manca un confine `<Suspense>` su una pagina: l'errore nomina il file. Aggiungerlo con la stessa forma dei Task 3 e 4, e riportare quale pagina era.

**Se fallisce lamentando `generateStaticParams`**, è rimasta una rotta dinamica non convertita: fermarsi e segnalarla, non aggiungere `generateStaticParams`.

- [ ] **Step 5: Verificare che il build statico funzioni davvero contro il backend**

Un build che compila non è un build che funziona. Con il backend avviato su `:8000`:

```bash
cd frontend && rm -rf out && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 CRATORY_STATIC_EXPORT=1 npm run build
npx --yes serve out -l 3999
```

Aprire `http://localhost:3999`, e riportare cosa succede davvero: se le chiamate `/api/*` partono verso `:8000`, se la console mostra errori CORS (è **atteso** a questo punto — il Task 6 li risolve), e se la navigazione fra le pagine funziona. Fermare `serve` e cancellare `out/` alla fine.

- [ ] **Step 6: Commit**

```bash
git add frontend/next.config.ts frontend/tests/next-config-export.test.ts
git commit -m "feat(build): modo statico dietro CRATORY_STATIC_EXPORT

In export non c'e' nessun server Next: i rewrites spariscono invece di restare
li' inerti a dire il falso. Senza la variabile non cambia niente."
```

---

### Task 6: L'origin del webview nel CORS

**Files:**
- Modify: `backend/app/core/config.py` (campo `frontend_origin`, riga 27)
- Test: `backend/tests/test_cors_origini.py` (nuovo)

**Interfaces:**
- Consumes: niente.
- Produces: il backend accetta le chiamate provenienti dal webview del bundle.

**Cosa è certo e cosa no.** `backend/app/main.py:104` costruisce `allow_origins` splittando `frontend_origin` sulle virgole. Il valore documentato per il webview di Tauri su macOS è `tauri://localhost`, ma la spec del ② lascia questo punto **aperto di proposito**: va confermato leggendolo dal webview reale nel ③. Aggiungerlo ora è comunque corretto — se il valore reale risultasse diverso, si aggiunge quello, e questo resta innocuo.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_cors_origini.py`:

```python
"""Le origini ammesse dal CORS. In un bundle la pagina non arriva piu' da
localhost:3000, e senza l'origin del webview non riesce una sola chiamata."""
from app.core.config import Settings


def _origini(s: Settings) -> list[str]:
    """Stessa scomposizione che fa main.py per costruire allow_origins."""
    return [o.strip() for o in s.frontend_origin.split(",") if o.strip()]


def test_le_origini_di_sviluppo_restano():
    origini = _origini(Settings())
    assert "http://localhost:3000" in origini
    assert "http://localhost:3001" in origini


def test_c_e_l_origin_del_webview():
    """Il bundle desktop serve la pagina da uno schema suo, non da http."""
    assert "tauri://localhost" in _origini(Settings())


def test_l_utente_puo_ancora_sovrascrivere_tutto():
    """Chi mette il proprio elenco non se lo vede allungare d'ufficio."""
    s = Settings(frontend_origin="http://192.168.1.10:3000")
    assert _origini(s) == ["http://192.168.1.10:3000"]
```

- [ ] **Step 2: Eseguirlo per vederlo fallire**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_cors_origini.py -q
```

Atteso: 1 FAIL (`test_c_e_l_origin_del_webview`), gli altri due passano già.

- [ ] **Step 3: Aggiungere l'origin**

In `backend/app/core/config.py`, sostituire:

```python
    # Origini CORS ammesse (lista separata da virgola). 3000 = dev normale, 3001 = preview.
    frontend_origin: str = "http://localhost:3000,http://localhost:3001"
```

con:

```python
    # Origini CORS ammesse (lista separata da virgola). 3000 = dev normale,
    # 3001 = preview, tauri://localhost = il webview del bundle desktop, dove
    # la pagina non arriva da un server http e senza il quale non riesce una
    # sola chiamata. Il valore per macOS va confermato sul webview reale.
    frontend_origin: str = "http://localhost:3000,http://localhost:3001,tauri://localhost"
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_cors_origini.py -q
```

Atteso: 3 passed.

- [ ] **Step 5: Suite backend completa**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

Atteso: nessun fallimento nuovo. Se un test esistente asserisce l'elenco esatto delle origini, va aggiornato: riportare quale.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_cors_origini.py
git commit -m "feat(cors): ammettere l'origin del webview del bundle

Da confermare sul webview reale quando ci sara': il valore documentato per
macOS e' tauri://localhost, ma e' il tipo di dettaglio che cambia fra versioni."
```

---

### Task 7: La documentazione

**Files:**
- Modify: `docs/ARCHITECTURE.md` (sezione Frontend), `docs/ROADMAP.md` (Current state), `PROGRESS.md` (Current state by area), `README.md` (se documenta gli URL delle pagine)
- Modify: `frontend/CLAUDE.md` (le note su Next 16 che l'AI legge prima di toccare le pagine)

**Interfaces:** niente codice.

`docs/API.md` non si tocca: nessun endpoint cambia.

- [ ] **Step 1: Verificare cosa afferma la documentazione sugli URL**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wizardly-bassi-00b805
grep -rn "tracks/\[id\]\|/tracks/{id}\|playlists/\[id\]\|rotte dinamiche\|dynamic route" docs/*.md README.md frontend/CLAUDE.md
```

Correggere ogni occorrenza che descriva le rotte vecchie. Se il comando non trova nulla, non inventare una sezione: passare allo step successivo.

- [ ] **Step 2: Aggiungere la voce in `docs/ROADMAP.md`**

Nella sezione «Current state», dopo la voce «Bundle-ready»:

```markdown
- **Frontend without the Next proxy** (2026-08-22). The frontend exports
  statically behind `CRATORY_STATIC_EXPORT=1`, which also drops `rewrites()` —
  there is no Next server in a bundle to apply them. Both HTTP clients now
  derive their base URL from one place (`lib/api/base.ts`), closing a
  duplication the backlog already flagged: only one of the two had an override,
  so half the app would have lost its calls. The five dynamic routes became
  query strings (`/tracks?id=42`, `/playlists/detail?id=7`), because a dynamic
  path segment cannot be statically exported — `generateStaticParams` over
  arbitrary ids does not exist. Bookmarks to the old URLs break; on a
  single-user personal app that was judged an acceptable price. Second of the
  four sub-projects of the Tauri packaging work.
```

- [ ] **Step 3: Aggiungere la voce in `PROGRESS.md`**

In cima all'elenco «Current state by area»:

```markdown
- **Frontend without the Next proxy** (2026-08-22): `CRATORY_STATIC_EXPORT=1`
  builds a static frontend with no `rewrites()`; one shared base URL feeds both
  HTTP clients; the five detail routes read their id from the query string
  instead of the path. Unset, `npm run dev` behaves exactly as before. Step two
  of four toward a Tauri desktop build.
```

- [ ] **Step 4: Aggiornare la sezione Frontend di `docs/ARCHITECTURE.md`**

Aggiungere, in coda a quella sezione:

```markdown
**Two build modes, one frontend.** `CRATORY_STATIC_EXPORT=1` turns on
`output: "export"` and omits `rewrites()`; without it nothing changes. The
proxy is not merely unused in export mode — there is no Next server to run it —
so it is omitted rather than left in place describing something that cannot
happen. The five detail pages take their id from the query string
(`/tracks?id=42`) rather than a path segment, because static export requires
`generateStaticParams` and no such list exists for arbitrary ids. Values from
`useSearchParams()` arrive already decoded once: decoding them again corrupts
anything containing `%`, `&` or `#`, which is why `labels` lost its
`decodeURIComponent` when it moved. `useSearchParams()` also requires a
`<Suspense>` boundary, which is why every detail page is a thin wrapper around
an inner component.
```

- [ ] **Step 5: Rileggere il proprio diff**

```bash
git diff docs/ PROGRESS.md README.md frontend/CLAUDE.md
```

Controllare che nessuna riga affermi che il bundle Tauri esiste — non esiste. Esistono due sotto-progetti su quattro.

- [ ] **Step 6: Commit**

```bash
git add docs/ PROGRESS.md README.md frontend/CLAUDE.md
git commit -m "docs(frontend): due modi di build, una base URL, le rotte in query string"
```

---

## Verifica finale

- [ ] `cd frontend && npm run test:unit && npm run lint && npm run build` — tutto verde.
- [ ] `cd frontend && CRATORY_STATIC_EXPORT=1 npm run build` — produce `out/`.
- [ ] `cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q` — nessun fallimento nuovo.
- [ ] `npm run test:e2e` dalla cartella `frontend` — la suite Playwright non naviga verso le rotte dinamiche (verificato al momento della scrittura del piano), ma va eseguita per confermarlo.
- [ ] Con `npm run dev`, le cinque pagine di dettaglio si aprono e il link "indietro" torna alla lista giusta.
- [ ] `git status --porcelain` vuoto, e nessuna cartella `out/` o `.next/` committata per sbaglio.
