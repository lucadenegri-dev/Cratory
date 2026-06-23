# PROGRESS - stato sviluppo

> File di ripresa lavoro. Aggiornare a ogni milestone reale. Per orientarsi leggere
> `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md` e `docs/ROADMAP.md`.

## Stato attuale

**Ultimo aggiornamento:** 2026-06-23

**Nome prodotto:** SetArc. DJ Assistant resta solo come nome storico; i path tecnici
legacy (`djassistant.db`, log path) restano invariati finche' non viene pianificata
una rename migration.

**Fase:** core streaming-first completo, Discovery playlist-seed operativo,
enrichment ampliato, Set Builder tecnico/creativo, test reale con chiavi completato,
confronto modelli AI implementato, correzioni manuali traccia, identificazione mix
via Shazam in corso di integrazione, documentazione riscritta.

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
- Import Spotify: solo playlist possedute; "Aggiorna" per le gia' importate.
- Merge su `master` e push. 186 test backend verdi, lint/build frontend puliti.

## Prossimi step (da vedere insieme)

Roadmap concordata, in ordine di discussione. Da dettagliare uno a uno prima di
implementare (brainstorming + spec dove serve).

1. **Multi-account (admin + users).** Introdurre autenticazione e separazione dati:
   ruolo admin + utenti. Impatta modello dati (oggi mono-utente), sessioni, scoping
   di libreria/playlist/set, e i token Spotify (oggi globali) -> per-utente.
2. **Miglioramento Discovery.** Affinare radar/expand: qualita' candidati, piu'
   segnali di gusto, dedup, spiegazioni, eventuale ranking configurabile.
3. **Sistemazione testi intera app (pagina per pagina).** Revisione copy/microcopy
   coerente, tono, errori, empty state — una pagina alla volta.
4. **Multi-lingua (inglese).** i18n: estrazione stringhe, struttura locale, switch
   lingua. Prerequisito utile per il punto 3 (testi gia' centralizzati).
5. **Rifacimento totale della documentazione.** README, ARCHITECTURE, API, ROADMAP,
   AGENTS, CLAUDE allineati allo stato reale post-rebranding e multi-account.
6. **Audit codice + sicurezza.** Revisione complessiva: dipendenze, gestione segreti,
   authz (legato al punto 1), input validation, superfici API, lint/typing.
7. **Cambio nome app.** "SetArc" risulta gia' esistente. **Nome scelto: Cratory**
   (`crate` + `-ory`, vibe "repository/archivio di crate", coerente col brand
   editoriale). _Da confermare la disponibilita' di `cratory.com` su un registrar._
   Il rollout (UI, docs, repo, chiave localStorage `setarc-theme`, ed eventuali path
   tecnici legacy `djassistant.*`) NON va fatto a se': si esegue insieme ai punti 3
   (testi) e 4 (i18n), dove tutte le stringhe sono gia' toccate -> swap a costo minimo.
   Nel frattempo: non incastonare "setarc" in nuove superfici persistenti/pubbliche.
8. **Preparazione pitch.** Materiale di presentazione del prodotto.

## Funzionalita' completate

- Import playlist Spotify, liked tracks e import manuale.
- Normalizzazione e deduplica streaming-first.
- Rimozione completa del flusso Rekordbox.
- Cache enrichment persistente con `EnrichmentCache`.
- Enrichment feature identita'-first:
  `Deezer -> MusicBrainz -> AcousticBrainz -> GetSongBPM -> Last.fm`.
- Proxy deterministico di energia quando nessun provider la fornisce direttamente.
- Stati traccia calcolati da `services/track_status.py`.
- PATCH manuale dei valori musicali, con precedenza sui provider.
- Gap Analysis deterministica.
- Set Builder deterministico + AI, modalita' `technical` e `creative`.
- Candidate Engine con cap 60 per impedire all'AI di vedere tutta la libreria.
- Validation Engine su output AI.
- Alternative deterministiche e Set Editor.
- Classificazione transizioni: `technically_safe`, `creative_risk`, `good_reset`.
- Discovery playlist-seed Last.fm-centric con resolver Spotify e write-back in libreria.
- Stato unificato integrazioni in `/api/services/status`.
- Modulo Shazam per identificare tracklist di mix in corpus separato dalla libreria.
- Test reale con chiavi completato.
- Confronto modelli AI completato e implementato.
- Discovery gap-driven rimossa dalla UI/prodotto; Gap Analysis resta lettura separata.

## Prossimi passi consigliati

1. Shazam fase 2: usare i `DjSetTrack` identificati come corpus per suggerimenti di
   co-occorrenza e confronto con la libreria.
2. Valutare SoundCloud import solo dopo verifica fattibilita' API.
3. PostgreSQL migration: low priority, SQLite e' sufficiente per mono-utente.
4. Rename tecnico opzionale: decidere se migrare anche database/log path legacy.

## Note operative

- Database canonico: `backend/data/djassistant.db`.
- Log backend: `backend/logs/djassistant.log`.
- Redirect Spotify locale: `http://127.0.0.1:8000/api/spotify/callback`.
- Discovery non usa Spotify `/recommendations`: Last.fm fornisce similarita',
  Spotify risolve via `/search`.
- AcousticBrainz usa dataset storico congelato al 2022: buona copertura catalogo,
  bassa copertura su uscite recentissime.
- Shazam richiede `ffmpeg`, `yt-dlp` e `shazamio`; salva `DjSet`/`DjSetTrack`, non
  `Track` di libreria.

## Verifiche consigliate

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

## Storico essenziale

- 2026-06-17: UI Dashboard/Set Builder ridisegnate, PATCH tracce, 140 test verdi.
- 2026-06-17: Deezer + AcousticBrainz aggiunti alla catena enrichment.
- 2026-06-15: import Spotify reale corretto, DB legacy ripulito, servizi status.
- 2026-06-15: classificazione transizioni e supporto modello economico Haiku 4.5.
- 2026-06-14: Rekordbox rimosso, cache enrichment, prompt AI arricchito, Discovery
  Last.fm-centric, import manuale, energia/mood deterministici.
