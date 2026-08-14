# Wishlist: rifacimento della sezione Download

Data: 2026-07-19 · Stato: approvato a voce, in attesa di review scritta

## Contesto e obiettivo

Oggi `/downloads` è una pagina centrata sul processo: acquisizione da playlist,
ricerca manuale Soulseek e il work-list delle tracce con esito download da
sistemare (`needs_review` / `not_found` / `failed`). Le tracce non possedute che
non hanno mai avuto un tentativo di download sono visibili solo in Libreria col
filtro `owned=false`.

Il rifacimento rovescia la prospettiva: **la pagina diventa la Wishlist**, cioè
la gestione di tutte le tracce che non possiedo, dove il download è una delle
azioni possibili e l'acquisto un'altra. Lo stato download (mai tentata / in
review / non trovata / fallita) diventa un attributo per traccia, non il
criterio d'ingresso.

Numeri reali al 2026-07-19: 55 tracce non possedute — 46 `not_found`, 8 mai
tentate, 1 `downloaded` senza file.

## Non-obiettivi

- Nessuna integrazione API con i negozi (prezzi/disponibilità): l'acquisto è un
  link di ricerca precompilato che si apre in un'altra tab.
- Nessuno stato "comprata/in arrivo" sul Track (rimandato: la promozione a
  posseduta avviene già via indicizzazione quando il file compare su disco).
- Nessun flag "in wishlist" esplicito: la popolazione è derivata
  (`has_local_file=false` e non archiviata), zero migrazioni di schema.
- La Libreria non cambia: il filtro `owned` resta come scorciatoia.

## Popolazione

Tutte le tracce con `has_local_file=false` e `archived=false`. Un solo fetch:
`GET /api/tracks?has_local_file=false&limit=0` (`limit=0` = tutte, il serializer
include già `playlists: [{id, name}]` e i campi `last_download_*`). Filtri,
ricerca e contatori sono client-side.

## Layout della pagina `/wishlist`

1. **Header**: titolo "Wishlist", meta = numero tracce.
2. **Barra azioni bulk**: select playlist + "Scarica playlist"; "Riprova tutte"
   (retry auto-pick su non trovate/fallite); "Collega tutte" (auto-link).
3. **Filtri** (persistiti in query string, pattern attuale di /downloads):
   - tab per stato con contatori: *Tutte / Mai tentate / In review / Non
     trovate / Fallite*;
   - ricerca testuale artista/titolo;
   - filtro per playlist di origine;
   - toggle *"mostra archiviate"* (vista di ripristino, vedi Archivia).
4. **Lista** — una riga per traccia:
   - **Titolo — Artista**, link a `/tracks/{id}`;
   - **Provenienza**: chip cliccabili con le playlist di origine →
     `/playlists/{id}`; oltre 2, "+N". Le tracce da Discovery hanno già la
     playlist di sistema "Scoperte" (`kind='discovery'`), quindi mostrano quel
     chip; solo le tracce create a mano possono non avere chip (nessun
     segnaposto).
   - **Badge stato**: *Mai tentata* (neutro), *In review* (warning), *Non
     trovata* (neutro), *Fallita* (danger), *Scaricata, non collegata*
     (warning; caso `downloaded` senza file). Motivo (`last_download_reason`)
     sotto quando presente.
   - **Azioni per riga**:
     - primaria contestuale: *Scarica* (auto-pick) se mai tentata; *Riprova* se
       non trovata/fallita; *Rivedi* se in review; *Collega file* se scaricata
       non collegata;
     - **Compra ▾**: menu con Bandcamp, Beatport, Juno Download, Discogs —
       ricerca `artist title` urlencoded, `target="_blank"`;
     - overflow "⋯": *Collega file*, *Azzera esito*, *Archivia* (con conferma).
5. **Ricerca Soulseek libera**: sezione secondaria/collassabile in fondo —
   resta disponibile (ricerca + grab manuale) ma non ruba la scena.

Il progresso dei job resta nella barra globale (JobsProvider), non duplicato.

### Template URL acquisto (frontend puro)

- Bandcamp: `https://bandcamp.com/search?q={q}`
- Beatport: `https://www.beatport.com/search?q={q}`
- Juno Download: `https://www.junodownload.com/search/?q%5Ball%5D%5B%5D={q}`
- Discogs: `https://www.discogs.com/search/?q={q}&type=release`

con `q = encodeURIComponent(artist + " " + title)`.

## Backend

Modifiche minime:

1. **`PATCH /api/tracks/{id}`: nuovo campo `archived: bool`** in `TrackUpdateIn`
   (assente = invariato, come gli altri campi; gestito in
   `repositories.update_track`). Prima via manuale per archiviare/ripristinare —
   oggi `archived` si imposta solo via DJPlayer/indicizzazione.
2. **Nessun altro endpoint nuovo.** Riuso completo di: `GET /api/tracks`
   (lista), `/api/downloads/track/auto` (auto-pick), `/api/downloads/review` +
   `keep-review`/`discard-review`, `DELETE /api/downloads/pending/{id}` (azzera
   esito), `/api/downloads/playlist/{id}`, `/api/downloads/retry-pending`,
   `/api/downloads/auto-link`, `/api/downloads/search` + `manual`,
   `/api/tracks/{id}/link-file`.

## Routing e navigazione

- Nuova pagina `frontend/app/wishlist/page.tsx`; la voce nav "Download" diventa
  "Wishlist" → `/wishlist` (il badge col conteggio pending resta).
- `/downloads` reindirizza a `/wishlist` (redirect Next), così i link esistenti
  non si rompono.
- Riuso dei componenti esistenti: `DownloadReviewModal`, `LinkLocalFileModal`,
  `AutoLinkModal`, `ConfirmModal`.

## Casi limite

- **`downloaded` senza file**: badge dedicato "Scaricata, non collegata",
  azione primaria *Collega file*; nei tab conta sotto "In review".
- **slskd non configurato**: banner info; azioni download disabilitate, ma
  Compra, Collega file e Archivia restano attive.
- **Job in corso**: azioni download disabilitate per riga (il backend risponde
  comunque 409).
- **Uscita dalla wishlist**: automatica quando l'indicizzazione trova il file
  (`has_local_file=true`) — comportamento emergente, zero codice.
- **Archivia reversibile**: il toggle "mostra archiviate" elenca le archiviate
  con azione *Ripristina* (`PATCH archived=false`); niente buchi neri. Il
  parametro `archived=true` della lista restituisce *solo* le archiviate,
  quindi il toggle fa un fetch dedicato
  (`has_local_file=false&archived=true&limit=0`) e sostituisce la vista (non si
  mescolano attive e archiviate).
- **Azzera esito**: riporta la traccia a "mai tentata" (semantica invariata di
  `DELETE /pending/{id}`), non la toglie dalla wishlist.

## Test

- **Backend (pytest)**: `PATCH archived` set/unset; il filtro `archived` della
  lista riflette il cambio; i test downloads esistenti restano verdi.
- **Frontend**: `npm run lint` + `npm run build`; e2e sul pattern esistente:
  filtri per stato coi contatori, chip di provenienza renderizzati, menu Compra
  con URL corretti, redirect `/downloads` → `/wishlist`.
