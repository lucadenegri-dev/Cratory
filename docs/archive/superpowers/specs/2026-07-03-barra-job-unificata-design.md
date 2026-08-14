# Design: barra job unificata (GlobalProgress)

Data: 2026-07-03
Stato: approvato

## Obiettivo

Uniformare tutti gli stati di avanzamento delle operazioni lunghe sulla barra DJ
fissa in basso (`GlobalProgress` in `frontend/components/jobs-provider.tsx`) e
migliorarla esteticamente. Oggi la barra copre solo enrichment, Shazam e due
client job indeterminati; download Soulseek e indicizzazione libreria hanno
polling e UI propri, isolati.

## Perimetro

Nella barra passano solo le **operazioni lunghe**:

- Download Soulseek (batch playlist e retry pending)
- Arricchimento feature
- Identificazione mix (Shazam)
- Crate digging (DIG, Discovery)
- Backfill etichette (Labels)
- Indicizzazione libreria (Settings)

Restano fuori, invariati:

- Caricamenti di pagina -> componente `Loading`
- Azioni puntuali e ricerche brevi (ricerca Soulseek manuale, alternative set,
  sync playlist, delete, ecc.) -> spinner locale nel bottone o `Loading` inline

Tre layer chiari: barra = job in background, `Loading` = pagina che carica,
spinner = azione istantanea.

## Architettura: frontend unificato

`JobsProvider` diventa l'unico poller (2000ms) e fonte unica di verita'.
Nessun nuovo endpoint aggregato: si interrogano i 4 endpoint di stato esistenti.

### Tipo Job esteso

```ts
type Job = {
  key: string;
  label: string;        // uppercase nella UI
  detail?: string;      // riga secondaria ellissata (traccia corrente, fase, ...)
  processed: number;
  total: number;
  indeterminate?: boolean;
  href?: string;        // click sulla riga -> navigazione
};
```

### Job da polling backend

| Key | Endpoint | Label | Detail | Href |
|---|---|---|---|---|
| `download` | `/api/downloads/status` | Download Soulseek | `current_label` (nuovo campo) | `/downloads` |
| `enrich` | `/api/enrichment/features/status` | Arricchimento feature | — | `/settings` |
| `shazam` | `/api/shazam/identify-status` | `phase` ?? Identificazione mix | fase corrente | `/shazam` |
| `library-index` | `/api/library/index/status` | Indicizzazione libreria | — | `/settings` |

Il provider espone via context anche gli stati raw (`download: DownloadStatus | null`,
`libraryIndex: LibraryIndexJob | null`) per le pagine che mostrano dettaglio
(downloads, settings), che cosi' non hanno piu' `setInterval` propri.

### Client job con progresso

API context estesa:

```ts
startClientJob(key, label)
updateClientJob(key, { processed?, total?, detail? })  // nuovo
endClientJob(key)
```

- DIG (Discovery): riporta conteggi del loop Discogs + detail (genere/etichetta).
- Backfill etichette: riporta artisti processati/totali.
- Se un client job non aggiorna mai i conteggi resta indeterminato (scan), come oggi.

### Fine job visibile

Quando un job polled passa da `running` a concluso, la riga resta ~4 secondi:

- Successo: waveform piena, testina a 100%, esito sintetico ("23/23 · completato").
  Per i download l'esito include i contatori ("X scaricate · Y da sistemare").
- Errore: esito in `danger`, riga cliccabile verso la pagina del job.

Implementazione: il provider confronta lo snapshot precedente; alla transizione
running->done/error tiene una riga transiente con `setTimeout` (cleanup su unmount).

## UI: direzione "Waveform raffinata"

`GlobalProgress` renderizza **righe impilate**, una per job, separate da hairline
(`border-border` interno); massimo 3 righe visibili, oltre compare "+N".

Ogni riga (contenitore `max-w-5xl` come oggi):

- Sinistra (larghezza fissa ~200px): label uppercase 10px tracking wide +
  detail 11px `text-faint` ellissato.
- Centro: `EqMeter` flessibile, altezza 24px.
- Destra: percentuale grande (15-16px, `.tnum`, `text-fg-strong`) con
  `processed/total` sotto in 10px `text-muted`. Indeterminato: "···".

Modifiche a `EqMeter` (`frontend/components/ui.tsx`):

- Coda "hot": le ~4 barre immediatamente prima della testina usano `--c-danger`
  (classe `eqm-hot`), il resto delle barre accese resta com'e'.
- Indeterminato: scan attuale invariato.

Comportamento e accessibilita':

- Riga intera cliccabile (`Link`) verso `href`; focus visibile.
- `prefers-reduced-motion: reduce` disattiva `eqmBreathe` e `eqmScan` nei CSS.
- Il provider imposta un padding-bottom dinamico sul contenuto (CSS var con
  l'altezza della barra) cosi' la barra non copre il fondo pagina.
- Ruoli ARIA come oggi (`progressbar`/`status` per riga).

Stile invariato rispetto al design system: monospace, hairline, no radius,
monocromo + solo `danger` come colore.

## Migrazioni pagine

- `frontend/app/downloads/page.tsx`: via il polling proprio (`setInterval`) e la
  `<Progress>` inline ridondante; lo stato arriva dal provider. Restano badge
  contatori, elenco esiti per traccia, sezione "Da sistemare", revisione manuale.
- `frontend/app/playlists/[id]/page.tsx`: "Scarica mancanti" non fa piu'
  `router.push("/downloads")`; avvia il download, chiama `refresh()` e si resta
  sulla playlist. La riga della barra porta a `/downloads`.
- `frontend/app/settings/page.tsx`: l'indicizzazione libreria legge dal provider
  (niente polling locale); il testo inline "In corso… X/Y" resta, alimentato dal
  provider.
- `frontend/app/discovery/page.tsx` e `frontend/app/labels/page.tsx`: passano a
  `updateClientJob` con conteggi reali.

## Backend (minimo)

Solo `/api/downloads/status` guadagna `current_label: string | null`: etichetta
"Artista — Titolo" della traccia in lavorazione, `null` a riposo. Il service dei
download la valorizza all'inizio della lavorazione di ogni traccia.

## Errori e edge case

- Backend offline: il poll fallisce in silenzio e la barra sparisce (come oggi).
- `total == 0` o sconosciuto: riga indeterminata.
- Piu' job conclusi insieme: ogni riga transiente ha il suo timer.
- Navigazione durante un job: il provider vive nello shell, nulla cambia.

## Verifica

- `npm run lint` e `npm run build` nel frontend.
- `python -m pytest tests` nel backend per il campo nuovo.
- Verifica visiva con dev server: download reale (barra, detail traccia, click,
  esito finale), enrichment + download simultanei (righe impilate), DIG con
  conteggi, reduced motion.
