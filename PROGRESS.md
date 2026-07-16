# PROGRESS - development diary

> Work-resumption diary: chronology and resume points only. The **current state,
> priorities and decisions** live in `docs/ROADMAP.md` (source of truth). For
> orientation: `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `CLAUDE.md`.

## Current state

**Last updated:** 2026-07-16

**Product name:** **Cratory** (rename done on 2026-06-25 across UI, code, docs and
icon). "SetArc" and "DJ Assistant" remain only as historical names; legacy technical
paths (`djassistant.db`, log path) stay unchanged until a rename migration is planned.
`cratory.com` availability to be confirmed with a registrar.

**Phase:** streaming-first core complete; **disk-first complete** (the library is the
disk, streaming playlists = leads); **disk-first + Rekordbox paradigm pivot complete**
(internal enrichment engine and AcoustID fingerprinting retired toward Sortory, BPM/key
now only from a Rekordbox XML import, `energy` derived); **Analysis page complete**
(BPM/key gained a second deterministic source, in-app analysis via Essentia, alongside
Rekordbox import — explicit per-value provenance, `bpm_source`/`key_source`: manual >
rekordbox > cratory); Discovery operational (Last.fm expand + Discogs dig — the pile
is sorted by demand, `depth` picks the window to fetch from it, taste always ranks
inside that window); technical/creative Set Builder with an "owned-only" guarantee; dashboard
with a five-stage pipeline (Index moved to a nav button) and documentation realigned to
the new paradigm; mix identification via Shazam integrated (phase 1; co-occurrence in
backlog); SoundCloud import (playlists/secret links + selective likes) via yt-dlp; the
app is now bilingual IT/EN (language toggle in Settings).

## Milestone 2026-07-16 - Discovery: il dig pesca nella pila ordinata per domanda, non più in un campione arbitrario

Il dig cercava dischi su Discogs **senza chiedere alcun ordinamento**: scaricava le prime
300 release di un seme che poteva averne 43.345 — un campione arbitrario dello 0,69% in cui
non c'era nemmeno un disco con più di mille possessori e il 46% ne aveva meno di cinque.
Sopra quel campione applicava poi un punteggio raffinato, che non poteva rimediare a un
ingresso già sbagliato in partenza. Ridisegnato da zero, TDD, in una serie di commit sul
branch `feat/discovery-dig-riprogettato`:

- **Motore (`backend/app/services/discovery_dig.py`):** la pila di release del seme si
  ordina ora per domanda (`sort=want` desc, via `DiscogsClient.search_releases`);
  `_window(depth, total)` sceglie IN CHE PUNTO pescarci dentro — 0.0 = i classici del
  seme, 1.0 = il fondo della cassa (la pila regge per tutta la sua lunghezza: `want`
  mediano ancora ~89 a rango 10.000, misurato su `style=Acid House`). Il punteggio
  (`_score`) è ora **solo gusto** — familiarità graduata sull'artista, affinità di
  etichetta e di stile: `novelty`/`demand`/`recency` sono usciti dal punteggio (dentro una
  finestra il `want` è ~costante, non discriminava). Costo di rete: 4-5 richieste Discogs
  per dig (una sonda `count_releases` per l'altezza della pila + 3 pagine; +1 sonda se il
  seme `genre` ripiega da `style=` a `genre=`). Normalizzata anche la grammatica Discogs
  sugli artisti (suffissi `*`/`(N)`, split solo su separatori non ambigui) e il possesso è
  ora verificato pure sul titolo di release/EP, non solo di traccia.
- **API (`app/routers/discovery.py`, `app/schemas.py`):** `DiscoveryDigRequest.depth`
  (0.0-1.0) sostituisce `adventurousness`; `DiscoveryDigResponse.pile_pages` dice alla UI
  se la pila è più corta della finestra scelta (allora `depth` non ha effetto).
- **Design system frontend:** `Combobox` (un campo che suggerisce generi **ed** etichette,
  raggruppati), `SegmentedControl` e `Chip` estratti da tre copie duplicate dello stesso
  pattern; un `Popover` introdotto e poi rimosso (zero consumatori dopo il Combobox, YAGNI).
- **UI (`DiscoveryDigBar`):** una riga sola — Combobox unificato per il soggetto (il
  `seed_type` è dedotto da quale gruppo dell'autocomplete è stato scelto), profondità
  (Surface/Mid/Deep) e gusto (playlist di riferimento) pari grado; via il vecchio toggle
  "Scava per"/"Dig by". I filtri sui lead (formato, ordinamento) sono ora nell'intestazione
  dei risultati, non più nel form del dig.
- **E2E:** `frontend/e2e/smoke.spec.ts` aggiornato ai selettori nuovi (niente più toggle) +
  nuovo test per il deep link `?seed=label&value=...` che precompila il soggetto (trappola:
  `<select>` del gusto e `Combobox` del soggetto condividono il ruolo ARIA `combobox`,
  disambiguato prendendo il primo in ordine di riga).

Stato finale verificato (2026-07-16): backend 933 test verdi (anche a rete bloccata);
frontend 30 test unit su 5 file verdi, 13 e2e verdi (incluso il deep link), lint 0 errori
(4 warning preesistenti non correlati), `tsc --noEmit` e `next build` puliti.

## Milestone 2026-07-16 - Player delle tracce possedute (audizione rapida, read-only)

Nuova capacità deliberata che rivede la regola non-negoziabile "non riproduce audio":
Cratory ora riproduce in sola lettura i file delle tracce possedute (`has_local_file`),
per audizione rapida — non è un deck DJ, i file non vengono mai modificati (i tag restano
di Sortory).

- **Endpoint `GET /api/tracks/{id}/audio`:** streaming del file locale via `FileResponse`
  (supporto Range/seek). Sicurezza: il path risolto deve stare dentro le radici consentite
  da `file_search.search_roots()` (`LIBRARY_ROOT` + cartella download slskd), verificato con
  `path_within_roots`. Errori 404: `track_not_found`, `track_no_local_file`,
  `track_file_not_allowed`, `track_file_missing`.
- **Player docked unico condiviso:** generalizzato dal player di preview di Discovery, ora
  riproduce sia la preview effimera di terzi sia una traccia posseduta, una alla volta
  (niente coda). Componente riusabile `TrackPlayButton` sulle righe traccia; player montato
  a livello di app shell.
- Nessuna feature da DJ deck (waveform/cue restano al Set Builder/Rekordbox), nessuna
  transcodifica (stream raw; formati non supportati dal browser mostrano un messaggio).
- **Documentazione allineata** al cambio di rotta: `CLAUDE.md` (paragrafo Project + regola 7),
  `docs/API.md` (endpoint), `docs/ARCHITECTURE.md` e `docs/ROADMAP.md` (capacità e scope).

## Milestone 2026-07-13 - Bug d'uso reale (note dell'utente) + una scelta di design

Sei osservazioni segnate dall'utente usando l'app, verificate una a una nel codice e nel DB
reale, poi risolte a batch (5 subagent Sonnet paralleli, verifica integrata + live di Fable):

- **Grab manuale → "da rivedere" (bug):** `_attempt_download` applicava la guardia
  durata-diversa anche ai candidati scelti a mano; ora `enforce_duration` è attivo solo in
  auto-pick.
- **URL SoundCloud rotto (bug):** `normalize_soundcloud_item` salvava lo stream temporaneo
  (`playback.media-streaming.soundcloud.cloud`) invece della pagina; ora preferisce
  `webpage_url`/host `soundcloud.com`, `_apply_fields` ripara al re-sync, migrazione che
  azzera gli URL-stream esistenti (0 residui verificati).
- **Link Sortory rotto + copy (bug):** `ORGANIZER_URL` senza schema → link relativo; validator
  che antepone `http://`. Testo inbox riscritto senza il riferimento a DJPlayer.
- **Filtri persi tornando dal dettaglio (bug):** i link traccia portano `?from=<filtri>`, il
  "← Library" del dettaglio ci ritorna (useSearchParams + Suspense). Verificato live.
- **Transizioni prima/dopo identiche (design):** lo score è simmetrico → una sola lista
  "Tracce compatibili", endpoint unico `GET /api/transitions/{id}` (via `/after` e `/before`).
- **"Duplicati" Spotify+Disco:** verificato NON essere un bug — sono due file fisici (FLAC +
  MP3) della stessa canzone; lasciato invariato su decisione dell'utente.

Rifiniture di integrazione: eslint ora ignora `.next-e2e` (cache degli e2e che sporcava il
lint). Stato: 853 test backend verdi, 12 e2e + 4 unit frontend verdi, lint/tsc/build puliti.

## Milestone 2026-07-12 - Backlog audit SVUOTATO (sweep completo in giornata)

In un'unica giornata di lavoro a batch (subagent paralleli Sonnet orchestrati e verificati
da Fable, TDD sul backend, verifiche live nel browser per la UI) l'intero backlog audit
2026-07-05 e' stato chiuso: ~45 item implementati, 2 risolti per decisione (A7 confermato
com'e'; dead scores + POST /transitions/score rimossi), 2 parcheggiati deliberatamente
(tag Last.fm nel dig; dedup fixture E14). Dettaglio per-tema nella sezione storica di
ROADMAP; i commit della giornata raccontano i singoli item.

Punti salienti oltre ai fix: import/sync streaming come job in background (A10), robustezza
slskd (E6), drag-and-drop e "aggiungi traccia" nell'editor set, bande BPM percentuali, API
utilizzabili da qualsiasi dispositivo in LAN (B24), client api modulare con ApiError e
AbortController (B20-22), presidio test frontend (Playwright 12 route + Vitest jobs-provider,
E15), e tre bug reali scovati dai nuovi test (redirect OAuth multi-origine — fixato; scan
della libreria reale durante i test — guardia in conftest; lock mancante sullo stato del job
mix — implementato). Stato finale: 842 test backend verdi, 12 e2e + 4 unit frontend verdi,
lint/tsc/build puliti.

Lezione operativa registrata: alcuni subagent hanno riportato lavoro mai scritto su disco —
da allora ogni lancio richiede `git status --porcelain` nel report e la verifica avviene
solo sul working tree.

## Milestone 2026-07-12 - Quick-wins: correttezza silenziosa + igiene Discovery

Primo blocco post-ri-triage sul branch `fix/quick-wins-correttezza-discovery` (5 item, TDD sul
backend, verifica live nel browser per il frontend; suite backend 591 verde, lint/build FE ok).

- **E8** — `~` nei path di config (`library_root`/`archive_root`/`slskd_download_dir`) ora
  espanso via `field_validator`: prima un `~/Music` non risolveva e indicizzazione/download
  fallivano in silenzio.
- **E9** — helper `ci_equals` in `repositories.py`: `ilike(value)` grezzo trattava `%`/`_` del
  valore come wildcard. Cablato nei match esatti di `manual_import`, `playlist_import` (fallback
  per nome) e `library_index` (match fuzzy).
- **A11** — `_find_existing` ripiega ora anche su artista+titolo(+durata) per i lead senza
  identità forte (`_find_by_name`, guardia durata ±5s): una traccia importata a mano e poi da
  Spotify non diventa più un doppione. Rimosso il fallback per-nome duplicato in
  `import_single_track`.
- **A16** — `_drop_in_library` (expand) riusa `_dedup_key` del dig: possedere
  "Strobe (Original Mix)" scarta anche il candidato "Strobe"/"Strobe (Radio Edit)".
- **A27** — pulsante "Scava questa etichetta" nella pagina Label → `/discovery?seed=label&value=`
  (la Discovery accettava già il seed); i18n IT/EN. Verificato live: il dig parte sull'etichetta.
- **A15 scartata** dopo analisi: l'etichetta rientra via il ciclo possesso→Sortory→index;
  scriverla in Cratory confliggerebbe con la proprietà del campo di Sortory (indicizzazione:
  `label = label or tag`, non sovrascrive).

## Milestone 2026-07-12 - Audit backlog re-triaged against the code

The 2026-07-05 audit backlog had drifted from the code (several "still to do" items were
actually done). Re-verified item-by-item against the real code with a parallel multi-agent
pass (6 agents by theme: Discovery, Set→console/scoring, Shazam/Soulseek, Spotify/Library,
frontend technical, backend robustness/tests). New reality vs the old "~70 still valid": **~7
closed, ~20 partial, ~40 open**.

- **Closed since the audit** (removed from the backlog): A1 (set export M3U/CSV/markdown + real
  Blob download), A3 (the 7 Set Builder strategies now genuinely distinct), A8 (needs_review
  path persisted + retry/review flow), B5 (path to the editable set `/sets/[id]`), the dig's
  per-release tracklists (`get_release_detail`), B16 (label backfill removed — Sortory's job),
  E12-TLS (`tls12_context` opt-in/unused, not forced).
- **Docs aligned**: `docs/ROADMAP.md` audit-backlog section rewritten with per-theme OPEN/⚠️
  verdicts and evidence; "Next steps"/"Technical backlog" updated (per-release tracklists done).
  `docs/API.md` gained the two Discovery routes that already existed but were undocumented
  (`GET /api/discovery/release/{discogs_id}`, `POST /api/discovery/save-for-later`).
- No production code changed in this pass — verification + documentation only. Per-ID detail in
  `docs/AUDIT-2026-07-05.md` (dated re-verification header in ROADMAP).

## Milestone 2026-07-12 - Analysis page: BPM/key provenance + in-app analysis via Essentia

Spec and plan in `docs/superpowers/specs/2026-07-12-analysis-page-design.md` and
`docs/superpowers/plans/2026-07-12-analysis-page.md`. BPM/key gain a second deterministic
source (in-app analysis) alongside the Rekordbox import, with explicit per-value
provenance so the two sources and manual corrections never silently overwrite each
other. Cratory still never asks an AI for BPM/key.

- **Schema.** `Track.bpm_source`/`key_source` (`manual|rekordbox|cratory`, null if the
  value itself is null) with an idempotent backfill migration (existing BPM/key marked
  `rekordbox` if present, since that was the only prior source); staging columns
  `analysis_bpm`, `analysis_camelot`, `analyzed_at`, `analysis_error`, written only by
  the analysis job and read by nobody else until an explicit apply.
- **Manual edit is source-aware.** `PATCH /api/tracks/{id}` now sets
  `bpm_source`/`key_source = "manual"` when the payload touches `bpm`/`camelot_key`
  (`repositories.update_track`), so a manual correction outranks both Rekordbox and the
  in-app analysis until the user re-imports with `?overwrite=true`.
- **Rekordbox import made source-aware** (`services/rekordbox_import.py`). Default
  behavior changed: it still fills empty values, but now also reclaims values sourced
  from the in-app analysis (`cratory`) — since a Rekordbox re-analysis is more
  authoritative than the in-app one — while continuing to protect `manual` corrections.
  `?overwrite=true` still wins over everything. Every write is marked `source=
  "rekordbox"`.
- **Essentia adapter** (`integrations/essentia_engine.py`, lazy import, `is_available()`
  guard): `RhythmExtractor2013` (`multifeature`) for BPM, `KeyExtractor` (`edma` profile,
  tuned for electronic music) for key, converted to the project's canonical Camelot
  notation. Pinned `essentia==2.1b6.dev1389` (AGPL-3.0, last release with a cp311
  macosx-arm64 wheel — Essentia only publishes rolling `2.1b6.devN` builds with patchy
  wheel coverage); documented in `docs/DEPENDENCIES.md`.
- **Apply/divergence service** (`services/audio_analysis.py`): `diverges` (BPM at
  1-decimal precision, key exact), `apply_analysis` (unconditional copy, source
  `cratory`), `auto_apply_missing` (only into empty canonical fields, used by the job —
  no conflict possible), `divergence_row` (canonical vs analyzed + Camelot-wheel
  compatibility for the divergence table).
- **Background job** (`services/audio_analysis_job.py`): same in-memory
  single-job-with-lock pattern as `library_index_job`. `scope="missing"` (default) or
  `"all"`/explicit `track_ids`; writes only `analysis_*`, calls `auto_apply_missing` per
  track, commits per track (survives interruption), a per-track decode failure
  (`analysis_error="analysis_decode_failed"`) does not stop the batch.
- **Router `/api/analysis/*`** (`overview`, `start` [202/409/503], `status`,
  `divergences`, `apply` [with `force`]) — full contract in `docs/API.md`.
- **Frontend.** New page `/analysis` (coverage by source, inline Rekordbox XML upload,
  start-analysis action, divergence table with per-row/bulk apply); nav entry; the
  dashboard's "Analyze" pipeline stage now links to it; the analysis job joins the
  global job-progress bar poller (same pattern as indexing/downloads/Shazam). API
  client + IT/EN i18n strings added.
- Verification: 579 backend tests green, frontend lint/build clean.

## Milestone 2026-07-12 - Bilingual IT/EN (i18n)

The app is made bilingual Italian/English across three surfaces. A persistent language toggle
in Settings (key `language` in `AppState`, default `it`, endpoints
`GET/PUT /api/settings/language`); no per-locale routing.

- **UI**: TypeScript dictionary in `frontend/lib/i18n/` (`en.ts` the source of truth, `it.ts`
  typed `: Dictionary` → key parity enforced at compile time), `I18nProvider`/`useT()` +
  `runtime.ts` (language state outside React, no cycles with `lib/api.ts`). All
  pages/components migrated; final sweep to zero residual Italian UI strings.
- **Backend errors**: from Italian strings to stable codes via
  `api_error(status, code, message, **params)` (`app/core/http_errors.py`), translated by the
  frontend (`errors` namespace, `translateApiError`); backend language-agnostic. All routers
  migrated (~55 raises), `errors` catalog at IT/EN parity.
- **Generated phrases + AI**: per-language catalogs indexed by `get_language(db)`. Removed
  `label_it`; transition classification/reason, `technical_reasons`/`warnings`, mixing
  tip/overview, job phases and the AI agent's texts are now bilingual. The AI system prompts
  stay IT (instructions to the model); only the output-language directive is parametric.

Verification: 535 backend tests green, frontend build/lint clean, residual sweep at zero (UI,
Italian `detail=`, `label_it`). Live end-to-end verification in the deferred running app
(SQLite DB shared with the active parallel session). Spec and plan in `docs/superpowers/`.
Known limitation: `transition_reason` values saved in the DB at set generation stay in the
language active at that moment.

## Milestone 2026-07-11 - SoundCloud import via yt-dlp

The official SoundCloud API stays closed to new apps (Artist Pro required): no OAuth,
a workaround via a metadata-only yt-dlp client (never audio).

- **`integrations/soundcloud.py`.** Flat yt-dlp extraction (`extract_flat="in_playlist"`,
  `skip_download`), sequential fetches with no parallelism (low profile on an unofficial
  API). `fetch_playlist` (public or secret link) and `fetch_likes` (the user's likes, most
  recent first). URL guard: only http(s) on `*.soundcloud.com` hosts (anti-SSRF/file://),
  `is_likes_url` to reject `/likes` from the import-playlist flow.
  `SoundCloudError`/`SoundCloudInvalidUrl` (422 vs 502).
- **Normalizer.** `normalize_soundcloud_item` (services/playlist_import.py): flat entry ->
  `NormalizedTrack`, artist/title via split on `" - "` in the title with a fallback to the
  uploader, no ISRC (not exposed).
- **Likes services.** `preview_soundcloud_likes` (preview with `already_imported`, no
  import) and `import_selected_soundcloud_likes` (selective import, stateless: refetches and
  filters by id) into the system playlist "SoundCloud Likes".
- **Router `/api/soundcloud/*`.** `GET status`, `PUT config` (username, saved in
  `app_state`), `POST import` (playlist/secret link), `GET likes/preview`,
  `POST import/likes`. `409` if the username is not configured on the likes endpoints.
- **Per-platform sync.** `POST /api/playlists/{id}/sync` extended: SoundCloud always
  additive (never prunes, unlike Spotify — a takedown does not unlink the lead), only for
  playlists imported from a URL (likes are not re-syncable here, they only grow via the
  selective flow).
- **Frontend.** SoundCloud username in Settings; dedicated pages
  `/playlists/import-soundcloud` (import from URL) and
  `/playlists/import-soundcloud/likes` (likes selection with `already_imported`).
- Final verification: backend suite and frontend lint/build green (detail in the task
  report).

## Milestone 2026-07-09 - Genre coherence in the set generator

Genre becomes a first-class signal in set generation (it previously weighed ~3 points,
diluted in the average with energy).

- `genre_similarity_score` (scoring.py) now knows the **genre families** (deterministic
  map techno/house/breaks/dnb/chill/trance/bass/hiphop/pop_rock, whole-word match):
  subgenres of the same family are coherent even without common tokens
  (Ambient~Downtempo=80, Techno~Acid Techno=90), super-genres ("Electronic", "Dance")
  neutral at 55 (never a false reset), different families at 25 (below the reset threshold
  of 45). Fallback to the old token overlap for genres outside the map.
- Set generator: a **dedicated genre-coherence term** in the ranking (`_GENRE_WEIGHT=0.25`,
  like the energy arc), always active with neutral 50 when the data is missing;
  `_feature_fit` stays energy smoothness only.
- `StrategyProfile.genre_coherence` (default 1.0): experimental uses 0.5 so the novelty
  bonus keeps rewarding exploration. "Electro" is in the breaks family (not techno):
  techno→electro counts as a change of sonic world.
- Verified on a real DB: a smooth 60min set with 0 cross-family breaks over 8 transitions,
  BPM/key unchanged for quality. Test: `tests/test_genre_coherence.py` (9 tests), whole
  suite green. Commit `29d82c3` (note: landed on branch `discovery-dischi-tracklist` due to
  the parallel session; cherry-pick onto master if needed before the merge).

## Milestone 2026-07-08 - Disk-first DB hygiene: authoritative disk, no phantom leads, cleaned dashboard

Consolidation of the disk-first paradigm: the disk becomes the authoritative source for
the disk-derivable metadata of owned tracks, and "orphan leads" (no file, not in a playlist
nor a saved set) no longer survive in the DB.

- **Fuller tag reading + on-demand cover.** `read_tags` now also reads `label` (ID3 `TPUB`
  / Vorbis `LABEL`); indexing backfills `label` from disk only if absent. New `read_cover`
  + endpoint `GET /api/tracks/{id}/cover`: serves the artwork embedded in the owned track's
  file on-demand (not saved in the DB; covers FLAC/OGG, ID3 APIC, MP4 `covr`), `404` if
  absent. The frontend uses the Spotify cover (`album_art_url`) when present and falls back
  to the endpoint (new `TrackCover`/`trackCoverSrc`).
- **Hidden folders excluded everywhere.** `scan_folder` skips folders and files starting
  with `.` (`.quarantine`, `.DS_Store`, `.git`) in inbox/disk counting and indexing: they
  are not library content.
- **Index reconciliation with no phantom leads.** An ownership whose file the scan does not
  see — deleted, moved out of `LIBRARY_ROOT`, or landed in a hidden folder — is unlinked
  (`has_local_file=False`, `local_path` cleared) while keeping `audio_hash` for re-linking
  (even to a Spotify lead via ISRC/artist+title). If the track is in no playlist nor saved
  set it is **deleted** (`orphans_removed`); otherwise it stays a lead (`lost`).
- **Orphan-lead cleanup on playlist delete.** `DELETE /api/playlists/{id}` now returns
  `200` with `{deleted_tracks}` and removes the leads that became orphans (shared helper
  `delete_orphan_leads`/`unreferenced_track_ids` in `repositories.py`); tracks on disk or in
  another playlist/set stay.
- **One-off maintenance tool.** `backend/app/tools/cleanup_disk_first.py` (dry-run by
  default, `--apply` to write) on `backend/app/services/db_hygiene.py`: merges same-file
  duplicates, deletes orphan leads, clears the legacy residual fields on leads
  (`genre`/`bpm`/`camelot_key`/`energy`) and re-reads owned tracks from disk (authoritative
  disk; never touches Rekordbox BPM/key nor Spotify covers, read-only on files).
- **More robust match + duplicate merge.** New helper `merge_tracks(keep, drop)` (moves
  playlist/set membership, fills empty fields, deletes the duplicate). The **manual linking**
  of a file (`attach_local_file`) now merges the track that already owns that same file
  instead of leaving two rows. The automatic match (`_find_track`) adds a **normalized
  fuzzy** step (strips `feat.`/`(Original Mix)`/`- ... Remix`/diacritics) on file-less
  leads, with a **duration guard** (±7s), so cases like "Rápido & Lento ;) feat. Verraco
  (Original Mix)" link themselves to the Spotify lead. New **dedup by `audio_hash`**
  operation (`dedupe_by_audio_hash`) for already-existing duplicates, keeps the row with
  streaming identity (`spotify_id`/`isrc`).
- **Redesigned dashboard.** The four figures are now Discovered tracks / Owned tracks /
  Playlists / Saved sets; a new "Most frequent genres" stat (`stats.genre_distribution`,
  genres merged case-insensitively) whose rows link to the Library filtered by genre
  (`/library?genre=...`). Removed the "Next step" card and the three quick-action buttons.
  The pipeline strip drops to five stages: "Index" is now a button in the left nav (above
  Settings), no longer a strip stage; `GET /api/pipeline` loses
  `files_on_disk`/`index_mismatch`/`last_index_at` (keeps `inbox_files`).
- **Icon track status + Spotify green.** In the Library the per-row status moves from text
  badges to compact icons (ready=check, owned=hard drive, discarded=archive); the Spotify
  link uses a glyph in Spotify green — an exception documented under the Monochrome Rule (a
  brand affordance), alongside the danger red and the EQ loaders.
- **Dead-code removal.** Removed the last residuals of the legacy enrichment
  (`LastFmTagProvider`, `MusicFeatureProvider`), dropped the unused `Track.release_date`
  column (FK-safe migration). `Track.playlist_id`/`playlist_name` stay in the schema (FK
  baked-in, not droppable on SQLite) but dead and empty. Also removed the
  `libraryGaps`/`rekordboxPending` dead exports in `api.ts`.

## Milestone 2026-07-06 - Disk-first + Rekordbox pivot: enrichment on Sortory, BPM/key from Rekordbox, dashboard and docs

Product reorientation in three slices, executed on dedicated branches (`slice1a-*`,
`slice1b-*`, `slice2-import-rekordbox-xml`, `slice3-dashboard-e-documentazione`): text
metadata enrichment and on-disk tagging move entirely to Sortory; Cratory reacquires BPM/key
from a single explicit source, the Rekordbox XML export.

- **Slice 1A/1B — retirement of the enrichment engine.** Removed the internal enrichment
  engine (Deezer/MusicBrainz/AcousticBrainz/GetSongBPM/Last.fm chain), the AcoustID
  fingerprinting (`Track.mbid`, `POST/GET /api/library/fingerprint[/status]`) and the
  read-only bridge `GET /api/tracks/lookup` for Sortory: text enrichment and on-disk tagging
  are now exclusively Sortory's job. DB columns of the old engine (feature provider,
  enrichment cache, `mbid` and the like) dropped with an idempotent **FK-safe** migration in
  `db.py` (no data loss on linked `tracks`/`setlist_tracks`). Remaining external providers:
  **Discovery only** (Last.fm similarity, Discogs dig, Spotify resolver) — none supply
  BPM/key/genre/mood anymore.
- **Slice 2 — Rekordbox XML import.** New `rekordbox` router (`POST /api/rekordbox/import`,
  `GET /api/rekordbox/pending`): safe parsing (`defusedxml`) of the collection exported from
  Rekordbox, three-step matching of owned tracks (NFC-normalized path → `audio_hash`
  fallback, gated on the basename to avoid superfluous ffmpeg decodes → fuzzy artist+title),
  writing `bpm`/`camelot_key` **only if absent** (never overwritten). `energy` becomes a
  deterministic derived field (`services/energy`, BPM+genre): recomputed at Rekordbox import
  and on PATCHes that touch bpm/genre, no longer hand-editable (`TrackUpdateIn` with
  `extra="forbid"` → 422 if the payload contains it). Track states reduced to
  `imported | ready_for_set` (removed `enriched`, `missing_features`, `low_confidence`).
- **Slice 3 — Analyze dashboard + documentation.** `GET /api/pipeline` extended with
  `analyze_pending` (owned tracks without BPM or key); six-stage dashboard strip
  **Discover → Acquire → Organize⤴ → Index → Analyze⤴ → Play**, with an inline Rekordbox XML
  upload panel in the Analyze stage. Rewrote the live docs (`README.md`,
  `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/PRODUCT.md`, `docs/ROADMAP.md`) to remove
  every reference to active enrichment/fingerprint/bridge and reflect the new paradigm; API
  surface verified against the real routers.
- **`.env`:** removed the audio-provider/fingerprint keys (`MUSICBRAINZ_USER_AGENT`,
  `GETSONGBPM_API_KEY`, `DEEZER_ENABLED`, `ACOUSTICBRAINZ_ENABLED`, `ACOUSTID_API_KEY`);
  kept `SPOTIFY_*`, `LASTFM_API_KEY`, `DISCOGS_TOKEN`, `AI_*`, `SLSKD_*`, `LIBRARY_ROOT`,
  `ARCHIVE_ROOT`, `ORGANIZER_URL` (`backend/.env.example` updated).

## Milestone 2026-07-05 - End-to-end audit: dead-code cleanup + docs realignment

Multi-agent audit of the whole project (backend, frontend, integrations, tests, product):
~135 improvement proposals collected and prioritized (session report; the most relevant will
go into `docs/ROADMAP.md` once decided).

- **Dead code removed** (double verification: exhaustive grep + context/git): the ABCs
  `SoundCloudClient`/`MusicBrainzClient` and `get_artist` from the `SpotifyClient` interface;
  in `spotify.py` the batch fallback (`_get_many`, `get_tracks_batch`, `get_artists_batch`,
  `get_artist`) and the constants `BATCH`/`SEARCH_LABEL_MAX`/`SINGLE_GET_DELAY`;
  `ECONOMY_MODEL` (llm.py); `discogs_configured`; `all_dj_set_tracks`;
  `preferred_keys_sanity`; `_BPM_BUCKET`; `BPM_JUMP_WARN`; `local_import_root` (config never
  read). Frontend (`lib/api.ts`): `libraryGaps`, `discoveryAddToLibrary`, `startEnrichment`,
  the `LocalDirEntry` interface. Tests (432) and build green after the removal.
- **Deliberately kept**: `bpm_compatibility_score`/`key_compatibility_score` (the "six
  deterministic scores" contract of the spec, today only tests);
  `POST /api/transitions/score` (endpoint never called by the UI); the `python-multipart`
  dependency; the legacy columns `Track.playlist_id`/`playlist_name`.
- **Docs realigned to the code** (43 verified fixes): `API.md` (Pipeline section,
  `downloads/search`+`manual`, `create-from-tracks`, `GET /api/tracks` filters);
  `ARCHITECTURE.md`+`README.md` (AcoustID, disk-first, Soulseek free search, `tools/`,
  start-dev); `ROADMAP.md` (done state: disk-first batches A-D, pipeline, job bar, download
  archive, AcoustID, playlists from the library); `DESIGN.md` (EQ loader as a documented
  One-Red exception, typography, nav) +`PRODUCT.md` (disk-first model, Soulseek/Labels
  modules); `CLAUDE.md` (router list) and `.env.example` (`ACOUSTID_API_KEY`).

## Milestone 2026-07-05 - Download-issues archive + manual file linking

Persistent page for problematic downloads and ownership without a download; plan in
`docs/superpowers/plans/2026-07-05-download-issues-e-link-file.md`.

- **Page `/downloads/issues`**: persistent archive of tracks with a `not_found`/
  `needs_review`/`failed` outcome, filter by outcome with counters, per-row actions (Pick
  Soulseek file, Link local file, Ignore) and "Retry all". In `/downloads` the "To fix"
  section is now a summary with counters + a link.
- **Manual local-file linking**: `POST /api/tracks/{id}/link-file` validates the
  path/audio extension, reuses `attach_local_file` (best-effort audio-hash) and clears the
  download outcome; disk search with `GET /api/files/search` (`LIBRARY_ROOT` +
  `SLSKD_DOWNLOAD_DIR`, case-insensitive AND match, cap 50). Shared modal
  (`link-local-file-modal.tsx`) used by the archive and the track detail ("Link
  file"/"Replace file" in the Disk card).
- **Ignore**: `DELETE /api/downloads/pending/{track_id}` clears the outcome and reason.
- Refactor: the Soulseek review modal extracted into `download-review-modal.tsx` (wrapper +
  key pattern like TrackEditModal).

## Milestone 2026-07-05 - AcoustID fingerprinting + enrichment optimizations

Certain acoustic identity for owned files; plan in
`docs/superpowers/plans/2026-07-05-fingerprinting-acoustid.md`.

- **AcoustID fingerprinting** (`integrations/acoustid.py`, `services/fingerprint*.py`):
  audio -> MusicBrainz Recording MBID (column `tracks.mbid`), score threshold 0.85, caches
  definitive outcomes in `EnrichmentCache` (retryable errors). Endpoints
  `POST/GET /api/library/fingerprint[/status]`, a card in Settings, a job in the
  GlobalProgress bar. Requires `ACOUSTID_API_KEY` + `fpcalc` (chromaprint).
- **The enrichment chain uses the mbid**: direct MusicBrainz lookup `/recording/{mbid}` (no
  fuzzy, confidence 95, fallback to ISRC/search), AcousticBrainz receives it from the
  context. The mbid also backfills the ISRC of local files (unlocks Deezer for BPM).
- **Enrichment optimizations**: batch extended to `bpm IS NULL OR camelot_key IS NULL`
  (tracks without a key no longer stay orphans); AI genre in batch (one LLM call per 20
  tracks, `genre_ai` phase) caching the nulls too in `EnrichmentCache` (failed chunks not
  cached -> retryable); energy estimation moved after the genre (fixed bias); report with
  `ai_genres`.

## Milestone 2026-07-03 - Unified job bar (GlobalProgress)

All long operations go through the DJ bar at the bottom; spec approved in
`docs/superpowers/specs/2026-07-03-barra-job-unificata-design.md`.

- **JobsProvider single poller** (2s on the 4 status endpoints: enrichment, Shazam,
  download, library index); exposes the raw states to `/downloads` and Settings, which no
  longer have their own polling. Client jobs with `updateClientJob` (counts/detail); DIG and
  labels pass the detail.
- **UI**: stacked rows (max 3 + "+N"), label + ellipsized detail (current track via a new
  `current_label` on the download state, phase for enrichment/Shazam), big percentage
  `.tnum`, clickable row toward the job page, "hot" danger trail on the bars behind the
  playhead (`.eqm-hot`), dynamic anti-overlap spacer.
- **Visible outcome**: at the running→done/error transition the row stays 4s with the
  outcome ("N downloaded · M to fix", errors in danger), then disappears.
- "Download missing" from the playlist no longer redirects: you stay on the playlist, the
  progress lives in the bar.
- Verification: 386 backend tests green (new TDD test for `current_label`), frontend
  lint/build ok, bar lifecycle observed live on a real retry (appearance → track detail →
  50% → 4s outcome → disappearance).

## Milestone 2026-07-01/02 - Disk-first (slices 1-4)

Disk-centric reorientation: track ownership is no longer a side effect of the Soulseek
download alone, but the state of an actively-indexed canonical folder. Four slices,
developed on dedicated branches and then refined:

- **Slice 1 — identity and indexing** (branch `feat/disk-first-core`). `Track.audio_hash`
  (SHA-256 of the first seconds of the decoded stream via ffmpeg, stable to rename/retag),
  computed both by `attach_local_file` (Soulseek) and by the new `library_index` service.
  Config `LIBRARY_ROOT`; `library_index` does scan + match
  (`audio_hash -> legacy digest -> ISRC -> fuzzy artist+title`) + reconciliation (vanished
  files -> back to wishlist, hash kept for re-linking) + anti-unmount guard + `duplicates`
  counter (same hash in the same run, first wins). Exposed via `POST /api/library/index`
  (202, async job) + `GET /status`.
- **Slice 2 — ownership on the surface** (end of `feat/disk-first-core`, then
  `feat/disk-first-rifiniture`). Filter `has_local_file` + source `local_files` on
  `GET /api/tracks`; stat `with_local_file`; library with a "Wishlist (no file)" filter and
  a FILE badge (closes the old backlog "Tracks-without-file view"); a Settings card to launch
  indexing; an "Owned" figure in the dashboard.
- **Slice 3 — "owned-only" Set Builder** (branches `feat/set-builder-owned` and
  `feat/set-editor-owned`). `SetGenerationRequest.owned_only=True` by default in the
  Candidate Engine, persisted on `Setlist.owned_only`; the editor (alternatives, track
  replacement) respects the guarantee with 422 if the substitute is not owned; an "owned
  tracks only" toggle + badge in the UI, an "you own N of M" indicator in the playlist
  detail.
- **Slice 4 — Sortory bridge and copy** (branch `feat/lookup-endpoint`, then
  `feat/disk-first-rifiniture`). `GET /api/tracks/lookup` read-only for Sortory: ISRC ->
  fuzzy artist+title, confidence 100/70/0, always `limit(1)` (never `MultipleResultsFound`
  on duplicates), never 404 (`found: false`). UI copy: streaming playlists are presented as
  "leads", not as the library.

Tests: 333 backend tests green (`cd backend && .venv/bin/python -m pytest tests -q`).
Documentation aligned in the same pass: `README.md` (disk-first paragraph + `LIBRARY_ROOT`
in setup), `CLAUDE.md` (rule 9), `docs/ARCHITECTURE.md` (a "Disk-first" subsection),
`docs/ROADMAP.md` (slices 1-4 in "Done state", "Tracks-without-file view" moved from backlog
to done).

**Resume point:** branch `feat/disk-first-rifiniture` (final refinement, on top of
`feat/disk-first-core` + `feat/lookup-endpoint` + `feat/set-builder-owned` +
`feat/set-editor-owned`). Disk-first is closed end-to-end: indexing, UI surface, Set Builder
and Sortory bridge. Next open front: **Discovery improvement** (expand/dig unification,
Last.fm tags as a 2nd source, per-release tracklists) — unchanged.

## Milestone 2026-06-28 - Many-to-many playlists

The track-playlist relational model taken from 1:1 to M2M.

- `backend/app/models.py`: associative table `playlist_tracks` (`playlist_id`, `track_id`,
  `added_at`); SQLAlchemy relations `Playlist.tracks` / `Track.playlists`; legacy columns
  `Track.playlist_id` / `playlist_name` kept physically but emptied.
- `backend/app/db.py`: idempotent migration `_migrate_playlist_many_to_many` with a backfill
  of `playlist_tracks` from the legacy columns.
- `backend/app/repositories.py`: helpers `add_track_to_playlist`, `remove_track_from_playlist`,
  `tracks_for_playlist`, `recount_playlist`.
- `backend/app/services/`: Spotify and manual import, prune, delete-playlist and enrichment
  scoping ported to membership; `discovered-tracks` endpoint via membership.
- `backend/app/schemas.py` / `backend/app/serializers.py`: `TrackPlaylistRef`,
  `TrackOut.playlists[]`, eager-load.
- `frontend/`: "in N playlists" badge in the library (`/library`) and playlist list in the
  track detail; type `Track.playlists` in `lib/api.ts`.
- `backend/tests/`: tests for migration, two playlists, no-steal, prune, delete, endpoint,
  enrichment-scoping, serializer.

**Resume point:** branch `feat/playlist-many-to-many`. Next open front: Discovery (expand/dig
unification, Last.fm tags as a 2nd source, per-release tracklists).

## Milestone 2026-06-28 - Expansion in the Playlist context + Spotify write-back

Discovery reduced to **DIG only**; playlist expansion now lives in the Playlist context.

- Backend: `SpotifyWebClient.add_tracks(playlist_id, ids)` (POST `/playlists/{id}/tracks`);
  new endpoint `POST /api/playlists/{id}/discovered-tracks` that imports the candidate,
  attaches it to the playlist (1:1 model: does not move a track already elsewhere) and does a
  best-effort Spotify write-back (never blocking). Schemas
  `PlaylistAddTrackRequest/Response`.
- Frontend: new page `app/playlists/[id]/expand/page.tsx` (autorun without AI, AI toggle +
  Recompute); shared component `components/expand-results.tsx`; Discovery reduced to DIG
  (removed the mode switcher and the expand branch); the "Discover similar music" button in
  the playlist detail -> `/playlists/[id]/expand`. API client
  `addDiscoveredTrackToPlaylist`.
- Tests: `tests/test_playlist_add_track.py` (add_tracks + 5 endpoint cases: spotify/manual/
  unresolved/non-blocking error/no-move 1:1). 217 backend tests green; frontend lint 0
  errors, build ok; browser verification (Discovery DIG-only, expand page autorun without
  AI).

**Resume point:** branch `feat/espansione-in-playlist`. Residual Discovery backlog: Last.fm
tags as a 2nd dig source, per-release tracklists; many-to-many playlists.

## Milestone 2026-06-28 - Discovery dig: taste + explanations

Closed the "taste + explanations" slice of point 1 (Discovery improvement). The dig flow
only, deterministic, no AI nor new dependencies/network.

- `backend/app/services/discovery_dig.py`: new `TasteProfile` (artist_counts, owned_labels,
  genre_tokens) built from a reference (library or playlist); `_score` extended with graded
  familiarity + label affinity + style affinity (weights W_ARTIST 0.5 / W_LABEL 0.3 /
  W_STYLE 0.2); `Reason` + `_reasons` with constant thresholds. Dedup always library-wide,
  affinity on the reference.
- `backend/app/schemas.py`: `ReasonOut`, `reasons` on `DiscoveryLeadOut`, `taste_playlist_id`
  on `DiscoveryDigRequest`.
- `backend/app/routers/discovery.py`: `_lead_out` maps the reasons; `dig_endpoint` builds
  `taste_tracks` from `tracks_for_playlist` when `taste_playlist_id` is given.
- Frontend `lib/api.ts` (`Reason`, `reasons`, `tastePlaylistId`) and `discovery/page.tsx`
  ("Affinity relative to" selector + explanation chips).
- Tests: extended dig suite (TasteProfile, scoring, reason codes, library-wide dedup) +
  router tests; 211 backend tests green, frontend lint/build clean.

**Resume point:** branch `feat/discovery-dig-gusto-spiegazioni`. Residual Discovery backlog:
expand/dig unification, Last.fm tags as a 2nd source, per-release tracklists.

## Milestone 2026-06-18 - Documentation reset

- Reduced the documentation from six numbered specs to three stable documents:
  `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md`.
- Rewrote `README.md` as the entry point for setup, workflow and status.
- Slimmed `AGENTS.md` as an operational guide for agents.
- Compacted `PROGRESS.md` into a resumption diary.
- Kept `CLAUDE.md` as the entry point for the AI used together with Codex.
- Removed duplicate or empty Markdown: `frontend/README.md`, `IMPROVEMENTS.MD`, old specs
  `docs/01`-`06`.
- Chosen name: **SetArc**. Updated the documentation and the main user-facing strings,
  without renaming legacy technical paths.
- Roadmap realigned: the real test with keys already done, the AI model comparison already
  implemented, the gap-based Discovery section removed.

## Milestone 2026-06-23 - Editorial rebranding + Discovery labels

- Complete rebranding: "editorial archive" monochrome design system (IBM Plex Mono,
  hairlines, square), dark theme by default + paper via toggle (runtime `--c-*` +
  `@theme inline`), editorial shell `EditorialShell`/`PageLayout`, no-FOUC.
- "Command center" dashboard: hero figures, interactive BPM histogram, recent activity,
  enrichment coverage, quick actions.
- Global job progress bar (enrichment/shazam/label backfill) persistent across page changes.
- Labels: backfill from Spotify `copyrights` (dev mode), name normalization (`_clean_label`),
  variant merge at read-time.
- Discovery direction C: **Label Radar** (`POST /api/discovery/labels`, Spotify `label:`
  filter), a **label signal** on `/expand`, removal of "technical compatibility" (stays with
  the Set Builder). Controls in a horizontal bar. (Note: this `label:` endpoint was later
  removed on 27/06; the Radar uses Discogs.)
- Spotify import: owned playlists only; "Refresh" for the already-imported ones.
- Product direction decided: a **personal/self-hosted** tool, not a public SaaS (Spotify
  dev-mode constraint). Detail and consequences in `docs/ROADMAP.md`.
- Merged onto `master` and pushed. 186 backend tests green, frontend lint/build clean.

## Milestone 2026-06-27 - Light audit (quick wins)

- SSRF guard: the Shazam mix URL is validated (http/https only) before yt-dlp.
- Performance: `library_stats` rewritten with aggregate SQL queries (no ORM full-load),
  identical output; lightens the dashboard and the AI set context.
- Removed the dead endpoint `/api/discovery/labels` (+ `discover_by_labels`, helpers, schema,
  `search_by_label`, tests and the frontend function): the Label Radar uses Discogs.
- Dependencies: removed `requirements copia.txt`, version ceilings on the critical deps,
  shortened upstream error bodies. 197 backend tests green.
- Audit confirmed: CORS, secrets, retry/timeout, SQL injection and temp cleanup already in
  place; nothing else urgent for self-hosted use.
- (UI off-roadmap: DJ-style EQ/waveform loaders with breathing and narrow bars.)

## Milestone 2026-06-27 - Documentation rework

- Redesign of the doc architecture: every piece of information has a single canonical owner
  (`docs/ROADMAP.md` = state; `PROGRESS.md` = diary), no more double-truth.
- `README.md` rewritten as an English showcase (pitch, features, architecture, quickstart);
  new monochrome diagram `docs/architettura.svg`, orphan assets retired.
- `AGENTS.md` (root and frontend) unified into `CLAUDE.md` / `frontend/CLAUDE.md`
  (Claude-only toolchain, no Codex).
- `PRODUCT.md` and `DESIGN.md` moved into `docs/`; PRODUCT reconciled with the
  editorial-archive (lime out, deliberate paper theme); branding `SetArc -> Cratory` fixed in
  `.impeccable/design.json`.
- Accuracy audit: `docs/API.md` (Labels section, track enrich) and `docs/ARCHITECTURE.md`
  (Discogs, SpotifyToken, `db.py`) aligned to the code.
- Spec and plan in `docs/superpowers/specs|plans/2026-06-27-rifacimento-documentazione*`.

## Resume point

Full priorities and backlog in `docs/ROADMAP.md` (state source of truth). In short: settled
core, quick-win audit and documentation rework done; many-to-many playlists complete;
**disk-first complete** (slices 1-4: `LIBRARY_ROOT` indexing by `audio_hash`, ownership on
the surface, "owned-only" Set Builder, `GET /api/tracks/lookup` bridge for Sortory — branch
`feat/disk-first-rifiniture`). The next open front is **Discovery improvement** (expand/dig
unification, Last.fm tags as a 2nd source, per-release tracklists). EN i18n and public
multi-account stay suspended.

## Essential history

- 2026-06-17: Dashboard/Set Builder UI redesigned, track PATCH, 140 tests green.
- 2026-06-17: Deezer + AcousticBrainz added to the enrichment chain.
- 2026-06-15: real Spotify import fixed, legacy DB cleaned, status services.
- 2026-06-15: transition classification and support for the Haiku 4.5 economy model.
- 2026-06-14: Rekordbox removed, enrichment cache, enriched AI prompt, Last.fm-centric
  Discovery, manual import, deterministic energy/mood.
