# CLAUDE.md — Guida allo sviluppo

## Cos'è questo progetto

**DJ Assistant**: webapp personale, locale/self-hosted, mono-utente. Importa la libreria DJ da un export XML di Rekordbox, arricchisce i metadata via Spotify, genera DJ set con un agente AI (con spiegazioni) e suggerisce come ampliare la libreria. **Non riproduce audio.**

La specifica completa è in `docs/` (leggere nell'ordine 01→06). La bozza originale è `prompt_ai_dj_set_builder.md`. Fixture dati reale: `export_rekordbox.xml` (293 tracce).

## Regole non negoziabili

1. **Separazione motore deterministico / agente AI.** Parsing, scoring, filtri, validazione = codice deterministico. Narrativa, interpretazione prompt, suggerimenti = AI. Mai mischiare.
2. **Rekordbox è la fonte di verità per i dati DJ** (BPM, tonalità, durata, beatgrid, cue, play count). Spotify non li sovrascrive mai.
3. **L'AI non riceve mai l'intera libreria**: solo candidate filtrate dal Candidate Engine.
4. **Ogni output AI è validato** (Validation Engine + schemi Pydantic) prima di essere mostrato.
5. **L'AI non inventa dati fattuali**: distingue dati da fonti esterne, inferenze musicali, ipotesi creative.

## Stack

Backend Python + FastAPI, SQLAlchemy su SQLite (PostgreSQL in futuro), Pydantic, lxml. Frontend React/Next.js. Integrazioni (Spotify OAuth, Discogs, MusicBrainz, LLM) dietro interfacce in `integrations/`, sempre con cache e gestione rate limit.

Struttura backend a layer: `routers/` (solo HTTP) → `services/` (logica) → `repositories/` (query) → `models/` (SQLAlchemy) + `schemas/` (Pydantic) + `integrations/` + `core/` (config, logging, errori). Type hints ovunque. Config via variabili ambiente (`.env.example` aggiornato).

## Insidie del formato XML (verificate sul file reale)

- Spotify: `Location="file://localhostspotify:track:ID"` — e `Name`/`Artist` **vuoti** (arrivano solo con l'enrichment MVP 2). BPM/Tonality però presenti.
- SoundCloud: `Location="file://localhostsoundcloud:tracks:ID"` (`tracks` plurale, ID numerico).
- File locali: `Location="file://localhost/Users/..."` URL-encoded.
- `Tonality` già in notazione Camelot (`7A`, `9A`).
- Valori anomali: `AverageBpm="0.00"`, `Year="0"`, sample da 5–7 secondi (sampler Rekordbox), `Genre` quasi sempre vuoto.
- Figli di `TRACK`: `TEMPO` (beatgrid) e `POSITION_MARK` (cue). La sezione `PLAYLISTS` può essere vuota.

## Comandi

```powershell
# Backend (da backend/)
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000   # avvio (docs su /docs)
.\.venv\Scripts\python.exe -m pytest tests  # test (usano export_rekordbox.xml reale)

# Frontend (da frontend/)
npm run dev                                  # porta 3000, proxy verso :8000
```

Node è in `C:\Program Files\nodejs` (installato via winget; nei terminali vecchi serve `$env:Path += ";C:\Program Files\nodejs"`).

## Layout backend

`routers/` (solo HTTP) → `services/` (parser, scoring, candidate_engine, set_generator, import_service) → `repositories.py` (query) → `models.py` + `schemas.py` + `serializers.py` (ORM→Pydantic con campi derivati) + `integrations/` (interfacce astratte MVP 2-4) + `core/config.py`.

## Stato e prossimo passo

Consultare **`PROGRESS.md`** (checklist aggiornata a ogni milestone, da committare). MVP 1 backend completo e testato; vedere la prima voce non spuntata per riprendere.
