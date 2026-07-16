# Player audio delle tracce possedute (audizione rapida)

Data: 2026-07-16
Stato: design approvato, in attesa di piano di implementazione.

## Contesto e cambio di rotta

Il CLAUDE.md dichiara come regola non-negoziabile che *"the project does not play
audio"*, con sole eccezioni effimere (Shazam per il fingerprint, preview di terzi in
Discovery via iTunes/YouTube). Questa feature introduce una **nuova capacità
deliberata**: riprodurre in-app le tracce che l'utente **possiede su disco**
(`has_local_file=true`), per audizione rapida.

È coerente con il principio *"the library is the disk"*: si tratta di **sola lettura**
del file, nessuna mutazione (i tag restano compito di Sortory). Il cambio di rotta va
recepito nei docs (vedi §6), ma con l'ordine deciso dall'utente: **codice prima, docs
dopo** — i docs non vengono saltati, si allineano al termine dell'implementazione.

Scelte di prodotto fissate in brainstorming:

- **Scopo**: audizione rapida — play/pausa/seek di **una traccia per volta**. Niente
  coda, niente waveform, niente cue (YAGNI).
- **Dove**: **ovunque compaia una riga-traccia** con file locale → componente play
  riusabile.
- **Formati**: **stream raw, nessuna transcodifica**. I formati non riproducibili dal
  browser (es. AIFF su Chrome) mostrano un messaggio; non aggiungiamo ffmpeg.
- **Player unico**: la barra docked è **una sola**, condivisa tra preview di Discovery
  (terzi) e tracce locali (possedute). Mutua esclusività naturale: una sola sorgente
  audio attiva alla volta.

## 1. Backend — endpoint di streaming

Nuovo endpoint, che rispecchia la convenzione già esistente `/api/tracks/{id}/cover`
(`backend/app/routers/tracks.py:82`, funzione `get_track_cover`):

```
GET /api/tracks/{track_id}/audio
```

Comportamento:

1. Risolve il `Track` per id. `404 track_not_found` se non esiste.
2. Verifica `has_local_file` e `local_path` valorizzato. `404 track_no_local_file`
   altrimenti.
3. **Sicurezza (difesa in profondità)**: risolve `Path(local_path).resolve()` e verifica
   che sia contenuto in una delle root consentite restituite da
   `file_search.search_roots()` (`library` + `downloads`). Se il path risolto esce dalle
   root (symlink/traversal) → `404 track_file_not_allowed`. Il path non è mai preso da
   input utente (solo `track_id`), ma il controllo resta esplicito.
4. Verifica che il file esista ancora su disco. `404 track_file_missing` altrimenti.
5. Restituisce **`starlette.responses.FileResponse`** puntando al path. `FileResponse`
   gestisce **nativamente le HTTP Range request** → seek gratuito, streaming a chunk,
   `Content-Type` dedotto dall'estensione. **Solo lettura**, il file non viene mai
   mutato.

Note:

- `FileResponse` risponde `206 Partial Content` alle richieste con header `Range` e
  `200` a quelle complete: entrambe verificate nei test.
- Nessuna nuova dipendenza. Nessuna cache-header particolare necessaria (file locale).
- La logica di validazione (punti 1–4) va in un piccolo helper deterministico
  riutilizzabile — es. `resolve_playable_path(track) -> Path` in un service — così è
  testabile in isolamento e non gonfia il router. Da valutare se collocarlo accanto a
  `file_search` (condivide `search_roots`).

## 2. Frontend — player unico condiviso (refactor del preview)

Oggi esistono, montati **solo** in `app/discovery/page.tsx`:

- `lib/preview-player.tsx` → `PreviewPlayerProvider` + `usePreviewPlayer` (context che
  tiene la preview attiva di terzi, con fetch async e race-guard `reqId`).
- `components/docked-preview-player.tsx` → barra docked che renderizza `<audio>` iTunes o
  iframe YouTube.

Il player unico generalizza questo materiale in un **context di riproduzione unico** a
livello di **app shell** (root layout / `EditorialShell`), così è raggiungibile da
qualunque pagina.

### 2.1 Context generico

Rinominare/generalizzare `preview-player.tsx` in un provider di riproduzione con una
**sorgente discriminata**:

```ts
type PlaybackSource =
  | { kind: "discovery-preview"; item: PreviewItem }   // terzi: iTunes/YouTube via API
  | { kind: "local-track"; track: { id: number; title: string; artist: string } };
```

- Stato: `active: PlaybackSource | null`, `status`, più i dati specifici del preview
  (`data: DiscoveryPreview | null`, usati solo per `discovery-preview`).
- `play(source)` imposta la sorgente attiva; se è `discovery-preview` esegue la fetch
  async esistente (con il race-guard `reqId`), se è `local-track` non serve fetch (lo
  stream è diretto).
- `stop()` azzera. **Mutua esclusività**: dato che `active` è una sola sorgente,
  chiamare `play` su una nuova sorgente sostituisce la precedente → non possono suonare
  insieme. Il singolo elemento `<audio>` garantisce una-sola-sorgente a runtime.
- L'hook pubblico resta un unico `usePlayer()` (rinominato da `usePreviewPlayer`).

### 2.2 Barra docked

Estendere `docked-preview-player.tsx` (rinominabile in `docked-player.tsx`) per
renderizzare in base a `active.kind`:

- `discovery-preview` → invariato (audio iTunes `controls` o iframe YouTube).
- `local-track` → `<audio src={`${API}/api/tracks/${track.id}/audio`} controls autoPlay>`
  con `title`/`artist` nell'header. Sull'evento `onError` dell'`<audio>` (formato non
  supportato dal browser o file sparito) → mostra messaggio inline "formato non
  riproducibile nel browser" (con estensione se disponibile).

### 2.3 Componente play riusabile

Nuovo `components/track-play-button.tsx`:

- Prop: la traccia (id, title, artist, `has_local_file`).
- Renderizza il bottone **solo se `has_local_file=true`**.
- Toggle: se questa traccia è già `active` e in play → `stop()`; altrimenti
  `play({ kind: "local-track", track })`.
- Icona play/pausa coerente con `lucide-react` già in uso.

### 2.4 Montaggio

- Spostare `PlaybackProvider` + `DockedPlayer` dal solo `app/discovery/page.tsx`
  all'**app shell** (`app/layout.tsx` via `EditorialShell`, o direttamente nel layout),
  così il player è globale.
- Aggiornare i call-site esistenti di Discovery (`discovery-lead-grid.tsx`,
  `discovery-tracklist-panel.tsx`, `app/discovery/page.tsx`) all'hook rinominato e alla
  nuova firma `play({ kind: "discovery-preview", item })`.

### 2.5 Punti di innesto del play button

Inserire `<TrackPlayButton>` nelle righe-traccia dove già si mostra il badge
"FILE"/"owned", riusando lo stesso gate `has_local_file` già presente in:
`app/library/page.tsx`, `app/playlists/[id]/page.tsx`,
`app/playlists/import-manual/page.tsx`, `app/sets/[id]/page.tsx`,
`app/transitions/page.tsx`, `app/tracks/[id]/page.tsx`,
`components/track-state-icons.tsx`. (Il piano deciderà l'elenco esatto; il componente è
lo stesso ovunque.)

## 3. Client API

Aggiungere in `lib/api` la costruzione dell'URL audio, come già fatto per la cover in
`lib/api/tracks.ts` (`${API}/api/tracks/${id}/cover`):

```ts
export const trackAudioUrl = (id: number) => `${API}/api/tracks/${id}/audio`;
```

Nessun nuovo tipo response (è uno stream, non JSON).

## 4. i18n

Nuove stringhe in `lib/i18n/it.ts` e `lib/i18n/en.ts`:

- label play/pausa/stop del bottone e della barra;
- messaggio "formato non riproducibile nel browser".

## 5. Test

Backend (`backend/tests`):

- `GET /api/tracks/{id}/audio` su traccia posseduta con file esistente → `200`, body =
  contenuto file, `Content-Type` coerente.
- Richiesta con header `Range` → `206 Partial Content` con il sotto-intervallo corretto.
- Traccia inesistente → `404 track_not_found`.
- Traccia senza file locale (`has_local_file=false`) → `404 track_no_local_file`.
- Path che risolve **fuori** dalle root consentite (symlink/traversal) → `404`
  `track_file_not_allowed`.
- File mancante su disco → `404 track_file_missing`.

Frontend (`tests`, vitest):

- Una-sola-sorgente attiva: far partire una traccia locale mentre un preview è attivo lo
  sostituisce (riuso del pattern del test race-guard già esistente per il preview).
- `TrackPlayButton` non si renderizza se `has_local_file=false`.
- `onError` dell'`<audio>` locale mostra il messaggio di formato non supportato.

## 6. Docs (dopo il codice)

Allineare, al termine dell'implementazione:

- **CLAUDE.md**: emendare la frase "the project does not play audio" e la regola 7 per
  aggiungere l'eccezione **riproduzione read-only dei file posseduti** (nessuna
  mutazione), accanto alle eccezioni già presenti (Shazam, preview Discovery, dig).
- **docs/API.md**: documentare `GET /api/tracks/{id}/audio`.
- **docs/ARCHITECTURE.md** / **docs/ROADMAP.md**: nota della nuova capacità e del suo
  scope (audizione rapida, sola lettura, un player condiviso).
- **PROGRESS.md**: voce di diario.

## Fuori scope (YAGNI)

- Coda/playlist, next/prev, ascolto continuo.
- Waveform, cue point, doppio deck, features DJ (restano al Set Builder / Rekordbox).
- Transcodifica server-side (ffmpeg).
- Persistenza dello stato di riproduzione tra pagine oltre a quanto dà il context in
  memoria.
