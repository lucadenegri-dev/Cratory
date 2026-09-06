# Discovery "Simili": dal disco che possiedi ai suoi parenti su Bandcamp

Data: 2026-09-06. Stato: approvata a voce.

## Problema

Il dig "Scava" parte sempre da un seme astratto — un genere o un'etichetta — e
riparte dalla barra a ogni colpo. Il digging reale non funziona così: parte da
un disco che piace e si muove lungo le sue parentele (chi l'ha fatto, su quale
etichetta, in che periodo). Oggi in Cratory questo movimento non esiste: da una
traccia posseduta non si arriva a nulla.

Il bisogno espresso è "tracce simili a quelle che mi piacciono", da acquisire.
Non "cosa ho già che sta con questa" (quello serve al Set Builder, non a
Discovery), e non "suona simile" (analisi audio: troppo complicata per il
ritorno).

## Decisioni chiave

- **Simile = imparentato nel grafo, non fuzzy.** A luglio 2026 è stato rimosso
  l'"expand" via Last.fm perché dava risultati deboli e vaghi
  (`docs/archive/superpowers/specs/2026-07-19-rimozione-expand-discovery-design.md`).
  Qui ogni lead ha una parentela verificabile con la traccia di partenza: stesso
  artista, stessa etichetta, oppure stesso stile nello stesso periodo.
- **Si parte solo da una traccia posseduta**, dalla pagina dettaglio. Non da un
  lead del dig, non dalla wishlist.
- **Si ottengono solo cose non possedute**, come nel dig: lead da ascoltare,
  salvare o scaricare.
- **Bandcamp è la fonte**, non Discogs. Chi usa l'app compra su Bandcamp: i lead
  sono comprabili subito e hanno lo stream reale per traccia, non la clip iTunes.
  Discogs copre di più (vinile, fuori catalogo) ma resta fuori dal primo taglio;
  il motore nasce dietro un protocollo che gli lascia la porta aperta.
- **Niente rinforzo da co-acquisto.** Uno spike ha verificato che Bandcamp non
  espone i collezionisti di una release via API JSON (solo dentro l'HTML della
  pagina album, ~290 KB) e che aggregare le collezioni di 10 fan produce 388
  release distinte con una sola sovrapposizione: segnale debole a costo alto,
  lo stesso profilo dell'expand rimosso. Scartato.
- **Archi: artista ed etichetta sempre, stile e periodo a interruttore.** I
  primi due coprono la maggior parte del digging reale e costano poco. Il terzo
  è vicino a un dig normale e rischia di annacquare i risultati: si accende a
  richiesta.
- **Degrado esplicito, mai silenzioso.** Il risultato dice sempre quale release
  è stata riconosciuta e quali archi sono attivi o assenti e perché. Un
  risultato povero deve spiegarsi da solo.

## Prerequisiti sulla traccia

La qualità dei simili è la qualità dei tag, quindi passa da Organize.

| Cosa ha la traccia | Cosa ottiene |
|---|---|
| Artista presente su Bandcamp, album (o titolo) che coincide con una release | Tutti gli archi |
| Artista presente, release non riconosciuta | Discografia dell'artista; etichetta e stile solo se i tag del file li hanno |
| Artista assente da Bandcamp | Nulla, con messaggio esplicito |

Il tag `artist` è la chiave d'ingresso e deve essere l'artista principale
pulito; si riusa `_clean_artist` del dig. Il tag `album` permette il match
diretto con la discografia (che elenca release, non brani); con il solo `title`
il match riesce se il brano è uscito come single o EP omonimo. Aprire ogni
release della discografia per cercarci il brano costerebbe una richiesta a
release: escluso.

## Motore

Nuovo `backend/app/services/discovery_similar.py`, affiancato a
`discovery_dig.py`, non dentro. Entra una `Track` e il flag `style_period`; esce
un `SimilarResult` con tre parti: **origine**, **bilancio degli archi**, **lead**.

### Protocollo

```python
class SimilarSource(Protocol):
    name: str
    def resolve(self, track) -> Origin | None: ...
    def expand(self, origin: Origin, *, style_period: bool) -> list[tuple[str, Any]]: ...
    def to_lead(self, edge: str, raw: Any) -> DiscoveryLead | None: ...
```

`expand` restituisce coppie `(edge, record grezzo)` con `edge` in
`same_artist | same_label | same_period_style`. Una sola implementazione,
`BandcampSimilar`, in `services/dig_sources/bandcamp.py`, che condivide con
`BandcampSource` i mapper `_lead_from_discography` e `_lead_from_discover`.

### Origine

```python
@dataclass
class Origin:
    artist: str                 # nome pulito
    band_id: int
    title: str | None           # release riconosciuta, None se artist_only
    tralbum_id: int | None
    tralbum_type: str | None    # "a" | "t"
    label: str | None
    label_id: int | None
    tag: str | None             # tag scelto per l'arco stile (norm_name)
    year: int | None
    source_url: str | None
    resolution: str             # "release" | "artist_only"
    discography: list[dict]     # già scaricata: l'arco artista non la ricompra
```

### Risoluzione, tre passi

1. `_clean_artist(track.artist)` → `find_band(nome)`. Se `None`: `resolve`
   ritorna `None`, il servizio produce `SimilarResult(origin=None, leads=[])`
   con `edges` tutti assenti per motivo `no_band`. Nessun'altra richiesta.
2. `band_discography(band_id)`. Match del titolo normalizzato (`_dedup_title`)
   prima con `track.album`, poi con `track.title`. Se trovata:
   `tralbum(band_id=item.band_id, tralbum_id=item.item_id, tralbum_type)` con
   `tralbum_type` derivato da `item_type` (`album → "a"`, `track → "t"`); da lì
   `label`, `label_id`, `tags[].norm_name`, `release_date` (epoch),
   `bandcamp_url`. `resolution="release"`. Se non trovata:
   `resolution="artist_only"`, `label` da `track.label`, `tag` da `track.genre`
   normalizzato con `_tag_norm`, `year` da `track.year`.
3. Scelta del `tag` quando la release è riconosciuta: il primo tag con
   `isloc=False` e `norm_name` fuori da un piccolo insieme generico
   (`electronic`, `music`, `dance`); se nessuno resta, `track.genre`
   normalizzato; se manca anche quello, `tag=None`.

### Archi

- **`same_artist`**: la discografia già in `Origin.discography`, meno la release
  d'origine (stesso `item_id`). Zero richieste.
- **`same_label`**: `band_discography(label_id)`. Assente per `self_released`
  quando `label_id` è nullo o uguale a `band_id`. In `artist_only`, se
  `track.label` esiste: `find_band(track.label)` e poi la sua discografia
  (due richieste); se non esiste, assente per `no_label`.
- **`same_period_style`**, solo con `style_period=True`: `discover(tag)` sul
  primo cursore, **una sola batch da 120 item** (`STYLE_EDGE_ITEMS`, non i 500 del
  dig: qui è un rinforzo e la finestra temporale scarta già molto), filtrata sul client a
  `|year - origin.year| <= PERIOD_YEARS` con `PERIOD_YEARS = 3`. Assente per
  `no_tag` se `tag` è nullo, per `no_year` se manca l'anno, per `off` se
  l'interruttore è spento. Nessuna richiesta quando è assente.

### Ranking e filtri, riusati dal dig

- Deduplica con `_dedup_key` e `_is_owned` contro la libreria intera
  (`_owned_index`), esclusa la release d'origine.
- `TasteProfile.from_tracks(library)`, `_score` con i pesi di `_weights("similar")`:
  trattato come il seme `genre` (nessun peso azzerato; `has_styles` è `False`
  su Bandcamp e azzera da solo il peso stile).
- `_select` con il tetto per artista `_MAX_PER_ARTIST`: qui serve a impedire che
  la discografia dell'artista di partenza mangi la griglia.
- Reason: un `Reason(code=edge, data={...})` per ogni arco che ha raggiunto il
  lead (`same_label` porta `{"label": ...}`, `same_period_style` porta
  `{"tag": ..., "year_from": ..., "year_to": ...}`). Un lead raggiunto da due
  archi porta due reason. `recent` resta come nel dig. `rare_wanted`,
  `deep_cut`, `label_followed`, `artist_collected`, `style_match` non si
  calcolano: i primi due non hanno dati su Bandcamp, gli altri direbbero
  l'ovvio.

### Bilancio degli archi

```python
@dataclass
class EdgeReport:
    count: int | None          # lead prodotti dopo dedup; None se assente
    absent_reason: str | None  # no_band | self_released | no_label | no_tag | no_year | off
```

`SimilarResult.edges: dict[str, EdgeReport]` con le tre chiavi sempre presenti.

### Costo

Da 4 a 6 richieste Bandcamp per chiamata (ricerca band, discografia, dettaglio
release, discografia etichetta, una batch di discover). Nessuna cache,
nessuna colonna nuova su `Track`.

## Endpoint

```text
GET /api/discovery/similar?track_id=<int>&source=bandcamp&style_period=false
```

Risposta `DiscoverySimilarResponse`:

```json
{
  "track_id": 42,
  "source": "bandcamp",
  "origin": {
    "artist": "Jasmín", "title": "Bite The Hand That Feeds You",
    "label": "Hessle Audio", "year": 2025, "tag": "bass",
    "source_url": "https://jasminhoek.bandcamp.com/album/...",
    "resolution": "release"
  },
  "edges": {
    "same_artist": {"count": 4, "absent_reason": null},
    "same_label": {"count": 31, "absent_reason": null},
    "same_period_style": {"count": null, "absent_reason": "off"}
  },
  "leads": [ ... ]
}
```

`origin` è `null` quando l'artista non esiste su Bandcamp. `leads` è nello
stesso formato `DiscoveryLeadOut` del dig, così anteprima, tracklist, aggiungi
e scarica funzionano senza modifiche.

Errori: `404 track_not_found`; `400 discovery_bad_source` per una sorgente
diversa da `bandcamp`; `502 discovery_provider_error` quando Bandcamp non
risponde, come nel dig — "nessun simile" e "Bandcamp giù" restano
distinguibili. Il backend non impone `has_local_file`: la restrizione alle
tracce possedute la fa la UI mostrando l'azione solo lì.

## Interfaccia

### Punto d'ingresso

Bottone "Simili" nella pagina dettaglio traccia (`frontend/app/tracks/page.tsx`),
accanto a "Modifica valori", visibile solo se `has_local_file`. Porta a:

```text
/discovery?similar=<track_id>&style_period=0
```

La riga della griglia libreria non lo prende: il dettaglio è a un click e la
riga è satura.

### Discovery in modalità simili

Stessa pagina `/discovery`, stato nell'URL come il dig. Con il parametro
`similar` la barra dello scavo sparisce e al suo posto c'è un'intestazione
"Partendo da", nuovo componente `frontend/components/discovery-similar-header.tsx`:

- Copertina, artista e titolo della traccia di partenza, link indietro al
  dettaglio.
- La release riconosciuta su Bandcamp con etichetta, anno e link esterno. In
  `artist_only`: "Release non riconosciuta su Bandcamp, uso i tag del file".
- Tre chip per gli archi con il conteggio ("Artista 4", "Etichetta 31", "Stile
  e periodo 44"). Un arco assente si mostra spento con il motivo in `title`:
  autoprodotto, nessuna etichetta nei tag, nessun tag di stile, nessun anno,
  disattivato.
- Interruttore "Stile e periodo": cambia `style_period` nell'URL e rilancia la
  chiamata.

Sotto, la riga delle lenti e la griglia di oggi, identiche. `DiscoveryLeadGrid`
oggi riceve l'intero `dig` per leggere sorgente e pila: si generalizza a
`{source, leads, empty}` dove `empty` è il nodo di stato vuoto passato dal
chiamante. La pagina dig continua a costruire i suoi due stati vuoti (seme
morto, pila corta); la modalità simili passa i propri. La griglia non finge di
avere una pila.

Il job client `dig` della barra dei lavori si riusa con dettaglio
"Simili · artista – titolo".

### Stati vuoti, tre e distinti

- **Artista assente su Bandcamp** (`origin=null`): "Nessuna pagina Bandcamp per
  X", senza consigli di scavare più a fondo perché non c'è fondo.
- **Tutto già posseduto** (origine presente, zero lead): "Possiedi già tutto ciò
  che Bandcamp collega a X", con il suggerimento di accendere stile e periodo
  se è spento.
- **Bandcamp non risponde** (502): alert rosso come nel dig, non uno stato vuoto.

### Testi

Nei due dizionari `frontend/lib/i18n/it.ts` e `en.ts`, entrambi.

## Ambito

Dentro: motore, endpoint, intestazione, generalizzazione della griglia, bottone
nel dettaglio traccia, test, documenti.

Fuori, in spec successive: Discogs come seconda sorgente dietro
`SimilarSource`; remixer e collaboratori come archi; "Simili" da un lead del dig
o dalla wishlist; memoria del perché sui lead salvati; riascolto a freddo della
playlist Discovery; feed continuo dalle etichette possedute.

## Limite accettato

Il match della release per titolo può sbagliare (omonimi, riedizioni,
discografie con "Various"). Si accetta e si rende visibile nell'intestazione
"Partendo da" invece di nasconderlo: se la release riconosciuta è quella
sbagliata l'utente lo vede al primo sguardo, e la cura è nei tag (Organize).

## Test

Backend, unitari su `discovery_similar` con un client Bandcamp finto, un caso
per riga; ogni asserzione va provata rompendo il codice:

- Risoluzione piena: release trovata per album; per titolo quando l'album manca.
- `artist_only`: release non trovata; etichetta e tag dai tag del file quando
  ci sono; archi assenti con `no_label` / `no_tag` quando non ci sono.
- Artista assente: `origin=None`, zero lead, una sola richiesta al client.
- `same_label` assente per `self_released` quando `label_id == band_id` o nullo.
- `same_period_style`: primo tag non generico scelto, `electronic` e tag di
  luogo saltati; finestra di `PERIOD_YEARS` applicata su entrambi i lati; zero
  richieste `discover` con l'interruttore spento.
- La release d'origine esclusa dai lead; i posseduti esclusi; un lead da due
  archi porta due reason.
- Tetto per artista applicato.
- Router: 404 su track inesistente, 400 su sorgente diversa da `bandcamp`, 502
  su `BandcampError`.

Frontend, vitest:

- L'intestazione nelle tre risoluzioni (`release`, `artist_only`, `null`) e i
  chip spenti con il motivo.
- La pagina rilancia la chiamata al cambio dell'interruttore e riflette
  `style_period` nell'URL.
- `DiscoveryLeadGrid` generalizzata rende identico il caso dig (test esistenti
  verdi senza modifiche di sostanza).

Nessun e2e nuovo: modale tracklist e salvataggio sono già coperti da quelli
del dig.

## Documenti

Sezione "Similar" in `docs/API.md` (dopo "Acquiring"), riga Discovery in
`docs/ROADMAP.md`, voce in `PROGRESS.md`. L'expand Last.fm resta citato solo
come storia nell'archivio.
