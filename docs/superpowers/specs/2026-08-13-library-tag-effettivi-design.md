# Library: tag effettivi dal file fisico

Data: 2026-08-13
Stato: approvato a voce, in attesa di review scritta

## Obiettivo

Per le tracce possedute, la Library deve mostrare (e permettere di modificare) i
metadati descrittivi reali del file fisico invece dei valori importati dallo
streaming. I tag curati in Organize diventano ciò che si vede e si filtra in
Library, senza introdurre un secondo punto di scrittura sui file.

## Decisioni prese

1. **Campi che seguono il file: `genre`, `album`, `label`, `year`.**
   `artist` e `title` restano l'identità Cratory della `Track` (reggono
   de-duplicazione, matching streaming, ISRC). Artist/title del file sono
   mostrati nel dettaglio come informazione, con evidenza se discrepanti.
2. **Valore effettivo risolto a query-time** (COALESCE sul join con
   `audio_file` via `tracks.primary_file_id`). Nessuna colonna derivata,
   nessun job di sincronizzazione: la fonte (`AudioFile`) è già mantenuta da
   Organize (scan, apply, edit tag). Alternative scartate: copia dei tag nelle
   colonne `Track` (quattro punti di scrittura da mantenere, perdita dei valori
   streaming) e colonne cache separate (stessa manutenzione senza il beneficio).
3. **Edit unificato nel `TrackEditModal`**: per tracce con file, i quattro
   campi salvano sul file via l'endpoint Organize esistente
   (`POST /api/organize/files/{id}/tags` sul primary file); tutto il resto — e
   tutto, per tracce senza file — salva sulla `Track` come oggi. La regola
   single-writer (CLAUDE.md, regola 7) resta rispettata: l'unica scrittura
   fisica dei tag passa dal servizio Organize.

## Comportamento

### Valore effettivo

- Per ogni campo in {genre, album, label, year}:
  `effettivo = COALESCE(file.campo, tracks.campo)` dove `file` è l'`AudioFile`
  puntato da `tracks.primary_file_id`.
- La regola vale ovunque la Library espone quei campi: lista (`GET /api/tracks`),
  dettaglio (`GET /api/tracks/{id}`), filtri, ordinamenti e l'aggregato generi
  (`GET /api/library/genres` / dashboard), così ciò che si vede e ciò che si
  filtra coincidono sempre.
- Nota semantica del COALESCE: un tag **vuoto sul file** (NULL) lascia visibile
  il valore streaming della `Track`. È il comportamento voluto: il file vince
  quando ha qualcosa da dire.
- Provenienza esposta per campo nel payload API (es. `genre_from_file: bool`)
  perché il frontend possa mostrare l'indicatore "dal file".

### Dettaglio traccia

- I quattro campi mostrano il valore effettivo con indicatore discreto "dal
  file" quando la provenienza è il file.
- Sezione informativa con artist/title letti dal file; se differiscono
  dall'identità Cratory (confronto case-insensitive, trim) vengono evidenziati:
  è il segnale di un file taggato male o linkato alla traccia sbagliata.
- Cross-link: dal dettaglio traccia (se `has_local_file`) link al file in
  Organize Files; da una riga di Files con `track_id` link al dettaglio traccia.

### Modifica

- `TrackEditModal`, traccia **con** file: genre/album/label/year sono
  precompilati col valore effettivo e al salvataggio vanno a
  `POST /api/organize/files/{primary_file_id}/tags` (solo i campi cambiati);
  gli altri campi seguono il percorso attuale (`PATCH` della `Track`). Il modal
  mostra una nota: "questi campi scrivono i tag del file".
- `TrackEditModal`, traccia **senza** file: comportamento attuale invariato.
- La risposta dell'endpoint Organize aggiorna già la riga `AudioFile`: al
  salvataggio il frontend ricarica la traccia e vede subito il nuovo effettivo.
- `normalize_genre` continua a valere solo per il genere della `Track`
  (percorso attuale); il tag `genre` del file si salva com'è, coerente con
  l'edit da Organize Files.

## Architettura

### Backend

- `repositories.list_tracks` / `get_track`: `outerjoin` su `AudioFile`
  (`tracks.primary_file_id == audio_file.id`, FK indicizzata) ed espressioni
  `coalesce()` per i quattro campi, riusate identiche in select, filtri e sort.
  `genres_overview` aggrega sull'espressione effettiva.
- `serializers`/`schemas`: i campi esistenti (`genre`, `album`, `label`,
  `year`) portano il valore effettivo; si aggiungono i flag di provenienza e,
  nel solo dettaglio, `file_artist`/`file_title`.
- Nessuna migrazione di schema. Nessun nuovo endpoint: la scrittura riusa
  `POST /api/organize/files/{id}/tags`.
- Import da `app.organize.models` limitato al livello repository/query (il
  modello core continua a non importare `app.organize`; la relationship vive
  già lato `AudioFile`).

### Frontend

- `lib/api.ts`: `Track` esteso con i flag di provenienza; `TrackDetail` con
  `file_artist`/`file_title`.
- Dettaglio traccia: indicatore "dal file" sui quattro campi, sezione
  artist/title del file con evidenza discrepanza, link a Organize Files.
- `TrackEditModal`: routing del salvataggio (campi file → `updateFileTags` di
  `lib/organize/api.ts` sul primary file; resto → percorso attuale), nota
  informativa. I due salvataggi possono essere entrambi necessari nello stesso
  submit; l'errore di uno non deve mascherare il successo dell'altro (riportare
  errori per percorso).
- Organize Files: colonna/azione "apri traccia" quando `track_id` è presente.

## Casi limite ed errori

- `primary_file_id` NULL ma `has_local_file` true (o viceversa, stati
  transitori dello scan): il COALESCE degrada da solo ai valori `Track`; l'edit
  tratta la traccia come "senza file" se manca il primary file.
- File sparito dal disco dopo lo scan: l'endpoint Organize fallisce con errore
  esplicito; il modal lo mostra senza toccare la `Track`.
- Tag del file rimosso (portato a vuoto) da Organize: l'effettivo torna al
  valore streaming — comportamento accettato, si documenta e basta.
- Traccia con più file: vince sempre `primary_file_id` (rappresentante già
  scelto dal linker), coerente con la cache `local_*` esistente.

## Test

- Repository: effettivo con file completo, file con tag NULL (fallback),
  traccia senza file; filtro e sort su genre effettivo (traccia che matcha solo
  per il tag file e traccia che matcha solo per il valore streaming);
  `genres_overview` con mix possedute/lead.
- Router: payload con flag di provenienza e `file_artist`/`file_title` nel
  dettaglio.
- Frontend (unit/e2e esistenti): TrackEditModal salva genre sul file per
  traccia posseduta e sulla Track per lead; indicatore "dal file" nel
  dettaglio.
- Ogni asserzione va provata rompendo il codice (regola di casa sui test
  vacui): in particolare il filtro effettivo deve fallire se si filtra sulla
  sola colonna `tracks.genre`.

## Fuori scope

- Colonne dei tag file nella tabella Library (eventuale iterazione futura).
- Qualsiasi scrittura di tag fuori dal servizio Organize.
- Sincronizzazione dei tag file dentro le colonne `Track`.
