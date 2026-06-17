# 06 — Roadmap

## Fasi completate

- **MVP 1 — Core deterministico** ✅ scoring transizioni, set generator algoritmico, API.
- **MVP 2 — Spotify** ✅ OAuth, enrichment metadata editoriali con cache, async + rate limit.
- **MVP 3 — AI** ✅ AI Set Agent (structured output), prompt libero, spiegazioni narrative, Validation Engine, alternative F9, generazione asincrona, gestione set salvati + editor.
- **Pivot Fase A** ✅ data model streaming-first, import playlist Spotify, gap analysis, ruoli set.
- **Pivot Fase B** ✅ GetSongBPMProvider, MusicBrainzProvider, ChainedFeatureProvider, router enrichment async.
- **Pivot Fase C** ✅ set da playlist (candidate scoped), scoring feature energia/mood/genere, export Markdown.
- **Fase D1 — Rimozione Rekordbox** ✅ import Rekordbox eliminato, test su dati sintetici Spotify, `lxml` rimosso.
- **Fase D2 — Cache enrichment** ✅ tabella `enrichment_cache`, bulk pre-load + upsert, caches anche i not-found, `force` bypassa la lettura.
- **Fase E — AI prompt arricchito** ✅ `ai_agent._compute_candidate_profile` (BPM arc, Camelot, generi, energia, lacune) nel payload come `candidate_profile`; system prompt aggiornato.
- **Fase F — Discovery mode** ✅ (read pipeline) Last.fm-centric, vedi sotto.
- **Copertura enrichment** ✅ (17/06/2026) **Deezer** (BPM via ISRC, senza chiave) + **AcousticBrainz** (BPM/key/mood/danceability/vocalness via MBID, senza chiave) aggiunti alla catena; MBID di MusicBrainz catturato e propagato via `context`. Nuovo ordine identità-first: Deezer → MusicBrainz → AcousticBrainz → GetSongBPM → Last.fm. Risolve il "nessun dato" tipico del solo match fuzzy.

---

## Fase F — Discovery mode (dettaglio)

Suggerisce musica nuova compatibile con il set/playlist. Due entry point sugli stessi servizi.

> **Pivot:** Spotify `/recommendations` (+ related-artists, audio-features) è **deprecato dal 27/11/2024** e restituisce 403/404 alle app nuove o in development mode. Discovery è quindi **Last.fm-centric**; Spotify resta solo resolver (`/search`, funzionante in dev mode). Recommendations resta agganciabile come fonte opzionale se in futuro si ottiene extended quota.

**Espandi playlist**: artisti/tracce dominanti della playlist → Last.fm `artist.getsimilar` + `track.getsimilar` → top track degli artisti simili → dedup vs libreria → resolve su Spotify → ranking per compatibilità (match Last.fm) → AI spiega l'affinità.

**Colma un buco (gap-driven)**: parte da un gap di `gap_analysis`; per i gap di genere usa `tag.gettoptracks` sui generi dominanti; stessa pipeline di dedup/resolve/ranking → AI spiega come ogni traccia colma quel gap.

- [x] `integrations/lastfm.py`: `LastFMClient` (similar_artists/tracks, artist_top_tracks, top_tracks_by_tag), httpx iniettabile
- [x] `services/discovery.py`: orchestratore (expand + gap), dedup per (artista,titolo) e ISRC, ranking, spiegazioni AI best-effort
- [x] `SpotifyWebClient.search_track` come resolver dev-mode-safe
- [x] Endpoint `POST /api/discovery/expand`, `POST /api/discovery/gap`, `GET /api/discovery/status`
- [x] Frontend: pagina Discovery — due tab (Espandi playlist / Colma un buco), card con compatibilità, sorgente, spiegazione AI, link Spotify
- [x] Write-back: `POST /api/discovery/add` → importa il candidato nella **libreria dell'app** (`import_single_track`, idempotente), bottone "Aggiungi" sulla card
- [x] Test `test_discovery.py` (9) senza rete
- [ ] **Da fare:** test reale con chiave Last.fm

## Import manuale playlist ✅ (14/06/2026)

Incolla una tracklist → playlist `kind=manual` nella libreria, pronta per l'enrichment.

- [x] `services/manual_import.py`: `parse_line` (Artista - Titolo / en-em dash / TSV / CSV / solo titolo) + `import_manual_playlist` (dedup per nome vs libreria, idempotente)
- [x] Endpoint `POST /api/playlists/import-manual`
- [x] Frontend: card "Import manuale" nella pagina Playlist
- [x] Test `test_manual_import.py` (4)

---

## Backlog

| Item | Note |
|---|---|
| ~~Import manuale playlist~~ | ✅ fatto 14/06/2026 (`services/manual_import.py`) |
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
| Spotify `/recommendations` deprecato (confermato 27/11/2024: 403/404 in dev mode) | Discovery non lo usa: similarità via Last.fm, Spotify solo come resolver `/search` |
| Output AI con track_id inventati | Validation Engine obbligatorio + schema Pydantic |
