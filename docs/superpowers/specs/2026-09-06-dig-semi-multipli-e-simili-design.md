# Dig ridisegnato: semi multipli, simili nella stessa barra, Discogs opzionale

Data: 2026-09-06. Stato: approvata a voce.

## Problema

La pagina Dig ha tre difetti che si sommano, e uno di essi è un bug vero.

1. **La selezione del seme è scomoda e singola.** Un Combobox con 319 voci
   miste (generi di libreria, etichette, stili curati) chiede di digitare per
   vedere, e accetta un seme solo. Chi scava non pensa "Deep House"; pensa
   "Deep House e Electro, e vediamo cosa esce".
2. **I simili sono un ramo separato raggiungibile solo da fuori.** Ci si
   arriva dal dettaglio traccia, e una volta dentro la barra sparisce: per
   cambiare idea si torna indietro. Nella stessa pagina convivono due ricerche
   che non si parlano.
3. **I simili restituiscono due lead.** Non è un'impressione: è il cap per
   artista del dig applicato a un arco che è per costruzione un artista solo.

In più Discogs occupa metà della barra per chi non lo usa.

## La diagnosi dei "pochi risultati" (misurata)

L'ipotesi corrente era l'interruttore "stile e periodo": senza, pochi
risultati; con, molti. La causa vera è un'altra.

`similar()` riusa `_select()` del dig, che applica `_MAX_PER_ARTIST = 2` per
impedire che un artista monopolizzi la lista. Nei simili l'arco `same_artist`
è **per costruzione** tutto lo stesso artista: l'intera discografia collassa
a due card.

Sonda deterministica (artista autoprodotto, 10 release non possedute, flag OFF):

```
LEAD RESTITUITI: 2 su 10 candidati
```

Con `same_label` quasi sempre assente — su Bandcamp l'autoprodotto è la norma,
`label_id` manca o coincide con la band e l'arco riporta
`absent_reason="self_released"` — senza il flag restano **due risultati in
tutto**. Accendere "stile e periodo" aggiunge il terzo arco, che non è capped
perché porta artisti diversi: da qui l'illusione che sia l'interruttore a fare
la differenza.

Difetto gemello, visibile: `edge_hits` conta i lead **prima** di `_select`,
quindi il chip in intestazione dice "ARTISTA 10" con due card a schermo.

## Decisioni chiave

- **Unione, non intersezione.** Più semi scavano ciascuno la propria pila e i
  risultati si fondono. L'intersezione (che entrambe le sorgenti
  supporterebbero nativamente: `style` ripetuto su Discogs, `tag_norm_names`
  su Bandcamp) restringe, ed è l'opposto del bisogno.
- **Il budget di uno scavo resta 300 item, diviso fra i semi.** Non 300 per
  seme. Il costo di uno scavo non deve crescere col numero di generi scelti.
- **Semi misti.** Un seme porta il proprio tipo: due generi e un'etichetta
  insieme sono una query legittima. Il `seed_type` globale sparisce.
- **La barra resta visibile in modalità simili.** I simili smettono di essere
  un ramo che sostituisce l'interfaccia e diventano un modo della stessa barra.
- **Generi e tracce hanno affordance diverse.** Per i generi una tavolozza di
  chip cliccabili (più testo libero per l'inserimento manuale); per le tracce
  una ricerca testuale. Fondere le due in un campo solo lo renderebbe ambiguo.
- **Discogs si spegne dall'interfaccia, non dal backend.** È una preferenza di
  presentazione, non un confine di sicurezza. Default acceso.
- **Il cap per artista resta, ma non sull'arco artista.** Il monopolio è un
  rischio vero sugli archi etichetta e stile; sull'arco artista il "monopolio"
  è il risultato richiesto.

## Lavoro zero: HEAD non compila

`4ef52f7d` ha tolto la prop `backHref` da `DiscoverySimilarHeader` (la freccia
indietro è passata in cima alla pagina) ma `frontend/app/discovery/page.tsx:359`
continua a passarla.

```
app/discovery/page.tsx(359,11): error TS2322:
  Property 'backHref' does not exist on type ...
```

Va rimossa la prop dal punto di chiamata prima di qualunque altra cosa. I test
passano lo stesso: `tsc` non gira nella suite Vitest, e questo è di per sé un
fatto da ricordare quando si valuta il verde.

## Il ridisegno della barra

Un riquadro solo, tre righe. La modalità è un controllo visibile invece di un
ramo dedotto dall'URL.

```
┌─────────────────────────────────────────────────────────────────────┐
│ Modo [Generi ed etichette | Traccia]   Sorgente [Discogs|Bandcamp]  │
│                                        Profondità [Sup|Media|Fondo] │
├─────────────────────────────────────────────────────────────────────┤
│ [Deep House ×] [Electro ×] [Hessle Audio ×]                         │
│ ┌───────────────────────────────────┐                               │
│ │ aggiungi o scrivi un genere…      │        [Scava] [Sorprendimi]  │
│ └───────────────────────────────────┘                               │
├─────────────────────────────────────────────────────────────────────┤
│ IN LIBRERIA  [House 412] [Techno 388] [Electro 91] [Bass 44] …      │
│ ALTRI STILI  [Dub Techno] [Italo-Disco] [Nu-Disco] …      ⌄ mostra  │
└─────────────────────────────────────────────────────────────────────┘
```

**Riga 1** — i controlli del modo corrente. `Modo` commuta fra scavo e simili.
In modalità simili `Profondità` lascia il posto alla checkbox "Stile e
periodo", e il selettore sorgente sparisce (i simili sono solo Bandcamp).

`Modo` è **stato locale, non URL**: commutarlo cambia solo quale campo si
vede. L'URL si muove quando parte una ricerca — `Scava` scrive `seeds=…`,
scegliere una traccia scrive `similar=…` — e la modalità mostrata all'apertura
della pagina si deduce da quale dei due c'è. I risultati già a schermo restano
finché non parte la ricerca nuova: commutare modo non è annullare quello che
si sta guardando.

**Riga 2, scavo** — i semi scelti come chip rimovibili, ciascuno con l'icona
del proprio tipo (`Disc3` genere, `Tags` etichetta), più il Combobox per
aggiungerne. Il Combobox accetta anche testo libero: è l'inserimento manuale.
Un seme scelto dal menu porta il tipo del proprio gruppo; uno scritto a mano e
confermato con Invio è un **genere**, come oggi. Un valore già in lista non si
duplica (confronto case-insensitive su tipo + valore): il chip esistente
lampeggia invece di sdoppiarsi.

**Riga 2, traccia** — il Combobox diventa una ricerca testuale sulla libreria,
con dropdown a copertina · artista — titolo. Sceglierne una naviga su
`?similar=<id>` e la barra resta dov'è.

**Riga 3, la tavolozza** — i generi in libreria col conteggio
(`GET /api/library/genres`) e gli stili curati, come chip che commutano la
selezione. Aperta a barra vuota, collassata dopo il primo seme. È la cura vera
per "la selezione è scomoda": si vede cosa si ha prima di digitare.

L'intestazione dei simili (release riconosciuta, chip degli archi) compare
sotto la barra come oggi, non al posto suo. La freccia indietro resta in cima
alla pagina dove l'ha messa `4ef52f7d`.

### Ricerca traccia: il parametro che manca

`GET /api/tracks` ha `artist` e `title` separati, entrambi già `ilike %…%`, ma
nessun campo unico. Serve un `q` che faccia OR fra i due in
`_apply_track_filters` — tre righe. Non tocca gli altri filtri: chi passa
`artist=` continua a filtrare solo per artista.

## Il motore: da un seme a molti

### Contratto HTTP

Rottura pulita, senza forma legacy: app locale mono-utente, e i vecchi URL
`?seed=&value=` non hanno lettori esterni da proteggere.

```
POST /api/discovery/dig
{ "seeds": [{"type": "genre", "value": "Deep House"},
            {"type": "label", "value": "Hessle Audio"}],
  "depth": 0.0, "source": "bandcamp" }
```

Cap a **4 semi**: oltre, il budget per seme scende sotto la soglia in cui la
finestra smette di dire qualcosa.

URL della pagina:
`?seeds=genre:Deep%20House,genre:Electro,label:Hessle%20Audio&depth=0&source=bandcamp`.

`:` separa tipo e valore, `,` separa i semi: entrambi compaiono nei nomi veri
(«Nu-Disco, Italo» non è inventato) e vanno codificati **dentro il valore**
prima di comporre la lista, non lasciati alla sola codifica della query string
— che li lascerebbe passare tali e quali e spezzerebbe il parsing. Il parser
splitta sul primo `:` soltanto, e scarta un tipo che non sia `genre` o
`label`: quella stringa arriva dall'URL, e chi lo scrive non è per forza
l'app.

### `dig()`

`dig()` prende `seeds: list[Seed]`. Per ogni seme: `probe` → `_window` →
`fetch`. Poi una sola passata di dedup, punteggio e selezione sull'unione.

- **Budget**: `WINDOW_ITEMS // len(seeds)` item per seme. Con tre generi sono
  tre round trip e 300 item, non nove round trip e 900.
- **Dedup globale** con la `_dedup_key` di oggi: un disco raggiunto da due
  generi compare una volta sola.
- **`_styles_beyond_seed`** riceve l'insieme dei valori dei semi, non uno solo:
  altrimenti il pavimento comune che quella funzione esiste per togliere
  tornerebbe da ogni seme che non è quello passato.
- **`_weights`** azzera il peso `label` solo se **tutti** i semi sono
  etichette. Con semi misti il segnale etichetta discrimina di nuovo (non è più
  costante per costruzione) e va tenuto.

### `DigResult`

`pile_total` e `pile_reach` scalari diventano `piles: list[PileOut]`, una voce
per seme con `seed_type`, `value`, `total`, `reach`, `resolution`.

Ne discendono i testi della UI:

| Situazione | Cosa dice la pagina |
|---|---|
| Un seme con `total == 0` fra altri vivi | Nomina il seme morto, non dichiara vuoto l'intero scavo |
| Tutti i semi con `total == 0` | L'attuale stato "seme sconosciuto alla sorgente", al plurale |
| Almeno un seme con `total > reach` | L'avviso "seme largo", elencando quali |
| Ogni `reach <= WINDOW_ITEMS / len(seeds)` | Profondità inerte, come oggi su pila corta |

## Discogs opzionale

```
GET/PUT /api/settings/discovery  →  { "discogs_enabled": true }
```

Persistito in `AppState`, chiave `discovery.discogs_enabled`, **default
acceso**: chi non tocca nulla non vede cambiare niente.

- Spento: la barra non mostra il selettore sorgente e forza Bandcamp; un URL
  con `source=discogs` degrada a Bandcamp invece di dare errore.
- **Il backend resta permissivo.** È una preferenza di interfaccia: rifiutare
  la richiesta romperebbe i link salvati e non proteggerebbe da nulla. Appena
  si riaccende, quei link tornano a funzionare.
- **Non tocca Organize.** Il client Discogs dei metadati testuali
  (`backend/app/organize/integrations/`) e il token in Servizi esterni restano
  dove sono: sono l'altra metà del confine che `CLAUDE.md` chiede di non
  attraversare. Restano funzionanti anche il dettaglio release Discogs e la
  preview YouTube, per i lead già in lista.
- Impostazioni: gruppo nuovo `Discovery`, fra Generale e Percorsi.

## I due difetti dei simili

**Il cap.** `_select()` si spezza in `_sort_by_score()` e
`_cap_per_artist(leads, exempt=…)`. Il dig continua a chiamarle in sequenza
senza esenzioni. `similar()` esenta i lead raggiunti dall'arco `same_artist`:
il cap resta attivo su etichetta e stile, dove il monopolio è un rischio vero.

Un lead raggiunto da più archi, di cui uno è `same_artist`, è esente: la
parentela più forte vince.

**Il conteggio.** `edge_hits` si calcola sui lead **selezionati**, non sui
candidati. Il chip "ARTISTA 10" deve corrispondere a dieci card.

`style_period` resta **spento** di default. Col cap risolto, senza flag si
ottiene la discografia intera più l'etichetta: un risultato onesto, e il
contratto dell'URL non cambia.

## Test

Backend:

- unione di semi misti: dedup fra pile, budget diviso, pesi con genere +
  etichetta insieme;
- `piles` per seme con un seme morto in mezzo agli altri;
- cap a 4 semi, e `seeds` vuoto rifiutato;
- `q` su `/api/tracks`: OR fra artista e titolo, e non interferisce con
  `artist=`/`title=` espliciti;
- `GET/PUT /api/settings/discovery`, default acceso, valore ignoto degradato;
- arco artista non tagliato (la sonda della diagnosi, come test permanente);
- conteggi degli archi uguali ai lead resi.

Frontend:

- chip: aggiunta, rimozione, dedup case-insensitive, cap a 4;
- tavolozza che commuta la selezione nei due versi;
- ricerca traccia che porta in modalità simili senza perdere la barra;
- selettore sorgente assente a Discogs spento, e `source=discogs` nell'URL che
  degrada;
- round-trip dell'URL multi-seme, semi con virgole e due punti nel nome
  compresi.

Ogni asserzione va provata rompendo il codice sotto: un test che resta verde
con la riga cancellata non misura niente.

## Fuori scope

- L'intersezione (AND) fra generi. Se servirà, entra come interruttore accanto
  ai chip senza toccare il contratto: i semi ci sono già.
- Discogs come sorgente dei simili. Il protocollo `SimilarSource` è già lì, ma
  nessuno lo implementa e non è questo il giro.
- La preferenza "Discogs spento" non nasconde nulla in Organize né altrove:
  vale per la barra del dig e basta.
