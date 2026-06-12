# 04 — API Spec (backend FastAPI)

Endpoint suggeriti, raggruppati per dominio. Le fasi indicano quando servono (vedi [06-roadmap.md](06-roadmap.md)).

## Import — MVP 1

```text
POST /api/import/rekordbox-xml        # upload file XML, avvia parsing
GET  /api/import/reports/{id}         # report di import (statistiche + errori)
```

## Tracks — MVP 1

```text
GET  /api/tracks                      # lista con filtri (vedi Library Explorer in 05-functional-spec)
GET  /api/tracks/{id}                 # dettaglio traccia
GET  /api/tracks/{id}/transitions     # tracce compatibili prima/dopo
GET  /api/tracks/{id}/expansion       # suggerimenti espansione da traccia (MVP 4)
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
GET  /api/sets                        # lista set salvati
GET  /api/sets/{id}                   # dettaglio set
POST /api/sets/{id}/validate          # validation engine (MVP 3)
POST /api/sets/{id}/alternatives      # alternative per traccia (MVP 3)
POST /api/sets/{id}/export            # export CSV / testo / playlist Spotify
```

## Spotify — MVP 2

```text
GET  /api/spotify/login               # avvio OAuth
GET  /api/spotify/callback            # callback OAuth
POST /api/spotify/enrich              # enrichment metadata (batch, con cache)
POST /api/spotify/create-playlist     # crea playlist da un set generato
```

## Library Expansion — MVP 4

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
