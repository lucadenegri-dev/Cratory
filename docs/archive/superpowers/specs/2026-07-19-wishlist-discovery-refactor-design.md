# Design — Refactor Wishlist/Discovery → Dig

Data: 2026-07-19
Stato: approvato (brainstorming)

## Obiettivo

Quattro ritocchi richiesti dall'utente, tutti lato frontend (nessun backend),
route invariate:

1. Spostare la voce **Wishlist** nel gruppo "Discover" della sidebar.
2. Rinominare la voce/pagina **Discovery → "Dig"** (solo etichetta).
3. Portare la ricerca **Soulseek libera ("FreeDownload") in testa** alla pagina Wishlist.
4. Rimuovere **JunoDownload** dai buy-link della wishlist (negozio non più funzionante).

Fuori scope: backend, route, redirect `/downloads`→`/wishlist`, badge conteggio pending,
titolo della **sezione** "Discover"/"Scopri" (resta invariato).

## Modifiche

### 1. Wishlist nel gruppo "Discover"

`frontend/components/index-nav.tsx`, `navGroups(t)`:
- Rimuovere `{ href: "/wishlist", label: t.nav.downloads }` dal gruppo `groupCollect`.
- Aggiungerlo al gruppo `groupDiscover` **dopo Shazam**.
- Ordine risultante del gruppo: **Dig · Shazam · Wishlist**.
- Route `/wishlist` invariata. Il badge pending è legato a `href === "/wishlist"`,
  quindi funziona identico nel nuovo gruppo.

### 2. Rinomina "Discovery" → "Dig" (solo etichetta)

- `frontend/lib/i18n/en.ts` e `frontend/lib/i18n/it.ts`: valore `nav.discovery`
  `"Discovery"` → `"Dig"` (chiave i18n invariata; "Dig" in entrambe le lingue,
  è un termine).
- `frontend/app/discovery/page.tsx`: `PageLayout title="Discovery"` → `title="Dig"`.
- Route `/discovery`, link interni e titolo del gruppo "Discover"/"Scopri" invariati.

### 3. Ricerca FreeDownload (Soulseek libera) in testa

`frontend/app/wishlist/page.tsx`:
- Spostare la `<section>` "Ricerca Soulseek libera" (attualmente ultima) **in cima**,
  prima della sezione "Azioni di gruppo".
- Nessun cambio di logica. Resta collassabile e **collassata di default**
  (`slskOpen` iniziale `false` invariato): solo riposizionata.

### 4. Rimozione JunoDownload

- `frontend/lib/store-links.ts`: rimuovere `"juno"` dall'union `StoreKey` e la relativa
  entry dall'array `STORES`. Nuovo ordine: `bandcamp · beatport · discogs`.
- `frontend/components/wishlist-row.tsx`: nessuna modifica (consuma `STORES` in modo generico).
- `frontend/tests/store-links.test.ts`: aggiornare l'asserzione d'ordine a
  `["bandcamp","beatport","discogs"]`, rimuovere l'asserzione dell'URL Juno, aggiornare
  la descrizione da "4 negozi" a "3 negozi".
- `docs/ROADMAP.md`: aggiornare se elenca Juno tra gli store correnti (source of truth vivente).
- `PROGRESS.md`: aggiungere una nuova voce di diario per questa modifica (non riscrivere le voci passate).
- `docs/superpowers/specs/2026-07-19-wishlist-redesign-design.md` e il relativo plan:
  restano come record storico (non modificati).

## Verifica

- `cd frontend && npm run lint && npm run build`
- vitest su `store-links.test.ts` (ordine e URL aggiornati)
- Controllo visivo nel browser:
  - sidebar: gruppo "Discover" mostra **Dig · Shazam · Wishlist**; "Collect" senza Wishlist.
  - pagina `/discovery`: titolo "Dig".
  - pagina `/wishlist`: sezione ricerca Soulseek in cima (collassata); menu "Compra ▾"
    di una riga senza la voce "Juno Download".
