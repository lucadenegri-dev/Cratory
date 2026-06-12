# DJ Assistant — AI DJ Set Builder & Library Expansion

Webapp personale (locale/self-hosted) per preparare DJ set in modo intelligente: importa la libreria da Rekordbox XML, arricchisce i metadata via Spotify, genera set coerenti con un agente AI, spiega le scelte e suggerisce come ampliare la collezione (crate digging contestualizzato).

**Non è** un software per suonare musica: è un assistente di preparazione, analisi e scoperta.

## Documentazione

| Documento | Contenuto |
|---|---|
| [docs/01-product-vision.md](docs/01-product-vision.md) | Contesto, obiettivi, cosa NON fa, criteri di successo |
| [docs/02-architecture.md](docs/02-architecture.md) | Stack, moduli, principio deterministico vs AI |
| [docs/03-data-model.md](docs/03-data-model.md) | Entità, schema dati, note sul formato XML reale |
| [docs/04-api-spec.md](docs/04-api-spec.md) | Endpoint REST del backend |
| [docs/05-functional-spec.md](docs/05-functional-spec.md) | Specifica funzionale dettagliata (F1–F15) |
| [docs/06-roadmap.md](docs/06-roadmap.md) | Fasi MVP 1→4 con checklist |

La bozza originale del progetto è conservata in [prompt_ai_dj_set_builder.md](prompt_ai_dj_set_builder.md).

## Stack

```text
Backend:    Python + FastAPI
Frontend:   React / Next.js
Database:   SQLite (MVP) → PostgreSQL (futuro)
ORM:        SQLAlchemy + Pydantic
XML:        lxml
Esterni:    Spotify Web API (OAuth), Discogs API, MusicBrainz API
AI:         LLM API astratta dietro un service layer
```

## Dati di esempio

[export_rekordbox.xml](export_rekordbox.xml) — export reale da Rekordbox 7.2.14 con 293 tracce (Spotify, SoundCloud e file locali). Usato come fixture per sviluppo e test.

## Setup

Prerequisiti: Python 3.12+, Node.js 20+.

### Backend (FastAPI, porta 8000)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # opzionale: i default funzionano per MVP 1
uvicorn app.main:app --reload --port 8000
```

API docs interattive: http://localhost:8000/docs

### Frontend (Next.js, porta 3000)

```powershell
cd frontend
npm install
npm run dev
```

App: http://localhost:3000

### Test

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests
```

I test usano `export_rekordbox.xml` (libreria reale, 293 tracce) come fixture.

### Primo utilizzo

1. Avvia backend e frontend.
2. Dalla Dashboard carica il file XML esportato da Rekordbox.
3. Esplora la libreria, genera un set dal Set Builder, esporta in testo/CSV.

> Nota: fino a MVP 2 (enrichment Spotify) le tracce Spotify appaiono senza titolo/artista — è un limite dell'export Rekordbox, non un bug.

## Stato del progetto

🔨 MVP 1 in corso — backend completo e testato, frontend in sviluppo. Stato dettagliato in [PROGRESS.md](PROGRESS.md), fasi in [roadmap](docs/06-roadmap.md).
