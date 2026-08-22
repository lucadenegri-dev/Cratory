# ① Bundle-ready: il backend smette di scrivere nel proprio checkout

Data: 2026-08-22. Stato: approvata a voce.
Contesto d'insieme: `2026-08-22-tauri-decomposizione-design.md`.

## Problema

`core/config.py:8` calcola `BACKEND_DIR` da `__file__`, e da lì discende tutto
ciò che l'app scrive: il database, i log, le cache cover e thumb, la cartella
`bin/` dei binari gestiti, il `.env`.

Dentro un `.app` firmato quella cartella è di sola lettura, e scriverci
invaliderebbe la firma. Non è un'ipotesi: lo spike ha avviato il backend da un
finto `Cratory.app/Contents/Resources/backend` e si è ritrovato
`data/djassistant.db` e `logs/` creati lì dentro.

La causa è che **`BACKEND_DIR` significa oggi due cose insieme**: dove sta il
codice, e dove si scrive. Oggi coincidono; in un bundle devono divergere.

## Decisioni chiave

- **Un secondo ancoraggio, non percorsi sparsi.** `DATA_DIR` accanto a
  `BACKEND_DIR`, e i punti di scrittura si riancorano a lui.
- **Stessa forma dei seam che esistono già.** `CRATORY_DATA_DIR` sta a
  `CRATORY_BIN_DIR` e `CRATORY_VERSION` come questo problema sta ai loro.
- **Il backend non indovina mai di essere in un bundle.** Non sniffa il proprio
  percorso, non cerca `Contents/Resources`: onora una variabile, e basta. È
  Tauri, al lancio, a impostarla — come dovrà già fare per le altre due.
- **Variabile assente = comportamento identico a oggi**, byte per byte. Lo
  sviluppo, il self-hosting e la suite pytest non si accorgono del cambiamento.
- **Nessuna migrazione del database esistente.** Vedi «Fuori ambito».

## Ambito

Dentro: la separazione fra cartella del codice e cartella dei dati, il
riancoraggio dei cinque punti di scrittura, il controllo di scrivibilità
all'avvio, i test.

Fuori: Tauri, il frontend, il packaging. Nessuna dipendenza nuova — `os` e
`pathlib`.

Il consegnabile è verificabile da solo: **il backend gira interamente da una
cartella di codice in sola lettura.** Serve anche a chi fa self-hosting da un
checkout non scrivibile.

---

## 1. `app/core/paths.py`

Un modulo nuovo, minuscolo e **senza dipendenze**:

```python
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = <CRATORY_DATA_DIR espansa e assoluta, altrimenti BACKEND_DIR>
```

**Perché un modulo separato e non `config.py`.** `main.py:11` chiama
`load_dotenv(...)` **prima** di importare `app.core.config`, di proposito: il
commento lì spiega che `FPCALC` viene letto da `os.environ` e non da
pydantic-settings, quindi il `.env` deve entrare nell'ambiente di processo prima
che `Settings()` venga costruito a import-time. Se `DATA_DIR` vivesse in
`config.py`, `main.py` dovrebbe importarlo prima di `load_dotenv` e costruire
`Settings` troppo presto. `paths.py` non dipende da niente, quindi entrambi
possono importarlo senza vincoli d'ordine.

`config.py` continua a ri-esportare `BACKEND_DIR`: `core/version.py` e
`services/system_probe.py` lo importano da lì oggi, e non c'è motivo di toccarli.

**Il calcolo non tocca il filesystem.** Nessun `mkdir`, nessun test di esistenza:
è la stessa disciplina che `managed_bin_dir()` già documenta nel suo docstring —
gira su praticamente ogni `resolve_binary`, e un accesso al filesystem lì
trasformerebbe un `GET /api/services` in un 500 su un mount di sola lettura.

**Una `CRATORY_DATA_DIR` relativa è un errore, non un'interpretazione.**
Risolverla contro la cwd metterebbe i dati in un posto che dipende da come hai
lanciato il processo — esattamente il difetto che i validator esistenti
dichiarano di aver corretto («mai alla cwd del processo»).

Il rifiuto avviene **all'import di `paths.py`**, con un `RuntimeError` che
nomina il valore ricevuto e dice che ne serve uno assoluto: è una configurazione
sbagliata che non deve poter passare inosservata, e a quel punto l'app non ha
ancora fatto niente. Non è il controllo del §3, che riguarda la scrivibilità di
una `DATA_DIR` già valida.

La `~` invece si espande, come già fa `expand_user_paths` per `library_root`.

## 2. I cinque punti di scrittura

Enumerati sul codice, non a memoria.

| Punto | Oggi | Dopo |
|---|---|---|
| Database | `DEFAULT_DATABASE_PATH = BACKEND_DIR/"data"/…` e il validator `normalize_database_url` | `DATA_DIR` |
| Log | `LOG_DIR = BACKEND_DIR/"logs"` (`config.py:9`) | `DATA_DIR/logs` |
| Cache cover, thumb, `bin/` | validator `_cache_dir_assoluta` (`config.py:107`) | `DATA_DIR` |
| `.env` | `env_file` in `SettingsConfigDict` + `main.py:11` | `DATA_DIR/.env` |
| `managed_bin_dir()` ramo relativo | `BACKEND_DIR/raw` (`system_probe.py`) | `DATA_DIR/raw` |

I default testuali delle impostazioni (`"./data/bin"`, `"./data/cover_cache"`,
`"./data/thumb_cache"`) **non cambiano**: cambia solo la radice contro cui i
validator li risolvono. Un utente che ha già messo un percorso assoluto nel
proprio `.env` continua a vederlo rispettato, perché i validator toccano solo i
percorsi relativi.

**Un punto resta fermo, di proposito.** `core/version.py` continua a leggere
`VERSION` da `BACKEND_DIR.parent`: è sola lettura, e il caso bundle ha già la
sua risposta in `CRATORY_VERSION`. Spostarlo sarebbe simmetria fine a sé stessa.

Restano fuori anche i percorsi che non sono dati di Cratory: `library_root` e
`archive_root` (la musica dell'utente) e `slskd_config_path` (la configurazione
di un altro programma, in `~/.config/slskd/`).

## 3. Il controllo all'avvio

Una funzione esplicita in `paths.py`, chiamata da `main.py` **prima** di
`setup_logging()` — che è il primo a scrivere, con `LOG_DIR.mkdir()`.

Verifica che `DATA_DIR` esista o sia creabile e che ci si possa scrivere. Se no,
fallisce con un messaggio che nomina il percorso e la variabile.

Il motivo è specifico dell'obiettivo: in un'app impacchettata **l'utente non ha
un terminale da cui leggere uno stack trace**. Un `PermissionError` grezzo
sepolto in un log che non sa di avere è indistinguibile da un'app che non parte
e basta.

## 4. Verifica

Tre test. I primi due sono ovvi, il terzo è quello che tiene nel tempo.

**Variabile assente → niente cambia.** Ogni ancoraggio risolve esattamente ai
valori di oggi. È la guardia di non-regressione, e va provata rompendo il
codice: se punto `DATA_DIR` altrove e il test resta verde, il test non serve.

**Variabile impostata → tutto atterra lì.** Database, log, cache, `bin/`, `.env`
sotto la cartella indicata; e la `~` espansa; e una `CRATORY_DATA_DIR` relativa
che solleva all'import di `paths.py`, prima che l'app faccia qualunque cosa.

**L'invariante.** Si fotografa l'albero di `BACKEND_DIR`, si avvia l'app **in un
subprocess** con `CRATORY_DATA_DIR` su una cartella temporanea, si esercitano i
percorsi di scrittura (`ensure_schema`, il logging, le cache), e si asserisce
che sotto `BACKEND_DIR` **non è comparso niente di nuovo**.

Il subprocess non è un dettaglio: `settings` e `DATA_DIR` sono singleton
costruiti a import-time, quindi cambiare la variabile dentro il processo di
pytest non rifà i calcoli. Un subprocess prova il percorso d'avvio vero, che è
poi ciò che Tauri eseguirà.

La fotografia ignora `__pycache__` e i `.pyc` — altrimenti è il test stesso a
sporcare l'albero che sta osservando, e diventa intermittente.

Questo test non confronta i cinque punti per nome: fotografa l'intero albero
prima e dopo, quindi si accorge anche di una riscrittura silenziosa di un file
già esistente, non solo di un nome nuovo comparso dal nulla. Ma resta una
guardia di regressione sui percorsi che lo script d'esercizio mette in moto
esplicitamente — non un rilevatore automatico di un punto di scrittura non
ancora enumerato lì dentro. Un ancoraggio dimenticato nello script resta
invisibile a questo test, che resta verde: è successo per davvero, nella
revisione finale di questo stesso lavoro, con i quattro percorsi propri del
demone slskd (config di fallback, cartella download di default, pid file, log
file), rimasti ancorati a `BACKEND_DIR` senza che questo test se ne
accorgesse, perché lo script d'esercizio non li toccava. Chi aggiunge un nuovo
punto di scrittura deve aggiungerlo anche lì, o questo test non lo vedrà mai.

## Fuori ambito, dichiarato

**Nessuna migrazione del database di sviluppo.** Quando il `.dmg` girerà,
`CRATORY_DATA_DIR` punterà a `~/Library/Application Support/Cratory/` e sarà
vuota; `backend/data/djassistant.db` resterà dov'è. Migrarlo automaticamente
sarebbe codice a vita lunga per un caso che capita una volta sola, a una persona
sola, e che nessun altro utente eserciterà mai — quindi nessun test reale lo
eserciterebbe. Si copia il file a mano.

**Non si sceglie qui il valore di `CRATORY_DATA_DIR` in produzione.**
`~/Library/Application Support/Cratory/` è la destinazione attesa, ma a
impostarla è Tauri al lancio: è una decisione del sotto-progetto ③.
