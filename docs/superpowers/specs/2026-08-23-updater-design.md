# Updater: aggiornamento in-place nel guscio desktop

Data: 2026-08-23. Stato: approvata a voce.

## Problema

Cratory sa dire che esiste una versione più recente, e finisce lì. Il bottone in
Impostazioni interroga l'API delle release di GitHub
(`app/services/update_check.py`), mostra numero e note, e offre un link alla
pagina della release. Da lì in poi tocca all'utente: scaricare 172 MB di `.dmg`,
montarlo, trascinare l'app in Applicazioni, e **rifare a ogni versione** il giro
in Impostazioni di Sistema → Privacy e sicurezza, perché la firma ad-hoc cambia
a ogni build e l'approvazione è legata alla firma.

La spec `2026-08-22-release-design.md` lasciò fuori l'updater di proposito:
servivano una coppia di chiavi, un manifesto pubblicato e una release esistente,
e nessuna delle tre c'era. Ora le release ci sono.

## Decisioni chiave

- **Updater di Tauri, aggiornamento in-place.** Non un download assistito del
  `.dmg`: l'app scarica `Cratory.app.tar.gz`, ne verifica la firma minisign,
  sostituisce sé stessa e riparte.
- **La sequenza vive in Rust, non nella pagina.** Il backend Python gira da
  dentro il bundle che si sta per sostituire: va terminato *prima*
  dell'installazione. È un vincolo d'ordine, e i vincoli d'ordine non si
  affidano a chi chiama.
- **Controllo automatico all'avvio.** Questo **ribalta** una decisione della
  spec del 2026-08-22 («nessun controllo automatico all'avvio: è stato chiesto
  un bottone»). Allora era giusta, perché scoprire un aggiornamento non portava
  a niente che l'app potesse fare. Ora ci porta, e un avviso che aspetta di
  essere cercato in Impostazioni non lo vedrebbe nessuno.
- **Si scarica e si installa solo su conferma esplicita.** Niente aggiornamenti
  che arrivano addosso mentre si costruisce un set: l'installazione uccide il
  backend e con lui i lavori in corso.
- **Build e pubblicazione restano due gesti.** `assembla.py` costruisce; un
  nuovo `pubblica.py` pubblica. Il secondo è irreversibile e va fatto di
  proposito.
- **La prima versione aggiornabile è la prossima.** La 1.0.2 già installata non
  ha l'updater: la 1.0.3 si installa ancora a mano. Da lì in poi il flusso vale.

## Ambito

Dentro: il plugin updater e i due comandi Rust, il provider e l'avviso nel
frontend, la card in Impostazioni che scarica e installa, la coppia di chiavi,
`createUpdaterArtifacts`, `latest.json`, `pubblica.py`, i test e la correzione
dei documenti che diventano falsi.

Fuori, dichiarato: firma e notarizzazione Apple (serve un account a pagamento,
e resta la ragione per cui la prima installazione passa da Privacy e sicurezza);
aggiornamenti differenziali (Tauri non ne fa: ogni aggiornamento è il bundle
intero); Windows e Linux; il rollback a una versione precedente; l'annullamento
di un download a metà.

Dipendenze nuove: `tauri-plugin-updater` (Rust) e `@tauri-apps/api` come
dipendenza diretta di npm — oggi c'è solo per transitività di
`@tauri-apps/plugin-opener`, e il provider ha bisogno di `invoke` e `listen`.

---

## 1. La sequenza, e perché sta in Rust

Un modulo nuovo, `src-tauri/src/aggiornamento.rs`, accanto a `backend.rs`.

```text
1. download(on_chunk, on_finish)   -> byte in memoria, firma verificata dal plugin
2. backend::termina(&app)          -> SIGTERM a uvicorn, SIGKILL di riserva
3. install(bytes)                  -> scompatta e sostituisce Cratory.app
4. app.restart()
```

Il punto 2 è la ragione di tutto il resto. Il backend è un CPython che vive
dentro `Cratory.app/Contents/Resources/`, e importa moduli dal disco mentre
gira: sostituire il bundle sotto un interprete vivo produce fallimenti
intermittenti e illeggibili. `downloadAndInstall()`, la scorciatoia documentata,
non lascia spazio per infilarci niente in mezzo; `download()` e `install()`
separati sì. È anche il motivo per cui il flusso non sta nel frontend: la pagina
non deve poter dimenticare un passo.

`backend::termina` è già idempotente — fa `guard.take()` sullo stato gestito —
quindi il `RunEvent::Exit` che scatta all'uscita non trova più nessun figlio e
non manda un secondo SIGTERM a un pid che nel frattempo potrebbe essere di
qualcun altro.

`installa_aggiornamento` **ricontrolla prima di scaricare**: l'oggetto `Update`
non sopravvive fra una chiamata e l'altra, e riprenderlo costa una GET di
`latest.json`. Se nel frattempo non c'è più niente da installare, il comando
finisce senza aver fatto nulla — non inventa un aggiornamento perché la pagina
ne aveva visto uno un minuto prima.

Su macOS `install` non riavvia niente da solo: il riavvio è a nostro carico, ed
è il punto 4. Serve solo `app.restart()` del core: nessun `tauri-plugin-process`.

## 2. I due comandi e l'evento

```rust
#[tauri::command]
async fn controlla_aggiornamento(app: AppHandle) -> Result<Option<InfoAggiornamento>, ErroreAggiornamento>;

#[tauri::command]
async fn installa_aggiornamento(app: AppHandle) -> Result<(), ErroreAggiornamento>;
```

`InfoAggiornamento` porta `versione`, `note`, `data`. `Ok(None)` è "sei
aggiornato", `Err` è "non è stato possibile controllare": **i tre esiti restano
tre**, come già li tiene distinti `update_check.py`, e il terzo non degrada mai
nel primo.

`ErroreAggiornamento` non porta frasi: porta un **codice** (`rete`, `firma`,
`permessi`, `sconosciuto`) e il dettaglio tecnico. La frase la scrivono i
dizionari del frontend, nelle due lingue. È la stessa regola per cui i testi
user-facing non nascono da chi solleva l'errore.

Il progresso viaggia come evento `aggiornamento://progresso` con byte scaricati
e totale. Il plugin lo chiamiamo da Rust, quindi in `capabilities/default.json`
non serve `updater:default`: i comandi dell'app non passano dal sistema dei
permessi. Se in implementazione si rivelasse falso, si aggiunge e lo si scrive
qui.

## 3. Dove nasce "c'è un aggiornamento"

Due fonti, che non si contraddicono perché rispondono a due domande diverse.

| Dove gira | Chi risponde | Cosa legge |
|---|---|---|
| Guscio desktop | il plugin, via `controlla_aggiornamento` | `latest.json` allegato alla release |
| Browser di sviluppo | `GET /api/updates/check` | API delle release di GitHub |

Nel guscio decide chi poi installa: chiedere a una fonte e scaricare da un'altra
è il modo per ritrovarsi a proporre una versione che il manifesto non descrive.
Fuori dal guscio non c'è niente da installare, e l'endpoint resta esattamente
com'è — nessuna modifica al backend.

A scegliere è `inTauri()`, già in `frontend/lib/external-url.ts`.

Endpoint del manifesto:
`https://github.com/lucadenegri-dev/Cratory/releases/latest/download/latest.json`.
URL stabile, servito da GitHub senza autenticazione e senza il rate limit
dell'API.

## 4. L'interfaccia

**Un provider solo.** `UpdateProvider` montato in `frontend/app/layout.tsx`
accanto a `ExternalLinkBridge`, con la stessa proprietà: fuori dal guscio
desktop non fa nulla. All'avvio controlla una volta per lancio e **fallisce in
silenzio** — un problema di rete all'avvio non è una notizia da dare a chi non
ha chiesto niente. Stato:

```text
sconosciuto | aggiornato | disponibile(info) | non_verificabile
            | scaricando(byte, totale) | installando | fallito(codice, dettaglio)
```

**L'avviso** è un punto sottile accanto a `IMPOSTAZIONI`, nel piede di
`frontend/components/index-nav.tsx` — dove si va comunque per la versione. C'è
il precedente del contatore di `/wishlist`, ma un numero accanto a
"Impostazioni" si legge male: il punto dice che c'è qualcosa senza pretendere di
dire cosa.

**Il resto succede in `frontend/components/settings/version-card.tsx`**, che
smette di essere solo un annuncio:

- *disponibile*: numero, note (contenuto di terzi, citato come oggi) e
  **Scarica e installa (≈172 MB)**. "Apri il rilascio" resta: è la via d'uscita
  quando l'automatismo non funziona.
- il clic apre un `ConfirmModal` che dice le tre cose vere: si scaricano ~172 MB,
  l'app si chiude e riparte da sola, **i lavori in corso vengono interrotti**.
  Un'analisi o un download a metà muoiono col backend.
- *scaricando*: MB su MB e percentuale. **Nessuna cancellazione**: il `download`
  del plugin non espone un modo per fermarsi, e un bottone "Annulla" che non
  annulla è peggio che non averlo.
- *installando*: "Installazione, l'app si riavvia da sola". Da qui il backend è
  morto e la pagina non deve provare a parlarci.
- *fallito*: la frase del codice, il dettaglio in piccolo, e **Riavvia l'app**.
  Non è cosmetico: se `install` fallisce, il backend è già stato terminato al
  punto 2 e l'app è un guscio vuoto — il riavvio è ciò che la rimette in piedi.
  In fondo resta "Apri il rilascio", per l'installazione a mano.

Testi nuovi in `it.ts` e `en.ts` sotto le chiavi `settings.version*` già
esistenti, in entrambe le lingue.

## 5. La chiave e la configurazione

`tauri signer generate -w ~/.tauri/cratory.key`, con password. Il file privato
non entra mai nel repository; la chiave pubblica sì, dentro `tauri.conf.json` —
è pubblica, è il suo mestiere.

Due cose vanno scritte nel README perché nessuna si scopre da sola:

- **la chiave privata va conservata fuori da questo Mac.** Se la perdi, nessuna
  app già installata potrà più aggiornarsi: la pubblica è murata dentro ogni
  bundle già distribuito, e un'altra chiave produrrebbe firme che quei bundle
  rifiutano.
- **`assembla.py` fallisce subito** se `TAURI_SIGNING_PRIVATE_KEY` non è
  nell'ambiente, prima di iniziare la build e non venti minuti dopo al momento
  del bundling. Lo script non stampa mai il valore.

In `tauri.conf.json`:

```json
{
  "bundle": { "createUpdaterArtifacts": true },
  "plugins": {
    "updater": {
      "pubkey": "<contenuto di cratory.key.pub>",
      "endpoints": ["https://github.com/lucadenegri-dev/Cratory/releases/latest/download/latest.json"]
    }
  }
}
```

`createUpdaterArtifacts` fa emettere `Cratory.app.tar.gz` e il suo `.sig`
accanto al `.dmg`. In `Cargo.toml` la dipendenza è vincolata al target non
mobile, come da documentazione del plugin.

## 6. La pubblicazione

`src-tauri/scripts/pubblica.py`, nuovo e separato da `assembla.py`.

1. **Rifiuta di partire** se l'albero di lavoro è sporco, se `VERSION` e
   `frontend/package.json` divergono, o se HEAD non porta il tag `vX.Y.Z`.
   Pubblicare è irreversibile, e questi tre sono i modi realistici di sbagliarlo.
2. Legge `Cratory.app.tar.gz.sig` e costruisce `latest.json`:

```json
{
  "version": "1.0.3",
  "notes": "<le stesse note del corpo della release>",
  "pub_date": "2026-08-23T10:00:00Z",
  "platforms": {
    "darwin-aarch64": {
      "signature": "<contenuto testuale del .sig, non un percorso>",
      "url": "https://github.com/lucadenegri-dev/Cratory/releases/download/v1.0.3/Cratory.app.tar.gz"
    }
  }
}
```

   L'URL punta all'asset **di quel tag**, non a `latest`: il manifesto della
   1.0.3 descrive la 1.0.3. La sola chiave di piattaforma è `darwin-aarch64`,
   che è il solo target che questo progetto costruisce.
3. Crea o aggiorna la release con `gh`, allegando quattro file: `.dmg` (prima
   installazione), `.app.tar.gz`, `.sig`, `latest.json`.

Le note arrivano da un file passato allo script e finiscono **sia** nel corpo
della release **sia** in `latest.json`: una fonte e due consumatori, così la
card in Impostazioni mostra le stesse parole qualunque delle due strade abbia
preso.

## 7. Cosa diventa falso

- `README.md`, sezione *Releases*: «**Nothing is downloaded or installed
  automatically.** There is no auto-updater yet» — da riscrivere, insieme alla
  lista dei passi di pubblicazione (ora quattro allegati, e la variabile
  d'ambiente della chiave).
- `README.md`, sezione *Opening it on another Mac*: «Every new version needs the
  same four steps again» resta vero solo per chi installa a mano. Cosa vale per
  chi si aggiorna dall'app lo decide la verifica del §8, e la frase si scrive
  dopo averla vista.
- `docs/ROADMAP.md`: la voce *Release* dichiara l'assenza dell'updater e le sue
  ragioni; va aggiornata, non cancellata — le ragioni erano giuste allora.
- `docs/ARCHITECTURE.md` (guscio desktop) e `docs/DEPENDENCIES.md` (plugin nuovo
  e chiave di firma).

## 8. Verifica

**Sul campo, con due bundle veri.** È l'unico modo di sapere se funziona:
la sequenza download → terminazione → sostituzione → riavvio non si prova con un
test unitario, e fingere il contrario sarebbe un test verde per il motivo
sbagliato.

1. Build 1.0.3 e 1.0.4 con `tauri build --config` che punta gli endpoint a un
   server statico locale (`dangerousInsecureTransportProtocol` acceso solo lì:
   la configurazione committata non lo contiene).
2. La 1.0.3 installata in `/Applications` dal suo `.dmg`, col giro in Privacy e
   sicurezza.
3. Si guarda l'intera catena: il progresso avanza; **nessun uvicorn orfano sulla
   8000** dopo l'installazione; il bundle è sostituito; l'app riparte; la
   versione a schermo è la 1.0.4; i dati in
   `~/Library/Application Support/com.cratory.app/` sono intatti.
4. **La domanda vera: compare o no il dialogo *"Cratory" Not Opened*?** Se non
   compare, il giro in Privacy e sicurezza resta solo per la prima installazione
   e il README lo dirà. Se compare, l'updater vale comunque il download e il
   trascinamento risparmiati, e il README dirà quello. Non si promette prima di
   aver visto.

**Test automatici**, e ognuno va provato rompendo il codice che sorveglia:

- `costruisci_manifest()` (funzione pura, in `backend/tests` dove c'è già il
  precedente dei test che leggono la radice del repository): la firma è il
  contenuto del `.sig` e non un percorso; la chiave di piattaforma è
  `darwin-aarch64`; l'URL contiene il tag e non `latest`; la `v` iniziale non
  finisce in `version`; `pub_date` è RFC 3339; un `.sig` mancante o vuoto è un
  errore, non un manifesto con la firma vuota.
- guardia su `tauri.conf.json`: `createUpdaterArtifacts` vero, `pubkey` non
  vuota, endpoint quello atteso — perché una modifica futura non possa spegnere
  gli aggiornamenti in silenzio.
- provider frontend: fuori dal guscio non invoca nulla; i tre esiti restano
  distinti; il progresso aggiorna i byte; il fallimento dell'installazione offre
  il riavvio.

## 9. Rischi e incognite

- **La quarantena.** L'ipotesi è che un bundle sostituito dall'app non porti
  `com.apple.quarantine` e quindi non passi da Gatekeeper. È l'argomento più
  forte a favore di tutto questo lavoro, ed è un'ipotesi finché il §8 non la
  conferma.
- **Permessi di scrittura.** `install` scrive dentro
  `/Applications/Cratory.app`. Se l'app gira da un percorso non scrivibile, o
  peggio dal `.dmg` montato, fallisce: è esattamente il caso che il fallback
  manuale copre.
- **~180 MB in memoria.** Il `download` del plugin restituisce un `Vec<u8>`:
  l'intero bundle sta in RAM prima di essere scritto. Accettato.
- **Due build complete per la verifica**, ognuna lenta perché `assembla.py`
  riscarica e ricostruisce tutto da zero a ogni giro.
