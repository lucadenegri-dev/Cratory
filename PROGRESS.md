# PROGRESS — stato sviluppo

> **File di ripresa lavoro.** Aggiornare e committare a ogni milestone. Se la sessione si interrompe, ripartire da qui: leggere questo file, `CLAUDE.md` e `docs/06-roadmap.md`.

## Stato attuale

**Fase:** D1-F + Discovery write-back + Import manuale + enrichment mood/energia + rimozione enrich Spotify + toggle Set Builder technical/creative (90 test verdi, 14/06/2026). Discovery è Last.fm-centric. Prossimo: valutazione modello AI economico (Haiku/Ollama); test reale con chiavi.

**Ultimo aggiornamento:** 2026-06-14

> **Allineamento spec `nuovo_progetto.md` verificato (14/06/2026).** Progetto e documentazione (`docs/01`→`06`, `README`, `CLAUDE.md`) confrontati riga per riga con la nuova specifica: import playlist (Spotify utente/collaborative/liked + manuale, SoundCloud in backlog), rimozione Rekordbox, enrichment con tutti i campi richiesti, Set Builder con input/output e ruoli `intro|warmup|groove|transition|peak|release|closing`, separazione algoritmo/AI, gap analysis, set editor, export (Markdown/CSV/testo + playlist Spotify; link SoundCloud in backlog). **Tutto già implementato.** Unico ritocco di codice: aggiunti a `services/scoring.py` i due score standalone mancanti `bpm_compatibility_score` e `key_compatibility_score` (0-100), così tutti i sei score nominati dalla spec sez. 5 esistono come funzioni pubbliche e l'architettura doc è accurata (+1 test in `test_scoring.py`).

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

### Fase D1 — Rimozione Rekordbox ✅ (14/06/2026)

- [x] Elimina `routers/imports.py` + endpoint `POST /api/imports`
- [x] Elimina `services/rekordbox_parser.py` + `services/import_service.py`
- [x] Rimuovi `export_rekordbox.xml` e `tests/conftest.py` fixture che la usa
- [x] Aggiorna `tests/` che dipendono da Rekordbox (rimpiazza fixture con dati sintetici Spotify)
- [x] Rimuovi voce "Upload XML" dalla dashboard frontend
- [x] Rimuovi `lxml` da `requirements.txt`
- [x] Verifica: `pytest` verde, `npm run build` OK, `/api/tracks` mostra solo tracce da Spotify

### Fase D2 — Cache enrichment ✅ (14/06/2026)

- [x] Aggiunge tabella/colonne cache in DB: `enrichment_cache` (provider, lookup_key, result_json, cached_at)
- [x] `feature_enrichment.py`: bulk pre-load cache, legge dalla cache prima di chiamare il provider
- [x] Cache upsert: aggiorna riga esistente o inserisce nuova; caches anche not-found (None)
- [x] Test: enrichment su traccia già in cache → zero chiamate rete; force=True bypassa cache

### Fase E — AI prompt arricchito ✅ (14/06/2026)

- [x] `ai_agent.py`: calcola profilo candidate (BPM arc, Camelot distribution, top generi, avg energia, lacune) e lo include nel payload come `candidate_profile`
- [x] System prompt aggiornato: istruisce l'AI a usare `candidate_profile` per la visione d'insieme
- [x] Test: `FakeLLM` riceve il profilo completo nel payload (assertion su bpm_range, key_distribution)

### Fase F — Discovery mode ✅ (14/06/2026, read pipeline)

> **Pivot architetturale:** Spotify `/recommendations` (+ related-artists, audio-features) è
> **deprecato dal 27/11/2024**: restituisce 403/404 alle app nuove o in development mode
> (esattamente il caso di questa app). Discovery è quindi **Last.fm-centric**: Last.fm fornisce
> la similarità, Spotify resta solo resolver (endpoint `/search`, funzionante in dev mode).

- [x] Integrazione `LastFMClient` concreto (`integrations/lastfm.py`): `similar_artists`, `similar_tracks`, `artist_top_tracks`, `top_tracks_by_tag`; httpx iniettabile, normalizza il dict-singolo di Last.fm
- [x] ABC `SimilarityClient` in `integrations/__init__.py`
- [x] Resolver Spotify: `SpotifyWebClient.search_track(artist, title)` (client_credentials, dev-mode safe)
- [x] `services/discovery.py`: orchestratore (seed → similarità → dedup vs libreria → resolve → ranking per compatibilità). Dedup per (artista,titolo) e per ISRC post-resolve
- [x] Endpoint `POST /api/discovery/expand` (playlist-seed) e `POST /api/discovery/gap` (gap-driven, usa tag per i gap di genere) + `GET /api/discovery/status`
- [x] AI (opzionale, best-effort): spiega in una frase perché ogni candidato è coerente / colma il gap; non sceglie i candidati
- [x] Frontend: pagina Discovery con due tab (Espandi playlist / Colma un buco), card traccia con compatibilità, sorgente, spiegazione AI e link Spotify
- [x] Test: `test_discovery.py` (9) — parsing Last.fm senza rete, dedup libreria/ISRC, ranking, resolver, spiegazioni AI, gap per genere, add-to-library
- [x] **Write-back:** `POST /api/discovery/add` importa il candidato nella **libreria dell'app** (decisione utente: non su Spotify). `playlist_import.import_single_track` (idempotente, dedup ISRC/spotify_id). Bottone "Aggiungi" sulla card
- [ ] **Da fare:** test reale Discovery con chiave Last.fm

### Backlog → Import manuale playlist ✅ (14/06/2026)

- [x] `services/manual_import.py`: `parse_line` ("Artista - Titolo", en/em dash, TSV, CSV, solo-titolo) + `import_manual_playlist` (playlist `kind=manual`, dedup per nome vs libreria)
- [x] Endpoint `POST /api/playlists/import-manual` (422 se nessuna traccia riconosciuta)
- [x] Frontend: card "Import manuale" nella pagina Playlist (nome + textarea tracklist)
- [x] Test `test_manual_import.py` (4)

### Enrichment mood/energia + rimozione enrich Spotify ✅ (14/06/2026)

- [x] Last.fm `track.getTopTags` → `LastFmTagProvider` (`MusicFeatureProvider`): ricava **mood** (mappa tag→mood) e genere (fallback) dai top tag; in catena dopo GetSongBPM/MusicBrainz
- [x] **Energy proxy** deterministico (`estimate_energy`): stima energia da BPM + danceability + genere (Spotify audio-features deprecato, Cyanite a pagamento) → gli score d'arco non lavorano più su dati vuoti
- [x] **Rimosso l'enrichment metadata Spotify** (ridondante: i metadata arrivano dall'import; sorgente = Spotify, non più Rekordbox): cancellati `services/enrichment.py`, endpoint `/api/spotify/enrich*`, `test_enrichment.py`, card UI + tipi TS. `year` ora catturato all'import per non perderlo
- [x] Test: tag provider, energy proxy, enrichment popola energia (`test_feature_provider.py`); top_tags parsing (`test_discovery.py`). **88 verdi**, frontend build OK

### Toggle Set Builder technical / creative ✅ (14/06/2026)

- [x] Campo `mode: technical|creative` su `SetGenerationRequest` (default technical)
- [x] `CREATIVE_SYSTEM_PROMPT` in `ai_agent.py`: l'AI usa la sua conoscenza musicale (arco emotivo, contrasti, sorprese) restando vincolata alle candidate + Validation Engine invariato
- [x] Modello per-modalità: `AI_MODEL_CREATIVE` (opzionale) → `get_llm_client(model)`; `_model_for(req)` in `sets.py`. Permette AI_MODEL economico + modello capace solo in creative
- [x] Frontend: toggle Tecnico/Creativo nel Set Builder (visibile quando l'AI è attiva)
- [x] Test: prompt creative vs technical (`test_ai_agent.py`). **90 verdi**, build OK

### Backlog

- [x] Import manuale playlist (CSV o testo "Artista - Titolo") — fatto 14/06/2026
- [ ] Valutare modello più economico per l'AI (Haiku 4.5 via AI_MODEL / provider locale Ollama dietro l'ABC) — discusso 14/06
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
- AI: modello di default `claude-opus-4-8` (override `AI_MODEL`). Con effort alto + thinking esteso la generazione è molto lenta → usare `AI_EFFORT=low` + `AI_THINKING=adaptive`.
