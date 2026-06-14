# PROGRESS — stato sviluppo

> **File di ripresa lavoro.** Aggiornare e committare a ogni milestone. Se la sessione si interrompe, ripartire da qui: leggere questo file, `CLAUDE.md` e `docs/06-roadmap.md`.

## Stato attuale

**Fase:** MVP 1-3 + Pivot Fasi A-C completati e testati (76 backend verdi). **Nuovo scope (14/06/2026):** rimozione Rekordbox, AI prompt arricchito, Discovery mode. Prossimo: pulizia Rekordbox.

**Ultimo aggiornamento:** 2026-06-14

---

## Nuovo scope — decisioni del 14/06/2026

Il progetto ha ridefinito il perimetro:

- **Rekordbox XML rimosso** — non è più neanche opzionale. Il flusso parte solo da playlist streaming.
- **SoundCloud** — rimandato a dopo il completamento del flusso Spotify. Valutare fattibilità API prima di implementare.
- **Import manuale** — CSV/testo libero "Artista - Titolo" da aggiungere, in coda dopo Discovery mode.
- **AI prompt arricchito** — l'AI riceverà il profilo completo della playlist (BPM arc, keys dominanti, gap, mood target) oltre ai soli candidati.
- **Discovery mode** — nuova funzionalità principale: suggerisce musica nuova compatibile con il set/playlist dell'utente. Due entry point: gap-driven (colma buchi specifici) e playlist-seed (espandi una playlist). Fonti: Spotify `/recommendations` + Last.fm similar artists. AI spiega perché ogni traccia risolve il problema.

---

## Roadmap nuova

### Fase D1 — Rimozione Rekordbox

- [ ] Elimina `routers/imports.py` + endpoint `POST /api/imports`
- [ ] Elimina `services/rekordbox_parser.py` + `services/import_service.py`
- [ ] Rimuovi `export_rekordbox.xml` e `tests/conftest.py` fixture che la usa
- [ ] Aggiorna `tests/` che dipendono da Rekordbox (rimpiazza fixture con dati sintetici Spotify)
- [ ] Rimuovi voce "Upload XML" dalla dashboard frontend
- [ ] Rimuovi `lxml` da `requirements.txt`
- [ ] Verifica: `pytest` verde, `npm run build` OK, `/api/tracks` mostra solo tracce da Spotify

### Fase D2 — Cache enrichment

- [ ] Aggiunge tabella/colonne cache in DB: `enrichment_cache` (provider, lookup_key, result_json, cached_at)
- [ ] `feature_enrichment.py`: legge dalla cache prima di chiamare il provider
- [ ] `GET /api/enrichment/features/status` espone hit/miss ratio
- [ ] Test: enrichment su traccia già in cache → zero chiamate rete

### Fase E — AI prompt arricchito

- [ ] `ai_agent.py`: calcola profilo playlist (BPM arc, Camelot distribution, top generi, mood medio, gap identificati) e lo include nel prompt
- [ ] Il prompt specifica esplicitamente cosa vuole l'utente (mood target, energia, durata) come vincoli narrativi
- [ ] Test: `FakeLLM` riceve il profilo completo nel prompt (assertion su contenuto)

### Fase F — Discovery mode

- [ ] Integrazione `SpotifyRecommendationsClient`: seed tracks + audio features → lista candidati
- [ ] Integrazione `LastFMProvider` concreto: similar artists → candidati aggiuntivi
- [ ] `services/discovery.py`: orchestratore che combina le due fonti, dedup, ranking per compatibilità con il set/playlist
- [ ] Endpoint `POST /api/discovery/gap` (gap-driven: riceve gap identificato, restituisce candidati rankkati)
- [ ] Endpoint `POST /api/discovery/expand` (playlist-seed: riceve playlist_id, restituisce candidati per espanderla)
- [ ] AI: per ogni candidato spiega perché risolve il problema specifico (gap BPM, energia, Camelot)
- [ ] Frontend: pagina Discovery con due tab (Gap-driven / Espandi playlist), card traccia con score di compatibilità e spiegazione AI, azione "Aggiungi a playlist"

### Backlog

- [ ] Import manuale playlist (CSV o testo "Artista - Titolo")
- [ ] SoundCloud import (valutare fattibilità API prima)
- [ ] F10 Transition Finder classification (technically safe / creative risk / good reset)
- [ ] Last.fm provider per generi/tag aggiuntivi (blocco enrichment)
- [ ] PostgreSQL migration (low priority, SQLite sufficiente per mono-utente)

---

## Storico completato

### MVP 1-3 + Pivot A-C (completo al 13/06/2026, 76 test verdi)

**MVP 1 — Core deterministico** ✅
- Parser Rekordbox XML, import service, scoring transizioni, set generator algoritmico, API rest, 293 tracce fixture

**MVP 2 — Spotify** ✅
- `SpotifyWebClient` OAuth (client_credentials + authorization_code)
- Enrichment metadata (title/artist/album/cover/generi), cache via `enriched_at`, asincrono con polling
- Hardening rate limit 429, redirect URI 127.0.0.1, fallback endpoint batch
- Test reale (12/06/2026): 198 tracce arricchite, 0 not found

**MVP 3 — AI Set Agent** ✅
- `AnthropicLLMClient` SDK ufficiale, structured outputs, adaptive thinking
- AI Set Agent: candidate engine (cap 60) → LLM → validation → narrative
- Validation Engine: track_id verificati, dedup, max artista, durata, BPM/Camelot jump warnings
- Generazione asincrona (`generate-async` + polling status)
- Set salvati + editing (sposta/rimuovi/sostituisci), F9 Alternative Generator
- Redesign UI (Tailwind + design system, tema scuro/lime)
- Tuning latenza: effort=low + adaptive thinking → ~66s, qualità ottima (default)
- Test reale (13/06/2026): 4 set generati, qualità ottima

**Pivot Fase A — Fondamenta streaming-first** ✅
- `rekordbox_track_id` nullable, modello `Playlist`, campi feature (camelot_key, mood, energy, danceability, vocalness, label, release_date, enrichment_source/confidence)
- Stati traccia: imported | enriched | ready_for_set | missing_features | low_confidence
- Import playlist Spotify deterministico con deduplica ISRC
- Gap Analysis deterministica (openers, ponti BPM, Camelot, energia, vocal consecutivi, variety)
- Ruoli set (`assign_roles`, peak ~70%)

**Pivot Fase B — Provider feature musicali** ✅
- `GetSongBPMProvider`: BPM/key/Camelot, confidenza stimata, httpx iniettabile
- `MusicBrainzProvider`: ISRC → label/release_date/genere
- `ChainedFeatureProvider`: GetSongBPM → MusicBrainz, first-wins
- Router `/api/enrichment/features` asincrono con polling
- Frontend: card feature musicali in Settings con progress bar

**Pivot Fase C — Set Builder dalla playlist** ✅
- `SetGenerationRequest.playlist_id` → candidate engine scoped alla playlist
- Scoring feature: energia/mood/genere in `_candidate_score`
- Export Markdown con ruolo/BPM/key/durata/transizione
- Frontend: Set Builder con selettore playlist + energia/mood, badge ruolo, nota transizione

**Logging (13/06/2026)** ✅
- Console + file rotante `backend/logs/djassistant.log` (5×2MB)
- Middleware log richieste, livello via `LOG_LEVEL`

---

## Come riprendere

1. `git log --oneline` per vedere i checkpoint.
2. Backend: `cd backend; .\.venv\Scripts\Activate.ps1; pytest` — i test devono essere verdi.
3. Avvio backend: `uvicorn app.main:app --reload --port 8000` (da `backend/`).
4. Proseguire dalla prima voce non spuntata della roadmap nuova (Fase D1 — Rimozione Rekordbox).

## Note tecniche

- Python 3.13.2, git 2.45.1.
- Node in `C:\Program Files\nodejs` (nei terminali vecchi: `$env:Path += ";C:\Program Files\nodejs"`).
- Next.js 16: `params` è una `Promise` nei client component — usare `use(params)`.
- OAuth Spotify: redirect URI deve essere esattamente `http://127.0.0.1:8000/api/spotify/callback` nel dashboard Spotify.
- AI: senza impostare l'effort, Sonnet 4.6 usa default `high` → thinking massiccio → blocco. Usare sempre `AI_EFFORT=low` + `AI_THINKING=adaptive`.
