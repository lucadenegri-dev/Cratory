# ③ La shell Tauri e il sidecar Python

Data: 2026-08-22. Stato: **decisioni prese in conversazione; scritta da Claude, da rivedere.**
Contesto d'insieme: `2026-08-22-tauri-decomposizione-design.md`.

## Problema

I due sotto-progetti precedenti hanno reso possibile il bundle: il backend gira
da una cartella di sola lettura (①) e il frontend si esporta staticamente (②).
Manca il bundle.

Serve un guscio nativo che apra una finestra, avvii il backend Python come
processo figlio, aspetti che risponda, mostri il frontend statico e spenga tutto
alla chiusura — portandosi dentro l'interprete, le dipendenze e i binari
esterni.

## Decisioni chiave

- **CPython rilocabile, non un binario congelato.** Provato con uno spike:
  `analyze_subprocess()` funziona senza modifiche perché `sys.executable` resta
  un Python vero. 195 MB potati, 71 compressi. Il razionale e i numeri sono nel
  documento di decomposizione.
- **Porta fissa 8000.** `spotify_redirect_uri` è registrata su Spotify con quel
  numero: una porta scelta a caso a ogni avvio romperebbe l'OAuth. Se è occupata
  si fallisce con un messaggio comprensibile, **non** si ripiega sulla prima
  libera.
- **Tauri imposta le variabili, il backend non indovina niente.**
  `CRATORY_DATA_DIR`, `CRATORY_BIN_DIR` e `CRATORY_VERSION` sono i tre seam che
  ① e il lavoro precedente hanno già preparato. Il guscio li passa al lancio; nel
  backend non cambia una riga.
- **ffmpeg viaggia nel bundle, rilocato dalla build di Homebrew.** È l'unico
  componente senza una build upstream arm64 con checksum. Homebrew serve **sulla
  macchina di build**, non su quella di chi installa: si compila una volta qui,
  si rilocano le dylib, e il binario entra nel `.dmg`. Installare Homebrew
  sull'utente finale è stato scartato: richiede privilegi di amministratore,
  si tira dietro gli Xcode Command Line Tools, ed è la scelta opposta a quella
  che il progetto ha già preso per iscritto — `system_probe.available_recipe`
  offre `brew install` **solo se brew c'è già**, proprio per non toccare il
  sistema dell'utente.
- **`fpcalc` e `slskd` dal manifest esistente**, che per `darwin-arm64` ha già
  URL e SHA256 pinnati. Non si duplica quella tabella: la si legge.
- **Firma ad-hoc**, perché non c'è un account Apple Developer. La firma vera e
  la notarizzazione sono variabili d'ambiente nel passo di build: prenderle più
  avanti non richiede di rifare niente.

## Ambito

Dentro: lo scaffold Tauri, la finestra, il ciclo di vita del backend
(avvio/health/spegnimento), lo script che costruisce il runtime Python, il
confezionamento dei tre binari esterni, il cablaggio delle variabili, e il
frontend statico dentro il bundle.

Fuori, e sono il ④: il `.dmg`, l'updater, il `LICENSE` AGPL-3.0, le istruzioni
per la quarantena.

Il consegnabile è **un `Cratory.app` che si apre con un doppio clic su questa
macchina e funziona senza che nulla sia installato a parte l'app**.

---

## 1. Dove vive il guscio

`src-tauri/` nella radice del repository, accanto a `backend/` e `frontend/`.
È un terzo componente di pari livello che lega gli altri due, non un dettaglio
del frontend: mettercelo dentro suggerirebbe che dipende da npm, mentre dipende
da entrambi.

Tauri v2. La CLI arriva come dipendenza di sviluppo npm (`@tauri-apps/cli`),
non con `cargo install`: è un binario precompilato invece di una compilazione
da sorgente di parecchi minuti, e resta pinnata nel lockfile come tutto il
resto.

## 2. Cosa contiene il bundle

```
Cratory.app/Contents/
  MacOS/Cratory                 il guscio Rust
  Resources/
    frontend/                   l'export statico di ② (out/)
    python/                     CPython 3.11 rilocabile + site-packages, potato
    backend/                    il sorgente di app/, senza test
    bin/
      ffmpeg/                   binario + dylib rilocate
      fpcalc                    dal manifest
      slskd/                    dal manifest
```

`bin/` rispetta il layout che `system_probe.resolve_binary` già conosce —
`single` per fpcalc, `bundle` (sottocartella per nome) per ffmpeg e slskd. È il
motivo per cui quella funzione fu scritta così, e qui si incassa.

## 3. Il ciclo di vita del backend

All'avvio il guscio lancia
`Resources/python/bin/python3 -m uvicorn app.main:app --port 8000`
con cwd `Resources/backend`, e con l'ambiente che porta i tre seam.

**Mai `bin/uvicorn`**: gli script in `bin/` di un runtime rilocabile si portano
dentro lo shebang il percorso assoluto della macchina di build. Lo spike l'ha
verificato.

Poi interroga `/api/setup/state` finché non risponde, con un limite di tempo.
Solo allora mostra la finestra: aprirla prima significherebbe una pagina bianca
o un muro di errori di rete mentre il backend sale.

Alla chiusura il processo figlio va terminato. Un backend orfano che resta
attaccato alla porta 8000 rende il secondo avvio dell'app un fallimento
inspiegabile.

**Se la porta 8000 è occupata**, il guscio lo dice e si ferma. Il messaggio deve
distinguere i due casi che l'utente può risolvere — «c'è già un Cratory aperto»
e «un altro programma usa la 8000» — perché sono azioni diverse.

## 4. Costruire il payload

Uno script (`src-tauri/scripts/`) fa, in ordine: scarica il CPython rilocabile
pinnato, ci installa dentro `backend/requirements.txt`, pota (`pip`,
`setuptools`, `pytest`, `__pycache__`, `test`, `idlelib`, `tkinter`,
`*.dist-info`), copia `backend/app`, scarica `fpcalc` e `slskd` **leggendo il
manifest esistente** invece di ripetere URL e hash, e riloca `ffmpeg`.

Lo script è idempotente e verificabile: alla fine **esegue ogni binario**, e
fallisce se uno non parte. È la stessa disciplina di `binary_installer` — un
download che verifica l'hash può comunque produrre un eseguibile che non gira.

## 5. Il frontend

`CRATORY_STATIC_EXPORT=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run build`.

`NEXT_PUBLIC_*` viene incorporata **a build time**, non letta a runtime: la
variabile va passata al build, non al processo del guscio. Sbagliarlo produce
un'app che non fa una sola chiamata e non dice perché.

**Una domanda che il ② ha lasciato aperta e che qui si chiude:** l'export produce
`out/tracks.html`, e l'URL `/tracks` risolve solo se chi serve i file mappa
l'uno sull'altro. `npx serve` lo fa; il protocollo asset di Tauri va verificato.
Se non lo fa, `trailingSlash: true` sotto `CRATORY_STATIC_EXPORT` fa produrre
`out/tracks/index.html` e la questione sparisce. **Da decidere guardando, non
ragionando.**

## 6. Verifica

Il criterio non è «compila», è **«funziona da un doppio clic»**:

- L'app si apre senza terminale, senza venv, senza `start-dev.sh`.
- I dati stanno in `~/Library/Application Support/Cratory/`, non nel bundle.
- La pagina Analisi produce un BPM: è la prova che essentia gira dal bundle.
- Una traccia posseduta si riproduce: è la prova che ffmpeg rilocato funziona.
- Chiudendo la finestra non resta nessun processo Python vivo.
- Riaprendo subito, l'app riparte (cioè la porta è stata liberata davvero).
- Il `.app` copiato in un'altra cartella funziona ancora: è la prova che niente
  dipende dal percorso di build.

## Rischi noti

- **La rilocazione di ffmpeg** è la parte più fragile: 18 dylib dirette più la
  chiusura transitiva. Va verificata eseguendo il binario **dopo** averlo
  spostato, non solo dopo averlo assemblato.
- **La firma ad-hoc va applicata dopo la rilocazione**: `install_name_tool`
  invalida la firma di ogni dylib che tocca.
- **Il bundle è grosso** (~300 MB scompattati). Atteso, non un difetto.
