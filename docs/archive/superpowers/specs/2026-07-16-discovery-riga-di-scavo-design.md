# Discovery — la riga di scavo

Data: 2026-07-16
Stato: design approvato (rev. 2), pronto per il piano di implementazione.
Da implementare **insieme** a `2026-07-16-discovery-dig-motore-design.md`, che è il
presupposto: questa spec espone i controlli di quel motore.

> **Rev. 2** — riconciliata con la spec del motore. L'analisi funzionale ha mostrato che
> «Profondità» non è una label bugiarda da rinominare: diventa onesta, perché cambia il
> motore. Rispetto alla rev. 1 decadono le rinomine "Ordina per" / "Il mio gusto ·
> Bilanciato · Rarità" e il popover con "Gusto misurato su" annidato; il fix della soglia
> `deep_cut` migra nella spec del motore. Regge invariato il resto.

## Obiettivo

Ridisegnare i controlli del dig in Discovery (`frontend/app/discovery/page.tsx`), oggi
percepiti come antiestetici e confusionari. L'intervento è **interamente frontend**: le
correzioni al backend stanno nella spec del motore, che va implementata insieme a questa.

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

**La spec del motore risolve la causa, non il sintomo.** `depth` sceglie il bacino (dove
pescare nella pila ordinata per domanda) e il gusto ordina **sempre**. Quindi:
«Profondità» torna a descrivere letteralmente il meccanismo, e «Gusto misurato su» conta
sempre — torna a essere davvero un pari grado. Questa spec espone quel modello; non deve
più compensare in UI una confusione che sta nel motore.

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
- Il contratto API `POST /api/discovery/dig` cambia — ma il cambiamento è **definito
  dalla spec del motore**, non da questa: `adventurousness` → `depth` (semantica nuova),
  più `pile_pages` in risposta. Questa spec consuma quel contratto, non lo negozia.
  `seed_type`, `value`, `taste_playlist_id`, `limit` restano quelli.
- Nessuna nuova chiamata di rete: i suggerimenti del campo soggetto usano gli endpoint
  già chiamati oggi (`GET /api/discovery/genres`, `GET /api/labels`).
- Next.js 16: leggere `frontend/CLAUDE.md` e `node_modules/next/dist/docs/` prima di
  toccare pagine o routing.

## Design

### La forma: un blocco, due righe

Un unico blocco con filetto, diviso da un filetto orizzontale. Sopra la domanda, sotto
la risposta.

```
 SCAVA [ ⌗ Trax Records      ]  PROFONDITÀ ▪superficie ▹metà ▹fondo  GUSTO [ Tutta la libreria ▾ ]  (SCAVA)
 ────────────────────────────────────────────────────────────────────────────────────────────────────────
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

### I modificatori: due pari grado, entrambi visibili

Nella rev. 1 il criterio era un `Popover` che si portava dentro il gusto come figlio.
Col motore nuovo quella gerarchia non esiste più: sono due assi indipendenti, e stanno
entrambi sulla riga, scoperti.

**Profondità** — un `SegmentedControl` a tre voci. È il controllo creativo del dig e
merita di essere visibile, non sepolto in un cassetto:

| voce | `depth` | cosa fa |
|---|---|---|
| Superficie | 0.0 | i classici del seme (che non hai) |
| A metà | 0.5 | `want` ~190: oscuri, ancora cercati |
| In fondo | 1.0 | `want` ~89: il fondo della cassa |

Il registro è quello del crate digging, che è ciò che `DESIGN.md` chiede a Discovery
("Experimental energy. Discovery should feel like digging through crates of records").
Sotto il controllo, una riga `text-xs text-muted` descrive la voce attiva — come oggi
(`page.tsx:279`), ma ora dicendo il vero.

Microcopy della voce attiva:

- Superficie → "I dischi più cercati del seme, meno quelli che hai già."
- A metà → "Più a fondo: meno noti, ancora molto cercati."
- In fondo → "Il fondo della cassa: oscuri, ma qualcuno li cerca ancora."

**Gusto** — un `Select`, invariato nella sostanza rispetto a oggi: "Tutta la libreria"
(default, `null`) o una playlist importata. Visibile solo se esiste almeno una playlist
(condizione attuale, `page.tsx:283`). Non è più un sotto-parametro: col gusto sempre
attivo conta sempre, a qualunque profondità.

Hint: "Rispetto a cosa misurare l'affinità. Non filtra: i dischi che hai già restano
esclusi comunque."

**Profondità inefficace sui semi piccoli.** Se la pila del seme è più corta della
finestra (`usable <= PAGES_PER_DIG`, cfr. spec motore), `depth` non ha effetto: non c'è
profondità da scegliere. Il backend lo sa e la UI no — e non deve saperlo prima del dig.
Va detto **dopo**, nella riga della risposta: se `DigResult` indica una pila corta, la
riga mostra "pila corta: tutta qui" accanto al conteggio, e il `SegmentedControl` della
profondità va in `disabled` fino al prossimo cambio di seme. Questo richiede un campo in
più nel DTO — **`pile_pages: int`** in `DiscoveryDigResponse` — che va aggiunto alla spec
del motore in fase di piano.

**Pila vuota ≠ pila corta** (aggiunto dopo l'implementazione). `pile_pages == 0` non è il
caso di sopra: significa che **Discogs non conosce il seme**, e trattarlo come pila corta
fa dire alla UI "tutta qui" su un nome che non ha mai avuto un disco. È successo davvero:
`_CURATED_STYLES` conteneva "Detroit Techno", che su Discogs non esiste né come `style` né
come `genre` — chi lo sceglieva otteneva zero lead e due messaggi falsi ("pila corta:
tutta qui" nella barra, "prova a scavare più a fondo" nell'empty state: un consiglio
impossibile, perché fondo non ce n'è).

I tre esiti vanno distinti perché la cura è diversa:

| `pile_pages` | lead | significato | cosa dire |
|---|---|---|---|
| 0 | 0 | Discogs non conosce il seme | non è la tua libreria, e la profondità non aiuta |
| 1–3 | ≥0 | pila vera ma corta | "tutta qui": non c'è profondità da scegliere |
| >3 | 0 | pila vera, tutto filtrato (lo possiedi già) | "prova più a fondo" — qui il consiglio funziona |

Questa distinzione è anche **la difesa strutturale** di `_CURATED_STYLES`: la lista è
scritta a mano, Discogs non espone un endpoint per enumerare gli style (quindi non è
derivabile dai dati) e marcirà ancora. Un test di rete andrebbe escluso dalla suite e non
lo eseguirebbe nessuno. Rendere il fallimento leggibile è ciò che rende la marcescenza
innocua — e vale anche per un genere digitato a mano che non esiste.

### Rinomine (i18n, `it.ts` + `en.ts`)

| Oggi | Nuovo | Perché |
|---|---|---|
| `depthLabel` "Profondità" | **invariato** | col motore nuovo descrive il meccanismo alla lettera |
| preset "Familiare" | "Superficie" | nomina il punto della pila, non il carattere dell'utente |
| preset "Bilanciato" | "A metà" | idem |
| preset "Avventuroso" | "In fondo" | idem |
| `affinityLabel` "Gusto di riferimento" | "Gusto" | è un pari grado, non un riferimento subordinato |
| `startFromLabel` "Scava per" | "Scava" | il seed non si sceglie più |
| `seedGenre` / `seedLabel` | rimossi | il toggle non esiste più |
| `noLabels` | rimosso | nessun empty state dedicato |
| `showMore` / `showLess` | rimossi | sostituiti dallo scroll del combobox |

Nuove stringhe: tag "genere" / "etichetta" nel combobox, le tre descrizioni di profondità,
l'hint del gusto, "pila corta: tutta qui", conteggio "{n} LEAD".

Il microcopy deve restare onesto su tre punti verificati nel motore:

1. `depth` sceglie **dove** si pesca nella pila ordinata per domanda, non quanto si cerca:
   il numero di release scaricate è sempre lo stesso.
2. `taste_playlist_id` non filtra mai nulla; i dischi già posseduti restano esclusi
   comunque, e l'esclusione usa sempre tutta la libreria, mai la playlist
   (`discovery_dig.py:311,328`).
3. I `reasons` sono badge a soglia calcolati post-hoc, non i fattori del punteggio
   (`discovery_dig.py:259-275`). Il microcopy non deve dire che "spiegano" la posizione.

## Componenti

### Nuove primitive in `frontend/components/ui.tsx`

Sono la ragione per cui quel pannello è finito così: mancavano, e ogni pagina se le è
ricostruite a mano.

> **`Popover` — decaduto (rev. 2).** La rev. 1 lo prevedeva per il popover del criterio;
> quando la rev. 2 lo ha eliminato, il testo continuava a giustificarlo come «base del
> `Combobox`». **Falso**: il `Combobox` si costruisce la propria lista di suggerimenti.
> Non è nemmeno adattabile — un `Popover` avvolge il trigger in un `onClick` che fa
> toggle, quindi con l'`Input` come trigger cliccare nel campo per scrivere chiuderebbe i
> suggerimenti. Un primitivo del design system senza consumatori è codice morto: YAGNI.
> Costruito e rimosso durante l'esecuzione (`eb03075` → `eac5efc`). Se un giorno servirà
> un popover, si farà quando ci sarà un consumatore vero.

**`Combobox`** — `Input` + lista di opzioni raggruppate, navigazione da tastiera
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

- Props: `{ subject, onSubjectChange, depth, onDepthChange, tasteRef, onTasteRefChange, options: {genres, labels, playlists}, pilePages, busy, ready, onSubmit }`.
- Resta un `<form>`: Invio nel campo lancia il dig (comportamento attuale, `page.tsx:165`).
- Il bottone "Scava" resta `disabled={busy || !ready}`.
- `pilePages` (dall'ultimo `DigResult`, `null` prima del primo dig) disabilita il controllo
  di profondità quando la pila è più corta della finestra.
- Su schermi stretti la riga va a capo (`flex-wrap`): tre zone più il bottone non stanno
  su una riga sotto il breakpoint `sm`. Il bottone resta full-width su mobile, come oggi
  (`page.tsx:307`).

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

### Backend

Nessuna modifica da questa spec. Il fix della soglia `deep_cut`, che nella rev. 1 stava
qui, è migrato nella spec del motore insieme al resto delle correzioni ai reason.

L'unico contratto che questa spec **richiede** al motore è `pile_pages` in
`DiscoveryDigResponse` (vedi "Profondità inefficace sui semi piccoli"), già recepito
dalla spec del motore.

## Flusso dati

```
URL (?seed=&value=&depth=&taste=)   ← source of truth
        │                  ▲
        │                  └─ `adv` rinominato `depth` (cfr. spec motore)
        ▼
   page.tsx  ──stato──▶  DiscoveryDigBar   (soggetto, profondità, gusto)
        │                      │
        │                      └─ onSubmit ─▶ runDig() ─▶ router.push
        │
        ├─ useEffect(paramsKey) ─▶ POST /api/discovery/dig ─▶ dig {leads, pile_pages}
        │                                                          │
        │                              pile_pages ────────────────▶┘ (torna in barra:
        │                                                             profondità inerte?)
        ├─ stato locale (format, sort) ─┐
        ▼                               ▼
   DiscoveryLeadGrid ◀──── dig + format + sort
```

Derivazione del `seed_type`, invariata a valle: voce scelta dal gruppo "etichetta" →
`"label"`; qualunque altro caso (genere scelto o testo libero) → `"genre"`.

Il parametro d'URL `adv` diventa **`depth`**: è un cambio di semantica, non solo di nome
(cfr. spec motore). I vecchi deep link con `?adv=` non vanno tradotti — `adv=0.85`
significava "ordina per rarità", `depth=0.85` significa "pesca in fondo alla pila": non
sono la stessa cosa e fingere che lo siano sarebbe peggio che ignorare il parametro. Un
`adv` non riconosciuto viene semplicemente ignorato e `depth` cade sul default 0.0. È uno
strumento personale: non ci sono link salvati da preservare se non i propri.

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

- profondità inerte: con `pile_pages <= 3` il `SegmentedControl` è `disabled` e la riga
  della risposta mostra "pila corta: tutta qui".
- **pila vuota ≠ pila corta**: con `pile_pages == 0` la profondità è comunque inerte, ma
  il messaggio dice che il seme è sconosciuto a Discogs — non "tutta qui". Il test deve
  mordere la confusione dei due casi, non solo l'assenza del messaggio.

**E2E** — `frontend/e2e/smoke.spec.ts:23` copre già `/discovery`: va aggiornato ai nuovi
selettori. Aggiungere: il deep link `?seed=label&value=<label>` precompila il combobox
con l'etichetta giusta.

I test del backend (soglie dei reason incluso `deep_cut`, `_window`, normalizzazione,
possesso, punteggio) stanno nella spec del motore.

## Fuori scope

- Unificazione expand/dig (già nel backlog tecnico, cfr. spec 2026-06-28).
- ~~Esporre `limit` in UI: il client lo supporta (`lib/api/discovery.ts:34,40`) ma la
  pagina non lo passa mai. Con `_MAX_PER_ARTIST = 2` e un budget di 300 release a monte,
  il default 80 non viene quasi mai raggiunto — un controllo che non cambierebbe nulla
  nel 90% dei dig.~~
  **Sbagliato, e misurato**: sul bacino nuovo sopravvivono 244 candidati su 300 e il tetto
  morde a **ogni** dig, nascondendo 160 lead. Il ragionamento veniva dal bacino vecchio,
  dove il rumore ne lasciava 30-60. `limit` viene **rimosso**, non esposto — vedi
  `2026-07-16-discovery-quanti-lead-e-suggeritore-completo-design.md`.
- Tradurre i vecchi deep link `?adv=` in `?depth=`: semantiche diverse (vedi Flusso dati).
- Migrazione degli altri consumatori di `SegmentedControl`/`Chip` fuori da Discovery: le
  primitive vengono create qui, l'adozione altrove è un refactoring separato.
