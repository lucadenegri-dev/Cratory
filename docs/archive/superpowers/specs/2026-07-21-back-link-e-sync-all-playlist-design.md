# Ritorno alla pagina di provenienza + sync di tutte le playlist

Data: 2026-07-21

Due interventi indipendenti, uno di navigazione e uno di import streaming.

## Problema

**1. Il link "indietro" mente.** Da `/tracks/[id]` il link di ritorno porta sempre in
libreria, anche quando ci si è arrivati da una playlist, da una label, da un set, dalle
transizioni, dalla wishlist o da Shazam. Il meccanismo esistente (`?from=<querystring>`,
emesso solo da `/library`) ripristina i filtri della libreria ma non sa rappresentare
un'origine diversa dalla libreria. Lo stesso limite vale per `/playlists/[id]`, il cui
ritorno è hardcoded su `/playlists`.

**2. Sincronizzare le playlist è un lavoro a mano.** Il sync esiste solo per una playlist
alla volta (`POST /api/playlists/{id}/sync`, dal dettaglio). Con una dozzina di playlist
importate riallinearle tutte significa aprirle una per una.

## Sezione A — Ritorno alla pagina di provenienza

### Meccanismo

Un modulo nuovo, `frontend/lib/back-link.ts`, con due funzioni pure e un hook:

- `withFrom(href, currentPathAndQuery)` — appende `?from=<encoded>` a un link uscente:
  `/tracks/42?from=%2Fplaylists%2F7%3Fpage%3D2`.
- `resolveBackLink(from, fallback)` — **pura**, quindi testabile senza React. Valida che
  `from` inizi con `/` e non con `//` (nessun URL esterno iniettabile nel param), ricava
  l'etichetta dalla rotta con una mappa, e restituisce `{ href, label }`. Se `from` manca
  o non passa la validazione restituisce il fallback della pagina.
- `useBackLink(fallback)` — wrapper che legge `useSearchParams()` e delega a
  `resolveBackLink`.

Mappa rotta → etichetta (chiavi i18n già esistenti): `/library` → `t.nav.library`,
`/playlists` → `t.nav.playlists`, `/labels` → `t.nav.labels`, `/sets` → `t.nav.sets`,
`/transitions` → `t.nav.transitions`, `/wishlist` → `t.nav.downloads`, `/shazam` →
`t.nav.shazam`. Una rotta non in mappa vale come `from` non valido: si usa il fallback.

### Formato del parametro

`from` passa da querystring nuda (`artist=X&page=2`) a **path+query completo**
(`/library?artist=X&page=2`). Un vecchio link salvato non supera la validazione e degrada
al fallback `/library` senza filtri: nessun ramo di compatibilità da mantenere.

Il valore letto da `useSearchParams()` è già decodificato una volta e non va
ri-decodificato — altrimenti i valori che contengono `&`, `%` o `#` si corrompono (è la
stessa trappola documentata oggi in `app/tracks/[id]/page.tsx`).

### Chi emette `from`

Link verso `/tracks/[id]`: `app/library/page.tsx` (cambio di formato),
`components/library-track-grid.tsx`, `app/playlists/[id]/page.tsx`,
`app/labels/[label]/page.tsx`, `app/sets/[id]/page.tsx`, `app/transitions/page.tsx`,
`components/wishlist-row.tsx`, `app/shazam/[id]/page.tsx`.

Link verso `/playlists/[id]`: `app/playlists/page.tsx`, `app/shazam/[id]/page.tsx`,
`components/wishlist-row.tsx`.

### Chi lo consuma

`/tracks/[id]` (fallback `/library`) e `/playlists/[id]` (fallback `/playlists`, in
entrambi i rami — stato di caricamento/errore e pagina piena).

`/labels/[label]`, `/sets/[id]` e `/shazam/[id]` hanno oggi un solo ingresso reale e
restano con il link fisso: il meccanismo è pronto per quando ne nascerà un secondo.

### Test

Unit vitest su `resolveBackLink`: param assente, path valido con query preservata,
`//evil.com` rifiutato, rotta sconosciuta, fallback restituito intatto.

## Sezione B — "Sincronizza tutte" in Playlist

Sincronizza in un colpo solo tutte le playlist Spotify e SoundCloud importate. **I liked
sono esclusi** (Spotify Liked e SoundCloud Likes crescono per selezione manuale), come le
playlist manuali.

### Schemi (`backend/app/schemas.py`)

```python
class PlaylistSyncFailure(BaseModel):
    playlist_id: int
    name: str
    platform: str
    error: str

class PlaylistsSyncAllReport(BaseModel):
    synced: int
    failed: int
    created: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    failures: list[PlaylistSyncFailure] = []
```

`StreamingImportJobStatus` guadagna due campi opzionali:

- `current_label: str | None` — la playlist in corso con il suo progresso interno
  (`"Techno 2026 · 45/120"`), stesso ruolo del campo omonimo nei job download e analisi;
- `sync_all: PlaylistsSyncAllReport | None` — il report aggregato.

`result` resta `None` per questo kind: nessuna union da districare lato frontend.

### Job (`backend/app/services/streaming_import_job.py`)

- `syncable_playlists(db)`, pubblica e testabile: `list_playlists()` filtrata su
  `p.kind != "liked" and sync_error_for(p) is None`. Riusa la validazione esistente —
  nessuna regola di sincronizzabilità duplicata.
- `_run_spotify_sync` e `_run_soundcloud_sync` prendono `on_progress=_progress` come
  parametro, così la sync di massa inietta il proprio callback senza cambiare il
  comportamento del sync singolo.
- `_run_playlists_sync_all`: `total` = numero di playlist, `processed` = quante concluse,
  `current_label` aggiornata dal callback interno. Ogni playlist in `try/except`: al
  fallimento `db.rollback()`, voce in `failures`, si prosegue con la successiva. Al
  termine `_state["sync_all"]` contiene il report aggregato e il job chiude in `done`
  anche con fallimenti presenti — una playlist morta non deve invalidare le altre venti.
- Short-circuit Spotify: al primo `SpotifyNotConnected` / `SpotifyNotConfigured` il
  messaggio viene memorizzato e le playlist Spotify successive falliscono subito, senza
  altre chiamate di rete. Le SoundCloud proseguono regolarmente.
- Registrato in `_RUNNERS` come `"playlists_sync_all"`. `start_job` azzera anche
  `current_label` e `sync_all`.

### Router (`backend/app/routers/playlists.py`)

`POST /api/playlists/sync-all` → 202 `StreamingImportJobStatus`.

- `409 no_syncable_playlists` se non c'è nulla da sincronizzare;
- `409 streaming_import_already_running` se un job è già in corso.

Le validazioni rapide restano sincrone nel router, come per il sync singolo.

### Frontend

- `lib/api.ts`: `syncAllPlaylists()` e i tipi `PlaylistSyncFailure` /
  `PlaylistsSyncAllReport`; `StreamingImportJobStatus` estesa con i due campi nuovi.
- `components/jobs-provider.tsx`: `detail: v.current_label ?? phaseDetail`; a job concluso,
  se `sync_all` è presente, riepilogo "8 sincronizzate, 2 fallite" al posto del sommario
  del singolo import.
- `app/playlists/page.tsx`: bottone `RefreshCw` "Sincronizza tutte" in cima alla
  marginalia, sopra i tre "Importa da…", disabilitato mentre
  `jobs.streamingImport?.status === "running"`. Sulla transizione running → done/error con
  `kind === "playlists_sync_all"`, un Alert in cima alla lista mostra conteggi ed elenco
  delle fallite con il motivo: tono `info` senza fallimenti, `warning` con almeno uno.
  L'Alert resta finché la pagina non viene ricaricata — la barra job globale svanisce dopo
  quattro secondi e porterebbe via con sé l'elenco dei problemi.
- i18n: nuove stringhe in `lib/i18n/it.ts` e `lib/i18n/en.ts`.

### Test

`backend/tests/test_playlists_sync_all.py`, con `_spawn` reso sincrono (pattern di
`test_streaming_import_job.py`):

- `syncable_playlists` esclude liked Spotify, likes SoundCloud, playlist manuali e Spotify
  prive di `platform_playlist_id`;
- un fallimento a metà non ferma il job: le successive vengono sincronizzate e il report
  aggregato contiene conteggi e `failures` corretti;
- Spotify disconnesso: le playlist Spotify falliscono tutte senza ulteriori chiamate di
  rete, le SoundCloud vengono sincronizzate lo stesso;
- il router risponde 409 quando non c'è nulla da sincronizzare e quando un job gira già.

## Fuori scope

- Sync automatico o schedulato: il bottone resta un'azione esplicita.
- Sync dei liked, di qualsiasi piattaforma.
- Job concorrenti: resta un solo job streaming alla volta, come oggi.
- Estensione del back-link a `/labels/[label]`, `/sets/[id]`, `/shazam/[id]`.
