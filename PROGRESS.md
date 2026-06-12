# PROGRESS — stato sviluppo

> **File di ripresa lavoro.** Aggiornare e committare a ogni milestone. Se la sessione si interrompe, ripartire da qui: leggere questo file, `CLAUDE.md` e `docs/06-roadmap.md`.

## Stato attuale

**Fase:** ✅ MVP 1 e MVP 2 COMPLETATI — prossimo: MVP 3 (AI Set Agent)
**Ultimo aggiornamento:** 2026-06-12

## Checklist MVP 1

- [x] Git init + commit docs
- [x] Backend skeleton (config, db, modelli SQLAlchemy)
- [x] Parser Rekordbox XML + import service + report
- [x] Test parser su `export_rekordbox.xml` (fixture reale, 293 tracce)
- [x] API import + tracks (filtri)
- [x] Scoring transizioni + test
- [x] API transitions (before/after/score)
- [x] Candidate engine + set generator algoritmico + test
- [x] API sets (generate/list/get/export csv+text)
- [x] Endpoint stats per dashboard (`GET /api/stats`)
- [x] Stub interfacce integrations (Spotify/Discogs/MusicBrainz/LLM in `app/integrations/`)
- [x] Frontend Next.js 16 scaffold (Node 24 installato in `C:\Program Files\nodejs`)
- [x] Frontend: Dashboard (stats+upload), Library (filtri+paginazione), Track Detail (cue+prima/dopo), Set Builder (vincoli+export), Transition Finder (ricerca+dopo/prima)
- [x] README setup + `.env.example`

## Stato verificato

- `pytest` backend: **17/17 verdi** (parser su XML reale, scoring, import idempotente, generator).
- Smoke test API completo OK: import 293 tracce → filtri → transizioni → generate set (9 tracce/46min, target 45) → export text/csv → stats.
- `npm run build` frontend: OK, 6 route.
- Verifica visiva nel browser (preview): Dashboard renderizza, Library carica le 293 tracce dal backend (CORS ok), zero errori console.

## Checklist MVP 2 — ✅ completata

- [x] `SpotifyWebClient` concreto (`integrations/spotify.py`): client_credentials per metadata (nessun login), authorization_code per playlist, refresh token, retry su 429
- [x] Endpoint: GET /api/spotify/status, /login, /callback; POST /enrich?force=, /create-playlist
- [x] Enrichment (`services/enrichment.py`): completa title/artist/album/anno SOLO se vuoti, cover+generi+artisti sempre; `enriched_at` = cache; mai BPM/key
- [x] Tabelle nuove: Artist (generi/popularity), SpotifyToken; colonne Track: album_art_url, spotify_artist_id, enriched_at; migrazione leggera in `db.ensure_schema()`
- [x] Re-import non cancella i metadata arricchiti (fix `_apply` in import_service)
- [x] UI: pagina Settings (stato, login, enrich con istruzioni credenziali), cover in Library e Track Detail, bottone "Crea playlist Spotify" nel Set Builder
- [x] 21 test verdi (4 nuovi con FakeSource: fill-only-empty, DJ-data intoccati, cache, re-import safe)
- [x] Verificato live: migrazione su DB esistente ok (293 tracce), /settings risponde, enrich senza credenziali → 409 con istruzioni

**Enrichment reale ESEGUITO con successo** (12/06/2026): 198 tracce arricchite, 127 artisti, 0 not found. Restrizioni Spotify 2025 scoperte sul campo e gestite:
- Redirect URI: `http://localhost` rifiutato → si usa `http://127.0.0.1:8000/api/spotify/callback` (in .env e nel dashboard Spotify).
- Endpoint batch (`/tracks?ids=`, `/artists?ids=`) → 403 per le app in development mode: il client fa fallback automatico a GET singole.
- Campo `genres` degli artisti: arriva sempre vuoto per le nuove app → Track.genre resta vuoto; i generi arriveranno da Discogs/MusicBrainz (MVP 4). Il candidate engine già tollera il genere assente.

⚠️ Login OAuth utente (per creare playlist) non ancora provato: richiede il browser dell'utente. Redirect URI nel dashboard Spotify deve essere `http://127.0.0.1:8000/api/spotify/callback`.

## Prossimo passo: MVP 3 (AI Set Agent)

1. `LLMClient` concreto in `integrations/` (provider astratto; API key in .env, `claude-api` skill per riferimento API Anthropic).
2. Prompt libero → AI Set Agent: input candidate+scores (F7 in docs/05), output JSON validato con Pydantic.
3. Validation Engine (F8): esistenza track_id, duplicati, durata, vincoli; retry/correzione/warning.
4. Alternative per traccia (F9) e spiegazioni narrative al posto di quelle tecniche.

## Note frontend

- Next.js **16** (App Router): `params` è una `Promise` — nei client component si usa `use(params)`. Docs in `frontend/node_modules/next/dist/docs/`.
- `frontend/dev.cmd` avvia il dev server garantendo Node nel PATH; usato da `.claude/launch.json` per il preview.
- API client e tipi TS in `frontend/lib/api.ts` (`NEXT_PUBLIC_API_URL`, default `http://localhost:8000`).

## Come riprendere

1. `git log --oneline` per vedere i checkpoint.
2. Backend: `cd backend; .\.venv\Scripts\Activate.ps1; pytest` — i test devono essere verdi.
3. Avvio backend: `uvicorn app.main:app --reload --port 8000` (da `backend/`).
4. Proseguire dalla prima voce non spuntata della checklist.

## Note tecniche accumulate

- Node NON era installato; avviata installazione `winget install OpenJS.NodeJS.LTS` (background). Se manca ancora, reinstallare o usare la versione portable.
- Python 3.13.2, git 2.45.1.
- Vedi `CLAUDE.md` per le insidie del formato XML (tracce Spotify senza Name/Artist, ecc.).
