# API

Contratti REST correnti del backend FastAPI. Tutte le response principali sono
validate con Pydantic in `backend/app/schemas.py`.

Base locale:

```text
http://localhost:8000
```

## Health

```text
GET /api/health
```

## Playlists

```text
GET    /api/playlists/spotify/available
POST   /api/playlists/import
POST   /api/playlists/{playlist_id}/sync
POST   /api/playlists/import-manual
GET    /api/playlists
GET    /api/playlists/{playlist_id}
DELETE /api/playlists/{playlist_id}
POST   /api/playlists/{playlist_id}/enrich
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
`POST /api/playlists/import-manual` crea una playlist da testo incollato. Tutti
avviano l'enrichment automatico best-effort sulle tracce importate.
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
GET   /api/tracks/lookup
GET   /api/tracks/{track_id}
PATCH /api/tracks/{track_id}
POST  /api/tracks/{track_id}/enrich
POST  /api/library/index
GET   /api/library/index/status
GET   /api/stats
```

Filtri supportati da `GET /api/tracks`: artista, titolo, album, genere, sorgente
(incl. `local_files`), playlist, stato, BPM min/max, key, durata, presenza
Spotify/SoundCloud, possesso (`has_local_file`), metadata incompleti, sort/order,
limit/offset.

`GET /api/tracks/lookup` — lookup read-only per il bridge DjOrganizer (sola lettura,
mai 404). Query: `isrc` oppure `artist`+`title` (altrimenti 422). Risposta:
`{found, match: "isrc"|"fuzzy"|null, track_id, artist, title, genre, genre_secondary,
label, year, confidence}` — confidence: 100 ISRC, 70 fuzzy, 0 non trovata.

`POST /api/library/index` (202) indicizza la libreria canonica `LIBRARY_ROOT`
(disk-first: il disco È la libreria) — scan + riaggancio per audio-hash +
riconciliazione dei possessi; `409` se `LIBRARY_ROOT` non è configurata. Stato del
job su `GET /api/library/index/status`.

`PATCH /api/tracks/{track_id}` accetta aggiornamenti parziali su BPM, Camelot, mood,
energia, danceability, vocalness, genere, label, anno e campi affini. I valori manuali
hanno precedenza sull'enrichment.

`POST /api/tracks/{track_id}/enrich` arricchisce le feature di una singola traccia in
modo sincrono e completa i campi mancanti senza sovrascrivere BPM/key esistenti.
Risponde `409` se nessun provider di feature e' configurato.

## Enrichment

```text
GET  /api/enrichment/status
POST /api/enrichment/features
GET  /api/enrichment/features/status
```

`POST /api/enrichment/features` avvia un job asincrono. `force=true` forza un nuovo
tentativo ignorando la cache in lettura.

## Labels

```text
GET  /api/labels
POST /api/labels/backfill
```

`GET /api/labels` restituisce la panoramica deterministica delle etichette presenti in
libreria (aggregati con nomi normalizzati e merge delle varianti).

`POST /api/labels/backfill` recupera l'etichetta dall'album Spotify completo per le
tracce che ne sono prive (la label non e' nell'album semplificato annidato nelle
tracce di playlist/liked). E' bounded e ripetibile: elabora un lotto per chiamata; se
`remaining > 0`, va rilanciato per continuare.

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

## Shazam / mix identification

```text
GET    /api/shazam/status
POST   /api/shazam/identify
GET    /api/shazam/identify-status
GET    /api/shazam/sets
GET    /api/shazam/sets/{dj_set_id}
DELETE /api/shazam/sets/{dj_set_id}
```

Richiede `ffmpeg`, `yt-dlp` e `shazamio`. Il job scarica temporaneamente l'audio,
campiona segmenti, riconosce le tracce e persiste `DjSet`/`DjSetTrack`. Le tracce non
entrano nella libreria principale.

## Downloads (Soulseek / slskd)

```text
GET  /api/downloads/status
POST /api/downloads/candidates
POST /api/downloads/playlist/{playlist_id}
POST /api/downloads/track
```

Acquisizione file via il daemon Soulseek headless slskd, deterministica (zero AI):
collega un file alla `Track` esistente (`has_local_file`/`local_path`/`local_format`/
`local_bitrate`). Richiede `SLSKD_URL` e `SLSKD_DOWNLOAD_DIR` configurati; senza,
`candidates`, `playlist/{id}` e `track` rispondono `409`.

`GET /api/downloads/status` restituisce `available` (slskd configurato) piu' lo stato
del job in background: `status` (`idle|running|done|error`), `processed`, `total`,
`downloaded`, `needs_review`, `not_found`, `failed`, `playlist_id`, `items[]`,
`error`, `started_at`, `finished_at`.

`POST /api/downloads/candidates` cerca su slskd e restituisce i candidati ordinati
deterministicamente (qualita' + aderenza nome + disponibilita'). Request: `artist`,
`title`. Response: lista di candidati con `username`, `filename`, `size`, `bitrate`,
`length`, `format`, `name_score`, `quality_tier`, `confidence`.

`POST /api/downloads/playlist/{playlist_id}` (`202`) avvia il job per tutte le tracce
della playlist senza file locale: per ciascuna cerca, sceglie in automatico il miglior
candidato (auto-pick sopra soglia di confidenza) ed esegue il download. `409` se slskd
non e' configurato o un job e' gia' in corso.

`POST /api/downloads/track` (`202`) avvia il job per una singola traccia con un
candidato scelto esplicitamente (mini-selettore, es. da Discovery). Request: `track_id`,
`candidate` (stessa forma di `CandidateOut`). `404` se la traccia non esiste, `409` se
slskd non e' configurato o un job e' gia' in corso.

Il job e' mono-istanza (un download alla volta, come l'import locale): un errore su una
traccia non ferma le altre. La UI fa polling di `GET /api/downloads/status` durante
l'esecuzione.

## AI e servizi

```text
GET /api/ai/status
GET /api/services/status
```

`/api/services/status` restituisce lo stato aggregato delle integrazioni: Spotify,
AI, Deezer, GetSongBPM, AcousticBrainz, Last.fm, MusicBrainz e servizi affini.

## Convenzioni

- Errori tramite `HTTPException` con `detail` leggibile.
- Operazioni lunghe tramite job e polling.
- Rate limit, retry, cache e fallback stanno nel layer `integrations/` o `services/`,
  non nei router.
- I router non devono contenere logica di scoring, deduplica o ranking.
