# CLAUDE.md - Guida per AI collaborator

Questo file e' intenzionalmente mantenuto: serve come entrypoint per l'AI usata
insieme a Codex. Non eliminarlo durante cleanup documentali.

## Progetto

**Cratory** e' il nuovo nome dell'app precedentemente chiamata DJ Assistant. E' una
webapp personale, locale/self-hosted e mono-utente per importare
playlist streaming, arricchire le tracce con feature musicali, costruire bozze di DJ
set, analizzare buchi della libreria, fare discovery e identificare tracklist di mix.

Il progetto non riproduce audio e non conserva file audio. Il modulo Shazam scarica
audio solo in modo temporaneo per fingerprinting e salva un corpus separato di
tracklist identificate.

## Fonte di verita'

Leggere in quest'ordine:

1. `README.md` - setup, workflow e panoramica.
2. `docs/ARCHITECTURE.md` - principi, pipeline, dati e integrazioni.
3. `docs/API.md` - endpoint correnti.
4. `docs/ROADMAP.md` - stato, naming, backlog e prossimi passi.
5. `PROGRESS.md` - diario operativo per riprendere il lavoro.
6. `AGENTS.md` - regole operative equivalenti per Codex/altri agenti.

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
