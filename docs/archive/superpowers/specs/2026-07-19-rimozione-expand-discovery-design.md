# Rimozione del flusso Discovery "expand" (Last.fm) — Design

**Data:** 2026-07-19
**Stato:** approvato (approccio A, taglio netto)

## Obiettivo

Rimuovere completamente il flusso di discovery **"espansione playlist"** (Last.fm-centrico)
da backend, frontend, test e documentazione. Resta l'unico flusso di discovery: il **dig
"Scava"** (Discogs, pagina `/discovery`).

## Motivazione

L'expand e il dig sono feature separate, ma l'expand è percepito come ridondante, dà
risultati deboli e porta con sé una dipendenza (Last.fm) da configurare e mantenere.
Rimuoverlo del tutto è l'unica opzione che ripaga sul fronte manutenzione: elimina la
config `LASTFM_API_KEY`, l'integration Last.fm e la relativa superficie di codice/test.

Decisione esplicita presa in fase di brainstorming: si rimuove **anche** l'endpoint
`POST /api/playlists/{id}/discovered-tracks` (l'"Aggiungi" dell'expand) e il write-back
Spotify `SpotifyWebClient.add_tracks` che serve solo quello — entrambi orfani dopo la
rimozione dell'expand.

## Fuori scope

- Il dig "Scava" (Discogs): invariato in tutto (motore, preview, tracklist, save-for-later,
  add-to-library `/api/discovery/add`).
- Gli endpoint discovery del dig: `/genres`, `/dig`, `/release/{id}`, `/preview`, `/add`,
  `/save-for-later` restano.
- La pagina `/discovery` e i suoi componenti (`DiscoveryDigBar`, `DiscoveryLeadGrid`,
  `DiscoveryTracklistPanel`): invariati.
- Il player docked condiviso: invariato (non è codice expand).
- La documentazione **storica** sotto `docs/superpowers/plans/` e
  `docs/superpowers/specs/`: sono verbali datati, non si riscrivono.

## L'intreccio degli import (il punto delicato)

`services/discovery.py` (expand) e `services/discovery_dig.py` (dig) sono mutuamente
accoppiati:

- `discovery_dig.py:34` importa `_library_tracks` e `_norm` da `services/discovery.py`.
- `services/discovery.py:206` importa `_dedup_key` da `discovery_dig.py` (import locale
  anti-ciclo, dentro `_drop_in_library`).

`_norm` e `_library_tracks` sono due helper generici (normalizza stringa; carica tutte le
`Track`). **Vanno spostati dentro `discovery_dig.py`** prima di cancellare
`services/discovery.py`. `_dedup_key` vive già nel dig e resta lì; il suo import in
`discovery.py` sparisce insieme al file.

Contratto di `discovery_dig.py` dopo lo spostamento: identico all'attuale (le stesse
funzioni pubbliche `dig` e `DiscoveryLead`), solo con `_norm`/`_library_tracks` definiti
localmente invece che importati. Nessun consumatore esterno di `discovery_dig` cambia.

## Interventi

### Backend — services
- **Eliminare** `backend/app/services/discovery.py` (tutto il flusso expand:
  `discover_for_playlist`, `DiscoveryCandidate`, `DiscoveryResult`, `_collect`, `_rank`,
  `_finalize`, `_explain`, `_annotate_labels`, ecc.).
- **Spostare** in `backend/app/services/discovery_dig.py` le due funzioni `_norm` e
  `_library_tracks` (con i loro import: `select`, `Session`, `Track`); rimuovere la riga
  `from app.services.discovery import _library_tracks, _norm`.

### Backend — router discovery (`routers/discovery.py`)
Rimuovere il ramo expand mantenendo intatto il dig:
- Handler `@router.get("/status")` (`status`) e `@router.post("/expand")` (`expand`).
- Helper solo-expand: `_require_lastfm`, `_owned_labels`, `_candidate_out`, `_response`,
  `_spotify_configured`, `_resolver`, `_maybe_llm`.
- Import ora inutili: `app.integrations.lastfm` (tutto), `app.integrations.llm`
  (`get_llm_client`, `llm_configured`), `app.integrations.spotify.SpotifyWebClient`,
  `app.core.config.settings`, `app.services.labels` (`_clean_label`, `album_label`,
  `labels_overview`), e da `app.services.discovery` i simboli `DiscoveryCandidate`,
  `DiscoveryResult`, `discover_for_playlist`. Da `app.schemas`: `DiscoveryCandidateOut`,
  `DiscoveryExpandRequest`, `DiscoveryResponse`.
- Aggiornare il docstring del modulo (oggi cita `/expand` e Last.fm).
- Verifica finale: nessun import resti orfano; il router importa ancora ciò che serve al dig.

### Backend — schemas (`schemas.py`)
- **Eliminare** `DiscoveryCandidateOut`, `DiscoveryResponse`, `DiscoveryExpandRequest`.
- **Eliminare** `PlaylistAddTrackRequest`, `PlaylistAddTrackResponse` (solo discovered-tracks).

### Backend — router playlists (`routers/playlists.py`)
- **Eliminare** l'handler `@router.post("/{playlist_id}/discovered-tracks")`
  (`add_discovered_track`) e il relativo import di `PlaylistAddTrackRequest/Response`.

### Backend — integrations / config
- **Eliminare** `backend/app/integrations/lastfm.py`.
- Rimuovere il campo `lastfm_api_key` da `backend/app/core/config.py:35`.
- Rimuovere la card `"lastfm"` in `backend/app/routers/services.py:44-50` (la voce
  Last.fm nella pagina Impostazioni).
- Rivedere `backend/app/integrations/__init__.py` (righe 10, 56): commenti/protocollo
  `SimilarityClient` che citano Last.fm come sorgente di similarità del Discovery. Il
  protocollo `SimilarityClient` diventa orfano (lo implementava solo `LastFMClient`):
  verificare se è ancora usato altrove; se no, rimuoverlo.
- **Eliminare** `SpotifyWebClient.add_tracks` (`integrations/spotify.py:291`), orfano dopo
  la rimozione di discovered-tracks (nessun altro chiamante).

### Frontend
- **Eliminare** la pagina `frontend/app/playlists/[id]/expand/` (intera cartella).
- **Eliminare** il componente `frontend/components/expand-results.tsx`.
- In `frontend/app/playlists/[id]/page.tsx`: rimuovere il `ButtonLink` verso
  `/playlists/[id]/expand` (riga 252) e l'icona `Compass` dall'import (riga 7, non più
  usata in quel file).
- In `frontend/lib/api/discovery.ts`: rimuovere `discoveryStatus` e `discoverExpand` e gli
  import di tipo `DiscoveryStatus`, `DiscoveryResponse` (tenere le funzioni del dig).
- In `frontend/lib/api/playlists.ts`: rimuovere `addDiscoveredTrackToPlaylist` e l'import
  `PlaylistAddTrackResult`.
- In `frontend/lib/api/types.ts`: rimuovere `DiscoveryStatus`, `DiscoveryResponse`,
  `PlaylistAddTrackResult` (e il tipo candidato usato solo da questi, se orfano).
- In `frontend/lib/i18n/it.ts` e `en.ts`: rimuovere `playlists.discoverSimilarButton`,
  l'intero blocco `playlists.expand`, e la chiave errore `lastfm_not_configured`.

### Test
- **Eliminare** i file solo-expand/Last.fm: `test_lastfm_cache.py`,
  `test_expand_variant_dedup.py`, `test_playlist_add_track.py`.
- `test_discovery.py`: rimuovere i test dell'expand e del client Last.fm
  (`test_lastfm_*`, `test_expand_*`, e ogni test che usa `discover_for_playlist`, es.
  `test_resolution_is_bounded`) e gli import di modulo `LastFMClient` /
  `discover_for_playlist`. **Tenere** `test_add_discovered_track_to_library` (nonostante il
  nome, testa `import_single_track` — idempotenza libreria, usata dal dig `/add`): se il
  file resta col solo questo test, va bene tenerlo lì o spostarlo in un test di
  `playlist_import`.
- `test_discovery_router_http.py`: rimuovere i test di `/status` e `/expand`; tenere i test
  del dig.
- `test_membership_provenance.py:140` (`test_endpoint_discovered_tracks_marca_cratory`):
  rimuovere solo quel test (usa `add_discovered_track`); tenere il resto del file.
- Verifica finale: `python -m pytest tests` verde; nessun import rotto.

### Documentazione (aggiornare lo stato corrente, non la storia)
- `README.md` (51, 84, 137, 201): Discovery = solo Scava/Discogs; togliere Last.fm dai
  provider e `LASTFM_API_KEY` dall'esempio `.env`.
- `CLAUDE.md` (90, 94): togliere Last.fm dai provider Discovery; il paragrafo "playlist
  expansion is Last.fm-centric…" va riscritto (resta solo il dig Discogs).
- `docs/ARCHITECTURE.md` (26, 77, 85, 436, 447, 457) e `docs/architettura.svg` (box
  "DISCOVERY · EXPAND", 73-74): togliere il ramo expand dal diagramma e dalle tabelle
  provider.
- `docs/API.md` (164, 347-367 sezione `expand`, 431-434): rimuovere gli endpoint
  `/expand` e `/status` e la nota su discovered-tracks/expand.
- `docs/ROADMAP.md` (29, 55, 88, 99, 194, 231): Discovery = solo dig; il backlog
  "unificazione expand/dig" e "Last.fm tag come 2ª sorgente" diventano **chiusi/non
  applicabili** (l'expand non esiste più).
- `docs/DEPENDENCIES.md` (74, 81): rimuovere la riga Last.fm dalla tabella servizi.
- `PROGRESS.md`: aggiungere una milestone datata 2026-07-19 che riassume la rimozione;
  aggiornare "Ultimo aggiornamento". Le entry storiche restano.

## Verifica end-to-end (post-implementazione)
1. Backend: `python -m pytest tests` verde.
2. Frontend: `npm run lint` e `npm run build` senza errori.
3. Browser (dev server): la pagina di dettaglio di una playlist non mostra più "Scopri
   musica simile"; la pagina `/discovery` (Scava) funziona; la pagina Impostazioni non
   mostra più la card Last.fm; nessun 404/500 in console/network.
4. `grep -rin "lastfm\|last\.fm\|expand-results\|discoverExpand\|discovered-tracks"`
   su `backend/app` e `frontend/{app,components,lib}` non trova più riferimenti vivi.

## Rischi
- **Import orfani**: il taglio tocca molti file; il rischio principale è lasciare un import
  rotto (soprattutto lo spostamento `_norm`/`_library_tracks`). Mitigazione: pytest + build
  come gate, e la verifica finale di grep.
- **`SimilarityClient` orfano**: da confermare che nessun altro modulo lo usi prima di
  rimuoverlo; se dubbioso, lasciarlo (è innocuo) e annotarlo.
