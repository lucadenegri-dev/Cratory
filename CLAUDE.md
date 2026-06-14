# CLAUDE.md — Guida allo sviluppo

## Cos'è questo progetto

**DJ Assistant**: webapp personale, locale/self-hosted, mono-utente. Importa una **playlist da Spotify**, normalizza e arricchisce le tracce con metadata e feature musicali (BPM, key, mood, energia via GetSongBPM/MusicBrainz/Last.fm), genera bozze di DJ set con ruoli e spiegazioni (motore deterministico + agente AI), segnala i buchi della playlist, aiuta a scoprire nuova musica compatibile e permette editing manuale ed export. **Non riproduce audio.**

> **Rekordbox rimosso.** Il flusso parte esclusivamente da playlist streaming (Spotify; SoundCloud in coda). L'import XML Rekordbox è eliminato dal progetto.

La specifica completa è in `docs/` (leggere nell'ordine 01→06).

## Regole non negoziabili

1. **Separazione motore deterministico / agente AI.** Import, normalizzazione, deduplica, enrichment, scoring, ruoli, gap analysis, validazione = codice deterministico. Narrativa, interpretazione prompt, suggerimenti, discovery = AI. Mai mischiare.
2. **BPM/key/feature musicali non si inventano.** Arrivano esclusivamente dall'enrichment esterno (GetSongBPM, MusicBrainz, Last.fm), con `enrichment_source`/`confidence`. Un dato già presente **non viene mai sovrascritto**.
3. **Lo streaming non fornisce BPM/key per il mixing**: dà identità traccia (ISRC, id, url) e metadata editoriali (titolo, artista, cover, durata).
4. **L'AI non riceve mai l'intera libreria**: solo candidate filtrate dal Candidate Engine (cap 60).
5. **Ogni output AI è validato** (Validation Engine + schemi Pydantic) prima di essere mostrato.
6. **L'AI non inventa dati fattuali**: distingue dati da fonti esterne, inferenze musicali, ipotesi creative.

## Stack

Backend Python + FastAPI, SQLAlchemy su SQLite (PostgreSQL in futuro), Pydantic. Frontend React/Next.js 16 (App Router, Tailwind + design system). Integrazioni (Spotify OAuth, provider feature musicali GetSongBPM/MusicBrainz/Last.fm, LLM Anthropic) dietro interfacce in `integrations/`, sempre con cache e gestione rate limit.

Struttura backend a layer: `routers/` (solo HTTP) → `services/` (logica) → `repositories.py` (query) → `models.py` + `schemas.py` + `serializers.py` + `integrations/` + `core/` (config, logging, errori). Type hints ovunque. Config via variabili ambiente (`.env.example` aggiornato).

## Identificazione tracce e matching

- Identità streaming: `platform` + `platform_track_id`, `isrc`, `url`.
- Deduplica/enrichment, in ordine: **ISRC → platform_track_id → artist+title+duration → fuzzy artist+title**.
- Stati traccia: `imported | enriched | ready_for_set | missing_features | low_confidence` (`services/track_status.py`).

## Comandi

```powershell
# Backend (da backend/)
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000   # avvio (docs su /docs)
.\.venv\Scripts\python.exe -m pytest tests  # test

# Frontend (da frontend/)
npm run dev                                  # porta 3000, proxy verso :8000
```

Node è in `C:\Program Files\nodejs` (nei terminali vecchi aggiungere al PATH: `$env:Path += ";C:\Program Files\nodejs"`).

## Layout backend

```
routers/       playlists, tracks, transitions, sets, spotify, enrichment, ai
routers/       + discovery, services (stato unificato integrazioni)
services/      playlist_import, manual_import, feature_enrichment, track_status,
               scoring, candidate_engine, set_generator, ai_agent, validation,
               set_editor, alternatives, gap_analysis, camelot, discovery
integrations/  spotify.py, llm.py, getsongbpm.py, musicbrainz.py, lastfm.py
repositories.py, models.py, schemas.py, serializers.py
core/          config.py (setup_logging, Settings)
```

## Stato e prossimo passo

Consultare **`PROGRESS.md`** (checklist aggiornata a ogni milestone, da committare).

Completati: D1 Rimozione Rekordbox · D2 Cache enrichment · E AI prompt arricchito (`candidate_profile`) · F Discovery mode (read pipeline).

> **Discovery è Last.fm-centric.** Spotify `/recommendations` è deprecato (403/404 per app in development mode dal 27/11/2024). Last.fm fornisce la similarità (`integrations/lastfm.py`), Spotify resta solo resolver (`SpotifyWebClient.search_track`, endpoint `/search`). L'AI spiega ma non sceglie i candidati.

Completati anche: **Discovery write-back** (`POST /api/discovery/add` → libreria dell'app via `import_single_track`), **Import manuale playlist** (`services/manual_import.py`), **enrichment mood/energia** (Last.fm `LastFmTagProvider` per genere+mood dai tag; `estimate_energy` proxy deterministico) e **rimozione enrichment metadata Spotify** (i metadata arrivano dall'import; `year` catturato lì).

> **Enrichment feature** = catena GetSongBPM (BPM/key/dance) → MusicBrainz (label/release/genere) → Last.fm (genere+mood). L'energia è un proxy stimato (`estimate_energy`), non un dato di un provider. Non esiste fonte gratuita per mood/energia reali (Spotify audio-features deprecato).

**Toggle Set Builder technical/creative** fatto: `mode` su `SetGenerationRequest`; `CREATIVE_SYSTEM_PROMPT` (l'AI usa la sua conoscenza musicale, sempre validata); `AI_MODEL_CREATIVE` opzionale + `_model_for(req)` in `sets.py` per usare un modello più capace solo in creative.

Prossimi step nell'ordine:
1. **Valutare modello AI economico** (Haiku 4.5 via `AI_MODEL`, o provider locale Ollama dietro l'ABC `LLMClient`). Con il toggle, technical può girare su un modello economico di default.
2. **Test reale** Discovery + enrichment + creative con chiavi (`LASTFM_API_KEY`/`GETSONGBPM_API_KEY`/`AI_API_KEY`).
3. **SoundCloud import** / **F10** / **PostgreSQL** (backlog).

Vedere `docs/06-roadmap.md` per checklist dettagliata.
