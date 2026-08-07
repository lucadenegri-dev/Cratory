# Playlist speciali fissate, copertina Discovery, fix conteggio tracce

Data: 2026-08-07 · Stato: approvata

## Obiettivo

Tre interventi sulla pagina Playlist e sui conteggi:

1. **Sezione "Speciali" fissata in alto**: le tre playlist di sistema — Discovery
   (`kind="discovery"`), SoundCloud Likes e Spotify Likes (`kind="liked"`) — appaiono
   in un blocco visivamente separato in cima alla pagina, in quest'ordine fisso.
   Sotto, la lista delle altre playlist resta invariata (ordinamento backend per
   `imported_at desc`, numerazione progressiva che riparte da 01 senza contare le
   speciali).
2. **Copertina Discovery**: nuovo asset statico `frontend/public/cover-discovery.svg`
   nello stile dei cover liked esistenti; `PlaylistCover` estende il fallback a
   `kind === "discovery"`.
3. **Fix conteggio tracce**: `merge_tracks` (dedup) elimina membership da
   `playlist_tracks` senza mai aggiornare il campo denormalizzato
   `Playlist.track_count`, che resta gonfiato quando `keep` e `drop` erano nella
   stessa playlist. Fix nel merge + riparazione dei conteggi esistenti.

## Design

### 1. Sezione Speciali (solo frontend)

- `frontend/app/playlists/page.tsx` partiziona la risposta di
  `listImportedPlaylists()` in `special` (`kind === "discovery" || kind === "liked"`)
  e `regular`.
- Ordine fisso delle speciali: Discovery, SoundCloud Likes, Spotify Likes
  (chiave: `kind === "discovery"` prima, poi `liked` per `platform` soundcloud →
  spotify).
- Se esistono speciali, la pagina mostra due heading di sezione (stile editoriale
  già in uso: `text-xs uppercase tracking-wide text-faint`): "Speciali" e
  "Importate" (i18n it/en). Le card delle speciali non hanno numero d'ordine;
  quelle normali mantengono la numerazione 01, 02, …
- Il backend non cambia: `kind` e `platform` sono già serializzati.

### 2. Copertina Discovery (solo frontend)

- Nuovo `frontend/public/cover-discovery.svg` (120×120, stile coerente con
  `cover-liked-*.svg`: fondo pieno/gradiente + glifo centrale; glifo bussola
  "explore" per il dig).
- `frontend/components/playlist-cover.tsx`: fallback anche per
  `kind === "discovery"`.

### 3. Fix conteggio tracce (backend)

- `merge_tracks` (`backend/app/repositories.py`): raccoglie le playlist a cui
  apparteneva `drop` e chiama `recount_playlist` su ciascuna dopo lo spostamento
  delle membership (prima del ritorno; il commit resta al chiamante).
- Migrazione idempotente in `backend/app/db.py` (`ensure_schema`):
  `UPDATE playlists SET track_count = (SELECT COUNT(*) FROM playlist_tracks …)`
  per riparare i conteggi già sbagliati; naturalmente idempotente e auto-riparante.
- Test in `backend/tests/test_track_merge.py`: merge con `keep` e `drop` nella
  stessa playlist → `track_count` scende di 1; merge con playlist disgiunte →
  conteggi invariati.

## Fuori scope

- Nessun campo nuovo a DB (niente `is_pinned`): la specialità resta codificata da
  `kind`.
- Nessun cambiamento all'ordinamento backend di `list_playlists`.
- Il conteggio resta denormalizzato (niente COUNT al volo nella GET).
