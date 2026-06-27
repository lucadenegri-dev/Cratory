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

## Tracks e libreria

```text
GET   /api/tracks
GET   /api/tracks/{track_id}
PATCH /api/tracks/{track_id}
POST  /api/tracks/{track_id}/enrich
GET   /api/stats
```

Filtri supportati da `GET /api/tracks`: artista, titolo, album, genere, sorgente,
playlist, stato, BPM min/max, key, durata, presenza Spotify/SoundCloud,
metadata incompleti, sort/order, limit/offset.

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
