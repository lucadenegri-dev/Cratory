# 03 — Data Model

Il modello ruota attorno alle **playlist importate** (da Spotify o dall'import manuale) e alle **tracce** raccolte da esse, arricchite con feature musicali da provider esterni. Le tracce possono anche entrare in libreria singolarmente dal Discovery.

## Entità

### Playlist

Playlist importata da uno streaming, punto di partenza del flusso.

```text
id
platform                 # spotify | manual (soundcloud in backlog)
platform_playlist_id
name
owner
url
artwork_url
track_count
kind                     # playlist | liked | manual
imported_at
created_at / updated_at
```

### Track

Una traccia raccolta da una o più playlist (ultima import vince per playlist_id/name).

```text
id
# Identità streaming (nuovo flusso)
platform                 # spotify | soundcloud
platform_track_id
spotify_id / soundcloud_id
isrc
url
added_at                 # quando è stata aggiunta alla playlist
playlist_id              # FK Playlist (provenienza)
playlist_name
source_type              # spotify | manual (soundcloud/local previsti)
# Colonna legacy Rekordbox: nullable, nessun codice la popola più (vestigiale)
rekordbox_track_id
location
play_count / rating / comments / date_added
# Metadata editoriali
title / artist / album / year
album_art_url            # artwork
# Feature musicali (da enrichment esterno: GetSongBPM/MusicBrainz/Last.fm)
bpm
tonality                 # Camelot legacy
camelot_key              # Camelot esplicito (es. "8A")
genre                    # genre_primary
genre_secondary
label
release_date
mood                     # stringa (es. "dark", "uplifting")
energy                   # 0-100
danceability             # 0-100
vocalness                # 0-100
# Stato e tracciabilità enrichment
status                   # imported | enriched | ready_for_set | missing_features | low_confidence
enrichment_source        # spotify | musicbrainz | getsongbpm | cyanite | ...
enrichment_confidence    # 0-100
enriched_at
created_at / updated_at
```

**Stati traccia** (calcolati in `services/track_status.py`):

| stato | significato |
|---|---|
| `imported` | importata, nessun enrichment musicale |
| `missing_features` | enrichment tentato ma BPM/key ancora assenti |
| `ready_for_set` | ha BPM **e** key (Camelot): usabile dal Set Builder |
| `low_confidence` | match enrichment a bassa confidenza (dato poco affidabile) |
| `enriched` | arricchita ma non ancora pronta per il set |

**Priorità di matching enrichment**: `ISRC` → `platform_track_id` → `artist + title + duration` → `fuzzy artist + title`.

### Artist

```text
id / name
spotify_artist_id / discogs_artist_id / musicbrainz_artist_id
genres / popularity / metadata_json
created_at / updated_at
```

### BeatgridPoint / CuePoint

Tabelle legacy (`start_seconds`, `bpm`, `meter`, `beat`; `name`, `type`, `num`, `color`, `comment`). Erano popolate dall'import Rekordbox, ora rimosso: nessun codice le scrive più. Restano nello schema per retro-compatibilità e per un eventuale reintegro futuro di una fonte beatgrid.

### Setlist

```text
id / name
target_duration_minutes
start_bpm / end_bpm
strategy                 # smooth | progressive | contrast | experimental | peak_time | warm_up | closing
prompt                   # prompt libero dell'utente
global_explanation       # narrativa AI
generated_by             # algorithmic | ai
validation               # warning/auto-fix del Validation Engine (JSON)
created_at / updated_at
```

### SetlistTrack

```text
id / setlist_id / track_id / position
role                     # intro | warmup | groove | transition | peak | release | closing
transition_score
transition_reason        # motivazione tecnica
transition_note          # nota di transizione (AI o tecnica)
ai_reason                # motivazione narrativa AI
risk_level               # low | medium | high
created_at
```

### Label / Release / DiscoverySuggestion (espansione libreria, opzionale)

Invariati rispetto alla versione precedente: usati dal modulo di espansione/crate digging (Discogs/MusicBrainz). `DiscoverySuggestion` ha stati `new | to_listen | listened | added_to_library | ignored`.

### EnrichmentCache

Cache persistente delle risposte dei provider feature, per non richiamare la rete sulla stessa traccia.

```text
id
provider                 # getsongbpm | musicbrainz | chain | ...
lookup_key               # isrc:<ISRC> oppure ta:<title>::<artist>
result_json              # dict del provider, oppure NULL = "not found" (cachato anch'esso)
cached_at
```

`services/feature_enrichment.py` pre-carica in blocco le righe rilevanti (niente N+1), fa upsert dei risultati e cacha anche i not-found. `force=True` bypassa la cache in lettura ma ne aggiorna comunque le righe. (Sostituisce il vecchio `ImportReport`, rimosso con l'import Rekordbox.)

## Migrazioni

App locale senza Alembic: `db.ensure_schema()` esegue `create_all` + `ALTER TABLE` idempotenti per le colonne aggiunte dopo MVP 1 (tutti i campi streaming/enrichment/ruoli sono già gestiti lì). La colonna `rekordbox_track_id` è **nullable** e non più scritta: su un DB nuovo è immediato; un DB storico con vincolo `NOT NULL` va ricreato per importare tracce puramente streaming/manuali.
