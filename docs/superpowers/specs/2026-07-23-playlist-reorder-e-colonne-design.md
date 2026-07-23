# Playlist: colonne Genere/Energia + riordino manuale

Data: 2026-07-23

## Obiettivo

Nella lista tracce di una playlist ([frontend/app/playlists/[id]/page.tsx](../../../frontend/app/playlists/[id]/page.tsx)):

1. Mostrare anche le colonne **Genere** ed **Energia**.
2. Dare un **metodo rapido per riordinare manualmente** le tracce: spostare una traccia a
   una posizione specifica (es. dal #35 al #1) facendo scalare le altre. Solo per le
   **playlist manuali** (`kind == "manual"`).

## Stato attuale

- L'ordine della playlist deriva da `added_at` (NULLs last); **non esiste una colonna
  posizione** (era esplicitamente fuori scope). Il `#` a video è calcolato lato client da
  `added_at` (`insertionRank`).
- La tabella ha già intestazioni cliccabili per l'ordinamento per colonna (`th`/`toggleSort`),
  con getter già presenti per `genre` ed `energy`, ma **nessuna colonna** Genere/Energia a
  schermo.

## Design

### Backend — ordine persistente (colonna `position`)

- Nuova colonna **`position`** (`Integer`, nullable) su `playlist_tracks`
  (`backend/app/models.py`). Viene aggiunta automaticamente da `_migrate_add_model_columns`
  (nessun dict da mantenere).
- Migrazione custom idempotente **`_migrate_backfill_playlist_positions(conn)`** in
  `backend/app/db.py` (chiamata da `ensure_schema`): per ogni playlist assegna `position`
  1..N nell'ordine attuale (`ROW_NUMBER() OVER (PARTITION BY playlist_id ORDER BY (added_at
  IS NULL), added_at, track_id)`), **solo dove `position IS NULL`**. Idempotente: dopo il
  backfill le posizioni sono valorizzate, quindi ri-esecuzioni sono no-op.
- `add_track_to_playlist` (`backend/app/repositories.py`) imposta
  `position = COALESCE(MAX(position),0)+1` per quella playlist (append in fondo). Vale per
  ogni inserimento (create-from-tracks, add-tracks, import/sync).
- `tracks_for_playlist` ordina per `(position IS NULL), position, (added_at IS NULL),
  added_at, track_id` (posizione primaria, tie-break robusti).

### Backend — endpoint di riordino

- **`POST /api/playlists/{playlist_id}/reorder`**, body `PlaylistReorderRequest`:
  `{ track_id: int, position: int (ge=1) }`.
- Comportamento:
  - 404 `playlist_not_found` se la playlist non esiste.
  - **409 `playlist_not_manual`** se `kind != "manual"` (il riordino manuale è consentito
    solo sulle playlist manuali).
  - 404 `track_not_in_playlist` se la traccia non appartiene alla playlist.
  - `position` clampata a `[1, N]` (N = numero tracce).
  - Ripo `reorder_playlist_track`: carica i membri in ordine di `position`, rimuove la
    traccia dalla sua posizione, la reinserisce all'indice `position-1`, **rinumera tutte**
    le membership 1..N.
  - Ritorna la lista tracce riordinata (`list[TrackOut]`, come `GET /{id}/tracks`).

### Frontend

- **Colonne Genere ed Energia** nella tabella: Genere dopo Artista, Energia dopo Key,
  cliccabili per ordinare come le altre colonne (i getter esistono già). Nuova chiave i18n
  `colEnergy`.
- `insertionRank` passa a usare **l'indice dell'array** `tracks` (che ora arriva già in
  ordine `position` dal backend) invece di ri-ordinare per `added_at`.
- **Riordino** (solo `playlist.kind === "manual"` e nessun ordinamento per colonna attivo,
  `sort === ""`):
  - La cella `#` diventa modificabile: click sul numero → input con la posizione corrente →
    si digita la nuova posizione → Invio chiama `reorderPlaylistTrack(id, track_id, pos)` e
    aggiorna `tracks` con la lista ritornata.
  - Pulsante **↑ "in cima"** per riga (sposta a posizione 1).
  - Quando è attivo un ordinamento per colonna, il `#` non è modificabile (l'ordine a video
    non è quello della playlist); le posizioni salvate non cambiano ordinando per colonna.
- Client: `reorderPlaylistTrack(playlistId, trackId, position): Promise<Track[]>`.

## Test

- Backend (TDD): backfill assegna 1..N nell'ordine corrente; `add_track_to_playlist`
  appende; `reorder_playlist_track` sposta+rinumera; endpoint 409 su non-manuale, 404 su
  traccia non membro, clamp della posizione.
- Frontend: verifica live (colonne visibili; riordino #35→#1 con scalata; controlli assenti
  su playlist non-manuali e con ordinamento per colonna attivo).

## Note e vincoli

- Nessuna modifica ai file audio; si tocca solo `playlist_tracks`.
- Il `#` mostrato resta l'indice contiguo 1..N dell'elenco; eventuali buchi di `position`
  sul DB non si vedono.
- Il sync delle playlist importate appende in fondo (position max+1) e non riordina; il
  riordino manuale non è comunque esposto per quelle playlist.
