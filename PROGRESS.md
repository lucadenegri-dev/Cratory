# PROGRESS — stato sviluppo

> **File di ripresa lavoro.** Aggiornare e committare a ogni milestone. Se la sessione si interrompe, ripartire da qui: leggere questo file, `CLAUDE.md` e `docs/06-roadmap.md`.

## Stato attuale

**Fase:** MVP 1 — in corso
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
- [ ] Frontend Next.js: scaffold (Node 24 installato in `C:\Program Files\nodejs`, PATH da riaprire)
- [ ] Frontend: Dashboard, Library, Track Detail, Set Builder, Transition Finder
- [ ] README setup (`.env.example` fatto)

## Stato verificato

- `pytest` backend: **17/17 verdi** (parser su XML reale, scoring, import idempotente, generator).
- Smoke test API completo OK: import 293 tracce → filtri → transizioni → generate set (9 tracce/46min, target 45) → export text/csv → stats.

## Come riprendere

1. `git log --oneline` per vedere i checkpoint.
2. Backend: `cd backend; .\.venv\Scripts\Activate.ps1; pytest` — i test devono essere verdi.
3. Avvio backend: `uvicorn app.main:app --reload --port 8000` (da `backend/`).
4. Proseguire dalla prima voce non spuntata della checklist.

## Note tecniche accumulate

- Node NON era installato; avviata installazione `winget install OpenJS.NodeJS.LTS` (background). Se manca ancora, reinstallare o usare la versione portable.
- Python 3.13.2, git 2.45.1.
- Vedi `CLAUDE.md` per le insidie del formato XML (tracce Spotify senza Name/Artist, ecc.).
