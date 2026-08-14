# Espansione playlist nel contesto Playlist + add con write-back Spotify

Data: 2026-06-28
Stato: design approvato, pronto per il piano di implementazione.

## Obiettivo

Spostare la funzione "Espandi playlist" da Discovery al contesto **Playlist**,
lanciandola dal dettaglio della playlist. Discovery resta una cosa sola: **crate
digging (DIG)**. L'azione "Aggiungi" di un suggerimento expand **aggiunge il brano a
quella playlist** (non solo alla libreria) e, dove possibile, **propaga l'aggiunta
anche sulla playlist Spotify** (i candidati expand sono gia' risolti su Spotify).

## Motivazione

Oggi l'expand vive in Discovery e costringe a **riselezionare la playlist** in un menu,
anche quando si arriva dal suo dettaglio (il bottone "Scopri musica simile" in
`playlists/[id]/page.tsx` linka al Discovery generico). Spostarlo nel contesto playlist
elimina il doppio passaggio e dà a Discovery un solo scopo (DIG). L'endpoint
`/api/discovery/expand` lavora già "per playlist": il cuore del cambio è IA/frontend,
più un nuovo endpoint backend per l'add mirato + write-back.

## Vincoli (regole del progetto)

- Motore deterministico / AI separati: l'expand resta deterministico; l'AI solo per le
  spiegazioni, opzionale.
- Non si inventano dati: i candidati sono risolti via Spotify resolver (identità/ISRC),
  nessuna feature di mixing toccata.
- Spotify è fonte di identità/metadata; qui lo usiamo anche come **destinazione di
  scrittura** della playlist (scope già concessi), non come fonte di feature.
- Stile commit: nessun trailer `Co-Authored-By`.

## Componenti

### Frontend

**1. Nuova route `frontend/app/playlists/[id]/expand/page.tsx`**

- Carica la playlist (id dalla route) e mostra un header minimo: nome playlist + link
  "← torna alla playlist" (`/playlists/[id]`).
- **Autorun al caricamento, SENZA AI**: esegue l'expand una volta appena la pagina è
  pronta, con `use_ai=false`.
- Barra controlli: toggle "Spiega con l'AI" (default **off**; disabilitato se l'AI non è
  configurata) + bottone "Ricalcola" che ri-esegue l'expand con le impostazioni
  correnti.
- Stato/Errori: se Last.fm non è configurato, mostra lo stesso Alert informativo di
  oggi. Se la playlist non esiste → messaggio + link indietro.
- Rende i risultati riusando i componenti spostati (`Results`/`CandidateRow`).

**2. `components/expand-results.tsx` (componente condiviso, nuovo)**

- Sposta qui da `app/discovery/page.tsx`: `Results`, `CandidateRow`, la costante
  `SOURCE_LABEL` e la logica di "add". Esporta `ExpandResults` usato dalla nuova pagina.
- `CandidateRow` riceve l'`playlistId` corrente: l'azione "Aggiungi" chiama il nuovo
  endpoint playlist-scoped (vedi backend), non più `discoveryAddToLibrary`.
- Dopo un add riuscito mostra "Aggiunto" (stato per-riga, come oggi). Se il write-back
  Spotify è avvenuto, lo indica (es. micro-nota "anche su Spotify"); se è fallito ma
  l'add locale è ok, mostra l'add come riuscito con una nota discreta.

**3. Discovery diventa solo DIG (`app/discovery/page.tsx`)**

- Rimuove il mode switcher (DIG | Espandi) e il ramo `mode === "expand"`.
- Rimuove lo stato/handler ora inutilizzati: `mode`, `result`, `playlistId`, `useAi`,
  `aiEnabled`, `runExpand`, `noPlaylists`, `expandReady`, e gli import non più usati
  (`discoverExpand`, `Wand2`, `Checkbox`, `Field`, `DiscoveryResponse`, ecc.).
- `playlists` resta solo per il selettore "Affinità rispetto a" del dig.
- La pagina parte direttamente sui controlli DIG (niente switcher).

**4. Bottone nel dettaglio playlist (`app/playlists/[id]/page.tsx`)**

- "Scopri musica simile" → `Link href={`/playlists/${pid}/expand`}` (al posto di
  `/discovery`).

### Backend

**5. Nuovo endpoint `POST /api/playlists/{playlist_id}/discovered-tracks`**

(router `app/routers/playlists.py`)

- Body: come `DiscoveryAddRequest` (artist, title, spotify_id, isrc, duration_seconds,
  url, album_art_url).
- Logica:
  1. `import_single_track(...)` → `(track, created)` (idempotente; non attacca a
     playlist di suo).
  2. **Attacca alla playlist**: se `track.playlist_id is None` → `track.playlist_id =
     playlist_id`. Se la traccia esiste già sotto un'altra playlist (modello 1:1) →
     **non spostarla** (lascia la membership), ma procedi comunque al write-back.
  3. **Write-back Spotify** (best-effort), se *tutte* le condizioni valgono:
     `playlist.platform == "spotify"`, `playlist.platform_playlist_id` presente,
     `req.spotify_id` presente, token utente disponibile → `client.add_tracks(
     playlist.platform_playlist_id, [req.spotify_id])`. Errori catturati: non fanno
     fallire l'add locale; finiscono in `spotify_error`.
  4. Aggiorna `playlist.track_count` se la traccia è stata effettivamente aggiunta alla
     playlist locale.
- Risposta `PlaylistAddTrackResponse`: `{ created: bool, track: TrackOut,
  spotify_added: bool, spotify_error: str | None }`.

**6. Nuovo metodo `SpotifyWebClient.add_tracks(playlist_id, track_ids)`**

(`app/integrations/spotify.py`)

```text
uris = [f"spotify:track:{tid}" for tid in track_ids]
for chunk of 100: POST /playlists/{playlist_id}/tracks  (user=True)  json={"uris": chunk}
```

Stesso pattern già usato da `create_playlist`. Usato solo dal nuovo endpoint.

**7. Schema** (`app/schemas.py`)

- `PlaylistAddTrackRequest` (o riuso di `DiscoveryAddRequest`): campi artist/title/
  spotify_id/isrc/duration_seconds/url/album_art_url.
- `PlaylistAddTrackResponse`: `created: bool`, `track: TrackOut`, `spotify_added: bool`,
  `spotify_error: str | None`.

### Frontend API client

**8. `frontend/lib/api.ts`**

- `addDiscoveredTrackToPlaylist(playlistId, candidate)` → `POST
  /api/playlists/{id}/discovered-tracks`; tipo di risposta `PlaylistAddTrackResponse`.
- `discoverExpand` resta (lo usa la nuova pagina). `discoveryAddToLibrary` resta in API
  ma non più usato dall'expand (eventuale pulizia se diventa orfano).

## Matrice write-back

| Caso | Add locale (playlist) | Write-back Spotify |
|---|---|---|
| Playlist Spotify posseduta (`platform_playlist_id`) + candidato risolto + token utente | sì | sì |
| Playlist manuale (no `platform_playlist_id`) | sì | no (no-op) |
| Playlist "liked" / candidato non risolto / token assente | sì | no (no-op) |

Il no-op non è errore: `spotify_added=false`, `spotify_error=null`.

## Dedup

- Spotify: best-effort via stato UI ("Aggiunto" per riga) per evitare doppi click. Non
  si aggiunge un controllo di rete per duplicati cross-sessione (basso rischio); lo si
  documenta.
- Locale: idempotenza già garantita da `import_single_track` (per platform_track_id /
  ISRC / nome).

## Testing

Backend (stile del progetto: chiamata diretta al router + fixture `db`, dipendenze
finte):

- add a playlist Spotify posseduta: la traccia entra in libreria con `playlist_id`
  corretto e `add_tracks` viene chiamato con `[spotify_id]`; risposta
  `spotify_added=true`.
- add a playlist manuale: `playlist_id` settato, `add_tracks` **non** chiamato,
  `spotify_added=false`.
- candidato non risolto (no `spotify_id`): solo locale, `spotify_added=false`.
- errore Spotify (mock che solleva): add locale riuscito, `spotify_added=false`,
  `spotify_error` valorizzato.
- traccia già sotto altra playlist (1:1): membership non spostata; (se applicabile)
  write-back comunque tentato.
- `track_count` aggiornato quando la traccia viene aggiunta.

Frontend: lint + build; verifica browser della nuova pagina (autorun senza AI, add con
nota write-back) e del Discovery ridotto a solo DIG.

## Fuori scope

- Many-to-many playlist (`playlist_tracks`): resta backlog; qui si convive col 1:1.
- "Salva nei Liked" di Spotify (endpoint `/me/tracks`): non incluso.
- Controllo di rete per i duplicati Spotify cross-sessione.
- Spiegazioni AI di default (restano opzionali, off all'autorun).

## Decisioni consolidate

- Discovery = solo DIG; expand vive nel dettaglio playlist (pagina dedicata
  `/playlists/[id]/expand`).
- Autorun dell'expand senza AI; AI opzionale via toggle + Ricalcola.
- "Aggiungi" → aggiunge alla playlist locale e, dove possibile, scrive sulla playlist
  Spotify; mai bloccante se il write-back fallisce.
- Edge 1:1: non spostare una traccia già appartenente ad altra playlist; write-back
  comunque tentato.
