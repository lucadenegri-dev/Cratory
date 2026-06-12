# PROGRESS — stato sviluppo

> **File di ripresa lavoro.** Aggiornare e committare a ogni milestone. Se la sessione si interrompe, ripartire da qui: leggere questo file, `CLAUDE.md` e `docs/06-roadmap.md`.

## Stato attuale

**Fase:** ✅ MVP 1 COMPLETATO — prossimo: MVP 2 (Spotify OAuth + enrichment)
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

## Prossimo passo: MVP 2

1. Implementare `SpotifyClient` concreto in `backend/app/integrations/` (OAuth code flow, endpoint login/callback come da `docs/04-api-spec.md`).
2. Tabella cache enrichment + servizio batch che completa title/artist/album/cover delle 198 tracce Spotify (MAI toccare bpm/tonality).
3. UI: cover nella Library/Track Detail, bottone "Enrich" in Dashboard, pagina Settings per le credenziali.
4. Creazione playlist Spotify da un set generato.

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
