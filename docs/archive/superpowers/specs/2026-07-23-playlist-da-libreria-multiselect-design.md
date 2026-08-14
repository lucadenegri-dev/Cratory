# Playlist da libreria: multi-selezione + filtri, e "Aggiungi a playlist" dal dettaglio traccia

Data: 2026-07-23

## Obiettivo

Potenziare la creazione di playlist da libreria con **selezione multipla / seleziona
tutto** e filtri per **genere** e per **playlist di appartenenza**, e aggiungere nel
**dettaglio traccia** un pulsante per **aggiungere la traccia a una playlist esistente**.

Due esigenze utente:

1. Nella creazione playlist da libreria (modalità `library` di import-manual): poter
   filtrare per genere e/o per un'altra playlist, e selezionare in blocco (multi-select
   con checkbox e "seleziona tutte le corrispondenti") le tracce da mettere nella nuova
   playlist.
2. Nella pagina di dettaglio di una traccia: un bottone, sulla destra, per aggiungere
   quella traccia a una playlist esistente.

## Stato attuale (ricognizione)

- La "creazione playlist da libreria" vive **dentro** `frontend/app/playlists/import-manual/page.tsx`,
  modalità `library`. È un pattern *click-per-aggiungere*: si cerca per testo, si clicca
  un risultato per accodarlo a una lista ordinata `picked`, con riordino per-riga
  (frecce su/giù) e rimozione. Niente checkbox, niente seleziona-tutto. Filtri: solo
  ricerca testo `title` + toggle "solo posseduti" (`has_local_file`). Nessun filtro genere
  né per playlist.
- La pagina Libreria (`frontend/app/library/page.tsx`) ha i filtri ricchi ma nessun
  multi-select e nessuna azione "crea playlist": resta di sola consultazione (scelta
  confermata: la nuova funzionalità va in import-manual).
- Il dettaglio traccia (`frontend/app/tracks/[id]/page.tsx`) ha una sidebar destra
  (marginalia) con il pulsante "Modifica valori" + riepilogo. La metadata card mostra i
  nomi delle playlist a cui la traccia appartiene. Nessuna azione "aggiungi a playlist"
  esiste oggi.
- Backend: esiste `POST /api/playlists/create-from-tracks` (crea una nuova playlist da una
  lista di `track_ids`). **Non** esiste un endpoint per aggiungere tracce a una playlist
  esistente. L'helper `repositories.add_track_to_playlist(db, track, playlist, *,
  added_at=None, added_by=None)` è idempotente (dedup sulla PK composita) e supporta già
  `added_by="cratory"` (le membership Cratory non vengono mai rimosse dal prune del sync).
- `GET /api/tracks` non ha filtro "appartiene a playlist X". `limit=0` significa "tutte".
  `genre` è match `ilike` substring case-insensitive.

## Design

### Backend

**1. Nuovo filtro `in_playlist` su `GET /api/tracks`**

- Nuovo parametro `in_playlist: int | None` sul router `tracks.py`, propagato a
  `repositories.list_tracks` → `_apply_track_filters`.
- Semantica: mostra le tracce **che appartengono** alla playlist indicata:
  `Track.id.in_(select(playlist_tracks.c.track_id).where(playlist_tracks.c.playlist_id == in_playlist))`.
- Combinabile in AND con `genre` e con tutti gli altri filtri esistenti.

**2. Nuovo endpoint `POST /api/playlists/{playlist_id}/add-tracks`**

- Body `PlaylistAddTracksRequest`: `{ track_ids: list[int] (min_length=1) }`.
- Comportamento:
  - Carica la playlist; 404 `playlist_not_found` se assente.
  - Valida che tutti gli id esistano; 422 `tracks_not_found` (con `missing`) altrimenti.
  - Calcola `before` = insieme dei `track_id` già membri della playlist.
  - Per ogni `track_id` (nell'ordine ricevuto): `add_track_to_playlist(db, track,
    playlist, added_at=<now>, added_by="cratory")` (idempotente → i già presenti vengono
    saltati; `added_at` valorizzato così le nuove membership si ordinano dopo le esistenti).
  - `added` = numero di id non presenti in `before` (ed esistenti); `skipped` = quelli già
    presenti.
  - `recount_playlist` + commit + refresh.
- Risposta `PlaylistAddTracksResult`: `{ playlist: PlaylistOut, added: int, skipped: int }`
  → la UI mostra "N aggiunte, M già presenti".
- L'endpoint accetta **qualsiasi** playlist. Perimetro dei selettori nel frontend
  (deciso in verifica, 2026-07-23): il **filtro "per playlist" in libreria elenca TUTTE
  le playlist** (incluse le importate/liked/discovery) — "filtrando per le altre
  playlist" deve funzionare subito con le playlist esistenti dell'utente. Invece i
  **selettori di destinazione "aggiungi a esistente"** (dropdown in import-manual e
  popover nel dettaglio traccia) elencano **solo le playlist `kind="manual"`**: le
  importate restano specchio fedele dello streaming e non si sporcano.

**3. Schemi (`backend/app/schemas.py`)**

- `PlaylistAddTracksRequest`: `track_ids: list[int] = Field(min_length=1)`.
- `PlaylistAddTracksResult`: `playlist: PlaylistOut`, `added: int`, `skipped: int`.

### Frontend

**Client API (`frontend/lib/api/playlists.ts`)**

- `addTracksToPlaylist(playlistId: number, trackIds: number[])` →
  `POST /api/playlists/{id}/add-tracks`, ritorna `PlaylistAddTracksResult`.

**A. Modalità `library` di `import-manual/page.tsx`**

- Il pattern *click-per-aggiungere* + riordino per-riga viene **sostituito** da una
  **lista con checkbox** e uno stato di selezione `Set<number>`.
- **Il riordino per-riga (frecce su/giù) viene rimosso**: con la selezione di massa non ha
  senso; l'ordine di inserimento segue l'ordinamento corrente della lista.
- Barra filtri:
  - ricerca testo `title` (esistente),
  - toggle "solo posseduti" → `has_local_file` (esistente),
  - **genere**: input testo con `datalist` dei generi noti → filtro `genre`,
  - **playlist**: dropdown di **tutte** le playlist (importate/liked/discovery/manuali) →
    filtro `in_playlist` (tracce dentro la playlist scelta).
- **Seleziona tutto**: casella in testata "Seleziona le N corrispondenti" che esegue un
  fetch `GET /api/tracks?...&limit=0` con i filtri correnti e seleziona **tutti** gli id
  risultanti (non solo quelli visibili). Deseleziona-tutto svuota la selezione. Contatore
  "N selezionate" sempre visibile.
- La lista visibile resta paginata (limit ridotto), ma la select-all copre l'intero
  risultato filtrato.
- Azioni sulla selezione:
  - **"Crea playlist"** (campo nome) → `createPlaylistFromTracks(name, [...selected])`, poi
    redirect a `/playlists`.
  - **"Aggiungi a playlist esistente"** → dropdown playlist manuali →
    `addTracksToPlaylist(id, [...selected])`, feedback "N aggiunte, M già presenti".
- Gli id vengono inviati nell'ordine in cui compaiono nella lista filtrata/ordinata.

**B. Dettaglio traccia `tracks/[id]/page.tsx`**

- Nella **sidebar destra (marginalia)**, accanto a "Modifica valori", nuovo pulsante
  **"Aggiungi a playlist"**.
- Apre un popover con l'elenco delle playlist manuali. Ogni riga segnala se la traccia è
  già dentro (da `track.playlists`). Click su una playlist → `addTracksToPlaylist(id,
  [track.id])`, feedback + refresh della traccia (aggiorna la lista "Playlist" nella
  metadata card e lo stato del popover).
- In fondo al popover, voce **"Crea nuova playlist con questa traccia"** (nome →
  `createPlaylistFromTracks(name, [track.id])`).

## Test (TDD)

- Backend (nuovi test, sullo stile di `test_playlist_membership.py` /
  `test_playlist_from_tracks.py`):
  - `add-tracks`: aggiunta tracce nuove (track_count aggiornato, `added_by="cratory"`),
    idempotenza (ri-aggiungere tracce già presenti → `skipped`, nessun duplicato), 404 su
    playlist inesistente, 422 su track id inesistenti, `added`/`skipped` corretti.
  - filtro `in_playlist` su `GET /api/tracks`: ritorna solo le tracce della playlist,
    combinato in AND con `genre`.
- Frontend: verifica manuale via preview (dev server) del flusso multi-select/filtri e del
  popover nel dettaglio; eventuale test unit/e2e leggero se il resto della suite lo rende
  agevole.

## Iterazione 2 (2026-07-23, post-verifica): multi-playlist, pannello, già-presente, conferma

Feedback utente dopo la verifica live. Modifiche additive sullo stesso branch, prima del
merge.

### Backend

- Il filtro `in_playlist` su `GET /api/tracks` diventa **multi-valore**:
  `?in_playlist=1&in_playlist=2` → tracce che appartengono a **una qualsiasi** delle
  playlist indicate (unione). `_apply_track_filters` accetta `in_playlist: list[int] | None`
  e usa `Track.id.in_(select track_id where playlist_id.in_(in_playlist))`. FastAPI
  interpreta un singolo `?in_playlist=8` come lista di uno → retro-compatibile col
  comportamento dell'iterazione 1.

### Frontend — `import-manual` (modalità library)

1. **Filtro playlist multi-selezione**: il `Select` singolo diventa un popover a checkbox
   ("Playlist ▾") con **tutte** le playlist; stato `Set<number>` (`inPlaylists`). La query
   invia `in_playlist` ripetuto. La lista mostra l'unione.
2. **Pannello "Selezionate (N)"** sempre visibile: elenca le tracce raccolte con label e una
   X per rimuoverle singolarmente. La selezione diventa `Map<number, Track>` (id → Track) per
   avere le label anche di tracce non più a video (raccolte con un altro filtro).
   "Seleziona tutte" popola la mappa dall'intero risultato (`limit=0`).
3. **Già presenti nella destinazione**: quando si sceglie una playlist nel target di
   "Aggiungi a esistente", si carica la sua membership (`playlistTracks(targetId)` → set di
   id) e nella lista le tracce già dentro diventano **non-selezionabili** con badge
   **"già presente"**, escluse anche dal seleziona-tutto.
4. **Conferma evidente**: il messaggio "N aggiunte, M già presenti" è ben visibile vicino ai
   pulsanti d'azione; dopo l'ADD si **ricarica la membership del target**, così le tracce
   appena aggiunte passano a "già presente" a vista (conferma visiva).

### Frontend — popover dettaglio traccia

- Dopo add/create, riga di **conferma** transitoria ("Aggiunta a {nome}" / "Creata {nome}")
  oltre allo spunto sulla riga già esistente.

### Test (iterazione 2)

- Backend: `in_playlist` multi-valore → unione di due playlist; il caso singolo resta verde.
- Frontend: verifica live via preview (multi-filtro, pannello, già-presente, conferma).

## Note e vincoli

- Nessuna modifica ai file audio: le playlist restano metadati; tag di competenza di
  Sortory (regola non negoziabile). L'aggiunta a playlist tocca solo `playlist_tracks`.
- Le nuove membership usano `added_by="cratory"` per essere protette dal prune del sync,
  coerentemente con Discovery.
- Fuori scope: multi-selezione/creazione playlist dalla pagina Libreria (resta di
  consultazione); ordinamento persistito delle tracce in playlist (non esiste una colonna
  posizione: l'ordine di recupero è per `added_at`).
