# Discovery — la riga di scavo

Data: 2026-07-16
Stato: **da rivedere** — superata in parte da `2026-07-16-discovery-dig-motore-design.md`,
che va implementata prima.

> L'analisi funzionale del motore (spec "il motore: pescare dove c'è pesce") ha mostrato
> che «Profondità» **non** è una label bugiarda da rinominare: lo diventa onesta, perché
> il motore cambia. Decadono da questa spec: le rinomine "Ordina per" / "Il mio gusto ·
> Bilanciato · Rarità"; il popover con "Gusto misurato su" annidato (col gusto sempre
> attivo torna un pari grado sulla riga); il fix della soglia `deep_cut`, che migra nella
> spec del motore. **Regge invariato** tutto il resto: il combobox unificato
> genere+etichetta, il blocco a due righe, le primitive `Popover`/`Combobox`/
> `SegmentedControl`/`Chip`.

## Obiettivo

Ridisegnare i controlli del dig in Discovery (`frontend/app/discovery/page.tsx`), oggi
percepiti come antiestetici e confusionari. L'intervento è prevalentemente frontend, con
una singola correzione deterministica al backend (soglia del reason `deep_cut`).

## Motivazione

Quattro problemi distinti, tutti confermati dall'utente.

### 1. Rumore visivo

Il pannello (`page.tsx:165-311`) è un rettangolo bordato diviso da due filetti
orizzontali che impila **quattro idiomi di controllo diversi** in ~150px: segmented
control per il seed, `Input` + `datalist` per il genere, chip per generi/etichette,
`Select` per il gusto, di nuovo segmented per la profondità. Ogni riga è introdotta da
una microlabel `text-[10px] uppercase` appesa a sinistra senza griglia comune: non
esiste un asse verticale, ogni riga parte da un punto diverso.

Questo viola le anti-reference di `docs/DESIGN.md` ("generic SaaS dashboard": card
identiche, tutto impilato) e il north star ("The Printed Archive").

### 2. Modello mentale poco chiaro — le label mentono

Questo è il problema di fondo, e non è grafico.

**"Profondità" non cambia nessuna profondità.** Non tocca la query a Discogs: a
`adventurousness` 0.0 e a 1.0 la chiamata `search_releases` è identica
(`discovery_dig.py:314-319`). Non è un filtro: nessun lead viene scartato, il set di
candidati è lo stesso. Agisce **solo sul ranking**, come cursore che sposta il peso tra
due termini (`discovery_dig.py:256`):

```python
return adventurousness * discovery + (1 - adventurousness) * taste + 0.2 * recency
```

**"Gusto di riferimento" non è un pari grado della profondità: è un sotto-parametro di
uno dei due poli.** Entra nello score solo attraverso il termine `taste`, quindi pesa
`(1 - adventurousness)`: ad "Avventuroso" (0.85) vale il 15%, e a 1.0 non farebbe
nulla. La UI attuale li presenta come due righe fratelli. Sono padre e figlio.

Nessun riallineamento tipografico avrebbe risolto questo.

### 3. Asimmetria genere/etichetta

Il genere ha un campo di testo libero **più** le chip, che fanno la stessa cosa.
L'etichetta ha solo le chip. Due modi diversi per la stessa scelta, più un toggle per
passare da uno all'altro.

### 4. Troppo peso prima del risultato

Il pannello di setup resta a schermo intero anche dopo il dig, mentre il protagonista
dovrebbero essere i lead. Sotto, `discovery-lead-grid.tsx:65-96` aggiunge **una seconda
fascia di controlli** (chip formato + segmented ordinamento) con gli stessi idiomi
copia-incollati: due pannelli che galleggiano uno sull'altro.

## Vincoli

- `docs/DESIGN.md` è vincolante: monospace ovunque, `radius: 0`, filetti da 1px, nessuna
  ombra, monocromia (solo `danger`), label uppercase tracked ~10px, `.tnum` sui numeri.
- **L'URL resta la source of truth** per lo stato del dig (comportamento attuale,
  `page.tsx:111-137`). Il deep link `?seed=label&value=<label>` dalla pagina Etichette
  (`app/labels/[label]/page.tsx:77-82`) deve continuare a funzionare invariato.
- Nessun cambiamento al contratto API `POST /api/discovery/dig`: `seed_type`, `value`,
  `adventurousness`, `taste_playlist_id`, `limit` restano quelli.
- Nessuna nuova chiamata di rete: i suggerimenti del campo soggetto usano gli endpoint
  già chiamati oggi (`GET /api/discovery/genres`, `GET /api/labels`).
- Next.js 16: leggere `frontend/CLAUDE.md` e `node_modules/next/dist/docs/` prima di
  toccare pagine o routing.

## Design

### La forma: un blocco, due righe

Un unico blocco con filetto, diviso da un filetto orizzontale. Sopra la domanda, sotto
la risposta.

```
 SCAVA  [ ⌗ Trax Records              ]  ORDINA PER  [ BILANCIATO ▾ ]      (SCAVA)
 ─────────────────────────────────────────────────────────────────────────────────
 42 LEAD    FORMATO  ▪tutti ▹LP ▹EP ▹12"    ORDINE  ▪rilevanza ▹recenti
```

La riga della risposta **esiste solo dopo il dig** e porta il conteggio dei lead. Non è
una seconda barra di controlli: è l'intestazione dei risultati, parte dello stesso
oggetto. Prima del dig il blocco è alto una riga.

Il blocco non collassa e non si anima: è già alto una riga, non c'è niente da nascondere.
Dopo il dig resta dov'è e diventa l'header dei risultati.

### Il soggetto: un campo unico

Un `Combobox` con popover di suggerimenti che offre **generi ed etichette insieme**,
ciascuno distinto da un'icona a sinistra e da un tag a destra:

```
 [ acid|                                  ]
 ↳  ♩ Acid House                    genere
    ♩ Acid Techno                   genere
    ⌗ Acid Avengers Records      etichetta
```

Il `seed_type` è **derivato dalla voce scelta**, non più chiesto all'utente. Il toggle
seed sparisce; l'asimmetria sparisce con lui. Le chip "in libreria" di oggi diventano i
suggerimenti mostrati a campo vuoto — non più una seconda copia dello stesso controllo.

Sorgenti dei suggerimenti, invariate rispetto a oggi:

- **generi**: `GET /api/discovery/genres` → `library` per primi (i generi che possiedi),
  poi `styles`.
- **etichette**: `GET /api/labels`.

Ordinamento a campo vuoto: prima i generi di `library`, poi le etichette, poi gli
`styles`. Con testo digitato: match per sottostringa case-insensitive su entrambe le
liste, generi prima delle etichette a parità. Cap a 12 voci visibili con scroll (sostituisce
`CHIP_CAP` e i bottoni "+N altre / − meno", che spariscono).

Il campo accetta anche **testo libero non presente nei suggerimenti**: in quel caso
`seed_type = "genre"` (comportamento attuale del campo genere, che prova prima come
`style` Discogs e ripiega su `genre`, `discovery_dig.py:314-316`). Un valore libero non
può essere un'etichetta: le etichette valide sono un insieme chiuso e noto.

Se `GET /api/labels` torna vuoto (nessuna etichetta in libreria), il combobox mostra solo
generi — nessun empty state dedicato, nessun ramo condizionale in più. Sostituisce
`t.discovery.noLabels`, che diventa inutile.

### Il criterio: il figlio annidato sotto il padre

Un `Popover` in cui il sotto-parametro sta **dentro** il suo genitore. Questa è la
correzione strutturale del problema 2:

```
┌────────────────────────────────────────┐
│ ORDINA PER                             │
│  ▸ Il mio gusto                        │
│    artisti ed etichette che già hai    │
│  ▪ Bilanciato                          │
│  ▹ Rarità                              │
│    pochi lo hanno, in molti lo cercano │
│ ───────────────────────────────────────│
│ GUSTO MISURATO SU                      │
│  [ Tutta la libreria               ▾ ] │
│  Conta poco se ordini per rarità.      │
└────────────────────────────────────────┘
```

I valori di `adventurousness` restano quelli di oggi (0.15 / 0.45 / 0.85): cambia il
nome, non il motore.

La sezione "Gusto misurato su" è visibile solo se esiste almeno una playlist importata
(condizione attuale, `page.tsx:283`). Non viene nascosta in base al criterio scelto: a
"Rarità" pesa poco ma non zero (15%), e nasconderla la renderebbe saltellante.

### Rinomine (i18n, `it.ts` + `en.ts`)

| Oggi | Nuovo | Perché |
|---|---|---|
| `depthLabel` "Profondità" | "Ordina per" | non cambia la profondità della ricerca, cambia l'ordine |
| preset "Familiare" | "Il mio gusto" | nomina il polo dell'ordinamento, non il carattere dell'utente |
| preset "Bilanciato" | "Bilanciato" | invariato |
| preset "Avventuroso" | "Rarità" | idem |
| `affinityLabel` "Gusto di riferimento" | "Gusto misurato su" | dice che è un riferimento di misura, non una preferenza |
| `startFromLabel` "Scava per" | "Scava" | il seed non si sceglie più |
| `seedGenre` / `seedLabel` | rimossi | il toggle non esiste più |
| `noLabels` | rimosso | nessun empty state dedicato |
| `showMore` / `showLess` | rimossi | sostituiti dallo scroll del combobox |

Nuove stringhe: tag "genere" / "etichetta" nel combobox, descrizioni dei tre poli, hint
"Non cambia cosa cerchiamo su Discogs — cambia l'ordine dei risultati.", "Conta poco se
ordini per rarità.", conteggio "{n} LEAD".

Il microcopy deve restare onesto su tre punti verificati nel motore:

1. `adventurousness` non allarga la ricerca né sblocca dischi nuovi — riordina soltanto.
2. `taste_playlist_id` non filtra mai nulla; i dischi già posseduti restano esclusi
   comunque, e l'esclusione usa sempre tutta la libreria, mai la playlist
   (`discovery_dig.py:311,328`).
3. I `reasons` sono badge a soglia calcolati post-hoc, non i fattori dello score
   (`discovery_dig.py:259-275`). Il microcopy non deve dire che "spiegano" la posizione.

## Componenti

### Nuove primitive in `frontend/components/ui.tsx`

Sono la ragione per cui quel pannello è finito così: mancavano, e ogni pagina se le è
ricostruite a mano.

**`Popover`** — contenitore ancorato con filetto, `radius: 0`, niente ombra (The Hairline
Rule), superficie `surface` sul floor `bg`. Chiusura su click esterno, `Escape`, e blur
fuori dal contenuto. Focus trap non necessario (strumento personale, nessun requisito
oltre il contrasto, `DESIGN.md` §Accessibility).

- Interfaccia: `{ trigger, children, open?, onOpenChange?, align? }`.
- Dipendenze: nessuna nuova — solo React + `cn`.

**`Combobox`** — `Input` + `Popover` di opzioni raggruppate, navigazione da tastiera
(`↑`/`↓`/`Enter`/`Escape`), `aria-expanded`/`aria-activedescendant`, filtro per
sottostringa. Accetta testo libero.

- Interfaccia: `{ value, onChange, onSelect, options: {value, label, group, icon}[], placeholder, disabled }`.
- Sostituisce `Input` + `datalist` + chip + "+N altre" nel dig.

**`SegmentedControl`** — estrae il pattern `inline-flex border border-border bg-surface
p-0.5` + `<button aria-pressed>` oggi copiato **tre volte** (`page.tsx:175-193`,
`page.tsx:261-278`, `discovery-lead-grid.tsx:82-96`).

- Interfaccia: `{ value, onChange, options: {value, label, icon?, title?}[], disabled? }`.

**`Chip`** — promuove al DS il componente locale non esportato di `page.tsx:336-353`,
duplicato concettualmente in `discovery-lead-grid.tsx:65-80`.

- Interfaccia: `{ on, onClick, disabled, children }`.

Ogni primitiva deve leggere correttamente in **entrambi i temi** (dark e paper): è una
regola esplicita del design system.

### `frontend/components/discovery-dig-bar.tsx` (nuovo)

La riga di scavo, estratta da `page.tsx`. Riceve lo stato e lo notifica in su; non
conosce l'URL né chiama l'API.

- Props: `{ subject, onSubjectChange, criterion, onCriterionChange, tasteRef, onTasteRefChange, options: {genres, labels, playlists}, busy, ready, onSubmit }`.
- Resta un `<form>`: Invio nel campo lancia il dig (comportamento attuale, `page.tsx:165`).
- Il bottone "Scava" resta `disabled={busy || !ready}`.

### `frontend/components/discovery-lead-grid.tsx` (modificato)

Perde la propria fascia di filtri (`:65-96`) e la `Chip` ad-hoc. Espone formato e
ordinamento verso l'alto, così che vivano nella riga della risposta.

- Props: da `{ dig }` a `{ dig, format, onFormatChange, sort, onSortChange }`.
- La griglia dei lead e `LeadCell` restano invariate.

### `frontend/app/discovery/page.tsx` (modificato)

Resta il proprietario dello stato e della sincronizzazione con l'URL (`runDig`,
`paramsKey`, `useEffect`), che non cambiano. Dimagrisce dei ~150 righe di markup
inline che diventano `DiscoveryDigBar`.

`format` e `sort` restano **stato locale, fuori dall'URL**: sono lenti sui risultati già
ottenuti, non parametri del dig. Metterli nell'URL rilancerebbe il `useEffect` su
`paramsKey` e rifarebbe la chiamata a Discogs.

### `backend/app/services/discovery_dig.py` (modificato)

Unica correzione al motore. Oggi (`:70-74`, `:262-274`) il reason `deep_cut` scatta su
`have <= 50` **senza alcun segnale di domanda**: un disco che nessuno possiede *e*
nessuno cerca prende lo stesso badge di una vera rarità. Il badge dice "pochi lo hanno",
la UI lo fa leggere come "è una gemma".

Fix: `deep_cut` richiede anche `want >= 5`. Sotto quella soglia non c'è segnale di
domanda misurabile. Il caso forte resta coperto da `rare_wanted` (`want >= 10` e
`want/(have+want) >= 0.5`), che è indipendente.

- Nuova costante `REASON_DEEP_CUT_MIN_WANT = 5`, accanto a `REASON_DEEP_CUT_MAX_HAVE`
  (già esistente, `:70-74`), nel blocco "Soglie per i reason code".
- **Nessun effetto sullo score**: i reason sono calcolati a parte, il ranking non cambia.

## Flusso dati

```
URL (?seed=&value=&adv=&taste=)   ← source of truth, invariata
        │
        ▼
   page.tsx  ──stato──▶  DiscoveryDigBar   (soggetto, criterio, gusto)
        │                      │
        │                      └─ onSubmit ─▶ runDig() ─▶ router.push
        │
        ├─ useEffect(paramsKey) ─▶ POST /api/discovery/dig ─▶ dig
        │
        ├─ stato locale (format, sort) ─┐
        ▼                               ▼
   DiscoveryLeadGrid ◀──── dig + format + sort
```

Derivazione del `seed_type`, invariata a valle: voce scelta dal gruppo "etichetta" →
`"label"`; qualunque altro caso (genere scelto o testo libero) → `"genre"`.

## Gestione errori

Invariata. Gli errori del provider Discogs (`502 discovery_provider_error`,
`routers/discovery.py:255-257`) restano un `<Alert tone="danger">` sopra il blocco. Il
combobox non ha stati di errore propri: un valore libero senza risultati produce un dig
a zero lead, che è già gestito.

Se `GET /api/discovery/genres` o `GET /api/labels` falliscono, il combobox resta usabile
con testo libero: i suggerimenti sono un aiuto, non un requisito.

## Test

Esistono già `npm run test:unit` e `npm run test:e2e` nel frontend.

**Unit (nuovi)** — sulle primitive del DS, che ora hanno consumatori multipli:

- `Combobox`: filtro per sottostringa; generi prima delle etichette; navigazione
  `↑`/`↓`/`Enter`; `Escape` chiude senza selezionare; testo libero accettato.
- `Popover`: apre sul trigger; chiude su click esterno e su `Escape`.
- `SegmentedControl`: `aria-pressed` sull'opzione attiva; `onChange` col valore giusto.

**Unit (nuovi)** — sulla derivazione:

- voce del gruppo "etichetta" → `seed_type: "label"`; genere o testo libero → `"genre"`.

**E2E** — `frontend/e2e/smoke.spec.ts:23` copre già `/discovery`: va aggiornato ai nuovi
selettori. Aggiungere: il deep link `?seed=label&value=<label>` precompila il combobox
con l'etichetta giusta.

**Backend (nuovo)** — `deep_cut`:

- `have=10, want=0` → nessun `deep_cut` (regressione che stiamo correggendo).
- `have=10, want=5` → `deep_cut`.
- `have=200, want=50` → nessun `deep_cut`.
- lo score è identico prima e dopo il fix a parità di input.

## Fuori scope

- Unificazione expand/dig (già nel backlog tecnico, cfr. spec 2026-06-28).
- Esporre `limit` in UI: il client lo supporta (`lib/api/discovery.ts:34,40`) ma la
  pagina non lo passa mai. Con `_MAX_PER_ARTIST = 2` e un budget di 300 release grezze a
  monte, il default 80 non viene quasi mai raggiunto — un controllo che non cambierebbe
  nulla nel 90% dei dig.
- Il disallineamento del default `adventurousness` (frontend 0.45, backend 0.4,
  `schemas.py:530`): irrilevante finché la UI invia sempre il valore.
- Migrazione degli altri consumatori di `SegmentedControl`/`Chip` fuori da Discovery: le
  primitive vengono create qui, l'adozione altrove è un refactoring separato.
