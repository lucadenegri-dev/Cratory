# Dashboard «Il Registro» — design

Data: 2026-08-15 · Stato: **superato** da
`2026-08-15-dashboard-cabina-statistiche-design.md` — implementato, visto
nell'app e rivisto in giornata: banco e colophon escono dalla dashboard.

## Obiettivo

Ripensare la prima pagina (`frontend/app/page.tsx`) perché sia insieme
esteticamente curata — il pezzo più bello del sistema "archivio editoriale",
senza evolverlo né derogarvi — e utile come pannello di controllo. Le tre
domande a cui la pagina risponde, in ordine di peso: *dove ero rimasto?*,
*cosa richiede attenzione?*, *com'è messa la libreria?* Lo stato tecnico dei
servizi resta fuori (vive in Settings).

Decisioni emerse in brainstorming:

- Si tengono la striscia pipeline e le quattro misure hero; le tre colonne
  attuali (forma libreria / attività recente / catalogo) spariscono in quella
  forma.
- Set e playlist recenti escono dalla dashboard.
- Il ritratto della libreria resta ma compresso in forma di colophon.
- La pagina è "viva sulle code": polling leggero solo dove le cose si
  muovono, il resto è un'istantanea.

## Struttura della pagina

Ordine verticale: **frontespizio → striscia pipeline → banco → colophon**.
Stati globali invariati rispetto a oggi: `Alert` danger in testa se il
backend non risponde, `Loading` durante il primo caricamento, empty state
attuale se `total_tracks === 0` (in quel caso frontespizio, banco e colophon
non si mostrano).

### 1 · Frontespizio

Le quattro misure attuali (`Figure`) diventano un'apertura tipografica da
catalogo stampato: quattro celle su un'unica riga divise da filetti 1px
(griglia hairline nuda, nessuna card), etichetta maiuscola tracciata `10px`
sopra, cifra grande — `text-4xl`/`text-5xl`, tabulare, `fg-strong` — sotto.
Le misure restano: **scoperte / possedute (con % in `muted`) / playlist /
set**. Sotto `sm` la riga diventa griglia 2×2.

La **striscia pipeline** (`PipelineStrip`) resta subito sotto, invariata.

### 2 · Il banco («Lavoro aperto»)

La sezione nuova e centrale. Titolo di sezione `LAVORO APERTO`; sotto, un
blocco a righe da registro dentro filetti orizzontali, ogni riga numerata
`01`, `02`, … in `faint`. Una riga compare **solo se ha contenuto** (stessa
scelta già fatta per i gaps: niente segnaposto). Le righe possibili, in
quest'ordine:

1. **Download in corso** — visibile se `downloadStatus().status === "running"`.
   `EqMeter` con progresso reale (`processed`/`total`) e la traccia in
   lavorazione (`current_label`) accanto in `muted`. La riga intera linka a
   `/wishlist`.
2. **Da rivedere** — visibile se `needs_review > 0` (da `downloadStatus`) o
   se `downloadPending()` restituisce elementi. Conteggio in `fg-strong` +
   i primi 2–3 titoli in attesa, troncati. Linka a `/wishlist`.
3. **Inbox Organize** — visibile se `pipeline.inbox_files > 0`. Conteggio
   file da sistemare. Linka a `/organize/files`.
4. **Ultimi leads** — visibile se esistono tracce non possedute; le 5 più
   recenti via `GET /api/tracks?sort=added_at&order=desc&has_local_file=false&limit=5`:
   artista — titolo, fonte come `Badge` neutro, data (`fmtDate`). Linka a
   `/library` (riga di testata) e alla traccia (`/tracks/{id}`) le singole voci.

Se nessuna riga ha contenuto, il banco non sparisce: una sola riga quieta in
`muted`, «Nessun lavoro aperto», dentro un filetto **tratteggiato** (la
grammatica "provvisoria" del sistema).

**Polling.** Solo `downloadStatus` e `getPipeline`, ogni ~5s, attivo solo
finché `status === "running"` o `pipeline.download_active`; quando la coda si
ferma il polling si ferma. Le cifre del frontespizio non si aggiornano mai
dopo il primo caricamento (niente sfarfallio). Cleanup del timer allo
smontaggio.

### 3 · Il colophon

In fondo, un unico blocco compatto chiuso tra due filetti orizzontali — righe
tipografiche, non grafici a colonne. Una riga per voce, etichetta maiuscola
`10px` a sinistra, contenuto in linea, ellissi se stretta:

- `BPM` — range `bpm_min–bpm_max` + l'istogramma ridotto a **sparkline
  inline**: barrette alte ~14px in `faint`, la classe modale in `fg`.
  Realizzata come variante compatta di `Histogram` (prop dedicata), così la
  logica dei bin resta in un posto solo.
- `TONALITÀ` — le prime 5 chiavi per frequenza (`key_distribution`),
  conteggio in `muted`.
- `GENERI` — primi 4 (`genre_distribution`), ognuno link a
  `/library?genre=…`, conteggio in `muted`.
- `LABEL` — prime 3 (`getLabels()`), link a `/labels/…`.

Sotto `sm` le righe vanno a capo naturalmente.

## Dati e API

Nessuna modifica backend. Tutto esiste già:

| Dato | Fonte |
|---|---|
| Misure hero | `GET /api/stats` (`LibraryStats`) |
| Pipeline | `getPipeline()` (`PipelineStatus`) |
| Download vivo | `downloadStatus()` (`DownloadStatus.current_label`, `processed`, `total`, `needs_review`) |
| Coda revisione | `downloadPending()` |
| Inbox | `PipelineStatus.inbox_files` |
| Ultimi leads | `GET /api/tracks?sort=added_at&order=desc&has_local_file=false&limit=5` |
| Colophon | `LibraryStats` (histogram, key/genre distribution) + `getLabels()` |

Il conteggio set (`/api/sets`) serve solo alla quarta cifra del frontespizio.
Il client tracce non espone ancora una `listTracks` generica: se ne aggiunge
una minima in `frontend/lib/api/tracks.ts` (o si usa `apiGet` direttamente,
come fa la pagina Library).

## Componenti

- Nessun componente nuovo nel design system: `EqMeter`, `Badge`, `Alert`,
  `Loading`, filetti e tipografia esistenti.
- `Figure` si adatta (o si sostituisce con markup locale) per le cifre grandi.
- `mini-bars.tsx` e `recent-list.tsx` restano nel repo finché altri consumer
  esistono; se la dashboard era l'unico consumer, si rimuovono nella
  implementazione (verificare con grep).
- i18n: tutte le stringhe nuove in `en.ts` e `it.ts`; si rimuovono le chiavi
  `dashboard.*` orfane.

## Vincoli

- **Design system al massimo, non oltre**: monospace, monocromo, filetti 1px,
  geometria quadrata, `tnum` su ogni cifra. Nessun colore nuovo, nessuna
  ombra, nessun raggio.
- **Non toccare gli hunk della sessione parallela** già nel working tree
  (nav riordinata, rimozione gaps): l'implementazione parte dallo stato
  attuale di `page.tsx` e committa solo i propri file.
- La striscia pipeline non si modifica.
- Entrambi i temi (dark e paper) devono leggere correttamente.

## Test

- Aggiornare/estendere i test frontend esistenti che toccano la dashboard.
- Nuovi test per: visibilità condizionale delle righe del banco (nessun
  segnaposto), stato «Nessun lavoro aperto», spegnimento del polling quando
  la coda è ferma, sparkline con istogramma vuoto.
- Verifica visiva su entrambi i temi e sotto `sm`.
