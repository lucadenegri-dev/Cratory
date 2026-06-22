# Dashboard "Command Center" — Design Spec

> Spec di design per il redo della pagina Dashboard di SetArc come command center
> editoriale. Fonte di verità per il piano di implementazione (`writing-plans`).
> Stato: **approvato in brainstorming, in attesa review utente.**

## 1. Obiettivo

Trasformare la dashboard nel **command center** dell'app: una broadsheet
editoriale densa che mostra a colpo d'occhio lo stato della libreria, la sua
forma (tempi/tonalità), l'attività recente e la prossima azione consigliata.
Estetica invariata: monocromatica, IBM Plex Mono, filetti, squadrato, cifre
tabellari, funzionante in dark e paper.

## 2. Layout (broadsheet, dall'alto in basso)

Dentro `PageLayout` (title `Dashboard`, meta `<n> tracce`), a piena larghezza,
griglia a filetti. **Niente colonna marginalia**: la dashboard usa l'intera
larghezza.

1. **Figure hero** — riga a 4 celle, numeri grandi tabellari:
   `Tracce`, `Pronte per il set`, `Playlist`, `Set salvati`.
2. **Prossimo passo** — la raccomandazione intelligente esistente
   (state-driven: completa BPM/key → sei pronto per un set → espandi la
   libreria) con la sua CTA primaria.
3. **Tre colonne** (filetti verticali, `lg:grid-cols-3`, stack < lg):
   - **Forma della libreria** — istogramma BPM + distribuzione tonalità Camelot
     (top 8, barre monocromatiche).
   - **Attività recente** — ultimi **4 set** (numerati, con data, link al
     dettaglio) + ultime **3 playlist** importate (numerate, con conteggio
     tracce, link al dettaglio).
   - **Salute & catalogo** — barre di copertura enrichment (BPM/key,
     mood/energia, pronte) + **top 5 etichette**.
4. **Azioni rapide** — riga di azioni a filetto: Importa playlist / Scopri
   musica / Identifica un mix.

## 3. Estensione backend `/api/stats`

`LibraryStatsOut` (in `backend/app/schemas.py`) e `library_stats()` (in
`backend/app/repositories.py:138`) aggiungono due campi deterministici:

- **`bpm_histogram: list[BpmBin]`** — istogramma dei BPM su **8 bin** a
  larghezza uguale tra `bpm_min` e `bpm_max` (inclusivi). Ogni bin:
  `{ "from": float, "to": float, "count": int }`. Conta solo tracce con `bpm`
  non nullo. Lista vuota se nessuna traccia ha BPM (`bpm_min` nullo).
  - Bordi: `width = (bpm_max - bpm_min) / 8`; il bin `i` copre
    `[bpm_min + i*width, bpm_min + (i+1)*width)`, l'ultimo bin è chiuso a destra
    (include `bpm_max`). Se `bpm_min == bpm_max` (un solo valore distinto): un
    singolo bin `{from: bpm_min, to: bpm_max, count: <tutti>}`.
- **`energy_distribution: list[EnergyBucket]`** — distribuzione su **5 bucket
  fissi** di ampiezza 20 sull'intervallo 0–100. Ogni bucket:
  `{ "from": int, "to": int, "count": int }` con `from/to` ∈
  `{0,20,40,60,80,100}`. Conta solo tracce con `energy` non nullo; il valore
  `100` cade nell'ultimo bucket `[80,100]`. Sempre 5 bucket (anche con count 0).

Entrambi i campi hanno default `[]` nello schema (retrocompatibilità). Test in
`backend/tests/` per: libreria vuota, BPM tutti nulli, valore singolo,
distribuzione normale, energia ai bordi (0 e 100).

## 4. Componenti & file

### Backend
- `backend/app/repositories.py` — `library_stats()`: calcola `bpm_histogram` ed
  `energy_distribution` (funzioni pure `_bpm_histogram(bpms)` e
  `_energy_distribution(energies)` testabili in isolamento).
- `backend/app/schemas.py` — `LibraryStatsOut` += i due campi + i modelli
  `BpmBin` ed `EnergyBucket`.
- `backend/tests/test_library_query.py` — test dei due aggregatori.

### Frontend
- `frontend/lib/api.ts` — `LibraryStats` += `bpm_histogram: BpmBin[]` ed
  `energy_distribution: EnergyBucket[]` (più i type `BpmBin`/`EnergyBucket`).
- `frontend/components/dashboard/` (nuovo) — componenti riusabili e focalizzati:
  - `Figure.tsx` — `Figure({ label, value })`: cella hero con numero grande
    tabellare.
  - `Histogram.tsx` — `Histogram({ bins })`: istogramma a barre monocromatiche
    (altezza ∝ count/max) con etichette agli estremi.
  - `MiniBars.tsx` — `MiniBars({ rows })` dove
    `rows: { label: string; value: number; href?: string }[]`: lista
    etichetta→barra→valore, riusata per Camelot e Top etichette.
  - `RecentList.tsx` — `RecentList({ items })` dove
    `items: { n: string; title: string; meta: string; href: string }[]`: lista
    numerata editoriale per set/playlist recenti.
- `frontend/app/page.tsx` — riscritta come broadsheet, compone le fetch e
  monta i componenti sopra.

## 5. Flusso dati

La dashboard esegue **4 fetch parallele** indipendenti:
`apiGet<LibraryStats>("/api/stats")`, `apiGet<SetlistSummary[]>("/api/sets")`,
`listImportedPlaylists()`, `getLabels()`. Ogni regione si popola quando la sua
fetch risolve; nessuno spinner a tutta pagina.

- **Ultimi set**: `/api/sets` ordinati per `created_at` desc → primi 4.
- **Ultime playlist**: `listImportedPlaylists()` ordinate per `imported_at`
  desc → prime 3.
- **Top etichette**: `getLabels()` (già ordinate per `track_count` desc) → prime 5.

## 6. Stati

- **Libreria vuota** (`total_tracks === 0`): mostra l'empty state di onboarding
  esistente ("Importa una playlist Spotify per iniziare…") al posto della
  broadsheet.
- **Loading**: ogni regione mostra un placeholder discreto (skeleton a filetto o
  `—`) finché la sua fetch non risolve; le regioni caricano indipendentemente.
- **Errore**: se `/api/stats` fallisce, `Alert tone="danger"` come oggi
  ("il backend è attivo su :8000?"). Le fetch secondarie (set/playlist/etichette)
  falliscono in silenzio mostrando `—` / sezione vuota.

## 7. Estetica

Monocromatico puro, IBM Plex Mono, filetti 1px, `radius 0`, cifre tabellari,
label maiuscole tracciate. Nessun colore nuovo (il rosso `danger` resta solo per
l'alert di errore). Verifica in dark **e** paper.

## 8. Testing

- **Backend:** `pytest backend/tests` — nuovi test su `_bpm_histogram` /
  `_energy_distribution` (bin corretti, casi limite §3) + suite esistente verde.
- **Frontend:** `npm run lint` (0 errori) + `npm run build` (pulita) +
  verifica visiva nei due temi, stato vuoto e popolato.

## 9. Fuori scope

- Nessun cambio alla grammatica dello shell, ai token o alle altre pagine.
- Nessuna nuova dipendenza o libreria di charting (istogrammi = `div` a filetto).
- Nessun nuovo endpoint oltre l'estensione di `/api/stats`.

## 10. Note di esecuzione (per il piano)

Fasatura: (A) **Backend** — aggregatori histogram/energy + schema + test; (B)
**API client** — tipi frontend; (C) **Componenti dashboard** — Figure,
Histogram, MiniBars, RecentList; (D) **Pagina** — riscrittura broadsheet +
stati. Ogni fase lascia `pytest`/`lint`/`build` verdi.
