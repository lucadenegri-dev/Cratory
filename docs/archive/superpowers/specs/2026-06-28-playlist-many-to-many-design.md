# Playlist many-to-many (membership) — design

Data: 2026-06-28
Stato: design approvato, pronto per il piano di implementazione.

## Obiettivo

Permettere a un brano di appartenere a **più playlist** contemporaneamente. Oggi
`Track.playlist_id` è una FK singola (1:1): reimportare/usare lo stesso brano in
un'altra playlist lo "sposta" invece di aggiungerlo. Si introduce una tabella
associativa `playlist_tracks` e si convertono import, prune, delete, enrichment-scoping
e l'endpoint discovered-tracks alla membership. La libreria mostra "in N playlist".

## Motivazione

Il modello 1:1 costringe a mitigazioni ("scollega invece di cancellare" su delete e
prune) e a un edge-case nell'endpoint `discovered-tracks` ("non spostare una traccia
già in un'altra playlist"). La membership M2M elimina la causa: un brano è in libreria
una volta sola e ha N appartenenze indipendenti.

Nota: `added_at` è **per-playlist** (quando il brano è stato aggiunto *a quella*
playlist) ma oggi vive su `Track`. Con M2M si sposta sulla membership, così
l'ordinamento per-playlist è corretto.

## Vincoli (regole del progetto)

- Niente Alembic: migrazione additiva idempotente in `ensure_schema` (app locale SQLite).
- Deterministico; nessuna AI in gioco.
- Non perdere dati: il backfill copia le appartenenze esistenti prima di svuotare le
  colonne legacy.
- Stile commit: nessun trailer `Co-Authored-By`.

## Decisioni consolidate

- Scope: modello dati **+ mostrare le appartenenze** (nessuna gestione membership da
  UI).
- Colonne legacy `Track.playlist_id` / `Track.playlist_name`: **lasciate fisicamente**
  in tabella (niente rebuild SQLite) ma **svuotate** (NULL) dopo il backfill. Non più
  lette/scritte.
- UI: badge "in N playlist" nella libreria; elenco nomi nel dettaglio traccia.

## Componenti

### 1. Modello (`backend/app/models.py`)

- Nuova tabella associativa `playlist_tracks`:
  - `playlist_id` FK → `playlists.id`, parte di PK, `ondelete` non necessario (gestito a
    livello app), indicizzata;
  - `track_id` FK → `tracks.id`, parte di PK, indicizzata;
  - `added_at: DateTime | None` (per-playlist);
  - PK composta `(playlist_id, track_id)`.
- Relationship: `Track.playlists: list[Playlist]` e `Playlist.tracks: list[Track]` via
  `secondary="playlist_tracks"`. (L'`added_at` di membership si gestisce con query
  dirette nelle repo, non tramite la relationship, per semplicità.)
- `Track.playlist_id` / `Track.playlist_name` restano come colonne ma diventano legacy
  (non usate).

### 2. Migrazione (`backend/app/db.py`, `ensure_schema`)

- `create_all` crea `playlist_tracks` (dal modello).
- Backfill idempotente in una funzione `_migrate_playlist_memberships(conn)` chiamata
  dentro `ensure_schema` (dopo gli ALTER, come `_migrate_drop_legacy`):
  - per ogni riga `tracks` con `playlist_id` non nullo, `INSERT OR IGNORE INTO
    playlist_tracks (playlist_id, track_id, added_at) SELECT playlist_id, id, added_at
    FROM tracks WHERE playlist_id IS NOT NULL`;
  - poi `UPDATE tracks SET playlist_id = NULL, playlist_name = NULL WHERE playlist_id IS
    NOT NULL`.
  - Idempotente: `INSERT OR IGNORE` non duplica; alla seconda esecuzione non ci sono più
    righe con `playlist_id` non nullo, quindi è no-op.
  - Guard: eseguire solo se la tabella `playlist_tracks` esiste (post create_all) — vero
    per costruzione.

### 3. Repository (`backend/app/repositories.py`)

- `add_track_to_playlist(db, track, playlist, *, added_at=None) -> None`: idempotente
  (`INSERT OR IGNORE` / controllo esistenza membership). Non committa (lascia al chiamante).
- `remove_track_from_playlist(db, playlist_id, track_id) -> None`.
- `recount_playlist(db, playlist) -> None`: `playlist.track_count = <conteggio membership>`.
- `tracks_for_playlist(db, playlist_id)`: join su `playlist_tracks`, ordinato per
  `playlist_tracks.added_at` (NULL last), come oggi.
- `delete_playlist(db, playlist_id)`: cancella le righe `playlist_tracks` di quella
  playlist (le tracce restano in libreria/altre playlist), poi elimina la `Playlist`.
  Sostituisce l'attuale "scollega via Track.playlist_id".

### 4. Import (`playlist_import.py`, `manual_import.py`)

- `_apply(track, norm, playlist)`: invece di settare `track.playlist_id/playlist_name`,
  chiama `add_track_to_playlist(db, track, playlist, added_at=norm.added_at)`.
  (Serve `db` nel chiamante; passare `db` a `_apply` o spostare l'add nel loop.)
- `import_playlist` prune: itera le membership della playlist
  (`tracks_for_playlist`/query su `playlist_tracks`); per quelle non più presenti
  (`isrc`/`platform_track_id` fuori dal set importato) chiama
  `remove_track_from_playlist`. Poi `recount_playlist`.
- `import_playlist` / `manual_import`: `track_count` via `recount_playlist` (non più
  `created + updated`, che con M2M e dedup non riflette le membership effettive).
- `manual_import.py`: stessa conversione (oggi setta `playlist_id`/`name` su create e
  update).

### 5. Enrichment scoping (`feature_enrichment.py`)

- Sostituire `stmt.where(Track.playlist_id == playlist_id)` con un filtro su membership:
  `Track.id.in_(select(playlist_tracks.c.track_id).where(playlist_tracks.c.playlist_id
  == playlist_id))`.

### 6. Endpoint (`routers/playlists.py`, `add_discovered_track`)

- Dopo `import_single_track`, chiamare `add_track_to_playlist(db, track, playlist)`
  (idempotente) + `recount_playlist` + commit. Rimuovere l'edge-case 1:1 "non spostare".
- Il write-back Spotify resta invariato. La risposta resta
  `{created, track, spotify_added, spotify_error}`.

### 7. Serializer + schema (`serializers.py`, `schemas.py`)

- `TrackOut`: rimuovere `playlist_id` e `playlist_name`; aggiungere
  `playlists: list[PlaylistRef]` dove `PlaylistRef{ id: int, name: str }`.
- `track_out(track)`: `playlists=[PlaylistRef(id=p.id, name=p.name) for p in
  track.playlists]`.
- Endpoint che listano molte tracce (libreria, playlist tracks): eager-load
  `Track.playlists` (`selectinload`) per evitare N+1.

### 8. Frontend

- `frontend/lib/api.ts`: nell'interfaccia `Track`, sostituire `playlist_id`/
  `playlist_name` con `playlists: { id: number; name: string }[]`.
- Libreria (`app/library/page.tsx`): badge "in N playlist" per riga (con `title`
  che elenca i nomi, o simile).
- Dettaglio traccia (`app/tracks/[id]/page.tsx`): elenco delle playlist di appartenenza.

## Testing

Backend (pytest, fixture `db` in-memory; per il backfill usare un engine sqlite file/temp
o costruire lo stato e invocare la funzione di migrazione direttamente):

- `add_track_to_playlist` è idempotente (due chiamate → una sola membership).
- un brano in 2 playlist: `tracks_for_playlist` lo restituisce per entrambe; appare in
  `track.playlists` con 2 voci.
- import non "ruba": importando lo stesso brano in P2, resta anche in P1.
- prune (sync) rimuove la membership solo dalla playlist sincronizzata, non dalle altre.
- `delete_playlist` elimina le membership di quella playlist; il brano resta nelle altre
  e in libreria.
- `add_discovered_track` aggiunge membership (niente più "non spostare"); idempotente su
  doppio add.
- enrichment scoping per playlist seleziona le tracce via membership.
- `recount_playlist` / `track_count` corretto dopo import, add, prune, delete.
- serializer `track_out` espone `playlists`.
- migrazione backfill: dato un `tracks.playlist_id` valorizzato, dopo `ensure_schema`
  esiste la membership e `playlist_id` è NULL; rieseguendo `ensure_schema` non si
  duplica.

Frontend: lint + build; verifica browser (badge "in N playlist" in libreria, elenco nel
dettaglio traccia).

## Fuori scope

- Gestione membership da UI (aggiungere/togliere un brano da playlist dall'interfaccia).
- Rimozione fisica delle colonne legacy `Track.playlist_id`/`playlist_name` (svuotate,
  non droppate).
- Ordinamento manuale (position) all'interno della playlist: si resta sull'ordine per
  `added_at`.
- Migrazione a PostgreSQL.
