# Sortory

Tool personale, locale e standalone per **organizzare** le cartelle di musica sul disco
e prepararle all'import in **Rekordbox**: pulizia tag/metadata, arricchimento da
provider esterni, rinomina file e struttura cartelle, deduplica e quality check.

Non riproduce audio, non conserva audio e **non analizza BPM/key** (quello lo fa
Rekordbox).

App separata da **Cratory**, con cui condivide il design system (monospace, editoriale,
squadrato). Le due app non comunicano via rete: l'unica interfaccia tra loro è il disco
(i tag dei file in `Libreria/`). Sortory funziona sempre al 100% da solo.

## Stato

Operativo end-to-end, oltre 290 test backend verdi. Pipeline completa:
`Sources → scan → Issues → Duplicates → Plan → Apply → History (undo)` + `Settings`.
Owner unico dei metadati testuali (Titolo/Artista/Album/Label/Genere/Anno): li pulisce,
li arricchisce da provider esterni e ne certifica l'identità via fingerprint acustico.

Interfaccia: pipeline a pagine con una **Guida** contestuale nel riepilogo di ognuna;
i job lunghi (scan, apply, ricerca provider) mostrano una **barra di progresso** fissa
in basso.

## Lingua (IT/EN)

App bilingue italiano/inglese, con toggle in **Settings** (default **inglese**). La
lingua è persistita lato backend (`Settings.language`, `GET/PUT /api/settings/language`)
e mirrorata in `localStorage` per evitare il flash al primo render. Il dizionario è un
modulo TypeScript fatto in casa (`frontend/lib/i18n/`, EN fonte di verità, IT tipizzato
contro EN: chiave mancante = errore di compilazione). Gli errori del backend viaggiano
come **codici stabili** (`{code, message, params}` via `app/core/http_errors.api_error`)
e vengono tradotti nel frontend, così il backend resta language-agnostic.

## Posto nella catena

`Downloads/` → **Sortory** → `Libreria/{genere}/{artist}/Artist - Title.ext` → Rekordbox.
Unico scrittore dei tag dell'ecosistema.

## Owner dei metadati testuali

Sortory è l'unico punto dell'ecosistema che scrive Titolo, Artista, Album, Label, Genere
e Anno nei tag dei file. Catena di precedenza, dalla più alla meno autorevole:

```
manuale > tag pulito del file > provider (fingerprint > testuale) > AI dal nome file
```

Ogni suggerimento salvato in `Issue.suggested_fix_json` porta un marker `source`
(`"provider"` | `"ai"`) e, per il provider, una `confidence` (`"high"` = match certo via
MBID/ISRC, `"text"` = match testuale, da rivedere). Un fix manuale chiude subito l'issue
(`accepted`), fuori dalla competizione. Tra i suggerimenti aperti il provider sovrascrive
AI e legacy; l'AI non tocca mai un suggerimento già `provider`. Nessuna sovrascrittura
silenziosa: i conflitti restano issue aperte finché non li accetti tu.

### Azioni nella pagina Issues

- **Recupera Artista/Titolo con AI** (`/api/issues/ai-suggest`) — Claude Haiku ricava
  artista/titolo dal nome file. Manuale.
- **Recupera Genere con AI** (`/api/issues/ai-suggest-genre`) — Haiku propone il genere
  principale da artista+titolo. Bassa confidenza, da rivedere.
- **Importa metadati mancanti da Provider** (`/api/issues/provider-suggest`) —
  **fingerprint-first**: se il file non ha `mbid` e AcoustID è configurato, lo
  fingerprinta prima della lookup MusicBrainz→Discogs → match esatto e confidenza `high`;
  altrimenti match testuale. Riempie solo le issue aperte, non accetta mai da solo.
- **Importa tutti i metadati da Provider** (`/api/issues/provider-rescan`) — ricerca
  provider **per traccia** (non per-issue): reinterroga i provider su tracce **già
  taggate** per riclassificare la libreria, creando issue sintetiche `provider_override`
  (con confidenza) solo dove il valore differisce da quello sul file. Gira come **job in
  background** con progress; filtrabile per cartella/genere e per campo
  (`genre/album/label/year`); un pop-up chiede se riconsiderare anche le proposte già
  accettate/ignorate.
- **Accetta tutti alta confidenza** (`/api/issues/provider-override/accept-high`) — accetta
  in blocco le override `high`. Più *accetta fixabili* / *ignora info* per le azioni di massa.

## Fingerprint acustico (AcoustID)

`POST /api/fingerprint` calcola l'impronta acustica dei file (via `fpcalc`/Chromaprint) e
la confronta col database AcoustID per risolvere un `AudioFile.mbid` certo. È usato anche
automaticamente da *Importa metadati mancanti/tutti da Provider* (fingerprint-first).
`GET /api/fingerprint/status` riporta se la feature è configurata (chiave AcoustID +
binario `fpcalc`). Senza, tutto degrada in modo pulito (solo match testuale) e la pipeline
continua a funzionare.

## Provider e stato

`GET /api/providers` elenca i provider (MusicBrainz, Discogs, AcoustID/Chromaprint,
Anthropic) con categoria, env-var, docs e stato (`configured`/`connected`/`missing`),
mostrati nella pagina **Settings** in stile uniforme a Cratory.

## Pagina Files

`/api/files` filtra per tag (`genre/artist/album/label/ext/year`) e cerca per
path/artista/titolo; `GET /api/library/facets` fornisce i valori distinti per i filtri.

## Configurazione (`.env`)

Copia `backend/.env.example` in `backend/.env` e compila (le env-var mantengono il prefisso
storico `DJORG_`):

- `DJORG_DATABASE_URL` — DB SQLite locale (default `./data/djorganizer.db`).
- `ANTHROPIC_API_KEY` — chiave Anthropic per le azioni AI (Claude Haiku). Non ha prefisso
  `DJORG_`. Senza, i bottoni AI restano disabilitati.
- `DJORG_MUSICBRAINZ_USER_AGENT` — nessuna chiave richiesta, ma serve uno User-Agent
  identificabile: mettici un contatto reale (email o URL).
- `DJORG_DISCOGS_TOKEN` — opzionale: funziona anche senza (~25 req/min), con token gratuito
  sale a ~60/min. Si genera su discogs.com/settings/developers.
- `DJORG_ACOUSTID_API_KEY` — chiave gratuita da acoustid.org/new-application. Serve anche il
  binario `fpcalc`: `brew install chromaprint`.

## Principio di sicurezza

Ogni operazione sui file è prima un **piano** che approvi. Le modifiche sono in-place ma
reversibili: i delete vanno in **quarantena** (mai hard-delete) e ogni run scrive un
**undo journal** per annullare tutto.
