# Voto tracce a 3 livelli

Data: 2026-08-07 · Stato: approvata

## Obiettivo

Un sistema di voto semplice a 3 livelli (qualità/gradimento: 1 = ok, 2 = buona,
3 = eccellente; assente = non ancora valutata) per organizzare libreria e
playlist. Il voto è votabile su **tutte** le tracce, anche i lead streaming non
posseduti (utile al triage wishlist/discovery), e viene usato in tre modi:

1. **Filtro e ordinamento** in library e playlist.
2. **Playlist speciale "Top"** auto-aggiornata con le tracce da 3.
3. **Bonus deterministico** nel punteggio del Set Builder (mai un filtro,
   mai passato all'AI).

## Design

### 1. Dati (backend)

- Nuova colonna `rating: Mapped[int | None]` su `Track` (`tracks`), valori
  ammessi 1–3, `NULL` = non votata, indicizzata (serve a filtro/sort e alla
  query della playlist Top).
- Migrazione idempotente in `ensure_schema` (`backend/app/db.py`), stesso
  pattern delle colonne recenti (`ADD COLUMN` se assente).
- `serializers.py`: `rating` esposto sia nella riga lista sia nel dettaglio.
- Nessuna tabella nuova: niente storico voti, niente dimensioni multiple
  (fuori scope, YAGNI).

### 2. API (backend)

- `PATCH /api/tracks/{track_id}` (esistente): `rating` entra in
  `TrackUpdateIn` con validazione Pydantic `int | None`, `ge=1`, `le=3`.
  `null` toglie il voto. Valori fuori range → 422.
- `GET /api/tracks`: nuovo parametro `rating` (match esatto, es. `?rating=3`)
  e nuova chiave di ordinamento `sort=rating` (voti alti prima, non votate in
  fondo — `NULLS LAST`).
- La sync della playlist Top (sotto) avviene nella stessa transazione del
  PATCH: nessun endpoint aggiuntivo.

### 3. Playlist speciale "Top" (backend + frontend)

Precedente: la playlist Discovery (`platform="manual"`, `kind="discovery"`,
creata al primo uso in `playlist_import.py`).

- Playlist reale `platform="manual"`, `kind="rating_top"`, nome "Top",
  creata al primo voto 3 (helper `get_or_create` nello stesso stile).
- Sync deterministica a ogni cambio voto, dentro la transazione del PATCH:
  - voto → 3: aggiunge la membership a `playlist_tracks` (se assente);
  - voto ≠ 3 (o `null`): rimuove la membership (se presente);
  - `track_count` riallineato a ogni modifica (lezione del fix conteggi:
    mai lasciare il denormalizzato indietro).
- Frontend (`frontend/app/playlists/page.tsx`): `isSpecial` include
  `kind === "rating_top"`; ordine fisso della sezione Speciali: Discovery,
  Top, SoundCloud Likes, Spotify Likes. Cover dedicata
  `frontend/public/cover-rating-top.svg` (stile dei cover speciali esistenti,
  glifo rombo; `PlaylistCover` estende il fallback).
- Essendo una playlist reale, è già usabile come sorgente nel Set Builder via
  `playlist_id`, senza codice aggiuntivo.

### 4. Set Builder (backend)

- Il voto **non filtra** i candidati: `candidate_engine.select_candidates`
  resta invariato (una traccia non votata resta eleggibile).
- Bonus deterministico nel punteggio di transizione/selezione del
  `set_generator`: a parità di compatibilità BPM/key, la traccia con voto più
  alto vince. Entità del bonus: piccola, da tie-break — non deve mai battere
  la compatibilità armonica/BPM (l'ordine di grandezza esatto si fissa nel
  piano guardando la scala dei punteggi esistenti).
- Nessun coinvolgimento AI: il rating non entra nei payload verso l'AI
  (regola 1 di CLAUDE.md rispettata).

### 5. Frontend — componente RatingDiamond

- Componente condiviso `frontend/components/rating-diamond.tsx`.
- **Resa**: rombo singolo SVG a 4 stati — non votata: contorno `faint`;
  1: pieno oliva `#8a8065`; 2: pieno ambra `#cfa14a`; 3: pieno terracotta
  (accento esistente, `--c-danger` / `#d8593f`). Dimensione ~18px nelle
  righe, più grande nel dettaglio.
- **Interazione a espansione**: click sul rombo apre i 3 livelli accanto
  (piccoli rombi colorati, transizione breve); click su un livello assegna;
  ri-click sul livello già attivo toglie il voto; click fuori o `Esc`
  chiude. Niente stati intermedi, qualsiasi voto in due click.
- **Update ottimistico**: lo stato locale cambia subito, `PATCH` in
  background, rollback con toast/error se fallisce.
- Montato in: righe library (`app/library`), righe della pagina tracks e
  playlist detail, pagina dettaglio traccia, player docked (vota la traccia
  in riproduzione). Nel player appare solo quando la sorgente è una traccia
  della libreria (ha un `track_id`): per le preview effimere di Discovery il
  rombo non viene mostrato.
- Filtro per voto + ordinamento nelle viste library/playlist (UI coerente con
  i filtri esistenti).

### 6. Test

Backend (pytest):

- PATCH: assegna/cambia/toglie voto; 0, 4, -1 → 422.
- Sync Top: primo voto 3 crea la playlist e aggiunge; downgrade rimuove;
  ri-voto 3 non duplica la membership; `track_count` sempre allineato.
- `GET /tracks`: filtro `rating=3`; `sort=rating` con non votate in fondo.
- Generator: a parità di transizione, la traccia votata più alta viene
  scelta; il bonus non ribalta una compatibilità BPM/key peggiore.

Frontend (unit, vitest/playwright esistenti):

- RatingDiamond: 4 stati resi correttamente; espansione apre/chiude;
  assegnazione e rimozione voto chiamano l'API col valore giusto.

## Fuori scope

- Export del voto verso Rekordbox o nei tag dei file (i tag sono di Sortory;
  Cratory non muta mai i file).
- Storico voti, voti multi-dimensione, medie.
- Smart playlist per i voti 1 e 2 (solo "Top" per il voto 3).
- Uso del voto in Discovery/dig ranking.
