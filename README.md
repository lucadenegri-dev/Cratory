# DJ Assistant — AI DJ Set Builder & Discovery

Webapp personale (locale/self-hosted) per preparare DJ set a partire da **playlist Spotify**: importa le tracce, arricchisce BPM/key/mood/energia via provider esterni, genera set coerenti con ruoli e spiegazioni (algoritmo deterministico + agente AI), segnala i buchi della playlist e aiuta a scoprire nuova musica compatibile con il tuo stile.

**Non è** un software per suonare musica: è un assistente di preparazione, analisi e scoperta.

## Documentazione

| Documento | Contenuto |
|---|---|
| [docs/01-product-vision.md](docs/01-product-vision.md) | Contesto, obiettivi, cosa NON fa, criteri di successo |
| [docs/02-architecture.md](docs/02-architecture.md) | Stack, moduli, principio deterministico vs AI |
| [docs/03-data-model.md](docs/03-data-model.md) | Entità, schema dati |
| [docs/04-api-spec.md](docs/04-api-spec.md) | Endpoint REST del backend |
| [docs/05-functional-spec.md](docs/05-functional-spec.md) | Specifica funzionale dettagliata (F1–F15) |
| [docs/06-roadmap.md](docs/06-roadmap.md) | Fasi con checklist |

## Stack

```text
Backend:    Python + FastAPI
Frontend:   React / Next.js 16 (App Router, Tailwind)
Database:   SQLite (MVP) → PostgreSQL (futuro)
ORM:        SQLAlchemy + Pydantic
Esterni:    Spotify Web API (OAuth), GetSongBPM, MusicBrainz, Last.fm
AI:         Anthropic SDK (claude-opus-4-8 default)
```

## Setup

Prerequisiti: Python 3.12+, Node.js 20+.

### Backend (FastAPI, porta 8000)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
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

### Primo utilizzo

1. Avvia backend e frontend.
2. In Settings configura le credenziali Spotify e connetti l'account.
3. Dalla pagina Playlists importa una playlist Spotify (o incolla una tracklist con l'import manuale).
4. Avvia l'enrichment feature (BPM/key/genere) dalla pagina Settings.
5. Dal Set Builder genera un set scegliendo la playlist e i parametri (durata, mood, energia).
6. Edita la scaletta, esporta in Markdown o crea una playlist Spotify.
7. Dalla pagina Discovery scopri musica nuova compatibile (espandi una playlist o colma un buco) e aggiungila alla libreria.

## Stato del progetto

MVP 1-3 + Pivot Fase A-C completati. Inoltre: cleanup Rekordbox, cache enrichment, AI prompt arricchito, **Discovery mode** (Last.fm + resolver Spotify) e import manuale playlist. Discovery non usa Spotify `/recommendations` (deprecato): la similarità arriva da Last.fm.

Stato dettagliato in [PROGRESS.md](PROGRESS.md).
