# Prompt per generazione webapp: AI DJ Set Builder & Library Expansion Assistant

## Contesto del progetto

Voglio sviluppare una webapp personale per aiutarmi a preparare DJ set in modo più intelligente e migliorare rapidamente come DJ amatoriale.

La webapp dovrà importare dati da un file XML esportato da Rekordbox, arricchire le informazioni delle tracce tramite Spotify e, se utile, tramite fonti esterne come Discogs e MusicBrainz. Dovrà poi usare un agente AI per aiutarmi a costruire set coerenti, spiegare le scelte musicali e suggerire come ampliare la mia libreria musicale in modo contestualizzato.

Il progetto non deve essere un software per suonare musica. Deve essere un assistente di preparazione, analisi e crate digging.

## Dati disponibili

Ho a disposizione un export XML di Rekordbox.

Nel file XML sono presenti tracce di diverse sorgenti:

- Spotify
- SoundCloud
- file locali

Le tracce Spotify sono spesso identificate nel campo `Location` con una stringa simile a:

```text
file://localhostspotify:track:SPOTIFY_TRACK_ID
```

Nel file sono disponibili dati utili come:

- `TrackID`
- `Name`
- `Artist`
- `Album`
- `Genre`
- `Year`
- `AverageBpm`
- `Tonality`
- `TotalTime`
- `PlayCount`
- `Location`
- `TEMPO`
- `POSITION_MARK`

Il sistema deve usare Rekordbox come fonte primaria per i dati DJ, quindi BPM, tonalità, durata, beatgrid, cue point e play count.

Spotify deve essere usato principalmente per arricchire i metadata, recuperare titolo, artista, album, cover, link Spotify e informazioni sull’artista.

## Obiettivo principale

Creare una webapp personale per DJ che:

1. importa la libreria da Rekordbox XML
2. riconosce tracce Spotify, SoundCloud e file locali
3. arricchisce i metadata tramite Spotify
4. permette di filtrare e interrogare la libreria
5. genera set DJ coerenti sulla base di artista, genere, BPM, tonalità, durata e intenzione musicale
6. usa un agente AI per interpretare richieste in linguaggio naturale
7. spiega perché una scaletta funziona
8. suggerisce alternative per ogni traccia del set
9. suggerisce come ampliare la libreria in base ad artista, etichetta, genere e lacune della collection
10. esporta il set generato in formati utili, come playlist Spotify, CSV o testo

## Cosa NON deve fare

La prima versione non deve:

- suonare file audio
- sostituire Rekordbox
- scaricare audio da Spotify
- fare scraping non autorizzato
- fare tracking dettagliato dei miei progressi
- richiedere tagging manuale dei brani
- basarsi su mood inseriti manualmente
- implementare machine learning complesso
- essere multiutente
- avere app mobile nativa

Il focus è: creazione set, spiegazione, suggerimenti intelligenti, crate digging contestualizzato.

## Stack tecnico desiderato

Sviluppare una webapp modulare e locale/self-hosted.

Stack consigliato:

```text
Backend: Python + FastAPI
Frontend: React o Next.js
Database MVP: SQLite
Database futuro: PostgreSQL
ORM: SQLAlchemy
Validation: Pydantic
XML parser: lxml
Spotify integration: Spotify Web API con OAuth
AI integration: LLM API astratta tramite service layer
External metadata: Discogs API, MusicBrainz API
```

Il codice deve essere pulito, modulare, documentato e facile da estendere.

## Architettura generale

La webapp deve avere questi moduli principali:

```text
Rekordbox XML Importer
↓
Database interno
↓
Spotify Metadata Enricher
↓
Music Metadata Layer, Discogs/MusicBrainz opzionali
↓
Candidate Engine deterministico
↓
AI Set Agent
↓
Validation Engine
↓
Set Builder UI / Library Expansion UI
```

## Principio architetturale fondamentale

Il sistema deve separare nettamente:

### Motore deterministico

Responsabile di:

- parsing XML
- calcolo durata set
- compatibilità BPM
- compatibilità Camelot
- deduplicazione tracce
- validazione risultati AI
- filtri tecnici
- scoring base delle transizioni

### Agente AI

Responsabile di:

- interpretare richieste in linguaggio naturale
- ragionare su artista, genere, estetica e direzione musicale
- creare una narrativa del set
- spiegare le scelte
- proporre alternative creative
- suggerire percorsi di espansione della libreria
- trasformare lacune tecniche in indicazioni di crate digging

L’AI non deve inventare dati fattuali. Quando suggerisce artisti, etichette o release deve distinguere tra:

- dati recuperati da fonti esterne
- inferenze musicali
- ipotesi creative

## Funzionalità 1: Import Rekordbox XML

La webapp deve permettere all’utente di caricare un file XML Rekordbox.

Il parser deve:

1. leggere il nodo `COLLECTION`
2. estrarre tutte le tracce
3. riconoscere la sorgente dal campo `Location`
4. estrarre Spotify ID quando presente
5. estrarre SoundCloud ID quando presente
6. distinguere file locali
7. salvare BPM, tonalità, durata e play count
8. salvare i punti `TEMPO` come beatgrid points
9. salvare i punti `POSITION_MARK` come cue points
10. generare un report di import

Il report deve mostrare:

- totale tracce importate
- numero tracce Spotify
- numero tracce SoundCloud
- numero file locali
- tracce con BPM
- tracce con tonalità
- tracce con cue point
- tracce con titolo/artista mancanti
- range BPM
- distribuzione tonalità
- eventuali errori di parsing

## Funzionalità 2: Spotify Metadata Enrichment

Per ogni traccia con Spotify ID, il sistema deve recuperare tramite Spotify API:

- title
- artist
- album
- cover image
- release year, se disponibile
- Spotify URL
- artist ID
- artist genres, se disponibili
- artist popularity, se disponibile

Regole:

- Non sovrascrivere BPM e tonalità provenienti da Rekordbox.
- Se `Name` o `Artist` sono vuoti nel file Rekordbox, completarli con Spotify.
- Conservare il collegamento tra traccia Rekordbox e Spotify ID.
- Gestire rate limit ed errori API.
- Salvare in cache i risultati per evitare chiamate ripetute.

## Funzionalità 3: Library Explorer

Creare una vista per esplorare la libreria.

Filtri richiesti:

- artista
- titolo
- album
- genere
- sorgente
- BPM minimo/massimo
- tonalità
- durata
- play count
- presenza Spotify ID
- presenza SoundCloud ID
- presenza cue point
- metadata incompleti

La vista deve mostrare almeno:

```text
Title
Artist
Source
BPM
Key
Duration
Genre
Year
Play Count
Spotify Link
Cue Count
```

## Funzionalità 4: Set Generator

La webapp deve permettere all’utente di generare un set tramite input strutturato e tramite prompt libero.

### Input strutturati

Campi possibili:

```text
Durata target
BPM iniziale
BPM finale
Artisti seed
Genere o stile
Tonalità preferite
Tipo di progressione
Numero massimo tracce dello stesso artista
Includi solo Spotify / SoundCloud / locali / tutti
Preferisci mix armonico
Preferisci BPM progressivo
Permetti cambi bruschi
Evita tracce troppo corte
Evita tracce troppo suonate
```

Tipi di progressione:

```text
smooth
progressive
contrast
experimental
peak_time
warm_up
closing
```

### Prompt libero

Esempi di prompt che la webapp deve supportare:

```text
Fammi un set da 45 minuti partendo da Arca e Sega Bodega, poi più club, senza diventare techno dritta troppo presto.

Costruisci un set experimental club da 40 minuti con progressione crescente e qualche cambio brusco.

Voglio un set house/speed garage tra 128 e 134 BPM, fluido ma non noioso.

Fammi una scaletta intorno a questo brano e dammi alternative più morbide e più aggressive.
```

## Funzionalità 5: Candidate Engine

Prima di chiamare l’AI, il sistema deve selezionare un sottoinsieme di tracce candidate.

Il Candidate Engine deve usare:

- artisti seed
- genere
- BPM range
- key range
- durata
- source
- play count
- playlist/contesto, se disponibile
- similarità testuale su titolo/artista/album/genere
- compatibilità tecnica con brani già selezionati

L’AI non deve ricevere tutta la libreria se non necessario. Deve ricevere un set di candidate ragionevole e già filtrato.

## Funzionalità 6: Scoring tecnico transizioni

Implementare una funzione di scoring tecnico tra due tracce.

Lo score deve considerare:

### BPM

```text
differenza 0-2 BPM: ottimo
differenza 2-5 BPM: buono
differenza 5-8 BPM: rischioso
oltre 8 BPM: difficile
```

### Camelot key

Compatibilità base:

```text
stessa key: molto compatibile
stesso numero, lettera diversa: compatibile
numero +1 o -1 stessa lettera: compatibile
altro: meno compatibile
```

### Durata e cue

- tracce molto corte: penalità
- presenza cue point: bonus
- beatgrid disponibile: bonus

### Play count

- tracce mai usate: possibile bonus per varietà
- tracce usate troppo spesso: leggera penalità, se richiesto

La funzione deve restituire:

```json
{
  "score": 0-100,
  "technical_reasons": [],
  "warnings": []
}
```

## Funzionalità 7: AI Set Agent

L’agente AI deve ricevere:

```json
{
  "user_request": "...",
  "structured_constraints": {},
  "candidate_tracks": [],
  "technical_scores": [],
  "library_context": {}
}
```

L’agente deve produrre un output JSON validabile:

```json
{
  "set_title": "...",
  "global_explanation": "...",
  "tracks": [
    {
      "position": 1,
      "track_id": "...",
      "reason": "...",
      "transition_note": "...",
      "risk_level": "low|medium|high"
    }
  ],
  "critical_points": [],
  "alternative_directions": [],
  "missing_library_suggestions": []
}
```

L’agente deve:

- costruire una scaletta coerente
- spiegare la logica narrativa
- spiegare ogni scelta
- indicare punti critici
- distinguere tra transizioni tecnicamente sicure e transizioni creative/rischiose
- proporre eventuali alternative
- rispettare i vincoli tecnici imposti dal sistema

## Funzionalità 8: Validation Engine

Dopo la generazione AI, il sistema deve validare il set.

Controlli richiesti:

- tutte le tracce esistono nel database
- nessun duplicato non voluto
- durata totale vicina al target
- BPM coerenti con la richiesta
- massimo numero tracce per artista rispettato
- source filter rispettato
- salti BPM troppo grandi segnalati
- incompatibilità Camelot importanti segnalate
- tracce troppo corte segnalate

Se il set non rispetta i vincoli, il sistema deve:

1. correggere automaticamente se possibile
2. oppure richiedere all’agente AI una nuova versione
3. oppure mostrare warning chiari all’utente

## Funzionalità 9: Alternative Generator

Per ogni traccia del set, l’utente deve poter chiedere:

```text
Sostituisci con una traccia più morbida
Sostituisci con una traccia più aggressiva
Sostituisci con una traccia più compatibile tecnicamente
Sostituisci con una traccia dello stesso artista
Sostituisci con una traccia di genere simile
Sostituisci con una traccia più sorprendente
```

L’app deve proporre 3-5 alternative con motivazione.

Ogni alternativa deve indicare:

- perché è adatta
- differenza BPM
- compatibilità key
- rischio transizione
- effetto narrativo nel set

## Funzionalità 10: Transition Finder

L’utente deve poter selezionare una traccia e chiedere:

```text
Cosa posso mettere dopo?
Cosa posso mettere prima?
Quali sono le transizioni più sicure?
Quali sono le transizioni più interessanti musicalmente?
Quali sono le transizioni più rischiose ma creative?
```

Il risultato deve distinguere:

```text
Tecnically safe
Musically interesting
Creative risk
Good reset
Good opening continuation
Good peak transition
```

## Funzionalità 11: Library Expansion Advisor

La webapp deve includere un modulo per suggerire come ampliare la libreria musicale.

Questo modulo deve generare suggerimenti contestualizzati sulla base di:

- artista
- label / etichetta
- genere
- release
- remix
- collaborazioni
- periodo
- artisti simili
- artisti presenti sulle stesse label
- buchi tecnici nella libreria
- necessità emerse durante la creazione set

Il modulo non deve produrre raccomandazioni generiche. Ogni suggerimento deve spiegare:

1. perché è rilevante rispetto alla libreria attuale
2. quale relazione ha con artista, label, genere o set
3. come potrebbe essere usato in un DJ set
4. se è utile come opening, bridge, peak, reset o closing
5. quali query pratiche cercare su Spotify, Discogs, Bandcamp o SoundCloud
6. quale priorità ha

## Funzionalità 12: Expansion from Track

L’utente seleziona una traccia.

L’app deve suggerire:

- altre release dello stesso artista
- remix
- collaboratori
- label della release
- altri artisti della stessa label
- generi/stili collegati
- tracce utili come prima/dopo nel set
- query di ricerca pratiche

Output esempio:

```json
{
  "source_track": "...",
  "directions": [
    {
      "title": "Explore the label catalog",
      "reason": "...",
      "set_usage": "bridge",
      "priority": "high",
      "search_queries": [
        "...",
        "..."
      ],
      "sources": [
        "Discogs",
        "Spotify"
      ]
    }
  ]
}
```

## Funzionalità 13: Expansion from Artist

L’utente seleziona un artista.

L’app deve suggerire:

- release essenziali
- label associate
- collaboratori
- remixers
- artisti vicini
- direzioni più club
- direzioni più sperimentali
- direzioni più morbide
- direzioni più aggressive

L’output deve essere raggruppato per direzioni musicali, non solo come lista.

## Funzionalità 14: Expansion from Set

Dopo aver generato un set, l’app deve analizzarlo e dire:

- quali blocchi sono forti
- quali blocchi sono deboli
- dove mancano alternative
- quali BPM/key servirebbero per renderlo più fluido
- quali artisti o label esplorare
- quali generi ponte potrebbero aiutare

Esempio:

```text
Il set ha una buona zona 137-141 BPM, ma manca una transizione naturale tra la parte experimental e la parte house. Cerca bridge tracks tra 130 e 134 BPM in key 6A/7A/8A, preferibilmente da label legate a house ruvida o speed garage.
```

## Funzionalità 15: Expansion from Genre

L’utente inserisce un genere o stile.

L’app deve:

- trovare tracce già presenti in libreria
- identificare artisti ricorrenti
- identificare label ricorrenti
- calcolare range BPM prevalente
- calcolare tonalità ricorrenti
- suggerire artisti/label da esplorare
- suggerire sottogeneri o scene affini
- segnalare cosa manca nella libreria

## Fonti esterne per crate digging

### Spotify

Usare Spotify per:

- metadata traccia
- metadata artista
- generi artista
- album
- cover
- link

### Discogs

Usare Discogs per:

- release
- label
- artisti collegati
- generi
- stili
- anni
- remix
- catalogo etichette

### MusicBrainz

Usare MusicBrainz come fallback aperto per:

- artisti
- release
- label
- relazioni tra entità

## Regole per AI e fonti esterne

L’AI deve:

- evitare di inventare dati fattuali
- citare internamente la fonte del dato quando disponibile
- distinguere tra dato verificato e inferenza
- non presentare ipotesi come certezze
- produrre query di ricerca anche quando non è sicura del suggerimento
- dare priorità a suggerimenti utili per set reali, non solo culturalmente interessanti

## Modello dati suggerito

### Track

```text
id
rekordbox_track_id
spotify_id
soundcloud_id
source_type
title
artist
album
genre
year
duration_seconds
bpm
tonality
play_count
location
date_added
rating
comments
created_at
updated_at
```

### BeatgridPoint

```text
id
track_id
start_seconds
bpm
meter
beat
```

### CuePoint

```text
id
track_id
name
type
start_seconds
num
color
comment
```

### Artist

```text
id
name
spotify_artist_id
discogs_artist_id
musicbrainz_artist_id
genres
popularity
metadata_json
created_at
updated_at
```

### Label

```text
id
name
discogs_label_id
musicbrainz_label_id
country
profile
metadata_json
created_at
updated_at
```

### Release

```text
id
title
artist_id
label_id
year
source
spotify_album_id
discogs_release_id
musicbrainz_release_id
genres
styles
metadata_json
created_at
updated_at
```

### Setlist

```text
id
name
target_duration_minutes
start_bpm
end_bpm
strategy
prompt
global_explanation
created_at
updated_at
```

### SetlistTrack

```text
id
setlist_id
track_id
position
transition_score
transition_reason
ai_reason
risk_level
created_at
updated_at
```

### Transition

```text
id
from_track_id
to_track_id
score
difficulty_estimate
technical_reason
ai_reason
created_at
updated_at
```

### LibraryGap

```text
id
gap_type
description
bpm_min
bpm_max
preferred_keys
related_genres
related_artists
priority
created_at
updated_at
```

### DiscoverySuggestion

```text
id
suggestion_type
source_entity_type
source_entity_id
suggested_name
suggested_entity_type
reason
set_usage
priority
external_url
search_queries_json
status
created_at
updated_at
```

Status possibili:

```text
new
to_listen
listened
added_to_library
ignored
```

## API backend suggerite

### Import

```text
POST /api/import/rekordbox-xml
GET /api/import/reports/{id}
```

### Tracks

```text
GET /api/tracks
GET /api/tracks/{id}
GET /api/tracks/{id}/transitions
GET /api/tracks/{id}/expansion
```

### Spotify

```text
GET /api/spotify/login
GET /api/spotify/callback
POST /api/spotify/enrich
POST /api/spotify/create-playlist
```

### Set Builder

```text
POST /api/sets/generate
GET /api/sets
GET /api/sets/{id}
POST /api/sets/{id}/validate
POST /api/sets/{id}/alternatives
POST /api/sets/{id}/export
```

### Transition Finder

```text
GET /api/transitions/before/{track_id}
GET /api/transitions/after/{track_id}
POST /api/transitions/score
```

### Library Expansion

```text
GET /api/expansion/track/{track_id}
GET /api/expansion/artist/{artist_id}
POST /api/expansion/genre
POST /api/expansion/set/{set_id}
POST /api/expansion/gaps
```

## UI richiesta

La webapp deve avere almeno queste sezioni:

### 1. Dashboard

Mostrare:

- numero tracce
- sorgenti
- range BPM
- distribuzione tonalità
- tracce con metadata mancanti
- ultime importazioni

### 2. Library

Tabella filtrabile delle tracce.

### 3. Track Detail

Vista dettaglio di una traccia con:

- metadata
- BPM/key
- cue point
- sorgente
- link Spotify
- possibili tracce prima/dopo
- pulsante “Expand from this track”

### 4. Set Builder

Interfaccia con:

- prompt libero
- vincoli strutturati
- bottone genera set
- scaletta risultante
- spiegazione globale
- motivazione per traccia
- warning tecnici
- alternative per traccia

### 5. Transition Finder

Interfaccia per trovare tracce prima/dopo una traccia scelta.

### 6. Expand Library

Interfaccia per:

- espandere da traccia
- espandere da artista
- espandere da genere
- espandere da set
- vedere suggerimenti salvati

### 7. Settings

Configurazioni:

- Spotify API credentials
- Discogs API token
- MusicBrainz user agent
- AI API key
- preferenze set builder
- preferenze source

## MVP richiesto

Generare una prima versione funzionante con queste funzionalità minime:

### MVP 1

- upload XML Rekordbox
- parsing collection
- estrazione tracce
- estrazione Spotify ID da Location
- salvataggio SQLite
- dashboard import
- tabella libreria
- filtri BPM, key, artist, source
- scoring tecnico tra tracce
- set generator algoritmico base
- spiegazione tecnica base

### MVP 2

- Spotify OAuth
- enrichment metadata Spotify
- cover e link Spotify
- creazione playlist Spotify da set generato

### MVP 3

- AI Set Agent
- prompt libero per generazione set
- spiegazioni narrative
- alternative per traccia
- validation engine

### MVP 4

- Library Expansion Advisor
- expansion from track
- expansion from artist
- expansion from set
- suggerimenti basati su label/genere/artista
- integrazione Discogs/MusicBrainz

Se possibile, implementare MVP 1 in modo completo e predisporre bene l’architettura per MVP 2, 3 e 4.

## Requisiti di qualità

Il codice deve:

- essere modulare
- usare type hints
- separare servizi, repository, modelli e router
- gestire errori in modo chiaro
- avere logging
- avere README con istruzioni setup
- usare variabili ambiente
- includere seed/demo con il file XML di esempio
- includere test di base per parser XML e scoring transizioni

## Output richiesto all’IA di sviluppo

Genera:

1. struttura completa del progetto
2. backend FastAPI
3. database SQLite con SQLAlchemy
4. parser Rekordbox XML
5. modelli dati principali
6. API principali per import e library
7. scoring tecnico transizioni
8. generatore set algoritmico MVP
9. frontend React/Next.js con pagine principali
10. README con istruzioni di avvio
11. file `.env.example`
12. test base

## Vincoli importanti

- Non implementare download audio da Spotify.
- Non usare dati Spotify per BPM o key.
- Non obbligare l’utente a taggare manualmente.
- Non inventare metadata musicali.
- Tenere separato il motore tecnico dall’agente AI.
- Ogni set generato deve avere spiegazioni.
- Ogni suggerimento di espansione libreria deve essere contestualizzato.
- Ogni output AI deve essere validato prima di essere mostrato come definitivo.

## Criterio di successo

La webapp è riuscita se ogni volta che la apro posso:

1. importare o aggiornare la mia libreria Rekordbox
2. capire rapidamente quali tracce ho a disposizione
3. chiedere un set in linguaggio naturale
4. ricevere una scaletta tecnicamente plausibile e musicalmente spiegata
5. modificare la scaletta con alternative sensate
6. capire cosa cercare per ampliare la libreria in modo mirato
7. esportare il set o salvarlo per usarlo in Rekordbox/Spotify

## Prima implementazione desiderata

Inizia implementando MVP 1.

Concentrati su:

- parser Rekordbox XML robusto
- database solido
- dashboard libreria
- scoring transizioni
- set generator algoritmico base

Predisponi interfacce e service layer per Spotify, Discogs, MusicBrainz e AI Agent, ma non è necessario completarli tutti nella prima iterazione.

