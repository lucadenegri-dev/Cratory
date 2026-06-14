# 02 — Architettura

## Stack tecnico

```text
Backend:           Python + FastAPI
Frontend:          Next.js 16 / React
Database MVP:      SQLite
Database futuro:   PostgreSQL
ORM:               SQLAlchemy
Validation:        Pydantic
Streaming:         Spotify Web API (OAuth); SoundCloud in backlog
Enrichment:        GetSongBPM (BPM/key), MusicBrainz (label/release/ISRC), Last.fm (tag)
Discovery:         Last.fm (similarità) + Spotify /search (resolver)
AI:                LLM API (Anthropic) astratta tramite service layer
Opzionale futuro:  Discogs
```

Webapp modulare, locale/self-hosted, mono-utente.

> **Rekordbox rimosso.** L'import XML Rekordbox non fa più parte del progetto. Le colonne e le tabelle dell'era Rekordbox (`rekordbox_track_id`, `tonality`, `play_count`/`rating`/`comments`/`location`/`date_added`, `BeatgridPoint`/`CuePoint`/`Artist`) sono state eliminate dal modello e dal DB (vedi [03-data-model.md](03-data-model.md)).
>
> **Spotify `/recommendations` non è utilizzabile** (deprecato dal 27/11/2024: 403/404 per app nuove o in development mode). Il Discovery usa Last.fm per la similarità e Spotify solo come resolver (`/search`).

## Pipeline dei moduli (nuovo flusso)

```text
Playlist Spotify  /  Import manuale (testo "Artista - Titolo")
        ↓
Playlist Importer  (normalizzazione + deduplica)
        ↓
Database interno (SQLite)   (metadata editoriali già presenti dall'import)
        ↓
Music Feature Enricher (GetSongBPM → MusicBrainz → Last.fm, con cache DB)
        ↓
Candidate Engine (deterministico, cap 60) ──┐
        ↓                                     │
Set Builder deterministico (scoring + ruoli) ──► AI Set Agent (profilo candidate + narrativa)
        ↓                                     │
Validation Engine                             │
        ↓                                     ▼
Set Editor UI / Gap Analysis / Export    Discovery (Last.fm → resolve Spotify → ranking → AI spiega)
```

Il Discovery riusa la Gap Analysis (entry point "colma un buco") e le playlist importate (entry point "espandi"): scopre tracce affini via Last.fm, le risolve su Spotify e le importa nella libreria su richiesta dell'utente.

## Principio architetturale fondamentale

Il sistema separa nettamente due responsabilità.

### Motore deterministico

Tutto ciò che è verificabile e calcolabile:

- import e normalizzazione playlist, deduplica (ISRC → platform_track_id → artist+title+duration → fuzzy)
- enrichment (applicazione dei dati dei provider con confidenza e fonte)
- compatibilità BPM e Camelot, progressione energia, coerenza mood, similarità genere
- scoring delle transizioni e assegnazione dei ruoli
- selezione candidate (Candidate Engine) e calcolo del profilo candidate (BPM arc, distribuzione Camelot, generi, energia, lacune) passato all'AI
- analisi dei buchi della playlist (Gap Analysis)
- Discovery: raccolta candidati da Last.fm, deduplica vs libreria (per nome e ISRC), resolve su Spotify, ranking per compatibilità
- validazione dei risultati AI

### Agente AI

Tutto ciò che richiede giudizio musicale e linguaggio:

- interpretare richieste in linguaggio naturale
- scegliere una direzione narrativa del set
- spiegare le scelte e annotare le transizioni
- proporre alternative creative
- trasformare i buchi tecnici in indicazioni di crate digging (artisti/label/generi)
- spiegare perché ogni traccia suggerita dal Discovery è coerente o colma un gap (l'AI **non** sceglie i candidati: solo li commenta)

**L'AI non inventa dati fattuali** e **non riceve mai tutta la libreria**: il Candidate Engine le passa un sottoinsieme già filtrato con i relativi score. Ogni output AI passa dal Validation Engine prima di essere mostrato come definitivo.

## Scoring deterministico

Prima dell'AI, il motore calcola (0-100, vedi [`services/scoring.py`](../backend/app/services/scoring.py)):

```text
bpm_compatibility_score
key_compatibility_score
energy_progression_score
mood_coherence_score
genre_similarity_score
transition_score   (composito BPM 50 + Camelot 40 + durata 10)
```

In assenza del dato i singoli score restituiscono un valore neutro, così la generazione resta possibile anche su tracce parzialmente arricchite.

## Struttura del codice (backend a layer)

```text
backend/app/
  routers/       # endpoint FastAPI (solo HTTP): playlists, tracks, transitions,
                 #   sets, spotify, enrichment, ai, discovery, services
  services/      # logica: playlist_import, manual_import, enrichment, feature_enrichment,
                 #   scoring, candidate_engine, set_generator, ai_agent, validation,
                 #   set_editor, alternatives, gap_analysis, discovery, track_status, camelot
  repositories.py# accesso dati (query SQLAlchemy)
  models.py      # modelli SQLAlchemy (incl. EnrichmentCache per la cache provider)
  schemas.py     # schemi Pydantic (request/response, output AI)
  serializers.py # ORM -> Pydantic con campi derivati
  integrations/  # client dietro ABC: spotify, llm, getsongbpm, musicbrainz, lastfm
  core/          # config, logging
```

Requisiti di qualità: type hints ovunque, errori chiari + logging, config via `.env` (`.env.example` aggiornato), README di setup, test di base per i moduli deterministici.

## Service layer per integrazioni esterne

Le integrazioni stanno dietro interfacce astratte (`integrations/__init__.py`): `SpotifyClient`, `MusicFeatureProvider`, `SimilarityClient` (Discovery), `LLMClient`, più gli ABC ancora non implementati (`SoundCloudClient`, `DiscogsClient`, `MusicBrainzClient`). Questo permette di: testare il core senza credenziali (fake injection ovunque), cambiare provider senza toccare il resto, cachare le risposte (`EnrichmentCache`), gestire rate limit/errori in un punto solo. Le risposte dei provider feature sono cachate in DB: un secondo enrichment sulla stessa traccia non richiama la rete.

## Fonti esterne: ruoli

| Fonte | Ruolo | Stato |
|---|---|---|
| **Spotify** | Identità traccia (ISRC, id, url), metadata editoriali, cover, durata, import playlist/liked, **resolver Discovery** (`/search`), creazione playlist | attivo |
| **GetSongBPM** | BPM e tonalità/Camelot | attivo |
| **MusicBrainz** | Identificazione, ISRC, release, label (fallback aperto) | attivo |
| **Last.fm** | Tag/generi (enrichment) **e similarità per il Discovery** (artist/track getsimilar, tag toptracks) | attivo |
| **Anthropic LLM** | AI Set Agent + spiegazioni Discovery | attivo |
| **SoundCloud** | Import playlist/liked | backlog |
| **Discogs** | Release, label, cataloghi (espansione libreria) | opzionale futuro |
| ~~Spotify `/recommendations`~~ | ~~raccomandazioni~~ | non disponibile (deprecato 2024) |
| ~~Rekordbox XML~~ | ~~BPM/key/beatgrid/cue~~ | rimosso |
