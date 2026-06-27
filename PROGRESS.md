# PROGRESS - diario di sviluppo

> Diario di ripresa lavoro: solo cronologia e punto di ripresa. Lo **stato corrente,
> le priorità e le decisioni** vivono in `docs/ROADMAP.md` (fonte di verità). Per
> orientarsi: `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `CLAUDE.md`.

## Stato attuale

**Ultimo aggiornamento:** 2026-06-27

**Nome prodotto:** **Cratory** (rename eseguito il 2026-06-25 su UI, codice, docs e
icona). "SetArc" e "DJ Assistant" restano solo come nomi storici; i path tecnici legacy
(`djassistant.db`, log path) restano invariati finche' non viene pianificata una rename
migration. Disponibilita' `cratory.com` da confermare su registrar.

**Fase:** core streaming-first completo; Discovery operativo (expand Last.fm + dig
Discogs); enrichment multi-provider; Set Builder tecnico/creativo; audit leggero (quick
win) fatto; identificazione mix via Shazam in integrazione. In corso: rifacimento
documentazione (ridisegno dell'architettura doc).

## Milestone 2026-06-18 - Reset documentazione

- Ridotta la documentazione da sei spec numerate a tre documenti stabili:
  `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md`.
- Riscritto `README.md` come porta d'ingresso per setup, workflow e stato.
- Snellito `AGENTS.md` come guida operativa per agenti.
- Compattato `PROGRESS.md` in un diario di ripresa.
- Mantenuto `CLAUDE.md` come entrypoint per l'AI usata insieme a Codex.
- Rimossi Markdown duplicati o vuoti: `frontend/README.md`, `IMPROVEMENTS.MD`,
  vecchie spec `docs/01`-`06`.
- Nome scelto: **SetArc**. Aggiornate documentazione e stringhe user-facing principali,
  senza rinominare path tecnici legacy.
- Roadmap riallineata: test reale con chiavi gia' fatto, confronto modelli AI gia'
  implementato, sezione Discovery basata sui gap rimossa.

## Milestone 2026-06-23 - Rebranding editoriale + Discovery etichette

- Rebranding completo: design system "editorial archive" monocromo (IBM Plex Mono,
  filetti, squadrato), tema dark di default + paper via toggle (runtime `--c-*` +
  `@theme inline`), shell editoriale `EditorialShell`/`PageLayout`, no-FOUC.
- Dashboard "command center": hero figures, istogramma BPM interattivo, attivita'
  recente, copertura enrichment, azioni rapide.
- Barra di avanzamento job globale (enrichment/shazam/backfill etichette) persistente
  al cambio pagina.
- Etichette: backfill da `copyrights` Spotify (dev mode), normalizzazione nomi
  (`_clean_label`), merge varianti a read-time.
- Discovery direzione C: **Radar Etichette** (`POST /api/discovery/labels`, filtro
  Spotify `label:`), **segnale-etichetta** su `/expand`, rimozione della
  "compatibilita' tecnica" (resta al Set Builder). Controlli in barra orizzontale.
  (Nota: questo endpoint `label:` e' stato poi rimosso il 27/06; il Radar usa Discogs.)
- Import Spotify: solo playlist possedute; "Aggiorna" per le gia' importate.
- Decisa la direzione prodotto: strumento **personale/self-hosted**, non SaaS pubblico
  (vincolo Spotify dev-mode). Dettaglio e conseguenze in `docs/ROADMAP.md`.
- Merge su `master` e push. 186 test backend verdi, lint/build frontend puliti.

## Milestone 2026-06-27 - Audit leggero (quick win)

- SSRF guard: l'URL del mix Shazam e' validato (solo http/https) prima di yt-dlp.
- Performance: `library_stats` riscritta con query SQL aggregate (niente full-load
  ORM), output identico; alleggerisce dashboard e contesto AI dei set.
- Rimosso l'endpoint morto `/api/discovery/labels` (+ `discover_by_labels`, helper,
  schema, `search_by_label`, test e funzione frontend): il Radar Etichette usa Discogs.
- Dipendenze: rimosso `requirements copia.txt`, tetti versione alle deps critiche,
  error body upstream accorciati. 197 test backend verdi.
- Audit confermato: CORS, secrets, retry/timeout, SQL injection e cleanup temp gia'
  a posto; niente altro di urgente per uso self-hosted.
- (UI fuori roadmap: loader EQ/waveform stile DJ con respiro e barre strette.)

## Punto di ripresa

Priorità e backlog completi in `docs/ROADMAP.md` (fonte di verità di stato). In sintesi:
core assestato e audit quick-win fatto; in corso il rifacimento documentazione. Il
prossimo fronte aperto dopo i doc è il **miglioramento Discovery** (qualità dei lead,
più segnali di gusto, spiegazioni). i18n EN e multi-account pubblico restano sospesi.

## Storico essenziale

- 2026-06-17: UI Dashboard/Set Builder ridisegnate, PATCH tracce, 140 test verdi.
- 2026-06-17: Deezer + AcousticBrainz aggiunti alla catena enrichment.
- 2026-06-15: import Spotify reale corretto, DB legacy ripulito, servizi status.
- 2026-06-15: classificazione transizioni e supporto modello economico Haiku 4.5.
- 2026-06-14: Rekordbox rimosso, cache enrichment, prompt AI arricchito, Discovery
  Last.fm-centric, import manuale, energia/mood deterministici.
