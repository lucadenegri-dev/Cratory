# Player: barra a tutta larghezza, controlli custom, continuità, Media Session

Data: 2026-08-16. Stato: approvata a voce.

## Problema

Il player docked (`components/docked-player.tsx`) è un riquadro d'angolo da
320px con i controlli nativi del browser: è l'unico punto dell'app con UI "di
sistema" fuori dal design system, non ha seek/tempi leggibili, si ferma a fine
traccia costringendo a tornare alla lista per ogni brano, e non parla con il
sistema operativo (niente tasti multimediali, niente Now Playing).

Vincolo di prodotto (CLAUDE.md): niente waveform/cue/queue in stile deck — il
player resta un orecchio d'audizione rapida, non un deck.

## Decisioni chiave

- **Barra a tutta larghezza** in fondo alla viewport (stile music player), non
  più dock d'angolo. Tre zone: sinistra (cover 56px, titolo/artista, rating),
  centro (trasporto), destra (ADD discovery, chiudi).
- **Controlli custom nel design system**: play/pause, prev/next, barra di seek
  con click e drag, tempo trascorso/durata in cifre tabellari. L'elemento
  `<audio>` perde `controls` e resta nel DOM come motore invisibile. Il backend
  (`GET /api/tracks/{id}/audio`, `FileResponse`) risponde già 206 alle Range
  request: il seek non richiede lavoro server.
- **Niente volume nel dock**: si regola dal sistema. Niente scorciatoie da
  tastiera in-app: i tasti multimediali passano da Media Session.
- **Continuità con contesto opzionale**: `play()` accetta lo snapshot ordinato
  delle tracce possedute riproducibili della lista di provenienza.
  Auto-avanzamento a fine traccia **solo per `local-track`**; le preview
  discovery restano una alla volta (il dig è valutazione deliberata di un
  lead, e si evita di far partire risoluzioni iTunes/YouTube a catena). Fine
  lista = stop, nessun loop.
- **Media Session API**: metadata (titolo, artista, artwork) e handler
  `play`/`pause` sempre; `previoustrack`/`nexttrack` solo quando c'è contesto.
- **YouTube resta iframe**: video in riquadro compatto (~256px) ancorato sopra
  la barra a destra, controlli suoi; la barra sotto mostra titolo/artista,
  ADD e chiudi (niente trasporto). Il trasporto pieno vale per i casi con
  `<audio>` reale (tracce possedute, clip iTunes, stream Bandcamp).

## Architettura

### `lib/player.tsx` (provider)

- `play(source, context?)`: `context` è `LocalTrack[]` — snapshot, non
  riferimento vivo: filtri o riordini successivi della lista non toccano
  l'ascolto in corso. Il provider tiene `context` e l'indice corrente
  (derivato dall'id della traccia attiva).
- Nuove capacità esposte: `next()`, `prev()`, `hasNext`/`hasPrev`. `next()` e
  `prev()` fanno `play` della traccia adiacente **mantenendo il contesto**.
  Un `play` senza contesto (o una preview discovery) azzera il contesto.
- `audible` e `setAudible` invariati: la fonte onesta restano gli eventi
  dell'elemento audio; l'animazione della consolle in Home non cambia.

### `components/docked-player.tsx` → barra

- Layout a tre zone, fissa in fondo; sale sopra la barra job con il meccanismo
  esistente (`--jobs-bar-height`).
- Pubblica la propria altezza in `--player-bar-height`; il layout aggiunge
  padding-bottom alle pagine quando il player è attivo, così l'ultima riga
  delle liste resta raggiungibile.
- Zona centro con larghezza massima ~40rem per non allungare il binario di
  seek su schermi larghi.
- Su schermi stretti le zone collassano: cover+testo e trasporto; la zona
  destra si riduce alle sole icone.
- A fine traccia (`onEnded`): se sorgente `local-track` e `hasNext`,
  auto-avanzamento; altrimenti comportamento attuale (resta caricata, muta).

### Trasporto custom (nuovo componente)

- Motore: ref all'elemento `<audio>` nascosto; `timeupdate`/`loadedmetadata`
  alimentano posizione e durata; click/drag sul binario impostano
  `currentTime`. Prev/next visibili solo con contesto.
- Riusato identico per traccia locale, clip iTunes e stream Bandcamp.

### `components/track-play-button.tsx` e call site

- Prop opzionale `context`: l'elenco ordinato delle tracce della lista
  filtrato a `has_local_file`. La passano griglia libreria
  (`library-track-grid.tsx`) e dettaglio set (`app/sets/[id]/page.tsx`);
  dettaglio traccia e righe sparse (`track-state-icons.tsx`) non cambiano.

### Media Session (nel componente barra)

- Su cambio sorgente attiva: `navigator.mediaSession.metadata` con titolo,
  artista, artwork (URL cover). Handler `play`/`pause` legati all'elemento
  audio; `previoustrack`/`nexttrack` registrati solo con contesto, rimossi
  senza. Guardia `"mediaSession" in navigator` (feature facoltativa, nessun
  errore dove manca).

## Gestione errori

- Errore dell'elemento audio (formato non supportato, file sparito): messaggio
  come oggi; con contesto e auto-avanzamento attivo l'errore **non** salta
  alla traccia dopo — si ferma e mostra l'errore (saltare a catena
  maschererebbe file rotti).
- Preview discovery `unavailable`/`loading`: messaggi attuali, nella zona
  centro della barra.

## Test

- Unit provider: avanzamento contesto (next/prev/fine lista), azzeramento del
  contesto al cambio sorgente e sulle preview, `hasNext`/`hasPrev`.
- Unit trasporto: formattazione tempo, seek che imposta `currentTime`,
  prev/next visibili solo con contesto.
- `track-play-button.test.tsx` esteso per la prop `context`.
- Media Session: mock di `navigator.mediaSession`, verifica metadata e
  registrazione/rimozione handler.
- E2e esistenti sul player: aggiornare i selettori se cambiano
  (`data-testid="local-audio"`/`"preview-audio"` restano).

## Fuori scope

- Waveform, cue point, coda manuale riordinabile (vietati da CLAUDE.md).
- Volume nel dock, scorciatoie da tastiera in-app.
- Loop/shuffle, cronologia d'ascolto, persistenza della posizione tra sessioni.
- Qualunque modifica al backend audio.
