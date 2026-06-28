# Design — Import playlist da cartella locale

**Data:** 2026-06-28
**Stato:** approvato (brainstorming), pronto per il piano di implementazione
**Ambito:** aggiungere una nuova sorgente di import — una cartella del filesystem locale — accanto a Spotify e import manuale.

## Contesto e obiettivo

Cratory è una webapp personale, locale/self-hosted e mono-utente. Oggi le playlist si
importano da Spotify (`POST /api/playlists/import`) e da testo incollato
(`POST /api/playlists/import-manual`). Entrambi gli endpoint convergono sulla stessa
funzione core `import_playlist()` in `services/playlist_import.py`, che gestisce
normalizzazione, deduplica, membership M2M, stato traccia e auto-enrichment.

**Obiettivo:** importare l'intera collezione DJ locale (file audio in una cartella) come
sorgente primaria, leggendo i metadati dai tag. La collezione locale può sovrapporsi a
quanto già importato da Spotify.

### Coerenza con le regole di progetto

- **Non si conservano file audio.** L'import legge i **tag** e calcola un hash di
  identità; non copia, non sposta e non conserva l'audio. Il path è un riferimento
  volatile (la cartella può cambiare). Coerente con `ARCHITECTURE.md` (l'app non
  conserva file audio; solo Shazam usa file temporanei per il fingerprinting).
- **BPM/key non si inventano.** L'import locale NON deriva feature di mixing
  dall'analisi audio: BPM/key arrivano dalla catena di enrichment esistente (provider
  esterni), come per Spotify e manuale.
- **Non si sovrascrive enrichment esistente.** Si riusa `_apply_fields` (riempie solo i
  campi vuoti). L'unico campo aggiornato deliberatamente è `local_path` (vedi sotto).

## Decisioni di prodotto (dal brainstorming)

| Tema | Decisione |
|------|-----------|
| Scopo | Specchio della collezione locale (sorgente primaria, sovrapposizione con Spotify ammessa) |
| Dedup cross-sorgente | **Tieni separate**: il file locale crea sempre una traccia distinta `source_type="local"`; nessuna fusione fuzzy con tracce Spotify |
| Identità traccia locale | **Hash dello stream audio** (robusto a spostamenti/rinomine e a modifiche dei tag) |
| Estensione hash | **Segmento iniziale ~60s** di audio decodificato (veloce su grandi collezioni) |
| Mapping cartelle | **Una cartella ricorsiva = una playlist** col nome della cartella |
| Selezione cartella | **File-browser servito dal backend**, confinato a una root configurabile |
| Tag mancanti | **Fallback dal nome file** (riusa il parser di `manual_import.parse_line`) |
| Cover art | **Ignorata per ora** (nessuna estrazione/serving immagini) |
| Esecuzione | **Job in background con progresso pollabile** (modello `enrichment_job.py`) |
| Approccio implementativo | **A** — modulo locale isolato che riusa `import_playlist()` |

## Architettura e componenti

### File nuovi (backend)

- **`integrations/local_files.py`** — lettore puro, senza DB.
  - `read_tags(path) -> dict` — artista, titolo, album, durata, anno, ISRC via `mutagen`.
  - `audio_hash(path) -> str` — SHA-256 dei primi ~60s di audio decodificato via ffmpeg.
  - Nuova dipendenza: `mutagen` in `requirements.txt`. ffmpeg di sistema è già assunto
    dal modulo Shazam.
- **`services/local_import.py`** — orchestrazione senza asincronia.
  - `scan_folder(path, recurse=True) -> list[str]` — elenco dei file audio.
  - `build_normalized(path) -> NormalizedTrack | None` — tag + fallback nome file + hash.
  - `import_local_folder(db, *, path, name, on_progress=None) -> dict` — fa il lavoro
    pesante (tag + hash) **file per file con `on_progress`**, accumula la lista di
    `NormalizedTrack`, poi chiama `import_playlist(platform="local", items=<normalizzati>,
    normalize=<identità>)`; ritorna il report (arricchito coi contatori `failed`/`errors`).
- **`services/local_import_job.py`** — job in background, stato in memoria con lock,
  un job alla volta. Ricalcato su `enrichment_job.py`: `job_state()`, `is_running()`,
  `start_job(path, name)`. A fine import chiama `_autoenrich(playlist_id)`.
- **`services/fs_browse.py`** — navigazione filesystem confinata a `LOCAL_IMPORT_ROOT`.
  - `browse(path=None) -> dict` — sottocartelle + conteggio file audio; valida che il
    path risolto (`realpath`) sia dentro la root.

### File modificati (backend)

- **`services/playlist_import.py`** — generalizzare `import_playlist` (miglioramento
  mirato al codice esistente, oggi hardcoded a Spotify): aggiungere un parametro
  `normalize: Callable[[Any], NormalizedTrack | None] = normalize_spotify_item` e
  sostituire la guardia `platform != "spotify"` (riga 194) e la chiamata fissa
  `normalize_spotify_item(item) if platform == "spotify" else None` (riga 220) con
  l'uso di `normalize`. Spotify resta invariato (default); il locale passa una funzione
  identità perché fornisce già `NormalizedTrack`. Comportamento Spotify/manuale immutato.
- **`routers/playlists.py`** — 3 endpoint nuovi (browse, import-local, status).
- **`schemas.py`** — `LocalDirEntry`, `LocalBrowseResponse`, `LocalFolderImportRequest`,
  `LocalImportJobStatus`.
- **`models.py`** — colonna nullable `local_path: str | None` su `Track`.
- **`db.py`** — migrazione idempotente per la colonna `local_path` (pattern `ensure_schema`).
- **`core/config.py`** — setting `local_import_root: str = ""` (vuoto = home utente).

### File nuovi/modificati (frontend)

- **`app/playlists/import-local/page.tsx`** — file-browser + nome playlist + avvio +
  barra di progresso con polling.
- **`lib/api.ts`** — `browseLocalFolder(path?)`, `importLocalFolder({path, name})`,
  `localImportStatus()` + tipi corrispondenti.
- **`app/playlists/page.tsx`** — CTA "Importa da cartella".
- Prima di toccare pagine/routing leggere `frontend/CLAUDE.md` (Next.js 16, breaking changes).

## Modello dati, identità e dedup

Mapping di una traccia locale sui campi `Track`:

- `source_type = "local"`
- `platform = "local"`
- `platform_track_id = <audio_hash>`
- `local_path = <percorso assoluto>` (**nuova colonna nullable**)
- `title`, `artist`, `album`, `year`, `duration_seconds` dai tag (o dal nome file)
- `isrc` solo se presente nel tag
- `url`, `album_art_url` = null

**Perché una colonna `local_path` dedicata:** l'identità è l'hash, non il path. Se un
file viene spostato/rinominato, alla ri-scansione l'hash combacia ma il path cambia: va
**aggiornato**. Il campo `url` ha semantica "URL streaming" e `_apply_fields` riempie
solo i campi vuoti; una colonna propria, aggiornata esplicitamente, tiene pulita la logica.

**Dedup — riuso totale, zero modifiche a `_find_existing`:** la funzione attuale
(`playlist_import.py`) matcha già su `platform + platform_track_id`. Con `platform="local"`
e `platform_track_id=hash`, la ri-scansione è idempotente senza nuovo codice di dedup.
Niente ISRC affidabile sui locali → nessuna fusione cross-sorgente (coerente con
"tieni separate"). Due file diversi con lo stesso brano restano due tracce.

**Aggiornamento del path:** aggiungere il campo `local_path: str | None = None` al
dataclass `NormalizedTrack`. In `_apply_fields` aggiungere una riga con semantica di
**overwrite-quando-presente**: `if norm.local_path: track.local_path = norm.local_path`.
Solo i NormalizedTrack locali valorizzano `local_path` (gli altri lo lasciano `None`,
quindi nessun effetto su Spotify/manuale), e un file spostato/rinominato aggiorna il
path pur mantenendo l'identità via hash. È l'unico campo sovrascritto deliberatamente;
BPM/key/enrichment restano intoccati.

**Stati traccia:** invariati — nuovo brano `imported`, poi enrichment →
`ready_for_set` / `missing_features`.

## Flusso di import (job in background)

1. **Avvio:** `POST /api/playlists/import-local` con `{ path, name?, recurse=true }`.
   Valida che `path` sia dentro `LOCAL_IMPORT_ROOT` ed esista, avvia il job, ritorna
   `202 { job_id }`. Se un import locale è già in corso → `409`.
2. **Scansione:** `os.walk` ricorsivo, filtra le estensioni audio. Conta i file → `total`.
3. **Fase pesante — per ogni file** (qui si riporta il progresso, `processed/total`):
   - `read_tags`; se artista/titolo mancano → fallback dal nome file (`parse_line`).
   - `audio_hash` sui primi ~60s.
   - Se ffmpeg fallisce / file illeggibile → conta come `failed`, registra il path in
     `errors[]`, **prosegue** (un file rotto non aborta il job).
   - Costruisce `NormalizedTrack` (`platform="local"`, `platform_track_id=hash`,
     `local_path=path`) e lo accumula nella lista.
4. **Import:** passa la lista già normalizzata a `import_playlist(db, platform="local",
   name=..., items=<normalizzati>, normalize=<identità>, prune=False)`. Riuso totale:
   create/update, membership M2M, dedup per hash, update `local_path`. Singola
   transazione/commit a fine import (le scritture DB sono leggere; il costo è nella fase
   3). La playlist si crea **solo se `total > 0`** (niente playlist vuote fantasma).
5. **Auto-enrichment:** a fine import `_autoenrich(playlist_id)`, identico alle altre
   sorgenti. Best-effort: un fallimento non annulla l'import già committato.

**Performance:** il progresso pollabile riflette la fase 3 (tag + hash), che è il vero
collo di bottiglia. Elaborazione **sequenziale** in v1 (I/O-bound; eventuale
parallelismo è ottimizzazione futura — YAGNI).

Estensioni audio supportate (v1): `.mp3 .flac .m4a .aac .aiff .aif .wav .ogg .opus .wma`.

## API

### 1. File-browser
```
GET /api/playlists/local/browse?path=<dir>
```
- `path` omesso → contenuto di `LOCAL_IMPORT_ROOT`.
- Valida `realpath` dentro la root (anti `../` e symlink); altrimenti `403`.
- Risposta: `{ current_path, parent_path|null, dirs: [{name, path, audio_file_count}] }`.
- Mostra solo sottocartelle (l'unità di import è la cartella), non i singoli file.

### 2. Avvio import
```
POST /api/playlists/import-local
body: { path: str, name?: str, recurse: bool = true }
→ 202 { job_id } | 409 job già in corso | 400 path fuori root/inesistente
```
`name` default = nome della cartella scelta.

### 3. Stato del job
```
GET /api/playlists/import-local/status
→ { state: idle|running|done|error, processed, total, created, updated,
    failed, playlist_id?, errors[] }
```

Schemi Pydantic nuovi in `schemas.py`, tutti validati. Convenzioni riusate: prefisso
`/api/playlists`, `Depends(get_db)`, mappatura errori del router, pattern di polling
identico all'enrichment.

### Sicurezza

`local_import_root` di default = home dell'utente (configurabile via env). Browse e
import non risolvono mai un path sopra la root. Sufficiente per app mono-utente locale;
assunzione documentata esplicitamente.

## Frontend

Pagina `app/playlists/import-local/page.tsx`, coerente col design system
"editorial archive" e con le altre pagine di import:

1. **File-browser** — breadcrumb/path corrente, pulsante "su" (parent), lista
   sottocartelle con conteggio file audio; click per navigare. Pulsante
   "Importa questa cartella" sulla directory corrente (ricorsiva).
2. **Nome playlist** — precompilato col nome cartella, editabile.
3. **Avvio** — `POST .../import-local` → `job_id`, poi polling dello status.
4. **Progresso** — barra `processed/total` + contatori `created/updated/failed` live.
   A fine job: link alla playlist; se `failed > 0`, elenco espandibile dei file saltati.

`lib/api.ts`: nuove funzioni e tipi (`LocalDirEntry`, `LocalBrowseResponse`,
`LocalImportJobStatus`). CTA "Importa da cartella" nella pagina playlists.

## Error handling

- Path fuori root / inesistente → `400`, nessun job.
- Job già in corso → `409`.
- File singolo illeggibile / ffmpeg fallisce / hash non calcolabile → `failed` +
  `errors[]`, il job prosegue.
- Tag mancanti → fallback nome file; se non parsabile, traccia grezza (titolo = nome file).
- ffmpeg assente → rilevato all'avvio con messaggio chiaro.
- Cartella senza file audio → job `done` con `total=0`, nessuna playlist creata.
- Errore enrichment post-import → non blocca (import già committato).

## Testing (TDD)

Backend (`backend/tests/`):

- **`local_files`**: `read_tags` per formato (mp3/flac/m4a); `audio_hash` deterministico
  (stesso file → stesso hash; tag diversi/stesso audio → stesso hash; audio diverso →
  hash diverso). Fixture audio minime nel repo di test.
- **`local_import`**: scansione ricorsiva conta i file giusti e ignora i non-audio;
  fallback nome file; ri-scansione idempotente (nessun doppione); file spostato/rinominato
  → `local_path` aggiornato senza doppione; due file = stesso brano → due tracce separate;
  brano locale NON si fonde con l'equivalente Spotify.
- **`fs_browse`**: path fuori root rifiutato (incluso `../` e symlink).
- **Router**: avvio → `202`+`job_id`; `409` se job attivo; `400` path invalido; status
  riflette i contatori; playlist creata solo con `total > 0`.
- **Regressione**: i test esistenti di Spotify/manuale restano verdi (comportamento intatto).

Frontend: verifica manuale del flusso (browse → import → progresso → playlist) via preview,
più `npm run lint` e `npm run build`.

## Fuori scope (esplicito)

- Estrazione/serving cover art incorporate.
- Fusione cross-sorgente locale↔Spotify.
- Analisi audio per BPM/key (resta alla catena di enrichment esterna).
- Parallelizzazione della scansione/hash (ottimizzazione futura).
- Astrazione `ImportSource` pluggable (refactor non richiesto ora).
