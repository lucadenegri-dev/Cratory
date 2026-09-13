# Backup e ripristino dei dati utente

Data: 2026-09-13. Stato: approvata a voce.

## Cosa

Cratory conserva in `DATA_DIR` dati che il disco non può ricostruire: voti,
wishlist, storico download, set, playlist manuali, cover caricate, credenziali
e token. Oggi non esiste un modo di salvarli né di rimetterli a posto. Questa
spec aggiunge un backup in un solo file zip, creabile da Impostazioni e — su
richiesta — prima di un aggiornamento in-place, e un ripristino dall'app che si
completa con un riavvio.

Decisioni prese a voce, che il resto del documento non rimette in discussione:

- **Il backup contiene tutto, credenziali comprese**: DB intero (con le chiavi
  `cfg.*` segrete e i token Spotify), `.env`, `slskd.yml` (password Soulseek).
  Un ripristino rimette l'app com'era, senza rifare il wizard. Il file va
  custodito come lo `.env`, e il README lo dice.
- **Innesco**: manuale da Impostazioni, e prima dell'aggiornamento l'updater
  *chiede* se farlo, dicendo quanto spazio occuperebbe. Nessun backup
  periodico.
- **Destinazione**: «salva con nome» ogni volta, con il dialogo nativo. Nessuna
  cartella configurata.
- **Ripristino dall'app, con riavvio**: si sceglie il file, si legge un
  riepilogo, si conferma, l'app riparte con i dati del backup.

Fuori scope: backup periodico, rotazione, backup della cartella download di
slskd (sono file audio, la libreria è il disco), esportazioni parziali,
piattaforme diverse da macOS per il dialogo nativo (c'è un ripiego, vedi §4).

## Perché lo scambio avviene a freddo

Il ripristino non tocca mai il DB vivo. Delle tre strade valutate — staging e
scambio al riavvio; scambio a caldo in-process (`engine.dispose()`, scambio,
`SessionLocal.configure(bind=…)`, ricarica di cache e dispatcher); scambio
fatto dal guscio Rust come l'updater — vince la prima: nessun file sostituito
sotto una connessione aperta, nessun job da fermare, un solo punto di scambio
deterministico e testabile senza server. Il prezzo è che nel browser di
sviluppo, dove non c'è un guscio che riavvia, il ripristino si completa
riavviando il backend a mano; nel guscio lo fa `riavvia_app`, che esiste già.

> **Correzione (review finale, 2026-09-13).** «`riavvia_app`, che esiste già»
> era vero solo a metà: la funzione esisteva ma nasceva per la via d'uscita
> dell'updater, dove il backend è già stato terminato. Chiamata a backend vivo
> non basta — `app.restart()` non passa per `RunEvent::Exit`, quindi
> `backend::termina` non gira e il vecchio uvicorn resta sulla porta 8000 col DB
> aperto; il guscio rilanciato la trova occupata e muore sul dialogo «Cratory è
> già aperto», senza mai re-importare `main.py`. `riavvia_app` ora chiama
> `backend::termina(&app)` prima di `app.restart()` (idempotente: `termina` fa
> `take()` dell'unico figlio tracciato). Vedi anche §5.

## 1. Il servizio (`backend/app/services/backup.py`)

Modulo deterministico, senza AI, senza HTTP. Legge `paths.DATA_DIR` e
`settings.database_url` come attributi di modulo (monkeypatchabili), mai per
import di nome.

### Contenuto

`contenuto()` restituisce la lista di ciò che entra nel backup, ognuno con
percorso, dimensione e presenza:

| Voce | Percorso | Obbligatoria |
|---|---|---|
| database | il file di `database_url` | sì |
| cover caricate | `DATA_DIR/data/covers/` (ricorsiva) | no |
| `.env` | `DATA_DIR/.env` | no |
| `slskd.yml` | `DATA_DIR/data/slskd.yml` | no |

Restano fuori, di proposito: `cover_cache`, `thumb_cache`, `logs/`,
`slskd.pid`, `slskd.log`, `slskd-downloads/`, `-wal` e `-shm` (assorbiti dallo
snapshot). Se in futuro si aggiunge una voce, si aggiunge qui e nella lista di
`applica_se_in_attesa` (§2): sono le due sole liste, e devono coincidere.

La dimensione del DB è `page_count × page_size` meno `freelist_count ×
page_size` (tre `PRAGMA`), non la somma dei file su disco: il WAL può essere
grande quanto il DB e sparire al checkpoint successivo, e la stima serve a
dire all'utente quanto peserà lo zip, non quanto pesa la cartella.
`stima_byte()` è la somma della lista.

### Creazione

`crea(destinazione: Path) -> EsitoBackup` con `EsitoBackup(percorso, byte,
creato_il)`.

1. Se `destinazione` non finisce in `.zip`, lo si aggiunge.
2. Il DB entra via `VACUUM INTO '<tmp>'` eseguito su una connessione sqlite3
   dedicata: snapshot transazionale coerente anche con il WAL aperto e altri
   worker che scrivono; nessun job va fermato. La sqlite disponibile è 3.53
   sia nel venv sia nel runtime del bundle (`VACUUM INTO` richiede ≥ 3.27).
3. Lo zip si scrive in un file temporaneo nella stessa cartella della
   destinazione (`<nome>.zip.parziale`) e si rinomina alla fine: un backup
   interrotto non lascia mai uno zip a metà con il nome buono. In caso di
   eccezione il parziale e il temporaneo del DB vengono rimossi e
   l'eccezione risale.
4. Membri, con nomi fissi: `manifest.json`, `data/djassistant.db`,
   `data/covers/<file>…`, `.env`, `data/slskd.yml`. Il nome del DB dentro lo
   zip è sempre `djassistant.db` a prescindere da `database_url`: il
   ripristino lo rimette dove `database_url` punta *al momento del
   ripristino*.
5. `manifest.json`: `{"formato": 1, "app_version": "<app_version()>",
   "creato_il": "<ISO 8601 UTC>", "membri": [{"nome", "byte"}…]}`.
6. A fine corsa `app_state["last_backup_at"] = creato_il`.

Un lock di modulo (`threading.Lock`, non bloccante) impedisce due backup
contemporanei: il secondo solleva `BackupInCorso`.

`nome_di_default()` → `cratory-backup-AAAAMMGG-HHMM.zip` in ora locale.

### Ispezione

`ispeziona(archivio: Path) -> Riepilogo` apre lo zip senza applicare nulla e
restituisce `Riepilogo(creato_il, app_version, tracce, playlist, membri,
ha_credenziali)`. Estrae il DB in una cartella temporanea e vi legge in sola
lettura (`mode=ro`) `PRAGMA integrity_check`, `SELECT count(*) FROM tracks` e
`FROM playlists`. `ha_credenziali` è vero se lo zip contiene `.env` o
`slskd.yml`.

Rifiuta con `BackupNonValido(codice)`, codici stabili tradotti dal frontend:

| Codice | Quando |
|---|---|
| `archivio_non_valido` | non è uno zip, o `testzip()` trova un membro corrotto |
| `manifest_assente` | manca `manifest.json`, o non è JSON, o `formato` ≠ 1 |
| `db_assente` | manca `data/djassistant.db` |
| `db_corrotto` | `integrity_check` ≠ `ok`, o il file non è un DB sqlite |
| `versione_piu_recente` | `app_version` del manifest > versione in esecuzione, confrontate come tuple di interi (le parti non numeriche valgono 0); versioni uguali o più vecchie passano perché `ensure_schema` migra solo in avanti. Se l'app in esecuzione riporta la versione di ripiego `0.0.0-dev` (checkout senza `VERSION`), il controllo si salta: altrimenti in sviluppo ogni backup fatto da un'app vera verrebbe rifiutato. |

## 2. Il ripristino in due tempi

Cartelle sotto `DATA_DIR/data/`: `restore-staging/` (l'archivio estratto e
validato, in attesa di conferma), `restore-pending.json` (il marker: la
conferma), `pre-restore/` (i dati messi da parte dall'ultimo ripristino).

- `prepara(archivio) -> Riepilogo`: `ispeziona`, poi svuota e ripopola
  `restore-staging/` con i membri estratti e con il riepilogo serializzato in
  `riepilogo.json`. **Non scrive il marker.** Rifiuta con `JobInCorso` se
  `audio_analysis_job.is_running()`, `streaming_import_job.is_running()`,
  `mix_identify_job.is_running()` o la coda download ha item `running`
  (`download_queue`): non perché lo scambio li disturberebbe — avviene al
  riavvio — ma perché il riavvio li interromperebbe, e l'utente deve saperlo
  prima di scegliere.
- `conferma()`: ripete il controllo dei job, poi scrive
  `restore-pending.json` = `{"staging": "<percorso>", "confermato_il": …,
  "riepilogo": {…}}`. Senza staging solleva `NienteDaRipristinare`.
- `annulla()`: rimuove staging e marker, idempotente.
- `applica_se_in_attesa() -> EsitoRipristino | None`: se il marker manca
  restituisce `None` e non tocca niente. Altrimenti:
  1. Se lo staging manca o non contiene `data/djassistant.db`, cancella il
     marker, logga, restituisce un esito `fallito` con motivo. Meglio
     ripartire con i dati vecchi che con metà dei nuovi.
  2. Svuota `pre-restore/` e vi sposta, se esistono, DB + `-wal` + `-shm`,
     `covers/`, `.env`, `slskd.yml` attuali. Si conserva **solo l'ultimo**
     stato pre-ripristino: è una rete di sicurezza, non un secondo sistema di
     backup.
  3. Sposta i membri dallo staging al loro posto (`rename`, stessa
     partizione), crea `covers/` anche se il backup non ne aveva.
  4. Cancella marker e staging, restituisce `EsitoRipristino(applicato_il,
     backup_creato_il, backup_app_version, tracce, playlist, stato="ok")`.
  L'esito viene poi salvato in `app_state["last_restore"]` (JSON) dal
  chiamante, a DB aperto.

### Dove si applica: prima di `load_dotenv`

`main.py` chiama `load_dotenv(paths.DATA_DIR / ".env")` a livello di modulo,
prima di importare `app.core.config`, perché alcune variabili vengono lette da
`os.environ`. Un `.env` ripristinato deve valere già a *questo* avvio,
altrimenti l'utente riparte con le credenziali vecchie in memoria e quelle
nuove sul disco. Quindi `applica_se_in_attesa()` si chiama in `main.py`
**subito dopo l'import di `paths` e prima di `load_dotenv`**, non nel
`lifespan`. A quel punto il logging non è configurato: il servizio usa il
`logging` di modulo (che senza handler stampa i WARNING+ su stderr, raccolti
dal guscio nel suo log) e restituisce l'esito, che `main.py` tiene in una
variabile di modulo; il `lifespan`, dopo `ensure_schema`, lo scrive in
`app_state`. Nessun DB viene aperto prima di quel punto: `engine` viene
costruito all'import di `app.db` ma SQLAlchemy non connette finché nessuno lo
usa, e `verifica_scrivibile` tocca solo un file sonda.

Per lo stesso motivo il servizio non importa `app.core.config` a livello di
modulo: il percorso del DB lo ricava da `settings` importato dentro le
funzioni, dopo che `load_dotenv` ha fatto il suo lavoro.

## 3. HTTP (`backend/app/routers/backup.py`, prefisso `/api/backup`)

Solo trasporto; ogni eccezione del servizio diventa un `api_error` con lo
stesso codice.

| Metodo | Percorso | Corpo / risposta |
|---|---|---|
| GET | `/api/backup/estimate` | `{byte, voci: [{nome, byte, presente}], last_backup_at, nome_di_default, picker_disponibile}` |
| POST | `/api/backup` | `{path: string \| null}` → `{percorso, byte, creato_il}`. `path` nullo = `~/Downloads/<nome_di_default>` (ripiego senza picker). 409 `backup_in_corso`. |
| POST | `/api/backup/restore/prepare` | `{path}` → il `Riepilogo`. 400 con il codice di `BackupNonValido`; 409 `job_in_corso` con `{job: "analysis" \| "import" \| "shazam" \| "downloads"}` nel dettaglio; 404 `file_non_trovato`. |
| POST | `/api/backup/restore/confirm` | → `{riavvio_necessario: true}`. 409 `job_in_corso`, 409 `niente_da_ripristinare`. |
| DELETE | `/api/backup/restore` | annulla lo staging → 204 |
| GET | `/api/backup/restore/last` | l'ultimo `EsitoRipristino` o `null` |

Il router va in `main.py` accanto agli altri e nella lista di
`docs/ARCHITECTURE.md`.

## 4. Il picker impara «salva con nome»

`native_picker.build_script` accetta `kind="save"` e un `default_name`:

```applescript
POSIX path of (choose file name with prompt "…" default name "…" default location (POSIX file "…"))
```

`choose file name` restituisce un percorso anche se il file non esiste e, se
esiste, chiede conferma di sovrascrittura da solo. `pick_path` non rimuove la
barra finale per `save` (non ce l'ha) e restituisce il percorso così com'è: è
`crea` ad aggiungere `.zip` se manca.

`PickIn.kind` diventa `Literal["folder", "file", "save"]`, con
`default_name: str | None`. Lato frontend `pickPath` e `PathPickerButton`
accettano il nuovo `kind` e l'opzione. Il ripristino usa `kind="file"` come
oggi.

Senza picker (non macOS, o `osascript` assente): il frontend non apre nessun
dialogo, manda `path: null`, e mostra dove il backend ha scritto. Per il
ripristino senza picker non c'è ripiego: il pulsante non si monta, come già
non si montano i «Sfoglia…».

## 5. Frontend

### La scheda Backup in Impostazioni

Nuovo gruppo **«Dati»** fra Organize e Versione in `app/settings/page.tsx`,
con `components/settings/backup-card.tsx`:

- Riga di stato: «Ultimo backup: 12 set 2026, 18:40» o «Nessun backup finora»;
  sotto, in piccolo, «circa 23 MB · database, 4 cover, credenziali» dalla
  stima. Se `restore/last` risponde, una riga «Ripristinato il … dal backup
  del …».
- **Backup ora…**: con il picker apre «salva con nome» con `nome_di_default`;
  senza picker chiama `POST /api/backup` con `path: null`. A fine corsa
  mostra il percorso scritto e la dimensione; l'errore va in un `Alert` nella
  scheda.
- **Ripristina da backup…** (solo con picker): picker `file` →
  `restore/prepare` → `Modal` con il riepilogo: data e versione del backup,
  tracce e playlist contenute, se include le credenziali, e due avvertenze
  fisse: «i dati attuali vengono messi da parte, non cancellati» e «la coda
  download torna com'era nel backup». Pulsanti: **Ripristina e riavvia**
  (`danger`) e Annulla (`DELETE /restore`). Alla conferma: `restore/confirm`,
  poi nel guscio `riavvia()` dal bridge esistente (`lib/updates-bridge.ts`);
  nel browser la modale resta aperta con «Riavvia il backend per completare
  il ripristino». `job_in_corso` diventa un `Alert` che nomina il job.

I codici passano dal pattern in uso: il backend manda il codice, i dizionari
IT/EN scrivono la frase (`t.settings.backup*`). Le date con `fmtDate`, che
segue la lingua attiva.

### L'updater chiede prima

In `aggiornamento-guscio.tsx` la `ConfirmModal` diventa una `Modal` propria,
`components/settings/conferma-aggiornamento.tsx`, che al montaggio chiama
`GET /api/backup/estimate`:

- Testo: la frase di conferma attuale più «Vuoi fare prima un backup?
  Occuperebbe circa N MB.» Se la stima fallisce (backend giù, risposta
  lenta), la domanda non compare e restano le due uscite di oggi.
- Tre uscite: **Backup e aggiorna** (primaria), **Aggiorna senza backup**
  (outline), Annulla (ghost).
- «Backup e aggiorna»: picker save → `POST /api/backup` → `installaOra()`.
  Il dialogo annullato riporta alla modale senza fare nulla; un backup
  fallito mostra l'errore nella modale e **l'aggiornamento non parte**.
  Durante la scrittura la modale dice «Backup in corso…» con i pulsanti
  spenti.

Niente cambia in `aggiornamento.rs`: il backup finisce prima che
`installa_aggiornamento` sia invocato, a backend vivo.

> **Correzione (review finale, 2026-09-13).** Vale per il *backup* pre-update,
> non per il ripristino: `riavvia_app` — nello stesso file — è dovuta cambiare.
> Vedi il riquadro in «Perché lo scambio avviene a freddo».

## 6. Test

Backend, `tests/test_backup.py`, su un `DATA_DIR` temporaneo
(`monkeypatch.setattr(paths, "DATA_DIR", …)`) con un DB reale creato da
`ensure_schema` su un engine di prova e WAL attivo:

- `crea`: i membri attesi ci sono, gli esclusi no (una `thumb_cache` e un
  `slskd.log` seminati apposta); lo snapshot contiene una riga scritta prima
  della chiamata mentre un'altra connessione è aperta; con un errore forzato
  (monkeypatch di `zipfile.ZipFile`) non resta né lo zip né il parziale;
  secondo `crea` concorrente → `BackupInCorso`; `last_backup_at` scritto.
- `stima_byte` non dipende dalla dimensione del WAL (si gonfia il WAL e la
  stima non cambia).
- `ispeziona`: un codice per caso — non-zip, zip senza manifest, `formato` 2,
  DB mancante, DB troncato, versione più recente; versione più vecchia
  accettata; contatori giusti.
- `prepara`/`conferma`/`annulla`: staging popolato senza marker; marker solo
  dopo `conferma`; `annulla` pulisce; `JobInCorso` con `is_running` patchato
  a `True`, per ciascuno dei quattro job.
- `applica_se_in_attesa`: senza marker non tocca niente; con marker scambia i
  file, `pre-restore/` contiene i vecchi (DB, wal, shm, `.env`), il marker e
  lo staging spariscono, l'esito è `ok`; con staging mancante il marker viene
  rimosso e i dati attuali restano identici (hash prima/dopo).
- Router: mapping dei codici a 400/404/409; `path: null` → file in
  `~/Downloads` (con `HOME` patchato).
- `native_picker.build_script("save", …, default_name=…)` contiene `choose
  file name` e il nome; `pick_path` non tronca il percorso per `save`.
- Il test di invarianza di `DATA_DIR` (nessuna scrittura in `BACKEND_DIR`)
  estende il suo script d'esercizio con un `POST /api/backup` e un
  `restore/prepare` + `DELETE`: la ROADMAP chiede a chi aggiunge punti di
  scrittura di estendere lo script, e questi ne aggiungono tre (`.parziale`,
  `restore-staging/`, `restore-pending.json`).

Frontend, vitest:

- `backup-card`: stato con e senza `last_backup_at`; backup senza picker
  mostra il percorso restituito; ripristino → modale con riepilogo; Annulla
  chiama la `DELETE`; conferma nel guscio chiama `riavvia`; nel browser
  mostra la frase di riavvio manuale; `job_in_corso` → Alert.
- `conferma-aggiornamento`: stima presente → tre pulsanti con i MB; stima
  fallita → due; picker annullato non installa; backup fallito non installa e
  mostra l'errore; percorso felice chiama backup poi `installaOra`. Bridge
  sostituito in blocco come nei test esistenti del provider.

## 7. Documentazione

- `docs/API.md`: i sei endpoint e il tipo `save` del picker.
- `docs/ARCHITECTURE.md`: sezione «Backup e ripristino» con la lista del
  contenuto, l'ordine di avvio (`applica_se_in_attesa` prima di
  `load_dotenv`) e il perché dello scambio a freddo; il router nella lista.
- `docs/ROADMAP.md` e `PROGRESS.md`: stato.
- `README.md`: una riga su backup e ripristino, e che il file contiene le
  credenziali.
- `CLAUDE.md`: nessuna regola nuova; il backup non è una scrittura sui file
  audio e non tocca le sette regole.

## Cosa resta fuori, e perché

- **Rotazione e backup periodico**: decisione esplicita, «manuale + prima
  dell'aggiornamento». Se un giorno servirà, `crea` e `stima_byte` sono già
  la base.
- **Ripristino a caldo nel browser**: costerebbe il rischio descritto sopra
  per il solo ambiente di sviluppo.
- **Cartella download di slskd**: sono i file della libreria, che il disco
  già rappresenta; un backup che li includesse peserebbe gigabyte e
  cambierebbe natura.
- **Cifratura dello zip**: il file equivale allo `.env`, che oggi non è
  cifrato; si documenta, non si cifra.
