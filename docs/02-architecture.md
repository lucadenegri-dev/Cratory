# 02 — Architettura

## Stack tecnico

```text
Backend:           Python + FastAPI
Frontend:          React o Next.js
Database MVP:      SQLite
Database futuro:   PostgreSQL
ORM:               SQLAlchemy
Validation:        Pydantic
XML parser:        lxml
Spotify:           Spotify Web API con OAuth
AI:                LLM API astratta tramite service layer
Metadata esterni:  Discogs API, MusicBrainz API
```

Webapp modulare, locale/self-hosted, mono-utente.

## Pipeline dei moduli

```text
Rekordbox XML Importer
        ↓
Database interno (SQLite)
        ↓
Spotify Metadata Enricher
        ↓
Music Metadata Layer (Discogs/MusicBrainz, opzionali)
        ↓
Candidate Engine (deterministico)
        ↓
AI Set Agent
        ↓
Validation Engine
        ↓
Set Builder UI / Library Expansion UI
```

## Principio architetturale fondamentale

Il sistema separa nettamente due responsabilità:

### Motore deterministico

Responsabile di tutto ciò che è verificabile e calcolabile:

- parsing XML
- calcolo durata set
- compatibilità BPM
- compatibilità Camelot
- deduplicazione tracce
- validazione dei risultati AI
- filtri tecnici
- scoring base delle transizioni
- selezione delle tracce candidate (Candidate Engine)

### Agente AI

Responsabile di tutto ciò che richiede giudizio musicale e linguaggio:

- interpretare richieste in linguaggio naturale
- ragionare su artista, genere, estetica e direzione musicale
- creare una narrativa del set
- spiegare le scelte
- proporre alternative creative
- suggerire percorsi di espansione della libreria
- trasformare lacune tecniche in indicazioni di crate digging

**L'AI non inventa dati fattuali.** Quando suggerisce artisti, etichette o release deve distinguere tra: dati recuperati da fonti esterne, inferenze musicali, ipotesi creative.

**L'AI non riceve mai tutta la libreria** se non necessario: il Candidate Engine le passa un sottoinsieme già filtrato. Ogni output AI passa dal Validation Engine prima di essere mostrato come definitivo.

## Struttura del codice (linee guida)

Separazione a layer nel backend:

```text
backend/
  app/
    routers/       # endpoint FastAPI (solo HTTP, niente logica)
    services/      # logica di business (parser, scoring, candidate engine, agent, validation)
    repositories/  # accesso dati (query SQLAlchemy)
    models/        # modelli SQLAlchemy
    schemas/       # schemi Pydantic (request/response, output AI)
    integrations/  # client Spotify, Discogs, MusicBrainz, LLM (dietro interfacce)
    core/          # config, logging, errori
  tests/
frontend/
```

Requisiti di qualità:

- codice modulare con type hints
- servizi, repository, modelli e router separati
- gestione errori chiara + logging
- configurazione tramite variabili ambiente (`.env.example` nel repo)
- README con istruzioni di setup
- seed/demo con il file XML di esempio (`export_rekordbox.xml`)
- test di base almeno per parser XML e scoring transizioni

## Service layer per integrazioni esterne

Le integrazioni (Spotify, Discogs, MusicBrainz, LLM) stanno dietro interfacce astratte fin da MVP 1, anche se implementate solo nelle fasi successive. Questo permette di:

- sviluppare e testare il core senza credenziali esterne
- cambiare provider LLM senza toccare il resto del sistema
- cachare le risposte (obbligatorio per Spotify, per evitare chiamate ripetute)
- gestire rate limit ed errori API in un punto solo

## Fonti esterne: ruoli

| Fonte | Ruolo |
|---|---|
| **Rekordbox XML** | Fonte primaria dati DJ: BPM, tonalità, durata, beatgrid, cue, play count |
| **Spotify** | Metadata traccia/artista, generi artista, album, cover, link, creazione playlist |
| **Discogs** | Release, label, artisti collegati, generi/stili, anni, remix, cataloghi etichette |
| **MusicBrainz** | Fallback aperto: artisti, release, label, relazioni tra entità |
