# DjOrganizer

Tool personale, locale e standalone per organizzare le cartelle di musica sul disco e
prepararle all'import in **Rekordbox**: pulizia tag/metadata, rinomina file e struttura
cartelle, deduplica e quality check.

Non riproduce audio, non conserva audio e **non analizza BPM/key** (quello lo fa
Rekordbox).

App separata da **Cratory**, con cui condivide il design system. Le due app non
comunicano più via rete: l'unica interfaccia tra loro è il disco (i tag dei file in
`Libreria/`). DjOrganizer funziona sempre al 100% da solo.

## Stato

Operativo: pipeline completa scan → issues → dedup → piano → applica → undo,
testata end-to-end (191 test). Owner unico dei metadati testuali (Titolo/Artista/
Album/Label/Genere): li pulisce, li arricchisce da provider esterni e ne certifica
l'identità via fingerprint acustico.

## Posto nella catena

`inbox/` → **DjOrganizer** → `Libreria/{genere}/{artist}/Artist - Title.ext` → Rekordbox.
Unico scrittore dei tag dell'ecosistema. Vedi `~/Develop/dj-ecosystem-north-star.md`.

## Owner dei metadati testuali

DjOrganizer è l'unico punto dell'ecosistema che scrive Titolo, Artista, Album, Label
e Genere nei tag dei file. Catena di precedenza, dalla più alla meno autorevole:

```
manuale > tag pulito del file > provider (MusicBrainz/Discogs) > AI dal nome file
```

Implementazione: ogni suggerimento salvato in `Issue.suggested_fix_json` porta un
marker `source` (`"provider"` o `"ai"`). Un fix manuale chiude subito l'issue
(`status="accepted"`), quindi è fuori dalla competizione. Tra i suggerimenti aperti:
il provider sovrascrive sia l'AI sia i suggerimenti senza marker; l'AI non
sovrascrive mai un suggerimento già marcato `"provider"`. Nessuna sovrascrittura
silenziosa: i conflitti restano issue aperte finché non li accetti tu.

`POST /api/issues/provider-suggest` riempie le issue aperte interrogando in catena
**MusicBrainz → Discogs** (una lookup per file, con cache in-memory). Non accetta
mai automaticamente un fix: propone soltanto, la scelta finale resta manuale (o via
"Risolvi con AI" per i campi ancora vuoti).

## Fingerprint acustico (AcoustID)

`POST /api/fingerprint` calcola l'impronta acustica dei file (via `fpcalc`/Chromaprint)
e la confronta contro il database AcoustID per risolvere un `AudioFile.mbid` certo,
utile quando tag e nome file sono entrambi inaffidabili. `GET /api/fingerprint/status`
riporta se la feature è configurata (chiave AcoustID presente + binario `fpcalc`
trovato). Senza una delle due cose l'endpoint degrada in modo pulito
(`configured: false`) e il resto della pipeline continua a funzionare.

## Configurazione (`.env`)

Copia `backend/.env.example` in `backend/.env` e compila. Impostazioni disponibili:

- `DJORG_DATABASE_URL` — DB SQLite locale.
- `ANTHROPIC_API_KEY` — chiave Anthropic per "Risolvi con AI" (Claude Haiku). Non ha
  prefisso `DJORG_`. Senza, il bottone AI resta disabilitato.
- `DJORG_MUSICBRAINZ_USER_AGENT` — nessuna chiave richiesta, ma serve uno User-Agent
  identificabile: mettici un contatto reale (email o URL) al posto del placeholder.
- `DJORG_DISCOGS_TOKEN` — opzionale: funziona anche senza (~25 richieste/min), con
  token gratuito sale a ~60/min. Si genera su discogs.com/settings/developers.
- `DJORG_ACOUSTID_API_KEY` — chiave gratuita da acoustid.org/new-application. Serve
  anche il binario `fpcalc`: `brew install chromaprint`.

## Principio di sicurezza

Ogni operazione sui file e' prima un **piano** che approvi. Le modifiche sono in-place
ma reversibili: i delete vanno in **quarantena** (mai hard-delete) e ogni run scrive un
**undo journal** per annullare tutto.
