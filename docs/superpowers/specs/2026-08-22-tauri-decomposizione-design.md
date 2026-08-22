# Tauri: obiettivo, vincoli e scomposizione

Data: 2026-08-22. Stato: approvata a voce.

Questo documento non è la spec di un lavoro: registra le decisioni d'insieme e
l'esito dello spike che le ha validate. Ogni sotto-progetto ha la sua spec.

## Problema

Cratory si avvia con `start-dev.sh`: un terminale, un venv da attivare, due
processi, e la conoscenza di dove stanno le cose. Non è distribuibile a nessuno
che non sia disposto a installare Python e Node.

## Decisioni chiave

- **L'obiettivo è la distribuzione ad altri**, non solo un'icona per sé. Da qui
  discendono firma, licenza e updater.
- **macOS Apple Silicon per la v1.** Un solo target, una sola macchina di build.
  Windows e Linux non sono esclusi, sono rimandati.
- **Nessun account Apple Developer, quindi nessuna notarizzazione.** La firma
  ad-hoc basta a far eseguire i binari arm64, ma un `.dmg` scaricato arriva in
  quarantena e macOS lo annuncia come «danneggiato» invece che «non firmato».
  L'utente deve passare da Impostazioni di Sistema → Privacy e sicurezza.
  Si accetta: firmare e notarizzare in Tauri sono variabili d'ambiente nel passo
  di build, quindi prendere l'account più avanti non richiede di rifare niente.
  **Non si progetta intorno all'assenza dell'account.**
- **Tutto dentro il bundle** (Python, dipendenze, ffmpeg, fpcalc, slskd): primo
  avvio senza rete e senza wizard di installazione componenti.
- **Cratory diventa AGPL-3.0, con i sorgenti pubblicati.** È la conseguenza
  diretta della decisione precedente: `essentia` è AGPL-3.0 e distribuirla
  dentro un artefatto vincola l'opera combinata. Va aggiunto un `LICENSE` e va
  corretta la riga del README che oggi dice «No license file is included».
  Si incastra con una decisione già presa altrove: il controllo aggiornamenti
  richiede che il repository sia pubblico.
- **Il backend è un CPython rilocabile, non un binario congelato.** Motivazione
  e prove nello spike qui sotto.
- **La porta del backend resta fissa.** `spotify_redirect_uri` vale
  `http://127.0.0.1:8000/api/spotify/callback` e Spotify pretende che la
  redirect URI registrata combaci esattamente: una porta scelta a caso a ogni
  avvio romperebbe l'OAuth. Se la porta è occupata si fallisce con un messaggio
  chiaro, non si ripiega sulla prima libera.

## Lo spike sul backend Python

La sola incognita reale era se `essentia==2.1b6.dev1389` — un build rolling con
copertura wheel a macchia di leopardo — potesse finire in un bundle. Testato in
scratchpad, buttato via: il prodotto è la risposta, non il codice.

Sono state confrontate due strade.

**PyInstaller `onedir`** dà il bundle più piccolo perché scarta ciò che non usi,
ma le tre librerie più pesanti qui (essentia, numpy, yt-dlp) sono esattamente
quelle che gli danno più problemi. Soprattutto obbliga a riscrivere
`integrations/essentia_engine.py`, che lancia
`[sys.executable, "-m", "app.integrations.essentia_worker", path]`: in un
binario congelato `sys.executable` è il binario stesso, che non accetta `-m`.
Sarebbe codice di produzione piegato allo strumento di packaging.

**CPython rilocabile** (python-build-standalone) con `site-packages` installato
dentro: si spedisce un interprete vero, non congelato. Scelta questa.

Esito, su `cpython-3.11.16+20260814-aarch64-apple-darwin`:

| Criterio | Esito |
|---|---|
| Runtime + tutto `requirements.txt` su arm64 | essentia `2.1-beta6-dev` inclusa |
| Albero spostato in un percorso assoluto diverso | `sys.prefix` lo segue |
| Analisi vera | 128.05 BPM su una click track a 128 esatti |
| `analyze_subprocess()` **senza modifiche** | 0.6 s, `sys.executable` è il Python del bundle |
| `uvicorn app.main:app` in HTTP | `/api/services/status` e `/api/setup/state` a 200 |
| Dimensione | 299 MB → **195 MB** potati → **71 MB** compressi |

La potatura toglie `pip`, `setuptools`, `pytest`, `__pycache__`,
`test`/`idlelib`/`tkinter` e i `*.dist-info`: 104 MB, con tutti gli import
ancora funzionanti (essentia, fastapi, uvicorn, yt-dlp, shazamio, mutagen, PIL,
acoustid). Un `.dmg` intorno agli 80 MB è realistico.

**Due cose trovate, da non riscoprire.**

1. **Gli script in `bin/` non sono rilocabili.** `bin/uvicorn` si porta dentro
   lo shebang il percorso assoluto della macchina di *build*. La forma corretta
   è `python3 -m uvicorn`, mai `bin/uvicorn`.
2. **Il backend scrive dentro il bundle.** Avviato da un finto
   `Cratory.app/Contents/Resources/backend`, ha creato lì dentro
   `data/djassistant.db` e `logs/`. In un `.app` firmato quella cartella è di
   sola lettura, e scriverci invaliderebbe la firma. È il problema che il
   sotto-progetto ① risolve.

## La scomposizione

Quattro sotto-progetti, ognuno con spec e piano propri. I primi tre hanno valore
anche senza i successivi.

**① Bundle-ready.** Il backend smette di scrivere nel proprio checkout: un seam
`CRATORY_DATA_DIR` della stessa forma di `CRATORY_BIN_DIR` e `CRATORY_VERSION`.
Nessuna riga di Tauri. Spec: `2026-08-22-bundle-ready-design.md`.

**② Il frontend senza il proxy Next.** `next.config.ts` usa `rewrites()` per
`/api/*`, che con un export statico non esiste; e `lib/organize/api.ts:8` fissa
`const API = "/api/organize"` senza override, mentre `lib/api/client.ts:7` ha
`NEXT_PUBLIC_API_URL`. Serve un solo aggancio per entrambi i client — la
ROADMAP già segnala questa duplicazione, qui diventa obbligatoria — più il CORS
per l'origin di Tauri. La vera domanda di design del ② sono le cinque rotte
dinamiche (`tracks/[id]`, `playlists/[id]`, `sets/[id]`, `labels/[label]`,
`shazam/[id]`): `generateStaticParams` su id arbitrari non esiste.

**③ La shell Tauri e il sidecar Python.** Lo scaffold, la finestra, l'avvio con
health-check e lo spegnimento del backend, il runtime rilocabile potato, e
`ffmpeg`/`fpcalc`/`slskd` nel bundle con `CRATORY_BIN_DIR` impostata al lancio.

**④ Release.** `.dmg`, firma ad-hoc, istruzioni per la quarantena, updater Tauri
agganciato alle stesse release GitHub che il bottone in Impostazioni già
interroga, `LICENSE` AGPL-3.0 e correzione del README.

Ordine: ① → ② → ③ → ④, con ① e ② indipendenti fra loro.

## Fuori ambito, dichiarato

Windows e Linux. La notarizzazione Apple. La migrazione del database di
sviluppo verso l'installazione impacchettata: si copia il `.db` a mano una
volta, non è codice che valga la pena scrivere e mantenere per un caso che
capita una volta sola a una persona sola.
