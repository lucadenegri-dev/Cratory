# 04 — API Spec (backend FastAPI)

Endpoint suggeriti, raggruppati per dominio. Le fasi indicano quando servono (vedi [06-roadmap.md](06-roadmap.md)).

## Playlists — flusso principale (nuovo paradigma)

```text
GET  /api/playlists/spotify/available # playlist Spotify dell'utente (per la selezione)
POST /api/playlists/import            # importa una playlist o i liked ({platform, playlist_id|"liked"})
POST /api/playlists/import-manual     # importa una tracklist incollata ({name, text}) → 422 se nulla riconosciuto
GET  /api/playlists                   # playlist importate
GET  /api/playlists/{id}              # dettaglio di una playlist importata
DELETE /api/playlists/{id}           # rimuove la playlist e le sue tracce (204)
GET  /api/playlists/{id}/tracks       # tracce di una playlist importata
GET  /api/playlists/{id}/gaps         # analisi deterministica dei buchi (sez. 6)
GET  /api/playlists/library/gaps      # analisi buchi sull'intera libreria
```

## Tracks & Libreria

```text
GET  /api/tracks                      # lista con filtri: artist,title,album,genre,source,
                                      #   bpm_min,bpm_max,key,duration_min/max,has_spotify,
                                      #   has_soundcloud,incomplete_metadata,limit,offset
GET  /api/tracks/{id}                 # dettaglio traccia
GET  /api/stats                       # statistiche libreria: playlists, tracce, with_bpm,
                                      #   with_key, with_features, ready_for_set, range BPM, key_distribution
```

## Transition Finder — MVP 1

```text
GET  /api/transitions/before/{track_id}
GET  /api/transitions/after/{track_id}
POST /api/transitions/score           # score tecnico tra due tracce
```

## Set Builder — MVP 1 (algoritmico) / MVP 3 (AI)

```text
POST /api/sets/generate               # genera set (vincoli strutturati + prompt libero)
POST /api/sets/generate-async         # avvia generazione in background
GET  /api/sets/generate-status        # stato job generazione async
GET  /api/sets                        # lista set salvati
GET  /api/sets/{id}                   # dettaglio set
PATCH /api/sets/{id}                  # rinomina set
DELETE /api/sets/{id}                 # elimina set
DELETE /api/sets/{id}/tracks/{pos}    # rimuove traccia dalla scaletta
POST /api/sets/{id}/tracks/{pos}/move # sposta traccia su/giù
POST /api/sets/{id}/tracks/{pos}/replace # sostituisce traccia e ricalcola transizioni
POST /api/sets/{id}/alternatives      # alternative deterministiche per traccia (MVP 3/F9)
POST /api/sets/{id}/export            # export CSV / testo
```

## Spotify — OAuth, enrichment metadata, export

```text
GET  /api/spotify/status              # configurato? account collegato? redirect uri
GET  /api/spotify/login               # avvio OAuth (scope: playlist read/modify, user-library-read)
GET  /api/spotify/callback            # callback OAuth
POST /api/spotify/create-playlist     # crea una playlist Spotify da un set generato
```

> L'enrichment metadata Spotify è stato **rimosso**: titolo/artista/album/cover/ISRC/durata arrivano già con l'import della playlist (incluso `year`). Genere/mood/BPM/key si ottengono dal Music Feature Enrichment qui sotto.

## Music Feature Enrichment (BPM/key/genere/mood/energia) — implementato

`services/feature_enrichment.py` applica i dati con `enrichment_source`/`enrichment_confidence` senza mai sovrascrivere BPM/key esistenti, con cache DB (`EnrichmentCache`). Provider concreti in catena: GetSongBPM (BPM/key/Camelot/danceability), MusicBrainz (label/release/ISRC/genere), Last.fm (genere + **mood** dai tag). L'**energia** è stimata deterministicamente (`estimate_energy`) da BPM + danceability + genere quando nessun provider la fornisce.

```text
GET  /api/enrichment/status           # provider configurato? (GETSONGBPM_API_KEY / MUSICBRAINZ_USER_AGENT)
POST /api/enrichment/features         # arricchisce le tracce prive di BPM/key (async, ?force=true ri-elabora tutto)
GET  /api/enrichment/features/status  # stato job async
```

## Discovery — Fase F (Last.fm + resolver Spotify)

Similarità da Last.fm, resolve su Spotify `/search`, ranking per compatibilità, spiegazioni AI opzionali. Non usa Spotify `/recommendations` (deprecato).

```text
GET  /api/discovery/status            # Last.fm configurato? resolver Spotify? spiegazioni AI?
POST /api/discovery/expand            # espandi una playlist ({playlist_id, limit?, use_ai?})
POST /api/discovery/gap               # colma un gap ({gap_type, description, suggestion, playlist_id?, limit?, use_ai?})
POST /api/discovery/add               # importa un candidato nella libreria dell'app ({artist, title, spotify_id?, isrc?, ...})
```

## AI

```text
GET  /api/ai/status                   # LLM configurato? modello attivo
```

## Servizi — stato unificato (pagina Impostazioni)

```text
GET  /api/services/status             # stato di TUTTE le integrazioni in un'unica risposta:
                                      #   spotify, anthropic, getsongbpm, lastfm, musicbrainz
                                      #   per ciascuno: configured, connected (null se non ha login), detail, env[]
```

> Affianca gli `*/status` per-dominio (`/api/spotify/status`, `/api/ai/status`, `/api/enrichment/status`, `/api/discovery/status`), che restano per le pagine specifiche. `musicbrainz` risulta `configured` solo se `MUSICBRAINZ_USER_AGENT` è impostato (nessuna API key, ma serve uno User-Agent identificativo).

## Library Expansion — non implementato (futuro)

Modulo di crate digging avanzato descritto in 05-functional-spec (F11–F15). Endpoint previsti, non ancora presenti:

```text
GET  /api/expansion/track/{track_id}
GET  /api/expansion/artist/{artist_id}
POST /api/expansion/genre
POST /api/expansion/set/{set_id}
POST /api/expansion/gaps
```

## Convenzioni

- Tutti gli endpoint restituiscono JSON validato con Pydantic.
- Errori con shape coerente (`detail`, codice, eventuale contesto).
- Operazioni lunghe (import, enrichment, generazione AI) devono gestire bene lo stato: o sincrone con timeout ragionevole, o job con polling sul report/risultato.
- Rate limit e caching gestiti nel layer integrations, non nei router.
