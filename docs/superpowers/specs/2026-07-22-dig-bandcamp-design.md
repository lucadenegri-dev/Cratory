# Design — Dig Bandcamp (seconda sorgente del crate digging)

Data: 2026-07-22
Stato: approvato (brainstorming)

## Obiettivo

Aggiungere **Bandcamp** come seconda sorgente del dig, accanto a Discogs. L'intento
dichiarato dall'utente è **"un'altra pila da cui pescare"**: stesso gioco, stessa pagina,
stessa griglia, stessi semi, stessa gestualità della profondità — si cambia cassa quando
su un genere Discogs è spremuto. Nessuna aspettativa di lead diversi per natura.

Fuori scope: fondere i risultati delle due sorgenti (si sceglie una sorgente alla volta,
niente dedup incrociata), l'acquisto in-app, il download, il seguire etichette su Bandcamp,
qualunque scrittura verso Bandcamp.

## Cosa dà davvero Bandcamp

Tutte le righe qui sotto sono **misurate contro l'API reale il 2026-07-22**, non ricordate.

L'endpoint di discovery è `POST https://bandcamp.com/api/discover/1/discover_web`
(`Content-Type: application/json`), quello dietro `bandcamp.com/discover`. Il vecchio
`api/hub/2/dig_deeper` è morto (`{"error":true,"error_message":"bad function"}`).

Corpo della richiesta:

```json
{"category_id":0,"tag_norm_names":["techno"],"geoname_id":0,"slice":"top",
 "include_result_types":["a"],"size":60,"cursor":"*"}
```

Risposta: `result_count` (altezza della pila), `batch_result_count`, `cursor` (opaco),
`results[]`.

`include_result_types` resta `["a"]` (album): con `["t"]` la risposta non contiene
`results` — le tracce sciolte non sono interrogabili per questa via. `category_id` e
`geoname_id` restano a `0` (nessun filtro per categoria o luogo).

| | Discogs (oggi) | Bandcamp |
|---|---|---|
| Altezza pila | `pagination.items` | `result_count` (`techno` = 434.149) |
| Paginazione | salto diretto a pagina N | **solo cursore sequenziale** |
| Ordinamenti | `sort=want desc` | `slice: "top"` e `"new"` (`rec` non risponde) |
| Seme genere | `style` con fallback `genre` | `tag_norm_names`, **combinabili in AND** (`techno`+`acid` = 38.280) |
| Seme etichetta | filtro `label` | altra strada (vedi sotto) |
| Rarità | `have`/`want` | **niente** |
| Per release | style multipli, formato dichiarato | prezzo, data esatta, luogo, `track_count`, **stream mp3 del brano in evidenza** |
| Seme inesistente | — | `result_count: 0`, pulito |

Misure di costo: `size` regge fino a **500** e il tempo è sublineare — 60 risultati in
0,8s, 500 in 3,2s. Sfogliare in profondità è quindi economico. 900 item raccolti su 15
batch consecutive: **zero duplicati**.

Le copertine si costruiscono da `primary_image.image_id`:
`https://f4.bcbits.com/img/a{image_id}_9.jpg` (~15KB, per la griglia) e `_16` (~50KB,
per il pannello). Verificate: HTTP 200.

Il dettaglio di una release si ottiene da
`POST https://bandcamp.com/api/mobile/24/tralbum_details` con
`{"band_id": <int>, "tralbum_id": <int>, "tralbum_type": "a"}`. Restituisce
`bandcamp_url`, `tralbum_artist`, `title`, `art_id`, `label`, `tags`, `price`,
`release_date` (timestamp unix) e `tracks[]` con `track_num`, `title`, `duration` e
`streaming_url["mp3-128"]`. Verificato su Ostgut Ton / "Love Letter": 2 tracce con stream.

Lo `stream_url` del brano in evidenza risponde **206 con qualunque `Origin`/`Referer`**,
senza autenticazione, `accept-ranges: bytes`, `cache-control: max-age=31536000`. La
risposta osservata era un cache HIT di 16 giorni: il token nell'URL non è applicato
per-richiesta. Il player usa un `<audio src>` nudo senza `crossOrigin`, quindi **non serve
alcun proxy**.

## Approccio scelto

Delle tre alternative valutate — (A) adattatore dentro il motore esistente, (B) servizio
gemello separato, (C) protocollo `DigSource` — si adotta **C**.

(A) riempirebbe il motore di condizionali per le differenze vere (pagine contro cursore,
`want` contro niente). (B) creerebbe due motori da tenere allineati per sempre: esattamente
il "futuro bug di coerenza" che il commento di `_usable_pages` in
`backend/app/services/discovery_dig.py` mette per iscritto. (C) porta a termine il seam che
il codice già suggerisce, visto che `search_releases`/`count_releases` sono **già** iniettate.

## 1 — Il seam `DigSource`

Oggi `dig()` parla la lingua di Discogs: `_window(depth, total)` restituisce **numeri di
pagina** e le costanti `SEARCH_PER_PAGE`/`DISCOGS_MAX_PAGES` sono cablate nel motore. Il
protocollo sposta il confine di un passo: **il motore ragiona in item, la sorgente traduce
nella sua paginazione**.

```python
# backend/app/services/dig_sources/__init__.py
@dataclass(frozen=True)
class Seed:
    type: str          # "genre" | "label"
    value: str

@dataclass
class Pile:
    height: int              # quanto è alta davvero la pila
    reach: int               # quanti item ne raggiunge QUESTA sorgente
    resolution: str | None   # "style"|"genre"|"label"|"tag"|"discography"
    handle: Any = None       # stato opaco della sorgente

class DigSource(Protocol):
    name: str
    def probe(self, seed: Seed) -> Pile: ...
    def fetch(self, seed: Seed, pile: Pile, offset: int, count: int) -> list[Any]: ...
    def to_lead(self, raw: Any, seed: Seed) -> DiscoveryLead | None: ...
```

`probe` restituisce anche `handle` perché **il motore non deve ri-sondare**: Discogs ci
mette i filtri già risolti (`style` contro `genre`), Bandcamp il `band_id` dell'etichetta
trovata. Una sonda, non due.

Il calcolo della finestra diventa uno solo per entrambe le sorgenti:

```python
WINDOW_ITEMS = 300      # ciò che oggi sono 3 pagine da 100

def _window(depth: float, pile: Pile) -> tuple[int, int]:   # (offset, count)
    reach = min(pile.height, pile.reach)
    start = round(clamp01(depth) * max(0, reach - WINDOW_ITEMS))
    return start, min(WINDOW_ITEMS, max(0, reach - start))
```

Discogs dichiara `reach = DISCOGS_MAX_PAGES * SEARCH_PER_PAGE` = 10.000 (il tetto di
pagina 101) e traduce l'offset in numeri di pagina. Bandcamp dichiara `reach = 3000`
(§2) e traduce l'offset in quante batch sfogliare col cursore.

`dig()` cambia firma: da `search_releases`/`count_releases` a `source: DigSource`. Il
resto della pipeline — dedup delle varianti, esclusione del posseduto, `TasteProfile`,
score, reasons, `_select` — **non cambia e non sa chi c'è dietro**.

### File

```text
backend/app/services/dig_sources/__init__.py    Protocol + Seed + Pile
backend/app/services/dig_sources/discogs.py     sorgente Discogs (estratta da discovery_dig)
backend/app/services/dig_sources/bandcamp.py    sorgente Bandcamp (nuova)
backend/app/integrations/bandcamp.py            client HTTP iniettabile, come discogs.py
backend/app/services/discovery_dig.py           il motore, senza più conoscenza di Discogs
```

`discovery_dig.py` è oggi a 588 righe: il pacchetto `dig_sources/` evita di portarlo oltre
le 800 e tiene ogni sorgente in un file che si legge tutto d'un fiato.

### Due conseguenze dichiarate

**Il dig Discogs scivola, e sulle pile corte scivola di due pagine.** Misurato
confrontando le due formule su tutto lo spazio (total, depth):

| pila | scivolamento massimo |
|---|---|
| ≥ 999 release | 1 pagina |
| ~300-700 release | **2 pagine** (es. 406 release a `depth=0.75`: `[3,4,5]` → `[1,2,3]`) |

La causa non è un arrotondamento: è che le due formule misurano lo scarto in **unità
diverse**. La vecchia lo misurava in pagine (`usable − 3`), la nuova in item
(`reach − 300`). Su 406 release la vecchia vedeva 2 pagine di scarto e a `depth=1.0`
pescava le pagine 3-5 — cioè **206 item veri spacciati per una finestra da 300**,
riempita con una pagina parziale. La nuova parte dall'item 106 e ne prende 300 davvero.

**Il comportamento nuovo è quindi più corretto, non una regressione:** sulle pile corte
il vecchio prometteva una profondità che la pila non aveva. Si accetta, e il limite vero
va fissato da un test invece che assunto.

Una nota su come questo è stato scoperto, perché vale più della correzione: la prima
stesura di questa spec dichiarava «una pagina» e portava come esempio `style=Acid House`
(43.345 release) a `depth=0.5`, «pagina 50 → 49». **Quell'esempio era inventato**: con
entrambe le formule il risultato è `[49,50,51]`. L'errore veniva da un arrotondamento
fatto a mente (`round(48.5) = 49`) dove Python arrotonda al pari (`48`). Il limite
dichiarato era sbagliato *e* l'esempio che avrebbe dovuto dimostrarlo non si verificava:
due errori che si coprivano a vicenda, trovati solo perché qualcuno ha ricostruito la
formula cancellata e le ha confrontate punto per punto.

**`discogs_id`/`discogs_url` diventano `source_id`/`source_url`.** Due sorgenti non
possono convivere in un campo che si chiama `discogs_id`. `source` esiste già nel lead e
diventa il discriminante. `source_id` è tipato `str | None`: l'id Discogs è un intero, ma
il tipo neutro evita che la terza sorgente debba esserlo per forza. Chi lo consuma
(l'endpoint di dettaglio Discogs) lo riconverte e valida. Tocca `DiscoveryLead`, `DiscoveryLeadOut`, il pannello tracklist,
il player e l'endpoint di dettaglio release. È churn vero, pagato adesso invece che alla
terza sorgente.

## 2 — La sorgente Bandcamp

### Semi

**`genre` → tag.** Normalizzazione: lowercase, spazi → trattini. Verificato:
`deep house` → `deep-house` (148.803), `uk garage` → `uk-garage` (16.472),
`trip hop` → `trip-hop` (55.486), `hip hop` → `hip-hop` (376.035).

La normalizzazione deve collassare **ogni corsa di caratteri non alfanumerici in un solo
trattino**, non limitarsi a sostituire gli spazi: `Funk / Soul` diventa così `funk-soul`
(1.630 release) invece di `funk-/-soul`, che su Bandcamp non esiste.

Resta un solo caso che la normalizzazione non può risolvere, e serve un alias esplicito:

| seme curato (Discogs) | normalizzazione | tag Bandcamp corretto |
|---|---|---|
| `Drum n Bass` | `drum-n-bass` → 9.745 | `drum-and-bass` → 37.264 |

È il caso peggiore da diagnosticare, e per questo l'alias è necessario: la forma
normalizzata trova una pila **vera ma sbagliata**, quindi nessun controllo su "zero
risultati" la intercetterebbe mai — il dig funzionerebbe scavando nel posto sbagliato.

Non esiste endpoint per enumerare o validare i tag Bandcamp: cercato e non trovato
(`discover_options`, `get_options`, `search_tags` → 404;
`autocomplete_elastic` con `search_filter` `t`/`g` restituisce tracce e album, non tag).
La tabella di alias marcirà come `_CURATED_STYLES` in
`backend/app/routers/discovery.py`, e ha la **stessa difesa**: `probe` restituisce
`result_count`, e `0` è un seme morto che la UI già sa dichiarare.

Tutti e 25 i semi di `_CURATED_STYLES` sono stati misurati contro l'API il 2026-07-22:
**24 su 25 funzionano con la sola normalizzazione** (da `acid-house` con 13.080 a
`ambient` con 812.272). La tabella ha la riga qui sopra e basta: non è un'incognita da
scoprire in implementazione.

**`label` → discografia, in due richieste:**

1. `POST /api/bcsearch_public_api/1/autocomplete_elastic` con
   `{"search_text": <etichetta>, "search_filter": "b"}` → il primo risultato di tipo `b`
   dà `id` (il `band_id`) e `item_url_root`. Verificato su "Ostgut Ton" →
   `https://ostgut.bandcamp.com`, id `2920024821`.
2. `POST /api/mobile/24/band_details` con `{"band_id": <id>}` → `discography[]`.
   Verificato: 153 release, ognuna con `item_id`, `band_id`, `item_type`, `title`,
   **`artist_name`** (non `artist`), `band_name` (l'etichetta), `art_id`, `release_date`.

**La discografia ha una forma diversa dai risultati del discover** e richiede un mapping
separato: mancano `featured_track`, `track_count` e l'URL della pagina, e `release_date`
è un formato diverso (`"26 Jun 2026 00:00:00 GMT"` contro `"2026-07-17 00:00:00 UTC"`).
Conseguenze: i lead da seme etichetta non hanno `stream_url` né `format_badge`, e il loro
`source_url` resta `None`. Nessuna delle tre è visibile nella griglia — la card non rende
un link esterno, e il play ricade sulla risoluzione iTunes che già esiste e non ha bisogno
di un id di sorgente. Il pannello, che apre `tralbum_details`, ha comunque URL, tag e
stream veri.

La discografia intera viene già scaricata da `probe` e finisce in `Pile.handle`: `fetch`
è una fetta di lista, zero richieste. La pila è quindi corta: `reach <= WINDOW_ITEMS` e la profondità non ha niente
da scegliere — **caso che la UI già gestisce** (oggi `pile_pages <= 3`, domani
`pile_reach <= 300`: slider disabilitato e messaggio dedicato). Un'etichetta che su
Bandcamp non c'è è un seme morto, già gestito.

### Profondità e costo

Si sfoglia col cursore a `size=500` scartando finché si è consumato l'offset, poi si
tiene la finestra da 300. Richieste = `ceil((offset + 300) / 500)`.

| `depth` | offset | richieste | tempo stimato |
|---|---|---|---|
| 0.0 | 0 | 1 | ~2s |
| 0.5 | 1350 | 4 | ~11s |
| 1.0 | 2700 | 6 | ~19s |

`BANDCAMP_REACH = 3000`, costante tarabile, scelta perché il dig peggiore resti sotto i
~20s. Su `techno` sono lo **0,7%** di 434.149; Discogs ne raggiunge il 23% (10.000 su
43.345). La differenza va detta all'utente, e la UI ha già il posto giusto: il messaggio
oggi legato al "seme largo" diventa condizionato a `pile_total > pile_reach`, neutro
rispetto alla sorgente.

`slice` resta fisso a `"top"`: è l'equivalente più vicino a `sort=want` di Discogs.
`"new"` funziona ma sarebbe un asse diverso, fuori dall'intento "stesso gioco".

### Da risultato a lead

| campo di `DiscoveryLead` | da |
|---|---|
| `artist` | `album_artist`, fallback `band_name` |
| `title` | `title` |
| `label` | `band_name` quando differisce da `album_artist` — su Bandcamp l'etichetta *è* la band che ospita (verificato: `band_name` "Mutual Rytm" / `album_artist` "Phil Berg") |
| `year` | anno di `release_date`. **Serve un parser dedicato**: `_parse_year` del motore àncora la regex all'inizio (`^\s*(\d{4})`) e su `"26 Jun 2026 00:00:00 GMT"` fallisce. Bandcamp cerca il primo gruppo di 4 cifre ovunque nella stringa |
| `source` | `"bandcamp"` |
| `source_id` | `item_id` |
| `source_url` | `item_url` ripulito di `?from=discover_page` |
| `thumb_url` | `https://f4.bcbits.com/img/a{primary_image.image_id}_9.jpg` |
| `stream_url` (nuovo) | `featured_track.stream_url` |
| `styles` | **lista vuota**: i tag della release stanno solo nella pagina album (337KB), quindi solo lazy nel pannello |
| `have`/`want` | restano 0: il concetto non esiste |
| `format_badge` | **derivato** da `track_count`: 1 → `Single`, 2-5 → `EP`, 6+ → `Album` |

Il badge derivato è **l'unico punto in cui si inferisce invece di leggere** — su Discogs
il formato è dichiarato dalla release. Serve perché i chip di filtro della griglia esistono
già e senza badge filtrerebbero via ogni lead Bandcamp. L'inferenza è deterministica e va
documentata nel codice come derivata.

### De-noise: non c'è

Su Discogs il rumore lo separa la domanda (`have`/`want`, `_demand`) più lo scarto dei
formati off-target (compilation, DJ mix) e dei self-released morti. Su Bandcamp **nessuno
dei tre segnali esiste**: non c'è domanda misurata, non c'è un campo formato, e
"self-released" non discrimina perché lo è quasi tutto.

Restano solo scarti **strutturali**: `featured_track` assente, `track_count` a 0, artista
in `_VARIOUS`, titolo o artista vuoti.

**Conseguenza accettata: il dig Bandcamp è più rumoroso del dig Discogs, e non esiste un
modo deterministico di renderlo meno rumoroso con i dati disponibili.** Scritto qui perché
sia una scelta e non una scoperta.

### Gusto e spiegazioni

`_weights` si generalizza da "quale seme" a "quali segnali esistono", conservando la
ridistribuzione che già fa oggi per il seme etichetta:

| sorgente + seme | artista | etichetta | stile |
|---|---|---|---|
| Discogs + genere | 0.5 | 0.3 | 0.2 |
| Discogs + etichetta (oggi) | 0.714 | 0.0 | 0.286 |
| Bandcamp + tag | 0.625 | 0.375 | 0.0 |
| Bandcamp + etichetta | 1.0 | 0.0 | 0.0 |

I due valori Discogs sono quelli attuali e **non devono cambiare**: `0.714 = 0.5/0.7` e
`0.286 = 0.2/0.7`, cioè `W_ARTIST` e `W_STYLE` normalizzati sulla loro somma quando
`W_LABEL` esce. La generalizzazione deve riprodurli esattamente, ed è un test.

Sul dig Bandcamp per etichetta il gusto ordina **solo** per familiarità dell'artista, e
sotto resta l'ordine stabile della discografia. È poco, ma è deterministico e il `sorted`
stabile di `_select` lo rende riproducibile — la stessa garanzia su cui poggia già il
fallback a gusto piatto.

Reason code: cadono `rare_wanted`, `deep_cut` (niente `have`/`want`) e `style_match`
(niente stili nella griglia). Restano `label_followed`, `artist_collected` e `recent` —
quest'ultimo più preciso di prima, perché la data di uscita è esatta.

## 3 — Preview e pannello tracklist

**Preview.** Lo `stream_url` arriva **già dentro il risultato del dig**: zero richieste in
più, brano intero invece dei 30s di iTunes, nessun fallback YouTube. `frontend/lib/player.tsx`
guadagna un ramo: se l'item di `discovery-preview` porta uno `streamUrl`, salta la
risoluzione via `GET /api/discovery/preview` e suona direttamente. Se la riproduzione
fallisce (token scaduto), si ricade sul dettaglio release, che restituisce URL freschi.

**Pannello tracklist.** `tralbum_details` restituisce in JSON la tracklist completa con
`streaming_url["mp3-128"]` per traccia, le durate, `bandcamp_url`, i tag veri della release
e il prezzo. Sul dig Bandcamp il pannello è quindi **più ricco** di quello Discogs, non più
povero.

Si è scartata l'alternativa di raschiare l'attributo `data-tralbum` dalla pagina album
(337KB di HTML per release): `tralbum_details` dà le stesse cose in JSON, e soprattutto
lavora su **id numerici**. È la differenza che cancella il rischio SSRF descritto in §4:
non c'è nessun URL da far seguire al backend, quindi non c'è nessun allowlist da tenere
corretto per sempre.

## 4 — API

- `POST /api/discovery/dig` prende `source: "discogs" | "bandcamp"`, default `"discogs"`.
- La risposta smette di parlare in pagine. `pile_pages` è sostituito da:
  - `pile_total` — l'altezza vera della pila;
  - `pile_reach` — quanti item questa sorgente raggiunge davvero.

  Ne discendono, source-neutral: **seme morto** = `pile_total == 0`; **pila corta** =
  `pile_reach <= 300`; **messaggio "ne vedi solo N di M"** = `pile_total > pile_reach`.
  `DISCOGS_PAGE_SIZE` sparisce dal frontend.
- `GET /api/discovery/release/{discogs_id}` diventa `GET /api/discovery/release` con
  query: `?source=discogs&id=<int>` oppure `?source=bandcamp&id=<item_id>&band_id=<band_id>`.
  Solo interi: nessun URL attraversa il confine, quindi **nessuna superficie SSRF e
  nessun allowlist da mantenere**.
- La risposta di dettaglio smette di chiamarsi `DiscogsReleaseOut` e diventa
  `DiscoveryReleaseOut`, con `source` e `source_url` al posto di `discogs_id`/`discogs_url`.
  `videos` (i video YouTube della release) resta popolato solo da Discogs; per Bandcamp
  è sempre vuoto, perché le tracce hanno già lo stream vero.
  Le tracce guadagnano `stream_url: str | None`, popolato solo da Bandcamp.
- `GET /api/discovery/preview` invariato: i lead Bandcamp non lo chiamano.
- `GET /api/discovery/genres` invariato: stessi semi, gli alias vivono lato backend.

## 5 — Frontend

- `frontend/components/discovery-dig-bar.tsx`: un `SegmentedControl` Discogs/Bandcamp.
- La sorgente entra nell'URL (`?source=`), quindi il dig si rilancia da sé — l'effetto su
  `paramsKey` in `frontend/app/discovery/page.tsx` c'è già e non va toccato.
- Griglia, lente (formato / ordina / mostra) e pannello restano gli stessi. La card usa
  `lead.source_url` per il link esterno e `lead.stream_url`, quando c'è, per il play.
- Stringhe nuove in `frontend/lib/i18n/it.ts` e `en.ts`.

## 6 — Errori e tenuta

L'endpoint Bandcamp è **interno e non documentato**: può cambiare senza preavviso. Tre
difese:

1. **Isolamento.** Tutto l'HTTP sta in `backend/app/integrations/bandcamp.py`, con `httpx`
   iniettabile come `discogs.py`. Il parsing è **difensivo**: un campo mancante scarta il
   lead, non solleva un 500.
2. **Errori espliciti.** `BandcampError` → 502 `discovery_provider_error`, come Discogs —
   mai uno "zero risultati" muto. Con una differenza rispetto a Discogs: se la richiesta
   fallisce **durante lo skip** si solleva, perché degradare restituirebbe lead da una
   profondità diversa da quella chiesta, cioè mentirebbe sul contratto; se fallisce
   **dopo** aver raggiunto la finestra, degrada ai risultati già raccolti, come oggi.
3. **Test di contratto** marcato `@pytest.mark.network` ed **escluso dalla suite**:
   interroga l'API vera e verifica la forma della risposta. Si lancia a mano quando
   qualcosa non torna, invece di indovinare.

## 7 — Test

Offline, su fixture JSON catturate dall'API reale (`discover_web` per tag, `band_details`
per etichetta, una pagina album per il pannello):

- `_window` in item: parità con il comportamento attuale su Discogs entro lo scivolamento
  di una pagina dichiarato in §1; estremi `depth` 0 e 1; pila più corta della finestra.
- Sorgente Bandcamp, mapping **discover**: artista/etichetta da `album_artist`/`band_name`,
  alias dei tag, badge derivato dai `track_count`, scarti strutturali, `result_count: 0`.
- Sorgente Bandcamp, mapping **discografia**: artista da `artist_name`, anno da
  `"26 Jun 2026 00:00:00 GMT"`, assenza di `stream_url`/`format_badge`/`source_url`.
- Sfogliata col cursore: l'offset viene consumato davvero; un errore **durante** lo skip
  solleva, un errore **dopo** degrada ai risultati raccolti.
- Pesi: ridistribuzione senza stili, per tag e per etichetta; i due valori Discogs
  invariati (0.714 / 0.286).
- Motore: dedup ed esclusione del posseduto invariati con una `DigSource` finta.
- Router: 502 su errore provider; seme morto; dettaglio release per entrambe le sorgenti.
- Frontend: la sorgente entra nell'URL, la lente resta invariata.
- E2E: lo smoke Playwright esistente non deve rompersi.

## 8 — Rischio accettato

Si costruisce su endpoint interni di Bandcamp. Uso personale, self-hosted, singolo utente,
nessuna ridistribuzione, volumi da persona che scava — coerente con quello che l'app già
fa (yt-dlp su SoundCloud, slskd per l'acquisizione). Nessun audio di terzi viene scaricato
o conservato: la preview è effimera come quella iTunes/YouTube già in `CLAUDE.md`.

**Il rischio è che Bandcamp cambi e il dig Bandcamp si rompa.** Il seam `DigSource` fa sì
che, quando succede, si rompa **solo quello**: il dig Discogs continua a funzionare e
l'utente cambia cassa.
