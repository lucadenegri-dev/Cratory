# CLAUDE.md - Guida per l'AI collaboratrice

Guida operativa unica per l'AI che lavora su Cratory.

## Progetto

**Cratory** e' il nuovo nome dell'app precedentemente chiamata DJ Assistant. E' una
webapp personale, locale/self-hosted e mono-utente per importare
playlist streaming, costruire bozze di DJ set su tracce possedute (BPM/key da
Rekordbox), analizzare buchi della libreria, fare discovery e identificare tracklist
di mix. **L'arricchimento dei metadati (titolo/artista/album/label/genere) e il
tagging sono di Sortory.**

Il progetto non riproduce audio. Il modulo Shazam scarica audio solo in modo temporaneo
per fingerprinting e salva un corpus separato di tracklist identificate. Eccezione
esplicita al "non conserva file audio" (il "non riproduce" resta valido): l'acquisizione
persistente via Soulseek/slskd, che collega un file alla `Track` esistente in libreria
(`has_local_file`/`local_path`/`local_format`/`local_bitrate`).

## Fonte di verita'

Leggere in quest'ordine:

1. `README.md` - panoramica, setup e workflow (vetrina, in inglese).
2. `docs/ARCHITECTURE.md` - principi, pipeline, dati e integrazioni.
3. `docs/API.md` - endpoint correnti.
4. `docs/ROADMAP.md` - stato, naming, backlog e prossimi passi (fonte di verita' di stato).
5. `PROGRESS.md` - diario cronologico per riprendere il lavoro.
6. `docs/PRODUCT.md` - prodotto, utenti, job-to-be-done e principi.
7. `docs/DESIGN.md` - design system "editorial archive".

## Regole non negoziabili

1. **Separare motore deterministico e AI.** Import, normalizzazione, deduplica,
   scoring, ruoli, gap analysis, discovery ranking e validazione sono codice
   deterministico. Narrativa, interpretazione prompt e spiegazioni sono AI.
2. **BPM/key vengono da Rekordbox.** Si importano dall'export XML della collezione
   (`/api/rekordbox/import`); di default un dato già presente non si sovrascrive
   (protegge le correzioni manuali), con `?overwrite=true` la ri-analisi Rekordbox
   vince. Cratory non stima né inventa BPM/key. `energy` è un dato derivato
   deterministico (da BPM+genere).
3. **Lo streaming non fornisce feature di mixing.** Spotify da identita' traccia,
   metadata editoriali, cover, durata, ISRC, URL e playlist.
4. **L'AI non riceve mai l'intera libreria.** Riceve solo candidate filtrate dal
   Candidate Engine, con cap 60.
5. **Ogni output AI e' validato.** Usare schemi Pydantic e Validation Engine prima
   di mostrare o salvare risultati.
6. **L'AI non inventa dati fattuali.** Deve distinguere fonte esterna, inferenza
   musicale e ipotesi creativa.
7. **Rekordbox è la fonte di BPM/tonalità.** L'utente analizza in Rekordbox ed
   esporta la collezione in XML; Cratory la importa per riempire BPM/key sulle
   tracce possedute. Beatgrid/cue restano fuori scope.
8. **La libreria è il disco.** Il possesso (`has_local_file`) viene dall'indicizzazione
   di `LIBRARY_ROOT` (riaggancio per `audio_hash`); le playlist streaming sono lead.
   Cratory legge i file ma non li muta mai: i tag li scrive solo Sortory.

## Stack e layout

Backend Python + FastAPI, SQLAlchemy su SQLite, Pydantic. Frontend Next.js 16 con App
Router, React e Tailwind/design system. Integrazioni esterne dietro interfacce in
`backend/app/integrations/`, con cache e gestione errori/rate limit dove serve.

Layer backend:

```text
backend/app/
  routers/       HTTP only: playlists, tracks, transitions, sets, spotify,
                 rekordbox, ai, discovery, services, labels, dj_sets,
                 downloads, files, pipeline
  services/      logica deterministica e orchestrazione
  repositories.py
  models.py
  db.py          sessione/engine, ensure_schema e migrazioni idempotenti
  schemas.py
  serializers.py
  integrations/
  core/
```

Nessuna catena di enrichment: BPM/key da Rekordbox, metadati testuali da Sortory.
I provider esterni rimasti servono **solo la Discovery**: Last.fm (similarita'),
Discogs (dig "Scava"), Spotify (resolver).

Discovery lavora per gusto, non per compatibilita' tecnica (quella resta al Set Builder):
l'espansione playlist e' Last.fm-centric (similarita') con Spotify resolver via `/search`;
il dig "Scava" usa Discogs per genere/etichetta. Spotify `/recommendations` non va usato:
per app nuove o in development mode restituisce 403/404.

## Identita' tracce

- Identita' streaming: `platform`, `platform_track_id`, `isrc`, `url`.
- Deduplica: `ISRC -> platform_track_id -> artist+title+duration -> fuzzy artist+title`.
- Stati traccia: `imported | ready_for_set` (ready = BPM+key presenti).

## Comandi

Backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
python -m pytest tests
```

Windows PowerShell:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
.\.venv\Scripts\python.exe -m pytest tests
```

Frontend:

```bash
cd frontend
npm run dev
npm run lint
npm run build
```

## Frontend

Next.js 16 ha breaking changes rispetto alle versioni note: nel frontend leggere
sempre `frontend/CLAUDE.md` prima di modificare pagine o routing.
