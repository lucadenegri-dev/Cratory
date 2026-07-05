# Design: archivio download problematici + collegamento manuale file locale

Data: 2026-07-05. Stato: approvato.

## Obiettivo

Due feature collegate:

1. Una pagina persistente che elenca le tracce con download problematico
   (non trovato, da rivedere, fallito), con filtro per esito e azioni per riga.
2. La possibilita' di collegare manualmente un file su disco a una Track,
   dal dettaglio traccia e dalla pagina archivio.

## Decisioni prese con l'utente

- L'archivio mostra lo **stato corrente** (`last_download_outcome` sulla Track),
  non uno storico dei tentativi: niente tabella nuova, niente migrazione.
- Include **tutti e tre gli esiti** (`not_found`, `needs_review`, `failed`) con
  filtro lato client; la sezione "Da sistemare" in `/downloads` diventa un
  riassunto compatto con contatori e link all'archivio.
- Azioni per riga: **Scegli file** (modal Soulseek esistente), **Collega file**
  (nuovo modal file locale), **Ignora** (azzera l'esito).
- Una traccia esce dall'archivio anche quando il file viene collegato dal
  dettaglio traccia: il collegamento azzera sempre l'esito.
- Scelta del file locale: **ricerca per nome sul server + percorso incollato**.
- "Riprova tutte" resta globale (tutte le tracce in sospeso), anche con un
  filtro attivo: nessun endpoint di retry per singola traccia.

## Backend

### Archivio (nessuna novita' dati)

- Fonte dati: `GET /api/downloads/pending` esistente (restituisce gia' i tre esiti).
- Nuovo endpoint: `DELETE /api/downloads/pending/{track_id}` ("Ignora") in
  `routers/downloads.py`. Azzera `last_download_outcome` e `last_download_reason`,
  404 se la traccia non esiste. Risponde con la Track aggiornata.

### Collegamento file locale

- Nuovo router `backend/app/routers/files.py`, prefisso `/api/files`:
  - `GET /api/files/search?q=...`: cerca file audio per sottostringa del nome
    (case-insensitive), ricorsivamente, in `settings.library_root` e
    `settings.slskd_download_dir` (se configurate). Query minima 2 caratteri,
    cap ~50 risultati. Ogni risultato: `path`, `name`, `format` (estensione),
    `size`, `source` ("library" | "downloads").
- Nuovo endpoint in `routers/tracks.py`:
  - `POST /api/tracks/{track_id}/link-file`, body `{"path": str}`.
    Validazioni: file esistente, estensione audio
    (mp3/flac/wav/aiff/aif/m4a/aac/ogg/opus/wma). Errori 400 con messaggio
    leggibile, 404 se la traccia non esiste.
    Esegue `attach_local_file` esistente (`services/acquisition.py`: setta
    `has_local_file`, `local_path`, `local_format`, `local_bitrate`,
    `audio_hash` best-effort) e azzera `last_download_outcome`/`last_download_reason`.
    Risponde con la Track aggiornata.
- Percorsi fuori da `LIBRARY_ROOT`/download dir sono ammessi: stesso pattern dei
  download slskd, l'audio-hash e' la chiave di riaggancio quando DjOrganizer
  sposta il file nella libreria canonica. Cratory legge il file, non lo muta.
- Formato/bitrate: da `read_audio_quality(path)` di `integrations/local_files.py`
  (gia' usata dall'indicizzazione; valori assenti restano null).

## Frontend

### Pagina `/downloads/issues` (nuova rotta App Router)

- Tabella: artista — titolo (link a `/tracks/{id}`), badge esito con tone
  coerente con "Da sistemare" (danger per not_found/failed, warning per
  needs_review), motivo (`last_download_reason`).
- Chip di filtro: Tutti / Non trovati / Da rivedere / Falliti, con contatori;
  filtro lato client sui dati di `downloadPending()`.
- Azioni per riga: Scegli file (riusa il modal di revisione Soulseek),
  Collega file (nuovo `LinkLocalFileModal`), Ignora (DELETE con conferma).
- Testata: pulsante "Riprova tutte" (endpoint esistente `retry-pending`) e
  link di ritorno a `/downloads`.
- La lista si aggiorna dopo ogni azione e al cambio di stato del job
  (stesso pattern della pagina downloads via `JobsProvider`).

### Pagina `/downloads`

- La sezione "Da sistemare" diventa un riassunto: contatori per esito
  (non trovati / da rivedere / falliti) + link "Vai all'archivio"
  (`/downloads/issues`). Restano invariati selettore playlist, ricerca
  manuale Soulseek e progresso job.

### `LinkLocalFileModal` (nuovo componente condiviso)

- Usato da dettaglio traccia e archivio.
- Campo di ricerca precompilato con "artista titolo", chiama
  `GET /api/files/search`, lista risultati con nome, cartella di provenienza,
  formato, dimensione e pulsante "Collega".
- Campo secondario "percorso esatto" per incollare un path assoluto.
- Al collega: `POST /api/tracks/{id}/link-file`; errori mostrati come Alert
  nel modal; al successo chiude e notifica il chiamante per il refresh.

### Dettaglio traccia `/tracks/[id]`

- Nella sezione Disco: pulsante "Collega file" (se `has_local_file` e' falso)
  o "Sostituisci file" (se vero). Apre il modal; al successo ricarica la
  traccia (badge "Posseduta", path visibile).

## Gestione errori

- `link-file`: 400 con messaggio specifico (file inesistente, estensione non
  audio), 404 traccia inesistente; l'hash non calcolabile non blocca
  (comportamento gia' presente in `attach_local_file`).
- `files/search`: query sotto i 2 caratteri restituisce lista vuota; cartelle
  non configurate o inesistenti vengono saltate senza errore.

## Test

- Pytest: `DELETE /api/downloads/pending/{id}` (azzera esito, 404);
  `POST /api/tracks/{id}/link-file` (successo con file temporaneo, path
  inesistente, estensione non audio, esito azzerato);
  `GET /api/files/search` (match case-insensitive su cartelle temporanee,
  cap risultati, query corta).
- Frontend: `npm run lint` e `npm run build`.

## Fuori scope

- Storico dei tentativi di download (tabella eventi): escluso esplicitamente.
- Retry per singola traccia: escluso, "Riprova tutte" resta globale.
- Spostamento/rinomina file: resta compito di DjOrganizer.
