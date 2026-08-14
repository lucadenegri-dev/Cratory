# Log di lavoro — Revisione totale codice e documentazione (2026-08-13)

Log condiviso tra i task del piano `docs/superpowers/plans/2026-08-13-revisione-codice-docs.md`.
Ogni task appende alla propria sezione; non riscrivere sezioni di altri task.

## Baseline (Fase 0)

Rilevata da Task 1, worktree `code-docs-review-plan-3345fa`, 2026-08-13 22:11 UTC.

Ambiente:
- `frontend/node_modules`: assente all'inizio (nessun symlink) → creato con `npm install` reale (446 pacchetti, 6s).
- Vulture installato nel venv principale (`$MAIN/backend/.venv`): `vulture-2.16`.

Metriche (Step 5, comando esatto nel brief del Task 1):

```
py files: 154, righe: 23962
ts files: 107, righe: 18395
endpoint: 148
deps pip: 18, deps npm: 19
    4509 total   (README.md + PROGRESS.md + CLAUDE.md + docs/*.md)
```

### Esito test di partenza

Stato di partenza: **completamente verde**, nessun rosso pre-esistente da segnalare.

**Backend — `pytest tests -q`** (cwd `$WT/backend`, venv `$MAIN/backend/.venv`):

```
1946 passed, 4 deselected in 32.36s
```

**Frontend — `npm run lint`** (cwd `$WT/frontend`):

```
✖ 4 problems (0 errors, 4 warnings)
```

0 errori, 4 warning pre-esistenti (non bloccanti):
- `app/library/page.tsx:135` — `react-hooks/exhaustive-deps` (dipendenza `limit` mancante in `useCallback`)
- `app/shazam/[id]/page.tsx:166` — `@next/next/no-img-element`
- `app/shazam/page.tsx:140` — `@next/next/no-img-element`
- `components/track-cover.tsx:29` — `@next/next/no-img-element`

**Frontend — `npm run build`** (Next.js 16.2.9, Turbopack):

```
✓ Compiled successfully in 1887ms
  Running TypeScript ...
  Finished TypeScript in 2.6s ...
✓ Generating static pages using 9 workers (27/27) in 168ms
```

27 route generate senza errori.

**Frontend — `npm run test:unit`** (vitest):

```
Test Files  32 passed (32)
     Tests  173 passed (173)
  Duration  5.53s
```

Conclusione: nessun rosso pre-esistente da attribuire a fasi successive. Qualsiasi
rosso comparso dopo il Task 1 è imputabile al lavoro dei task successivi.

## Fase 1 — Findings backend

Rilevato dal Task 2, worktree `code-docs-review-plan-3345fa`, 2026-08-13.
Metodo: **doppia conferma obbligatoria** — i tool statici producono CANDIDATI, mai
verdetti; nulla entra in L1 senza un grep indipendente su tutto il repo (test e docs
inclusi) che confermi zero referenze reali E senza aver escluso una convenzione di
framework (decorator FastAPI, campi Pydantic, colonne SQLAlchemy, re-export).

### Step 1 — vulture

```
cd $WT/backend && $MAIN/backend/.venv/bin/python -m vulture app --min-confidence 80 --sort-by-size
app/integrations/_http.py:211: unused variable 'exc_info' (100% confidence, 1 line)
app/services/local_import.py:24: unused import 'identity_normalize' (90% confidence, 5 lines)
```

Solo 2 voci a confidence 80. Passata aggiuntiva a `--min-confidence 60`: 100+ voci,
**tutte** riconducibili ai falsi positivi noti (colonne SQLAlchemy in `app/models.py` e
`app/organize/models.py`, campi Pydantic in `app/schemas.py` e `app/organize/schemas.py`,
attributi `updated_at`/`started_at`/`finished_at` scritti dai service). Nessuna promossa
a candidato.

Poiche' vulture non vede le funzioni morte in questo stack (i router sono referenziati
dai decorator), ho aggiunto due rilevatori AST scritti per l'occasione (read-only):
(a) censimento dei simboli top-level mai referenziati fuori dal proprio file;
(b) import mai usati come `ast.Name`. Da qui vengono i candidati non-endpoint sotto.

### Step 2 — censimento endpoint reali

Il comando del brief (`for r in app.routes: if hasattr(r,'methods')`) su questa versione
di FastAPI **restituisce solo 5 righe**: gli include_router sono avvolti in oggetti
`_IncludedRouter` (36 route totali, di cui 31 wrapper) e le APIRoute non sono al primo
livello. Censimento rifatto sullo schema OpenAPI, che e' la fonte autorevole:

```bash
cd $WT/backend && $MAIN/backend/.venv/bin/python -c "
from app.main import app
spec = app.openapi()
for path, ops in spec['paths'].items():
    print(sorted(m.upper() for m in ops if m.upper() in {'GET','POST','PUT','PATCH','DELETE'}), path)
" | sort
```

138 path unici / **149** coppie metodo+path. La baseline del Task 1 dice 148: la
differenza e' `GET /api/health`, registrato con `@app.get` in `app/main.py:130` e non con
`@router.*`, quindi invisibile al grep sui decoratori che ha prodotto il 148
(`grep -rE "@router\.(get|post|put|patch|delete)" app | wc -l` -> 148 esatti). 148 + 1 = 149.
Il Task 14, se riconta, deve aspettarsi 149.

```text
['GET'] /api/ai/status
['POST'] /api/analysis/apply
['GET'] /api/analysis/divergences
['GET'] /api/analysis/overview
['POST'] /api/analysis/start
['GET'] /api/analysis/status
['POST'] /api/discovery/add
['POST'] /api/discovery/dig
['GET'] /api/discovery/genres
['GET'] /api/discovery/preview
['GET'] /api/discovery/release
['POST'] /api/discovery/save-for-later
['GET'] /api/downloads/auto-link
['POST'] /api/downloads/candidates
['POST'] /api/downloads/discard-review
['POST'] /api/downloads/keep-review
['POST'] /api/downloads/manual
['GET'] /api/downloads/pending
['DELETE'] /api/downloads/pending/{track_id}
['POST'] /api/downloads/playlist/{playlist_id}
['POST'] /api/downloads/retry-pending
['GET'] /api/downloads/review/{track_id}
['POST'] /api/downloads/search
['GET'] /api/downloads/status
['POST'] /api/downloads/track
['POST'] /api/downloads/track/auto
['POST'] /api/downloads/track/soundcloud
['POST'] /api/files/pick
['GET'] /api/files/pick/availability
['GET'] /api/files/search
['GET'] /api/health
['GET'] /api/labels
['GET'] /api/library/genres
['POST'] /api/library/index
['GET'] /api/library/index/status
['POST'] /api/organize/analyze
['POST'] /api/organize/apply
['GET'] /api/organize/apply/status
['GET'] /api/organize/duplicates
['POST'] /api/organize/duplicates/{group_id}/dismiss
['POST'] /api/organize/duplicates/{group_id}/keeper
['GET'] /api/organize/files
['POST'] /api/organize/files/{file_id}/tags
['GET'] /api/organize/files/{file_id}/thumb
['POST'] /api/organize/fingerprint
['GET'] /api/organize/fingerprint/status
['POST'] /api/organize/genre-review
['GET'] /api/organize/genre-review/preview
['GET'] /api/organize/genre-review/status
['GET'] /api/organize/history
['POST'] /api/organize/history/{plan_id}/undo
['GET'] /api/organize/issues
['POST'] /api/organize/issues/ai-suggest
['POST'] /api/organize/issues/bulk
['GET'] /api/organize/issues/cover-thumb/{file_id}
['POST'] /api/organize/issues/detect-ratings
['POST'] /api/organize/issues/integrity-check
['GET'] /api/organize/issues/integrity-check/status
['POST'] /api/organize/issues/provider-override/accept-strong
['POST'] /api/organize/issues/provider-rescan
['GET'] /api/organize/issues/provider-rescan/status
['POST'] /api/organize/issues/provider-suggest
['POST'] /api/organize/issues/{issue_id}/fix
['POST'] /api/organize/issues/{issue_id}/status
['GET'] /api/organize/library/facets
['GET'] /api/organize/library/stats
['GET'] /api/organize/picker/availability
['POST'] /api/organize/picker/pick
['GET', 'POST'] /api/organize/plan
['POST'] /api/organize/scan
['GET'] /api/organize/scan/status
['GET', 'PUT'] /api/organize/settings
['GET', 'PUT'] /api/organize/settings/language
['GET'] /api/pipeline
['GET'] /api/playlists
['POST'] /api/playlists/create-from-tracks
['POST'] /api/playlists/import
['POST'] /api/playlists/import-manual
['POST'] /api/playlists/import/liked/selected
['GET'] /api/playlists/import/status
['GET'] /api/playlists/library/gaps
['GET'] /api/playlists/spotify/available
['GET'] /api/playlists/spotify/liked/preview
['POST'] /api/playlists/sync-all
['DELETE', 'GET', 'PATCH'] /api/playlists/{playlist_id}
['POST'] /api/playlists/{playlist_id}/add-tracks
['POST'] /api/playlists/{playlist_id}/duplicate
['POST'] /api/playlists/{playlist_id}/export
['GET'] /api/playlists/{playlist_id}/gaps
['PUT'] /api/playlists/{playlist_id}/order
['POST'] /api/playlists/{playlist_id}/reorder
['POST'] /api/playlists/{playlist_id}/sync
['GET'] /api/playlists/{playlist_id}/sync-log
['GET'] /api/playlists/{playlist_id}/tracks
['POST'] /api/playlists/{playlist_id}/tracks/remove
['DELETE'] /api/playlists/{playlist_id}/tracks/{track_id}
['POST'] /api/rekordbox/import
['GET'] /api/rekordbox/pending
['GET'] /api/services/status
['GET'] /api/sets
['POST'] /api/sets/generate
['POST'] /api/sets/generate-async
['GET'] /api/sets/generate-status
['DELETE', 'GET', 'PATCH'] /api/sets/{setlist_id}
['POST'] /api/sets/{setlist_id}/alternatives
['POST'] /api/sets/{setlist_id}/export
['POST'] /api/sets/{setlist_id}/tracks
['DELETE'] /api/sets/{setlist_id}/tracks/{position}
['POST'] /api/sets/{setlist_id}/tracks/{position}/move
['POST'] /api/sets/{setlist_id}/tracks/{position}/replace
['GET', 'PATCH'] /api/settings/config
['GET', 'PUT'] /api/settings/language
['PUT'] /api/settings/share-library
['POST'] /api/shazam/identify
['GET'] /api/shazam/identify-status
['GET'] /api/shazam/sets
['DELETE', 'GET'] /api/shazam/sets/{dj_set_id}
['POST'] /api/shazam/sets/{dj_set_id}/import-playlist
['GET'] /api/shazam/status
['POST'] /api/slskd/connect
['POST'] /api/slskd/disconnect
['GET'] /api/slskd/status
['PUT'] /api/soundcloud/config
['POST'] /api/soundcloud/import
['POST'] /api/soundcloud/import/likes
['GET'] /api/soundcloud/likes/preview
['GET'] /api/soundcloud/status
['GET'] /api/spotify/callback
['POST'] /api/spotify/create-playlist
['GET'] /api/spotify/login
['GET'] /api/spotify/status
['GET'] /api/stats
['GET'] /api/tracks
['GET', 'PATCH'] /api/tracks/{track_id}
['GET'] /api/tracks/{track_id}/audio
['GET'] /api/tracks/{track_id}/cover
['POST'] /api/tracks/{track_id}/link-file
['GET'] /api/transitions/{track_id}
```

### Step 3 — incrocio endpoint <-> chiamate frontend

Attenzione alle due basi diverse: `frontend/lib/api/*.ts` scrive il path **completo**
(`/api/...`), mentre `frontend/lib/organize/api.ts` usa `const API = "/api/organize"` e
scrive solo il **suffisso relativo** (`"/files"` -> `/api/organize/files`). L'incrocio e'
stato fatto due volte, una per convenzione, piu' una terza passata sul suffisso dopo il
path param (`/undo`, `/fix`, `/keeper`, ...): nessun endpoint con path param e' rimasto a
zero hit.

**Nota di metodo — difetto della passata 1, corretto dopo la review.** La passata 1
cercava il prefisso statico come **sottostringa nuda** (`grep -F "/api/sets/generate"`), quindi
ogni endpoint il cui path completo e' prefisso di un fratello vivo piu' lungo risultava
invisibile: `/api/sets/generate` matchava su `/api/sets/generate-async`. La passata 3 copriva
i path con `{param}` ma non quelli a suffisso piano. Ricontrollo rifatto su tutti i path non
parametrici con match **ancorato al terminatore** (prefisso seguito da `"`, `` ` `` o `?`):
una sola vittima, `POST /api/sets/generate`. Il difetto sbagliava in direzione "morto non
trovato", mai in direzione "vivo dichiarato morto", quindi non intacca le classificazioni
gia' fatte. (Attenzione se si ripete il controllo: anche il match ancorato ha falsi positivi,
p.es. `/api/rekordbox/import` e' vivo ma il call site termina con `${`
— `frontend/lib/api/misc.ts:57`.)

8 endpoint senza call site nel frontend; verificati uno per uno su frontend, backend/tests,
docs, script e possibili chiamanti esterni:

- `GET /api/health` — **non un finding**: chiamante esterno/umano, documentato in
  `README.md:120` come smoke check e usato nei curl di verifica dei piani.
- `GET /api/spotify/callback` — **non un finding**: e' il redirect OAuth di Spotify
  (`SPOTIFY_REDIRECT_URI` in `backend/.env.example:12`); per costruzione nessun `fetch`
  lo puo' chiamare. Il flusso e' `SPOTIFY_LOGIN_URL` (`frontend/lib/api/client.ts:9`) ->
  `<a href>` (`components/settings/services-list.tsx:63`) -> Spotify -> callback ->
  redirect a `/settings?spotify=connected` letto in `frontend/app/settings/page.tsx:20`.
- `GET /api/organize/issues/cover-thumb/{file_id}` — **non un finding**: falso negativo
  classico, non e' un `fetch` ma un `<img src>` costruito da `coverThumbUrl`
  (`frontend/lib/organize/api.ts:265`), usato in `components/organize/issues-table.tsx:77`
  e `:83` e `components/organize/plan-ops.tsx:48`.
- `POST /api/downloads/search`, `POST /api/downloads/manual` — nessun chiamante e chiamanti
  cancellati di proposito, ma restano richiamabili via curl: **L3, candidati alla promozione
  a rimozione al checkpoint di Fase 1** (vedi L3 per l'evidenza a favore e contro).
- `GET /api/rekordbox/pending`, `POST /api/organize/analyze` — dubbi, vedi L3.
- `POST /api/sets/generate` — trovato solo dal ricontrollo ancorato: wrapper HTTP morto sopra
  un servizio vivissimo, stessa forma di `/api/organize/analyze`. Vedi L3.

**Tutti gli endpoint sono finiti in L3, nessuno in L1** — ma per due ragioni diverse, da non
confondere al checkpoint: `/api/downloads/search`, `/api/downloads/manual` e
`/api/rekordbox/pending` sono L3 **per dubbio** (la regola "in dubbio → L3, l'utente potrebbe
chiamarlo via curl": l'asimmetria del rischio e' netta, da L3 l'utente li promuove con una riga
di conversazione, da L1 se ne accorge quando gli si rompono); `/api/organize/analyze` e
`/api/sets/generate` sono L3 **per morte accertata ma superficie di prodotto** — sono wrapper
HTTP dimostrabilmente non chiamati sopra servizi vivi, e cio' che li tiene fuori da L1 non e'
l'incertezza sul fatto che siano morti ma il fatto che rimuovere un endpoint documentato sia
una decisione di prodotto (e, per `analyze`, il vincolo su `organize/`).

### Step 4 — dipendenze pip

```
== fastapi: 121   == uvicorn: 0     == sqlalchemy: 318  == pydantic: 14
== pydantic_settings: 1  == dotenv: 1  == multipart: 0  == ruamel: 3
== yaml: 0        == pytest: 102    == httpx: 17        == anthropic: 3
== yt_dlp: 4      == shazamio: 1    == mutagen: 25      == defusedxml: 1
== essentia: 5    == acoustid: 6    == PIL: 4
```

**Nessuna dipendenza morta.** I tre zero sono tutti spiegati:
`uvicorn` e' invocato da CLI (`start-dev.sh`, README); `python-multipart` e' usato
internamente da FastAPI e serve davvero — `app/routers/rekordbox.py:25` dichiara
`file: UploadFile = File(...)`, senza il pacchetto l'endpoint fallisce a runtime;
`yaml` e' zero perche' il pacchetto in uso e' `ruamel.yaml` (3 hit), non PyYAML.

### Findings L1 — rimozione (Task 3)

Import inutilizzati (confermati sia dal rilevatore AST sia da grep sul file):

- [L1] `app/services/local_import.py:15` — `from sqlalchemy.orm import Session` — grep sul file: 1 sola occorrenza (l'import); il modulo non ha nessuna funzione con parametro `db`
- [L1] `app/services/local_import.py:19` — `LocalFilesError` — le uniche altre 2 occorrenze nel file sono una docstring (`:56`) e un commento (`:67`), nessun `raise`/`except`
- [L1] `app/services/local_import.py:26` — `identity_normalize` — vulture 90%; i test lo importano da `app.services.playlist_import`, mai da `local_import`; `app/services/__init__.py` e' vuoto (0 byte), nessun `__all__`
- [L1] `app/services/local_import.py:27` — `import_playlist` — l'unica altra occorrenza e' la docstring di modulo (`:4`), che descrive un flusso rimosso
- [L1] `app/services/mix_identify.py:22` — `field` da `dataclasses` — 1 sola occorrenza nel file; `dataclass` e' usato, `field(default_factory=...)` no
- [L1] `app/services/pipeline.py:18` — `from app.core.config import settings` — 1 sola occorrenza; il modulo usa `runtime_settings` (`:17`, `:69`), non `settings`; `pipeline.settings` ha 0 hit nei test
- [L1] `app/organize/services/text_providers.py:8` — `DiscogsMetaClient` — import a livello di modulo mai usato (i provider sono iniettati da `resolve()`); tutti gli altri call site lo importano **dentro le funzioni** (`app/organize/routers/issues.py:202`, `genre_review_job.py:39`, `provider_rescan_job.py:41`), come prescritto da `docs/superpowers/plans/2026-07-07-force-provider-rescan.md:21`
- [L1] `app/organize/services/text_providers.py:9` — `MusicBrainzProvider` — identico al precedente

Simboli morti:

- [L1] `app/schemas.py:472` — `class LocalDirEntry(BaseModel)` — grep su tutto il backend: **1 hit, la definizione**; 0 hit nel frontend; il suo consumatore `LocalBrowseResponse` non esiste piu'; nessun `response_model=`, nessun `list[LocalDirEntry]`. `PROGRESS.md:1209` registra che l'interfaccia gemella nel frontend era gia' stata cancellata come codice morto
- [L1] `app/services/ai_curation.py:120` — `_safe_library_context()` — unico hit in `backend/app` e' la definizione, 0 test, 0 `getattr`; il chiamante previsto `ai_agent.py` non esiste piu'. **Cascata:** rimuovendola resta orfano anche l'import `library_stats` a `app/services/ai_curation.py:16` (usato solo a `:121`)
- [L1] `app/services/local_import.py:55` — `build_normalized()` — unico hit in `backend/app` e' la definizione, **0 hit nei test**; il chiamante storico `import_local_folder` e' stato cancellato; i consumatori superstiti del modulo importano solo `scan_folder` (`library_index.py:39`, `pipeline.py:21`, `tests/test_local_import.py:10`). E' la causa dei 4 import morti qui sopra. **Cascata completa per il Task 3:** rimuovendolo resta orfana anche la costante `PLATFORM` (`app/services/local_import.py:32`, usata solo a `:69` dentro `build_normalized`; `library_index.py:44` ne ha una copia propria indipendente, da **non** toccare). Inoltre nello stesso modulo `import logging` (`:11`) e `logger = logging.getLogger(__name__)` (`:30`) sono **gia' morti oggi**, indipendentemente da questa rimozione: `logger` non ha nessun uso nel file. Vanno via nella stessa passata, altrimenti il file resta con tre righe inerti
- [L1] `app/services/audio_energy.py:113` — `backfill_energy()` — 0 chiamanti di produzione; gli unici usi sono `tests/test_audio_energy.py:141` (import) e `:155` (call), quindi test che coprono SOLO codice morto. `library_index.py:30` importa da questo modulo solo `analyze_file, recompute_energy`
- [L1] `app/services/soulseek_select.py:251` — `best_for_auto()` — unico hit in `backend/app` e' la definizione; usi solo in `tests/test_soulseek_select.py` (import `:3`, chiamate `:38,45,76,91,108,131`). E' un wrapper di comodo su `rank_candidates`+`auto_pick_candidates` che la produzione scavalca (`soulseek_download_job.py:24`, `routers/downloads.py:18` importano le due primitive)

**Esito Task 3 sui test dedicati** (righe originarie prima dell'esecuzione; annotato per il
checkpoint di Fase 1 / verifica del Task 14):

- `tests/test_audio_energy.py` — `test_backfill_only_untouched_owned_tracks` (`:139-160`):
  **cancellato**, copriva solo `backfill_energy` (commit `31aec1a`).
- `tests/test_soulseek_select.py` — `test_best_for_auto_picks_strong_lossless` (`:43-47`):
  **cancellato**; lo scenario (match esatto lossless, confidence >= 0.7) resta comunque coperto
  dal test riscritto `test_durata_ignota_resta_neutra`, che usa lo stesso file
  `Daft Punk - Da Funk.flac` (commit `7f98173`).
- `tests/test_soulseek_select.py` — `test_best_for_auto_returns_none_below_threshold` (`:35-40`):
  **riscritto** come `test_nome_plausibile_ma_imperfetto_escluso`, contro `rank_candidates`
  diretto (`ranked == []`, comportamento reale verificato eseguendo lo scorer). Prima cancellato
  per errore nel commit `7f98173` con una motivazione sbagliata (si credeva coperto da
  `test_auto_pick_candidates_vuota_se_tutti_sotto_soglia`, che pero' costruisce lo
  `ScoredCandidate` a mano ed esercita solo il filtro, mai lo scorer); corretto in review nel
  commit `a73e041`.
- `tests/test_soulseek_select.py` — `test_name_match_uses_basename_not_full_path` (`:70-78`):
  **riscritto** contro `rank_candidates` diretto, stessa asserzione sulla soglia di confidenza
  (commit `7f98173`).
- `tests/test_soulseek_select.py` — `test_nome_file_con_underscore_riconosciuto` (`:84-92`):
  **riscritto**, idem (commit `7f98173`).
- `tests/test_soulseek_select.py` — `test_artista_quasi_uguale_nella_cartella_padre` (`:102-110`):
  **riscritto**, idem (commit `7f98173`).
- `tests/test_soulseek_select.py` — `test_durata_ignota_resta_neutra` (`:128-133`):
  **riscritto**, idem (commit `7f98173`).

**Cascata `build_normalized`/`_safe_library_context` (righe sopra), completata oltre il testo
qui scritto.** Verificato con la stessa metodologia (grep repo-wide, 0 hit, doppia conferma) e
confermato dalla review indipendente del Task 3: orfani anche `NormalizedTrack`, `read_tags`,
`audio_hash`, `parse_line` (`local_import.py`, usati solo dentro `build_normalized`, commit
`afc06a4`) e `Session` (`ai_curation.py`, usato solo nella firma di `_safe_library_context`,
commit `276a454`) — stesso meccanismo gia' descritto per `PLATFORM`/`library_stats`. Le
definizioni restano vive altrove (`playlist_import.py:39`, `local_files.py`, `manual_import.py:30`)
e i gemelli omonimi non sono stati toccati (`PLATFORM` sopravvive in `library_index.py:44`,
`read_tags` ha un gemello vivo e indipendente in `app/organize/integrations/tagio.py:392`).

(Nessun endpoint classificato L1: i due candidati piu' forti, `POST /api/downloads/search`
e `POST /api/downloads/manual`, sono stati declassati a L3 — vedi sotto.)

### Findings L2 — consolidamento (Task 4)

Nessun L2 tocca `app/organize/` (vincolo del piano).

- [L2] `app/routers/sets.py:228-236` + `app/routers/playlists.py:449-458` — blocco di render M3U8 duplicato quasi verbatim (unica differenza: il set itera `SetlistTrack` e dereferenzia `.track`); l'output byte-per-byte e' identico, commento italiano compreso. `playlists.py:400-403` ammette la duplicazione a parole ("stessa logica dell'export set"). **Entrambi i siti sono fissati dai test**: `tests/test_playlist_export.py:30,48,64` e `tests/test_set_texts.py:126,174`. Fusione meccanica: `render_m3u8(tracks, total)`
- [L2] `app/routers/playlists.py:78` + `app/routers/spotify.py:47` — `_http_error(exc: SpotifyError)` **byte-identico** (verificato con `diff`: nessuna differenza). Fusione meccanica: spostarlo accanto ad `api_error` in `app/core/http_errors.py`. **Caveat onesto:** la mappatura non e' asserita da nessun test a livello router — `tests/test_streaming_import_job.py:210-256` asserisce gli stessi tre codici ma sullo `state["error_code"]` del job, altro code path. Il Task 4 aggiunga un test per sito prima di fondere. Da **non** fondere con `app/routers/soundcloud.py:32`: altra famiglia di eccezioni, altri codici (sarebbe una decisione di design)
- [L2] `app/services/auto_link.py:20` (`_label`) + `app/services/soulseek_download_job.py:54` (`_track_label`) — corpi identici (3 righe), differisce solo il nome. Entrambi coperti: `tests/test_auto_link.py` e `tests/test_soulseek_download_job.py` (asserisce `current_label`). La localizzazione delle stringhe italiane hard-coded e' fuori scope: fondere, non tradurre
- [L2] `app/services/audio_analysis_job.py:39` + `app/services/streaming_import_job.py:76` — `_spawn(fn)` identico, docstring compresa. Entrambi monkeypatchati dai test (`test_audio_analysis_job.py:22`, `test_streaming_import_job.py:24`, `test_job_double_start.py:215`, ...). Fusione meccanica in un helper condiviso
- [L2] `app/routers/sets.py:161` (`_fmt_dur`) + `app/routers/playlists.py:436` (stessa espressione inline, stesso fallback `"—"`) — chiamare `_fmt_dur` anche dal ramo markdown delle playlist. Il resto dei rami CSV/markdown/testo e' genuinamente diverso e **non** va fuso

**Esito Task 4:** 5 dei 6 finding L2 fusi (vedi commit `refactor(revisione): consolida ...`
uno per finding, `.superpowers/sdd/task-4-report.md` per il dettaglio). Il sesto
(`_norm` discovery_dig/manual_import) e' stato **retrocesso a L3**, vedi sotto — non
per un ostacolo emerso a meta' fusione, ma perche' la sua stessa condizione dichiarata
("fondere solo se il Task 4 crea comunque un modulo di util testuali") non si e'
verificata.

### Candidati scartati (falsi positivi, per tracciabilita')

- `app/integrations/_http.py:211` `exc_info` (vulture **100%**) — **falso positivo**: e' il varargs di `def __exit__(self, *exc_info)`, protocollo context manager di `ClosableHttpClient` (`:189`). Rimuoverlo rompe ogni `with client:` con `TypeError`; `tests/test_integrations_http.py:125` percorre esattamente quel path. Al massimo si rinomina in `*_`, ma non e' codice morto
- `app/main.py:88` `log_requests` — middleware registrato dal decorator `@app.middleware("http")`
- ~100 "unused variable" di vulture a confidence 60 in `models.py`/`schemas.py` — colonne SQLAlchemy e campi Pydantic dichiarativi
- Tutti gli handler dei router — referenziati solo dai decorator

### Findings L3 — segnalazione, nessuna azione automatica

Retrocesso dal Task 4 (era L2, non fuso):

- [L3] `app/services/discovery_dig.py:43` (`_norm`) + `app/services/manual_import.py:26` (`_norm`) — one-liner identico (`(value or "").strip().lower()`), entrambi coperti (`test_discovery_dig.py`, `test_manual_import.py`). Il finding L2 originale condizionava esplicitamente la fusione ("fondere solo se il Task 4 crea comunque un modulo di util testuali"): il Task 4 non ha creato un simile modulo per nessuno degli altri cinque finding (`export_render.py` e' formattazione di export, non normalizzazione testuale; `http_errors.py` e' HTTP; `track_label.py` e' un'etichetta d'interfaccia; `job_spawn.py` e' avvio thread) — la precondizione non si e' avverata, quindi nessuna fusione. Resta valida l'ATTENZIONE originale: gli altri 7 helper `_norm`-simili nel backend sono tutti diversi e portanti (`candidate_engine.py:19` NFKD+ASCII, `library_index.py:53` strip `feat.`/`(Original Mix)`, `soulseek_select.py:73` `&`->`and`, `playlist_import.py:107` casefold alnum, `preview.py:38` ritorna un set, `rekordbox_import.py:76` NFC+normpath, `scoring.py:594`) — **non** toccarli

Duplicazione core <-> `app/organize/` (il piano vieta L2 in `organize/`: qui solo L1 o L3;
nessuno di questi e' morto, quindi tutti L3 — richiedono una decisione dell'utente):

- [L3] `app/services/genre_norm.py` ≡ `app/organize/services/genre_norm.py` — **byte-identici** (37 righe, `diff` vuoto). Entrambi vivi. Fondere significa comunque toccare `organize/`
- [L3] `app/services/native_picker.py` ≡ `app/organize/services/native_picker.py` — **byte-identici** (93 righe, `diff` vuoto). Entrambi vivi
- [L3] `app/core/http_errors.py` vs `app/organize/core/http_errors.py` — due `api_error()`; la versione organize e' un superset (parametro `headers` per il Cache-Control delle thumb). Fondibile solo adottando il superset, ma tocca `organize/`
- [L3] `app/integrations/_http.py` (212 righe) vs `app/organize/integrations/_http.py` (44 righe) — due fork divergenti dello stesso helper di retry HTTP: la versione core ha il workaround TLS 1.2 e i docstring, quella organize ha in piu' `post_with_retries`. Nessuna delle due e' un sottoinsieme dell'altra
- [L3] `GET /api/files/pick/availability` + `POST /api/files/pick` vs `GET /api/organize/picker/availability` + `POST /api/organize/picker/pick` — quattro endpoint, due router quasi verbatim (`app/routers/files.py:41-56` vs `app/organize/routers/picker.py` intero); differiscono solo per il prefisso, il nome dell'handler e da quale copia di `native_picker`/`http_errors` importano. Entrambe le coppie sono chiamate dal frontend
- [L3] `GET|PUT /api/settings/language` vs `GET|PUT /api/organize/settings/language` — **due store di lingua indipendenti per una app monoutente**, con default diversi: core usa `app_state` chiave `language` con default `"it"` (`app/services/app_state.py:47-54`), organize usa la colonna `Settings.language` con `DEFAULT_LANGUAGE` = EN (`app/organize/services/planning.py:42-54`). Evidenza aggiuntiva: i client organize `getLanguage`/`setLanguage` (`frontend/lib/organize/api.ts:514-519`) **non hanno nessun chiamante nel frontend** (0 hit) — la UI usa solo `/api/settings/language` (`frontend/lib/i18n/index.tsx:37,58`). Unificare e' una decisione di prodotto, non un merge meccanico

Endpoint senza chiamante ma non rimovibili d'ufficio:

- [L3] `GET /api/rekordbox/pending` (`app/routers/rekordbox.py:15`) — 0 call site nel frontend (la UI legge lo stesso numero da `/api/analysis/overview` e `/api/pipeline`; `frontend/components/analysis/rekordbox-import-card.tsx:57` lo dice in un commento), coperto solo da `tests/test_rekordbox_api.py:64`, e `docs/API.md:31,83` ammette la duplicazione. **Non L1** perche' `docs/superpowers/specs/2026-07-12-analysis-page-design.md:114` decise esplicitamente di tenerlo, ed e' un `GET` banale richiamabile via curl: rimuoverlo ribalta una decisione presa
- [L3] `POST /api/organize/analyze` (`app/organize/routers/analyze.py:11`) — 0 call site nel frontend (ho enumerato tutti i suffissi di `frontend/lib/organize/api.ts`: `/analyze` non c'e'), non documentato in nessun `.md`, coperto solo da `tests/organize/test_analyze_api.py:24,72,102`. Il **service** `analysis.recompute()` e' vivissimo (`organize/services/scan_job.py:71`, `integrity_job.py:45`): morto e' solo il wrapper HTTP. **Non L1** perche' e' in `organize/` ed e' un plausibile trigger manuale via curl per ricalcolare gli issue senza rifare la scansione del disco
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/routers/sets.py:127` — `POST /api/sets/generate` (handler `generate`) — **stessa forma di `/api/organize/analyze`: wrapper HTTP morto sopra un servizio vivissimo.** 0 call site nel frontend, che usa solo la coppia asincrona (`frontend/app/set-builder/page.tsx:160` -> `/api/sets/generate-async`, `frontend/lib/api/sets.ts:6` -> `/api/sets/generate-status`); 0 copertura HTTP nei test (tutte le occorrenze `sets/generate` in `tests/` sono `-async`/`-status`; gli altri 20+ hit chiamano il **servizio** `generate_set`/`run_curated_generation` direttamente, non l'endpoint); grep ancorato `'/api/sets/generate"'` su frontend + tests + docs: 0 hit. Documentato in `docs/API.md:401`. **Non L1** perche' rimuovere un endpoint documentato e' una decisione di prodotto: e' plausibile che l'utente lo chiami via curl per una generazione sincrona senza polling. Se promosso, il servizio resta e va toccato solo il router. **Decisione dell'utente al checkpoint: rimuovere.** Rimosso solo il router; `generate_set`/`run_curated_generation` intatti, usati da `/generate-async`. Il test `test_router_uses_curated_pipeline`, che chiamava l'handler direttamente, e' stato riscritto contro `_run_generation` (stessa garanzia di instradamento use_ai, ora sull'unico punto vivo). `docs/API.md` aggiornato
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/routers/downloads.py:240` — `POST /api/downloads/search` (handler `search`) — **candidato alla promozione a rimozione: decisione utente al checkpoint di Fase 1.** A favore della rimozione: 0 call site nel frontend, e il wrapper `searchDownloads()` in `frontend/lib/api/downloads.ts` e' stato cancellato di proposito nel commit `a56b60e` ("feat(wishlist): link a slskd al posto della ricerca libera"), il cui messaggio dice "Rimosso il codice morto: ... wrapper API searchDownloads/downloadManual"; nella UI e' stato sostituito dal link esterno "Apri slskd" (`web_url` di `/api/slskd/status`); coperto solo da `tests/test_downloads_router.py:84,101,124,154`. Contro: l'utente ha rimosso i chiamanti **lasciando in piedi l'endpoint**, che e' un POST richiamabile a mano via curl su una app self-hosted, ed e' documentato per intero in `docs/API.md:722,751-755`. Regola del piano "in dubbio → L3": vince l'asimmetria del rischio. Da non confondere con `POST /api/downloads/candidates`, che e' vivo (`frontend/lib/api/downloads.ts:28`). **Decisione dell'utente al checkpoint: rimuovere.** Rimossi i 4 test che coprivano solo questo endpoint; `docs/API.md`/`docs/ARCHITECTURE.md` aggiornati
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/routers/downloads.py:264` — `POST /api/downloads/manual` (handler `download_manual`) — **candidato alla promozione a rimozione: decisione utente al checkpoint di Fase 1**, inseparabile dal precedente (stesso commit `a56b60e` ha cancellato `downloadManual()`, stessa motivazione pro e contro; documentato in `docs/API.md:723,756-759`); 0 call site, coperto solo da `tests/test_downloads_router.py:161,176`. **Se promossi, cascata per il Task 3:** restano orfani `SearchIn` (`downloads.py:62`), `ManualDownloadIn` (`downloads.py:66`) e `start_manual_job()` (`app/services/soulseek_download_job.py:357`); **NON** rimuovere `_slskd_file` (`:98`) ne' `_candidate_out` (`:90`), che servono anche a `/track` (`:192`) e `/candidates` (`:166`); aggiornare `docs/API.md:722-758` e `docs/ARCHITECTURE.md:134,152-153` nella stessa passata (Task 11/12). **Decisione dell'utente al checkpoint: rimuovere.** Cascata eseguita come previsto: `SearchIn`, `ManualDownloadIn`, `start_manual_job()` rimossi; `_slskd_file`/`_candidate_out` intatti. Rimossi i 2 test dedicati; `docs/API.md`/`docs/ARCHITECTURE.md` aggiornati

Script one-shot gia' applicati in `app/tools/` (0 importer in `backend/app`; decisione utente:
sono documentazione eseguibile di migrazioni passate o zavorra?):

- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/tools/align_genre_from_file.py` — la docstring dice "una-tantum"; 0 importer, 0 test. Il payload `db_hygiene.align_owned_genre_from_file` resta usato da `app/services/genre_align.py:9` e coperto da `tests/test_db_hygiene.py:145-195`: cancellare la CLI non perde logica testata. Citato in `PROGRESS.md:48,65`, `docs/ARCHITECTURE.md:207,360`, `docs/ROADMAP.md:104`. **Decisione dell'utente al checkpoint: rimuovere.** Script cancellato, `db_hygiene.align_owned_genre_from_file` intatto e coperto dai test esistenti; `docs/ARCHITECTURE.md` aggiornato (i riferimenti in `PROGRESS.md`/`docs/ROADMAP.md` sono diario storico, non toccati)
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/tools/backfill_track_files.py` — backfill della migrazione F3, gia' applicata; 0 importer, 1 test (`tests/test_backfill_track_files.py:8`) che coprirebbe solo codice morto. **Decisione dell'utente al checkpoint: rimuovere.** Script e i suoi 3 test cancellati (coprivano solo la CLI stessa)
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/tools/cleanup_disk_first.py` — la docstring dice "una-tantum", `PROGRESS.md:1128` dice "One-off maintenance tool"; 0 importer, 0 test. Tutte le op che orchestra sono coperte in `tests/test_db_hygiene.py`. **Decisione dell'utente al checkpoint: rimuovere.** Script cancellato, le operazioni di `db_hygiene.py` che orchestrava restano e restano coperte da `tests/test_db_hygiene.py`; `docs/ARCHITECTURE.md` aggiornato
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/tools/migrate_organize_db.py` — migrazione F2 (DB unico) gia' applicata; 0 importer, 1 test (`tests/test_migrate_organize_db.py:12`). **Decisione dell'utente al checkpoint: rimuovere.** Script e i suoi 14 test cancellati (coprivano solo la CLI stessa)
- [L3 — **evaporato, Task 5b**] `app/tools/backfill_track_files.py:98` + `app/tools/merge_duplicate_tracks.py:70` — `_sessione()` con corpo identico (differisce solo la docstring). Estrazione meccanica in `app/tools/_common.py`, ma contingente: se i one-shot vengono cancellati il problema evapora. Confermato: `backfill_track_files.py` e' stato rimosso al Task 5b, quindi non c'e' piu' duplicazione da estrarre — `merge_duplicate_tracks.py` e' l'unico sopravvissuto con `_sessione()`
- [L3] **Da NON toccare in `app/tools/`**: `clean_user_data.py` (unico tool documentato all'utente, `README.md:186`) e `merge_duplicate_tracks.py` (riparazione ricorrente, non one-shot; l'unico "riferimento" trovato dallo scan e' un commento in prosa a `backfill_track_files.py:101`, ora orfano — lo script citato non esiste piu'). Confermato intoccato al Task 5b

Emerso dalla review del Task 5b (codice morto di seconda generazione, conseguenza
diretta delle rimozioni sopra — nessuno di questi era nella cascata autorizzata, quindi
non toccato in quella passata):

- [L3] `app/services/db_hygiene.py`: `dedupe_by_audio_hash` (:41), `purge_lead_residue`
  (:64), `realign_owned_from_disk` (:102) e `align_owned_genre_from_file` (:132) hanno
  **zero chiamanti di produzione** da quando `app/tools/cleanup_disk_first.py` e
  `app/tools/align_genre_from_file.py` sono stati rimossi (Task 5b): le uniche
  referenze rimaste in `backend/app/` sono due righe di docstring
  (`app/services/genre_align.py:9` cita `align_owned_genre_from_file` come "il backfill
  retroattivo"; `app/services/db_hygiene.py:135` cita `realign_owned_from_disk` a
  confronto). Ogni chiamata reale e' nei test (`tests/test_db_hygiene.py`), che restano
  verdi e non se ne accorgono: la suite non segnala codice morto, lo segnala solo
  l'assenza di importer in `app/`. Non rimosso in questa passata: fuori dalla cascata
  autorizzata per il Task 5b, che elencava solo i quattro script CLI
- [L3] `app/services/soulseek_download_job.py:246` — il ramo `if track_id is None:`
  dentro `_run()` (con `_process_manual()`) e' diventato irraggiungibile in produzione
  dopo la rimozione di `start_manual_job()` (Task 5b, unico chiamante che passava
  `track_id=None`). **Non e' orfano di test**: `tests/test_soulseek_download_job.py:157`
  (`test_manual_download_lascia_il_file_senza_catalogare`) chiama
  `job._run([(None, file)], None)` direttamente ed e' vivo e verde — asserisce che il
  download manuale lascia il file sul disco senza catalogarlo in Cratory. Questo rende
  ancora piu' netta la decisione di non toccarlo nella cascata del Task 5b (era fuori
  scope autorizzato, e cancellarlo avrebbe portato via un test vivo): ma chi fara' la
  prossima passata mirata su questo file deve sapere che il ramo morto viaggia insieme
  a un test che lo esercita, non da solo

Ridondanza architetturale profonda (fusione = decisione di design, esplicitamente fuori
da una passata meccanica):

- [L3] Cinque macchine a stati di job scritte a mano: `app/services/audio_analysis_job.py:21`, `app/services/streaming_import_job.py:46`, `app/services/soulseek_download_job.py:36`, `app/services/mix_identify_job.py:19`, `app/routers/sets.py:64`. Una classe base unificata richiede di decidere: (a) la disciplina di lock (due leggono `_state` senza lock, due con lock e con `_state_snapshot` per la non-reentrancy), (b) la forma del payload di stato (5 shape diverse), (c) la semantica della start-guard (tre ritornano lo stato corrente se gia' in corso, `routers/sets.py:107-113` alza deliberatamente 409 con commento che spiega perche'), (d) i response model gia' fissati da `tests/test_job_response_schemas.py:141`. Il solo `_spawn` e' stato estratto come L2 sopra
- [L3] Idioma "carica o 404" ripetuto ~40 volte nei router (`routers/playlists.py:173,241,265,303,318,336,356,404,...`, `tracks.py:90,128,150,175`, `sets.py:157,176,320`, `dj_sets.py:124,136,149`, `downloads.py:127,189,208,232,279,288,302`, `transitions.py:31`, `spotify.py:119`). Il fix idiomatico (`Depends(get_playlist_or_404)`) romperebbe i test che invocano gli handler **direttamente** anziche' via HTTP (es. `tests/test_playlist_export.py:38` chiama `export_playlist(pl.id, "m3u8", db)`): una `Depends` non si risolve in chiamata diretta. Decisione di design, non pulizia
- [L3] `app/services/set_generator.py:33` — `_STRATEGY_PROFILES` re-esportato da `set_skeleton` ma importato da nessuno (0 hit fuori da `set_skeleton.py`). **Non L1** perche' sta dentro un blocco marcato `# noqa: F401 - re-export per compat test` deliberato: la convenzione spiega l'apparente inutilizzo. Il gemello `_DEFAULT_PROFILE` nello stesso blocco e' invece portante (5 file di test lo importano da `set_generator`) e va lasciato
- [L3] `file_tags_for_tracks(db, [x.id]).get(x.id)` ripetuto 5 volte (`routers/downloads.py:132,294,304`, `routers/discovery.py:313,330`) — manca un wrapper `file_tags_for_track` accanto a `app/repositories.py:203`. Meccanico ma cosmetico

Schema DB (intoccabile per definizione nel piano):

- [L3] Le ~100 voci di `vulture --min-confidence 60` su `app/models.py`, `app/organize/models.py`, `app/schemas.py`, `app/organize/schemas.py` sono colonne SQLAlchemy e campi Pydantic dichiarativi. Alcune sono effettivamente scritte e mai lette dal backend (es. `Track.playlist_name`, `analysis_error`, i vari `updated_at`), ma lo schema non si tocca e il frontend puo' leggerle via i response model: nessuna azione, solo segnalazione

## Fase 2 — Findings frontend

Rilevata dal Task 6. Tutte le conferme sono state rifatte con `/usr/bin/grep`: vedi
l'avvertenza sotto, il `grep` della shell e' inaffidabile su questi pattern.

### ATTENZIONE metodologica — il `grep` della shell falsa gli zeri

In questa shell `grep` e' una **funzione che avvolge ugrep** (`type grep` ->
`shell function from ~/.claude/shell-snapshots/...`), che differisce dal binario in due
modi rilevanti per questo lavoro.

**1. Un `^` in testa dentro un gruppo di alternanza non viene onorato.** Il trigger e'
solo il `^`, non il `$`: isolato su `lib/i18n/en.ts`, cercando `none`,

| pattern | wrapper | `/usr/bin/grep` |
|---|---|---|
| `none([^A-Za-z0-9_]\|$)` — solo `$` | 3 hit | 3 hit |
| `(^\|[^A-Za-z0-9_])none` — solo `^` | **0 hit** | 3 hit |
| `(^\|[^A-Za-z0-9_])none([^A-Za-z0-9_]\|$)` — il pattern del brief | **0 hit** | 3 hit |

Quindi il pattern ancorato prescritto dal brief restituisce **zero anche quando il simbolo
c'e'**. E' lo stesso "falso zero" di cui avvisa il piano, per un'altra causa. Attenzione a
non generalizzare oltre il dovuto: `\bNOME\b` funziona, e cosi' l'ancoraggio con il solo `$`
— chi ha provato a riprodurre il bug con quelli ha concluso, sbagliando, che non esistesse.

**2. Il wrapper onora `.gitignore` (ugrep `--ignore-files`), il binario no.** Su una ricerca
ricorsiva della cwd in `frontend/`, `grep -rl webpack .` trova **2** file e
`/usr/bin/grep -rl webpack .` ne trova **1338** (la differenza e' `.next/`). Un path
ignorato passato **esplicitamente** viene invece letto da entrambi. Non ha inquinato i
risultati di questo task — ogni ricerca qui nomina esplicitamente `app components lib tests e2e`,
nessuna delle quali e' in `.gitignore` — ma su una ricerca "a tappeto" i due comandi
rispondono a domande diverse.

**Chi fa i Task 7-8 usi `/usr/bin/grep` (o `command grep`) per ogni controgrep ancorato.**
Le conferme di questa sezione sono state tutte rieseguite col binario vero.

### Step 1-2 — knip e depcheck

`npx knip` (nessun config, plugin Next auto-rilevato): **0 file inutilizzati**,
**0 dipendenze inutilizzate**, 10 export inutilizzati, 21 tipi esportati inutilizzati,
1 "duplicate export". Nessun falso positivo App Router da scartare: knip riconosce da
solo `page.tsx`/`layout.tsx`/`route.ts`/i config/`e2e/**`.

`npx depcheck`: due sole segnalazioni, **entrambe falsi positivi**, e knip non le
conferma (la regola del brief richiede che le flagghino tutti e due):
`@tailwindcss/postcss` e' il plugin dichiarato in `postcss.config.mjs:3`, `tailwindcss`
e' importato da `app/globals.css:1` (`@import "tailwindcss"`). **Nessun finding sulle
dipendenze npm.** Controllati anche gli altri config dove i plugin non si importano:
`@vitejs/plugin-react` + `jsdom` (`vitest.config.ts:2,8`), `eslint-config-next`
(`eslint.config.mjs:2-3`).

Controprova indipendente sui file orfani: per ogni file di `components/` e `lib/` ho
cercato un importatore (path assoluto `@/...` e relativo). Nessun orfano — concorde con knip.

### Findings L1 — rimozione (Task 7)

Export morti di `lib/organize/api.ts` (knip + controgrep ancorato con `/usr/bin/grep` su
`app components lib tests e2e`: **unica occorrenza la definizione**; nessun import
namespace `import * as` nel frontend, quindi non esiste accesso dinamico `api["nome"]`):

- [L1] `lib/organize/api.ts:164` — `scanJobStatus()` — knip: unused export; grep ancorato: 1 hit, la definizione. `components/jobs-provider.tsx:16` importa `startScan` ma **non** lo stato: la riga scan della barra job non esiste apposta (commento a `jobs-provider.tsx:243`: e' lo stesso job di `library-index`, letto dall'altro endpoint)
- [L1] `lib/organize/api.ts:514` — `getLanguage()` — knip: unused export; grep ancorato: 1 hit. **Gia' segnalato dalla Fase 1** (vedi L3 `GET|PUT /api/settings/language` sotto): la UI usa solo `/api/settings/language` via `lib/i18n/index.tsx:37,58`
- [L1] `lib/organize/api.ts:517` — `setLanguage()` — identico al precedente
- [L1] `lib/organize/api.ts:534` — `fingerprintStatus()` — knip: unused export; grep ancorato: 1 hit. `components/settings/services-list.tsx:11` importa solo `runFingerprint`. **Cascata per il Task 7:** resta orfana anche `interface FingerprintStatus` (`lib/organize/api.ts:522`), il cui unico uso e' l'annotazione di ritorno a `:535` (knip la flagga gia' oggi fra i tipi inutilizzati)
- [L1] `lib/organize/api.ts:561` — `pickerAvailability()` — knip: unused export; **doppione morto** di `lib/api/settings.ts:20` (stessa docstring parola per parola, cambia solo il path: `/picker/availability` sotto la base organize vs `/api/files/pick/availability`). L'unico consumatore, `components/path-picker-button.tsx:4`, importa da `@/lib/api` (barrel `lib/api.ts:15` -> `./api/settings`). Coerente con la consolidazione gia' fatta: `tests/componenti-unici.test.tsx` asserisce che `components/organize/path-picker-button.tsx` non esiste piu'
- [L1] `lib/organize/api.ts:565` — `pickPath()` — identico al precedente, doppione di `lib/api/settings.ts:25`

Re-export morto:

- [L1] `lib/i18n/index.tsx:11` — `export { getCurrentLanguage, translateApiError, translateGap } from "./runtime";` — **due dei tre nomi non hanno nessun consumatore da qui**: i due call site reali importano direttamente da `./runtime` (`lib/api/client.ts:1`, `lib/organize/api.ts:1`). Enumerati tutti i `from "@/lib/i18n"` del repo: prendono `useT`/`useI18n`/`I18nProvider`/`type Dictionary`/`type Language` e, in due file soli, `translateGap` (`app/playlists/[id]/page.tsx:30`, `components/dashboard/gaps-list.tsx:3`). Azione: **restringere la riga a `translateGap`**, non cancellarla

Keyword `export` superflua (il simbolo e' vivo, lo e' solo dentro il proprio file):

- [L1] `components/confidence-badge.tsx:7` — `export const DUBIOUS_CONFIDENCE_THRESHOLD = 60` — knip: unused export; grep ancorato: 2 hit, la definizione e l'uso a `:13` **nello stesso file**. Nessun test lo importa. Via solo la keyword `export`, la costante resta

Chiavi i18n morte. **Vanno rimosse in coppia da `en.ts` e `it.ts`** (`it.ts` si tipizza
con `typeof en`: una rimozione a senso unico rompe `npm run build`). `tests/i18n-organize.test.ts:24`
pretende `> 100` foglie sotto `organize` — oggi sono **312**, le 9 rimozioni qui sotto
non lo avvicinano nemmeno. Prima di classificarle ho enumerato **tutti** gli accessi
dinamici al dizionario esistenti nel repo (`/usr/bin/grep -rnE "\bt\.[a-zA-Z.]*\["`
piu' `DICTIONARIES[...]`): sono solo `errors[code]` e `gaps[gapType]` (`lib/i18n/runtime.ts:28,41`),
`setBuilder.presets[p.key]`, `setBuilder.strategies[s.key]`, `sets.modes[...]`,
`transitions.lenses[l.key]`, `transitionLabels[...]`, `settings.servicesMeta[s.key]`,
`organize.files.field[f]`, piu' `discovery[...]` con chiavi letterali. **Nessuno dei
namespace toccati qui sotto e' indicizzato dinamicamente, e nessuno e' aliasato o
destrutturato** (verificato: zero `= t.downloads`, `t.downloads[`, template literal
`` `filter${ `` ecc.).

- [L1] `lib/i18n/en.ts` + `it.ts`, namespace `downloads` — **18 chiavi** superstiti della vecchia pagina `/downloads`, cancellata nel commit `26e35c3` ("feat(wishlist): nav e redirect — /downloads diventa /wishlist, vecchia pagina rimossa") e sostituita da `app/wishlist/page.tsx`, che usa il namespace `wishlist`. Grep ancorato con `/usr/bin/grep`: 0 hit per `downloads.<chiave>` in `app components lib tests e2e`. en.ts/it.ts: `pageTitle` 392/391, `acquisitionHeading` 394/393, `singleDownloadHeading` 395/394, `filterByOutcomeAria` 396/395, `filterAll` 397/396, `filterNeedsReview` 398/397, `filterNotFound` 399/398, `filterFailed` 400/399, `outcomeNotFound` 401/400, `outcomeNeedsReview` 402/401, `outcomeFailed` 403/402, `emptyTitle` 418/417, `emptyBody` 419/418, `reviewButton` 420/419, `chooseFileButton` 421/420, `linkFileButton` 422/421, `ignoreButton` 423/422, `ignoreConfirm` 424/423. **Restano vive e NON si toccano** nello stesso namespace: `notConfigured` (`app/wishlist/page.tsx:150`), `failedReason` (`components/wishlist-row.tsx:50`), `linkAllButton` (`page.tsx:174`), `retryAllButton` (`page.tsx:171`) e tutto il sotto-oggetto `review.*` (11 membri, `components/download-review-modal.tsx:84-149`). **Trappola:** `downloads.filterAll` (397) e' omonimo ma distinto da `organize.files.filterAll` (1296), che e' un finding separato qui sotto; e `default:` dentro `failedReason` (en.ts:413) **non e' una chiave** — e' la clausola di uno `switch`, un falso positivo dell'estrattore: rimuoverla rompe il tipo di ritorno della funzione
- [L1] `common.none` (en 41 / it 38) e `common.retry` (en 43 / it 40) — 0 hit `common.none`/`common.retry`. Enumerazione esaustiva di `t.common.*` realmente usati: `cancel, confirm, delete, error, inProgress, loading, save, search`. (Il nome nudo `none` ha 107 hit e `retry` 1, ma sono classi CSS `select-none`/`pointer-events-none`, union di tipi e il path `/api/downloads/retry-pending` — nessun accesso al dizionario: e' esattamente il caso in cui il grep sul nome nudo mente)
- [L1] `discovery.closePreview` (en 840 / it 840) — 0 hit. La chiusura dell'anteprima e' passata al player condiviso, che usa `t.player.close` (`components/docked-player.tsx:99`)
- [L1] `playlists.marginaliaOptions` (en 559 / it 558) — 0 hit; le marginalia in uso sono `marginaliaSource`/`marginaliaNotes`/`marginaliaDetails`
- [L1] `settings.soulseekReconnect` (en 157 / it 156) — 0 hit; `components/settings/services-list.tsx:154,158` rende solo `soulseekDisconnect`/`soulseekConnect`, un pulsante "riconnetti" non esiste. Da non confondere con `t.settings.reconnectButton` (en.ts:64), che e' vivo e serve ai servizi OAuth
- [L1] `organize.common.none` (en 1222 / it 1220) e `organize.common.retry` (en 1224 / it 1222) — 0 hit. `t.organize.common.*` realmente usati: `all, backendOffline, cancel, coverProposed, empty, error, guide, save, summary`
- [L1] `organize.jobs.scan` (en 1234 / it 1232) — 0 hit. `t.organize.jobs.*` usati: `apply, genreReview, integrity, providerLookup`. La riga scan nella barra job non esiste per scelta (`components/jobs-provider.tsx:243`)
- [L1] `organize.files.filterAll` (en 1296 / it 1294) — 0 hit; il `<Select>` che la usava e' stato rifatto e ora rende `t.organize.common.all` (`app/organize/files/page.tsx:165`). Il gemello `filterIssues` (en 1297) e' invece **vivo** (`app/organize/files/page.tsx:206`) e non si tocca
- [L1] `organize.files.sortPath/sortArtist/sortTitle/sortBitrate/sortDuration` (en 1298-1302 / it 1296-1300) — 0 hit. Erano le `<option>` di un `<Select>` di ordinamento previsto da `docs/superpowers/plans/2026-07-16-unify-sources-files.md:374-379`, poi sostituito da intestazioni di colonna cliccabili (`components/organize/files-table.tsx:78-83`). I valori sono nella forma `"sort: path"`/`"ordina: path"`, che non e' il testo di un'intestazione: non sono la traduzione mancante del nuovo controllo, sono le etichette di un controllo che non c'e' piu'. (Che le nuove intestazioni siano inglesi hard-coded e' un buco i18n separato, segnalato L3 sotto). **Ripiego dichiarato, per il checkpoint:** questi cinque sono il confine piu' discutibile di tutta la Fase 2 — hanno lo stesso profilo di `themePaper`/`themeDark` (chiave orfana + UI hard-coded in inglese), e li separa solo l'argomento sulla forma del valore. Se al checkpoint quell'argomento non convince, **la mossa prudente e' spostare tutti e cinque in L3**, non rimuoverli: il costo di sbagliare in questa direzione e' cinque chiavi morte in piu' nel dizionario, nell'altra e' chiudere un buco i18n al contrario
- [L1] `organize.plan.applyingLabel` (en 1479 / it 1476) — 0 hit; `app/organize/plan/page.tsx:55` calcola `applying` ma rende solo `computing` (`:83`), il progresso dell'apply vive nella barra job globale
- [L1] `organize.issues.forceProvider` (en 1373 / it 1371) — 0 hit; sostituita da `forceLookupToggle`/`forceLookupHint` (`app/organize/issues/page.tsx:468,472`)

**Seconda passata i18n — 15 chiavi in piu', trovate rigenerando le candidate coi percorsi
qualificati.** La prima passata usava lo script del brief, che cerca il **nome della foglia
nudo** (`rf"\.{k}\b"`): una chiave morta il cui nome foglia e' omonimo di una chiave viva in
un altro namespace **non diventa mai candidata**, quindi la doppia conferma non ci gira
nemmeno sopra. E' la trappola del prefisso un livello piu' su — non `TrackCard` dentro
`TrackCardCompact`, ma `organize.common.close` nascosto dietro `t.common.close`. Rilevatore
rifatto sui **percorsi dotted completi** (foglie estratte eseguendo `en.ts` con `tsx`, non
con una regex), alias-aware ed escludendo le famiglie a indicizzazione dinamica: 1411 foglie,
173 escluse perche' dinamiche, **52 candidate qualificate** contro le 34 della prima passata.
Le 18 nuove sono le 15 qui sotto piu' `organize.common.never`/`organize.nav.themePaper`/
`themeDark`, gia' classificate L3. Verificati anche **tutti** gli alias di sotto-oggetto
esistenti nel repo (sono 6: `isc`, `isf`, `im`, `likes`, `liked`, `g` — tutti su
`playlists.import*` e `setBuilder.guide`, nessuno sui namespace toccati qui) e le
destrutturazioni da `t.` (zero). Ogni chiave sotto e' a **0 hit** per
`t.<percorso.completo>` in `app components lib tests e2e` con `/usr/bin/grep`.

- [L1] `common.close` (en 36 / it 33) e `common.all` (en 40 / it 37) — 0 hit. Sono i due omonimi che la prima passata si e' persa: il nome `close` e' vivo come `t.player.close`/`t.organize.*`, `all` come `t.organize.common.all` (`app/organize/files/page.tsx:165`). Enumerazione esaustiva dei `t.common.*` vivi: `cancel, confirm, delete, error, inProgress, loading, save, search` — invariata rispetto alla prima passata, che infatti aveva gia' individuato `none` e `retry` nello stesso oggetto
- [L1] `organize.common.loading` (en 1213 / it 1211), `browseButton` (1215/1213), `close` (1217/1215), `confirm` (1218/1216), `delete` (1219/1217), `search` (1220/1218), `inProgress` (1229/1227) — 7 chiavi, tutte a 0 hit, tutte con un gemello vivo di primo livello che le nasconde al grep sul nome nudo (`t.common.loading`, `t.settings.browseButton`, `t.common.confirm`, ...). **Trappola verificata:** i test che asseriscono `"Sfoglia…"` (`tests/link-local-file-modal.test.tsx`, `tests/settings-config-card.test.tsx`) rendono `t.settings.browseButton` (it.ts:139) via `components/path-picker-button.tsx:47`, **non** la copia organize (it.ts:1213): restano verdi. Con queste, di `organize.common` muoiono 9 membri su 18; restano vivi `all, backendOffline, cancel, coverProposed, empty, error, guide, save, summary`
- [L1] `organize.nav.tagline` (en 1241 / it 1239), `organize.nav.settings` (1247/1245), `organize.nav.toggleTheme` (1248/1246) — 0 hit. Sono **residuo pre-fusione**: la shell autonoma di Sortory (tagline, link alle impostazioni, toggle tema) e' stata assorbita, e `tests/organize-cluster-morto.test.ts` gia' asserisce che `components/organize/{editorial-shell,index-nav,clock,theme-toggle}.tsx` non esistono piu'. Di `organize.nav` sopravvivono solo le 5 voci di sezione (`files, issues, duplicates, plan, history`). **Perche' queste tre sono L1 e `themePaper`/`themeDark` no:** `tagline` e `toggleTheme` hanno un **gemello di primo livello vivo** — `t.nav.tagline` (`components/index-nav.tsx:91`) e `t.nav.toggleTheme` (`components/theme-toggle.tsx:32`) — quindi la copia organize-scoped e' puro doppione senza nessuna decisione appesa; `themePaper`/`themeDark` un gemello di primo livello **non ce l'hanno**, ed e' esattamente li' che vive la decisione (vedi L3 sotto). `organize.nav.settings` non ha nemmeno un consumatore possibile: la pagina `/organize/settings` non esiste piu' (fusione F5, cfr. `e2e/smoke.spec.ts:35-36`)
- [L1] `organize.settings.languageLabel` (en 1253 / it 1251), `languageIt` (1254/1252), `languageEn` (1255/1253) — 0 hit. Il selettore di lingua e' uno solo e sta nella pagina unificata, che usa `t.settings.languageLabel` (`app/settings/page.tsx:45`). Combacia con la Fase 1, che aveva gia' rilevato come i client `getLanguage`/`setLanguage` di organize non abbiano chiamanti (qui rimossi come L1): **muoiono insieme le chiavi e il client** dello store di lingua organize-scoped

Effetto cumulativo sul test guardiano `tests/i18n-organize.test.ts:24` (`> 100` foglie sotto
`organize`): 312 prima, **288 dopo** le 24 rimozioni organize-scoped di questa sezione. Ampio
margine. Nessun test asserisce i valori letterali delle 15 chiavi (controllati EN e IT).

### Findings L2 — consolidamento (Task 8)

Due helper **byte-identici** (verificati con `diff`, nessuna differenza), trovati con un
rilevatore di corpi di funzione duplicati, non da knip:

- [L2] `components/auto-link-modal.tsx:9` + `components/download-review-modal.tsx:14` + `components/link-local-file-modal.tsx:15` — `fmtSize(bytes)` in **tre copie identiche** (3 righe: `if (!bytes) return ""; return \`${(bytes/1024/1024).toFixed(1)} MB\`;`). Destinazione naturale `lib/api/format.ts`, che ospita gia' `fmtDuration`/`fmtDate`/`fmtDateShort`. **Caveat onesto, stessa disciplina del finding `_http_error` della Fase 1:** nessun test asserisce l'output ("MB" non compare in `tests/link-local-file-modal.test.tsx`, e gli altri due componenti non hanno test dedicati). Il Task 8 aggiunga un test sull'helper condiviso prima di fondere
- [L2] `components/auto-link-modal.tsx:14` + `components/link-local-file-modal.tsx:20` — `sourceLabel(t: Dictionary)` in **due copie identiche** (mappa `{ library, downloads }` dalle chiavi `t.tracks.sourceLibrary`/`sourceDownloads`; entrambi i file la chiamano una volta, `:32` e `:41`). Prende un `Dictionary`, quindi **non** va in `format.ts` con `fmtSize`: e' una mappa i18n, sta accanto ai componenti o in un modulo di etichette. Stesso caveat sui test. **Trappola di grep:** `t.discovery.sourceLabel` (`components/discovery-dig-bar.tsx:88`) e' una chiave i18n omonima e **non c'entra nulla**

### Candidati scartati (falsi positivi, per tracciabilita')

- **Tutti e 21 i "tipi esportati inutilizzati" di knip** (`lib/api/types.ts` × 11, `lib/organize/api.ts` × 8, `lib/player.tsx` × 2) — **falsi positivi**: ognuno e' usato **dentro il proprio file** come mattone di un altro tipo esportato (es. `SyncTrackRef` -> `types.ts:66,67`; `EnergyBucket` -> `:461`; `DupMember` -> `organize/api.ts:393`; `PreviewItem` -> `player.tsx:34`). Non sono codice morto: e' la convenzione di un modulo di tipi, dove nominare ogni nodo dell'albero serve a chi destruttura la risposta. Unica eccezione, gia' in L1 come cascata: `FingerprintStatus`, il cui unico uso e' la funzione morta `fingerprintStatus()`
- `components/ui.tsx:309` `Spinner` (knip: "duplicate export" con `Equalizer`) — **falso positivo**: e' un alias di compatibilita' dichiarato tale dal commento a `:308` ("i consumer che importano Spinner restano invariati"), usato da ~30 file. Rinominarli tutti in `Equalizer` sarebbe churn cosmetico, non pulizia
- `@tailwindcss/postcss` e `tailwindcss` (depcheck) — usati nei config/CSS, vedi Step 1-2
- `components/track-cover.tsx` / `playlist-cover.tsx` / `organize/cover-thumb.tsx` — sembrano una famiglia ma sono **genuinamente diversi** (sorgenti dati, catene di fallback e convenzioni di dimensionamento differenti). Nessuna fusione
- `components/spotify-glyph.tsx` / `soundcloud-glyph.tsx` — stesso involucro SVG, `path` diverso. Fonderli in un `<BrandGlyph path=...>` perderebbe i nomi parlanti: non e' un miglioramento

### Findings L3 — segnalazione, nessuna azione automatica

- [L3] `lib/api/client.ts:13` — `export class ApiError` — knip: unused export; grep ancorato: 3 hit, tutti in `lib/api/client.ts` (definizione `:13`, `this.name` `:19`, `throw` `:50`). Nessun `instanceof ApiError` nel frontend. Meccanicamente togliere la keyword `export` e' a rischio zero (lo impone `tsc`), ma **la classe e' la superficie d'errore pubblica del client API** — porta `status` e `code` proprio "per i call site che vogliono distinguerli" (docstring `:11-12`) ed e' ri-esportata dal barrel `lib/api.ts:3`. Depubblicarla e' una decisione sull'API interna, non pulizia
- [L3] `lib/i18n/en.ts` + `it.ts`, namespace `errors` — **8 codici errore senza piu' nessun emettitore nel backend**. Sono raggiunti dinamicamente (`DICTIONARIES[lang].errors[code]`, `lib/i18n/runtime.ts:28`), quindi nessun controllo statico li vede: la prova e' l'incrocio col backend, dove hanno **0 hit in tutto `backend/`** (`app/` e `tests/`), e il `git log -S` che mostra chi li emetteva. `discovery_not_found` (en 1587 / it 1584): unico emettitore il ramo `expand` di Discovery, rimosso in `bc89328`. `set_ai_generation_failed` (1592/1589) e `set_generation_failed` (1593/1590): unico emettitore `POST /api/sets/generate`, **rimosso dal Task 5b di questa stessa revisione** (commit `3dc62a1`) — sono codice morto di seconda generazione, come le funzioni di `db_hygiene.py` gia' segnalate in Fase 1. `source_path_invalid` (1616/1613), `source_already_present` (1617/1614), `source_not_found` (1618/1615), `source_has_run_history` (1619/1616), `target_root_not_absolute` (1620/1617): li emetteva `app/organize/routers/sources.py`, cancellato in `5336c6f` ("feat(f3b): via l'API delle sorgenti e il target per-radice") — il file **non esiste piu'**. **Non L1** per la regola del piano (famiglia indicizzata dinamicamente -> L3) e perche' il catalogo errori e' anche documentazione della superficie API; ma qui l'evidenza e' piu' forte del solito zero statico: non c'e' nessun emettitore possibile. Se promossi, rimuovere le coppie en+it in lockstep
- [L3] `organize.nav.themePaper` (en 1249 / it 1247) e `organize.nav.themeDark` (en 1250 / it 1248) — 0 hit, e **il buco i18n che dovrebbero tappare esiste davvero**: `components/theme-toggle.tsx:36` rende ancora `{theme === "dark" ? "Paper" : "Dark"}` hard-coded. Ma la via d'uscita **non** e' quella scritta in `docs/superpowers/plans/2026-07-11-i18n-it-en-sortory.md:646` (`{theme === "dark" ? t.nav.themePaper : t.nav.themeDark}`): quello snippet e' di quando Organize aveva un dizionario proprio, e oggi **non compilerebbe**. Il componente e' quello unificato e legge gia' il `nav` di **primo livello** (`t.nav.toggleTheme`, `theme-toggle.tsx:32` -> `en.ts:66`), e il `nav` di primo livello `themePaper`/`themeDark` **non ce li ha**: le uniche due copie esistenti sono queste, organize-scoped, che il componente non puo' raggiungere. La decisione e' quindi: **aggiungere le due chiavi al `nav` di primo livello** (e cablare il toggle li'), **oppure cancellare i residui organize-scoped** e accettare l'hard-code. Nota che sono le ultime due superstiti della coda pre-fusione di `organize.nav`: le altre tre (`tagline`, `settings`, `toggleTheme`) sono gia' L1 sopra, perche' un gemello vivo di primo livello ce l'hanno. Questo pende dal lato "rimuovere"
- [L3] `organize.common.never` (en 1225 / it 1223) — 0 hit, stesso schema: `lib/organize/api.ts:552` scrive a mano `lang === "it" ? "mai" : "never"`, cioe' **esattamente i due valori della chiave**. La chiave non e' morta, e' scavalcata da un hard-code. Decisione: usare la chiave in `fmtDate` oppure rimuoverla
- [L3] `components/organize/files-table.tsx:78-83` — le intestazioni ordinabili della tabella FILES hanno le etichette **inglesi hard-coded** (`<SortHead label="Path" …>`, `"Artist"`, `"Title"`, `"Fmt"`, `"Kbps"`, `"Dur"`) mentre tutto il resto della pagina e' tradotto. Non e' codice morto ed e' indipendente dalla rimozione delle vecchie `sortPath…` (L1 sopra, che sono etichette di `<option>`, forma diversa): se si vuole tradurre, servono chiavi nuove
- [L3] `lib/organize/api.ts:110-157` (`handle`/`apiGet`/`apiSend`) vs `lib/api/client.ts:30-100` — **due client HTTP paralleli** nello stesso frontend, con lo stesso scheletro (stesso `handle` con `translateApiError`, stesso commento "Niente `new URL(...)`", stessa costruzione manuale della query string — `lib/organize/api.ts:139-141` cita esplicitamente `lib/api/client.ts`). Ma **non sono sovrapponibili**: la versione core lancia `ApiError` con `status`/`code`, supporta `AbortSignal`, i parametri array e `apiUpload`; quella organize lancia un `Error` nudo e non ha niente di tutto cio'. Unificare significa decidere quale semantica d'errore vince per tutte le pagine Organize — decisione di design, non fusione meccanica. Coperto da `tests/organize-api-base.test.ts`
- [L3] `lib/api/format.ts:9` (`fmtDuration`) + `:17` (`fmtDate`) vs `lib/organize/api.ts:543` (`fmtDuration`) + `:550` (`fmtDate`) — **omonimi con comportamento diverso, entrambi vivi**. `fmtDuration`: la copia organize fa `Math.round(seconds)` prima di dividere, quella core no (sui float sputa secondi decimali). `fmtDate`: la copia organize e' consapevole della lingua (`getCurrentLanguage()`, locale `it-IT`/`en-GB`) e include ora e minuti; quella core **cabla `it-IT` a prescindere dalla lingua attiva** e mostra solo la data. Fondere richiede di scegliere il comportamento vincente per ogni call site — decisione di prodotto. **Nota a parte, e' un bug i18n vero:** `lib/api/format.ts:20` rende date in italiano anche con la UI in inglese (call site: `app/page.tsx:82`, `app/playlists/page.tsx:151`, `app/library/page.tsx:306`, `app/shazam/page.tsx:150`, ...)
- [L3] `lib/api/format.ts:4-5` — `trackLabel()` ricade su `"Artista sconosciuto"` / `"Senza titolo"` **hard-coded in italiano, a prescindere dalla lingua attiva**. Stessa classe del bug `it-IT` di `fmtDate` qui sopra, stesso file, ma superficie piu' ampia: la funzione e' l'etichetta standard di una traccia in tutta la UI — 7 file, ~14 call site (`app/tracks/[id]/page.tsx:47`, `app/sets/[id]/page.tsx:390,442,464,496`, `app/transitions/page.tsx:110,126,168`, `app/wishlist/page.tsx:250`, `components/wishlist-row.tsx:99`, `app/playlists/import-manual/page.tsx:282,303`). Non e' codice morto: e' una segnalazione. Il fix non e' meccanico — `format.ts` non importa il dizionario e non deve farlo alla leggera (`lib/i18n/runtime.ts:3` vieta l'import inverso da `lib/api`), quindi o si passa `t` come parametro a tutti i call site o si usa `getCurrentLanguage()` come fa gia' la copia organize di `fmtDate`
- [L3] `app/playlists/import-spotify/liked/page.tsx` (160 righe) vs `app/playlists/import-soundcloud/likes/page.tsx` (159 righe) — **quasi fotocopie**: normalizzando i nomi di piattaforma il `diff` si riduce a ~15 righe (il campo di ricerca e' `artist` vs `uploader`, la chiave `spotify_id` vs `track_id`, due note di marginalia in piu' su SoundCloud, e una `clearSelection` estratta da una parte e inline dall'altra). Tutta l'impalcatura — stato, preview, filtro, selezione, import, tabella — e' identica. **Non L2** perche' nessuna delle due pagine ha copertura: non sono in `ROUTES` di `e2e/smoke.spec.ts` e non hanno test unitari; estrarre un componente condiviso e parametrizzarlo su due modelli dati diversi e' un refactor a occhi chiusi
- [L3] Endpoint backend che restano senza chiamante frontend **se** il Task 7 esegue le rimozioni L1 qui sopra: `GET /api/organize/scan/status` (perdeva `scanJobStatus`), `GET /api/organize/fingerprint/status` (`fingerprintStatus`), `GET|PUT /api/organize/settings/language` (`getLanguage`/`setLanguage`), `GET /api/organize/picker/availability` + `POST /api/organize/picker/pick` (`pickerAvailability`/`pickPath`). Le ultime due famiglie sono **gia' segnalate in Fase 1** come duplicazione core <-> `organize/`; le prime due sono nuove. Nessuna azione qui: sono nel backend, e il piano vieta L1/L2 dentro `app/organize/`. Da valutare insieme, non uno alla volta

## Segnalazioni (livello 3)

### Backend (Task 2) — copia dei findings L3 della Fase 1

Duplicazione core <-> `app/organize/` (il piano vieta L2 in `organize/`: qui solo L1 o L3;
nessuno di questi e' morto, quindi tutti L3 — richiedono una decisione dell'utente):

- [L3] `app/services/genre_norm.py` ≡ `app/organize/services/genre_norm.py` — **byte-identici** (37 righe, `diff` vuoto). Entrambi vivi. Fondere significa comunque toccare `organize/`
- [L3] `app/services/native_picker.py` ≡ `app/organize/services/native_picker.py` — **byte-identici** (93 righe, `diff` vuoto). Entrambi vivi
- [L3] `app/core/http_errors.py` vs `app/organize/core/http_errors.py` — due `api_error()`; la versione organize e' un superset (parametro `headers` per il Cache-Control delle thumb). Fondibile solo adottando il superset, ma tocca `organize/`
- [L3] `app/integrations/_http.py` (212 righe) vs `app/organize/integrations/_http.py` (44 righe) — due fork divergenti dello stesso helper di retry HTTP: la versione core ha il workaround TLS 1.2 e i docstring, quella organize ha in piu' `post_with_retries`. Nessuna delle due e' un sottoinsieme dell'altra
- [L3] `GET /api/files/pick/availability` + `POST /api/files/pick` vs `GET /api/organize/picker/availability` + `POST /api/organize/picker/pick` — quattro endpoint, due router quasi verbatim (`app/routers/files.py:41-56` vs `app/organize/routers/picker.py` intero); differiscono solo per il prefisso, il nome dell'handler e da quale copia di `native_picker`/`http_errors` importano. Entrambe le coppie sono chiamate dal frontend
- [L3] `GET|PUT /api/settings/language` vs `GET|PUT /api/organize/settings/language` — **due store di lingua indipendenti per una app monoutente**, con default diversi: core usa `app_state` chiave `language` con default `"it"` (`app/services/app_state.py:47-54`), organize usa la colonna `Settings.language` con `DEFAULT_LANGUAGE` = EN (`app/organize/services/planning.py:42-54`). Evidenza aggiuntiva: i client organize `getLanguage`/`setLanguage` (`frontend/lib/organize/api.ts:514-519`) **non hanno nessun chiamante nel frontend** (0 hit) — la UI usa solo `/api/settings/language` (`frontend/lib/i18n/index.tsx:37,58`). Unificare e' una decisione di prodotto, non un merge meccanico

Endpoint senza chiamante ma non rimovibili d'ufficio:

- [L3] `GET /api/rekordbox/pending` (`app/routers/rekordbox.py:15`) — 0 call site nel frontend (la UI legge lo stesso numero da `/api/analysis/overview` e `/api/pipeline`; `frontend/components/analysis/rekordbox-import-card.tsx:57` lo dice in un commento), coperto solo da `tests/test_rekordbox_api.py:64`, e `docs/API.md:31,83` ammette la duplicazione. **Non L1** perche' `docs/superpowers/specs/2026-07-12-analysis-page-design.md:114` decise esplicitamente di tenerlo, ed e' un `GET` banale richiamabile via curl: rimuoverlo ribalta una decisione presa
- [L3] `POST /api/organize/analyze` (`app/organize/routers/analyze.py:11`) — 0 call site nel frontend (ho enumerato tutti i suffissi di `frontend/lib/organize/api.ts`: `/analyze` non c'e'), non documentato in nessun `.md`, coperto solo da `tests/organize/test_analyze_api.py:24,72,102`. Il **service** `analysis.recompute()` e' vivissimo (`organize/services/scan_job.py:71`, `integrity_job.py:45`): morto e' solo il wrapper HTTP. **Non L1** perche' e' in `organize/` ed e' un plausibile trigger manuale via curl per ricalcolare gli issue senza rifare la scansione del disco
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/routers/sets.py:127` — `POST /api/sets/generate` (handler `generate`) — **stessa forma di `/api/organize/analyze`: wrapper HTTP morto sopra un servizio vivissimo.** 0 call site nel frontend, che usa solo la coppia asincrona (`frontend/app/set-builder/page.tsx:160` -> `/api/sets/generate-async`, `frontend/lib/api/sets.ts:6` -> `/api/sets/generate-status`); 0 copertura HTTP nei test (tutte le occorrenze `sets/generate` in `tests/` sono `-async`/`-status`; gli altri 20+ hit chiamano il **servizio** `generate_set`/`run_curated_generation` direttamente, non l'endpoint); grep ancorato `'/api/sets/generate"'` su frontend + tests + docs: 0 hit. Documentato in `docs/API.md:401`. **Non L1** perche' rimuovere un endpoint documentato e' una decisione di prodotto: e' plausibile che l'utente lo chiami via curl per una generazione sincrona senza polling. Se promosso, il servizio resta e va toccato solo il router. **Decisione dell'utente al checkpoint: rimuovere.** Rimosso solo il router; `generate_set`/`run_curated_generation` intatti, usati da `/generate-async`. Il test `test_router_uses_curated_pipeline`, che chiamava l'handler direttamente, e' stato riscritto contro `_run_generation` (stessa garanzia di instradamento use_ai, ora sull'unico punto vivo). `docs/API.md` aggiornato
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/routers/downloads.py:240` — `POST /api/downloads/search` (handler `search`) — **candidato alla promozione a rimozione: decisione utente al checkpoint di Fase 1.** A favore della rimozione: 0 call site nel frontend, e il wrapper `searchDownloads()` in `frontend/lib/api/downloads.ts` e' stato cancellato di proposito nel commit `a56b60e` ("feat(wishlist): link a slskd al posto della ricerca libera"), il cui messaggio dice "Rimosso il codice morto: ... wrapper API searchDownloads/downloadManual"; nella UI e' stato sostituito dal link esterno "Apri slskd" (`web_url` di `/api/slskd/status`); coperto solo da `tests/test_downloads_router.py:84,101,124,154`. Contro: l'utente ha rimosso i chiamanti **lasciando in piedi l'endpoint**, che e' un POST richiamabile a mano via curl su una app self-hosted, ed e' documentato per intero in `docs/API.md:722,751-755`. Regola del piano "in dubbio → L3": vince l'asimmetria del rischio. Da non confondere con `POST /api/downloads/candidates`, che e' vivo (`frontend/lib/api/downloads.ts:28`). **Decisione dell'utente al checkpoint: rimuovere.** Rimossi i 4 test che coprivano solo questo endpoint; `docs/API.md`/`docs/ARCHITECTURE.md` aggiornati
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/routers/downloads.py:264` — `POST /api/downloads/manual` (handler `download_manual`) — **candidato alla promozione a rimozione: decisione utente al checkpoint di Fase 1**, inseparabile dal precedente (stesso commit `a56b60e` ha cancellato `downloadManual()`, stessa motivazione pro e contro; documentato in `docs/API.md:723,756-759`); 0 call site, coperto solo da `tests/test_downloads_router.py:161,176`. **Se promossi, cascata per il Task 3:** restano orfani `SearchIn` (`downloads.py:62`), `ManualDownloadIn` (`downloads.py:66`) e `start_manual_job()` (`app/services/soulseek_download_job.py:357`); **NON** rimuovere `_slskd_file` (`:98`) ne' `_candidate_out` (`:90`), che servono anche a `/track` (`:192`) e `/candidates` (`:166`); aggiornare `docs/API.md:722-758` e `docs/ARCHITECTURE.md:134,152-153` nella stessa passata (Task 11/12). **Decisione dell'utente al checkpoint: rimuovere.** Cascata eseguita come previsto: `SearchIn`, `ManualDownloadIn`, `start_manual_job()` rimossi; `_slskd_file`/`_candidate_out` intatti. Rimossi i 2 test dedicati; `docs/API.md`/`docs/ARCHITECTURE.md` aggiornati

Script one-shot gia' applicati in `app/tools/` (0 importer in `backend/app`; decisione utente:
sono documentazione eseguibile di migrazioni passate o zavorra?):

- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/tools/align_genre_from_file.py` — la docstring dice "una-tantum"; 0 importer, 0 test. Il payload `db_hygiene.align_owned_genre_from_file` resta usato da `app/services/genre_align.py:9` e coperto da `tests/test_db_hygiene.py:145-195`: cancellare la CLI non perde logica testata. Citato in `PROGRESS.md:48,65`, `docs/ARCHITECTURE.md:207,360`, `docs/ROADMAP.md:104`. **Decisione dell'utente al checkpoint: rimuovere.** Script cancellato, `db_hygiene.align_owned_genre_from_file` intatto e coperto dai test esistenti; `docs/ARCHITECTURE.md` aggiornato (i riferimenti in `PROGRESS.md`/`docs/ROADMAP.md` sono diario storico, non toccati)
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/tools/backfill_track_files.py` — backfill della migrazione F3, gia' applicata; 0 importer, 1 test (`tests/test_backfill_track_files.py:8`) che coprirebbe solo codice morto. **Decisione dell'utente al checkpoint: rimuovere.** Script e i suoi 3 test cancellati (coprivano solo la CLI stessa)
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/tools/cleanup_disk_first.py` — la docstring dice "una-tantum", `PROGRESS.md:1128` dice "One-off maintenance tool"; 0 importer, 0 test. Tutte le op che orchestra sono coperte in `tests/test_db_hygiene.py`. **Decisione dell'utente al checkpoint: rimuovere.** Script cancellato, le operazioni di `db_hygiene.py` che orchestrava restano e restano coperte da `tests/test_db_hygiene.py`; `docs/ARCHITECTURE.md` aggiornato
- [L3 — **PROMOSSO E RIMOSSO, Task 5b**] `app/tools/migrate_organize_db.py` — migrazione F2 (DB unico) gia' applicata; 0 importer, 1 test (`tests/test_migrate_organize_db.py:12`). **Decisione dell'utente al checkpoint: rimuovere.** Script e i suoi 14 test cancellati (coprivano solo la CLI stessa)
- [L3 — **evaporato, Task 5b**] `app/tools/backfill_track_files.py:98` + `app/tools/merge_duplicate_tracks.py:70` — `_sessione()` con corpo identico (differisce solo la docstring). Estrazione meccanica in `app/tools/_common.py`, ma contingente: se i one-shot vengono cancellati il problema evapora. Confermato: `backfill_track_files.py` e' stato rimosso al Task 5b, quindi non c'e' piu' duplicazione da estrarre — `merge_duplicate_tracks.py` e' l'unico sopravvissuto con `_sessione()`
- [L3] **Da NON toccare in `app/tools/`**: `clean_user_data.py` (unico tool documentato all'utente, `README.md:186`) e `merge_duplicate_tracks.py` (riparazione ricorrente, non one-shot; l'unico "riferimento" trovato dallo scan e' un commento in prosa a `backfill_track_files.py:101`, ora orfano — lo script citato non esiste piu'). Confermato intoccato al Task 5b

Emerso dalla review del Task 5b (codice morto di seconda generazione, conseguenza
diretta delle rimozioni sopra — nessuno di questi era nella cascata autorizzata, quindi
non toccato in quella passata):

- [L3] `app/services/db_hygiene.py`: `dedupe_by_audio_hash` (:41), `purge_lead_residue`
  (:64), `realign_owned_from_disk` (:102) e `align_owned_genre_from_file` (:132) hanno
  **zero chiamanti di produzione** da quando `app/tools/cleanup_disk_first.py` e
  `app/tools/align_genre_from_file.py` sono stati rimossi (Task 5b): le uniche
  referenze rimaste in `backend/app/` sono due righe di docstring
  (`app/services/genre_align.py:9` cita `align_owned_genre_from_file` come "il backfill
  retroattivo"; `app/services/db_hygiene.py:135` cita `realign_owned_from_disk` a
  confronto). Ogni chiamata reale e' nei test (`tests/test_db_hygiene.py`), che restano
  verdi e non se ne accorgono: la suite non segnala codice morto, lo segnala solo
  l'assenza di importer in `app/`. Non rimosso in questa passata: fuori dalla cascata
  autorizzata per il Task 5b, che elencava solo i quattro script CLI
- [L3] `app/services/soulseek_download_job.py:246` — il ramo `if track_id is None:`
  dentro `_run()` (con `_process_manual()`) e' diventato irraggiungibile in produzione
  dopo la rimozione di `start_manual_job()` (Task 5b, unico chiamante che passava
  `track_id=None`). **Non e' orfano di test**: `tests/test_soulseek_download_job.py:157`
  (`test_manual_download_lascia_il_file_senza_catalogare`) chiama
  `job._run([(None, file)], None)` direttamente ed e' vivo e verde — asserisce che il
  download manuale lascia il file sul disco senza catalogarlo in Cratory. Questo rende
  ancora piu' netta la decisione di non toccarlo nella cascata del Task 5b (era fuori
  scope autorizzato, e cancellarlo avrebbe portato via un test vivo): ma chi fara' la
  prossima passata mirata su questo file deve sapere che il ramo morto viaggia insieme
  a un test che lo esercita, non da solo

Ridondanza architetturale profonda (fusione = decisione di design, esplicitamente fuori
da una passata meccanica):

- [L3] Cinque macchine a stati di job scritte a mano: `app/services/audio_analysis_job.py:21`, `app/services/streaming_import_job.py:46`, `app/services/soulseek_download_job.py:36`, `app/services/mix_identify_job.py:19`, `app/routers/sets.py:64`. Una classe base unificata richiede di decidere: (a) la disciplina di lock (due leggono `_state` senza lock, due con lock e con `_state_snapshot` per la non-reentrancy), (b) la forma del payload di stato (5 shape diverse), (c) la semantica della start-guard (tre ritornano lo stato corrente se gia' in corso, `routers/sets.py:107-113` alza deliberatamente 409 con commento che spiega perche'), (d) i response model gia' fissati da `tests/test_job_response_schemas.py:141`. Il solo `_spawn` e' stato estratto come L2 sopra
- [L3] Idioma "carica o 404" ripetuto ~40 volte nei router (`routers/playlists.py:173,241,265,303,318,336,356,404,...`, `tracks.py:90,128,150,175`, `sets.py:157,176,320`, `dj_sets.py:124,136,149`, `downloads.py:127,189,208,232,279,288,302`, `transitions.py:31`, `spotify.py:119`). Il fix idiomatico (`Depends(get_playlist_or_404)`) romperebbe i test che invocano gli handler **direttamente** anziche' via HTTP (es. `tests/test_playlist_export.py:38` chiama `export_playlist(pl.id, "m3u8", db)`): una `Depends` non si risolve in chiamata diretta. Decisione di design, non pulizia
- [L3] `app/services/set_generator.py:33` — `_STRATEGY_PROFILES` re-esportato da `set_skeleton` ma importato da nessuno (0 hit fuori da `set_skeleton.py`). **Non L1** perche' sta dentro un blocco marcato `# noqa: F401 - re-export per compat test` deliberato: la convenzione spiega l'apparente inutilizzo. Il gemello `_DEFAULT_PROFILE` nello stesso blocco e' invece portante (5 file di test lo importano da `set_generator`) e va lasciato
- [L3] `file_tags_for_tracks(db, [x.id]).get(x.id)` ripetuto 5 volte (`routers/downloads.py:132,294,304`, `routers/discovery.py:313,330`) — manca un wrapper `file_tags_for_track` accanto a `app/repositories.py:203`. Meccanico ma cosmetico

Schema DB (intoccabile per definizione nel piano):

- [L3] Le ~100 voci di `vulture --min-confidence 60` su `app/models.py`, `app/organize/models.py`, `app/schemas.py`, `app/organize/schemas.py` sono colonne SQLAlchemy e campi Pydantic dichiarativi. Alcune sono effettivamente scritte e mai lette dal backend (es. `Track.playlist_name`, `analysis_error`, i vari `updated_at`), ma lo schema non si tocca e il frontend puo' leggerle via i response model: nessuna azione, solo segnalazione

### Frontend (Task 6) — copia dei findings L3 della Fase 2

Superficie API interna:

- [L3] `lib/api/client.ts:13` — `export class ApiError` — knip: unused export; grep ancorato: 3 hit, tutti in `lib/api/client.ts` (definizione `:13`, `this.name` `:19`, `throw` `:50`). Nessun `instanceof ApiError` nel frontend. Meccanicamente togliere la keyword `export` e' a rischio zero (lo impone `tsc`), ma **la classe e' la superficie d'errore pubblica del client API** — porta `status` e `code` proprio "per i call site che vogliono distinguerli" (docstring `:11-12`) ed e' ri-esportata dal barrel `lib/api.ts:3`. Depubblicarla e' una decisione sull'API interna, non pulizia

Chiavi i18n che richiedono una decisione (non semplice cruft):

- [L3] `lib/i18n/en.ts` + `it.ts`, namespace `errors` — **8 codici errore senza piu' nessun emettitore nel backend**. Sono raggiunti dinamicamente (`DICTIONARIES[lang].errors[code]`, `lib/i18n/runtime.ts:28`), quindi nessun controllo statico li vede: la prova e' l'incrocio col backend, dove hanno **0 hit in tutto `backend/`** (`app/` e `tests/`), e il `git log -S` che mostra chi li emetteva. `discovery_not_found` (en 1587 / it 1584): unico emettitore il ramo `expand` di Discovery, rimosso in `bc89328`. `set_ai_generation_failed` (1592/1589) e `set_generation_failed` (1593/1590): unico emettitore `POST /api/sets/generate`, **rimosso dal Task 5b di questa stessa revisione** (commit `3dc62a1`) — sono codice morto di seconda generazione, come le funzioni di `db_hygiene.py` gia' segnalate in Fase 1. `source_path_invalid` (1616/1613), `source_already_present` (1617/1614), `source_not_found` (1618/1615), `source_has_run_history` (1619/1616), `target_root_not_absolute` (1620/1617): li emetteva `app/organize/routers/sources.py`, cancellato in `5336c6f` ("feat(f3b): via l'API delle sorgenti e il target per-radice") — il file **non esiste piu'**. **Non L1** per la regola del piano (famiglia indicizzata dinamicamente -> L3) e perche' il catalogo errori e' anche documentazione della superficie API; ma qui l'evidenza e' piu' forte del solito zero statico: non c'e' nessun emettitore possibile. Se promossi, rimuovere le coppie en+it in lockstep
- [L3] `organize.nav.themePaper` (en 1249 / it 1247) e `organize.nav.themeDark` (en 1250 / it 1248) — 0 hit, e **il buco i18n che dovrebbero tappare esiste davvero**: `components/theme-toggle.tsx:36` rende ancora `{theme === "dark" ? "Paper" : "Dark"}` hard-coded. Ma la via d'uscita **non** e' quella scritta in `docs/superpowers/plans/2026-07-11-i18n-it-en-sortory.md:646` (`{theme === "dark" ? t.nav.themePaper : t.nav.themeDark}`): quello snippet e' di quando Organize aveva un dizionario proprio, e oggi **non compilerebbe**. Il componente e' quello unificato e legge gia' il `nav` di **primo livello** (`t.nav.toggleTheme`, `theme-toggle.tsx:32` -> `en.ts:66`), e il `nav` di primo livello `themePaper`/`themeDark` **non ce li ha**: le uniche due copie esistenti sono queste, organize-scoped, che il componente non puo' raggiungere. La decisione e' quindi: **aggiungere le due chiavi al `nav` di primo livello** (e cablare il toggle li'), **oppure cancellare i residui organize-scoped** e accettare l'hard-code. Nota che sono le ultime due superstiti della coda pre-fusione di `organize.nav`: le altre tre (`tagline`, `settings`, `toggleTheme`) sono gia' L1 sopra, perche' un gemello vivo di primo livello ce l'hanno. Questo pende dal lato "rimuovere"
- [L3] `organize.common.never` (en 1225 / it 1223) — 0 hit, stesso schema: `lib/organize/api.ts:552` scrive a mano `lang === "it" ? "mai" : "never"`, cioe' **esattamente i due valori della chiave**. La chiave non e' morta, e' scavalcata da un hard-code. Decisione: usare la chiave in `fmtDate` oppure rimuoverla
- [L3] `components/organize/files-table.tsx:78-83` — le intestazioni ordinabili della tabella FILES hanno le etichette **inglesi hard-coded** (`<SortHead label="Path" …>`, `"Artist"`, `"Title"`, `"Fmt"`, `"Kbps"`, `"Dur"`) mentre tutto il resto della pagina e' tradotto. Non e' codice morto ed e' indipendente dalla rimozione delle vecchie `sortPath…` (L1 in Fase 2, che sono etichette di `<option>`, forma diversa): se si vuole tradurre, servono chiavi nuove

Duplicazione frontend che non e' una fusione meccanica:

- [L3] `lib/organize/api.ts:110-157` (`handle`/`apiGet`/`apiSend`) vs `lib/api/client.ts:30-100` — **due client HTTP paralleli** nello stesso frontend, con lo stesso scheletro (stesso `handle` con `translateApiError`, stesso commento "Niente `new URL(...)`", stessa costruzione manuale della query string — `lib/organize/api.ts:139-141` cita esplicitamente `lib/api/client.ts`). Ma **non sono sovrapponibili**: la versione core lancia `ApiError` con `status`/`code`, supporta `AbortSignal`, i parametri array e `apiUpload`; quella organize lancia un `Error` nudo e non ha niente di tutto cio'. Unificare significa decidere quale semantica d'errore vince per tutte le pagine Organize — decisione di design, non fusione meccanica. Coperto da `tests/organize-api-base.test.ts`
- [L3] `lib/api/format.ts:9` (`fmtDuration`) + `:17` (`fmtDate`) vs `lib/organize/api.ts:543` (`fmtDuration`) + `:550` (`fmtDate`) — **omonimi con comportamento diverso, entrambi vivi**. `fmtDuration`: la copia organize fa `Math.round(seconds)` prima di dividere, quella core no (sui float sputa secondi decimali). `fmtDate`: la copia organize e' consapevole della lingua (`getCurrentLanguage()`, locale `it-IT`/`en-GB`) e include ora e minuti; quella core **cabla `it-IT` a prescindere dalla lingua attiva** e mostra solo la data. Fondere richiede di scegliere il comportamento vincente per ogni call site — decisione di prodotto. **Nota a parte, e' un bug i18n vero:** `lib/api/format.ts:20` rende date in italiano anche con la UI in inglese (call site: `app/page.tsx:82`, `app/playlists/page.tsx:151`, `app/library/page.tsx:306`, `app/shazam/page.tsx:150`, ...)
- [L3] `lib/api/format.ts:4-5` — `trackLabel()` ricade su `"Artista sconosciuto"` / `"Senza titolo"` **hard-coded in italiano, a prescindere dalla lingua attiva**. Stessa classe del bug `it-IT` di `fmtDate` qui sopra, stesso file, ma superficie piu' ampia: la funzione e' l'etichetta standard di una traccia in tutta la UI — 7 file, ~14 call site (`app/tracks/[id]/page.tsx:47`, `app/sets/[id]/page.tsx:390,442,464,496`, `app/transitions/page.tsx:110,126,168`, `app/wishlist/page.tsx:250`, `components/wishlist-row.tsx:99`, `app/playlists/import-manual/page.tsx:282,303`). Non e' codice morto: e' una segnalazione. Il fix non e' meccanico — `format.ts` non importa il dizionario e non deve farlo alla leggera (`lib/i18n/runtime.ts:3` vieta l'import inverso da `lib/api`), quindi o si passa `t` come parametro a tutti i call site o si usa `getCurrentLanguage()` come fa gia' la copia organize di `fmtDate`
- [L3] `app/playlists/import-spotify/liked/page.tsx` (160 righe) vs `app/playlists/import-soundcloud/likes/page.tsx` (159 righe) — **quasi fotocopie**: normalizzando i nomi di piattaforma il `diff` si riduce a ~15 righe (il campo di ricerca e' `artist` vs `uploader`, la chiave `spotify_id` vs `track_id`, due note di marginalia in piu' su SoundCloud, e una `clearSelection` estratta da una parte e inline dall'altra). Tutta l'impalcatura — stato, preview, filtro, selezione, import, tabella — e' identica. **Non L2** perche' nessuna delle due pagine ha copertura: non sono in `ROUTES` di `e2e/smoke.spec.ts` e non hanno test unitari; estrarre un componente condiviso e parametrizzarlo su due modelli dati diversi e' un refactor a occhi chiusi

Ricadute sul backend delle rimozioni L1 del Task 7:

- [L3] Endpoint backend che restano senza chiamante frontend **se** il Task 7 esegue le rimozioni L1 della Fase 2: `GET /api/organize/scan/status` (perdeva `scanJobStatus`), `GET /api/organize/fingerprint/status` (`fingerprintStatus`), `GET|PUT /api/organize/settings/language` (`getLanguage`/`setLanguage`), `GET /api/organize/picker/availability` + `POST /api/organize/picker/pick` (`pickerAvailability`/`pickPath`). Le ultime due famiglie sono **gia' segnalate in Fase 1** come duplicazione core <-> `organize/`; le prime due sono nuove. Nessuna azione qui: sono nel backend, e il piano vieta L1/L2 dentro `app/organize/`. Da valutare insieme, non uno alla volta

## Riepiloghi checkpoint

### Checkpoint Fase 1 (Task 5)

**Rimosso** — 13 simboli L1 (Task 3), doppia conferma su ciascuno (grep repo-wide + AST),
raggruppabili in due famiglie:

- *Import inutilizzati* (8, in 4 file): `Session`, `LocalFilesError`,
  `identity_normalize`, `import_playlist` in `local_import.py`; `field` in
  `mix_identify.py`; `settings` in `pipeline.py`; `DiscogsMetaClient` e
  `MusicBrainzProvider` a livello di modulo in `organize/services/text_providers.py`
  (i provider restano vivi, iniettati dentro le funzioni altrove).
- *Funzioni/classi morte con cascata* (5 punti d'ingresso che trascinano ~8 simboli
  orfani): `LocalDirEntry` (il suo consumatore frontend era gia' sparito);
  `_safe_library_context()` (chiamante `ai_agent.py` non esiste piu') + import orfano
  `library_stats`; `build_normalized()` (chiamante storico rimosso) + cascata
  `PLATFORM`, `NormalizedTrack`, `read_tags`, `audio_hash`, `parse_line` +
  `import logging`/`logger` gia' morti indipendentemente; `backfill_energy()`
  (coperta solo da test che testavano lei sola); `best_for_auto()` (wrapper scavalcato
  in produzione) + import orfano `Session` in `ai_curation.py`. Nessun gemello vivo
  toccato (`PLATFORM` sopravvive in `library_index.py`, `read_tags` ha un gemello
  indipendente in `organize/`).

Effetto sui test: **1946 → 1944**. Due test cancellati perche' coprivano solo codice
morto (`test_backfill_only_untouched_owned_tracks`,
`test_best_for_auto_picks_strong_lossless`); altri quattro riscritti contro
`rank_candidates` direttamente, stessa copertura comportamentale. Da dire con
chiarezza: uno di questi (`test_best_for_auto_returns_none_below_threshold`) e' stato
**inizialmente cancellato per errore**, con una motivazione sbagliata (si credeva
coperto altrove — non lo era), poi **ripristinato in forma riscritta**
(`test_nome_plausibile_ma_imperfetto_escluso`), corretto in review.

**Consolidato** — 5 delle 6 duplicazioni L2 fuse (Task 4), nessuna tocca `organize/`:

1. Render M3U8 (sets.py + playlists.py, output byte-identico) →
   `app/services/export_render.py::render_m3u8()`. Coverage esistente sufficiente,
   nessun test nuovo.
2. `_http_error(SpotifyError)` byte-identico (playlists.py + spotify.py) →
   `spotify_http_error()` in `app/core/http_errors.py`. Nessun test router
   preesistente copriva la mappatura: **6 test** di caratterizzazione (3 codici x 2
   siti) scritti e verificati verdi PRIMA del merge.
3. `_label`/`_track_label` (auto_link.py + soulseek_download_job.py) →
   `app/services/track_label.py::track_label()`. **1 test** aggiunto (il sito
   auto_link asseriva solo `hit`, mai il campo `label`).
4. `_spawn(fn)` (audio_analysis_job.py + streaming_import_job.py) →
   `app/services/job_spawn.py::spawn()`. Nessun test nuovo: gia' monkeypatchato dai
   test esistenti, verificato che l'import preserva la monkeypatchabilita'.
5. `_fmt_dur` (sets.py) esteso anche al ramo markdown di playlists.py → stesso modulo,
   `export_render.py::fmt_duration()`. **2 test** aggiunti (uno per sito): la coverage
   precedente non asseriva mai la colonna Durata formattata.

Totale **9 test di caratterizzazione** (6+1+2), tutti scritti e verificati verdi prima
del rispettivo merge. Effetto sui test: **1944 → 1953**.

Un sesto finding, `_norm` (discovery_dig.py + manual_import.py), e' stato
**retrocesso a L3, non fuso**: la sua stessa condizione dichiarata ("fondere solo se
il Task 4 crea comunque un modulo di util testuali") non si e' avverata — nessuno dei
4 moduli creati per gli altri 5 finding e' un modulo di normalizzazione testuale
(`export_render` = formattazione output, `track_label` = etichetta UI, `job_spawn` =
avvio thread, l'estensione di `http_errors` = mappatura eccezioni). Gli altri 7 helper
`_norm`-simili nel backend restano intoccati: sono semanticamente diversi, non
ridondanti.

**Segnalato** — lista L3, organizzata per tipo di decisione:

*a) Pronti per un si'/no sulla rimozione* (wrapper HTTP morti sopra servizi vivi o
funzionalita' gia' scollegata dal frontend) — **decisione dell'utente al checkpoint:
rimuovere entrambi, eseguito al Task 5b** (dettagli e verifica nella lista L3 sopra):
- `POST /api/downloads/search` + `POST /api/downloads/manual` — lo stesso commit
  (`a56b60e`) ha gia' cancellato i wrapper frontend `searchDownloads()`/
  `downloadManual()`, sostituiti dal link "Apri slskd", con messaggio di commit che
  dice esplicitamente "codice morto". A favore della rimozione: 0 call site, l'intento
  di dismissione e' scritto nero su bianco nel commit che ha tolto i chiamanti. Contro:
  restano POST richiamabili via curl su un'app self-hosted, documentati per intero in
  `docs/API.md`. Se rimossi: cascata su `SearchIn`, `ManualDownloadIn`,
  `start_manual_job()` — **non** toccare `_slskd_file`/`_candidate_out` (condivisi con
  `/track` e `/candidates`); aggiornare `docs/API.md` e `docs/ARCHITECTURE.md` nella
  stessa passata.
- `POST /api/sets/generate` — stessa forma: wrapper HTTP morto (0 call site, 0
  copertura HTTP diretta nei test — tutte le occorrenze nei test chiamano il servizio,
  non l'endpoint) sopra `generate_set`/`run_curated_generation`, vivissimi altrove. Il
  frontend usa solo la coppia asincrona (`/sets/generate-async` + `-status`).
  Documentato in `docs/API.md:401`. Contro: e' plausibile un uso via curl per
  generazione sincrona senza polling. Se rimosso, il servizio resta: si tocca solo il
  router.

*b) Segnalati ma non promuovibili, per un vincolo gia' deciso altrove*:
- `GET /api/rekordbox/pending` — 0 call site, ma tenuto per una decisione di design
  esplicita e pregressa (spec 2026-07-12).
- `POST /api/organize/analyze` — 0 call site, wrapper morto sopra
  `analysis.recompute()` (vivissimo), ma sta in `organize/` (fuori scope L1) ed e' un
  plausibile trigger manuale via curl.

*c) Duplicazione core <-> organize/* (il piano vieta L2 dentro `organize/`: qui solo
segnalazione, unificare e' una decisione di prodotto):
- `genre_norm.py` e `native_picker.py` — copie byte-identiche, entrambe vive.
- `core/http_errors.py` vs `organize/core/http_errors.py` — la versione organize e' un
  superset (parametro `headers`).
- `integrations/_http.py` — due fork divergenti (core ha il workaround TLS 1.2,
  organize ha in piu' `post_with_retries`): nessuno e' sottoinsieme dell'altro.
- `/api/files/pick*` vs `/api/organize/picker/*` — quattro endpoint quasi-verbatim,
  entrambe le coppie vive e chiamate dal frontend.
- `/api/settings/language` vs `/api/organize/settings/language` — due store di lingua
  indipendenti con default diversi (it vs en); i client organize
  (`getLanguage`/`setLanguage`) hanno 0 chiamanti nel frontend.

*d) Ridondanza piu' profonda, note per dopo* (fuori da una passata meccanica):
- 5 macchine a stati di job scritte a mano, ciascuna con disciplina di
  lock/payload/start-guard diversa — solo `_spawn` estratto come L2.
- Idioma "carica o 404" ripetuto ~40 volte nei router — il fix idiomatico (`Depends`)
  romperebbe i test che chiamano gli handler direttamente.
- `file_tags_for_tracks(db,[x.id]).get(x.id)` ripetuto 5 volte — manca un wrapper,
  meccanico ma cosmetico.
- Script one-shot in `app/tools/` (`align_genre_from_file`, `backfill_track_files`,
  `cleanup_disk_first`, `migrate_organize_db`) — 0 importer, migrazioni gia'
  applicate: documentazione eseguibile o zavorra? Decisione utente. **Non** toccare
  `clean_user_data.py` (documentato all'utente in README) ne' `merge_duplicate_tracks.py`
  (riparazione ricorrente, non one-shot). **Decisione dell'utente al checkpoint: sono
  zavorra, rimuovere tutti e quattro — eseguito al Task 5b** (dettagli e verifica nella
  lista L3 sopra); `clean_user_data.py`/`merge_duplicate_tracks.py` confermati intoccati.
- ~100 colonne SQLAlchemy/campi Pydantic mai letti dal backend — schema DB intoccabile
  per definizione nel piano, solo segnalazione.

### Checkpoint Fase 2 (Task 8)

**Rimosso** — 23 findings L1 (Task 7), doppia conferma su ciascuno (grep ancorato con
`/usr/bin/grep`, non il wrapper della shell): **49 chiavi i18n morte** e **7
export/re-export morti**, rimossi in coppia da `en.ts`/`it.ts` dove pertinente (mai a
senso unico: `it.ts` si tipizza su `typeof en`). Effetto sul test guardiano
`tests/i18n-organize.test.ts`: le foglie del dizionario passano da **1411 a 1362** per
locale (verificato ora, simmetrico EN/IT), quelle del solo namespace `organize` da
**312 a 288** — ampio margine sopra la soglia `> 100` che il test impone. (Nota: il
report del Task 7 aveva scritto 1366 foglie finali; il numero corretto, ricontato ora
sui file effettivi, e' 1362 — differenza di 4, nessun impatto sulle rimozioni ne' sui
test, solo un refuso nel report.)

Nessun file orfano e nessuna dipendenza npm morta: **zero** in entrambi i casi (`npx
knip`: 0 file inutilizzati, 0 dipendenze inutilizzate; `npx depcheck` segnalava due
falsi positivi — `@tailwindcss/postcss` e `tailwindcss`, entrambi usati nei config —
smentiti anche da knip). E' un risultato reale, non un buco della ricerca: vale la pena
dirlo esplicitamente perche' un frontend che ha appena assorbito Sortory (fusione F1-F6)
avrebbe potuto facilmente portarsi dietro pacchi di file morti, e non e' cosi'.

**Consolidato** — 2 delle 2 duplicazioni L2 fuse (Task 8), nessuna richiedeva
retrocessione:

1. `fmtSize(bytes)`, tre copie byte-identiche (`auto-link-modal.tsx`,
   `download-review-modal.tsx`, `link-local-file-modal.tsx`) → spostata in
   `lib/api/format.ts`, accanto a `fmtDuration`/`fmtDate`/`fmtDateShort`. Nessun test
   preesistente asseriva l'output (ne' "MB" ne' il ramo byte falsy): **2 test** di
   caratterizzazione scritti in `tests/format.test.ts` (valori arrotondati a una
   cifra decimale, incluso un valore non tondo; `0`/`null` → stringa vuota) e
   verificati verdi PRIMA di toccare i tre siti.
2. `sourceLabel(t: Dictionary)`, due copie identiche (`auto-link-modal.tsx`,
   `link-local-file-modal.tsx`) → **non** in `format.ts` (prende un `Dictionary`, e'
   una mappa i18n, non un formattatore): nuovo modulo `lib/track-source.ts`, stesso
   posto di `lib/wishlist-status.ts` (precedente diretto nel repo per un piccolo
   helper di dominio label-mapping). **2 test** in `tests/track-source.test.ts`, uno
   per dizionario (EN e IT), verificati verdi prima della fusione. Attenzione alla
   trappola di grep gia' segnalata dal Task 6: `t.discovery.sourceLabel`
   (`components/discovery-dig-bar.tsx:88`) e' una chiave i18n omonima e non
   c'entra — non toccata.

Totale **4 test di caratterizzazione**, tutti scritti e verificati verdi prima del
rispettivo merge. Effetto sui test: **173 → 177**. Nessuna retrocessione a L3: entrambi
i finding erano davvero meccanici come previsto dal log (corpi byte-identici, stessa
firma, stessi due chiamanti). Nella stessa passata, corretta anche la riga vuota persa
nella review del Task 7 in `lib/organize/api.ts:511` (separatore di sezione
`SETTINGS`/`FINGERPRINT`, coerente col resto del file).

**Segnalato** — 10 finding L3 frontend (Task 6), organizzati per tipo di decisione:

*a) Chiavi/simboli in attesa di un si'/no sulla rimozione* (morti per grep statico, ma
con una ragione per esitare):
- Namespace `errors`, 8 codici — raggiunti solo dinamicamente
  (`DICTIONARIES[lang].errors[code]`), quindi invisibili a qualunque controllo
  statico; **qui l'evidenza e' piu' forte del solito "zero grep"**: incrociati col
  backend, hanno 0 emettitori possibili, non solo 0 hit oggi. Tre gruppi: 2 chiavi il
  cui unico emettitore (`POST /api/sets/generate`) e' stato rimosso da questa stessa
  revisione (Task 5b); 5 chiavi il cui emettitore (`app/organize/routers/sources.py`)
  non esiste piu' nel codice, cancellato in `5336c6f`; 1 chiave il cui emettitore e'
  stato rimosso in `bc89328`. A favore della rimozione: zero possibilita' di
  riemissione senza riscrivere il backend. Contro: il catalogo `errors` e' anche
  documentazione della superficie API, e la regola del piano manda le famiglie
  indicizzate dinamicamente a L3 per costruzione.
- `export class ApiError` (`lib/api/client.ts`) — 0 `instanceof` nel frontend, ma e'
  la superficie d'errore pubblica del client (porta `status`/`code`), ri-esportata dal
  barrel `lib/api.ts`. Depubblicarla e' una decisione sull'API interna, non pulizia.

*b) Il problema inverso: buchi i18n, stringa hard-coded dove dovrebbe esserci una
chiave* (qui la chiave morta e' il sintomo, non il difetto):
- `organize.nav.themePaper`/`themeDark` — il buco esiste davvero:
  `theme-toggle.tsx:36` rende ancora `"Paper"`/`"Dark"` hard-coded in inglese. Ma le
  due chiavi organize-scoped non sono la soluzione (il componente unificato legge il
  `nav` di primo livello, che non le ha): la decisione e' aggiungerle li' o accettare
  l'hard-code e cancellare i residui. **Pende dal lato "rimuovere"**, e' l'ultima coda
  della shell Organize pre-fusione.
- `organize.common.never` — scavalcata da un hard-code equivalente
  (`lang === "it" ? "mai" : "never"` in `lib/organize/api.ts:552`): usare la chiave in
  `fmtDate` o cancellarla.
- Intestazioni ordinabili di `components/organize/files-table.tsx:78-83` — inglese
  hard-coded (`"Path"`, `"Artist"`, ...) mentre il resto della pagina e' tradotto; non
  e' collegata alle vecchie chiavi `sortPath...` gia' rimosse come L1 (quelle erano
  etichette di un `<Select>` che non c'e' piu', forma diversa). Servirebbero chiavi
  nuove, non un ripristino.
- `lib/api/format.ts` — due bug i18n distinti, non codice morto: `fmtDate` cabla
  `it-IT` a prescindere dalla lingua attiva (~10+ call site), e `trackLabel()` ricade
  su `"Artista sconosciuto"`/`"Senza titolo"` sempre in italiano (~14 call site in 7
  file). Il fix non e' meccanico: `format.ts` non puo' importare il dizionario
  (`lib/i18n/runtime.ts` vieta l'import inverso da `lib/api`).

*c) Duplicazione strutturale core <-> `organize/`* (fondere e' una decisione di
design, non un merge meccanico — stesso principio gia' visto in Fase 1 per
`genre_norm.py`/`native_picker.py`):
- `lib/organize/api.ts` (`handle`/`apiGet`/`apiSend`) vs `lib/api/client.ts` — due
  client HTTP paralleli con lo stesso scheletro (stesso commento sorgente, stessa
  costruzione della query string), ma non sovrapponibili: solo la versione core ha
  `ApiError` tipizzato, `AbortSignal`, parametri array, `apiUpload`.
- `fmtDuration`/`fmtDate` — omonimi **con comportamento diverso**, entrambi vivi, tra
  `lib/api/format.ts` e `lib/organize/api.ts`: `fmtDuration` organize arrotonda prima
  di dividere, quella core no sui float; `fmtDate` organize e' consapevole della
  lingua e mostra ora/minuti, quella core no (e' anche il bug i18n del gruppo b).
- `app/playlists/import-spotify/liked/page.tsx` vs
  `app/playlists/import-soundcloud/likes/page.tsx` — quasi fotocopie (il diff si
  riduce a ~15 righe normalizzando i nomi piattaforma), ma **senza copertura**: non
  in `e2e/smoke.spec.ts`, nessun test unitario. Estrarre un componente condiviso
  parametrizzato su due modelli dati diversi e' un refactor a occhi chiusi, non
  incluso in questa fase.
- Endpoint backend rimasti senza chiamante frontend **a causa** delle rimozioni L1 di
  questa fase (`GET /api/organize/scan/status`, `GET /api/organize/fingerprint/status`
  nuovi; `GET|PUT /api/organize/settings/language`,
  `GET /api/organize/picker/availability` + `POST /api/organize/picker/pick` gia'
  segnalati in Fase 1 come duplicazione core<->organize) — nessuna azione qui, il
  piano vieta L1/L2 dentro `app/organize/`: da valutare insieme alla duplicazione di
  Fase 1, non uno alla volta.

**Riportato dalla Fase 1, ancora in attesa di decisione** (codice morto di seconda
generazione emerso dalla review del Task 5b, mai autorizzato in quella cascata):
- `app/services/db_hygiene.py`: `dedupe_by_audio_hash`, `purge_lead_residue`,
  `realign_owned_from_disk`, `align_owned_genre_from_file` — zero chiamanti di
  produzione da quando gli script CLI che li invocavano sono stati rimossi (Task 5b);
  restano coperti da `tests/test_db_hygiene.py`, che non se ne accorge perche' chiama
  le funzioni direttamente.
- `app/services/soulseek_download_job.py:246` — il ramo `if track_id is None:` dentro
  `_run()` e' irraggiungibile in produzione dopo la rimozione di `start_manual_job()`
  (Task 5b), ma viaggia insieme a un test vivo e verde
  (`test_manual_download_lascia_il_file_senza_catalogare`,
  `tests/test_soulseek_download_job.py:157`) che lo chiama direttamente: non e'
  orfano di copertura, solo di chiamante di produzione.
