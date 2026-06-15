# 05 — Specifica funzionale

Funzionalità raggruppate per area. Il flusso principale parte da una **playlist Spotify** (o da un import manuale); il Discovery aiuta a scoprire musica nuova compatibile. Rekordbox è stato rimosso.

---

## Area: Libreria

### F1 — Import Playlist (flusso principale)

L'utente importa una playlist da uno streaming. Supportato:

- playlist Spotify dell'utente autenticato
- playlist collaborative accessibili all'utente
- liked tracks Spotify
- **import manuale**: tracklist incollata come testo, una riga per traccia in formato "Artista - Titolo" (o CSV "artista,titolo") — crea una playlist `kind=manual`, dedup per nome (`services/manual_import.py`)
- playlist SoundCloud → backlog

Per ogni traccia importata salvare almeno: `title`, `artist`, `duration`, `platform`, `platform_track_id`, `playlist_id`, `playlist_name`, `url`, `artwork_url`, `isrc` (se disponibile), `added_at`.

Il modulo deterministico (`services/playlist_import.py`):

1. normalizza gli item della piattaforma nel modello `Track`
2. deduplica con priorità `ISRC → platform_track_id → artist+title+duration → fuzzy`
3. collega le tracce alla `Playlist` importata
4. imposta lo stato iniziale (`imported`)
5. è idempotente (re-import senza duplicati)

Nessuna chiamata AI in import. L'enrichment musicale è un passo separato (F2b).

### F1b — Import Rekordbox XML — RIMOSSO

L'import XML Rekordbox è stato eliminato dal progetto (router, parser, service, fixture e test), insieme a tutte le colonne/tabelle dell'era Rekordbox (`rekordbox_track_id`, `tonality`, `play_count`/`rating`/`comments`/`location`/`date_added`, `BeatgridPoint`/`CuePoint`/`Artist`). Le feature musicali si ottengono ora esclusivamente dall'enrichment esterno (F2b).

### F2 — Spotify Metadata Enrichment — RIMOSSO

Aveva senso quando la sorgente era Rekordbox e i metadata mancavano. Ora che le tracce arrivano dall'import della **playlist Spotify**, titolo/artista/album/cover/ISRC/durata/`year` sono già presenti dall'import: un passo separato di enrichment metadata è ridondante ed è stato rimosso (servizio, endpoint `/api/spotify/enrich*`, card UI). Il genere — unica cosa che il vecchio passo aggiungeva — ora arriva dal Music Feature Enrichment (Last.fm/MusicBrainz, F2b).

### F2b — Music Feature Enrichment (BPM/key/mood/energia)

Per le tracce prive di feature musicali (tipico delle tracce streaming), un livello di enrichment esterno (`services/feature_enrichment.py`) recupera: `bpm`, `key`/`camelot_key`, `genre_primary`/`genre_secondary`, `mood`, `energy`, `danceability`, `vocalness`, `label`, `release_date`, con `confidence` e `source`.

Regole:

- **Non sovrascrive mai BPM/key già presenti** (da un enrichment precedente).
- Matching con priorità `ISRC → platform_track_id → artist+title+duration → fuzzy`.
- Aggiorna lo stato della traccia (`ready_for_set` quando ha BPM **e** key; `low_confidence` se il match è debole).
- Risposte dei provider cachate in DB (`EnrichmentCache`): il secondo enrichment sulla stessa traccia non richiama la rete.
- Provider dietro l'interfaccia `MusicFeatureProvider`, in catena (first-wins per campo): **GetSongBPM** (BPM/key/Camelot/danceability) → **MusicBrainz** (ISRC/label/release/genere) → **Last.fm** (genere + **mood** dai top tag).
- **Energia**: non esiste una fonte gratuita affidabile (Spotify audio-features deprecato, Cyanite/Soundcharts a pagamento). Viene quindi **stimata deterministicamente** (`estimate_energy`) da BPM + danceability + genere — un proxy monotono per l'arco del set, non energia percepita "vera". Così gli score d'arco (`energy_progression_score`, `mood_coherence_score`) non lavorano più su dati vuoti.

### F3 — Library Explorer

Vista tabellare filtrabile della libreria.

Filtri: artista, titolo, album, genere, sorgente/piattaforma, playlist di provenienza, stato traccia, BPM min/max, tonalità, durata, energia, presenza Spotify/SoundCloud ID, metadata incompleti.

Colonne minime: Title, Artist, Platform, Status, BPM, Key (Camelot), Energy, Mood, Duration, Genre, Playlist, Link.

---

## Area: Set building

### F4 — Set Generator (deterministico + AI)

Generazione set tramite **input strutturato** e tramite **prompt libero**, partendo da una playlist (o dall'intera libreria).

Input strutturati: playlist di partenza, durata target, BPM iniziale/finale (o range desiderato), mood iniziale/finale, progressione energia, artisti seed, preferenze genere, tonalità preferite, tipo di progressione, max tracce per artista, filtro sorgente, preferisci mix armonico, preferisci BPM progressivo, permetti cambi bruschi, evita tracce troppo corte, evita tracce troppo suonate, vincoli opzionali.

Output per ogni traccia: posizione, **ruolo** (`intro`, `warmup`, `groove`, `transition`, `peak`, `release`, `closing`), motivazione della posizione, nota di transizione, confidence/rischio, alternative suggerite. Il ruolo è assegnato deterministicamente lungo l'arco del set (`services/set_generator.py::assign_roles`, peak ~70%).

Tipi di progressione: `smooth`, `progressive`, `contrast`, `experimental`, `peak_time`, `warm_up`, `closing`.

**Modalità AI (`mode`, solo quando l'AI è attiva):**
- `technical` (default): mix prudente: l'AI ordina e narra sui soli dati forniti (BPM/Camelot/mood/energia), privilegiando compatibilità e progressione. Adatta a un modello economico.
- `creative`: l'AI usa anche la **propria conoscenza musicale** di brani/artisti (vibe, peso culturale, come funzionano in pista) per costruire un arco emotivo — tensione/rilascio, contrasti voluti, sorprese — potendo rompere di proposito una regola armonica (segnalando il rischio). Restano i vincoli inderogabili: solo candidate fornite, niente track_id inventati, dati tecnici autorevoli, e il Validation Engine valida comunque tutto. Opzionalmente legata a un modello più capace via `AI_MODEL_CREATIVE`.

Esempi di prompt libero da supportare:

> Fammi un set da 45 minuti partendo da Arca e Sega Bodega, poi più club, senza diventare techno dritta troppo presto.
>
> Costruisci un set experimental club da 40 minuti con progressione crescente e qualche cambio brusco.
>
> Voglio un set house/speed garage tra 128 e 134 BPM, fluido ma non noioso.
>
> Fammi una scaletta intorno a questo brano e dammi alternative più morbide e più aggressive.

### F5 — Candidate Engine (MVP 1)

Prima di chiamare l'AI, il sistema seleziona deterministicamente un sottoinsieme di tracce candidate usando: artisti seed, genere, BPM range, key range, durata, source, play count, playlist/contesto (se disponibile), similarità testuale su titolo/artista/album/genere, compatibilità tecnica con i brani già selezionati.

**L'AI non riceve tutta la libreria**: riceve un set di candidate ragionevole e già filtrato.

### F6 — Scoring tecnico transizioni (MVP 1)

Funzione di scoring tra due tracce.

**BPM:**

| Differenza | Giudizio |
|---|---|
| 0–2 BPM | ottimo |
| 2–5 BPM | buono |
| 5–8 BPM | rischioso |
| > 8 BPM | difficile |

**Camelot key:**

| Relazione | Giudizio |
|---|---|
| stessa key | molto compatibile |
| stesso numero, lettera diversa | compatibile |
| numero ±1, stessa lettera | compatibile |
| altro | meno compatibile |

**Durata:** tracce molto corte → penalità. (I bonus cue/beatgrid e play count dell'era Rekordbox sono stati rimossi: lo streaming non fornisce quei dati.)

**Score aggiuntivi sulle feature di enrichment** (0-100, neutro=50 se il dato manca): `energy_progression_score` (premia salita dolce/plateau, penalizza i crolli), `mood_coherence_score`, `genre_similarity_score`. Usati dal motore quando le feature sono disponibili.

Output:

```json
{
  "score": 0-100,
  "technical_reasons": [],
  "warnings": []
}
```

### F7 — AI Set Agent (MVP 3)

Input dell'agente:

```json
{
  "user_request": "...",
  "structured_constraints": {},
  "candidate_profile": { "bpm_range": {}, "key_distribution": {}, "top_genres": [], "avg_energy": null, "missing": {} },
  "candidate_tracks": [],
  "library_context": {}
}
```

`candidate_profile` (Fase E) riassume la palette delle candidate — arco BPM, distribuzione Camelot, generi predominanti, energia media, lacune — così l'AI ha la visione d'insieme senza scorrere tutte le tracce a mano.

Output JSON validabile:

```json
{
  "set_title": "...",
  "global_explanation": "...",
  "tracks": [
    {
      "position": 1,
      "track_id": "...",
      "reason": "...",
      "transition_note": "...",
      "risk_level": "low|medium|high"
    }
  ],
  "critical_points": [],
  "alternative_directions": [],
  "missing_library_suggestions": []
}
```

L'agente deve: costruire una scaletta coerente; spiegare la logica narrativa e ogni scelta; indicare punti critici; distinguere transizioni tecnicamente sicure da transizioni creative/rischiose; proporre alternative; rispettare i vincoli tecnici imposti dal sistema.

### F8 — Validation Engine (MVP 3)

Dopo la generazione AI, validare il set:

- tutte le tracce esistono nel database
- nessun duplicato non voluto
- durata totale vicina al target
- BPM coerenti con la richiesta
- max tracce per artista rispettato
- source filter rispettato
- salti BPM troppo grandi segnalati
- incompatibilità Camelot importanti segnalate
- tracce troppo corte segnalate

Se il set non rispetta i vincoli: (1) correggere automaticamente se possibile, (2) altrimenti richiedere all'agente una nuova versione, (3) altrimenti mostrare warning chiari all'utente.

### F9 — Alternative Generator (MVP 3)

Per ogni traccia del set l'utente può chiedere una sostituzione: più morbida, più aggressiva, più compatibile tecnicamente, stesso artista, genere simile, più sorprendente.

L'app propone 3–5 alternative motivate. Ogni alternativa indica: perché è adatta, differenza BPM, compatibilità key, rischio transizione, effetto narrativo nel set.

Versione MVP 3 implementata: alternative deterministiche basate sulla libreria già importata, escludendo tracce già presenti nel set e valutando compatibilità con brano precedente/successivo. Modalità supportate: `safer`, `softer`, `harder`, `same_artist`, `surprising`. La sostituzione ricalcola posizioni, durata e score transizioni.

### F10 — Transition Finder (MVP 1 tecnico, arricchito in MVP 3)

L'utente seleziona una traccia e chiede: cosa mettere dopo / prima, transizioni più sicure, più interessanti musicalmente, più rischiose ma creative.

I risultati sono classificati: `technically safe`, `musically interesting`, `creative risk`, `good reset`, `good opening continuation`, `good peak transition`.

### F10b — Gap Analysis della playlist

Funzione **deterministica** (`services/gap_analysis.py`) che analizza una playlist (o l'intera libreria) e segnala problemi utili per il DJ set:

- mancano tracce di apertura (poche sotto ~120 BPM)
- mancano tracce ponte tra due range BPM
- pochi brani adatti al peak (sopra ~126 BPM)
- playlist troppo uniforme come energia
- dati armonici insufficienti (poche key/Camelot)
- troppe tracce vocal consecutive
- playlist poco varia o troppo dispersiva per genere

Ogni finding: `{gap_type, severity (info|warning), description, suggestion}`. Output esempio:

> La playlist ha molte tracce tra 122 e 124 BPM, ma poche tra 126 e 128 BPM. Potrebbe servire una sezione ponte per rendere più naturale la crescita del set.

L'AI può, a valle, trasformare questi findings in linguaggio naturale e suggerimenti di crate digging, ma i fatti vengono dal motore deterministico.

### F10e — Discovery mode (Fase F)

Scopre musica nuova compatibile con le playlist dell'utente. Due entry point sugli stessi servizi (`services/discovery.py`):

- **Espandi playlist**: dagli artisti/tracce dominanti della playlist → Last.fm `artist.getsimilar` + `track.getsimilar` + top tracks degli artisti simili.
- **Colma un buco**: parte da un finding della Gap Analysis (F10b); per i gap di genere usa `tag.gettoptracks` sui generi dominanti.

Pipeline deterministica: raccolta candidati → dedup vs libreria (per nome **e** per ISRC dopo il resolve) → resolve su Spotify `/search` (solo i migliori per match, budget limitato) → ranking per compatibilità (le tracce risolvibili in testa). L'AI, opzionale e best-effort, spiega in una frase perché ogni candidato è coerente o colma il gap — **non sceglie i candidati**.

> **Spotify `/recommendations` non è usato** (deprecato dal 27/11/2024: 403/404 in development mode). La similarità arriva da Last.fm; Spotify resta solo resolver.

L'utente può **aggiungere un candidato alla libreria dell'app** (`POST /api/discovery/add`): la traccia entra in libreria (idempotente, dedup per ISRC/spotify_id o per nome) pronta per l'enrichment e per i set. Non viene scritta su Spotify.

### F10c — Set Editor

Sulla scaletta generata l'utente può: vedere la scaletta con ruoli e note di transizione, spostare tracce, bloccare una traccia in posizione, escludere una traccia, chiedere alternative per una posizione (F9), rigenerare una sezione, rinominare/eliminare il set. Ogni modifica ricalcola posizioni, durata e score delle transizioni (`services/set_editor.py`).

### F10d — Export

Export del set in: Markdown, CSV, testo; creazione di una nuova playlist Spotify dal set (`POST /api/spotify/create-playlist`). Lista link SoundCloud → backlog.

---

## Area: Library Expansion (opzionale)

### F11 — Library Expansion Advisor

Modulo per suggerire come ampliare la libreria, su base: artista, label, genere, release, remix, collaborazioni, periodo, artisti simili, artisti sulla stessa label, buchi tecnici nella libreria, necessità emerse durante la creazione set.

**Niente raccomandazioni generiche.** Ogni suggerimento spiega:

1. perché è rilevante rispetto alla libreria attuale
2. quale relazione ha con artista, label, genere o set
3. come potrebbe essere usato in un DJ set
4. se è utile come opening, bridge, peak, reset o closing
5. quali query pratiche cercare su Spotify, Bandcamp o SoundCloud
6. quale priorità ha

### F12 — Expansion from Track

Da una traccia selezionata suggerire: altre release dello stesso artista, remix, collaboratori, label della release, altri artisti della stessa label, generi/stili collegati, tracce utili come prima/dopo nel set, query di ricerca pratiche.

Output esempio:

```json
{
  "source_track": "...",
  "directions": [
    {
      "title": "Explore the label catalog",
      "reason": "...",
      "set_usage": "bridge",
      "priority": "high",
      "search_queries": ["...", "..."],
      "sources": ["Spotify", "Bandcamp"]
    }
  ]
}
```

### F13 — Expansion from Artist

Da un artista suggerire: release essenziali, label associate, collaboratori, remixer, artisti vicini, direzioni più club / più sperimentali / più morbide / più aggressive.

L'output è **raggruppato per direzioni musicali**, non una semplice lista.

### F14 — Expansion from Set

Dopo aver generato un set, analizzarlo e dire: quali blocchi sono forti/deboli, dove mancano alternative, quali BPM/key servirebbero per renderlo più fluido, quali artisti o label esplorare, quali generi ponte potrebbero aiutare.

Esempio di output atteso:

> Il set ha una buona zona 137–141 BPM, ma manca una transizione naturale tra la parte experimental e la parte house. Cerca bridge tracks tra 130 e 134 BPM in key 6A/7A/8A, preferibilmente da label legate a house ruvida o speed garage.

### F15 — Expansion from Genre

Da un genere/stile inserito dall'utente: trovare le tracce già in libreria, identificare artisti e label ricorrenti, calcolare range BPM prevalente e tonalità ricorrenti, suggerire artisti/label da esplorare, suggerire sottogeneri o scene affini, segnalare cosa manca nella libreria.

---

## UI — Sezioni richieste

1. **Dashboard** — numero tracce e playlist, sorgenti, range BPM, distribuzione tonalità, stati traccia (imported/ready_for_set/…), ultime importazioni
2. **Playlists** — selezione e import da Spotify (e liked), import manuale (tracklist incollata), elenco playlist importate, analisi buchi (F10b)
3. **Library** — tabella filtrabile (F3) con stato traccia e feature musicali
4. **Track Detail** — metadata, BPM/key/mood/energia, playlist di provenienza, link streaming, possibili tracce prima/dopo
5. **Set Builder** — playlist di partenza, prompt libero, vincoli strutturati, genera set, scaletta con ruoli, spiegazione globale, motivazione e nota di transizione per traccia, warning, alternative
6. **Discovery** — due tab (Espandi playlist / Colma un buco), card con compatibilità, sorgente, spiegazione AI, link Spotify e azione "Aggiungi alla libreria" (F10e)
7. **Set salvati / Editor** — lista set, dettaglio scaletta, rinomina, elimina, sposta/rimuovi/sostituisci/blocca tracce, rigenera sezione, export (F10c/F10d)
8. **Transition Finder** — tracce prima/dopo una traccia scelta
9. **Settings** — credenziali Spotify, provider enrichment (GetSongBPM API key, MusicBrainz user agent), Last.fm API key (enrichment + Discovery), AI API key, preferenze set builder e sorgenti
