# API

Contratti REST correnti del backend FastAPI. Tutte le response principali sono
validate con Pydantic in `backend/app/schemas.py`. Superficie verificata contro
i router in `backend/app/routers/`.

Base locale:

```text
http://localhost:8000
```

## Health

```text
GET /api/health
```

## Pipeline

```text
GET /api/pipeline
```

Snapshot unico per la striscia di orientamento in dashboard. Response `PipelineOut`:
conteggi libreria (`playlists`, `total_tracks`, `missing_key`, `wishlist`,
`archived_count`, `with_local_file`, `analyze_pending`, `ready_for_set`), stato
download (`download_active`, `download_pending`) e stato disco (`inbox_files` da
`SLSKD_DOWNLOAD_DIR`, `organizer_url` da `ORGANIZER_URL`). `analyze_pending` conta le
tracce possedute senza BPM o senza key, cioe' quante restano da "analizzare in
Rekordbox ed importare" (stesso numero di `GET /api/rekordbox/pending`). `inbox_files`
e' `null` quando `SLSKD_DOWNLOAD_DIR` non e' configurata o non esiste (fase neutra,
non errore). L'indicizzazione della libreria non e' piu' un campo di questo snapshot
(i vecchi `files_on_disk`/`index_mismatch`/`last_index_at` sono stati rimossi): si
lancia dal pulsante "Indicizza" nella nav.

## Rekordbox (fonte di BPM/key)

```text
GET  /api/rekordbox/pending
POST /api/rekordbox/import
```

`GET /api/rekordbox/pending` conta le tracce possedute (`has_local_file`) ancora
senza BPM o senza Camelot key. Response: `{pending}`.

`POST /api/rekordbox/import` (multipart, campo `file`) importa l'XML esportato da
Rekordbox (`File > Export Collection in xml format`). Per ogni traccia dell'XML
cerca la `Track` posseduta corrispondente nell'ordine: path normalizzato NFC ->
`audio_hash` di fallback (gated sul basename) -> fuzzy artist+title. Riempie
`bpm`/`camelot_key` **solo se assenti** (non sovrascrive mai un dato gia'
presente) e ricalcola `energy` quando il BPM viene impostato. Response:
`{in_file, matched, unmatched, bpm_set, key_set, energy_set}`. `400` su file
vuoto o XML non valido/non sicuro.

## Playlists

```text
GET    /api/playlists/spotify/available
POST   /api/playlists/import
POST   /api/playlists/{playlist_id}/sync
POST   /api/playlists/import-manual
POST   /api/playlists/create-from-tracks
GET    /api/playlists
GET    /api/playlists/{playlist_id}
DELETE /api/playlists/{playlist_id}
GET    /api/playlists/{playlist_id}/tracks
POST   /api/playlists/{playlist_id}/discovered-tracks
GET    /api/playlists/{playlist_id}/gaps
GET    /api/playlists/library/gaps
```

`GET /api/playlists/spotify/available` elenca solo le playlist **possedute**
dall'utente collegato (quelle altrui che segue non sono importabili in dev mode).
`POST /api/playlists/import` importa una playlist Spotify o i liked tracks.
`POST /api/playlists/{playlist_id}/sync` riallinea una playlist gia' importata con
Spotify: importa le nuove tracce e scollega quelle rimosse (che restano in libreria).
`DELETE /api/playlists/{playlist_id}` rimuove la playlist e i suoi "lead orfani":
tracce senza file locale che non sono in nessun'altra playlist ne' in un set salvato
(le tracce su disco, o presenti in altra playlist/set, restano). Risponde `200` con
`{deleted_tracks}` (quante tracce orfane sono state rimosse), `404` se non esiste.
`POST /api/playlists/import-manual` crea una playlist da testo incollato. Nessuno di
questi avvia piu' enrichment: il testuale (titolo/artista/album/label/genere) e' di
DjOrganizer, BPM/key arrivano solo dall'import Rekordbox.
`POST /api/playlists/create-from-tracks` (`201`) crea una playlist manuale
componendo tracce gia' in libreria (disk-first), nell'ordine fornito. Request:
`{name, track_ids}`. Response: `PlaylistOut`. `422` se il nome e' vuoto o un
track_id non esiste.
`POST /api/playlists/{playlist_id}/discovered-tracks` aggiunge a quella playlist una
traccia scoperta dall'espansione (request: artist/title/spotify_id/isrc/
duration_seconds/url/album_art_url). Importa il brano (idempotente), lo attacca alla
playlist (modello 1:1: non sposta una traccia gia' appartenente ad altra playlist) e,
se la playlist e' una Spotify posseduta e il brano e' risolto, lo aggiunge anche su
Spotify (write-back best-effort). Response: `created`, `track`, `spotify_added`,
`spotify_error`. L'espansione si lancia dal dettaglio playlist
(`/playlists/[id]/expand`); l'endpoint `POST /api/discovery/expand` resta invariato.

## Tracks e libreria

```text
GET   /api/tracks
GET   /api/tracks/{track_id}
GET   /api/tracks/{track_id}/cover
PATCH /api/tracks/{track_id}
POST  /api/tracks/{track_id}/link-file
GET   /api/files/search
POST  /api/library/index
GET   /api/library/index/status
GET   /api/stats
```

Filtri supportati da `GET /api/tracks`: artista, titolo, album, genere, etichetta
(`label`, match esatto) e archiviate (`archived`, default `false`: le archiviate
sono escluse; `true` mostra solo le archiviate), sorgente (incl. `local_files`),
stato (`imported` | `ready_for_set`), BPM min/max, key, durata, presenza
Spotify/SoundCloud, possesso (`has_local_file`), metadata incompleti, sort/order,
limit/offset — per le tracce di una playlist usare
`GET /api/playlists/{playlist_id}/tracks`.

`GET /api/tracks/{track_id}/cover` serve l'artwork **incorporato nel file** di una
traccia posseduta, letto on-demand dal disco (non salvato in DB). Risponde con i byte
dell'immagine (`Cache-Control: max-age=3600`); `404` se la traccia non esiste, non e'
posseduta (`has_local_file`), il file manca o non contiene cover. Il frontend usa
`album_art_url` (Spotify) quando presente e ripiega su questo endpoint altrimenti.

`POST /api/library/index` (202) indicizza la libreria canonica `LIBRARY_ROOT`
(disk-first: il disco È la libreria) — scan + riaggancio per audio-hash +
riconciliazione dei possessi; `409` se `LIBRARY_ROOT` non è configurata. Stato del
job su `GET /api/library/index/status`.

`PATCH /api/tracks/{track_id}` accetta aggiornamenti parziali su BPM, Camelot,
genere, label, anno e campi affini. I valori manuali hanno precedenza sui dati
importati. `422` su tonalita' non in notazione Camelot valida. `energy` **non e'
accettato**: e' sempre derivata da BPM+genere e viene ricalcolata automaticamente
quando il patch tocca `bpm` o `genere`; un payload che include `energy` viene
rifiutato con `422` (schema `extra="forbid"`).

`POST /api/tracks/{track_id}/link-file` collega manualmente un file su disco alla
traccia (possesso senza download): valida esistenza ed estensione audio, imposta
`has_local_file`/`local_path`/`local_format`/`local_bitrate` + audio-hash
best-effort e azzera l'esito download (`last_download_outcome`/`reason`).
Request: `{path}`. `400` su percorso non valido, `404` se la traccia non esiste.

`GET /api/files/search?q=...` cerca file audio per nome (match AND dei termini,
case-insensitive) in `LIBRARY_ROOT` e `SLSKD_DOWNLOAD_DIR`; max 50 risultati,
query sotto i 2 caratteri restituisce lista vuota. Risposta: lista di
`{path, name, format, size, source}` con `source` = `library` | `downloads`.

`GET /api/stats` restituisce gli aggregati deterministici della libreria
(`LibraryStatsOut`): conteggi, copertura BPM/key, `key_distribution` e
`genre_distribution` (mappa genere->conteggio; i generi sono fusi
case-insensitive tenendo la grafia piu' frequente), istogramma BPM ed energia.

## Labels

```text
GET  /api/labels
```

`GET /api/labels` restituisce la panoramica deterministica delle etichette presenti in
libreria (aggregati con nomi normalizzati e merge delle varianti). Ogni voce espone
`label`, `track_count`, `artist_count`, `artists` (lista completa, per il filtro per
artista), `genres` (cap) e il range anni. La `label` arriva dal tag del file (letta in
indicizzazione, scritta da DjOrganizer): il vecchio backfill da Spotify e' stato
rimosso.

## Set Builder e set salvati

```text
POST   /api/sets/generate
POST   /api/sets/generate-async
GET    /api/sets/generate-status
GET    /api/sets
GET    /api/sets/{setlist_id}
PATCH  /api/sets/{setlist_id}
DELETE /api/sets/{setlist_id}
POST   /api/sets/{setlist_id}/export
DELETE /api/sets/{setlist_id}/tracks/{position}
POST   /api/sets/{setlist_id}/tracks/{position}/move
POST   /api/sets/{setlist_id}/tracks/{position}/replace
POST   /api/sets/{setlist_id}/alternatives
```

Generazione:

- `generate` restituisce subito il set.
- `generate-async` avvia un job e la UI legge `generate-status`.
- `mode=technical|creative` seleziona il comportamento AI quando disponibile.
- Disk-first: `owned_only` (default `true`) genera il set dai soli brani posseduti.
  Il flag resta sul set salvato (esposto in `SetlistOut.owned_only`) e l'editing lo
  rispetta: `alternatives` esclude i lead dal pool e `replace` con una traccia senza
  file locale risponde 422.

Export: CSV, Markdown/testo o creazione playlist Spotify tramite endpoint Spotify.

## Transitions

```text
GET  /api/transitions/after/{track_id}
GET  /api/transitions/before/{track_id}
POST /api/transitions/score
```

Le transizioni espongono score tecnico e classificazione deterministica:

```text
technically_safe | creative_risk | good_reset
```

## Spotify

```text
GET  /api/spotify/status
GET  /api/spotify/login
GET  /api/spotify/callback
POST /api/spotify/create-playlist
```

Spotify gestisce OAuth, import e export playlist. Non e' una fonte di BPM/key.

## Discovery

```text
GET  /api/discovery/status
POST /api/discovery/expand
GET  /api/discovery/genres
POST /api/discovery/dig
POST /api/discovery/add
```

`expand` espande una playlist importata, suggerendo brani di **gusto affine** da
aggiungere (non una compatibilita' tecnica: BPM/key/transizioni restano del Set Builder):

```text
playlist -> seed artisti/tracce -> Last.fm similarity -> resolver Spotify -> ranking per gusto
```

I candidati di `expand` sono annotati con la loro **etichetta**: chi e' su
un'etichetta che gia' collezioni riceve un piccolo boost ed e' marcato `label_owned`.

`dig` ("Scava") fa crate digging via **Discogs** per genere o etichetta: trova
release/tracce non ancora possedute, con ranking per profondita'/novita' (domanda
want/have) e preset Familiare/Bilanciato/Avventuroso. `genres` elenca generi e stili
disponibili come seme del dig.

Il ranking del dig combina la scoperta (novita'+domanda) con il **gusto**: familiarita'
graduata sull'artista, etichetta posseduta e affinita' di stile coi tuoi generi.
L'affinita' e' misurata rispetto a un riferimento selezionabile via il campo opzionale
`taste_playlist_id` (default: tutta la libreria); la **dedup resta sempre library-wide**.
Ogni lead porta `reasons[]` deterministici (`{code, data}`) per spiegare il perche'
(es. `rare_wanted`, `deep_cut`, `label_followed`, `artist_collected`, `style_match`,
`recent`); il testo dei chip lo compone la UI.

`add` importa un candidato nella libreria dell'app in modo idempotente. Non scrive su
Spotify. L'AI, se configurata e richiesta, aggiunge spiegazioni ma non sceglie i
candidati.

La vecchia modalita' Discovery basata sui gap della playlist e' stata rimossa:
Discovery espande playlist, mentre Gap Analysis resta un endpoint separato di lettura.

Nota: questi tre provider (Last.fm, Discogs, Spotify-come-resolver) sono gli unici
rimasti in Cratory e servono solo la Discovery — non forniscono BPM/key/genere/mood
alla libreria.

## Shazam / mix identification

```text
GET    /api/shazam/status
POST   /api/shazam/identify
GET    /api/shazam/identify-status
GET    /api/shazam/sets
GET    /api/shazam/sets/{dj_set_id}
POST   /api/shazam/sets/{dj_set_id}/import-playlist
DELETE /api/shazam/sets/{dj_set_id}
```

Richiede `ffmpeg`, `yt-dlp` e `shazamio`. Il job scarica temporaneamente l'audio,
campiona segmenti, riconosce le tracce e persiste `DjSet`/`DjSetTrack`. Le tracce non
entrano nella libreria principale. Questo e' l'unico fingerprinting audio del
progetto: identifica i brani di un mix esterno, non le tracce della libreria.

`POST /api/shazam/sets/{id}/import-playlist` promuove le tracce identificate a lead in
una playlist con `source=shazam` (dedup su artista+titolo, ISRC conservato per il
riaggancio disk-first). Ritorna un `PlaylistImportReport`. Ripetibile bloccato finché
la playlist esiste: il set memorizza `imported_playlist_id` (esposto in `DjSetOut`) e
risponde `409` alla seconda import; l'eliminazione di quella playlist azzera il
riferimento e riabilita l'import.

## Downloads (Soulseek / slskd)

```text
GET    /api/downloads/status
GET    /api/downloads/pending
POST   /api/downloads/retry-pending
DELETE /api/downloads/pending/{track_id}
POST   /api/downloads/candidates
POST /api/downloads/playlist/{playlist_id}
POST /api/downloads/track
POST   /api/downloads/search
POST   /api/downloads/manual
```

Acquisizione file via il daemon Soulseek headless slskd, deterministica (zero AI):
collega un file alla `Track` esistente (`has_local_file`/`local_path`/`local_format`/
`local_bitrate`). Richiede `SLSKD_URL` e `SLSKD_DOWNLOAD_DIR` configurati; senza,
tutti gli endpoint di ricerca/download (`candidates`, `search`, `playlist/{id}`,
`track`, `manual`, `retry-pending`) rispondono `409`. Restano disponibili
`GET status` (con `available=false`), `GET pending` e `DELETE pending/{track_id}`.

`GET /api/downloads/pending` elenca le "da sistemare" (esito `needs_review` /
`not_found` / `failed` persistito sulla Track, tracce non possedute e non scartate);
`POST /api/downloads/retry-pending` (`202`) ritenta l'auto-pick su tutte;
`DELETE /api/downloads/pending/{track_id}` ("Ignora") azzera l'esito e toglie la
traccia dall'archivio (`404` se la traccia non esiste).

`GET /api/downloads/status` restituisce `available` (slskd configurato) piu' lo stato
del job in background: `status` (`idle|running|done|error`), `processed`, `total`,
`downloaded`, `needs_review`, `not_found`, `failed`, `playlist_id`, `items[]`,
`error`, `started_at`, `finished_at`.

`POST /api/downloads/candidates` cerca su slskd e restituisce i candidati ordinati
deterministicamente (qualita' + aderenza nome + disponibilita'). Request: `artist`,
`title`, `duration_seconds` (opzionale: durata attesa dalla Track, premia la
versione giusta nel ranking). Response: lista di candidati con `username`,
`filename`, `size`, `bitrate`, `length`, `format`, `name_score`, `quality_tier`,
`confidence`.

`POST /api/downloads/search` fa una ricerca libera su Soulseek. Request: `{query}`.
Query vuota -> lista vuota. Response: stessa lista di candidati di `candidates` ma
senza soglia di aderenza al nome (l'utente sceglie a vista). `409` se slskd non e'
configurato, `502` su errore slskd.

`POST /api/downloads/manual` (`202`) scarica un candidato scelto dalla ricerca
libera senza collegarlo a una `Track` (il file finisce nella cartella download
slskd). Request: `{candidate}` (stessa forma di `CandidateOut`). `409` se slskd non
e' configurato o un job e' gia' in corso.

`POST /api/downloads/playlist/{playlist_id}` (`202`) avvia il job per tutte le tracce
della playlist senza file locale: per ciascuna cerca, sceglie in automatico il miglior
candidato (auto-pick sopra soglia di confidenza) ed esegue il download. `409` se slskd
non e' configurato o un job e' gia' in corso.

`POST /api/downloads/track` (`202`) avvia il job per una singola traccia con un
candidato scelto esplicitamente (mini-selettore, es. da Discovery). Request: `track_id`,
`candidate` (stessa forma di `CandidateOut`). `404` se la traccia non esiste, `409` se
slskd non e' configurato o un job e' gia' in corso.

Il job e' mono-istanza (un download alla volta, come l'indicizzazione libreria): un
errore su una traccia non ferma le altre. La UI fa polling di `GET /api/downloads/status`
durante l'esecuzione.

## AI e servizi

```text
GET /api/ai/status
GET /api/services/status
```

`/api/services/status` restituisce lo stato aggregato delle integrazioni: Spotify,
AI, Last.fm, Discogs (`connected` = `DISCOGS_TOKEN` presente; funziona anche senza
token, il token alza il rate limit), slskd e servizi affini.

## Convenzioni

- Errori tramite `HTTPException` con `detail` leggibile.
- Operazioni lunghe tramite job e polling.
- Rate limit, retry, cache e fallback stanno nel layer `integrations/` o `services/`,
  non nei router.
- I router non devono contenere logica di scoring, deduplica o ranking.
