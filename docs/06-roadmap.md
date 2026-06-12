# 06 — Roadmap (MVP 1 → 4)

Strategia: implementare **MVP 1 in modo completo**, predisponendo architettura e interfacce (service layer per Spotify, Discogs, MusicBrainz, AI) per le fasi successive senza implementarle subito.

> ⚠️ **Nota dal file XML reale**: le tracce Spotify hanno `Name` e `Artist` vuoti nell'export (sono ~198 su 293 tracce nel file di esempio). Fino a MVP 2 la libreria mostrerà molte tracce "senza titolo": il Library Explorer in MVP 1 deve gestire il caso con grazia (mostrare Spotify ID, badge "metadata mancanti", filtro dedicato). Questo rende MVP 2 (enrichment) la priorità immediata dopo MVP 1.

## MVP 1 — Core deterministico ✅ obiettivo prima iterazione

- [ ] Struttura progetto (backend FastAPI a layer + frontend Next.js/React)
- [ ] Database SQLite con SQLAlchemy + modelli principali
- [ ] Upload XML Rekordbox e parsing collection (lxml)
- [ ] Estrazione tracce, riconoscimento sorgente, estrazione Spotify/SoundCloud ID da `Location`
- [ ] Salvataggio beatgrid (`TEMPO`) e cue point (`POSITION_MARK`)
- [ ] Report di import (statistiche + errori)
- [ ] Re-import idempotente (nessun duplicato)
- [ ] Dashboard import
- [ ] Tabella libreria con filtri: BPM, key, artist, source (+ metadata incompleti)
- [ ] Scoring tecnico tra tracce (BPM, Camelot, durata, cue, play count)
- [ ] Transition finder tecnico (prima/dopo)
- [ ] Set generator algoritmico base con spiegazione tecnica
- [ ] Interfacce/service layer predisposti per Spotify, Discogs, MusicBrainz, AI Agent
- [ ] `.env.example`, README setup, logging
- [ ] Seed/demo con `export_rekordbox.xml`
- [ ] Test base: parser XML e scoring transizioni

## MVP 2 — Spotify

- [ ] Spotify OAuth (login + callback)
- [ ] Enrichment metadata (title/artist/album/cover/link/artist genres/popularity) con cache
- [ ] Completamento `Name`/`Artist` vuoti dalle API (senza mai toccare BPM/key di Rekordbox)
- [ ] Cover e link Spotify nella UI (Library, Track Detail)
- [ ] Creazione playlist Spotify da set generato
- [ ] Gestione rate limit ed errori API

## MVP 3 — AI

- [ ] AI Set Agent (input/output JSON come da F7)
- [ ] Prompt libero per generazione set
- [ ] Spiegazioni narrative (globale + per traccia)
- [ ] Alternative per traccia (F9)
- [ ] Validation Engine (F8) con auto-correzione / retry / warning
- [ ] Transition Finder arricchito con classificazione musicale (F10)

## MVP 4 — Library Expansion

- [ ] Integrazione Discogs API
- [ ] Integrazione MusicBrainz API (fallback)
- [ ] Library Expansion Advisor (F11)
- [ ] Expansion from Track (F12)
- [ ] Expansion from Artist (F13)
- [ ] Expansion from Set (F14)
- [ ] Expansion from Genre (F15)
- [ ] Gestione suggerimenti salvati con stati (new / to_listen / listened / added_to_library / ignored)

## Rischi e punti di attenzione

| Rischio | Mitigazione |
|---|---|
| Tracce Spotify senza titolo/artista fino a MVP 2 | UI MVP 1 tollerante ai metadata mancanti; MVP 2 subito dopo |
| Sample/oneshot del sampler Rekordbox inquinano la libreria (durata 5–7s, BPM 0) | Filtro "evita tracce troppo corte" + flag nel report import |
| `Genre` quasi sempre vuoto nell'XML | I generi arrivano dagli artist genres Spotify (MVP 2): il Candidate Engine deve funzionare anche senza genere |
| Output AI non valido o con track_id inventati | Validation Engine obbligatorio + schema Pydantic sull'output |
| Rate limit Spotify su enrichment massivo | Batch + cache persistente |
