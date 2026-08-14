# Import playlist e like da SoundCloud — Design

Data: 2026-07-09
Stato: approvato (brainstorming con Luca)

## Obiettivo

Importare in Cratory, come lead di libreria, i metadati di playlist SoundCloud
(pubbliche e private via secret link) e dei like dell'utente. Solo metadati:
nessun audio, mai. BPM/key restano da Rekordbox; la pulizia dei metadati oltre
la normalizzazione da import resta a Sortory.

## Contesto e vincoli

- L'API ufficiale SoundCloud richiede un abbonamento Artist Pro attivo per
  generare credenziali. Decisione: non pagarlo ora; usare **yt-dlp in modalità
  solo-metadati** come fetcher provvisorio, dietro l'interfaccia
  `integrations/`, così un eventuale passaggio all'API ufficiale sostituisce
  solo il client interno.
- yt-dlp non rispetta i ToS SoundCloud: rischio accettato per uso personale
  mono-utente; failure mode noto = "smette di funzionare finché non si
  aggiorna yt-dlp".
- L'API pubblica (ufficiale o meno) non espone l'ISRC: la dedup atterra su
  `platform_track_id` e poi sul fuzzy artist+title.

## Decisioni prese

1. **Entry point (opzione B)**: campo incolla-URL nella sezione Playlists
   (playlist pubbliche e secret link) + username SoundCloud configurato in
   Settings, che abilita il pulsante "I miei like".
2. **Like (opzione B)**: preview selettiva con checkbox, come i liked Spotify.
3. **Sync (opzione B)**: solo additivo, mai prune per SoundCloud — un takedown
   sulla piattaforma non deve togliere la membership di un lead valido.
4. **Metadati (opzione A)**: split deterministico del titolo alla prima
   occorrenza di `" - "` (sinistra = artist, destra = title); fallback
   artist = username uploader. È normalizzazione da import (competenza
   Cratory), non enrichment (competenza Sortory).
5. **Integrazione yt-dlp (approccio 1)**: pacchetto pip nel venv, usato via
   API Python (`extract_flat="in_playlist"`, `socket_timeout`), versione
   pinnata in requirements. Niente subprocess, niente client api-v2 fatto in
   casa.

## Architettura

Nuovo codice piattaforma-specifico in tre punti; il core di import non cambia.

### `backend/app/integrations/soundcloud.py` (nuovo)

Client yt-dlp via API Python. Espone:

- `fetch_playlist(url) -> dict` — metadati playlist + entries flat.
- `fetch_likes(username, limit) -> dict` — costruisce
  `https://soundcloud.com/{username}/likes` e delega allo stesso fetch.
- `SoundCloudError` — incapsula gli errori yt-dlp (come `SpotifyError`).

Fetch sequenziali, nessun parallelismo (profilo basso su API non ufficiale).

### `normalize_soundcloud_item` in `services/playlist_import.py`

Entry flat yt-dlp -> `NormalizedTrack`, accanto a `normalize_spotify_item`.
Il motore `import_playlist` esistente (callback `normalize`, kind `liked`,
idempotenza) fa il resto senza modifiche.

Mapping:

- `platform="soundcloud"`, `platform_track_id` = id yt-dlp (stringa),
  `url` = permalink, `isrc=None`.
- Titolo: split alla prima `" - "` -> artist/title; senza separatore ->
  title intero, artist = uploader.
- `duration_seconds` dalla duration yt-dlp; `artwork_url` se presente,
  altrimenti `None`; `added_at`, `album`, `year` = `None` (non disponibili
  in flat mode).

### `backend/app/routers/soundcloud.py` (nuovo, gemello di `spotify.py`)

Endpoint sotto `/api/soundcloud/`:

- `GET /status` — username configurato + disponibilità/versione yt-dlp.
- `PUT /config` — salva `soundcloud_username` in `AppState`.
- `POST /import` `{url}` -> `PlaylistImportReport`. Playlist pubbliche e
  secret link, stesso flusso. Un URL `/likes` incollato qui risponde 422
  con l'indicazione di usare il flusso like.
- `GET /likes/preview?limit=` — like recenti (default limit 100) con flag
  già-importata.
- `POST /import/likes` `{track_ids}` — il backend rifà il fetch dei like e
  importa solo gli id selezionati (stateless, nessuna cache server-side).

### Playlist e identità

- Playlist: `platform_playlist_id` = id yt-dlp -> re-import dello stesso URL
  aggiorna la stessa playlist (idempotente). `url` salvato, secret link
  incluso (resta solo nel DB locale).
- Like: `kind="liked"`, nome "SoundCloud Likes", ritrovata per `kind` come i
  liked Spotify (nessun `platform_playlist_id`).
- Dedup cascata invariata: `platform_track_id` -> fuzzy artist+title
  (l'ISRC manca sempre).

### Sync

`POST /api/playlists/{id}/sync` diventa un dispatch per piattaforma:

- Spotify: comportamento attuale, `prune=True`.
- SoundCloud: re-fetch dell'`url` salvato via yt-dlp, `prune=False`.

## Error handling

- `SoundCloudError` mappato su HTTP: 422 per input invalido (URL malformato,
  playlist privata senza secret token), 502 per problemi remoti (rete,
  estrazione fallita).
- Estrazione rotta (SoundCloud ha cambiato qualcosa): il messaggio d'errore
  suggerisce esplicitamente di aggiornare yt-dlp; `GET /status` mostra la
  versione installata.

## Frontend

- **Playlists**: nuova voce "Importa da SoundCloud" -> pagina
  `playlists/import-soundcloud` con campo URL + report esito (pattern
  `import-manual`). Con username configurato, pulsante "I miei like" ->
  vista preview con checkbox (pattern liked Spotify).
- **Settings**: campo "Username SoundCloud".
- `lib/api.ts`: funzioni per i nuovi endpoint.

## Testing

- Unit su `normalize_soundcloud_item`: split con/senza separatore, trattini
  multipli (split solo sulla prima occorrenza), campi mancanti, fallback
  uploader.
- Servizio/router con yt-dlp mockato su fixture JSON di entries flat
  realistiche; mai rete nei test.
- Sync: playlist soundcloud -> nessun prune; spotify -> prune invariato.

## Fuori scope

- Audio in ogni forma (download, streaming, playback).
- BPM/key (Rekordbox) e pulizia metadati oltre lo split (Sortory).
- OAuth ufficiale Artist Pro (sostituirebbe solo `integrations/soundcloud.py`).
- Listing delle playlist pubbliche per username (possibile slice futura).
- Prune per SoundCloud.
