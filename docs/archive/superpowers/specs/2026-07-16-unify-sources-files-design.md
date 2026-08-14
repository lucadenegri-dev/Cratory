# Unificazione Sources + Files, con auto-scan post-Apply

**Data:** 2026-07-16
**Stato:** design approvato, in attesa di piano

## Obiettivo

Ridurre l'ingombro della navigazione fondendo le due schede **Sources** e
**Files** in un'unica voce **Files**. Le sorgenti (cartelle-radice: aggiungi /
scansiona / elimina) diventano una **tendina** in cima alla pagina Files, che
serve contemporaneamente da *gestore* delle sorgenti e da *filtro* per
sorgente. In aggiunta: dopo un Apply andato a buon fine, la libreria viene
**ri-scansionata automaticamente** così da riflettere subito i file
spostati/rinominati.

Spinta principale (da brainstorming): **declutter** del menu (7 → 6 voci).
Sources e Files sono due facce della stessa cosa — le sorgenti producono i
file — e la pagina Files ha già oggi un selettore "sorgente" come primo filtro.

## Stato attuale (cosa cambia)

- `frontend/app/sources/page.tsx` — gestione radici: `AddSource`,
  `SourcesTable` (lista con scan/elimina per riga), marginalia = risultato
  ultimo scan (found/new/updated/moved/missing/errors).
- `frontend/app/files/page.tsx` — navigazione libreria: filtri (selettore
  root, toggle issues, sort, ricerca) + facet (genre/artist/album/label/ext/
  year), `FilesTable`, marginalia = stat libreria.
- `frontend/components/index-nav.tsx` — `NAV` con 7 voci, incluse
  `/sources` e `/files`.
- Backend: `startScan(rootIds?: number[])` → `POST /api/scan` con
  `root_ids` — **supporta già lo scan di sorgenti specifiche**. Nessuna
  modifica backend necessaria.

## Feature 1 — Pagina Files unificata

### 1.1 Identità & navigazione

- Il menu passa da **7 a 6 voci**: sparisce `Sources`, resta `Files`.
- `frontend/app/sources/page.tsx` diventa un **redirect** a `/files`
  (client redirect, così i vecchi link/bookmark continuano a funzionare).
- Contatore nav di `Files` = `files_total` (invariato). Il conteggio "n°
  sorgenti" si legge dentro la tendina.

### 1.2 Barra in cima (sempre visibile)

Una riga sopra la tabella file:

```
[ ▾ All sources · 2 ]  [ Scan ]   [issues ▾] [sort ▾]  [ search… ]
```

- **Tendina sorgente** (`SourceMenu`): chiusa mostra la sorgente attiva
  (`▾ All sources · N` oppure `▾ Downloads`). È insieme filtro e gestore.
- **Scan**: bottone **sempre visibile**, accanto alla tendina. Etichetta
  adattiva:
  - nessuna sorgente selezionata → `Scan all` → `startScan()` (tutte).
  - sorgente X selezionata → `Scan <label>` → `startScan([X.id])`.
- A seguire i filtri File esistenti (issues / sort / ricerca), invariati.
- Sotto, la riga dei **facet** (genre·artist·album·label·ext·year),
  invariata.

### 1.3 La tendina aperta (`SourceMenu`)

Pannello disclosure che scende dalla tendina sorgente:

```
┌─────────────────────────────────┐
│ ○ All sources              1.2k │
│ ● Downloads      617   ⟳  🗑   │
│ ○ Library        580   ⟳  🗑   │
│ ─────────────────────────────── │
│ + Add source  [ path…      ] →  │
└─────────────────────────────────┘
```

Interazione:

- **Click sul corpo riga** = seleziona quella sorgente come filtro dei file
  **e chiude** la tendina. La selezione guida `FileQuery.root_id`.
- **`○ All sources`** = azzera il filtro sorgente (root_id = undefined),
  chiude.
- **⟳ (scan riga)** = `startScan([root.id])`, **non chiude** la tendina.
- **🗑 (elimina)** = `deleteSource(root.id)`, **non chiude**; con la stessa
  guardia `deletingId` di oggi (una sola eliminazione alla volta).
- **Add source** in fondo = componente `AddSource` esistente, riusato.
- La riga della sorgente attiva è evidenziata; ogni riga mostra `count` +
  `last_scanned` (dati da `ScanRoot`, come `SourcesTable` oggi).

Comportamento chiusura: click fuori dalla tendina la chiude (senza applicare
selezioni). La tendina parte **chiusa** (scan è comunque raggiungibile dal
bottone sempre visibile).

### 1.4 Contorno

- **Marginalia** destra: restano le **stat libreria** di Files (files, issues
  per severità, dup groups, formati) — invariata (`Marginalia` di files/page).
- **Risultato ultimo scan** (found/new/updated/moved/missing/errors): oggi
  era la marginalia di Sources. Diventa una **striscia compatta** che appare
  **sotto la barra in cima** quando c'è un `scan.result` disponibile
  (`useJobs().scan.result`), riusando le stesse righe (`Row k/v`). La
  progress-bar dei job resta invariata.
- **Guida**: fusione delle due guide esistenti — prima le frasi Sources
  (aggiungi cartelle + `scan`), poi le frasi Files (naviga + filtra).
- **Empty state**: se non ci sono file, messaggio "Aggiungi una sorgente e
  scansiona"; la tendina (con Add source) resta raggiungibile in cima.

### 1.5 Struttura codice

- **Nuovo componente** `frontend/components/source-menu.tsx` (`SourceMenu`):
  incapsula elenco radici + selezione + scan/elimina per riga + `AddSource`.
  Props: `roots`, `selectedId`, `onSelect(id | null)`, `onScanRoot(id)`,
  `onDelete(id)`, `onAdded()`, `deletingId`. Riusa il markup di riga oggi in
  `SourcesTable`.
- **`frontend/app/files/page.tsx`** diventa l'host: aggiunge lo stato radici
  (`listSources`, `deleteSource`) preso oggi da `sources/page.tsx`, oltre allo
  stato file/filtri che già ha. Il selettore root attuale (`<Select>` "All
  roots") è **sostituito** dalla tendina `SourceMenu`.
- **`frontend/app/sources/page.tsx`** → redirect a `/files`
  (`useRouter().replace("/files")` o `redirect`).
- **`frontend/components/sources-table.tsx`** → si ritira: markup assorbito
  da `SourceMenu`. (Rimosso quando non più referenziato.)
- **`frontend/components/index-nav.tsx`** → rimuovere la voce `/sources`
  da `NAV`; rimuovere `/sources` da `counts`. Il link logo può puntare a
  `/files` invece di `/sources`.
- **i18n**: le chiavi `t.sources.*` che restano usate (add source, scan
  labels, stat*, guide) vengono riusate; nuove chiavi solo se servono
  (es. etichetta `Scan all` / `Scan <label>`). Aggiungere prima a `en.ts`,
  poi tradurre in `it.ts`.

## Feature 2 — Auto-scan dopo Apply

Comportamento **globale** (non legato alla pagina Files): vive in
`frontend/components/jobs-provider.tsx`.

- Quando `apply.status` transisce a `"done"` **e** `apply.result.applied_ops
  > 0`, avviare automaticamente `startScan()` (tutte le sorgenti), così la
  libreria riflette i file spostati/rinominati.
- **Guardia sul fronte di salita**: usare un `ref` che ricorda l'ultimo
  `apply.finished_at` (o la transizione running→done) già gestito, per non
  ri-lanciare lo scan a ogni poll mentre lo stato resta `"done"`.
- **Guardia ops > 0**: su un apply no-op (nessuna operazione applicata) non
  si scansiona.
- La progress-bar dei job mostra prima l'apply, poi lo scan, in sequenza
  (meccanica invariata; è solo un nuovo trigger di `startScan`).
- Nessun setting/toggle (YAGNI): sempre attivo. Eventuale opzione in Settings
  è un follow-up futuro, fuori scope.

## Fuori scope

- Modifiche backend (non servono: `root_ids` già supportato).
- Toggle/impostazione per disattivare l'auto-scan.
- Ridisegno dei facet o della `FilesTable`.

## Test

- **Frontend**: verifica manuale in preview del flusso — apri tendina,
  seleziona sorgente (filtra), scan globale vs per-riga, elimina, add source,
  redirect `/sources`→`/files`, striscia risultato-scan. Screenshot di prova.
- **Backend**: `backend/.venv/bin/python -m pytest backend/tests -q` deve
  restare verde (nessuna modifica backend, ma la suite fa da regressione).
- Auto-scan: dopo un Apply con ops>0, lo scan parte da solo una volta sola;
  con ops=0 non parte.
