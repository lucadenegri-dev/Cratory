# SetArc

> Nuovo nome dell'app finora chiamata DJ Assistant. I nomi tecnici legacy come
> `djassistant.db` restano invariati per compatibilita' locale.

SetArc e' una webapp personale, locale/self-hosted e mono-utente per preparare DJ
set a partire da playlist streaming. Importa playlist Spotify o tracklist manuali,
normalizza le tracce, arricchisce BPM/key/mood/energia tramite provider esterni,
analizza i buchi della libreria, genera bozze di set spiegate e aiuta a scoprire
nuova musica compatibile.

Non e' un player e non conserva audio. Il modulo Shazam, quando disponibile, usa
download temporanei solo per fingerprinting di mix esterni e salva esclusivamente la
tracklist identificata.

## Cosa fa

- Importa playlist Spotify, liked tracks e tracklist manuali.
- Deduplica le tracce con priorita' ISRC, id piattaforma, artista/titolo/durata e fuzzy match.
- Arricchisce feature musicali con Deezer, MusicBrainz, AcousticBrainz, GetSongBPM e Last.fm.
- Mantiene fonte e confidenza dei dati; BPM/key esistenti non vengono sovrascritti.
- Permette correzioni manuali di BPM, Camelot, mood, energia, genere e label.
- Genera set con motore deterministico e, se configurata, AI validata.
- Classifica transizioni come sicure, rischiose o buoni reset.
- Espande una playlist con Discovery Last.fm-centric e resolver Spotify.
- Identifica tracklist di mix via Shazam/yt-dlp/ffmpeg in un corpus separato dalla libreria.

## Documentazione

| Documento | Uso |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Principi, pipeline, layer backend, modello dati e integrazioni |
| [docs/API.md](docs/API.md) | Contratti REST correnti del backend FastAPI |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Stato, naming, backlog e prossimi passi |
| [PROGRESS.md](PROGRESS.md) | Diario operativo compatto per riprendere il lavoro |
| [AGENTS.md](AGENTS.md) | Regole per agenti/collaboratori automatici |
| [CLAUDE.md](CLAUDE.md) | Entry point mantenuto per l'AI usata insieme a Codex |

## Stack

```text
Backend:   Python, FastAPI, SQLAlchemy, Pydantic
Frontend:  Next.js 16, React, Tailwind/design system
Database:  SQLite locale, PostgreSQL in backlog
AI:        LLM dietro interfaccia, output validati con Pydantic
External:  Spotify, Deezer, MusicBrainz, AcousticBrainz, GetSongBPM, Last.fm, Shazam
```

## Setup locale

Prerequisiti: Python 3.12+, Node.js 20+. Per il modulo Shazam servono anche `ffmpeg`
di sistema e le dipendenze Python `yt-dlp` e `shazamio` incluse in `backend/requirements.txt`.

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Su Windows PowerShell, l'attivazione dell'ambiente e':

```powershell
.\.venv\Scripts\Activate.ps1
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

URL locali:

- App: http://localhost:3000
- API docs: http://localhost:8000/docs
- Healthcheck: http://localhost:8000/api/health

## Configurazione

Le variabili stanno in `backend/.env`, partendo da `backend/.env.example`.

Minimo per import Spotify:

```text
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/spotify/callback
```

Provider consigliati:

```text
MUSICBRAINZ_USER_AGENT=
GETSONGBPM_API_KEY=
LASTFM_API_KEY=
DEEZER_ENABLED=true
ACOUSTICBRAINZ_ENABLED=true
AI_API_KEY=
AI_MODEL=
AI_MODEL_CREATIVE=
```

Spotify non fornisce BPM/key affidabili per il mixing. Serve per identita' traccia,
metadata editoriali, import playlist e creazione playlist in export.

## Database locale

Il database canonico resta:

```text
backend/data/djassistant.db
```

I path SQLite relativi in `DATABASE_URL` vengono risolti rispetto a `backend/`, cosi'
l'app non crea database diversi in base alla current working directory.

Pulizia dati utente:

```bash
cd backend
python -m app.tools.clean_user_data library --include-backups
```

La modalita' `library` svuota playlist, tracce, set e cache enrichment, preservando i
token Spotify. La modalita' `all` elimina anche i token, salvo `--preserve-tokens`.

## Workflow consigliato

1. Avvia backend e frontend.
2. In Impostazioni configura Spotify e collega l'account.
3. Importa una playlist Spotify o incolla una tracklist manuale.
4. Lascia partire l'enrichment automatico o rilancialo dalla playlist.
5. Correggi manualmente eventuali BPM/key mancanti importanti.
6. Genera un set in modalita' tecnica o creativa.
7. Controlla transizioni, warning e alternative.
8. Esporta il set o crea una playlist Spotify.
9. Usa Discovery per trovare tracce compatibili e aggiungerle alla libreria.

## Test

Backend:

```bash
cd backend
python -m pytest tests
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```
