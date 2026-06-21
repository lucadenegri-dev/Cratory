# SetArc — Rebrand "Editorial Archive" · Design Spec

> Spec di design per il rebrand completo del frontend SetArc. Fonte di verità per
> il piano di implementazione (`writing-plans`). Stato: **approvato in
> brainstorming, in attesa review utente.**

## 1. Obiettivo

Sostituire integralmente l'identità visiva attuale ("studio-dark workbench",
accento lime, Geist, card arrotondate, badge colorati) con un'estetica
**editoriale/archivio** ispirata al moodboard Cargo.site: monospace ovunque,
griglia a filetti, geometria squadrata, quasi-monocromatica, densa e
text-forward. Massima fedeltà al moodboard. Nessun cambio di tecnologia.

## 2. Stack (invariato)

- **Next.js 16 / React 19 / Tailwind v4 / lucide-react.** Nessun cambio di
  framework: l'estetica è interamente questione di token, tipografia e layout.
- L'identità è centralizzata in: `app/globals.css` (token `@theme`),
  `app/layout.tsx` (shell + font), `components/sidebar.tsx`, `components/ui.tsx`,
  più `components/key-badge.tsx` e `components/track-edit-modal.tsx`.

## 3. Decisioni di design (vincolanti)

1. **Monocromatico puro.** Nessun colore funzionale: chiavi Camelot e stati del
   mix sono resi con testo, peso, posizione e filetti — mai con tinta.
2. **Un solo colore: il rosso `danger`.** Usato esclusivamente per errori e
   azioni distruttive (es. "elimina"). Successi/avvisi restano testo+peso+icona.
3. **Tema dark di default + toggle paper.** Persistito in `localStorage`, senza
   FOUC (script inline prima del paint).
4. **Font: IBM Plex Mono ovunque**, caricato via `next/font/google`, esposto come
   **singolo token swappable** `--font-ui` (per sostituire in futuro Monument
   Grotesk Mono con un solo file `.woff2` + un cambio di variabile). Geist rimosso.
5. **Geometria squadrata.** `--radius: 0`. Niente ombre (eccetto il dim del
   backdrop modale). Separatori = filetti da 1px.
6. **Icone minime ed editoriali.** Si mantiene lucide-react ma solo dove
   davvero necessario, monocromatico e sottile; altrove glifi testuali
   (`→`, `×`, `+`, `✓`, `!`).
7. **Layout bespoke per-pagina** secondo una **grammatica editoriale riusabile**
   (vedi §6), non un semplice restyling in-place.

## 4. Token colore (valori confermati)

Stessi **nomi** dei token attuali (le primitive continuano a funzionare), nuovi
valori, commutati a runtime via `data-theme` su `<html>`.

| Token              | Dark (default) | Paper (toggle) |
|--------------------|----------------|----------------|
| `--color-bg`         | `#0d0d0d`      | `#e9e5db`      |
| `--color-surface`    | `#161616`      | `#f1eee6`      |
| `--color-surface-2`  | `#1c1c1c`      | `#eae6dc`      |
| `--color-elevated`   | `#222222`      | `#e2ddd0`      |
| `--color-border`     | `#2b2b2b`      | `#cdc7b8`      |
| `--color-border-strong` | `#3d3d3d`   | `#b2ab99`      |
| `--color-muted`      | `#787878`      | `#86806f`      |
| `--color-faint`      | `#555555`      | `#a79f8d`      |
| `--color-fg`         | `#c4c4c4`      | `#2a2823`      |
| `--color-fg-strong`  | `#ededed`      | `#15140f`      |
| `--color-danger`     | `#d8593f`      | `#a83a22`      |

Token rimossi/rimappati:
- `--color-primary` / `primary-hover` / `primary-fg` → **ink**: il bottone
  primario diventa fill pieno `fg-strong` con testo invertito (`bg`). Non c'è
  più il lime.
- `--color-info` / `warning` / `success` → **eliminati**; ogni uso diventa
  `fg`/`muted`. La distinzione semantica passa a label maiuscole + icona + peso.
- Nuovo token `--color-fg-strong` (per titoli/numeri/wordmark).

Implementazione tema: i valori vivono su `:root` (dark) e
`html[data-theme="paper"]`. Il blocco `@theme` di Tailwind v4 mappa i nomi
utility (`bg-bg`, `text-fg`, …) alle variabili, così le utility esistenti
restano valide e il toggle funziona riassegnando le variabili.

## 5. Tipografia

- Famiglia unica: **IBM Plex Mono** (`400/500/600`) → `--font-ui`. `--font-mono`
  e `--font-sans` puntano entrambi a `--font-ui`.
- Scala (tutta monospace):
  - **brand** — wordmark `SETARC`, maiuscolo, `letter-spacing: 0.16em`.
  - **title** — titoli di pagina/sezione, `fg-strong`, `letter-spacing: -0.01em`.
  - **body** — prosa, `fg`, max ~46–60ch.
  - **label** — UPPERCASE, `letter-spacing: 0.12em`, `~9.5–10px`, `muted`. Per
    ogni intestazione di colonna/sezione e label di campo.
  - **data** — numerici (BPM, Camelot, energy, durata) con `font-variant-numeric: tabular-nums`.

## 6. Grammatica di layout editoriale

Sostituisce `Sidebar` + il `<main>` centrato di `layout.tsx`. Componente
**`EditorialShell`** a tutta altezza, tre colonne separate da filetti verticali,
ognuna con la propria intestazione maiuscola in alto (come le colonne del
moodboard: "PROFILE", "MATERIAL", "CV").

```
┌──────────────┬───────────────────────────┬──────────────────┐
│ INDEX        │ CONTENT                   │ MARGINALIA       │
│ SETARC       │ [TITOLO PAGINA] (conteggio)│ [HEADER CTX]     │
│ tagline      │                           │                  │
│ · Dashboard  │ contenuto primario:       │ stat, ultimo     │
│ · Playlist   │ liste con righe numerate  │ sync, note,      │
│ · Libreria   │ (01, 02…), tabelle a      │ azioni           │
│ · Etichette  │ filetti, form, dettaglio  │ secondarie       │
│ · Discovery  │                           │                  │
│ · Shazam     │                           │                  │
│ · Set        │                           │                  │
│ · Impostaz.  │                           │                  │
│              │                           │                  │
│ 14:57:29 ◑   │                           │                  │
└──────────────┴───────────────────────────┴──────────────────┘
```

- **INDEX** (sinistra, ~170px): header = wordmark `SETARC` + tagline
  "Workbench per DJ set". Nav: link maiuscoli; voce attiva **sottolineata**.
  Footer (in basso, echo del timestamp del moodboard): **orologio live**
  `HH:MM:SS` + **toggle tema** (glifo `◑`/testo `DARK·PAPER`).
- **CONTENT** (centro, flessibile): header = titolo pagina maiuscolo + conteggio.
  Corpo della pagina.
- **MARGINALIA** (destra, ~220px, opzionale per pagina): header contestuale +
  contenuto contestuale. Quando una pagina non la dichiara, la griglia diventa a
  2 colonne.
- Righe liste numerate `01, 02…` (tabular). Sezioni separate da filetti
  orizzontali. Nessun radius, nessuna ombra.

**Responsive** (breakpoint `lg` = 1024px esistente):
- `< lg`: INDEX collassa in una barra superiore (wordmark + nav orizzontale
  scrollabile + toggle); MARGINALIA scende **sotto** il contenuto come sezione a
  filetto. CONTENT a piena larghezza.
- `>= lg`: griglia a 3 colonne come sopra.

Nav (invariata rispetto a oggi): Dashboard `/`, Playlist `/playlists`, Libreria
`/library`, Etichette `/labels`, Discovery `/discovery`, Shazam `/shazam`, Set
`/sets`, Impostazioni `/settings`.

**Wordmark:** testo `SETARC` (no `logo.png`). Niente immagine logo nello shell.

## 7. Primitive (`components/ui.tsx`) — ridisegno

Stesse firme/props pubbliche (le pagine non cambiano API), nuovo look:

- **Button** — `radius 0`. `primary` = fill `fg-strong`, testo `bg`, hover
  inverte a outline; `outline` = trasparente + filetto `border-strong`; `ghost`
  = solo testo `muted`→`fg`; `danger` = testo/filetto `danger`. Label in
  maiuscolo con `letter-spacing`.
- **Card** — `bg surface`, filetto `border`, `radius 0`, nessuna ombra.
- **CardHeader** — titolo + filetto inferiore; sottotitolo `muted`.
- **Input / Select / Textarea** — squadrati, `bg`, filetto `border`, focus =
  filetto `fg`/`border-strong` (niente ring lime). `Select` mantiene la freccia
  testuale.
- **Field** — label UPPERCASE tracked sopra il campo.
- **Checkbox** — `accent-color: var(--color-fg)`.
- **Badge** — monocromatico: `bg elevated`, testo `muted`/`fg`, `radius 0`;
  varianti tone collassano su neutro (la sola eccezione `danger` usa il rosso).
- **Progress / bar interne** — track `elevated`, fill `fg` (no lime, no
  arrotondamento). Le barre della dashboard (`Coverage`, `KeyDistribution`,
  `LabelBars`) seguono la stessa regola.
- **Spinner** — bordo `border-strong` + top `fg`.
- **EmptyState** — riquadro a filetto tratteggiato, testo `muted`.
- **Modal** — pannello `surface` con filetto `border`, `radius 0`; backdrop
  `bg/70` **senza blur** (solo dim); chiusura con glifo `×`.
- **Alert** — varianti collassate a due: neutro (filetto `border`, testo `fg`) e
  `danger` (filetto/testo rosso). `warning`/`info`/`success` mappano su neutro.

**`KeyBadge`** — diventa monocromatico: mostra il valore Camelot (es. `8A`) in
`data`/`fg`; chiave assente = `—` in `faint`. Rimosso `CAMELOT_COLOR`.

**`track-edit-modal.tsx`** — solo restyle ai nuovi token/primitive.

## 8. Marginalia per pagina (contenuto colonna destra)

Sintesi dell'intento; il piano leggerà ogni pagina per i dettagli.

| Pagina | CONTENT (focus) | MARGINALIA (destra) |
|---|---|---|
| `/` Dashboard | Stat panoramica + azioni rapide + coverage | Distribuzione key, top etichette, alert enrichment |
| `/library` | Tabella tracce a filetti, numerata | Filtri (key/bpm/sorgente), conteggi, copertura feature |
| `/playlists` | Lista playlist numerata | Conteggi per sorgente, ultimo sync, azione import |
| `/playlists/[id]` | Tracklist a filetti | Meta playlist (sorgente, durata, bpm medio), azioni sync/elimina |
| `/playlists/import-spotify` | Form import (URL/ID) + stato | Passi/aiuto (note su scope dati Spotify) |
| `/playlists/import-manual` | Form inserimento manuale | Aiuto formato + anteprima conteggio |
| `/set-builder` | Area costruzione set (candidate + draft) | Vincoli/parametri, stato validazione |
| `/sets` | Lista set numerata | Conteggi, azione nuovo set |
| `/sets/[id]` | Tracklist set + transizioni | Meta set, note AI validate, azioni export/elimina |
| `/labels` | Lista etichette numerata | Totali, ordinamento |
| `/labels/[label]` | Tracce dell'etichetta | Statistiche etichetta |
| `/discovery` | Risultati discovery (ranking) | Filtri/sorgenti, spiegazione ranking |
| `/shazam` | Lista identificazioni | Stato job, aiuto |
| `/shazam/[id]` | Dettaglio tracklist identificata | Meta sorgente, confidenza |
| `/tracks/[id]` | Dettaglio traccia + feature | Enrichment source/confidence, azioni edit |
| `/transitions` | Tabella transizioni | Legenda criteri (testuale, monocromatica) |
| `/settings` | Form impostazioni | Aiuto/descrizioni campi |

Pagine senza marginalia significativa usano la colonna come aiuto/contesto o
collassano a 2 colonne.

## 9. Dettagli di chrome

- **Orologio live** in basso a INDEX: client component `HH:MM:SS` aggiornato al
  secondo (echo del `14:57:29` del moodboard). Degrada a statico se necessario.
- **Theme toggle**: pulsante testuale/`◑` accanto all'orologio; aggiorna
  `data-theme` e `localStorage["setarc-theme"]`.
- **No FOUC**: script inline in `<head>` che legge `localStorage` e imposta
  `data-theme` prima del primo paint.
- **Scrollbar** discreta come oggi, su token nuovi.

## 10. Testing & verifica

`frontend/` non ha framework di unit test. La verifica è:
1. `npm run lint` — zero errori.
2. `npm run build` — build pulita.
3. Verifica visiva nel dev server di **ogni pagina** in **entrambi i temi**
   (dark + paper), inclusi stati: vuoto, errore (rosso), modale.

## 11. Fuori scope

- Nessuna modifica al backend o alle API.
- Nessun cambio funzionale/comportamentale: solo presentazione.
- Nessun nuovo framework, libreria di componenti o sistema di build.
- Monument Grotesk Mono: predisposto (token swappable) ma non incluso (licenza).

## 12. Note di esecuzione (per il piano)

Fasatura suggerita: (A) **Fondamenta** — token+tema+font+toggle+no-FOUC; (B)
**Shell editoriale** — `EditorialShell`, INDEX, orologio; (C) **Primitive** —
`ui.tsx`, `key-badge`, `track-edit-modal`; (D) **Pagine** a batch secondo la
tabella §8. Ogni fase deve lasciare `lint`+`build` verdi.

I file `DESIGN.md` e `.impeccable/design.json` (radice repo) descrivono il
**vecchio** sistema lime e vanno rigenerati/aggiornati al nuovo sistema come
ultimo step (allineati ai token §4 e alle primitive §7).
