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

138 path unici / 148 coppie metodo+path (coerente con la baseline del Task 1):

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

7 endpoint senza call site nel frontend; verificati uno per uno su frontend, backend/tests,
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
- `POST /api/downloads/search`, `POST /api/downloads/manual` — confermati morti, vedi L1.
- `GET /api/rekordbox/pending`, `POST /api/organize/analyze` — dubbi, vedi L3.

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
- [L1] `app/services/local_import.py:55` — `build_normalized()` — unico hit in `backend/app` e' la definizione, **0 hit nei test**; il chiamante storico `import_local_folder` e' stato cancellato; i consumatori superstiti del modulo importano solo `scan_folder` (`library_index.py:39`, `pipeline.py:21`, `tests/test_local_import.py:10`). E' la causa dei 4 import morti qui sopra
- [L1] `app/services/audio_energy.py:113` — `backfill_energy()` — 0 chiamanti di produzione; gli unici usi sono `tests/test_audio_energy.py:141` (import) e `:155` (call), quindi test che coprono SOLO codice morto. `library_index.py:30` importa da questo modulo solo `analyze_file, recompute_energy`
- [L1] `app/services/soulseek_select.py:251` — `best_for_auto()` — unico hit in `backend/app` e' la definizione; usi solo in `tests/test_soulseek_select.py` (import `:3`, chiamate `:38,45,76,91,108,131`). E' un wrapper di comodo su `rank_candidates`+`auto_pick_candidates` che la produzione scavalca (`soulseek_download_job.py:24`, `routers/downloads.py:18` importano le due primitive)

Endpoint morti (coppia inseparabile, stesso commit li ha orfanati):

- [L1] `app/routers/downloads.py:240` — `POST /api/downloads/search` (handler `search`) — 0 call site nel frontend; il wrapper `searchDownloads()` in `frontend/lib/api/downloads.ts` e' stato **cancellato di proposito** nel commit `a56b60e` ("feat(wishlist): link a slskd al posto della ricerca libera", messaggio: "Rimosso il codice morto"), sostituito nella UI dal link esterno "Apri slskd". Da non confondere con `POST /api/downloads/candidates`, che e' vivo (`frontend/lib/api/downloads.ts:28`). Coperto solo da `tests/test_downloads_router.py:84,101,124,154`
- [L1] `app/routers/downloads.py:264` — `POST /api/downloads/manual` (handler `download_manual`) — stesso commit `a56b60e` ha cancellato `downloadManual()`; 0 call site; coperto solo da `tests/test_downloads_router.py:161,176`. **Cascata:** restano orfani `SearchIn` (`downloads.py:62`), `ManualDownloadIn` (`downloads.py:66`) e `start_manual_job()` (`app/services/soulseek_download_job.py:357`). **NON** rimuovere `_slskd_file` (`:98`) e `_candidate_out` (`:90`): servono anche a `/track` (`:192`) e `/candidates` (`:166`). Aggiornare `docs/API.md:722-758` e `docs/ARCHITECTURE.md:134,152-153` nella stessa passata (Task 11/12)

### Findings L2 — consolidamento (Task 4)

Nessun L2 tocca `app/organize/` (vincolo del piano).

- [L2] `app/routers/sets.py:228-236` + `app/routers/playlists.py:449-458` — blocco di render M3U8 duplicato quasi verbatim (unica differenza: il set itera `SetlistTrack` e dereferenzia `.track`); l'output byte-per-byte e' identico, commento italiano compreso. `playlists.py:400-403` ammette la duplicazione a parole ("stessa logica dell'export set"). **Entrambi i siti sono fissati dai test**: `tests/test_playlist_export.py:30,48,64` e `tests/test_set_texts.py:126,174`. Fusione meccanica: `render_m3u8(tracks, total)`
- [L2] `app/routers/playlists.py:78` + `app/routers/spotify.py:47` — `_http_error(exc: SpotifyError)` **byte-identico** (verificato con `diff`: nessuna differenza). Fusione meccanica: spostarlo accanto ad `api_error` in `app/core/http_errors.py`. **Caveat onesto:** la mappatura non e' asserita da nessun test a livello router — `tests/test_streaming_import_job.py:210-256` asserisce gli stessi tre codici ma sullo `state["error_code"]` del job, altro code path. Il Task 4 aggiunga un test per sito prima di fondere. Da **non** fondere con `app/routers/soundcloud.py:32`: altra famiglia di eccezioni, altri codici (sarebbe una decisione di design)
- [L2] `app/services/auto_link.py:20` (`_label`) + `app/services/soulseek_download_job.py:54` (`_track_label`) — corpi identici (3 righe), differisce solo il nome. Entrambi coperti: `tests/test_auto_link.py` e `tests/test_soulseek_download_job.py` (asserisce `current_label`). La localizzazione delle stringhe italiane hard-coded e' fuori scope: fondere, non tradurre
- [L2] `app/services/audio_analysis_job.py:39` + `app/services/streaming_import_job.py:76` — `_spawn(fn)` identico, docstring compresa. Entrambi monkeypatchati dai test (`test_audio_analysis_job.py:22`, `test_streaming_import_job.py:24`, `test_job_double_start.py:215`, ...). Fusione meccanica in un helper condiviso
- [L2] `app/routers/sets.py:161` (`_fmt_dur`) + `app/routers/playlists.py:436` (stessa espressione inline, stesso fallback `"—"`) — chiamare `_fmt_dur` anche dal ramo markdown delle playlist. Il resto dei rami CSV/markdown/testo e' genuinamente diverso e **non** va fuso
- [L2] `app/services/discovery_dig.py:43` + `app/services/manual_import.py:26` — `_norm(value)` one-liner identico. Entrambi coperti (`test_discovery_dig.py`, `test_manual_import.py`). Valore marginale (2 righe, moduli scorrelati): fondere solo se il Task 4 crea comunque un modulo di util testuali. **ATTENZIONE:** gli altri 7 helper `_norm`-simili nel backend sono tutti diversi e portanti (`candidate_engine.py:19` NFKD+ASCII, `library_index.py:53` strip `feat.`/`(Original Mix)`, `soulseek_select.py:73` `&`->`and`, `playlist_import.py:107` casefold alnum, `preview.py:38` ritorna un set, `rekordbox_import.py:76` NFC+normpath, `scoring.py:594`) — **non** toccarli

### Candidati scartati (falsi positivi, per tracciabilita')

- `app/integrations/_http.py:211` `exc_info` (vulture **100%**) — **falso positivo**: e' il varargs di `def __exit__(self, *exc_info)`, protocollo context manager di `ClosableHttpClient` (`:189`). Rimuoverlo rompe ogni `with client:` con `TypeError`; `tests/test_integrations_http.py:125` percorre esattamente quel path. Al massimo si rinomina in `*_`, ma non e' codice morto
- `app/main.py:88` `log_requests` — middleware registrato dal decorator `@app.middleware("http")`
- ~100 "unused variable" di vulture a confidence 60 in `models.py`/`schemas.py` — colonne SQLAlchemy e campi Pydantic dichiarativi
- Tutti gli handler dei router — referenziati solo dai decorator

### Findings L3 — segnalazione, nessuna azione automatica

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

Script one-shot gia' applicati in `app/tools/` (0 importer in `backend/app`; decisione utente:
sono documentazione eseguibile di migrazioni passate o zavorra?):

- [L3] `app/tools/align_genre_from_file.py` — la docstring dice "una-tantum"; 0 importer, 0 test. Il payload `db_hygiene.align_owned_genre_from_file` resta usato da `app/services/genre_align.py:9` e coperto da `tests/test_db_hygiene.py:145-195`: cancellare la CLI non perde logica testata. Citato in `PROGRESS.md:48,65`, `docs/ARCHITECTURE.md:207,360`, `docs/ROADMAP.md:104`
- [L3] `app/tools/backfill_track_files.py` — backfill della migrazione F3, gia' applicata; 0 importer, 1 test (`tests/test_backfill_track_files.py:8`) che coprirebbe solo codice morto
- [L3] `app/tools/cleanup_disk_first.py` — la docstring dice "una-tantum", `PROGRESS.md:1128` dice "One-off maintenance tool"; 0 importer, 0 test. Tutte le op che orchestra sono coperte in `tests/test_db_hygiene.py`
- [L3] `app/tools/migrate_organize_db.py` — migrazione F2 (DB unico) gia' applicata; 0 importer, 1 test (`tests/test_migrate_organize_db.py:12`)
- [L3] `app/tools/backfill_track_files.py:98` + `app/tools/merge_duplicate_tracks.py:70` — `_sessione()` con corpo identico (differisce solo la docstring). Estrazione meccanica in `app/tools/_common.py`, ma contingente: se i one-shot vengono cancellati il problema evapora
- **Da NON toccare in `app/tools/`**: `clean_user_data.py` (unico tool documentato all'utente, `README.md:186`) e `merge_duplicate_tracks.py` (riparazione ricorrente, non one-shot; l'unico "riferimento" trovato dallo scan e' un commento in prosa a `backfill_track_files.py:101`)

Ridondanza architetturale profonda (fusione = decisione di design, esplicitamente fuori
da una passata meccanica):

- [L3] Cinque macchine a stati di job scritte a mano: `app/services/audio_analysis_job.py:21`, `app/services/streaming_import_job.py:46`, `app/services/soulseek_download_job.py:36`, `app/services/mix_identify_job.py:19`, `app/routers/sets.py:64`. Una classe base unificata richiede di decidere: (a) la disciplina di lock (due leggono `_state` senza lock, due con lock e con `_state_snapshot` per la non-reentrancy), (b) la forma del payload di stato (5 shape diverse), (c) la semantica della start-guard (tre ritornano lo stato corrente se gia' in corso, `routers/sets.py:107-113` alza deliberatamente 409 con commento che spiega perche'), (d) i response model gia' fissati da `tests/test_job_response_schemas.py:141`. Il solo `_spawn` e' stato estratto come L2 sopra
- [L3] Idioma "carica o 404" ripetuto ~40 volte nei router (`routers/playlists.py:173,241,265,303,318,336,356,404,...`, `tracks.py:90,128,150,175`, `sets.py:157,176,320`, `dj_sets.py:124,136,149`, `downloads.py:127,189,208,232,279,288,302`, `transitions.py:31`, `spotify.py:119`). Il fix idiomatico (`Depends(get_playlist_or_404)`) romperebbe i test che invocano gli handler **direttamente** anziche' via HTTP (es. `tests/test_playlist_export.py:38` chiama `export_playlist(pl.id, "m3u8", db)`): una `Depends` non si risolve in chiamata diretta. Decisione di design, non pulizia
- [L3] `app/services/set_generator.py:33` — `_STRATEGY_PROFILES` re-esportato da `set_skeleton` ma importato da nessuno (0 hit fuori da `set_skeleton.py`). **Non L1** perche' sta dentro un blocco marcato `# noqa: F401 - re-export per compat test` deliberato: la convenzione spiega l'apparente inutilizzo. Il gemello `_DEFAULT_PROFILE` nello stesso blocco e' invece portante (5 file di test lo importano da `set_generator`) e va lasciato
- [L3] `file_tags_for_tracks(db, [x.id]).get(x.id)` ripetuto 5 volte (`routers/downloads.py:132,294,304`, `routers/discovery.py:313,330`) — manca un wrapper `file_tags_for_track` accanto a `app/repositories.py:203`. Meccanico ma cosmetico

Schema DB (intoccabile per definizione nel piano):

- [L3] Le ~100 voci di `vulture --min-confidence 60` su `app/models.py`, `app/organize/models.py`, `app/schemas.py`, `app/organize/schemas.py` sono colonne SQLAlchemy e campi Pydantic dichiarativi. Alcune sono effettivamente scritte e mai lette dal backend (es. `Track.playlist_name`, `analysis_error`, i vari `updated_at`), ma lo schema non si tocca e il frontend puo' leggerle via i response model: nessuna azione, solo segnalazione

## Fase 2 — Findings frontend

(vuota — compilata dal Task 6, rilevamento frontend)

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

Script one-shot gia' applicati in `app/tools/` (0 importer in `backend/app`; decisione utente:
sono documentazione eseguibile di migrazioni passate o zavorra?):

- [L3] `app/tools/align_genre_from_file.py` — la docstring dice "una-tantum"; 0 importer, 0 test. Il payload `db_hygiene.align_owned_genre_from_file` resta usato da `app/services/genre_align.py:9` e coperto da `tests/test_db_hygiene.py:145-195`: cancellare la CLI non perde logica testata. Citato in `PROGRESS.md:48,65`, `docs/ARCHITECTURE.md:207,360`, `docs/ROADMAP.md:104`
- [L3] `app/tools/backfill_track_files.py` — backfill della migrazione F3, gia' applicata; 0 importer, 1 test (`tests/test_backfill_track_files.py:8`) che coprirebbe solo codice morto
- [L3] `app/tools/cleanup_disk_first.py` — la docstring dice "una-tantum", `PROGRESS.md:1128` dice "One-off maintenance tool"; 0 importer, 0 test. Tutte le op che orchestra sono coperte in `tests/test_db_hygiene.py`
- [L3] `app/tools/migrate_organize_db.py` — migrazione F2 (DB unico) gia' applicata; 0 importer, 1 test (`tests/test_migrate_organize_db.py:12`)
- [L3] `app/tools/backfill_track_files.py:98` + `app/tools/merge_duplicate_tracks.py:70` — `_sessione()` con corpo identico (differisce solo la docstring). Estrazione meccanica in `app/tools/_common.py`, ma contingente: se i one-shot vengono cancellati il problema evapora
- **Da NON toccare in `app/tools/`**: `clean_user_data.py` (unico tool documentato all'utente, `README.md:186`) e `merge_duplicate_tracks.py` (riparazione ricorrente, non one-shot; l'unico "riferimento" trovato dallo scan e' un commento in prosa a `backfill_track_files.py:101`)

Ridondanza architetturale profonda (fusione = decisione di design, esplicitamente fuori
da una passata meccanica):

- [L3] Cinque macchine a stati di job scritte a mano: `app/services/audio_analysis_job.py:21`, `app/services/streaming_import_job.py:46`, `app/services/soulseek_download_job.py:36`, `app/services/mix_identify_job.py:19`, `app/routers/sets.py:64`. Una classe base unificata richiede di decidere: (a) la disciplina di lock (due leggono `_state` senza lock, due con lock e con `_state_snapshot` per la non-reentrancy), (b) la forma del payload di stato (5 shape diverse), (c) la semantica della start-guard (tre ritornano lo stato corrente se gia' in corso, `routers/sets.py:107-113` alza deliberatamente 409 con commento che spiega perche'), (d) i response model gia' fissati da `tests/test_job_response_schemas.py:141`. Il solo `_spawn` e' stato estratto come L2 sopra
- [L3] Idioma "carica o 404" ripetuto ~40 volte nei router (`routers/playlists.py:173,241,265,303,318,336,356,404,...`, `tracks.py:90,128,150,175`, `sets.py:157,176,320`, `dj_sets.py:124,136,149`, `downloads.py:127,189,208,232,279,288,302`, `transitions.py:31`, `spotify.py:119`). Il fix idiomatico (`Depends(get_playlist_or_404)`) romperebbe i test che invocano gli handler **direttamente** anziche' via HTTP (es. `tests/test_playlist_export.py:38` chiama `export_playlist(pl.id, "m3u8", db)`): una `Depends` non si risolve in chiamata diretta. Decisione di design, non pulizia
- [L3] `app/services/set_generator.py:33` — `_STRATEGY_PROFILES` re-esportato da `set_skeleton` ma importato da nessuno (0 hit fuori da `set_skeleton.py`). **Non L1** perche' sta dentro un blocco marcato `# noqa: F401 - re-export per compat test` deliberato: la convenzione spiega l'apparente inutilizzo. Il gemello `_DEFAULT_PROFILE` nello stesso blocco e' invece portante (5 file di test lo importano da `set_generator`) e va lasciato
- [L3] `file_tags_for_tracks(db, [x.id]).get(x.id)` ripetuto 5 volte (`routers/downloads.py:132,294,304`, `routers/discovery.py:313,330`) — manca un wrapper `file_tags_for_track` accanto a `app/repositories.py:203`. Meccanico ma cosmetico

Schema DB (intoccabile per definizione nel piano):

- [L3] Le ~100 voci di `vulture --min-confidence 60` su `app/models.py`, `app/organize/models.py`, `app/schemas.py`, `app/organize/schemas.py` sono colonne SQLAlchemy e campi Pydantic dichiarativi. Alcune sono effettivamente scritte e mai lette dal backend (es. `Track.playlist_name`, `analysis_error`, i vari `updated_at`), ma lo schema non si tocca e il frontend puo' leggerle via i response model: nessuna azione, solo segnalazione

## Riepiloghi checkpoint

(vuota — compilata dai Task 5, 8 e 14 con i riepiloghi di checkpoint)
