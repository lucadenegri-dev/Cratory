# Import selettivo dei Liked Spotify

Data: 2026-07-09

## Problema

I brani "piaciuti" (liked / saved tracks) su Spotify sono generalmente tantissimi
(potenzialmente migliaia). L'import attuale è tutto-o-niente: `POST /api/playlists/import`
con `playlist_id="liked"` scarica *tutti* i liked e li mette nella playlist `kind="liked"`.

L'utente vuole poter **scegliere** quali brani importare, sia al primo import sia in
aggiornamenti successivi, aggiungendone altri alla stessa playlist.

## Obiettivo

La playlist Liked diventa un **sottoinsieme curato**: cresce solo con i brani che
l'utente seleziona, in modo **additivo** (nessun prune automatico).

## Decisioni di design

- **Lista selezione:** carico tutti i liked in un colpo, con casella di ricerca/filtro
  client-side (per artista/titolo).
- **Aggiornamento:** mostro *tutti* i liked; quelli già nella playlist appaiono spuntati
  e disabilitati (non ri-selezionabili né rimuovibili da qui).
- **Additiva, niente prune.** Per la playlist Liked non si usa il `sync` con `prune=True`.
- **Nome playlist:** "Liked Spotify".
- **UI:** pagina dedicata (non modale), per reggere migliaia di righe + ricerca.

## Backend

### a) Anteprima liked — `GET /api/playlists/spotify/liked/preview`

Scarica tutti i liked (`SpotifyWebClient.get_liked_tracks()`, già pagina tutto), li
restituisce **senza importarli**, ognuno marcato se già presente nella playlist Liked
locale.

Risposta: `list[LikedTrackPreview]`
```
{ spotify_id: str, isrc: str | None, title: str, artist: str,
  duration_ms: int | None, artwork_url: str | None, already_imported: bool }
```

`already_imported` si calcola confrontando ogni item con le tracce già linkate alla
playlist `kind="liked"`, riusando la logica di dedup esistente (`isrc → platform_track_id
→ spotify_id`, come `_find_existing()` in `services/playlist_import.py`).

### b) Import selettivo — `POST /api/playlists/import/liked/selected`

Body: `{ spotify_ids: string[] }`.
Scarica i liked, tiene solo gli item il cui `spotify_id` è tra i selezionati, chiama
`import_playlist(..., name="Liked Spotify", kind="liked", prune=False)`. Additivo.

Risposta: `PlaylistImportReport` (invariato).

### Bug fix: playlist liked duplicata

Oggi la playlist liked ha `platform_playlist_id=None`, quindi l'upsert in `import_playlist`
non ritrova quella esistente e ne creerebbe una duplicata a ogni import. La ricerca della
playlist liked va fatta per `kind="liked"` (+ `platform`) invece che per
`platform_playlist_id`.

## Frontend

### Nuova rotta `/playlists/import-spotify/liked` (`ImportLikedPage`)

- Al load: `previewLikedTracks()` → mostra contatore ("N liked, M già importati").
- Lista scrollabile con **ricerca** (filtra client-side per artista/titolo).
- Riga: checkbox + titolo/artista/durata; artwork opzionale. `already_imported` →
  checkbox spuntato + disabilitato.
- Azioni: "Seleziona tutti i visibili" / "Deseleziona"; bottone
  **"Importa selezionati (N)"** → `importSelectedLikedTracks(ids)` → redirect `/playlists`.
- **Performance:** renderizzo solo le righe *filtrate* e cappo le righe visibili
  (es. 300) con avviso "affina la ricerca". Evita di montare migliaia di nodi DOM.

### Punti d'ingresso

- Bottone **"Liked"** in `import-spotify/page.tsx`: non fa più import istantaneo →
  naviga a `/playlists/import-spotify/liked`.
- Dettaglio playlist `[id]/page.tsx`: per `kind="liked"` il bottone "Aggiorna" diventa
  **"Aggiungi altri"** → stessa pagina. Il `sync` con prune resta per le playlist normali.

### Helper in `lib/api.ts`

- `previewLikedTracks(): Promise<LikedTrackPreview[]>`
- `importSelectedLikedTracks(spotifyIds: string[]): Promise<PlaylistImportReport>`

## Dati / flusso

Nessuna modifica al modello. La playlist `kind="liked"` esiste già; cambia solo *come*
viene popolata (sottoinsieme scelto, additivo). Dedup, `_apply_fields`, transizione
`ready_for_set` invariati.

## Test

Backend:
- preview marca `already_imported` correttamente (match ISRC / platform_track_id / spotify_id);
- import selettivo importa solo i `spotify_ids` passati;
- re-import non duplica la playlist liked (bug fix);
- `prune=False`: nulla viene rimosso.

Frontend:
- filtro ricerca;
- checkbox disabilitato per i già-importati;
- conteggio nel bottone import.
