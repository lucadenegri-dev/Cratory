# Back-link alla pagina di provenienza + sync di tutte le playlist — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il link "indietro" delle pagine di dettaglio riporta alla pagina da cui si è
arrivati, e la pagina Playlist guadagna un bottone che sincronizza in blocco tutte le
playlist Spotify e SoundCloud (liked esclusi).

**Architecture:** Lato frontend un modulo `lib/back-link.ts` con logica pura (validazione
del param `from`, mappa rotta → etichetta di sezione) più un hook sottile; le pagine di
origine emettono `?from=<path+query>`, le pagine di dettaglio lo consumano con un
fallback. Lato backend un nuovo kind del job singleton `streaming_import_job`
(`playlists_sync_all`) che cicla le playlist sincronizzabili riusando i runner di sync
esistenti, prosegue dopo un fallimento e pubblica un report aggregato in un campo nuovo
dello stato del job.

**Tech Stack:** Next.js 16 (App Router, client components), React 19, TypeScript, vitest +
jsdom; FastAPI, SQLAlchemy, Pydantic, pytest.

## Global Constraints

- **Next.js 16 non è il Next che conosci**: prima di modificare pagine o routing leggi
  `frontend/CLAUDE.md` e le guide in `frontend/node_modules/next/dist/docs/`.
- **i18n sempre in coppia**: ogni stringa nuova va aggiunta sia in
  `frontend/lib/i18n/it.ts` sia in `frontend/lib/i18n/en.ts`, con le stesse chiavi.
- **Un solo job streaming alla volta**: il nuovo kind riusa lo slot singolo di
  `streaming_import_job`, nessun job parallelo.
- **I liked non si sincronizzano mai in blocco**: né Spotify Liked né SoundCloud Likes.
- **Il job di sync di massa chiude in `done` anche con fallimenti.** Gli errori delle
  singole playlist vivono in `sync_all.failures`, non nello stato `error` del job.
- **`from` è validato**: solo path interni (inizio `/`, secondo carattere diverso da `/` e
  da `\`) e solo rotte di sezione conosciute; qualsiasi altro valore vale come assente.
- **Commit message senza `Co-Authored-By`.**
- **Prima di ogni commit**: `git status --porcelain`, si stageano solo i file della task
  corrente (possono girare altre sessioni sullo stesso checkout).

## Comandi

Test backend (il worktree non ha un `.venv` proprio: si usa quello del checkout
principale, con cwd nella `backend/` del worktree):

```bash
cd backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

Test/lint/build frontend (dalla directory `frontend/`):

```bash
npm run test:unit
npm run lint
npm run build
```

---

### Task 1: Modulo `back-link` (logica pura + hook)

**Files:**
- Create: `frontend/lib/back-link.ts`
- Test: `frontend/tests/back-link.test.ts`

**Interfaces:**
- Consumes: `t.nav` da `@/lib/i18n` (chiavi `library`, `playlists`, `labels`, `sets`,
  `transitions`, `downloads`, `shazam`, tutte già esistenti in `it.ts` e `en.ts`).
- Produces:
  - `type SectionKey = "library" | "playlists" | "labels" | "sets" | "transitions" | "downloads" | "shazam"`
  - `type BackLink = { href: string; label: string }`
  - `type BackLinkFallback = { href: string; labelKey: SectionKey }`
  - `sectionOf(path: string): SectionKey | null`
  - `resolveBackLink(from: string | null, fallback: BackLinkFallback, labels: Record<SectionKey, string>): BackLink`
  - `useBackLink(fallback: BackLinkFallback): BackLink`
  - `withFrom(href: string, from: string): string`

- [ ] **Step 1: Installare le dipendenze del worktree (una volta sola)**

Il worktree non ha `frontend/node_modules` e un symlink romperebbe Turbopack: serve
un'installazione vera.

```bash
cd frontend
npm install
```

Atteso: termina senza errori, `frontend/node_modules` esiste.

- [ ] **Step 2: Scrivere il test che fallisce**

Crea `frontend/tests/back-link.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { resolveBackLink, sectionOf, withFrom, type BackLinkFallback, type SectionKey } from "@/lib/back-link";

const LABELS: Record<SectionKey, string> = {
  library: "Libreria",
  playlists: "Playlists",
  labels: "Etichette",
  sets: "Set",
  transitions: "Transizioni",
  downloads: "Wishlist",
  shazam: "Shazam",
};
const FALLBACK: BackLinkFallback = { href: "/library", labelKey: "library" };

describe("resolveBackLink", () => {
  it("senza `from` usa il fallback della pagina", () => {
    expect(resolveBackLink(null, FALLBACK, LABELS)).toEqual({ href: "/library", label: "Libreria" });
  });

  it("torna alla pagina di provenienza con l'etichetta della sua sezione", () => {
    expect(resolveBackLink("/playlists/7", FALLBACK, LABELS)).toEqual({
      href: "/playlists/7",
      label: "Playlists",
    });
  });

  it("conserva la query dell'origine: filtri e paginazione non si perdono", () => {
    const from = "/library?artist=Simon+%26+Garfunkel&offset=50";
    expect(resolveBackLink(from, FALLBACK, LABELS)).toEqual({ href: from, label: "Libreria" });
  });

  it("rifiuta un `from` che punta fuori dall'app", () => {
    for (const evil of ["//evil.com", "/\\evil.com", "https://evil.com", "evil.com", ""]) {
      expect(resolveBackLink(evil, FALLBACK, LABELS)).toEqual({ href: "/library", label: "Libreria" });
    }
  });

  it("rifiuta una rotta interna che non è una sezione nota", () => {
    expect(resolveBackLink("/settings", FALLBACK, LABELS)).toEqual({ href: "/library", label: "Libreria" });
  });
});

describe("sectionOf", () => {
  it("riconosce la sezione dal segmento di rotta, non da un prefisso parziale", () => {
    expect(sectionOf("/sets/12")).toBe("sets");
    expect(sectionOf("/sets")).toBe("sets");
    // /set-builder non è /sets: un match per prefisso nudo lo prenderebbe per errore.
    expect(sectionOf("/set-builder")).toBeNull();
  });

  it("ignora la query quando riconosce la sezione", () => {
    expect(sectionOf("/library?artist=A")).toBe("library");
  });
});

describe("withFrom", () => {
  it("codifica l'origine, query compresa", () => {
    expect(withFrom("/tracks/42", "/library?artist=A&offset=50")).toBe(
      "/tracks/42?from=%2Flibrary%3Fartist%3DA%26offset%3D50",
    );
  });
});
```

- [ ] **Step 3: Eseguire il test e verificare che fallisca**

Run: `cd frontend && npm run test:unit -- back-link`
Atteso: FAIL — `Failed to resolve import "@/lib/back-link"`.

- [ ] **Step 4: Scrivere l'implementazione**

Crea `frontend/lib/back-link.ts`:

```ts
"use client";

import { useSearchParams } from "next/navigation";

import { useT } from "@/lib/i18n";

/** Le sezioni a cui una pagina di dettaglio può appartenere: rotta -> chiave in t.nav. */
const SECTIONS = [
  ["/library", "library"],
  ["/playlists", "playlists"],
  ["/labels", "labels"],
  ["/sets", "sets"],
  ["/transitions", "transitions"],
  ["/wishlist", "downloads"],
  ["/shazam", "shazam"],
] as const;

export type SectionKey = (typeof SECTIONS)[number][1];
export type BackLink = { href: string; label: string };
/** Dove tornare quando `from` manca o non è valido (ingresso diretto, link condiviso). */
export type BackLinkFallback = { href: string; labelKey: SectionKey };

/** Un path interno e innocuo: niente URL assoluti, niente `//host` o `/\host`
 *  (che i browser trattano come protocol-relative, cioè come uscita dall'app). */
function isInternalPath(path: string): boolean {
  return path.startsWith("/") && path[1] !== "/" && path[1] !== "\\";
}

/** La sezione a cui appartiene un path interno, o null se non è una rotta nota.
 *  Il confronto è per segmento: "/set-builder" non è la sezione "/sets". */
export function sectionOf(path: string): SectionKey | null {
  const route = path.split("?")[0];
  for (const [prefix, key] of SECTIONS) {
    if (route === prefix || route.startsWith(`${prefix}/`)) return key;
  }
  return null;
}

/** Il link "indietro" di una pagina di dettaglio. `from` è il valore del param
 *  omonimo GIÀ decodificato una volta da useSearchParams: non ri-decodificarlo,
 *  altrimenti i valori con &, % o # si corrompono e i filtri ripristinati saltano.
 *  Pura di proposito: la logica si testa senza React. */
export function resolveBackLink(
  from: string | null,
  fallback: BackLinkFallback,
  labels: Record<SectionKey, string>,
): BackLink {
  const section = from && isInternalPath(from) ? sectionOf(from) : null;
  if (!from || !section) return { href: fallback.href, label: labels[fallback.labelKey] };
  return { href: from, label: labels[section] };
}

/** Versione hook di resolveBackLink: legge `from` dall'URL e le etichette da i18n. */
export function useBackLink(fallback: BackLinkFallback): BackLink {
  const t = useT();
  const searchParams = useSearchParams();
  return resolveBackLink(searchParams.get("from"), fallback, t.nav);
}

/** Appende `?from=<origine>` a un link verso una pagina di dettaglio.
 *  `href` non deve avere già una query (i link verso i dettagli non ne hanno). */
export function withFrom(href: string, from: string): string {
  return `${href}?from=${encodeURIComponent(from)}`;
}
```

- [ ] **Step 5: Eseguire il test e verificare che passi**

Run: `cd frontend && npm run test:unit -- back-link`
Atteso: PASS, 8 test.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add frontend/lib/back-link.ts frontend/tests/back-link.test.ts
git commit -m "feat(nav): modulo back-link con validazione del param from"
```

---

### Task 2: `/tracks/[id]` consuma il back-link, la libreria emette il nuovo formato

**Files:**
- Modify: `frontend/app/tracks/[id]/page.tsx:37-45,98`
- Modify: `frontend/app/library/page.tsx:98-100`

**Interfaces:**
- Consumes: `useBackLink` da Task 1.
- Produces: `/tracks/[id]` risponde a `?from=<path+query>`; `/library` emette
  `?from=/library?<filtri>` sui link verso il dettaglio traccia (il prop
  `trackLinkQuery` di `LibraryTrackGrid` resta un suffisso stringa: il componente
  non cambia).

- [ ] **Step 1: Sostituire la lettura manuale di `from` in `/tracks/[id]`**

In `frontend/app/tracks/[id]/page.tsx`, sostituisci il blocco alle righe 37-45:

```tsx
  // Il link "Torna alla libreria" porta con sé i filtri/sort/paginazione da cui si
  // proviene (param `from`, impostato da library/page.tsx sui link verso il
  // dettaglio), cosi' non si perde il filtro attivo tornando indietro (vedi B1).
  const searchParams = useSearchParams();
  // `from` è già decodificato una volta da useSearchParams: è la query string
  // pronta (es. "artist=Simon+%26+Garfunkel"). NON ri-decodificare, altrimenti
  // valori con &/%/# vengono corrotti e i filtri ripristinati saltano.
  const from = searchParams.get("from");
  const libraryHref = from ? `/library?${from}` : "/library";
```

con:

```tsx
  // Al dettaglio traccia si arriva da mezza app (libreria, playlist, etichette,
  // set, transizioni, wishlist, Shazam): il link indietro torna dove eri, filtri
  // compresi. Senza `from` (link diretto, refresh) ripiega sulla libreria.
  const back = useBackLink({ href: "/library", labelKey: "library" });
```

- [ ] **Step 2: Aggiornare import e link**

Nello stesso file, sostituisci la riga 5:

```tsx
import { useSearchParams } from "next/navigation";
```

con:

```tsx
import { useBackLink } from "@/lib/back-link";
```

e la riga 98:

```tsx
      <Link href={libraryHref} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {t.nav.library}</Link>
```

con:

```tsx
      <Link href={back.href} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {back.label}</Link>
```

Il `<Suspense>` che avvolge `TrackPageInner` (riga 200) resta: `useBackLink` usa
`useSearchParams`, che lo richiede.

- [ ] **Step 3: Emettere il nuovo formato dalla libreria**

In `frontend/app/library/page.tsx`, sostituisci le righe 98-100:

```tsx
  // Il suffisso da appendere ai link verso il dettaglio traccia: solo se c'e'
  // almeno un filtro/sort/offset attivo, altrimenti niente `from` nell'URL.
  const trackLinkQuery = queryString ? `?from=${encodeURIComponent(queryString)}` : "";
```

con:

```tsx
  // Suffisso `?from=` per i link verso il dettaglio traccia: porta con sé path +
  // filtri/sort/paginazione, così il link indietro là torna esattamente qui.
  // NB: si usa `queryString` (lo stato vivo) e non searchParams, che è indietro
  // di un debounce rispetto ai filtri appena toccati.
  const trackLinkQuery = `?from=${encodeURIComponent(queryString ? `${pathname}?${queryString}` : pathname)}`;
```

`pathname` è già in scope (dichiarato a riga 36).

- [ ] **Step 4: Verificare tipi e lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Atteso: nessun errore. In particolare nessun "useSearchParams is defined but never used"
in `app/tracks/[id]/page.tsx`.

- [ ] **Step 5: Commit**

```bash
git status --porcelain
git add frontend/app/tracks/\[id\]/page.tsx frontend/app/library/page.tsx
git commit -m "feat(nav): il dettaglio traccia torna alla pagina di provenienza"
```

---

### Task 3: Emettitori verso `/tracks/[id]` — etichette, set, transizioni

**Files:**
- Modify: `frontend/app/labels/[label]/page.tsx:106`
- Modify: `frontend/app/sets/[id]/page.tsx:387`
- Modify: `frontend/app/transitions/page.tsx:165`

**Interfaces:**
- Consumes: `withFrom` da Task 1; `usePathname` da `next/navigation`.
- Produces: i link verso `/tracks/[id]` da queste tre pagine portano `?from=<path corrente>`.

Queste pagine tengono ordinamento e paginazione nello stato del componente, non
nell'URL: basta il path, e `usePathname()` non richiede un boundary `<Suspense>`
(a differenza di `useSearchParams`).

- [ ] **Step 1: `/labels/[label]`**

In `frontend/app/labels/[label]/page.tsx` aggiungi l'import di `usePathname` e `withFrom`:

```tsx
import { usePathname } from "next/navigation";
import { withFrom } from "@/lib/back-link";
```

Dentro `LabelDetail`, subito dopo le altre dichiarazioni di stato, aggiungi:

```tsx
  // Origine per il link indietro del dettaglio traccia (es. "/labels/Hessle%20Audio").
  const from = usePathname();
```

e sostituisci la riga 106:

```tsx
                  <Link href={`/tracks/${tr.id}`} className="flex items-center gap-2.5">
```

con:

```tsx
                  <Link href={withFrom(`/tracks/${tr.id}`, from)} className="flex items-center gap-2.5">
```

- [ ] **Step 2: `/sets/[id]`**

In `frontend/app/sets/[id]/page.tsx` aggiungi gli stessi import (`usePathname` da
`next/navigation` — se il file importa già altro da lì, aggiungilo alla graffa
esistente — e `withFrom` da `@/lib/back-link`), dichiara dentro `SetDetail`:

```tsx
  const from = usePathname();
```

e sostituisci la riga 387:

```tsx
                    <Link href={`/tracks/${st.track.id}`} className="truncate font-medium hover:text-fg-strong">{trackLabel(st.track)}</Link>
```

con:

```tsx
                    <Link href={withFrom(`/tracks/${st.track.id}`, from)} className="truncate font-medium hover:text-fg-strong">{trackLabel(st.track)}</Link>
```

- [ ] **Step 3: `/transitions`**

In `frontend/app/transitions/page.tsx` aggiungi gli stessi import, dichiara dentro
`TransitionFinder`:

```tsx
  const from = usePathname();
```

e sostituisci la riga 165:

```tsx
                      <Link href={`/tracks/${track.id}`} className="min-w-0 flex-1 truncate font-medium hover:text-fg-strong">{trackLabel(track)}</Link>
```

con:

```tsx
                      <Link href={withFrom(`/tracks/${track.id}`, from)} className="min-w-0 flex-1 truncate font-medium hover:text-fg-strong">{trackLabel(track)}</Link>
```

- [ ] **Step 4: Verificare tipi e lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Atteso: nessun errore.

- [ ] **Step 5: Commit**

```bash
git status --porcelain
git add frontend/app/labels/\[label\]/page.tsx frontend/app/sets/\[id\]/page.tsx frontend/app/transitions/page.tsx
git commit -m "feat(nav): etichette, set e transizioni marcano l'origine dei link traccia"
```

---

### Task 4: Emettitori misti — wishlist e Shazam

**Files:**
- Modify: `frontend/components/wishlist-row.tsx:87,90`
- Modify: `frontend/app/shazam/[id]/page.tsx:30,142`
- Test: `frontend/tests/wishlist-row.test.tsx` (esistente: deve continuare a passare)

**Interfaces:**
- Consumes: `withFrom` da Task 1.
- Produces: i link verso `/tracks/[id]` e `/playlists/[id]` da wishlist e Shazam portano
  `?from=<path corrente>`.

- [ ] **Step 1: `wishlist-row.tsx`**

Aggiungi gli import:

```tsx
import { usePathname } from "next/navigation";
import { withFrom } from "@/lib/back-link";
```

Dentro il componente riga (quello che rende il `<li>`), prima del `return`, aggiungi:

```tsx
  // Origine per i link indietro di dettaglio traccia e dettaglio playlist.
  const from = usePathname();
```

Sostituisci la riga 87:

```tsx
        <a href={`/tracks/${track.id}`} className="block truncate hover:text-fg-strong">{trackLabel(track)}</a>
```

con:

```tsx
        <a href={withFrom(`/tracks/${track.id}`, from)} className="block truncate hover:text-fg-strong">{trackLabel(track)}</a>
```

e la riga 90:

```tsx
            <Link key={p.id} href={`/playlists/${p.id}`}
```

con:

```tsx
            <Link key={p.id} href={withFrom(`/playlists/${p.id}`, from)}
```

- [ ] **Step 2: `/shazam/[id]`**

Aggiungi gli stessi import. In `TrackLibraryAction` (il componente che rende il badge
"in libreria") aggiungi `const from = usePathname();` prima del `return`, e sostituisci
la riga 30:

```tsx
      <Link href={`/tracks/${track.library_track_id}`} title={t.shazam.detail.viewInLibraryTitle} className="shrink-0">
```

con:

```tsx
      <Link href={withFrom(`/tracks/${track.library_track_id}`, from)} title={t.shazam.detail.viewInLibraryTitle} className="shrink-0">
```

In `DjSetDetailPage` aggiungi `const from = usePathname();` accanto alle altre
dichiarazioni e sostituisci la riga 142:

```tsx
              <Link href={`/playlists/${importedPlaylistId}`} className="text-fg underline-offset-4 hover:underline">{t.shazam.detail.openLink}</Link>
```

con:

```tsx
              <Link href={withFrom(`/playlists/${importedPlaylistId}`, from)} className="text-fg underline-offset-4 hover:underline">{t.shazam.detail.openLink}</Link>
```

- [ ] **Step 3: Eseguire i test unit e verificare che passino**

Run: `cd frontend && npm run test:unit`
Atteso: PASS, compreso `tests/wishlist-row.test.tsx`. Se quel test asserisce un `href`
esatto verso `/tracks/...`, aggiornalo al valore con `?from=...` prodotto da `withFrom`
(in jsdom `usePathname()` va mockato o restituisce `/`: adegua l'asserzione al valore
effettivo, non aggirare il test).

- [ ] **Step 4: Verificare tipi e lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Atteso: nessun errore.

- [ ] **Step 5: Commit**

```bash
git status --porcelain
git add frontend/components/wishlist-row.tsx frontend/app/shazam/\[id\]/page.tsx frontend/tests/wishlist-row.test.tsx
git commit -m "feat(nav): wishlist e Shazam marcano l'origine dei link"
```

---

### Task 5: `/playlists/[id]` consuma il back-link

**Files:**
- Modify: `frontend/app/playlists/[id]/page.tsx:1-20,40,213,319,407`
- Modify: `frontend/app/playlists/page.tsx:111,123`

**Interfaces:**
- Consumes: `useBackLink`, `withFrom` da Task 1.
- Produces: `/playlists/[id]` risponde a `?from=`; i link dalla lista playlist e dal
  dettaglio playlist verso il dettaglio traccia portano l'origine.

- [ ] **Step 1: Avvolgere `/playlists/[id]` in un `<Suspense>`**

`useBackLink` usa `useSearchParams`, che in Next 16 richiede un boundary: senza, la build
fallisce. In `frontend/app/playlists/[id]/page.tsx` rinomina il componente esportato in
`PlaylistDetailInner` (riga 40):

```tsx
function PlaylistDetailInner({ params }: { params: Promise<{ id: string }> }) {
```

e aggiungi in fondo al file il wrapper esportato:

```tsx
export default function PlaylistDetail(props: { params: Promise<{ id: string }> }) {
  return <Suspense><PlaylistDetailInner {...props} /></Suspense>;
}
```

Aggiungi `Suspense` all'import di React (riga 4):

```tsx
import { Suspense, use, useCallback, useEffect, useMemo, useRef, useState } from "react";
```

- [ ] **Step 2: Usare il back-link e marcare i link traccia**

Aggiungi gli import:

```tsx
import { usePathname } from "next/navigation";
import { useBackLink, withFrom } from "@/lib/back-link";
```

(`useRouter` è già importato da `next/navigation`: aggiungi `usePathname` alla graffa
esistente.)

Dentro `PlaylistDetailInner`, accanto alle altre dichiarazioni:

```tsx
  // Alla playlist si arriva dalla lista, da Shazam e dalla wishlist: si torna
  // dove eri, non sempre all'elenco.
  const back = useBackLink({ href: "/playlists", labelKey: "playlists" });
  const from = usePathname();
```

Sostituisci **entrambi** i link indietro (righe 213 e 319, ramo errore e pagina piena):

```tsx
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {t.playlists.backLink}</Link>
```

con:

```tsx
      <Link href={back.href} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {back.label}</Link>
```

e la riga 407:

```tsx
                  <Link href={`/tracks/${tr.id}`} className="flex items-center gap-2.5">
```

con:

```tsx
                  <Link href={withFrom(`/tracks/${tr.id}`, from)} className="flex items-center gap-2.5">
```

- [ ] **Step 3: Marcare i link dalla lista playlist**

In `frontend/app/playlists/page.tsx` aggiungi gli import:

```tsx
import { usePathname } from "next/navigation";
import { withFrom } from "@/lib/back-link";
```

Dentro `PlaylistsPage`, accanto alle altre dichiarazioni:

```tsx
  const from = usePathname();
```

Sostituisci la riga 111:

```tsx
                    <Link href={`/playlists/${p.id}`} className="truncate font-medium hover:text-fg-strong">{p.name}</Link>
```

con:

```tsx
                    <Link href={withFrom(`/playlists/${p.id}`, from)} className="truncate font-medium hover:text-fg-strong">{p.name}</Link>
```

e la riga 123:

```tsx
                <ButtonLink href={`/playlists/${p.id}`} size="sm" variant="outline">
```

con:

```tsx
                <ButtonLink href={withFrom(`/playlists/${p.id}`, from)} size="sm" variant="outline">
```

- [ ] **Step 4: Verificare tipi, lint e build**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`
Atteso: build completata senza l'errore "useSearchParams() should be wrapped in a
suspense boundary".

- [ ] **Step 5: Commit**

```bash
git status --porcelain
git add frontend/app/playlists/\[id\]/page.tsx frontend/app/playlists/page.tsx
git commit -m "feat(nav): il dettaglio playlist torna alla pagina di provenienza"
```

---

### Task 6: Backend — schemi del report e selezione delle playlist sincronizzabili

**Files:**
- Modify: `backend/app/schemas.py:298-321`
- Modify: `backend/app/services/streaming_import_job.py:35-53,80-100`
- Test: `backend/tests/test_playlists_sync_all.py`

**Interfaces:**
- Consumes: `sync_error_for(playlist)` e `list_playlists(db)` esistenti.
- Produces:
  - `PlaylistSyncFailure(playlist_id: int, name: str, platform: str, error: str)`
  - `PlaylistsSyncAllReport(synced, failed, created, updated, removed, skipped, failures)`
  - `StreamingImportJobStatus.current_label: str | None`,
    `StreamingImportJobStatus.sync_all: PlaylistsSyncAllReport | None`
  - `streaming_import_job.syncable_playlists(db) -> list[Playlist]`

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/test_playlists_sync_all.py`:

```python
"""Sync di massa delle playlist: quali playlist entrano nel giro, prosecuzione
dopo un fallimento, short-circuit quando Spotify non è connesso, guardie del router."""

import pytest

from app.models import Playlist


def test_syncable_playlists_excludes_liked_and_manual(db):
    """Solo playlist vere Spotify/SoundCloud: i liked crescono per selezione
    manuale, le manuali non hanno una sorgente da cui riallinearsi."""
    from app.services.streaming_import_job import syncable_playlists

    db.add_all([
        Playlist(platform="spotify", name="PL", kind="playlist", platform_playlist_id="PL1"),
        Playlist(platform="spotify", name="Liked", kind="liked"),
        Playlist(platform="spotify", name="Senza id", kind="playlist"),
        Playlist(platform="soundcloud", name="SC", kind="playlist",
                 url="https://soundcloud.com/utente/set"),
        Playlist(platform="soundcloud", name="SC Likes", kind="liked"),
        Playlist(platform="soundcloud", name="SC senza url", kind="playlist"),
        Playlist(platform="manual", name="Manuale", kind="manual"),
    ])
    db.commit()

    assert sorted(p.name for p in syncable_playlists(db)) == ["PL", "SC"]
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run:

```bash
cd backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_playlists_sync_all.py -v
```

Atteso: FAIL con `ImportError: cannot import name 'syncable_playlists'`.

- [ ] **Step 3: Aggiungere gli schemi**

In `backend/app/schemas.py`, subito dopo `PlaylistImportReport` (riga 306), aggiungi:

```python
class PlaylistSyncFailure(BaseModel):
    """Una playlist che il sync di massa non è riuscito a riallineare."""

    playlist_id: int
    name: str
    platform: str
    error: str


class PlaylistsSyncAllReport(BaseModel):
    """Esito aggregato del sync di massa: i conteggi sono la somma sulle playlist
    riuscite, `failures` elenca quelle saltate con il motivo."""

    synced: int
    failed: int
    created: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    failures: list[PlaylistSyncFailure] = []
```

e nella classe `StreamingImportJobStatus` aggiungi i due campi dopo `result`:

```python
    result: PlaylistImportReport | None = None
    # Sync di massa: la playlist in corso col suo progresso interno ("Techno · 45/120").
    current_label: str | None = None
    # Valorizzato solo dal kind playlists_sync_all (per gli altri kind vale `result`).
    sync_all: PlaylistsSyncAllReport | None = None
```

- [ ] **Step 4: Aggiungere `syncable_playlists` e i campi di stato**

In `backend/app/services/streaming_import_job.py`:

Estendi l'import da `app.repositories` (riga 35):

```python
from app.repositories import get_playlist, list_playlists
```

Aggiungi al dict `_state` (dopo `"result": None,`):

```python
    "current_label": None,
    "sync_all": None,
```

Subito sotto `sync_error_for`, aggiungi:

```python
def syncable_playlists(db) -> list:
    """Le playlist riallineabili in blocco, nell'ordine di `list_playlists`.

    Esclude i liked di entrambe le piattaforme (crescono per selezione manuale,
    non per sync totale) e tutto ciò che `sync_error_for` già rifiuta: playlist
    manuali, Spotify senza `platform_playlist_id`, SoundCloud senza URL."""
    return [
        p for p in list_playlists(db)
        if p.kind != "liked" and sync_error_for(p) is None
    ]
```

- [ ] **Step 5: Eseguire il test e verificare che passi**

Run:

```bash
cd backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_playlists_sync_all.py -v
```

Atteso: PASS, 1 test.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add backend/app/schemas.py backend/app/services/streaming_import_job.py backend/tests/test_playlists_sync_all.py
git commit -m "feat(playlists): schemi e selezione per il sync di massa"
```

---

### Task 7: Backend — runner del sync di massa

**Files:**
- Modify: `backend/app/services/streaming_import_job.py:145-210,250-260,275-295`
- Test: `backend/tests/test_playlists_sync_all.py`

**Interfaces:**
- Consumes: `syncable_playlists` da Task 6.
- Produces: kind `"playlists_sync_all"` in `_RUNNERS`; `_run_soundcloud_sync(db, playlist,
  on_progress=_progress)` e `_run_spotify_sync(db, playlist, on_progress=_progress)`
  accettano il callback; a fine job `job_state()["sync_all"]` è il dict del report e
  `job_state()["result"]` resta `None`.

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungi in coda a `backend/tests/test_playlists_sync_all.py`:

```python
@pytest.fixture()
def sync_job(db, monkeypatch):
    """Job sincrono legato alla sessione del test (mirror di sync_job in
    test_playlist_sync.py): start_job(...) ritorna già lo stato finale."""
    from sqlalchemy.orm import sessionmaker

    from app.services import streaming_import_job as sij

    monkeypatch.setattr(sij, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(sij, "_spawn", lambda fn: fn())
    return sij


def _spotify_item(tid: str, *, name: str, artist: str, isrc: str) -> dict:
    return {
        "added_at": "2024-01-01T00:00:00Z",
        "track": {
            "id": tid, "type": "track", "name": name, "duration_ms": 200_000,
            "artists": [{"name": artist}],
            "album": {"name": "Album", "images": []},
            "external_ids": {"isrc": isrc},
            "external_urls": {"spotify": f"https://open.spotify.com/track/{tid}"},
        },
    }


class _FakeSpotify:
    """Client Spotify finto: `broken` elenca gli id di playlist che esplodono."""

    def __init__(self, items, broken=()):
        self._items = items
        self._broken = set(broken)

    def get_playlist_meta(self, playlist_id):
        from app.integrations.spotify import SpotifyError

        if playlist_id in self._broken:
            raise SpotifyError("playlist sparita")
        return {}

    def get_playlist_tracks(self, playlist_id):
        return self._items

    def get_liked_tracks(self):
        return self._items

    def close(self):
        pass


def test_sync_all_continues_after_a_failure(db, sync_job, monkeypatch):
    """Una playlist rotta non deve impedire il riallineamento delle altre."""
    db.add_all([
        Playlist(platform="spotify", name="Buona", kind="playlist", platform_playlist_id="OK1"),
        Playlist(platform="spotify", name="Rotta", kind="playlist", platform_playlist_id="KO1"),
    ])
    db.commit()

    fake = _FakeSpotify([_spotify_item("t1", name="One", artist="A", isrc="ISRC0000001")], broken={"KO1"})
    monkeypatch.setattr(sync_job, "SpotifyWebClient", lambda _db: fake)

    state = sync_job.start_job("playlists_sync_all")

    assert state["status"] == "done"  # i fallimenti non fanno fallire il job
    assert state["result"] is None
    report = state["sync_all"]
    assert report["synced"] == 1
    assert report["failed"] == 1
    assert report["created"] == 1
    assert [f["name"] for f in report["failures"]] == ["Rotta"]
    assert "playlist sparita" in report["failures"][0]["error"]
    assert report["failures"][0]["platform"] == "spotify"


def test_sync_all_short_circuits_when_spotify_is_disconnected(db, sync_job, monkeypatch):
    """Token assente: inutile ritentare playlist per playlist. Le SoundCloud
    proseguono comunque."""
    from app.integrations.spotify import SpotifyNotConnected

    db.add_all([
        Playlist(platform="spotify", name="S1", kind="playlist", platform_playlist_id="P1"),
        Playlist(platform="spotify", name="S2", kind="playlist", platform_playlist_id="P2"),
        Playlist(platform="soundcloud", name="SC", kind="playlist",
                 url="https://soundcloud.com/utente/set"),
    ])
    db.commit()

    calls = {"spotify": 0}

    def _boom(_db):
        calls["spotify"] += 1
        raise SpotifyNotConnected("Spotify non connesso")

    monkeypatch.setattr(sync_job, "SpotifyWebClient", _boom)
    monkeypatch.setattr(sync_job, "sc_fetch_playlist", lambda url: {
        "title": "SC", "uploader": "u", "thumbnails": [], "id": "SC1",
        "entries": [{
            "id": "sc1", "title": "Artist X - Cool Track", "uploader": "Artist X",
            "duration": 300, "webpage_url": "https://soundcloud.com/utente/track-1",
        }],
    })

    state = sync_job.start_job("playlists_sync_all")

    assert state["status"] == "done"
    report = state["sync_all"]
    assert calls["spotify"] == 1  # la seconda Spotify non ritenta la rete
    assert report["failed"] == 2
    assert report["synced"] == 1
    assert sorted(f["name"] for f in report["failures"]) == ["S1", "S2"]
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run:

```bash
cd backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_playlists_sync_all.py -v
```

Atteso: FAIL con `KeyError: 'playlists_sync_all'` in `_run`.

- [ ] **Step 3: Rendere iniettabile il progresso dei runner di sync**

In `backend/app/services/streaming_import_job.py`, cambia la firma di
`_run_soundcloud_sync`:

```python
def _run_soundcloud_sync(db, playlist, on_progress=_progress) -> dict:
```

e nella chiamata a `import_playlist` dentro quella funzione sostituisci
`on_progress=_progress` con `on_progress=on_progress`.

Fai lo stesso per `_run_spotify_sync`:

```python
def _run_spotify_sync(db, playlist, on_progress=_progress) -> dict:
```

con `on_progress=on_progress` nella chiamata a `import_playlist`.

Nessun altro chiamante cambia: `_run_playlist_sync` continua a chiamarle con il default.

- [ ] **Step 4: Scrivere il runner**

Subito dopo `_run_playlist_sync`, aggiungi:

```python
def _run_playlists_sync_all(db, params: dict) -> dict:
    """Riallinea tutte le playlist sincronizzabili, una alla volta.

    Una playlist che fallisce finisce in `failures` e il giro prosegue: su una
    sync di massa una playlist morta non deve invalidare le altre. La barra
    avanza sulle playlist; il progresso interno vive in `current_label`."""
    playlists = syncable_playlists(db)
    _state.update(total=len(playlists), processed=0)
    report: dict = {
        "synced": 0, "failed": 0,
        "created": 0, "updated": 0, "removed": 0, "skipped": 0,
        "failures": [],
    }
    # Credenziali Spotify assenti/scadute: vale per tutte le sue playlist, non ha
    # senso ripetere la stessa chiamata di rete una volta per playlist.
    spotify_dead: str | None = None

    for done, playlist in enumerate(playlists):
        _state.update(processed=done, phase="fetching", current_label=playlist.name)

        def on_progress(processed: int, total: int, name: str = playlist.name) -> None:
            _state["current_label"] = f"{name} · {processed}/{total}"

        try:
            if playlist.platform == "soundcloud":
                one = _run_soundcloud_sync(db, playlist, on_progress=on_progress)
            elif spotify_dead is not None:
                raise SpotifyNotConnected(spotify_dead)
            else:
                one = _run_spotify_sync(db, playlist, on_progress=on_progress)
        except Exception as exc:  # noqa: BLE001 — l'errore è dato di report, non un crash
            db.rollback()
            if isinstance(exc, (SpotifyNotConnected, SpotifyNotConfigured)) and spotify_dead is None:
                spotify_dead = str(exc)
            report["failed"] += 1
            report["failures"].append({
                "playlist_id": playlist.id, "name": playlist.name,
                "platform": playlist.platform, "error": str(exc),
            })
            logger.warning("Sync di massa: playlist '%s' fallita: %s", playlist.name, exc)
        else:
            report["synced"] += 1
            for key in ("created", "updated", "removed", "skipped"):
                report[key] += one.get(key, 0)

    _state.update(processed=len(playlists), current_label=None)
    return report
```

Registra il kind in `_RUNNERS`:

```python
    "playlist_sync": _run_playlist_sync,
    "playlists_sync_all": _run_playlists_sync_all,
```

- [ ] **Step 5: Pubblicare il report nel campo giusto**

In `_run`, il risultato del sync di massa non è un `PlaylistImportReport` e non può
finire in `result` (la response model lo rifiuterebbe). Sostituisci:

```python
        report = _RUNNERS[kind](db, params)
        _state.update(status="done", phase=None, result=report)
```

con:

```python
        report = _RUNNERS[kind](db, params)
        # Il sync di massa produce un aggregato, non il report di una playlist:
        # vive in un campo suo (`result` resta None per quel kind).
        key = "sync_all" if kind == "playlists_sync_all" else "result"
        _state.update(status="done", phase=None, current_label=None, **{key: report})
```

In `start_job`, azzera anche i campi nuovi:

```python
        _state.update(status="running", kind=kind, phase="fetching",
                      processed=0, total=0, result=None, sync_all=None,
                      current_label=None, error=None, error_code=None,
                      started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
```

- [ ] **Step 6: Eseguire i test e verificare che passino**

Run:

```bash
cd backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_playlists_sync_all.py tests/test_playlist_sync.py tests/test_streaming_import_job.py -v
```

Atteso: PASS su tutti — i test del sync singolo e del job devono restare verdi.

- [ ] **Step 7: Commit**

```bash
git status --porcelain
git add backend/app/services/streaming_import_job.py backend/tests/test_playlists_sync_all.py
git commit -m "feat(playlists): job di sync di massa che prosegue dopo i fallimenti"
```

---

### Task 8: Backend — endpoint `POST /api/playlists/sync-all`

**Files:**
- Modify: `backend/app/routers/playlists.py:150-167`
- Modify: `docs/API.md:115-144`
- Test: `backend/tests/test_playlists_sync_all.py`

**Interfaces:**
- Consumes: `syncable_playlists`, kind `playlists_sync_all` da Task 6-7.
- Produces: `POST /api/playlists/sync-all` → `202 StreamingImportJobStatus`;
  `409 no_syncable_playlists`; `409 streaming_import_already_running`.

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungi in coda a `backend/tests/test_playlists_sync_all.py`:

```python
def test_sync_all_endpoint_409_when_nothing_to_sync(db):
    """Solo liked e playlist manuali: non c'è nulla da riallineare."""
    from fastapi import HTTPException

    from app.routers import playlists as playlists_router

    db.add_all([
        Playlist(platform="spotify", name="Liked", kind="liked"),
        Playlist(platform="manual", name="Manuale", kind="manual"),
    ])
    db.commit()

    with pytest.raises(HTTPException) as exc:
        playlists_router.sync_all_playlists(db)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "no_syncable_playlists"


def test_sync_all_endpoint_409_when_a_job_is_running(db, sync_job):
    """Slot singolo: un import già in corso blocca il sync di massa."""
    from fastapi import HTTPException

    from app.routers import playlists as playlists_router

    db.add(Playlist(platform="spotify", name="PL", kind="playlist", platform_playlist_id="PL1"))
    db.commit()
    sync_job._state.update(status="running", kind="spotify_playlist")

    with pytest.raises(HTTPException) as exc:
        playlists_router.sync_all_playlists(db)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "streaming_import_already_running"
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run:

```bash
cd backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_playlists_sync_all.py -v
```

Atteso: FAIL con `AttributeError: module 'app.routers.playlists' has no attribute 'sync_all_playlists'`.

- [ ] **Step 3: Aggiungere l'endpoint**

In `backend/app/routers/playlists.py`, subito dopo `sync_playlist` (riga 162), aggiungi:

```python
@router.post("/sync-all", response_model=StreamingImportJobStatus, status_code=202)
def sync_all_playlists(db: Session = Depends(get_db)):
    """Avvia in background il riallineamento di TUTTE le playlist Spotify e
    SoundCloud importate; i liked sono esclusi (crescono per selezione manuale).
    Una playlist che fallisce non ferma le altre: l'elenco dei fallimenti è in
    `sync_all.failures` dello stato del job. Segui lo stato con
    GET /api/playlists/import/status."""
    if not streaming_import_job.syncable_playlists(db):
        raise api_error(
            409, "no_syncable_playlists",
            "No syncable playlists: only Spotify/SoundCloud playlists, liked excluded.",
        )
    _streaming_job_or_409()
    return streaming_import_job.start_job("playlists_sync_all")
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run:

```bash
cd backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_playlists_sync_all.py -v
```

Atteso: PASS, 5 test.

- [ ] **Step 5: Documentare l'endpoint**

In `docs/API.md`, nel blocco di rotte alla riga 119, aggiungi la riga dopo
`POST   /api/playlists/{playlist_id}/sync`:

```text
POST   /api/playlists/sync-all
```

e dopo il paragrafo che descrive `POST /api/playlists/{playlist_id}/sync` (finisce a
riga 144 con "provider errors surface in the job state") aggiungi:

```text
`POST /api/playlists/sync-all` (also `202` + the same status endpoint) realigns **every**
imported Spotify and SoundCloud playlist in one job; liked playlists are excluded on both
platforms (they grow through the selective flow). A playlist that fails does not stop the
others: the job still ends `done` and the aggregate report lands in `sync_all`
(`synced`, `failed`, summed `created`/`updated`/`removed`/`skipped`, plus `failures` with
name, platform and reason). While it runs, `current_label` carries the playlist in flight
with its own item progress, and `processed`/`total` count playlists, not tracks. Responds
`409 no_syncable_playlists` when there is nothing to realign.
```

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add backend/app/routers/playlists.py backend/tests/test_playlists_sync_all.py docs/API.md
git commit -m "feat(api): POST /api/playlists/sync-all"
```

---

### Task 9: Frontend — client API, tipi, i18n e barra job

**Files:**
- Modify: `frontend/lib/api/types.ts:56-64,359-368`
- Modify: `frontend/lib/api/playlists.ts:1-11,75-77`
- Modify: `frontend/lib/i18n/it.ts:84-101,451-490`
- Modify: `frontend/lib/i18n/en.ts:82-99` e sezione `playlists`
- Modify: `frontend/components/jobs-provider.tsx:188-196`

**Interfaces:**
- Consumes: la risposta di `POST /api/playlists/sync-all` da Task 8.
- Produces: `syncAllPlaylists(): Promise<StreamingImportJobStatus>`, i tipi
  `PlaylistSyncFailure` / `PlaylistsSyncAllReport`, e le chiavi i18n
  `t.jobs.syncAllSummary`, `t.playlists.syncAllButton`, `t.playlists.syncAllStarted`,
  `t.playlists.syncAllSummary`, `t.playlists.syncAllFailuresHeading`.

- [ ] **Step 1: Tipi**

In `frontend/lib/api/types.ts`, dopo `PlaylistImportReport` (riga 64), aggiungi:

```ts
export interface PlaylistSyncFailure {
  playlist_id: number;
  name: string;
  platform: string;
  error: string;
}

/** Esito aggregato del sync di massa (kind `playlists_sync_all`). */
export interface PlaylistsSyncAllReport {
  synced: number;
  failed: number;
  created: number;
  updated: number;
  removed: number;
  skipped: number;
  failures: PlaylistSyncFailure[];
}
```

e in `StreamingImportJobStatus` (riga 359) aggiungi i due campi dopo `result`:

```ts
  result: PlaylistImportReport | null;
  /** Sync di massa: playlist in corso col suo progresso interno. */
  current_label: string | null;
  /** Valorizzato solo dal sync di massa; per gli altri kind vale `result`. */
  sync_all: PlaylistsSyncAllReport | null;
```

- [ ] **Step 2: Funzione client**

In `frontend/lib/api/playlists.ts`, dopo `syncPlaylist` (riga 77), aggiungi:

```ts
/** Avvia in background il riallineamento di tutte le playlist Spotify e
 *  SoundCloud importate (liked esclusi). */
export function syncAllPlaylists() {
  return apiPost<StreamingImportJobStatus>("/api/playlists/sync-all");
}
```

- [ ] **Step 3: Stringhe i18n**

In `frontend/lib/i18n/it.ts`, dentro `jobs` (dopo `streamingImportSummary`, riga 93):

```ts
    syncAllSummary: (synced: number, failed: number) =>
      `${synced} sincronizzate${failed > 0 ? ` · ${failed} fallite` : ""}`,
```

e dentro `playlists` (dopo `syncSummary`, riga 485):

```ts
    syncAllButton: "Sincronizza tutte",
    syncAllStarted: "Sincronizzazione avviata: progresso nella barra in basso.",
    syncAllSummary: (synced: number, created: number, removed: number) =>
      `${synced} playlist sincronizzate · ${created} nuove · ${removed} rimosse (restano in libreria)`,
    syncAllFailuresHeading: (n: number) =>
      n === 1 ? "1 playlist non sincronizzata:" : `${n} playlist non sincronizzate:`,
```

In `frontend/lib/i18n/en.ts`, dentro `jobs` (dopo `streamingImportSummary`, riga 91):

```ts
    syncAllSummary: (synced: number, failed: number) =>
      `${synced} synced${failed > 0 ? ` · ${failed} failed` : ""}`,
```

e dentro `playlists`, nella stessa posizione relativa (dopo `syncSummary`):

```ts
    syncAllButton: "Sync all",
    syncAllStarted: "Sync started: progress in the bar below.",
    syncAllSummary: (synced: number, created: number, removed: number) =>
      `${synced} playlists synced · ${created} new · ${removed} removed (still in the library)`,
    syncAllFailuresHeading: (n: number) =>
      n === 1 ? "1 playlist not synced:" : `${n} playlists not synced:`,
```

- [ ] **Step 4: Barra job**

In `frontend/components/jobs-provider.tsx`, sostituisci il blocco `if (si.status === "fulfilled")`
(righe 188-196) con:

```tsx
    if (si.status === "fulfilled") {
      const v = si.value;
      if (alive.current) setStreamingImport(v);
      const phaseDetail = v.phase === "fetching" ? t.jobs.streamingImportPhaseFetching
        : v.phase === "importing" ? t.jobs.streamingImportPhaseImporting
        : undefined;
      track(v.status, {
        // Nel sync di massa `current_label` porta la playlist in corso col suo
        // progresso interno: più informativo della sola fase.
        key: "streaming-import", label: t.jobs.streamingImport, detail: v.current_label ?? phaseDetail,
        processed: v.processed, total: v.total, href: "/playlists",
      }, v.status === "error"
        ? (v.error ?? t.common.error)
        : v.sync_all ? t.jobs.syncAllSummary(v.sync_all.synced, v.sync_all.failed)
        : v.result ? t.jobs.streamingImportSummary(v.result.name, v.result.created)
        : t.jobs.completed);
    }
```

- [ ] **Step 5: Verificare tipi, lint e test**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run test:unit`
Atteso: nessun errore; `tests/jobs-provider.test.tsx` verde. Se quel test costruisce a
mano uno `StreamingImportJobStatus`, aggiungi ai suoi oggetti `current_label: null` e
`sync_all: null`.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add frontend/lib/api/types.ts frontend/lib/api/playlists.ts frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/components/jobs-provider.tsx frontend/tests/jobs-provider.test.tsx
git commit -m "feat(playlists): client e barra job per il sync di massa"
```

---

### Task 10: Frontend — bottone "Sincronizza tutte" e riepilogo

**Files:**
- Modify: `frontend/app/playlists/page.tsx:1-20,38-47,68-80,88-96`

**Interfaces:**
- Consumes: `syncAllPlaylists`, `PlaylistsSyncAllReport`, le chiavi i18n da Task 9.
- Produces: nessuna interfaccia per altre task (è la foglia della feature).

- [ ] **Step 1: Import**

In `frontend/app/playlists/page.tsx` estendi l'import da `lucide-react` con `RefreshCw`:

```tsx
import { Download, ClipboardList, Music2, Eye, Trash2, Calendar, CloudDownload, RefreshCw } from "lucide-react";
```

e quello da `@/lib/api`:

```tsx
import {
  listImportedPlaylists,
  deletePlaylist,
  syncAllPlaylists,
  errText,
  fmtDate,
  type Playlist,
  type PlaylistsSyncAllReport,
} from "@/lib/api";
```

- [ ] **Step 2: Stato e azione**

Dentro `PlaylistsPage`, accanto agli altri `useState`:

```tsx
  const [startingSyncAll, setStartingSyncAll] = useState(false);
  const [syncAllReport, setSyncAllReport] = useState<PlaylistsSyncAllReport | null>(null);
  const [syncAllError, setSyncAllError] = useState<string | null>(null);
  // Slot singolo lato backend: qualsiasi import/sync in corso blocca il bottone.
  const jobRunning = jobs.streamingImport?.status === "running";
```

e dopo `reload`:

```tsx
  const doSyncAll = async () => {
    setError(null);
    setNotice(null);
    setSyncAllReport(null);
    setSyncAllError(null);
    setStartingSyncAll(true);
    try {
      await syncAllPlaylists();
      setNotice(t.playlists.syncAllStarted);
    } catch (e) {
      setError(errText(e));
    } finally {
      setStartingSyncAll(false);
    }
  };
```

- [ ] **Step 3: Catturare l'esito a fine job**

Sostituisci l'effetto che ricarica su running → done (righe 38-47) con:

```tsx
  const prevStreamingImportStatus = useRef<string | null>(null);
  useEffect(() => {
    const status = jobs.streamingImport?.status ?? null;
    if (prevStreamingImportStatus.current === "running") {
      if (status === "done") {
        // Il riepilogo del sync di massa resta qui: la barra job svanisce dopo
        // pochi secondi e porterebbe via con sé l'elenco delle fallite.
        setSyncAllReport(jobs.streamingImport?.sync_all ?? null);
        reload();
      } else if (status === "error") {
        setSyncAllError(jobs.streamingImport?.error ?? null);
      }
    }
    prevStreamingImportStatus.current = status;
  }, [
    jobs.streamingImport?.status,
    jobs.streamingImport?.sync_all,
    jobs.streamingImport?.error,
    reload,
  ]);
```

- [ ] **Step 4: Bottone in marginalia**

Nella `marginalia`, come primo elemento dentro il `<div className="space-y-3">`:

```tsx
      <Button size="sm" variant="outline" className="w-full" onClick={doSyncAll} disabled={startingSyncAll || jobRunning}>
        {startingSyncAll ? <Spinner /> : <RefreshCw size={15} />} {t.playlists.syncAllButton}
      </Button>
```

- [ ] **Step 5: Riepilogo in cima alla lista**

Subito dopo il blocco `{notice && ...}` nel corpo della pagina, aggiungi:

```tsx
      {syncAllError && <div className="mb-4"><Alert tone="danger">⚠ {syncAllError}</Alert></div>}
      {syncAllReport && (
        <div className="mb-4">
          <Alert tone={syncAllReport.failed > 0 ? "warning" : "info"}>
            <p>{t.playlists.syncAllSummary(syncAllReport.synced, syncAllReport.created, syncAllReport.removed)}</p>
            {syncAllReport.failures.length > 0 && (
              <>
                <p className="mt-2 font-medium">{t.playlists.syncAllFailuresHeading(syncAllReport.failures.length)}</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
                  {syncAllReport.failures.map((f) => (
                    <li key={f.playlist_id}><span className="font-medium">{f.name}</span> — {f.error}</li>
                  ))}
                </ul>
              </>
            )}
          </Alert>
        </div>
      )}
```

- [ ] **Step 6: Verificare tipi, lint e build**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`
Atteso: nessun errore.

- [ ] **Step 7: Verifica manuale nel browser**

Avvia il backend (`cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m uvicorn app.main:app --reload --port 8000`)
e il dev server frontend tramite `preview_start`, poi apri `/playlists`:

1. il bottone "Sincronizza tutte" è visibile in cima alla colonna laterale;
2. cliccandolo compare la nota di avvio e la barra job mostra `n/N` con il nome della
   playlist in corso;
3. a fine job compare l'Alert col riepilogo e la lista si ricarica.

Cattura uno screenshot dell'Alert finale come prova.

- [ ] **Step 8: Commit**

```bash
git status --porcelain
git add frontend/app/playlists/page.tsx
git commit -m "feat(playlists): bottone Sincronizza tutte con riepilogo dei fallimenti"
```

---

### Task 11: Documentazione e verifica finale

**Files:**
- Modify: `PROGRESS.md`
- Modify: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: tutto il lavoro delle task precedenti.
- Produces: nessuna.

- [ ] **Step 1: Eseguire l'intera suite backend**

Run:

```bash
cd backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

Atteso: nessun fallimento. Se qualcosa si rompe, si corregge qui: non si documenta un
lavoro che non passa.

- [ ] **Step 2: Eseguire l'intera suite frontend**

Run: `cd frontend && npm run test:unit && npm run lint && npm run build`
Atteso: nessun fallimento.

- [ ] **Step 3: Aggiornare il diario**

In `PROGRESS.md` porta **Last updated** (riga 9) a `2026-07-21` e inserisci una milestone
nuova subito prima di `## Milestone 2026-07-20 - Set Builder: guida scopribile…`
(riga 33), completando i numeri con quelli osservati davvero:

```markdown
## Milestone 2026-07-21 - Ritorno alla pagina di provenienza + sync di tutte le playlist

Due interventi, brainstorming → spec → piano → esecuzione a task (spec in
`docs/superpowers/specs/`, piano in `docs/superpowers/plans/`, entrambi 2026-07-21).

- **Il link "indietro" non mente piu'**: al dettaglio traccia si arriva da mezza
  app, ma il ritorno buttava sempre in libreria. Ora ogni link verso un dettaglio
  porta `?from=<path+query>` e la pagina di dettaglio torna esattamente li',
  filtri e paginazione compresi, con l'etichetta della sezione di provenienza.
- Logica isolata e pura in `lib/back-link.ts` (`resolveBackLink`, `sectionOf`,
  `withFrom`): valida che `from` sia un path interno (niente `//host` o `/\host`)
  e che punti a una sezione nota, altrimenti ripiega sul default della pagina.
  Emettono l'origine libreria, etichette, set, transizioni, wishlist, Shazam e
  lista playlist; la consumano `/tracks/[id]` e `/playlists/[id]` (quest'ultima
  avvolta in `<Suspense>`, richiesto da `useSearchParams`).
- **"Sincronizza tutte" in Playlist**: nuovo kind `playlists_sync_all` del job
  singleton `streaming_import_job` (`POST /api/playlists/sync-all`) che riallinea
  tutte le playlist Spotify e SoundCloud; i liked restano esclusi (crescono per
  selezione manuale). Una playlist che fallisce non ferma le altre: finisce in
  `sync_all.failures` e il job chiude comunque `done`. Se Spotify non e'
  connesso le sue playlist falliscono subito senza altre chiamate di rete,
  le SoundCloud proseguono.
- La barra job avanza sulle playlist (`processed`/`total`) e mostra in
  `current_label` quella in corso col suo progresso interno; il riepilogo con
  l'elenco delle fallite resta in un Alert su `/playlists`, che la barra job
  — transitoria — non poteva ospitare.
- Test: unit su `resolveBackLink` (8) e pytest su selezione, prosecuzione dopo
  fallimento, short-circuit Spotify e le due guardie 409 del router.
```

- [ ] **Step 4: Aggiornare la roadmap**

In `docs/ROADMAP.md`, in coda alla sezione `## Current state`, aggiungi una frase in
inglese coerente col registro del file:

```markdown
**Detail pages now return where you came from** (2026-07-21): links into a detail page
carry a validated internal `?from=<path+query>`, so the back link restores the origin —
library filters included — instead of always falling back to the library. **Playlists
gained a bulk "Sync all"**: one background job realigns every Spotify and SoundCloud
playlist (liked excluded, they grow through the selective flow); a failing playlist is
reported and skipped, never fatal to the rest.
```

- [ ] **Step 5: Commit**

```bash
git status --porcelain
git add PROGRESS.md docs/ROADMAP.md
git commit -m "docs(progress): back-link alla provenienza e sync di massa delle playlist"
```

---

## Copertura della spec

| Requisito della spec | Task |
| --- | --- |
| `withFrom` / `resolveBackLink` / `useBackLink` in `lib/back-link.ts` | 1 |
| Validazione `from` interno + mappa rotta → etichetta | 1 |
| Test unit su `resolveBackLink` | 1 |
| `/tracks/[id]` consumer, `/library` nuovo formato | 2 |
| Emettitori verso `/tracks/[id]` | 2, 3, 4, 5 |
| `/playlists/[id]` consumer + emettitori verso `/playlists/[id]` | 4, 5 |
| Schemi `PlaylistSyncFailure` / `PlaylistsSyncAllReport`, campi `current_label` / `sync_all` | 6 |
| `syncable_playlists` (liked e manuali esclusi) | 6 |
| Runner con prosecuzione dopo fallimento e short-circuit Spotify | 7 |
| `on_progress` iniettabile nei runner di sync | 7 |
| Endpoint `POST /api/playlists/sync-all` + i due 409 | 8 |
| `docs/API.md` | 8 |
| Client API, tipi, i18n it/en, barra job | 9 |
| Bottone in marginalia + Alert persistente con le fallite | 10 |
| Test backend (selezione, continue-on-error, short-circuit, 409) | 6, 7, 8 |
