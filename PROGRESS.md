# PROGRESS - diario di sviluppo

> Diario di ripresa lavoro: solo cronologia e punto di ripresa. Lo **stato corrente,
> le priorità e le decisioni** vivono in `docs/ROADMAP.md` (fonte di verità). Per
> orientarsi: `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `CLAUDE.md`.

## Stato attuale

**Ultimo aggiornamento:** 2026-07-05

**Nome prodotto:** **Cratory** (rename eseguito il 2026-06-25 su UI, codice, docs e
icona). "SetArc" e "DJ Assistant" restano solo come nomi storici; i path tecnici legacy
(`djassistant.db`, log path) restano invariati finche' non viene pianificata una rename
migration. Disponibilita' `cratory.com` da confermare su registrar.

**Fase:** core streaming-first completo; **disk-first completo** (la libreria e' il
disco, playlist streaming = lead); Discovery operativo (expand Last.fm + dig Discogs);
enrichment multi-provider; Set Builder tecnico/creativo con garanzia "solo posseduti";
audit leggero (quick win) e rifacimento documentazione fatti; identificazione mix via
Shazam in integrazione.

## Milestone 2026-07-05 - Archivio download da sistemare + collegamento manuale file

Pagina persistente dei download problematici e possesso senza download; piano in
`docs/superpowers/plans/2026-07-05-download-issues-e-link-file.md`.

- **Pagina `/downloads/issues`**: archivio persistente delle tracce con esito
  `not_found`/`needs_review`/`failed`, filtro per esito con contatori, azioni per
  riga (Scegli file Soulseek, Collega file locale, Ignora) e "Riprova tutte". In
  `/downloads` la sezione "Da sistemare" e' ora un riassunto con contatori + link.
- **Collegamento manuale file locale**: `POST /api/tracks/{id}/link-file` valida
  percorso/estensione audio, riusa `attach_local_file` (audio-hash best-effort) e
  azzera l'esito download; ricerca sul disco con `GET /api/files/search`
  (`LIBRARY_ROOT` + `SLSKD_DOWNLOAD_DIR`, match AND case-insensitive, cap 50).
  Modal condiviso (`link-local-file-modal.tsx`) usato da archivio e dettaglio
  traccia ("Collega file"/"Sostituisci file" nella card Disco).
- **Ignora**: `DELETE /api/downloads/pending/{track_id}` azzera esito e motivo.
- Refactor: modal revisione Soulseek estratto in `download-review-modal.tsx`
  (pattern wrapper + key come TrackEditModal).

## Milestone 2026-07-05 - Fingerprinting AcoustID + ottimizzazioni enrichment

Identita' acustica certa per i file posseduti; piano in
`docs/superpowers/plans/2026-07-05-fingerprinting-acoustid.md`.

- **Fingerprinting AcoustID** (`integrations/acoustid.py`, `services/fingerprint*.py`):
  audio -> MusicBrainz Recording MBID (colonna `tracks.mbid`), soglia score 0.85,
  cache esiti definitivi in `EnrichmentCache` (errori ritentabili). Endpoint
  `POST/GET /api/library/fingerprint[/status]`, card in Impostazioni, job nella
  barra GlobalProgress. Richiede `ACOUSTID_API_KEY` + `fpcalc` (chromaprint).
- **La catena enrichment usa l'mbid**: MusicBrainz lookup diretto
  `/recording/{mbid}` (niente fuzzy, confidence 95, fallback su ISRC/search),
  AcousticBrainz lo riceve dal context. L'mbid backfilla anche l'ISRC dei file
  locali (sblocca Deezer per il BPM).
- **Ottimizzazioni enrichment**: batch esteso a `bpm IS NULL OR camelot_key IS
  NULL` (le tracce senza key non restano piu' orfane); genere AI in batch (una
  chiamata LLM ogni 20 tracce, fase `genre_ai`) con cache anche dei null in
  `EnrichmentCache` (chunk falliti non cachati -> ritentabili); stima energia
  spostata dopo il genere (bias corretto); report con `ai_genres`.

## Milestone 2026-07-03 - Barra job unificata (GlobalProgress)

Tutte le operazioni lunghe passano dalla barra DJ in basso; spec approvata in
`docs/superpowers/specs/2026-07-03-barra-job-unificata-design.md`.

- **JobsProvider poller unico** (2s sui 4 endpoint di stato: enrichment, Shazam,
  download, library index); espone gli stati raw a `/downloads` e Impostazioni,
  che non hanno piu' polling propri. Client job con `updateClientJob`
  (conteggi/dettaglio); DIG ed etichette passano il dettaglio.
- **UI**: righe impilate (max 3 + "+N"), label + dettaglio ellissato (traccia in
  corso via nuovo `current_label` sullo stato download, fase per enrichment/Shazam),
  percentuale grande `.tnum`, riga cliccabile verso la pagina del job, coda "hot"
  danger sulle barre dietro la testina (`.eqm-hot`), spacer dinamico anti-overlap.
- **Esito visibile**: alla transizione running→done/error la riga resta 4s con
  l'esito ("N scaricate · M da sistemare", errori in danger), poi scompare.
- "Scarica mancanti" dalla playlist non fa piu' redirect: si resta sulla playlist,
  il progresso vive nella barra.
- Verifica: 386 test backend verdi (nuovo test TDD per `current_label`), lint/build
  frontend ok, ciclo di vita barra osservato live su un retry reale (comparsa →
  dettaglio traccia → 50% → esito 4s → scomparsa).

## Milestone 2026-07-01/02 - Disk-first (fette 1-4)

Riorientamento disco-centrico: il possesso di una traccia non e' piu' un side-effect
del solo download Soulseek, ma lo stato di una cartella canonica indicizzata
attivamente. Quattro fette, sviluppate su branch dedicati e poi rifinite:

- **Fetta 1 — identita' e indicizzazione** (branch `feat/disk-first-core`).
  `Track.audio_hash` (SHA-256 dei primi secondi di stream decodificato via ffmpeg,
  stabile a rinomina/retag), calcolato sia da `attach_local_file` (Soulseek) sia dal
  nuovo servizio `library_index`. Config `LIBRARY_ROOT`; `library_index` fa scan +
  match (`audio_hash -> digest legacy -> ISRC -> fuzzy artist+title`) + riconciliazione
  (file spariti -> tornano wishlist, hash mantenuto per riaggancio) + guard
  anti-unmount + contatore `duplicates` (stesso hash nello stesso run, primo vince).
  Esposto via `POST /api/library/index` (202, job async) + `GET /status`.
- **Fetta 2 — possesso in superficie** (fine `feat/disk-first-core`, poi
  `feat/disk-first-rifiniture`). Filtro `has_local_file` + sorgente `local_files` su
  `GET /api/tracks`; stat `with_local_file`; libreria con filtro "Wishlist (senza
  file)" e badge FILE (chiude il vecchio backlog "Vista tracce senza file"); card
  Impostazioni per lanciare l'indicizzazione; figura "Possedute" in dashboard.
- **Fetta 3 — Set Builder "solo posseduti"** (branch `feat/set-builder-owned` e
  `feat/set-editor-owned`). `SetGenerationRequest.owned_only=True` di default nel
  Candidate Engine, persistito su `Setlist.owned_only`; editor (alternative,
  sostituzione traccia) rispetta la garanzia con 422 se la sostituta non e' posseduta;
  toggle "solo brani posseduti" + badge in UI, indicatore "possiedi N di M" nel
  dettaglio playlist.
- **Fetta 4 — bridge DjOrganizer e copy** (branch `feat/lookup-endpoint`, poi
  `feat/disk-first-rifiniture`). `GET /api/tracks/lookup` read-only per DjOrganizer:
  ISRC -> fuzzy artist+title, confidence 100/70/0, sempre `limit(1)` (mai
  `MultipleResultsFound` su duplicati), mai 404 (`found: false`). Copy UI: le
  playlist streaming sono presentate come "lead", non come la libreria.

Test: 333 test backend verdi (`cd backend && .venv/bin/python -m pytest tests -q`).
Documentazione allineata in questo stesso giro: `README.md` (paragrafo disk-first +
`LIBRARY_ROOT` in setup), `CLAUDE.md` (regola 9), `docs/ARCHITECTURE.md` (sottosezione
"Disk-first"), `docs/ROADMAP.md` (fette 1-4 in "Stato completato", "Vista tracce senza
file" spostata da backlog a fatto).

**Punto di ripresa:** branch `feat/disk-first-rifiniture` (rifinitura finale, sopra
`feat/disk-first-core` + `feat/lookup-endpoint` + `feat/set-builder-owned` +
`feat/set-editor-owned`). Il disk-first e' chiuso end-to-end: indicizzazione, superficie
UI, Set Builder e bridge DjOrganizer. Prossimo fronte aperto: **miglioramento Discovery**
(unificazione expand/dig, Last.fm tag come 2a sorgente, tracklist per-release) — invariato.

## Milestone 2026-06-28 - Playlist many-to-many

Modello relazionale brano-playlist portato da 1:1 a M2M.

- `backend/app/models.py`: tabella associativa `playlist_tracks` (`playlist_id`,
  `track_id`, `added_at`); relazioni SQLAlchemy `Playlist.tracks` / `Track.playlists`;
  colonne legacy `Track.playlist_id` / `playlist_name` mantenute fisicamente ma svuotate.
- `backend/app/db.py`: migrazione idempotente `_migrate_playlist_many_to_many` con
  backfill `playlist_tracks` dalle colonne legacy.
- `backend/app/repositories.py`: helper `add_track_to_playlist`,
  `remove_track_from_playlist`, `tracks_for_playlist`, `recount_playlist`.
- `backend/app/services/`: import Spotify e manuale, prune, delete-playlist e scoping
  enrichment portati su membership; `discovered-tracks` endpoint via membership.
- `backend/app/schemas.py` / `backend/app/serializers.py`: `TrackPlaylistRef`,
  `TrackOut.playlists[]`, eager-load.
- `frontend/`: badge "in N playlist" in libreria (`/library`) e lista playlist nel
  dettaglio traccia; tipo `Track.playlists` in `lib/api.ts`.
- `backend/tests/`: test migrazione, due playlist, no-steal, prune, delete, endpoint,
  enrichment-scoping, serializer.

**Punto di ripresa:** branch `feat/playlist-many-to-many`. Prossimo fronte aperto:
Discovery (unificazione expand/dig, Last.fm tag come 2a sorgente, tracklist per-release).

## Milestone 2026-06-28 - Espansione nel contesto Playlist + write-back Spotify

Discovery ridotto a **solo DIG**; l'espansione playlist vive ora nel contesto Playlist.

- Backend: `SpotifyWebClient.add_tracks(playlist_id, ids)` (POST `/playlists/{id}/tracks`);
  nuovo endpoint `POST /api/playlists/{id}/discovered-tracks` che importa il candidato,
  lo attacca alla playlist (modello 1:1: non sposta una traccia gia' altrove) e fa
  write-back Spotify best-effort (mai bloccante). Schemi `PlaylistAddTrackRequest/Response`.
- Frontend: nuova pagina `app/playlists/[id]/expand/page.tsx` (autorun senza AI, toggle
  AI + Ricalcola); componente condiviso `components/expand-results.tsx`; Discovery
  ridotto a DIG (rimosso mode switcher e ramo expand); bottone "Scopri musica simile"
  del dettaglio playlist -> `/playlists/[id]/expand`. API client
  `addDiscoveredTrackToPlaylist`.
- Test: `tests/test_playlist_add_track.py` (add_tracks + 5 casi endpoint: spotify/manuale/
  non risolto/errore non bloccante/no-move 1:1). 217 test backend verdi; frontend lint
  0 errori, build ok; verifica browser (Discovery solo DIG, pagina expand autorun senza AI).

**Punto di ripresa:** branch `feat/espansione-in-playlist`. Backlog Discovery residuo:
Last.fm tag come 2a sorgente del dig, tracklist per-release; playlist many-to-many.

## Milestone 2026-06-28 - Discovery dig: gusto + spiegazioni

Chiuso lo slice "gusto + spiegazioni" del punto 1 (Miglioramento Discovery). Solo il
flusso dig, deterministico, niente AI ne' nuove dipendenze/rete.

- `backend/app/services/discovery_dig.py`: nuovo `TasteProfile` (artist_counts,
  owned_labels, genre_tokens) costruito da un riferimento (libreria o playlist);
  `_score` esteso con familiarita' graduata + affinita' etichetta + affinita' stile
  (pesi W_ARTIST 0.5 / W_LABEL 0.3 / W_STYLE 0.2); `Reason` + `_reasons` con soglie
  costanti. Dedup sempre library-wide, affinita' sul riferimento.
- `backend/app/schemas.py`: `ReasonOut`, `reasons` su `DiscoveryLeadOut`,
  `taste_playlist_id` su `DiscoveryDigRequest`.
- `backend/app/routers/discovery.py`: `_lead_out` mappa i reason; `dig_endpoint`
  costruisce `taste_tracks` da `tracks_for_playlist` quando e' dato `taste_playlist_id`.
- Frontend `lib/api.ts` (`Reason`, `reasons`, `tastePlaylistId`) e `discovery/page.tsx`
  (selettore "Affinita' rispetto a" + chip spiegazione).
- Test: suite dig estesa (TasteProfile, scoring, reason code, dedup library-wide) +
  test router; 211 test backend verdi, frontend lint/build puliti.

**Punto di ripresa:** branch `feat/discovery-dig-gusto-spiegazioni`. Backlog Discovery
residuo: unificazione expand/dig, Last.fm tag come 2a sorgente, tracklist per-release.

## Milestone 2026-06-18 - Reset documentazione

- Ridotta la documentazione da sei spec numerate a tre documenti stabili:
  `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md`.
- Riscritto `README.md` come porta d'ingresso per setup, workflow e stato.
- Snellito `AGENTS.md` come guida operativa per agenti.
- Compattato `PROGRESS.md` in un diario di ripresa.
- Mantenuto `CLAUDE.md` come entrypoint per l'AI usata insieme a Codex.
- Rimossi Markdown duplicati o vuoti: `frontend/README.md`, `IMPROVEMENTS.MD`,
  vecchie spec `docs/01`-`06`.
- Nome scelto: **SetArc**. Aggiornate documentazione e stringhe user-facing principali,
  senza rinominare path tecnici legacy.
- Roadmap riallineata: test reale con chiavi gia' fatto, confronto modelli AI gia'
  implementato, sezione Discovery basata sui gap rimossa.

## Milestone 2026-06-23 - Rebranding editoriale + Discovery etichette

- Rebranding completo: design system "editorial archive" monocromo (IBM Plex Mono,
  filetti, squadrato), tema dark di default + paper via toggle (runtime `--c-*` +
  `@theme inline`), shell editoriale `EditorialShell`/`PageLayout`, no-FOUC.
- Dashboard "command center": hero figures, istogramma BPM interattivo, attivita'
  recente, copertura enrichment, azioni rapide.
- Barra di avanzamento job globale (enrichment/shazam/backfill etichette) persistente
  al cambio pagina.
- Etichette: backfill da `copyrights` Spotify (dev mode), normalizzazione nomi
  (`_clean_label`), merge varianti a read-time.
- Discovery direzione C: **Radar Etichette** (`POST /api/discovery/labels`, filtro
  Spotify `label:`), **segnale-etichetta** su `/expand`, rimozione della
  "compatibilita' tecnica" (resta al Set Builder). Controlli in barra orizzontale.
  (Nota: questo endpoint `label:` e' stato poi rimosso il 27/06; il Radar usa Discogs.)
- Import Spotify: solo playlist possedute; "Aggiorna" per le gia' importate.
- Decisa la direzione prodotto: strumento **personale/self-hosted**, non SaaS pubblico
  (vincolo Spotify dev-mode). Dettaglio e conseguenze in `docs/ROADMAP.md`.
- Merge su `master` e push. 186 test backend verdi, lint/build frontend puliti.

## Milestone 2026-06-27 - Audit leggero (quick win)

- SSRF guard: l'URL del mix Shazam e' validato (solo http/https) prima di yt-dlp.
- Performance: `library_stats` riscritta con query SQL aggregate (niente full-load
  ORM), output identico; alleggerisce dashboard e contesto AI dei set.
- Rimosso l'endpoint morto `/api/discovery/labels` (+ `discover_by_labels`, helper,
  schema, `search_by_label`, test e funzione frontend): il Radar Etichette usa Discogs.
- Dipendenze: rimosso `requirements copia.txt`, tetti versione alle deps critiche,
  error body upstream accorciati. 197 test backend verdi.
- Audit confermato: CORS, secrets, retry/timeout, SQL injection e cleanup temp gia'
  a posto; niente altro di urgente per uso self-hosted.
- (UI fuori roadmap: loader EQ/waveform stile DJ con respiro e barre strette.)

## Milestone 2026-06-27 - Rifacimento documentazione

- Ridisegno dell'architettura doc: ogni informazione ha un solo proprietario canonico
  (`docs/ROADMAP.md` = stato; `PROGRESS.md` = diario), niente piu' doppia-verita'.
- `README.md` riscritto come vetrina in inglese (pitch, feature, architettura, quickstart);
  nuovo diagramma `docs/architettura.svg` monocromo, ritirati gli asset orfani.
- `AGENTS.md` (root e frontend) unificato in `CLAUDE.md` / `frontend/CLAUDE.md`
  (toolchain solo-Claude, niente Codex).
- `PRODUCT.md` e `DESIGN.md` spostati in `docs/`; PRODUCT riconciliato con
  l'editorial-archive (via lime, tema paper deliberato); branding `SetArc -> Cratory`
  corretto in `.impeccable/design.json`.
- Audit di accuratezza: `docs/API.md` (sezione Labels, enrich traccia) e
  `docs/ARCHITECTURE.md` (Discogs, SpotifyToken, `db.py`) allineati al codice.
- Spec e piano in `docs/superpowers/specs|plans/2026-06-27-rifacimento-documentazione*`.

## Punto di ripresa

Priorità e backlog completi in `docs/ROADMAP.md` (fonte di verità di stato). In sintesi:
core assestato, audit quick-win e rifacimento documentazione fatti; playlist many-to-many
completato; **disk-first completato** (fette 1-4: indicizzazione `LIBRARY_ROOT` per
`audio_hash`, possesso in superficie, Set Builder "solo posseduti", bridge
`GET /api/tracks/lookup` per DjOrganizer — branch `feat/disk-first-rifiniture`). Il
prossimo fronte aperto è il **miglioramento Discovery** (unificazione expand/dig,
Last.fm tag come 2a sorgente, tracklist per-release). i18n EN e multi-account pubblico
restano sospesi.

## Storico essenziale

- 2026-06-17: UI Dashboard/Set Builder ridisegnate, PATCH tracce, 140 test verdi.
- 2026-06-17: Deezer + AcousticBrainz aggiunti alla catena enrichment.
- 2026-06-15: import Spotify reale corretto, DB legacy ripulito, servizi status.
- 2026-06-15: classificazione transizioni e supporto modello economico Haiku 4.5.
- 2026-06-14: Rekordbox rimosso, cache enrichment, prompt AI arricchito, Discovery
  Last.fm-centric, import manuale, energia/mood deterministici.
