# 06 — Roadmap

## Fasi completate

- **MVP 1 — Core deterministico** ✅ scoring transizioni, set generator algoritmico, API.
- **MVP 2 — Spotify** ✅ OAuth, enrichment metadata editoriali con cache, async + rate limit.
- **MVP 3 — AI** ✅ AI Set Agent (structured output), prompt libero, spiegazioni narrative, Validation Engine, alternative F9, generazione asincrona, gestione set salvati + editor.
- **Pivot Fase A** ✅ data model streaming-first, import playlist Spotify, gap analysis, ruoli set.
- **Pivot Fase B** ✅ GetSongBPMProvider, MusicBrainzProvider, ChainedFeatureProvider, router enrichment async.
- **Pivot Fase C** ✅ set da playlist (candidate scoped), scoring feature energia/mood/genere, export Markdown.

---

## In lavorazione

### Fase D1 — Rimozione Rekordbox

Rekordbox XML non è più parte del flusso. Si rimuove l'intero import Rekordbox e si ripulisce il codice dipendente.

- [ ] Elimina `routers/imports.py` + endpoint `POST /api/imports`
- [ ] Elimina `services/rekordbox_parser.py` + `services/import_service.py`
- [ ] Rimuovi fixture `export_rekordbox.xml` e aggiorna `tests/conftest.py`
- [ ] Aggiorna test che usano la fixture Rekordbox (sostituisci con dati sintetici Spotify)
- [ ] Rimuovi voce "Upload XML" dalla dashboard frontend
- [ ] Rimuovi `lxml` da `requirements.txt`
- [ ] Verifica: `pytest` verde, `npm run build` OK

### Fase D2 — Cache enrichment

- [ ] Tabella `enrichment_cache` in DB (provider, lookup_key, result_json, cached_at)
- [ ] `feature_enrichment.py`: legge dalla cache prima di chiamare il provider
- [ ] `GET /api/enrichment/features/status` espone hit/miss ratio
- [ ] Test: enrichment su traccia già in cache → zero chiamate rete

### Fase E — AI prompt arricchito

- [ ] `ai_agent.py`: calcola profilo playlist (BPM arc, Camelot distribution, top generi, mood medio, gap identificati) e lo include nel prompt
- [ ] Il prompt comunica esplicitamente i vincoli dell'utente (mood target, energia, durata) come direzione narrativa
- [ ] Test: `FakeLLM` verifica che il prompt contenga il profilo completo

### Fase F — Discovery mode

Nuova funzionalità: suggerisce musica nuova compatibile con il set/playlist. Due entry point che usano gli stessi servizi sotto.

**Gap-driven**: Gap Analysis identifica il buco (BPM range, Camelot target, energia mancante) → Spotify `/recommendations` con audio features target + seed = tracce adiacenti al gap → Last.fm similar artists → candidati rankkati per compatibilità → AI spiega perché ogni traccia risolve il buco specifico.

**Playlist-seed**: parti da una playlist importata → Spotify `/recommendations` con seed = tracce rappresentative della playlist → Last.fm similar artists degli artisti dominanti → candidati rankkati → AI spiega compatibilità con il tuo stile.

- [ ] `integrations/lastfm.py` concreto: `similar_artists(artist)` → lista artisti
- [ ] `services/discovery.py`: orchestratore (gap-driven + playlist-seed), combina fonti, dedup, ranking compatibilità
- [ ] Endpoint `POST /api/discovery/gap` (input: gap object → output: candidati rankkati + spiegazioni AI)
- [ ] Endpoint `POST /api/discovery/expand` (input: playlist_id → output: candidati rankkati + spiegazioni AI)
- [ ] Frontend: pagina Discovery — due tab (Colma un buco / Espandi playlist), card traccia con score compatibilità, spiegazione AI, azione "Aggiungi a playlist"

---

## Backlog

| Item | Note |
|---|---|
| Import manuale playlist | CSV o testo "Artista - Titolo", parsing + enrichment automatico |
| SoundCloud import | Valutare fattibilità API prima di implementare |
| F10 Transition Finder classification | technically safe / creative risk / good reset |
| PostgreSQL | Low priority, SQLite sufficiente per mono-utente |

---

## Rischi e punti di attenzione

| Rischio | Mitigazione |
|---|---|
| Tracce senza BPM/key | Stato `missing_features`; il motore tollera feature assenti (score neutri) |
| Provider BPM/key con copertura variabile | `enrichment_confidence` + stato `low_confidence`; mai sovrascrivere dati esistenti |
| Rate limit Spotify/provider | Batch, cache persistente, job async con polling |
| Spotify `/recommendations` deprecato o ristretto | Fase F da verificare con le API restrictions 2025 prima di implementare |
| Output AI con track_id inventati | Validation Engine obbligatorio + schema Pydantic |
