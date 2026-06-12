# 05 — Specifica funzionale

Le 15 funzionalità, raggruppate per area. Ogni titolo indica la fase MVP di riferimento.

---

## Area: Libreria

### F1 — Import Rekordbox XML (MVP 1)

L'utente carica un file XML Rekordbox. Il parser deve:

1. leggere il nodo `COLLECTION`
2. estrarre tutte le tracce
3. riconoscere la sorgente dal campo `Location` (vedi pattern in [03-data-model.md](03-data-model.md))
4. estrarre lo Spotify ID quando presente
5. estrarre il SoundCloud ID quando presente
6. distinguere i file locali
7. salvare BPM, tonalità, durata e play count
8. salvare i punti `TEMPO` come beatgrid points
9. salvare i punti `POSITION_MARK` come cue points
10. generare un report di import

Il report deve mostrare: totale tracce importate; numero tracce Spotify / SoundCloud / locali; tracce con BPM; tracce con tonalità; tracce con cue point; tracce con titolo/artista mancanti; range BPM; distribuzione tonalità; eventuali errori di parsing.

Il re-import deve aggiornare la libreria esistente senza creare duplicati (chiave: `rekordbox_track_id`).

### F2 — Spotify Metadata Enrichment (MVP 2)

Per ogni traccia con Spotify ID, recuperare via Spotify API: title, artist, album, cover image, release year (se disponibile), Spotify URL, artist ID, artist genres, artist popularity.

Regole:

- **Non sovrascrivere mai BPM e tonalità di Rekordbox.**
- Se `Name` o `Artist` sono vuoti nell'XML (caso frequente per tracce Spotify), completarli con Spotify.
- Conservare il collegamento traccia Rekordbox ↔ Spotify ID.
- Gestire rate limit ed errori API.
- Cache dei risultati per evitare chiamate ripetute.

### F3 — Library Explorer (MVP 1)

Vista tabellare filtrabile della libreria.

Filtri: artista, titolo, album, genere, sorgente, BPM min/max, tonalità, durata, play count, presenza Spotify ID, presenza SoundCloud ID, presenza cue point, metadata incompleti.

Colonne minime: Title, Artist, Source, BPM, Key, Duration, Genre, Year, Play Count, Spotify Link, Cue Count.

---

## Area: Set building

### F4 — Set Generator (MVP 1 algoritmico, MVP 3 con AI)

Generazione set tramite **input strutturato** e tramite **prompt libero**.

Input strutturati: durata target, BPM iniziale/finale, artisti seed, genere o stile, tonalità preferite, tipo di progressione, max tracce per artista, filtro sorgente (Spotify/SoundCloud/locali/tutti), preferisci mix armonico, preferisci BPM progressivo, permetti cambi bruschi, evita tracce troppo corte, evita tracce troppo suonate.

Tipi di progressione: `smooth`, `progressive`, `contrast`, `experimental`, `peak_time`, `warm_up`, `closing`.

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

**Durata e cue:** tracce molto corte → penalità; cue point presenti → bonus; beatgrid disponibile → bonus.

**Play count:** mai usate → possibile bonus varietà; usate troppo spesso → leggera penalità se richiesto.

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
  "candidate_tracks": [],
  "technical_scores": [],
  "library_context": {}
}
```

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

### F10 — Transition Finder (MVP 1 tecnico, arricchito in MVP 3)

L'utente seleziona una traccia e chiede: cosa mettere dopo / prima, transizioni più sicure, più interessanti musicalmente, più rischiose ma creative.

I risultati sono classificati: `technically safe`, `musically interesting`, `creative risk`, `good reset`, `good opening continuation`, `good peak transition`.

---

## Area: Library Expansion (MVP 4)

### F11 — Library Expansion Advisor

Modulo per suggerire come ampliare la libreria, su base: artista, label, genere, release, remix, collaborazioni, periodo, artisti simili, artisti sulla stessa label, buchi tecnici nella libreria, necessità emerse durante la creazione set.

**Niente raccomandazioni generiche.** Ogni suggerimento spiega:

1. perché è rilevante rispetto alla libreria attuale
2. quale relazione ha con artista, label, genere o set
3. come potrebbe essere usato in un DJ set
4. se è utile come opening, bridge, peak, reset o closing
5. quali query pratiche cercare su Spotify, Discogs, Bandcamp o SoundCloud
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
      "sources": ["Discogs", "Spotify"]
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

1. **Dashboard** — numero tracce, sorgenti, range BPM, distribuzione tonalità, tracce con metadata mancanti, ultime importazioni
2. **Library** — tabella filtrabile (F3)
3. **Track Detail** — metadata, BPM/key, cue point, sorgente, link Spotify, possibili tracce prima/dopo, pulsante "Expand from this track"
4. **Set Builder** — prompt libero, vincoli strutturati, genera set, scaletta risultante, spiegazione globale, motivazione per traccia, warning tecnici, alternative per traccia
5. **Transition Finder** — tracce prima/dopo una traccia scelta
6. **Expand Library** — espandi da traccia/artista/genere/set, suggerimenti salvati
7. **Settings** — credenziali Spotify API, token Discogs, user agent MusicBrainz, AI API key, preferenze set builder e sorgenti
