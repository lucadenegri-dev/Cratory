# AGENTS.md - Guida allo sviluppo

## Progetto

**SetArc** e' il nuovo nome dell'app precedentemente chiamata DJ Assistant. E' una
webapp personale, locale/self-hosted e mono-utente per importare
playlist streaming, arricchire le tracce con feature musicali, costruire bozze di DJ
set, analizzare buchi della libreria, fare discovery e identificare tracklist di mix.

Il progetto non riproduce audio e non conserva file audio. Il modulo Shazam scarica
audio solo in modo temporaneo per fingerprinting e salva un corpus separato di
tracklist identificate.

## Fonte di verita' documentativa

Leggere in quest'ordine:

1. `README.md` - setup, workflow e panoramica.
2. `docs/ARCHITECTURE.md` - principi, pipeline, dati e integrazioni.
3. `docs/API.md` - endpoint correnti.
4. `docs/ROADMAP.md` - stato, naming, backlog e prossimi passi.
5. `PROGRESS.md` - diario operativo per riprendere il lavoro.

`CLAUDE.md` e' mantenuto come entrypoint per l'AI usata insieme a Codex. Le vecchie
spec numerate sono state rimosse per evitare documentazione duplicata.

## Regole non negoziabili

1. **Separare motore deterministico e AI.** Import, normalizzazione, deduplica,
   enrichment, scoring, ruoli, gap analysis, discovery ranking e validazione sono
   codice deterministico. Narrativa, interpretazione prompt e spiegazioni sono AI.
2. **BPM/key/feature musicali non si inventano.** Arrivano da provider esterni o da
   correzione manuale esplicita, con `enrichment_source` e `enrichment_confidence`.
3. **Non sovrascrivere BPM/key esistenti.** Un dato gia' presente resta autorevole,
   soprattutto se `enrichment_source="manual"`.
4. **Lo streaming non fornisce feature di mixing.** Spotify da identita' traccia,
   metadata editoriali, cover, durata, ISRC, URL e playlist.
5. **L'AI non riceve mai l'intera libreria.** Riceve solo candidate filtrate dal
   Candidate Engine, con cap 60.
6. **Ogni output AI e' validato.** Usare schemi Pydantic e Validation Engine prima
   di mostrare o salvare risultati.
7. **L'AI non inventa dati fattuali.** Deve distinguere fonte esterna, inferenza
   musicale e ipotesi creativa.
8. **Rekordbox resta fuori progetto.** Import XML, beatgrid/cue e colonne legacy sono
   state rimosse.

## Stack e layout

Backend Python + FastAPI, SQLAlchemy su SQLite, Pydantic. Frontend Next.js 16 con App
Router, React e Tailwind/design system. Integrazioni esterne dietro interfacce in
`backend/app/integrations/`, con cache e gestione errori/rate limit dove serve.

Layer backend:

```text
backend/app/
  routers/       HTTP only: playlists, tracks, transitions, sets, spotify,
                 enrichment, ai, discovery, services, dj_sets
  services/      logica deterministica e orchestrazione
  repositories.py
  models.py
  schemas.py
  serializers.py
  integrations/
  core/
```

Provider feature in catena:

```text
Deezer -> MusicBrainz -> AcousticBrainz -> GetSongBPM -> Last.fm
```

Discovery e' Last.fm-centric. Spotify `/recommendations` non va usato: per app nuove
o in development mode restituisce 403/404; Spotify resta resolver via `/search`.

## Identita' tracce

- Identita' streaming: `platform`, `platform_track_id`, `isrc`, `url`.
- Deduplica/enrichment: `ISRC -> platform_track_id -> artist+title+duration -> fuzzy artist+title`.
- Stati traccia: `imported | enriched | ready_for_set | missing_features | low_confidence`.

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

Next.js 16 ha breaking changes rispetto alle versioni note: nel frontend leggere
sempre `frontend/AGENTS.md` prima di modificare pagine o routing.
