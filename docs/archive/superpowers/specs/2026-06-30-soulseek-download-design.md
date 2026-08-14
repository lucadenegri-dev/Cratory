# Soulseek Download — Design

Data: 2026-06-30
Stato: approvato (brainstorming), pronto per implementation plan.

## Obiettivo

Permettere a Cratory di **acquisire i file audio** di tracce che esistono gia' in
libreria (provenienti da playlist o da Discovery), usando la rete Soulseek tramite il
daemon headless **slskd**, e di **collegare** ogni file scaricato alla sua `Track`
(ownership). Chiude il cerchio tra "ho identificato il brano dallo streaming" e "ho il
file da suonare".

Job-to-be-done concreto:

1. Sezione **Download** dedicata: scelgo una playlist, Cratory cerca ogni traccia su
   Soulseek e la scarica.
2. In **Discovery**: accanto alle altre fonti, un bottone **Download** per scaricare la
   singola traccia trovata su Soulseek.

## Estensione consapevole dello scopo

Cratory ha un principio esplicito: "l'app non riproduce audio e non conserva file audio",
con la sola eccezione del modulo Shazam (download temporaneo per fingerprint, non
conservato).

Questa feature introduce una seconda eccezione, **dichiarata**: acquisizione
**persistente** di file audio via Soulseek, isolata in un modulo dedicato.

- Resta invariato il "no play": Cratory **non riproduce** audio in-app. Acquisisce e
  cataloga, non suona.
- Cambia il "no store": ora Cratory **puo' conservare** file, ma solo quelli acquisiti
  esplicitamente dall'utente e collegati a una `Track` gia' esistente.

`docs/ARCHITECTURE.md` va aggiornato per riflettere questa eccezione (vedi "Documentazione
da aggiornare").

## Decisioni prese

| Tema | Decisione | Alternative scartate |
|---|---|---|
| Come parlare con Soulseek | **slskd** (daemon headless con REST API) | aioslsk in-process (piu' fragile); pilotare la GUI di Nicotine+ (non e' una libreria) |
| Cosa fare del file | **Acquisizione + ownership**: salva e collega il file alla `Track` esistente | Puro downloader (Cratory cieco sul possesso); re-import (duplica la traccia) |
| Modello di possesso | **Campi separati** su `Track`, NON un nuovo valore di `status` di enrichment | Stato `acquired` dentro `status` (confonde possesso ed enrichment) |
| Scelta del file | **Ibrido**: auto-pick deterministico in blocco, selezione manuale per la singola | Solo auto (rischio file sbagliato); solo manuale (improponibile su playlist intere) |
| Preferenza qualita' default | lossless prima -> MP3 >= 320 -> mai sotto 256 (configurabile) | - |
| Vista "Tracce senza file" | **Fast-follow opzionale**, fuori dal primo taglio | Inclusa subito (gonfia il primo taglio) |

## Flusso

```text
Track in libreria (identita' da streaming)
  -> SoulseekClient.search(artista, titolo)            [via slskd REST]
  -> ranking deterministico dei candidati
       (match nome, formato/bitrate vs preferenza, disponibilita' uploader)
  -> auto-pick (Download-da-playlist) | mini-selettore (Discovery, singola)
  -> slskd enqueue download
  -> polling stato transfer
  -> a completamento: file nella download dir,
     collegato alla Track (has_local_file + local_path/local_format/local_bitrate)
```

## Integrazione slskd

- Nuovo client `backend/app/integrations/soulseek.py`, dietro interfaccia, **iniettabile e
  fakeabile** (test senza rete, come gli altri provider).
- Configurazione via env (come Spotify/Discogs):
  - `SLSKD_URL` — base URL del daemon slskd.
  - `SLSKD_API_KEY` — autenticazione.
  - `SLSKD_DOWNLOAD_DIR` — cartella in cui slskd deposita i file (Cartory la legge per
    risolvere il `local_path`).
- **Degradazione pulita**: se slskd non e' configurato/raggiungibile, la sezione Download e
  il bottone Discovery sono disabilitati con messaggio chiaro (come il modulo Shazam quando
  mancano ffmpeg/yt-dlp).
- Metodi del client (nomi endpoint slskd da confermare contro la doc in fase di plan):
  - `search(artist, title) -> list[Candidate]` — mappa su `/api/v0/searches`.
  - `enqueue_download(candidate) -> transfer_id` — mappa su `/api/v0/transfers`.
  - `transfer_status(transfer_id) -> TransferState` — mappa su `/api/v0/transfers`.

slskd viene usato **solo come downloader**. Non sfruttiamo la sua funzione di condivisione:
non esponiamo la libreria dell'utente. Scelta documentata (etica/etichetta + privacy).

## Backend

### Modello dati

Estendere `Track` (nessuna nuova entita' pesante), con migrazione idempotente in
`ensure_schema()`:

- `has_local_file` (BOOL, default false) — flag di possesso, **separato** da `status`.
- `local_path` (TEXT, null) — path del file acquisito.
- `local_format` (TEXT, null) — es. `flac`, `mp3`.
- `local_bitrate` (INT, null) — kbps (o lossless flag).

Lo `status` di enrichment resta intatto: possesso del file ed enrichment sono dimensioni
ortogonali.

### Job di download (async)

slskd e' asincrono (peer offline, code di attesa). Per uso mono-utente serve un modello
job leggero, senza infrastruttura pesante:

- Tabella job (id, track_id, candidate scelto, transfer_id slskd, stato, errore, timestamp).
- Stati job: `queued -> searching/selected -> downloading -> completed | failed | needs_review`.
- Avanzamento via **polling** dello stato transfer su slskd; nessun websocket richiesto nel
  primo taglio.
- A `completed`: risolvere il file nella download dir, popolare i campi `local_*` e
  `has_local_file=true` sulla `Track`.

### Servizi (deterministici)

In `services/`:

- `soulseek_search_service` — orchestrazione search + ranking dei candidati.
- `acquisition_service` — accodamento download, tracking job, link file -> `Track` a
  completamento.

### Router

`routers/downloads.py` (solo HTTP, nessuna logica di business):

- avvio ricerca/acquisizione per playlist;
- lista candidati di una traccia;
- accodamento download (singolo o blocco);
- stato job / avanzamento;
- (fast-follow) lista "tracce senza file".

## Motore di selezione deterministico

Funzione di scoring sui candidati restituiti da slskd, **zero AI**:

- **Match nome**: fuzzy di filename/path del candidato vs `artista + titolo`. Riusa la
  logica fuzzy gia' usata nella deduplica (`fuzzy artist+title`).
- **Qualita'**: formato (lossless > 320 > 256 > inferiori) + bitrate, confrontati con la
  preferenza configurata. Sotto-soglia -> scartato o marcato bassa confidenza.
- **Affidabilita' uploader**: slot liberi / lunghezza coda / online vs offline.
- **Output**: candidato top + punteggio di **confidence**.

Politica per superficie:

- **Download-da-playlist (blocco)**: auto-pick del candidato top. Sotto una soglia di
  confidence (nessun match buono, solo bitrate bassi, match nome dubbio) il download NON
  parte in automatico: la traccia va in `needs_review`.
- **Discovery (singola traccia)**: il bottone Download apre un **mini-selettore** dei
  candidati ordinati per punteggio; la scelta manuale costa poco su un brano solo.

## UI

Due superfici nel primo taglio, una terza come fast-follow opzionale.

### Sezione Download (nuova)

- Selezione di una playlist.
- Tabella tracce con stato per riga: gia' posseduta / candidato trovato (+ formato e
  qualita') / da rivedere / non trovata.
- Azioni: "Scarica tutto" oppure download per-traccia.
- Avanzamento via polling (barra/stato per traccia).

### Discovery (esistente)

- Bottone **Download** per-traccia, accanto alle fonti attuali (Discogs ecc.), attivo
  quando esiste un candidato su Soulseek.
- Apre il mini-selettore dei candidati.

### Vista "Tracce senza file" (fast-follow opzionale)

- Lettura tipo gap analysis: tracce in libreria/playlist/set di cui NON ho il file
  (`has_local_file=false`).
- Alimenta naturalmente la coda della sezione Download.
- **Non inclusa nel primo taglio**: progettata ma rinviata per non gonfiare lo scope.

## Non-goal

- **Niente riproduzione/streaming** in-app: Cratory non suona.
- **Niente condivisione** Soulseek: slskd usato solo come downloader, libreria utente non
  esposta.
- **Niente AI** nel percorso di selezione/acquisizione: tutto deterministico.
- **Niente re-import** che duplichi tracce: il file si collega alla `Track` esistente.

## Responsabilita' d'uso

Strumento personale/self-hosted: l'acquisizione di materiale audio e' responsabilita'
dell'utente. Una riga nel README/spec, senza moralismi.

## Documentazione da aggiornare (in fase di implementazione)

- `docs/ARCHITECTURE.md` — dichiarare l'eccezione "acquisizione persistente via Soulseek";
  aggiungere il modulo alle integrazioni e il flusso di acquisizione.
- `docs/API.md` — nuovi endpoint `downloads`.
- `docs/ROADMAP.md` — spostare la feature da idea a stato; aggiornare la tabella
  integrazioni (Soulseek/slskd: attiva se configurato).
- `README.md` — riga su acquisizione e responsabilita' d'uso.
- `CLAUDE.md` — nota sulla nuova eccezione al principio "no store".

## Punti aperti per il plan

- Nomi esatti degli endpoint slskd e forma dei payload (search results, transfers).
- Forma del parsing formato/bitrate: dai metadata slskd o derivati dal filename.
- Soglie precise di confidence per `needs_review`.
- Strategia di costruzione della query di ricerca (artista+titolo; eventuale fallback senza
  feat./remix tag).
