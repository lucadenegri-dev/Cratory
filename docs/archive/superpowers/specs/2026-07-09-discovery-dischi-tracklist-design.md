# Discovery dig — dal lead-traccia al lead-disco: griglia, tracklist e "per dopo"

Data: 2026-07-09
Stato: design approvato, pronto per il piano di implementazione.

## Obiettivo

Correggere il modello concettuale del flusso **dig** ("Scava", `discovery_dig.py`):
un lead Discogs non è una traccia, è un **disco** (release). Lo slice ridisegna la
presentazione dei risultati come **griglia di copertine** ("cassa di dischi"), apre
ogni disco su un **pannello tracklist** con la tracklist reale da Discogs, e sposta le
azioni al livello giusto: per **singola traccia**, con due esiti — **"Scarica ora"**
(auto-pick Soulseek immediato) e **"Per dopo"** (import + playlist di sistema
"Scoperte"). Implementa il punto "tracklist per-release" lasciato esplicitamente a
backlog dalla spec precedente
(`docs/superpowers/specs/2026-06-28-discovery-dig-gusto-spiegazioni-design.md`).

## Motivazione

Il difetto è alla radice del parsing dei risultati. Discogs
`/database/search?type=release` restituisce oggetti in cui il campo `title` è
**"Artista - Titolo della RELEASE"** (es. "Aphex Twin - Selected Ambient Works
85-92"), non il titolo di un brano. `_lead_from_release` (`discovery_dig.py`) fa:

```python
artist, _, track_title = title.partition(" - ")
```

e tratta la seconda metà come il titolo di **una traccia**. Per una release
multi-traccia (EP, LP, compilation sfuggita al filtro `_BAD_FORMATS`) il lead
rappresenta erroneamente l'intero disco come "una traccia". Le conseguenze a valle:

- **"Salva"** (`POST /api/discovery/add`) crea in libreria una `Track` che si chiama
  come un EP intero — un dato sbagliato che poi inquina dedup e set builder.
- **"Download"** cerca su Soulseek `artist` + `title` del lead aspettandosi un file:
  ma nessun file si chiama come il titolo di un EP, quindi la ricerca fallisce o —
  peggio — aggancia il file sbagliato.

Il modello dati `Track` e tutta la filiera download (`soulseek_select.py`,
`soulseek_download_job.py`) ragionano **per traccia singola**: sono corretti così e
questa spec non li cambia. Quello che cambia è il significato del lead: un lead è un
disco che **si apre** sulla sua tracklist vera, e le azioni per-traccia vivono lì.

Bonus che si sblocca gratis: la tracklist Discogs porta la **durata** di ogni brano,
che oggi il flusso Discovery non ha mai. La durata è il discriminatore più forte del
ranking Soulseek (`_duration_score` in `soulseek_select.py`: distingue radio edit da
extended mix), ma dal dig `track.duration_seconds` è sempre `None` e il segnale resta
neutro. Con la tracklist il gap si chiude.

## Vincoli (dalle regole non negoziabili del progetto e dalle decisioni prese)

- Motore **deterministico**, nessuna AI in questo slice.
- **Nessuna tabella DB nuova, nessun job in background nuovo.**
- Fetch della tracklist Discogs **lazy**: solo all'apertura del pannello, mai in
  batch/eager per tutta la griglia (rate limit Discogs: ~25/min senza token,
  ~60/min con token).
- Il modello `Track` e il download Soulseek restano **per traccia singola**.
- La modalità **Expand** (Last.fm) è invariata, non toccata da questa spec.
- Riuso deliberato dell'infrastruttura esistente e già idempotente:
  `import_single_track`, `add_track_to_playlist`, job Soulseek, flusso
  "da sistemare" (`GET /api/downloads/pending`), bulk download playlist
  (`POST /api/downloads/playlist/{playlist_id}`).
- Design system "editorial archive": `rounded-none`, bordi hairline, nessuna ombra
  (pattern del componente `Modal` in `frontend/components/ui.tsx`).

## Componenti

### 1. Il lead diventa un disco: `format_badge` + `discogs_id` esposti

`DiscoveryLead` (dataclass, `discovery_dig.py`) ha già `discogs_id: int | None` ma
non lo espone mai: `DiscoveryLeadOut` (`schemas.py`) e `_lead_out`
(`routers/discovery.py`) vanno estesi per includerlo — è la chiave con cui il
frontend apre il pannello tracklist.

Nuovo campo `format_badge: str | None` su `DiscoveryLead`/`DiscoveryLeadOut`,
derivato in `_lead_from_release` dal campo `format` già presente nella risposta di
`/database/search` (già letto per il filtro `_BAD_FORMATS`, ma il valore raw non è
mai salvato sul lead): **zero chiamate di rete aggiuntive**. Normalizzazione
deterministica, primo match in ordine di priorità sui descrittori (lowercase):

| priorità | descrittore Discogs contiene | badge |
|---|---|---|
| 1 | `ep` | `EP` |
| 2 | `lp` | `LP` |
| 3 | `album` | `Album` |
| 4 | `single` | `Single` |
| 5 | `12"` | `12"` |
| — | nessun match / campo assente o vuoto | `None` (nessun badge sulla cella) |

### 2. `DiscogsClient.get_release(id)` (nuovo, `integrations/discogs.py`)

Nuovo metodo sullo stesso pattern di `search_releases`: `GET /releases/{id}` via
`_get`. Differenza deliberata: mentre `search_releases` degrada a lista vuota (una
ricerca fallita non deve rompere il dig), qui l'errore Discogs **solleva
`DiscogsError`** — il chiamante deve poterlo distinguere e mostrare, mai propagarlo
come 500 grezzo. Dal payload servono: titolo release, artista, tracklist (lista di
`{position, title, duration}` dove `duration` è una stringa `"mm:ss"` talvolta
vuota), etichetta, anno, immagine.

### 3. Endpoint `GET /api/discovery/release/{discogs_id}` (nuovo, `routers/discovery.py`)

Chiama `get_release`, normalizza e restituisce un nuovo schema Pydantic
`DiscogsReleaseOut`:

```
discogs_id:   int
title:        str
artist:       str
format_badge: str | None
thumb_url:    str | None
discogs_url:  str | None
year:         int | None
label:        str | None
tracks:       list[{position: str, title: str, duration_seconds: int | None}]
```

Normalizzazione durata: `"mm:ss"` → secondi interi; stringa vuota o non parsabile →
`None` (il ranking Soulseek tratta già l'ignoto come neutro, mai penalizzato).
`DiscogsError` → HTTP 502 con il messaggio leggibile dell'eccezione (stesso pattern
di `LastFMError` su `/expand`).

### 4. Playlist di sistema "Scoperte" + azione "Per dopo"

- **Playlist "Scoperte"**: `Playlist(platform="manual", kind="playlist",
  name="Scoperte")`. Serve un helper `get_or_create` idempotente: lookup per nome,
  crea solo se assente, non duplica mai su chiamate ripetute. Collocazione esatta
  (`repositories.py` o `services/discovery_dig.py`) demandata al piano di
  implementazione.
- **"Per dopo"** (per riga-traccia del pannello): un'unica chiamata che fa
  `import_single_track` (idempotente, passa anche `duration_seconds` dalla
  tracklist) + `add_track_to_playlist` sulla playlist "Scoperte" (idempotente, non
  duplica la membership). Nessun download. Realizzabile come estensione di
  `POST /api/discovery/add` o endpoint nuovo: nome esatto di endpoint/schema
  demandato al piano; la spec fissa il comportamento (un colpo solo, doppio click
  innocuo).
- **"Tutte per dopo"** (in testa al pannello): itera l'azione per-traccia su tutte
  le righe della tracklist. Nessun endpoint bulk nuovo: per un EP/LP sono poche
  chiamate idempotenti, sproporzionato ottimizzarle.
- **Bulk download** delle "Scoperte": riusa l'endpoint esistente
  `POST /api/downloads/playlist/{playlist_id}` dalla pagina playlist. Nessuna nuova
  UI di bulk-action.

Nota dedup: `import_single_track` mette la traccia in libreria, e `owned_keys` in
`dig()` è costruito su **tutta** la libreria (`_library_tracks`). Quindi una traccia
segnata "per dopo" **non ricompare come lead** al prossimo dig sullo stesso seme:
nessuno stato di sessione "già visto/agito" da mantenere lato server.

### 5. "Scarica ora": auto-pick con la durata Discogs

Per riga-traccia del pannello: `import_single_track` (con `duration_seconds` dalla
tracklist) e poi la macchina job Soulseek esistente
(`soulseek_download_job.py`, riuso di `start_track_job`) in modalità **auto-pick**
— la stessa del flusso playlist: candidato non pre-scelto, cascata di varianti di
query, `rank_candidates` con soglia di confidenza. Nessun modal di scelta manuale
del file (il vecchio modal di `LeadRow` viene rimosso).

È qui che si chiude il gap della durata: `_process_item` legge
`track.duration_seconds` come `expected_duration` per `rank_candidates` /
`_duration_score`, ma dal flusso Discovery quella durata non è mai stata valorizzata.
Con la durata della tracklist Discogs sul `Track` importato, l'auto-pick distingue le
versioni (radio edit vs extended) e la verifica post-download sulla durata reale del
file diventa efficace anche per i lead del dig.

Esiti dubbi o falliti (confidenza sotto soglia, durata incoerente, non trovato)
restano nel flusso **"da sistemare"** esistente (`GET /api/downloads/pending`): il
pannello non duplica retry né scelta manuale, linka lì.

### 6. UI: griglia "cassa di dischi" + pannello tracklist (`frontend/app/discovery/page.tsx`)

Il componente `LeadRow` (righe ~314-443, incluso il modal di download righe
~419-440) viene **sostituito** da:

- **Cella di griglia**: copertina (`thumb_url`, fallback icona `Disc3` invariato),
  **badge formato sempre visibile** sulla cella, e una **striscia di dettagli**
  (etichetta · anno · chip reason) che appare su hover/focus della cella. La cella è
  attivabile da tastiera: click o Enter aprono il pannello tracklist del disco
  (fetch lazy di `GET /api/discovery/release/{discogs_id}` solo in quel momento).
- **Pannello tracklist**: side panel o modal coerente col design system
  (`rounded-none`, bordo hairline, nessuna ombra — riuso del pattern `Modal` di
  `frontend/components/ui.tsx`). Testata: copertina, artista, titolo release,
  etichetta · anno, badge formato, link Discogs, bottone **"Tutte per dopo"**. Ogni
  riga-traccia: posizione, titolo, durata (se presente) e i due bottoni **"Scarica
  ora"** / **"Per dopo"**. "Salva" come azione diretta sul disco **sparisce**: resta
  solo dentro il pannello, per singola traccia.
- **Filtri leggeri sulla griglia**: chip di formato (Tutti / LP / EP / 12" / Album),
  calcolati client-side dal `format_badge` già sul lead, + un ordinamento
  (**Punteggio** [default, l'ordine server] / **Più recenti** [anno decrescente]).
  Nessun raggruppamento server-side: gli 80 lead e il ranking restano invariati.

### 7. Stato del dig in query string

Seme (tipo e valore), adventurousness e riferimento di gusto
(`taste_playlist_id`) vivono nei **query params dell'URL**: il dig è bookmarkabile,
sopravvive a back/forward del browser, e al ritorno sulla pagina con parametri
presenti si **ri-lancia lo stesso dig** (chiamata deterministica: nessuna cache
client-side da mantenere o invalidare). Lo stato di apertura del pannello tracklist
resta effimero, fuori dall'URL. Next.js 16 ha breaking changes rispetto al training
data (`frontend/CLAUDE.md`): la spec fissa il comportamento atteso, l'API esatta di
lettura/scrittura dei query params si verifica nel piano/implementazione.

## Gestione errori

| caso | comportamento |
|---|---|
| Release senza tracklist valorizzata (capita) | Il pannello mostra comunque una riga di ripiego con il titolo della release e le due azioni "Scarica ora"/"Per dopo" (durata `None`): mai un vicolo cieco vuoto. |
| Auto-pick fallito o dubbio | Resta nel flusso "da sistemare" esistente (`GET /api/downloads/pending`); il pannello linka lì, non duplica retry/scelta manuale. |
| Rate limit / errore Discogs sul fetch della release | Errore leggibile dentro il pannello (pattern `Alert tone="danger"` già usato nella pagina); il resto della griglia resta interattivo; nessun retry automatico. |
| Thumbnail assente | Fallback icona `Disc3` esistente, invariato. |

## Test

Backend (pattern esistenti, nessuna rete):

- `get_release` con http finto (stesso pattern `_FakeHttp` di
  `backend/tests/test_discogs.py`): payload ok → dati estratti; errore HTTP →
  `DiscogsError`.
- Endpoint release con tracklist mock: durata `"mm:ss"` → secondi interi; durata
  vuota → `None`.
- "Per dopo" idempotente: doppio click sulla stessa traccia non duplica né la
  `Track` né la membership nella playlist "Scoperte".
- `get_or_create` della playlist "Scoperte": chiamate ripetute non creano duplicati.
- `format_badge` su vari valori del campo `format` Discogs, incluso
  assente/vuoto → `None`, e la priorità quando più descrittori coesistono.

Frontend: nessun framework di test e2e esistente per questa pagina (verificato).
Verifica manuale via browser dev tool su: apertura pannello tracklist, "Tutte per
dopo", filtro formato, stato query string che sopravvive a un reload.

## Fuori scope

- **Modalità Expand** (Last.fm): invariata.
- **Fetch eager/batch delle tracklist** per tutta la griglia con cache persistente:
  valutato e scartato — 80 chiamate `GET /releases/{id}` per dig violerebbero i rate
  limit Discogs e richiederebbero job in background e cache nuovi, sproporzionati
  per un tool mono-utente. Il fetch lazy all'apertura del pannello costa una
  chiamata per disco effettivamente esplorato.
- **Scelta manuale del file Soulseek** dentro il pannello tracklist: resta solo
  l'auto-pick; la scelta manuale esiste già altrove nell'app per altri flussi.
- **Persistenza di uno stato "lead scartato/dismisso" lato server**: risolto
  implicitamente dal dedup esistente su import, nessun meccanismo nuovo.
- **Rinominare il bottone "DIG"** o altre modifiche cosmetiche minori non legate al
  flusso disco→tracklist: non richieste per questo slice.

## Decisioni consolidate

- Un lead **è un disco**: si apre sulla tracklist Discogs reale; salvataggio e
  download esistono solo per singola traccia, dentro il pannello.
- Layout risultati: **griglia di copertine** con badge formato sempre visibile +
  striscia dettagli (etichetta · anno · reason) su hover/focus (scelta ibrida).
- Fetch tracklist **lazy** (solo all'apertura del pannello); nessuna tabella DB
  nuova, nessun job in background nuovo.
- Download **sempre auto-pick** (niente scelta manuale nel pannello); esiti
  dubbi/falliti al flusso "da sistemare" esistente.
- "Per dopo" = `import_single_track` + membership nella playlist di sistema
  **"Scoperte"** (entrambi idempotenti); "Tutte per dopo" itera l'azione
  per-traccia; bulk download via `POST /api/downloads/playlist/{playlist_id}`
  esistente.
- Il dedup library-wide esistente (`owned_keys`) copre anche le tracce "per dopo":
  nessuno stato "già visto/agito" lato server.
- Stato del dig (seme/valore/adventurousness/riferimento gusto) in **query string**:
  bookmarkabile, back/forward, ri-lancio deterministico senza cache client.
- Filtri client-side (chip formato dal `format_badge`) + ordinamento
  Punteggio/Più recenti; ranking e cap server-side invariati.
- La durata dalla tracklist Discogs valorizza `Track.duration_seconds` e chiude il
  gap del discriminatore di durata nel ranking Soulseek per il flusso Discovery.
