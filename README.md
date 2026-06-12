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

> Da completare con l'avvio dello sviluppo (MVP 1): istruzioni backend, frontend, `.env.example`.

## Stato del progetto

📋 Fase di specifica — pronto per iniziare MVP 1 (vedi [roadmap](docs/06-roadmap.md)).
