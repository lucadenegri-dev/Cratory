# Coda dei download (sotto-progetto B)

Data: 2026-08-15. Stato: approvata a voce, in attesa di revisione scritta.

## Problema

L'acquisizione oggi è un job monolitico: un thread, uno stato in un dizionario
in memoria, **un download alla volta**. Le conseguenze che si sentono usando
l'app: non si può accodare un lotto di tracce e andarsene, una traccia lenta
blocca tutte le altre, non si vede cosa stia facendo il job né lo si può
correggere, e un riavvio del backend cancella ciò che stava succedendo.

La coda risolve tutti e quattro i punti e diventa **l'unica strada per
acquisire un file**: auto-pick da wishlist, azioni di gruppo, candidato scelto
a mano nel modal di ricerca, download SoundCloud.

Fuori scope: riordino libero a trascinamento, messa in pausa della coda,
ritentativi automatici. Gli altri job in memoria dell'app (analisi, import
streaming, Shazam) restano come sono: questa coda è specifica per
l'acquisizione.

## Decisioni chiave

- Coda persistente in SQLite + pool di thread **dentro il processo backend**.
  Niente processo separato (attrito operativo per un'app locale mono-utente),
  niente delega della coda a slskd (la parte lenta è la ricerca, che è tutta
  di Cratory e non delegabile).
- **3 download in parallelo di default**, regolabile dalle Impostazioni.
- Il vincolo "un download alla volta" sparisce, e con lui il
  `409 download_already_running` e l'avviso «un download è già in corso» nel
  modal di ricerca.
- `GET /api/downloads/status` mantiene la forma che ha oggi, derivata da
  aggregati sulla coda: la barra di avanzamento globale e il poller del
  frontend non vanno riscritti.

## Modello dati

Una tabella, **`DownloadQueueItem`**. `ensure_schema` fa `create_all` sulle
tabelle registrate, quindi non serve una migrazione scritta a mano.

Campi: `track_id` (FK `tracks` — l'acquisizione lega sempre un file a una
traccia esistente), `kind` (`soulseek_auto` | `soulseek_chosen` |
`soundcloud`), `payload` JSON (il candidato scelto per `soulseek_chosen`, null
altrimenti), `position` per l'ordine, `attempts`, `phase`
(`searching` | `downloading` | null), `bytes_done`/`bytes_total` per la barra
per-item, e i tempi `enqueued_at`/`started_at`/`finished_at`.

Due campi distinti per non avere due verità sullo stesso fatto:

- **`state`** — ciclo di vita: `queued` → `running` → `done`, più `cancelled`.
  Dice se il lavoro è stato eseguito.
- **`outcome`** — risultato, valorizzato quando `state` diventa `done`, con lo
  stesso vocabolario già in uso sulla traccia: `downloaded` | `needs_review` |
  `not_found` | `failed`.

Una traccia scaricata ma con durata sospetta è quindi
`state=done, outcome=needs_review`, senza stati ibridi.

**La coda non sostituisce `last_download_outcome` sulla traccia**: quello resta
e continua ad alimentare i tab della wishlist. La coda racconta *come sta
andando adesso*, la traccia *com'è finita*; il runner scrive l'esito sulla
traccia a fine lavoro, esattamente come fa il job oggi.

**Deduplica:** accodare una traccia che ha già un item `queued` o `running` non
crea un secondo item. Senza questo, "accoda la playlist" due volte raddoppia la
coda.

**Ricucitura al riavvio:** all'avvio ogni item rimasto `running` torna
`queued`, perché dopo un riavvio nessun worker è più vivo.

**Nessun ritentativo automatico:** un item fallito resta con il suo errore e il
conteggio dei tentativi. L'auto-pick prova già fino a quattro utenti diversi al
suo interno; un secondo livello automatico martellerebbe Soulseek senza averlo
chiesto. Riprovare resta un gesto dell'utente (i tab «fallite»/«non trovate» e
l'azione di gruppo esistente).

## Dispatcher e worker

Tre moduli con confini netti, al posto dell'unico file di oggi:

- **`backend/app/services/download_queue.py`** — servizio dati: accoda (con
  deduplica), elenca, annulla, riordina, rivendica il prossimo item, chiude un
  item con il suo esito. Nessun thread, nessuna rete: testabile senza slskd.
- **`backend/app/services/download_dispatcher.py`** — il pool: tiene occupati
  fino a N slot, pesca un item, lancia un thread daemon, ripesca quando uno
  slot si libera. Non sa cosa sia un download.
- **`backend/app/services/download_runner.py`** — l'esecuzione di un singolo
  item: ricerca, scelta, trasferimento e aggancio del file per Soulseek; yt-dlp
  per SoundCloud. In gran parte il codice esistente in
  `soulseek_download_job.py`, estratto dalla sua orchestrazione monolitica.

**Rivendicazione dell'item:** due worker non devono prendere lo stesso lavoro.
Essendo un solo processo, un lock in-process attorno a "prendi il primo in
attesa e marcalo in corso" è sufficiente e provabile; l'UPDATE resta comunque
condizionato a `state='queued'` come seconda cintura, così due processi
eventuali si accorgerebbero di aver perso la gara invece di duplicare il
download. Il DB è già in WAL con `busy_timeout=5000` e
`check_same_thread=False`: la scrittura concorrente da più thread è già
configurata.

**Il dispatcher si sveglia** all'avvio dell'app (dove prima ricuce i `running`),
a ogni accodamento e alla fine di ogni item.

**Annullamento di un item in corso:** scrive `cancelled` nel DB; il worker
guarda il flag tra una fase e l'altra e a ogni poll del trasferimento, e se c'è
un transfer vivo su slskd ne chiede la cancellazione (`cancel_download`, già
usato per i transfer abbandonati).

**Numero di slot:** letto dalle impostazioni a ogni riempimento, non all'avvio.
Cambiarlo ha effetto senza riavviare; abbassarlo non uccide i worker in corso,
semplicemente non ne parte di nuovi finché non si rientra sotto la soglia.

**Cosa sparisce:** lo stato globale in memoria con il suo lock, le cinque
funzioni `start_*_job` (diventano riempimenti della coda), la guardia
`is_running()` e il `409 download_already_running` su tutti gli endpoint.

## API

Un router nuovo, **`backend/app/routers/download_queue.py`**, sotto
`/api/downloads/queue` (`downloads.py` è già lungo e continuerebbe a crescere):

- `GET` la coda: item divisi per stato, con fase e byte di chi sta scaricando.
- `POST` per accodare: body con una **lista** di `track_ids` (il singolo è il
  caso da uno), un `kind` che vale per l'intero lotto (default `soulseek_auto`;
  `soundcloud` va chiesto esplicitamente) e il candidato scelto quando arriva
  dal modal. Il candidato è ammesso **solo** con esattamente un `track_id` e
  implica `kind=soulseek_chosen`: un candidato è per definizione la scelta su
  una traccia sola, e accettarlo con una lista sarebbe ambiguo. Risponde con
  quanti accodati e quanti saltati per deduplica, così l'interfaccia può dire
  «12 accodate, 3 erano già in coda».
- `DELETE` di un item: annulla, valido sia da `queued` sia da `running`.
- Rimetti un item in cima. Niente riordino libero: «in cima» copre quasi tutto
  il bisogno a una frazione del costo.
- Annulla tutti gli item in attesa.
- Svuota lo storico delle finite (altrimenti cresce senza fine).

**Gli endpoint esistenti restano dove sono** — «scarica playlist», «riprova
tutte», download del candidato scelto, download SoundCloud — ma cambiano
mestiere: accodano invece di avviare un job e rispondono con quanto hanno
accodato. I punti di chiamata del frontend non si spostano.

## Frontend

**La pagina `/downloads`** (va rimosso il redirect verso `/wishlist` in
`frontend/next.config.ts`) ha tre fasce: **in corso**, con fase e barra per
traccia; **in attesa**, in ordine, con annulla e «in cima»; **fatte**, lo
storico recente raggruppato per esito, con «svuota». In testa il conteggio e
gli slot occupati sul totale disponibile. La pagina si aggiorna da sé mentre è
aperta, più in fretta del poller globale quando ci sono item vivi.

**Nella wishlist** arrivano le checkbox di riga e una barra che compare con la
selezione: «Accoda N tracce». È la parte di UI più nuova.

**Impostazioni:** il numero di download in parallelo (default 3).

**i18n:** ogni testo nuovo in entrambi i dizionari, `it.ts` ed `en.ts`.

## Test

- **Concorrenza (il più importante):** due claim lanciati in parallelo, uno
  solo deve vincere l'item.
- **Servizio dati:** deduplica; annullo da `queued` e da `running`; «in cima»;
  ricucitura al riavvio (i `running` tornano `queued`).
- **Dispatcher:** rispetta N slot; riempie quando uno si libera; rilegge il
  valore aggiornato dalle impostazioni senza riavvio.
- **Runner (regressione):** gli esiti scritti sulla traccia restano identici a
  quelli odierni — i tab della wishlist ci si appoggiano.
- **API:** accodamento a lotti con deduplica, annullo, «in cima», e
  `GET /api/downloads/status` che mantiene la forma attuale.
- **Frontend (vitest):** la vista coda (tre fasce, azioni) e la selezione
  multipla nella wishlist.
- **E2e:** accoda due tracce dalla wishlist e ritrovale in `/downloads`.

## Criteri di successo

- Si selezionano venti tracce dalla wishlist, si accodano in un gesto e la coda
  le macina da sola con tre download in volo.
- Riavviando il backend a coda piena, la coda riparte da dove era.
- Da `/downloads` si vede cosa sta scendendo e a che punto, e si può annullare
  o dare precedenza a una traccia.
- Nessuna regressione sugli esiti scritti sulla traccia né sui tab della
  wishlist.
