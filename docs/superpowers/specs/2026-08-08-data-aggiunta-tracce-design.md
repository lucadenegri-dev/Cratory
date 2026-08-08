# Data di aggiunta tracce in Library e Playlist — Design

**Data:** 2026-08-08
**Stato:** approvato

## Obiettivo

Mostrare la data di aggiunta delle tracce nelle due viste tabellari principali:

- **Library**: data del primo import in libreria (`Track.added_at`), colonna ordinabile.
- **Dettaglio playlist**: data di ingresso del brano in *quella* playlist
  (`playlist_tracks.added_at`, per gli import Spotify è la data originale della
  playlist sorgente).

Nessuna migrazione DB: entrambi i campi esistono già.

## Stato attuale

- `Track.added_at` è già serializzato da `track_out` e tipizzato nel frontend
  (`frontend/lib/api/types.ts`), ma nessuna vista lo mostra.
- `playlist_tracks.added_at` esiste ma non è esposto dall'API: l'endpoint
  `GET /playlists/{id}/tracks` restituisce `TrackOut` con il solo `added_at`
  di libreria.
- L'endpoint `GET /tracks` ordina per
  `title|artist|source|bpm|key|energy|genre|duration|year|status|rating`,
  non per data di aggiunta.

## Design

### Backend

1. **Sort per data in Library**
   - `backend/app/routers/tracks.py`: aggiungere `added_at` al pattern del
     parametro `sort`.
   - `backend/app/repositories.py`: aggiungere `added_at` a `_SORT_COLUMNS`.

2. **Esposizione della data per-playlist**
   - `backend/app/schemas.py`: nuovo campo opzionale
     `playlist_added_at: datetime | None = None` su `TrackOut`
     (default `None`, valorizzato solo dal dettaglio playlist — stesso
     pattern di `playlist_position`).
   - `backend/app/routers/playlists.py`, endpoint `playlist_tracks`:
     una query sulla tabella di associazione
     (`track_id → added_at` per la playlist richiesta) e assegnazione
     `row.playlist_added_at = mapping.get(t.id)`.
   - Scartata l'alternativa di far restituire tuple `(Track, added_at)` a
     `tracks_for_playlist`: toccherebbe tutti i chiamanti senza beneficio.

3. **Default `added_at` per aggiunte manuali**
   - In `add_track_to_playlist` (repositories): se il chiamante non passa
     `added_at`, valorizzarlo con l'ora corrente. Le aggiunte fatte da
     Cratory da oggi in poi avranno la data; le righe storiche senza data
     restano `NULL`.

### Frontend

4. **Library** (`frontend/app/library/page.tsx`)
   - Colonna "Aggiunta" ordinabile (`toggleSort("added_at")`), dopo le
     colonne esistenti.
   - Formato corto locale it (`12 lug 2026`), `whitespace-nowrap`, tono
     attenuato (muted) per non pesare sulla gerarchia visiva.
   - Valore mancante: trattino `—`.

5. **Dettaglio playlist** (`frontend/app/playlists/[id]/`)
   - Colonna con `playlist_added_at`, stesso formato e stesso fallback `—`.

Le tabelle tracce sono state appena compattate per evitare lo scroll
orizzontale: la colonna data è stretta e nowrap; verifica visiva nel browser
dopo la modifica.

## Test

- Backend: test per il sort `added_at` su `GET /tracks` e per la presenza di
  `playlist_added_at` in `GET /playlists/{id}/tracks` (valorizzato quando la
  riga di associazione ha la data, `null` altrimenti); test che
  `add_track_to_playlist` senza `added_at` valorizzi l'ora corrente.
- Frontend: lint + build; verifica visiva delle due tabelle (niente scroll
  orizzontale).

## Fuori scope

- Backfill delle righe `playlist_tracks.added_at` NULL storiche.
- Filtri per intervallo di date.
- Data di aggiunta nella vista a griglia della library (solo tabella).
