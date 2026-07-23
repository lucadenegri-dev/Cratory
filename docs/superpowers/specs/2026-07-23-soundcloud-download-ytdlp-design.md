# Download SoundCloud via yt-dlp nel dettaglio traccia — design

Data: 2026-07-23

## Obiettivo

Aggiungere, **solo nella pagina di dettaglio traccia** (`/tracks/[id]`) e **solo per le
tracce SoundCloud** (`platform == "soundcloud"` con `url` presente), un bottone "Scarica da
SoundCloud" accanto a "Cerca su Soulseek". Il click scarica l'audio della traccia via yt-dlp,
lo transcodifica in MP3 e lo collega alla `Track` come file posseduto, esattamente come fa
l'acquisizione Soulseek.

## Decisioni (confermate)

- **Formato**: MP3. Estrazione via `FFmpegExtractAudio` di yt-dlp, qualità VBR ~V0
  (`preferredquality="0"`), nessun upscaling forzato (la sorgente SoundCloud è già lossy
  ~128 kbps). MP3 è leggibile da Rekordbox, Set Builder e dal player docked in-app.
- **Esecuzione**: job in background condiviso con l'infrastruttura del download Soulseek.
  Riusa lo stesso stato in memoria, lo stesso lock (un solo download alla volta, Soulseek
  *o* SoundCloud) e la **stessa barra di progresso globale**.
- **Cartella di download**: la stessa di Soulseek, cioè `settings.slskd_download_dir`
  (`SLSKD_DOWNLOAD_DIR` nel `.env`). Nessuna nuova variabile d'ambiente.
- **Linking**: `attach_local_file()` — identico a Soulseek. Nessuna logica di possesso nuova.
- **No auto-refetch**: a job concluso la pagina non si aggiorna da sola (serve un reload per
  vedere il badge "Posseduto"): **parità col flusso Soulseek attuale**, scelta deliberata.

## Contesto (com'è oggi)

- Bottone "Cerca su Soulseek": `frontend/app/tracks/[id]/page.tsx` (handler `searchSoulseek`,
  card "Disco", visibile se `!track.has_local_file`). Chiama `downloadTrackAuto(track.id)` →
  `POST /api/downloads/track/auto`.
- Job Soulseek: `backend/app/services/soulseek_download_job.py` — mono-utente, uno-job-per-
  volta, `_state: dict` + `threading.Lock`, worker daemon `_run`. Persiste su ogni Track
  `last_download_outcome/reason/path`.
- Linking possesso: `backend/app/services/acquisition.py` → `attach_local_file(db, track, *,
  path, fmt, bitrate)` (setta `has_local_file/local_path/local_format/local_bitrate/audio_hash`
  e deduplica per path/hash).
- yt-dlp già dipendenza: metadati SoundCloud (`integrations/soundcloud.py`, mai audio) e
  download audio temporaneo per Shazam (`services/mix_identify.py::download_audio`, template
  del pattern `format="bestaudio/best"`).
- Identità SoundCloud: `track.platform == "soundcloud"`, `track.url` = pagina pubblica
  `soundcloud.com/...`.
- Barra di progresso: `frontend/components/jobs-provider.tsx` polla `GET /api/downloads/status`
  e mappa la riga `download`. Riusando lo stesso `_state`, il download SoundCloud appare
  automaticamente in quella riga: nessun nuovo poller né nuovo endpoint di stato.

## Architettura

### A. `backend/app/integrations/soundcloud_audio.py` (nuovo)

Unità isolata, l'unico punto che tocca yt-dlp/audio per questa feature.

- `download_track_audio(url: str, dest_dir: str) -> str`
  - Valida l'URL con la **stessa allowlist host** di `integrations/soundcloud.py` (host
    `soundcloud.com` e sottodomini ammessi; rifiuta `file://`, schemi non http(s), host
    estranei → SSRF guard). Per non duplicare, `soundcloud.py` espone un helper pubblico
    `validate_soundcloud_url(url) -> str` (wrapper sul `_validate_url` esistente) usato da
    entrambi.
  - Se `dest_dir` è vuoto → `SoundCloudAudioError` (il router lo previene già a monte).
  - Opzioni yt-dlp: `quiet`, `no_warnings`, `noplaylist=True`, `format="bestaudio/best"`,
    `socket_timeout`, `outtmpl` dentro `dest_dir` (template basato su titolo, sanitizzato da
    yt-dlp), `postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
    "preferredquality": "0"}]`.
  - Path finale: `info["requested_downloads"][0]["filepath"]` (dopo il postprocessor);
    fallback = `splitext(ydl.prepare_filename(info))[0] + ".mp3"`.
  - Errori yt-dlp/ffmpeg → `SoundCloudAudioError` con messaggio leggibile.
- Eccezioni: `SoundCloudAudioError(RuntimeError)`; riusa la mappatura URL-invalido esistente
  (`SoundCloudInvalidUrl`) dove serve.

### B. `backend/app/services/soulseek_download_job.py` (edit)

- Generalizzare l'avvio: `_start` accetta un worker (o si aggiunge un `_start_worker(worker,
  *args, total)` che condivide `_lock` e il reset di `_state`). Nessuna modifica al flusso
  Soulseek esistente.
- `start_soundcloud_track_job(track_id: int) -> dict`: avvia `_run_soundcloud` con `total=1`,
  stesso guard "già in esecuzione".
- `_run_soundcloud(track_id: int) -> None`:
  - `db = SessionLocal()`; `download_dir = settings.slskd_download_dir`.
  - `track = get_track(db, track_id)`; se `None` → stato `error`/`failed` e ritorno.
  - `_state["current_label"] = _track_label(track)`.
  - `path = download_track_audio(track.url, download_dir)` → `quality =
    read_audio_quality(path)` → `attach_local_file(db, track, path=path,
    fmt=quality["format"], bitrate=quality["bitrate"])`. `outcome = "downloaded"`.
  - In errore (`SoundCloudAudioError` o altro): `outcome = "failed"`, `reason = <codice/msg>`,
    log con `logger.exception`.
  - Aggiorna i contatori di `_state` (`downloaded`/`failed`, `processed=1`, `items.append`),
    persiste `track.last_download_outcome/reason/path`, `db.commit()`, chiude con
    `status="done"` e `finished_at`. **Non** chiama mai `get_slskd_client`.

### C. `backend/app/routers/downloads.py` (edit)

- `class TrackSoundcloudIn(BaseModel): track_id: int`.
- `POST /api/downloads/track/soundcloud` (status 202). Pre-flight con `api_error`:
  - `409 ytdlp_unavailable` se yt-dlp non importabile (`soundcloud_available()`).
  - `409 ffmpeg_unavailable` se `shutil.which("ffmpeg")` è `None`.
  - `409 download_dir_not_configured` se `settings.slskd_download_dir` è vuoto.
  - `409 download_already_running` se `job.is_running()`.
  - `404 track_not_found` se la Track non esiste.
  - `422 not_a_soundcloud_track` se `platform != "soundcloud"` o `url` mancante.
  - Successo: `return {"available": True, **job.start_soundcloud_track_job(track.id)}`.

### D. Frontend

- `frontend/lib/api/downloads.ts`: `downloadTrackSoundcloud(trackId: number)` →
  `apiPost<DownloadStatus>("/api/downloads/track/soundcloud", { track_id: trackId })`.
- `frontend/app/tracks/[id]/page.tsx`:
  - Stato locale `scState: "idle" | "running" | "queued"` e `scError` (clone di
    `dlState`/`dlError`).
  - Handler `downloadSoundcloud` (clone di `searchSoulseek` che chiama
    `downloadTrackSoundcloud`).
  - Nuovo `<Button>` accanto a quello Soulseek nella card "Disco", reso solo se
    `track.platform === "soundcloud" && track.url && !track.has_local_file`. Icona `Download`,
    label `t.tracks.downloadSoundcloud`; stato queued → `t.tracks.soundcloudQueued`.
  - `scError` mostrato inline come `dlError`.
- i18n (`frontend/lib/i18n/it.ts` e `en.ts`), sezione `tracks`:
  - `downloadSoundcloud`: "Scarica da SoundCloud" / "Download from SoundCloud".
  - `soundcloudQueued`: "Download avviato" / "Download started".

## Flusso dati

1. Utente clicca "Scarica da SoundCloud" su una traccia SoundCloud senza file locale.
2. `POST /api/downloads/track/soundcloud {track_id}` → pre-flight → `start_soundcloud_track_job`.
3. Il worker scarica `track.url` in `SLSKD_DOWNLOAD_DIR`, transcodifica in MP3, legge
   formato/bitrate, `attach_local_file` marca il possesso; `last_download_outcome` persiste.
4. `jobs-provider` mostra il progresso nella barra globale (riga `download`) pollando
   `GET /api/downloads/status`. A fine job la Track è posseduta (visibile dopo reload).

## Gestione errori

- Tutti i rami di gating usano `api_error` con codici espliciti (sopra).
- Un download fallito imposta `outcome="failed"` sul Track e sulla barra; non lascia file
  a metà referenziati come posseduti (`attach_local_file` chiamato solo su successo).
- yt-dlp/SoundCloud fragili per natura (cambi lato SoundCloud, tracce Go+/DRM che non
  streammano): il fallimento è gestito come "failed" con reason, non crasha il job.

## Docs / policy da aggiornare

- `CLAUDE.md` (intro): l'eccezione di **acquisizione persistente** ora include, oltre a
  Soulseek, il download SoundCloud via yt-dlp (collega il file alla Track, `has_local_file`).
- `docs/API.md`: nuovo endpoint `POST /api/downloads/track/soundcloud`.
- `PROGRESS.md`: voce di milestone.
- Nota policy: scaricare audio da SoundCloud può violare i loro ToS; coerente con
  l'acquisizione Soulseek già adottata per questo strumento personale/self-hosted. Citato per
  consapevolezza, non è un blocco.

## Test

- `soundcloud_audio`: `validate_soundcloud_url` rifiuta `file://` e host non-soundcloud
  (mappa su errore URL-invalido), accetta un link soundcloud valido. Nessuna rete.
- Router: i sei rami di gating (`ytdlp_unavailable`, `ffmpeg_unavailable`,
  `download_dir_not_configured`, `download_already_running`, `track_not_found` 404,
  `not_a_soundcloud_track` 422) e l'happy path 202 con `start_soundcloud_track_job` stubbato.
- Job: `download_track_audio` / `read_audio_quality` / `attach_local_file` mockati → `_state`
  arriva a `done`, `downloaded=1`, `has_local_file=True`, `last_download_outcome="downloaded"`;
  ramo di fallimento (download solleva) → `failed=1`, `outcome="failed"`.

## Fuori scope

- Nessuna coda persistente / nessun `Download` model (si resta sul pattern uno-job-per-volta).
- Nessun download SoundCloud da liste/batch: solo la singola traccia dal dettaglio.
- Nessun auto-refetch della pagina a fine job (parità Soulseek).
- Nessuna scrittura di tag sul file scaricato (i tag restano compito di Sortory).
