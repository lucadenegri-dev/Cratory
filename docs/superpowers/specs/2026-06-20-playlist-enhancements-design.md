# Miglioramenti pagina playlist — Design

Data: 2026-06-20
Stato: approvato (in attesa di piano di implementazione)

## Obiettivo

Migliorare la pagina di dettaglio di una playlist (`frontend/app/playlists/[id]/page.tsx`)
portandola al livello della libreria e aggiungendo la sincronizzazione con Spotify.
Quattro funzionalità:

1. Filtri e ordinamento sulle tracce della playlist (come in libreria).
2. La colonna `#` rappresenta l'ordine cronologico di inserimento della traccia nella
   playlist Spotify (la prima aggiunta = `#1`).
3. Pulsante "Aggiorna da Spotify": importa le tracce nuove e scollega dalla playlist
   quelle rimosse, mantenendole però in libreria.
4. Colorazione delle tonalità (Camelot) in stile Mixed In Key / Spotify.

Nessuna modifica al modello dati. Una traccia continua ad appartenere a una sola
playlist via `Track.playlist_id`.

## Contesto rilevante (stato attuale)

- `GET /api/playlists/{id}/tracks` restituisce tutte le tracce della playlist, già
  ordinate per `added_at` crescente (`repositories.tracks_for_playlist`, nulls last).
- `Track.added_at` esiste nel modello ma **non** è esposto in `TrackOut` (`schemas.py`).
- `Track.playlist_id` / `Track.playlist_name` legano la traccia a una sola playlist.
  La libreria (`/api/tracks`) mostra tutte le tracce indipendentemente dalla playlist,
  quindi azzerare `playlist_id` mantiene la traccia in libreria.
- `services/playlist_import.import_playlist()` importa/aggiorna in modo idempotente ma
  **non** rimuove mai tracce non più presenti.
- La libreria (`frontend/app/library/page.tsx`) ha già il pattern di barra filtri +
  header colonna cliccabili per l'ordinamento (helper `th`, `toggleSort`).
- Le key sono stringhe Camelot tipo `7A`, `12B` (`services/camelot.py` valida/parsa).

## 1. Filtri e ordinamento (client-side)

Le tracce di una playlist sono in numero limitato (decine / poche centinaia) e già tutte
caricate. Filtro e ordinamento avvengono **nel frontend**, senza modifiche al backend né
paginazione.

- Barra filtri come in libreria: artista, titolo, genere, sorgente, stato, BPM min/max,
  key, checkbox "solo dati incompleti".
- Header colonna cliccabili (toggle asc/desc) riusando lo stesso pattern di
  `library/page.tsx` (helper `th` + stato `sort`/`order`).
- Il filtraggio/ordinamento opera su un array derivato dallo stato `tracks`; lo stato
  originale resta intatto (serve per il calcolo del rank di inserimento, vedi §2).

Colonne ordinabili: titolo, artista, sorgente, BPM, key, durata, stato. (Energy/genere
opzionali, in linea con la libreria.)

## 2. Colonna `#` = ordine di inserimento

- Backend: aggiungere `added_at: datetime | None` a `TrackOut` (`schemas.py`) e
  passarlo esplicitamente in `serializers.track_out` (che costruisce `TrackOut` con
  kwargs espliciti): `added_at=track.added_at`.
- Frontend: calcolare una mappa **rank di inserimento stabile** una volta sola dai dati
  originali — ordinando per `added_at` crescente (nulls last, fallback su `id` per
  stabilità), assegnare `1..N`. Mostrare questo rank nella colonna `#`.
- Il rank resta legato alla traccia anche quando la tabella è ordinata/filtrata per
  un'altra colonna (es. ordinando per BPM, ogni riga mostra comunque il proprio numero
  di inserimento, quindi non sequenziale).
- Ordinamento di default della vista: per ordine di inserimento crescente (`#1` in cima).
- Nessuna colonna data aggiuntiva (scelta esplicita dell'utente).

## 3. Aggiorna da Spotify (sync)

### Backend

- Nuovo endpoint `POST /api/playlists/{id}/sync` in `routers/playlists.py`.
- 404 se la playlist non esiste. 409 (o messaggio chiaro) se la playlist non è
  sincronizzabile: solo `platform == "spotify"`. Sono sincronizzabili:
  - playlist con `platform_playlist_id` (ri-scarica i brani della playlist),
  - playlist `kind == "liked"` (ri-scarica i brani piaciuti).
  - le playlist manuali non sono sincronizzabili → nessun pulsante in UI.
- Recupero item via `SpotifyWebClient` (stesso codice usato in `import_from_spotify`:
  `get_playlist_tracks` / `get_liked_tracks`).
- Logica di sync:
  - **Importa/aggiorna** gli item correnti riusando `import_playlist(...)` con un nuovo
    parametro `prune=True`.
  - **Prune**: costruito il set delle identità correnti (per ciascun item normalizzato:
    `isrc` e/o `platform_track_id`), le tracce con `playlist_id == playlist.id` la cui
    identità non è presente nel set vengono scollegate: `playlist_id = None`,
    `playlist_name = None`. Restano nella tabella `tracks` (quindi in libreria).
  - `playlist.track_count` aggiornato al numero di tracce ancora collegate.
- Enrichment automatico delle nuove tracce via `_autoenrich(playlist_id)` (best-effort,
  come nell'import).
- Report restituito: estendere `PlaylistImportReport` (o uno schema dedicato
  `PlaylistSyncReport`) con `removed: int`. Forma:
  `{ playlist_id, name, created, updated, removed, skipped, total }` dove
  `total` = tracce collegate dopo il sync.

### `import_playlist(..., prune: bool = False)`

- Default `prune=False` → comportamento attuale invariato (import iniziale e re-import
  non rimuovono nulla).
- `prune=True` → dopo aver applicato gli item, scollega le tracce orfane come sopra e
  conteggia `removed`.
- L'identità di una traccia importata si raccoglie durante il loop (gli `isrc` e
  `platform_track_id` normalizzati), così il prune confronta sullo stesso criterio del
  matching (`_find_existing`).

### Frontend

- Pulsante "Aggiorna da Spotify" nella barra azioni della pagina playlist, mostrato solo
  quando la playlist è sincronizzabile (Spotify con `platform_playlist_id` oppure liked).
- Al click: stato di caricamento, chiamata `POST /api/playlists/{id}/sync`, poi:
  - mostra un `Alert`/riepilogo: es. "3 nuove · 2 rimosse (restano in libreria) · 41 totali",
  - ricarica tracce, dettaglio playlist e gaps.
- Nuova funzione in `frontend/lib/api.ts`: `syncPlaylist(id)`.

## 4. Colorazione tonalità (Camelot)

- Solo frontend. Componente condiviso `KeyBadge` (in `frontend/components/`, es.
  `key-badge.tsx`) che riceve la key Camelot (`1A`…`12B`) e la rende come badge colorato.
- Palette: colore canonico della ruota Camelot (stessa famiglia di colori degli
  screenshot Spotify / Mixed In Key) — 12 tinte (una per numero), con le varianti `A`/`B`
  distinguibili. Mappa esplicita `1A…12B → colore` per controllo preciso.
- Key assente o non valida → badge neutro / trattino (mai inventare la tonalità).
- Usato nella tabella della pagina playlist al posto del testo grigio attuale.
- (La libreria può adottare lo stesso componente in un secondo momento; fuori scope qui,
  ma il componente è condiviso e riutilizzabile.)

## Testing

- Backend (`backend/tests`):
  - `import_playlist(prune=True)` scollega le tracce non più presenti impostando
    `playlist_id=None`/`playlist_name=None` e lasciandole nella tabella `tracks`.
  - `import_playlist(prune=True)` importa le tracce nuove e aggiorna `track_count`.
  - `import_playlist(prune=False)` mantiene il comportamento attuale (nessuna rimozione).
  - Endpoint `POST /api/playlists/{id}/sync`: 404 playlist inesistente, errore per
    playlist manuale, report con `removed` corretto (con Spotify client mockato).
  - `TrackOut` espone `added_at`.
- Frontend: verifica manuale via preview — filtri/ordinamento, rank `#` stabile sotto
  ordinamento per altra colonna, colori key, flusso di sync con report.

## Fuori scope

- Riordino manuale (drag & drop) delle tracce nella playlist.
- Appartenenza di una traccia a più playlist contemporaneamente.
- Sincronizzazione automatica/schedulata (il sync è solo manuale, su richiesta).
- Adozione di `KeyBadge` nella libreria (rinviabile).
