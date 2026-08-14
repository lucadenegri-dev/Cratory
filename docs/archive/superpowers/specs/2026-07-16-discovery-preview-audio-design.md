# Discovery — preview audio dei dischi (iTunes + fallback YouTube)

Data: 2026-07-16
Stato: design approvato, pronto per il piano di implementazione.

## Obiettivo

Aggiungere una **preview audio** ai dischi proposti dalla modalità **Scava/dig**
(Discogs) del Discovery, sia sulla **card della griglia** (assaggio del disco) sia
**per singola traccia** nel pannello tracklist. La preview è a **doppia sorgente con
fallback**: iTunes Search API (clip 30s, pulita) quando disponibile, altrimenti il
video YouTube che Discogs già associa alla release. Copertura reale misurata: ~75%
delle tracce deep-cut (iTunes 39% + fallback YouTube che porta l'unione al 75%).

## Motivazione ed eccezione al principio "no audio"

Cratory dichiara *"The app does not play audio"* (`docs/ARCHITECTURE.md:30`,
`CLAUDE.md`). Una preview in Discovery è, letteralmente, riprodurre audio: è quindi
una **eccezione dichiarata**, nello stesso spirito delle eccezioni già esistenti
(Shazam scarica audio temporaneo per il fingerprinting; Soulseek acquisisce file
persistenti). La natura dell'eccezione: **riproduzione effimera di audio di terzi
per valutare un lead prima di acquisirlo**. Non si scarica, non si conserva, non si
riproduce nulla della libreria — si streamma da iTunes/YouTube e si scarta.

Perché doppia sorgente. Misurazione empirica su 61 tracce reali da vinili Discogs
(house/techno/disco/breakbeat):

| Sorgente | Copertura | Note |
|---|---|---|
| iTunes Search API | 39% | clip 30s AAC, no auth, **no pubblicità** |
| Video YouTube (da Discogs) | 69% | traccia intera, **con pubblicità** + zona grigia ToS |
| Unione (iTunes + fallback YT) | **75%** | pulito dove possibile, ripiego dove serve |
| Nessuna delle due | 25% | catalogo assente ovunque |

Il paradosso: proprio i deep-cut rari (il cuore del crate digging) sono assenti da
iTunes ma presenti su YouTube, perché caricati dai collezionisti. iTunes-only
lascerebbe muta la maggioranza delle tracce; l'unione recupera i tre quarti.

## Vincoli e decisioni prese

- **iTunes è primario, YouTube è fallback.** Per una traccia si tenta prima iTunes
  (pulito); solo se manca si cerca un video YouTube nella release.
- **Player unico ancorato in basso a destra.** Non ci sono mini-player inline nelle
  card/righe: c'è **un solo player floating**, `position: fixed` in basso a destra
  della pagina Scava (come il player video di discogs.com). I pulsanti play su card e
  tracklist si limitano a impostare l'item attivo; il player docked lo riproduce.
  Mostra titolo/artista dell'item corrente ed è chiudibile.
- **Player differenziato per sorgente** (risolve il problema pubblicità), sempre
  dentro il riquadro docked in basso a destra:
  - iTunes → **barra audio nostra** (`<audio>` nativo, play/pausa + progress 30s).
  - YouTube → **mini-player video visibile** (iframe compatto ~16:9, appare solo al
    play) così l'eventuale annuncio è **saltabile**. Niente player audio-only
    nascosto proprio dove ci sono gli ads.
- **Risoluzione lazy, on-demand.** Nessun pre-fetch: la preview si risolve solo al
  click su play, per non martellare iTunes/Discogs su ogni disco visibile e restare
  nei rate-limit.
- **Un solo player attivo alla volta** a livello di pagina Scava: premere play
  altrove ferma il corrente.
- **Nessuna persistenza.** I lead non sono ancora `Track`: la risoluzione è effimera,
  con sola cache in-memory a TTL per evitare query ripetute sullo stesso item.
- **Niente Deezer, niente Spotify.** Scelte esplicitamente escluse.

## Architettura

```
[Card griglia] play ─┐
                     ├─► GET /api/discovery/preview?artist=&title=&discogs_id=
[Riga tracklist] play┘         │
                               ▼
                   services/preview.resolve_preview()
                     1. iTunes search(artist, title) → previewUrl 30s? ─► kind="itunes"
                     2. altrimenti video YouTube della release (fuzzy match titolo)
                                                                       ─► kind="youtube"
                     3. altrimenti                                     ─► kind="none"
                               │
                               ▼
        { kind, audio_url?, youtube_video_id?, source_url?, matched_title? }
```

- La **card** (da `search_releases`) non contiene la tracklist né i video → per il
  fallback YouTube serve un `get_release(discogs_id)` on-click, messo in cache; la
  preview della card usa `artist + titolo release`. Non essendoci una traccia
  specifica, il fallback YouTube a livello release prende il **primo video** della
  release (nessun match di titolo da fare).
- La **riga tracklist** è già dentro il dettaglio (i video della release sono già
  caricati) → preview con `artist + titolo traccia`; il fallback YouTube fa il
  **fuzzy match** del titolo traccia sui video della release.

Per distinguere i due casi, `resolve_preview` accetta un flag/parametro implicito:
se `title` è il titolo della release (card) il fallback prende il primo video; se è
una traccia (tracklist) fa il match. In pratica l'endpoint riceve sempre
`artist`/`title`/`discogs_id`; la distinzione card-vs-traccia si modella con un
parametro esplicito `level=release|track` (default `track`).

## Backend

### Nuovo mini-client `integrations/itunes.py`
- `search_preview(artist: str, title: str) -> ItunesHit | None`.
- GET pubblica `https://itunes.apple.com/search?term=<artist title>&media=music&entity=song&limit=5`,
  **nessuna auth, nessun token**. Segue lo stile `ClosableHttpClient`/`get_json` degli
  altri client, con gestione errore/rate-limit e `httpx` iniettabile per i test.
- Ritorna `preview_url`, `track_name`, `artist_name`, `source_url` (`trackViewUrl`).
- Match: normalizzazione leggera (lowercase, rimozione di `(...)`/`[...]`,
  `feat./remix/edit/version/original/mix`, punteggiatura) e verifica che i token del
  titolo cercato siano coperti almeno a metà dal `trackName` del risultato; scarta i
  risultati senza `previewUrl`. Prende il primo risultato che passa il match.

### Estrazione video da Discogs
- In `serializers`/`services` esporre i `videos[]` già presenti nel payload di
  `get_release` (oggi scartati). Parsing del video-id YouTube da `uri`
  (`watch?v=…` / `youtu.be/…`). Esporli in `DiscogsReleaseOut` come lista
  `{ youtube_video_id, title, duration_seconds }`.
- Match video↔traccia: stessa normalizzazione di iTunes; un video "copre" la traccia
  se i token del titolo traccia sono contenuti a metà nel titolo del video.

### Nuovo service `services/preview.py`
- `resolve_preview(artist, title, discogs_id=None, level="track") -> PreviewResult`
  applica la catena iTunes → video Discogs → none. Con `level="release"` il fallback
  YouTube prende il primo video; con `level="track"` fa il fuzzy match del titolo.
- Per il fallback recupera i `videos` via `get_release(discogs_id)` (già usato
  altrove), con **cache in-memory TTL** perché lo stesso disco può essere interrogato
  più volte (card + più tracce).
- Ordine: iTunes prima (pulito). Se `matched_title` iTunes esiste → `kind="itunes"`.

### Endpoint `routers/discovery.py`
- `GET /api/discovery/preview` con query `artist`, `title`, opzionale `discogs_id`,
  opzionale `level` (`release`|`track`, default `track`). Ephemeral, nessuna
  scrittura. Errori iTunes/Discogs → degradano a `kind="none"`, mai 500 grezzo
  (coerente con la gestione `DiscogsError` esistente).

### Schema `schemas.py`
```
DiscoveryPreviewOut {
  kind: "itunes" | "youtube" | "none"
  audio_url: str | None          # mp3/m4a iTunes (kind=itunes)
  youtube_video_id: str | None   # id per l'embed (kind=youtube)
  source_url: str | None         # pagina iTunes/YouTube per "apri fuori"
  matched_title: str | None      # cosa ha effettivamente agganciato
}
```

## Frontend

- **`components/preview-player.tsx`** — **player docked** unico, `position: fixed` in
  basso a destra della pagina Scava. Stato dell'item attivo tenuto in un context/store
  a livello pagina; impostare un nuovo item ferma e sostituisce il precedente
  (garantisce "uno alla volta"). Header con titolo/artista dell'item e pulsante
  chiudi. Due rese secondo `kind`:
  - `itunes`: `<audio>` nativo + barra compatta (play/pausa, progress 30s), stile
    design system.
  - `youtube`: iframe YouTube compatto ~16:9 che appare solo al play (annuncio
    saltabile). Un solo iframe montato alla volta.
  - Stato: `idle | loading | playing | unavailable`. In `idle` il riquadro è nascosto.
- **`components/discovery-lead-grid.tsx`** (`LeadCell`): pulsante play in overlay sulla
  thumb → imposta l'item attivo (`artist`, titolo release, `discogs_id`, `level=release`),
  che il player docked risolve via `discoveryPreview(...)`.
- **`components/discovery-tracklist-panel.tsx`** (`TrackRow`): pulsante play accanto a
  "per dopo"/"scarica" → imposta l'item attivo (`artist`, titolo traccia, `discogs_id`,
  `level=track`).
- **Client API**: nuova `discoveryPreview(...)` accanto a `discoveryDig`.
- Stati UI: spinner in `loading`; play/pausa in `playing`; icona disabilitata +
  tooltip "nessuna anteprima" in `unavailable` (`kind:"none"`). i18n IT/EN per le
  nuove stringhe.

## Testing

- Backend:
  - unit `integrations/itunes.py` con `httpx` mockato: hit con match, hit senza
    `previewUrl` scartato, nessun risultato, match negativo per titolo diverso.
  - unit `resolve_preview`: iTunes hit → `itunes`; iTunes miss + video match →
    `youtube`; entrambi miss → `none`; errore Discogs → `none` (no raise).
  - test parsing video-id da `uri` (`watch?v=`, `youtu.be/`, con query extra).
  - test endpoint `GET /api/discovery/preview` (200 con payload, degradazione a
    `none`).
- Frontend (`test:unit`): player un-solo-attivo (play su B ferma A); transizioni di
  stato; resa differenziata itunes vs youtube; stato `unavailable`.

## Documentazione da aggiornare

- `docs/ARCHITECTURE.md:30` e `CLAUDE.md`: dichiarare l'eccezione "preview audio
  effimera di terzi nel Discovery" accanto a Shazam/Soulseek.
- `docs/API.md`: nuovo endpoint `GET /api/discovery/preview` e i campi `videos` in
  `DiscogsReleaseOut`.
- `docs/DEPENDENCIES.md`: iTunes Search API come servizio esterno (pubblico, no auth,
  solo Discovery preview); nota sul fallback YouTube-embed e la relativa zona grigia
  ToS accettata per uso personale/self-hosted.

## Fuori scope (YAGNI)

- Nessun pre-fetch/prefetch delle preview sulle card visibili.
- Nessuna preview nella modalità **Expand** (Last.fm+Spotify): solo Scava/dig.
- Nessuna persistenza dell'URL di preview sul `Track`.
- Niente Deezer, niente Spotify embed.
- Nessun tentativo di risolvere le tracce nel 25% scoperto da nessuna sorgente.
