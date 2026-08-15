# Dashboard «La Cabina» + pagina Statistiche — design

Data: 2026-08-15 · Stato: approvato in chat · **Supera** la spec
`2026-08-15-dashboard-registro-design.md` (il Registro è stato implementato,
visto nell'app e rivisto: banco e colophon escono dalla dashboard).

## Obiettivo

La prima pagina si riduce all'essenziale e guadagna carattere: le due griglie
in alto (frontespizio a cifre grandi + striscia pipeline, invariate dal
Registro) e, sotto, un **DJ in ASCII art animato** — il pezzo su cui investire
di più: deve essere molto curato, non necessariamente fedele allo sketch
proposto dall'utente. Tutto il ritratto statistico della libreria migra in una
pagina dedicata **`/statistics`**, raggiunta da un link nella dashboard.

## Dashboard

Ordine verticale: link `STATISTICHE →` (right-aligned, sopra il frontespizio —
la pagina non ha header `PageLayout`, quindi niente slot `action`) →
frontespizio (4 `Figure big`) → striscia pipeline → `AsciiDj` centrato.

Spariscono: banco «Lavoro aperto», colophon, polling (la pagina torna
un'istantanea al primo caricamento). Restano identici: `Alert` d'errore,
`Loading`, empty state a libreria vuota (in quel caso niente DJ).

## AsciiDj

Un componente `frontend/components/dashboard/ascii-dj.tsx` in due strati:

1. **Core puro**: `djFrame(tick: number): string[]` — dato il numero di tick
   restituisce le righe del fotogramma. Completamente deterministico, quindi
   testabile: stesse dimensioni (righe × colonne) per ogni tick, fasi dei
   piatti cicliche, blink su schedule fisso, EQ con altezze limitate.
   Pseudo-casualità solo da LCG interno seedato dal tick (mai `Math.random`).
2. **Guscio React**: `AsciiDj` renderizza il fotogramma in `<pre>` monospace,
   avanza il tick con `setInterval` (~500ms, cleanup allo smontaggio) e con
   `prefers-reduced-motion` resta sul fotogramma 0 statico.

La scena (soggetta a raffinamento visivo in browser, che fa parte del lavoro):
DJ con cuffie dietro una console — due piatti che girano (marcatore che cicla
`| / - \`, fasi sfalsate), occhi che sbattono ogni pochi secondi, EQ del mixer
che pulsa, crossfader che scivola, note (`♪ ♫ ·`) che salgono e svaniscono
nell'aria sopra la scena.

Colori per zone (righe fisse → classi): aria in `text-faint`, corpo in
`text-muted`/`text-fg`, parti vive in `text-fg-strong`. Un solo accento: i
picchi dell'EQ del mixer in `danger`, citando la grammatica decorativa dei DJ
loader (`Equalizer`/`EqMeter`) già sancita dal design system — è l'unica
estensione, un carattere per volta, rimovibile con una classe.

## Pagina /statistics

Route `frontend/app/statistics/page.tsx` (thin: fetch + stati) sopra una vista
presentazionale testabile `frontend/components/statistics/statistics-view.tsx`
che riceve `stats: LibraryStats` e `labels: LabelStats[]`. Sezioni, in griglia
hairline a due colonne (sotto `sm` una colonna):

- **BPM** — `Histogram` pieno (interattivo, già esistente) + range min–max.
- **Tonalità** — distribuzione completa delle chiavi (`key_distribution`,
  tutte, ordinate per frequenza) in `MiniBars`.
- **Generi** — top 12 in `MiniBars`, link `/library?genre=…`.
- **Label** — top 10 in `MiniBars`, link `/labels/…` (da `getLabels()`).
- **Energia** — `energy_distribution` (che il backend già calcola e nessuno
  mostra) in `MiniBars`, etichette `from–to`.
- **Fonti** — `by_source` in `MiniBars` (spotify / soundcloud / manual /
  local_files).
- **Copertura** — con BPM, con tonalità, pronte per un set: `EqMeter` calmo
  con percentuale tabulare accanto (`with_bpm`, `with_key`, `ready_for_set`
  su `total_tracks`).

Una sezione senza dati si omette (grammatica consolidata: niente segnaposto).
Titolo pagina via `PageLayout` (`title` = chiave i18n `stats.title`).
Nessuna voce di nav: ci si arriva dal link in dashboard (aggiungerla è una
decisione futura).

## Pulizia del Registro

- Si rimuovono: `open-work.tsx`, `colophon.tsx`, i loro test, la variante
  `spark` di `Histogram` col suo test (nessun consumer superstite), le chiavi
  i18n `ow*` e `colophon*`.
- Restano: `Figure` con `big`, la rimozione delle tre colonne, la rimozione di
  set/playlist recenti, `mini-bars.tsx` (consumer: labels e ora statistiche).
- i18n nuove: sezione `stats.*` per la pagina statistiche; `dashboard.statsLink`
  per il link. Entrambe le lingue, sempre.

## Vincoli e test

Invariati dal Registro: design system al massimo (monospace, filetti, quadrato,
`tnum`), entrambi i temi, non toccare gli hunk della sessione parallela,
commit per path espliciti, nessun backend nuovo.

Test: core `djFrame` (dimensioni stabili su molti tick, ciclo piatti, blink,
determinismo), `StatisticsView` (sezioni presenti coi dati, omesse senza,
link corretti, percentuali copertura), suite completa + lint + tsc + build,
verifica visiva nei due temi e su mobile con iterazione estetica sul DJ.
