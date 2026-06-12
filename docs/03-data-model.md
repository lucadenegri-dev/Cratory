# 03 — Data Model

## Note sul formato XML reale (da `export_rekordbox.xml`)

Osservazioni verificate sull'export di esempio (Rekordbox 7.2.14, 293 tracce):

- Radice `DJ_PLAYLISTS` → `COLLECTION Entries="293"` → nodi `TRACK`.
- **Tracce Spotify**: `Location="file://localhostspotify:track:SPOTIFY_ID"`, `Kind="Formato sconosciuto"`, `Size="0"`, `BitRate="0"`. **`Name` e `Artist` sono spesso vuoti** → senza enrichment Spotify la libreria è quasi illeggibile. `AverageBpm` e `Tonality` sono però presenti (analizzati da Rekordbox).
- **Tracce SoundCloud**: `Location="file://localhostsoundcloud:tracks:NUMERIC_ID"` (notare `tracks` plurale).
- **File locali**: `Location="file://localhost/Users/..."` (path URL-encoded, es. `%20`).
- `Tonality` è già in **notazione Camelot** (es. `7A`, `9A`).
- Figli di `TRACK`: `TEMPO` (beatgrid: `Inizio`, `Bpm`, `Metro`, `Battito`) e `POSITION_MARK` (cue point). Una traccia può avere molti punti TEMPO (BPM variabile/grid corretto a mano).
- La sezione `PLAYLISTS` esiste ma può essere quasi vuota; non farne una dipendenza.
- Campi anomali da gestire: `AverageBpm="0.00"`, `Year="0"`, `TotalTime` molto basso (sample/oneshot del sampler Rekordbox), `Name`/`Artist` vuoti.

### Campi TRACK utilizzati

`TrackID`, `Name`, `Artist`, `Album`, `Genre`, `Year`, `AverageBpm`, `Tonality`, `TotalTime`, `PlayCount`, `Location`, `Rating`, `Comments`, `DateAdded`, `Label`, `Remixer`, `Mix` + figli `TEMPO` e `POSITION_MARK`.

## Entità

### Track

```text
id
rekordbox_track_id
spotify_id
soundcloud_id
source_type            # spotify | soundcloud | local
title
artist
album
genre
year
duration_seconds
bpm
tonality               # Camelot (es. "7A")
play_count
location
date_added
rating
comments
created_at
updated_at
```

### BeatgridPoint (da nodi TEMPO)

```text
id
track_id
start_seconds          # Inizio
bpm                    # Bpm
meter                  # Metro (es. "4/4")
beat                   # Battito
```

### CuePoint (da nodi POSITION_MARK)

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
strategy               # smooth | progressive | contrast | experimental | peak_time | warm_up | closing
prompt                 # prompt libero dell'utente, se usato
global_explanation     # spiegazione narrativa dell'AI
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
risk_level             # low | medium | high
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
source_entity_type     # track | artist | genre | set
source_entity_id
suggested_name
suggested_entity_type
reason
set_usage              # opening | bridge | peak | reset | closing
priority
external_url
search_queries_json
status                 # new | to_listen | listened | added_to_library | ignored
created_at
updated_at
```

## Priorità per fase

- **MVP 1**: Track, BeatgridPoint, CuePoint, Setlist, SetlistTrack, Transition (+ report import, anche solo come tabella o JSON salvato)
- **MVP 2**: estensioni Spotify su Track/Artist (cache enrichment)
- **MVP 3**: campi AI su Setlist/SetlistTrack già previsti sopra
- **MVP 4**: Label, Release, LibraryGap, DiscoverySuggestion
