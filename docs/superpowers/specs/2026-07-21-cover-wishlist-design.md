# Wishlist: cover della traccia nelle righe

Data: 2026-07-21 · Stato: approvato a voce, in attesa di review scritta

## Contesto e obiettivo

La wishlist è oggi l'unica lista di tracce dell'app senza artwork: Libreria,
dettaglio playlist, pagina label, Set Builder e Transitions montano tutte
`TrackCover`. Scorrere ~55 righe di solo testo costringe a leggere
"artista — titolo" per capire di cosa si tratta, mentre la copertina è
riconoscibile a colpo d'occhio.

Obiettivo: aggiungere la cover alla riga wishlist riusando il componente
esistente, senza toccare backend, API o tipi.

## Non-obiettivi

- Nessun endpoint nuovo e nessuna modifica al serializer: `album_art_url` è già
  nella risposta di `GET /api/tracks` e già nel tipo `Track` del frontend.
- Nessun proxy o cache immagini lato backend: gli URL Spotify si caricano
  direttamente, come nelle altre liste.
- Nessun lazy-loading custom: `TrackCover` ha già `loading="lazy"` e
  `decoding="async"`.
- Nessun cambiamento a filtri, tab, contatori o azioni della riga.
- Nessuna vista a griglia per la wishlist: resta una lista.

## Sorgente dell'immagine

`trackCoverSrc` (`frontend/lib/api/tracks.ts`) risolve in ordine:
`album_art_url` (Spotify, popolato all'import playlist in
`services/playlist_import.py`) → artwork embedded del file per le possedute →
`null`.

La wishlist carica `GET /api/tracks?has_local_file=false`: il secondo ramo non
si attiva mai. Conseguenza pratica: **nessuna richiesta a
`/api/tracks/{id}/cover`, nessun 404 da gestire**, il fallback `onError` di
`TrackCover` resta inerte. Le tracce senza artwork Spotify mostrano il
placeholder `Music4` su `bg-elevated`.

## Modifica alla riga

File unico: `frontend/components/wishlist-row.tsx`.

Il blocco sinistro passa da colonna singola a riga flex
(`flex items-center gap-2.5`): cover a sinistra, colonna titolo + chip di
provenienza a destra. Formato `h-10 w-10` con `iconSize={16}`, lo stesso preset
delle righe del Set Builder (`app/sets/[id]/page.tsx`), scelto perché la riga
wishlist è su due righe di testo e una cover da 40px ne copre l'altezza.

La cover è avvolta in un `<a>` verso `/tracks/{id}` con lo stesso
`withFrom(…, from)` del titolo, marcato `aria-hidden="true"` e `tabIndex={-1}`:
il mouse guadagna superficie cliccabile, mentre tastiera e screen reader
continuano a vedere **un solo** link per traccia. Il wrapping separato (invece
di un unico `<a>` attorno a cover e testo) è anche un vincolo di correttezza
HTML: i chip di provenienza sono già `<Link>` e non possono annidarsi dentro un
altro `<a>`.

`WishlistRow` è lo stesso componente per la vista normale e per quella
archiviata: la cover compare in entrambe.

Costo visivo: trascurabile. Misurato in pagina, la riga passa da ~59px a 61px:
il blocco titolo + chip era già alto quanto la cover, quindi i 40px non
aggiungono altezza, la assecondano.

## Test

Due casi nuovi in `frontend/tests/wishlist-row.test.tsx`:

1. Traccia con `album_art_url` valorizzato → nel DOM c'è una `<img>` con quel
   `src`.
2. Traccia con `album_art_url: null` (e `has_local_file: false`) → nessuna
   `<img>`, viene reso il placeholder.

Verifica: `npm run test:unit` e `npm run lint` dalla cartella `frontend`.

## Rischi

Basso. Il rischio residuo è estetico (densità della lista) ed è reversibile
cambiando una classe di dimensione.
