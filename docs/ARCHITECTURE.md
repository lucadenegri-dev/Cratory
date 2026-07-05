# Architettura

Cratory e' una webapp locale/self-hosted, mono-utente, per trasformare playlist
streaming in materiale operativo da DJ: libreria arricchita, bozze di set, gap
analysis, discovery e corpus di mix identificati.

## Principi

- Il motore deterministico gestisce fatti, score, deduplica, ruoli, ranking e validazione.
- L'AI gestisce linguaggio, narrativa, interpretazione del prompt e spiegazioni.
- BPM, Camelot/key e feature musicali non vengono inventati.
- Un dato musicale gia' presente non viene sovrascritto dai provider.
- Spotify non fornisce feature di mixing: serve per identita', metadata, import/export.
- L'AI non riceve mai tutta la libreria: il Candidate Engine le passa al massimo 60 candidate.
- Ogni output AI passa da schema Pydantic e Validation Engine.
- L'app non riproduce audio. Non conserva file audio, con un'eccezione dichiarata:
  l'acquisizione persistente via Soulseek/slskd, collegata a una `Track` esistente
  (`has_local_file`/`local_path`/`local_format`/`local_bitrate`). Resta distinta dal
  modulo Shazam, che scarica audio solo in modo temporaneo per il fingerprinting e
  non lo conserva.

## Flusso principale

```text
Spotify / import manuale
  -> Playlist Importer
  -> normalizzazione + deduplica
  -> SQLite
  -> Music Feature Enrichment con cache
  -> Library Explorer / Gap Analysis
  -> Candidate Engine
  -> Set Builder deterministico
  -> AI Set Agent opzionale
  -> Validation Engine
  -> Set Editor / Export / Discovery write-back
```

Discovery ha due rami paralleli, entrambi orientati al **gusto** (non alla
compatibilita' tecnica, che resta del Set Builder). Espansione playlist:

```text
playlist importata
  -> seed artisti/tracce
  -> Last.fm similarity
  -> dedup vs libreria
  -> resolver Spotify /search
  -> ranking per gusto + annotazione etichetta (boost se gia' collezionata)
  -> spiegazione AI opzionale
  -> add to library
```

Crate digging (Scava), sorgente alternativa via Discogs (niente Last.fm/Spotify):

```text
seme: genere o etichetta
  -> Discogs search (release per genere/stile o per label)
  -> lead non posseduti, dedup vs libreria + dedup varianti
  -> ranking per domanda (want/have), profondita' e novita'
  -> preset Familiare/Bilanciato/Avventuroso, cap per artista
  -> add to library
```

La Gap Analysis resta una lettura deterministica delle mancanze della playlist, ma la
vecchia sezione Discovery che suggeriva tracce partendo dai gap e' stata rimossa.

Identificazione mix:

```text
URL SoundCloud/Mixcloud/YouTube
  -> yt-dlp download temporaneo
  -> ffmpeg segmenti audio
  -> Shazam recognizer
  -> dedup match consecutivi
  -> DjSet + DjSetTrack
```

Le tracce identificate nei mix non entrano nella libreria principale: restano un corpus
separato per analisi e suggerimenti futuri.

Acquisizione file via Soulseek (slskd), distinta dal download temporaneo Shazam:

```text
Track in libreria (identita' streaming)
  -> SlskdClient.search (slskd REST)
  -> selezione deterministica (qualita' + match nome + disponibilita')
     | ricerca libera -> selezione manuale (/api/downloads/search + /manual)
  -> auto-pick (blocco playlist) | mini-selettore (Discovery)
  -> slskd enqueue + polling transfer
  -> attach_local_file: has_local_file + local_path/format/bitrate
```

E' deterministica (zero AI), mono-job (un download alla volta) e best-effort: un
errore su una traccia non ferma il job. Richiede slskd configurato; senza, gli
endpoint rispondono `409`. Il file resta collegato alla `Track` come riferimento
locale, non viene ricaricato ne' ridistribuito dall'app.

Oltre all'auto-pick, `POST /api/downloads/search` offre ricerca libera su slskd con
selezione manuale del candidato (`POST /api/downloads/manual`). Gli esiti da rivedere
(`needs_review|not_found|failed`) restano in coda "da sistemare", persistiti su
`Track.last_download_outcome`/`last_download_reason` cosi' da sopravvivere a job e
riavvii (`GET /api/downloads/pending`, `DELETE /api/downloads/pending/{track_id}`,
`POST /api/downloads/retry-pending`). Un file gia' su disco puo' anche essere
collegato manualmente dal dettaglio traccia (`POST /api/tracks/{track_id}/link-file`,
ricerca per nome in `LIBRARY_ROOT` e nella cartella download slskd via
`GET /api/files/search`), con lo stesso `attach_local_file`/`audio_hash`
dell'acquisizione.

## Disk-first

La libreria e' il disco: il possesso di una traccia (`has_local_file`) non e' un
side-effect dell'acquisizione Soulseek soltanto, ma lo stato di una cartella
canonica che Cratory indicizza attivamente. Cratory legge i file audio ma non li
muta mai — tag e organizzazione restano competenza di DjOrganizer.

- **`LIBRARY_ROOT`**: cartella organizzata (gestita da DjOrganizer) che Cratory
  indicizza da Impostazioni -> "Libreria (disco)". Vuota = indicizzazione disattiva.
  L'indicizzazione parte anche automaticamente a ogni avvio dell'app (job in
  background, se `LIBRARY_ROOT` e' configurata), oltre che on-demand.
- **`ARCHIVE_ROOT`**: archivio delle scartate (PASSED di DJPlayer), scansionato
  insieme alla libreria. Un match in archivio marca la Track `archived=True` e
  toglie il possesso, senza creare tracce nuove; il possesso in Libreria vince
  sempre sullo scarto e riabilita la traccia.
- **`audio_hash`**: SHA-256 dei primi secondi di audio decodificato via ffmpeg (mono,
  22050 Hz, s16le) — stabile a rinomina e retag, a differenza di path o tag ID3/MP4.
  Calcolato sia dall'indicizzazione di libreria sia dall'acquisizione Soulseek
  (`attach_local_file`), cosi' i due percorsi convergono sullo stesso identificativo.
- **`library_index`** (`backend/app/services/library_index.py`, deterministico):
  per ogni file sotto `LIBRARY_ROOT` calcola l'hash e cerca un match nell'ordine
  `audio_hash -> digest legacy (import locali storici, in platform_track_id) ->
  ISRC -> fuzzy artist+title`; se non trova nulla crea una nuova `Track`. I tag del
  file riempiono solo i campi identita' vuoti (mai sovrascrivere enrichment o
  correzioni manuali). Scan incrementale: un file con path+mtime+size invariati non
  viene ri-hashato. Riconciliazione: un possesso il cui file non e' piu' presente
  nello scan (spostato, cancellato) perde `has_local_file`/`local_path` ma mantiene
  `audio_hash`, cosi' il riaggancio e' immediato se il file ricompare altrove. Guard
  anti-unmount: uno scan a zero file (radice vuota, path sbagliato, disco smontato)
  non tocca i possessi esistenti. `duplicates` conta i file con lo stesso hash visti
  nello stesso run (il primo vince; la dedup su disco resta compito di DjOrganizer).
  Le tracce nuove create dall'indice avviano l'enrichment automaticamente
  (best-effort). Esposto via `POST /api/library/index` (202, job async) e
  `GET /api/library/index/status`; risponde `409` se `LIBRARY_ROOT` non e' configurata.
- **`GET /api/tracks/lookup`**: bridge read-only per DjOrganizer, nessuna scrittura
  ne' side-effect. Query `isrc` oppure `artist`+`title` (altrimenti 422); match
  `isrc` (confidence 100) poi fuzzy artist+title (confidence 70), sempre `limit(1)`
  per non far fallire il lookup su duplicati; mai 404, risponde `found: false`.
- Il possesso alimenta anche il Set Builder: `SetGenerationRequest.owned_only` (default
  `True`) filtra le candidate del Candidate Engine alle sole tracce con file locale;
  la scelta e' persistita su `Setlist.owned_only` e rispettata anche da editor
  (alternative, sostituzione traccia — 422 se la sostituta non e' posseduta e il set
  e' nato "solo posseduti").
- **Fingerprinting AcoustID** (`backend/app/services/fingerprint.py`, job in background
  `fingerprint_job.py`): identifica via audio le tracce possedute senza `mbid`, un job
  on-demand distinto dall'indicizzazione. Esposto via `POST /api/library/fingerprint` e
  `GET /api/library/fingerprint/status`.

## Layer backend

```text
backend/app/
  routers/        endpoint FastAPI, solo HTTP e mapping errori
  services/       logica applicativa deterministica e orchestrazione
  repositories.py query SQLAlchemy e mutazioni DB
  models.py       modelli SQLAlchemy
  db.py           sessione/engine, ensure_schema e migrazioni idempotenti
  schemas.py      request/response Pydantic
  serializers.py  ORM -> Pydantic, campi derivati
  integrations/   client esterni dietro interfacce
  core/           config, logging
  tools/          script di manutenzione (es. clean_user_data)
```

I router non devono contenere logica di business. Le integrazioni esterne devono
essere iniettabili o isolabili, cosi' i test possono usare fake client senza rete.

## Motore deterministico

Responsabilita':

- import playlist e import manuale;
- deduplica con priorita' `ISRC -> platform_track_id -> artist+title+duration -> fuzzy`;
- applicazione enrichment con fonte/confidenza;
- stato traccia (`imported`, `enriched`, `ready_for_set`, `missing_features`, `low_confidence`);
- score BPM, Camelot, energia, mood, genere e durata;
- classificazione transizioni;
- assegnazione ruoli nell'arco del set;
- candidate filtering con cap 60;
- gap analysis;
- discovery ranking;
- validazione output AI.

L'assenza di una feature non deve bloccare il sistema: gli score parziali usano valori
neutri dove possibile e lo stato traccia segnala cosa manca.

## AI

L'AI puo':

- interpretare prompt liberi;
- proporre una direzione narrativa;
- spiegare scelte e transizioni;
- suggerire alternative creative;
- commentare candidati Discovery;
- classificare il genere come anello di riserva della catena enrichment (solo a
  genere vuoto, marcato `genre_source="ai"`, mai sovrascrive generi esistenti).

L'AI non puo':

- inventare track_id;
- inventare BPM/key/ISRC/fonti;
- selezionare tracce fuori dalle candidate ricevute;
- bypassare il Validation Engine;
- toccare BPM/key o sovrascrivere generi gia' presenti con la classificazione genere.

Modalita' Set Builder:

- `technical`: prudente, basata sui dati forniti.
- `creative`: usa anche conoscenza musicale generale, ma resta vincolata a candidate e validazione.

## Modello dati

Entita' principali:

- `Playlist`: playlist importata da Spotify o import manuale.
- `Track`: traccia della libreria, con identita' streaming, metadata editoriali,
  feature musicali, stato e tracciabilita' enrichment. Ownership file locale
  (indicizzazione `LIBRARY_ROOT`, acquisizione Soulseek o collegamento manuale
  link-file): `has_local_file`, `local_path`, `local_format`, `local_bitrate`,
  `audio_hash` (vedi "Disk-first"). Altri campi: `mbid` (da fingerprinting
  AcoustID), `archived` (file finito nell'archivio delle scartate),
  `local_mtime`/`local_size` (scan incrementale), `last_download_outcome`/
  `last_download_reason` (coda "da sistemare" dei download).
- `playlist_tracks`: tabella associativa M2M (Playlist <-> Track) con `added_at`
  per-playlist. Un brano puo' appartenere a piu' playlist; l'import aggiunge
  membership senza sovrascrivere.
- `Setlist`: set generato, prompt, strategia, spiegazione globale, validazione e
  `owned_only` (garanzia "solo posseduti", vedi "Disk-first").
- `SetlistTrack`: posizione, ruolo, score, note di transizione, motivo AI e rischio.
- `EnrichmentCache`: cache provider (catena feature, genere AI, AcoustID), incluso
  not-found.
- `SpotifyToken`: token OAuth Spotify persistiti per l'utente locale.
- `DjSet`: mix esterno identificato via Shazam, separato dalla libreria.
- `DjSetTrack`: traccia identificata dentro un `DjSet`.
- `AppState`: chiave-valore persistente per stato applicativo (es. `last_index_at`).

Campi legacy Rekordbox come beatgrid, cue, `rekordbox_track_id`, `play_count` e
`tonality` sono fuori modello.

## Enrichment feature

Catena attuale:

```text
Deezer -> MusicBrainz -> AcousticBrainz -> GetSongBPM -> Last.fm
```

Ruoli:

| Fonte | Ruolo |
|---|---|
| Deezer | BPM via ISRC, senza API key |
| MusicBrainz | ISRC, MBID, release, label, genere/canonical fallback |
| AcousticBrainz | BPM, key/Camelot, mood, danceability, vocalness via MBID |
| GetSongBPM | BPM, key/Camelot, danceability con fallback fuzzy |
| Last.fm | genere, mood dai tag e similarita' Discovery |

La catena passa un `context` accumulato ai provider successivi. L'MBID — trovato da
MusicBrainz o ricavato dal fingerprinting AcoustID dei file posseduti (`Track.mbid`)
e passato nel `context` della catena — abilita il lookup diretto MusicBrainz e
AcousticBrainz.

Catena del genere: `manual` > provider (Last.fm/MusicBrainz) > anello AI in batch
(solo a genere vuoto, cache provider `genre_ai`, `genre_source="ai"`, mai
sovrascrive) > tag del file (`genre_source="file_tag"`, applicato dall'indicizzazione
di libreria, ultima spiaggia).

L'energia e' stimata deterministicamente quando nessun provider la fornisce.

## Integrazioni

| Integrazione | Stato | Note |
|---|---|---|
| Spotify | attiva | OAuth, import, resolver Discovery, export playlist |
| Deezer | attiva | gratuita, BPM via ISRC |
| MusicBrainz | attiva | richiede User-Agent configurato |
| AcousticBrainz | attiva | dataset storico congelato al 2022 (bassa copertura sulle uscite recenti), nessuna API key |
| GetSongBPM | attiva | API key opzionale/consigliata |
| Last.fm | attiva | API key per enrichment tag e Discovery |
| Discogs | attiva | crate digging Discovery "Scava" per genere/etichetta; funziona senza token, `DISCOGS_TOKEN` alza il rate limit |
| AcoustID | attiva se configurata | fingerprinting dei file posseduti -> MusicBrainz Recording MBID (`Track.mbid`); richiede `ACOUSTID_API_KEY` + binario `fpcalc` (Chromaprint); rate ~3 req/s; cache in `EnrichmentCache` (provider `acoustid`) |
| LLM | attiva se configurata | output strutturati e validati |
| Shazam | attiva se dipendenze presenti | ffmpeg, yt-dlp, shazamio |
| slskd (Soulseek) | attiva se configurato | download via REST API; `SLSKD_URL`/`SLSKD_API_KEY`/`SLSKD_DOWNLOAD_DIR` |
| SoundCloud import | backlog | da valutare fattibilita' API |
| PostgreSQL | backlog | SQLite basta per mono-utente |

Spotify `/recommendations` non deve essere usato: per app nuove o in development mode
puo' restituire 403/404. Discovery usa Last.fm per similarita' e Spotify solo come
resolver via `/search`.

## Persistenza e migrazioni

SQLite resta il database operativo:

```text
backend/data/djassistant.db
```

`ensure_schema()` crea tabelle e applica migrazioni idempotenti. Non c'e' Alembic.
Per cambio nome prodotto, non rinominare automaticamente il DB: pianificare una
migrazione o mantenere il path legacy per compatibilita'.
