# Roadmap

## Naming

Nome scelto: **Cratory** (`crate` + `-ory`, "repository/archivio di crate").

Perche':

- evoca il crate digging: l'archivio di tracce del DJ;
- coerente col brand editoriale (archivio, monospace, squadrato);
- coniato e brandabile, breve e facile nell'interfaccia;
- piu' specifico e distintivo di "DJ Assistant" (ed evita la collisione del vecchio
  nome provvisorio "SetArc", gia' esistente).

Disponibilita' `cratory.com` da confermare su un registrar. I path tecnici legacy
(`djassistant.db`, log file) restano invariati per compatibilita' locale, salvo futura
migrazione esplicita.

## Stato completato

- Core deterministico: scoring, set generator, transition finder.
- Spotify OAuth, import playlist, liked tracks, export playlist.
- Import manuale da tracklist incollata.
- Data model streaming-first.
- Rimozione Rekordbox.
- Cache enrichment.
- Provider feature: Deezer, MusicBrainz, AcousticBrainz, GetSongBPM, Last.fm.
- Gap Analysis.
- Candidate Engine con cap 60.
- AI Set Agent con output strutturato.
- Validation Engine.
- Set Editor e alternative.
- Modalita' `technical` e `creative`.
- Transition classification.
- Discovery playlist-seed Last.fm-centric con resolver Spotify e write-back.
- PATCH manuale valori traccia.
- UI Dashboard e Set Builder ridisegnate.
- Shazam/mix identification in integrazione.
- Test reale con chiavi completato.
- Confronto modelli AI completato e implementato.
- Rimossa la sezione Discovery che suggeriva tracce sulla base dei gap della playlist.
- Reset documentazione 2026-06-18.
- Rebranding UI "editorial archive" (monocromo, IBM Plex Mono, tema dark/paper).
- Dashboard command center (figure, istogramma BPM, attivita', copertura, azioni).
- Sezione Etichette: backfill da copyright Spotify + normalizzazione nomi.
- Discovery con etichette: Radar Etichette (`label:`) + segnale-etichetta su expand;
  rimossa la "compatibilita' tecnica" dal Discovery (resta del Set Builder).
- Import Spotify: solo playlist possedute; sync/aggiorna delle gia' importate.
- Discovery v2 "Scava generi": dig a volume via Discogs (genere/stile), lead non
  risolti, ranking profondita'+novita', salva-al-volo. Fix: cancellare una playlist
  non elimina piu' i brani condivisi (scollega invece di hard-delete).
- Rename prodotto a **Cratory** (UI, codice, docs, icona); legacy `djassistant.*` invariati.

## Direzione prodotto

Cratory e' uno **strumento personale/self-hosted eccellente** per DJ, NON un SaaS
multi-tenant pubblico. Vincolo bloccante (verificato): Spotify Web API non consente un
SaaS pubblico Spotify-based (dev mode max 5 utenti / Premium / endpoint ridotti;
extended quota mode solo per organizzazioni con servizio lanciato e >= 250k utenti/mese).
Il valore e' la qualita' del prodotto, non la scala.

## Prossimi passi

In ordine concordato (dettaglio operativo in `PROGRESS.md`):

1. **Miglioramento Discovery (continua).** Dopo "Scava generi" (Discogs): qualita' dei
   lead, piu' segnali di gusto, spiegazioni, e unificazione expand/dig (vedi backlog).
2. **Testi + multi-lingua (inglese).** Estrazione stringhe per l'i18n e revisione
   copy/microcopy pagina per pagina, in un passaggio unico (rollout nome gia' fatto).
3. **Audit leggero + quick win.** Threat model piccolo (nessun utente pubblico):
   efficienza `library_stats`, robustezza, dipendenze. Niente authz da SaaS.
4. **Rifacimento documentazione** quando il resto si assesta.

Sospesi / rivisti:

- **Multi-account pubblico** — sospeso (muro Spotify + direzione personale). Eventuale
  reshape futuro = piccola crew self-hosted con credenziali Spotify proprie, solo se serve.
- **Pitch** — da riformulare attorno alla natura reale del prodotto (non "SaaS Spotify").
- **Cambio nome** — FATTO (Cratory). Resta solo `cratory.com` da confermare su registrar.

Backlog tecnico (non bloccante):

- **Discovery: unificare expand/dig.** Portare anche il seme Playlist alla lista-dig a
  volume e arricchire il dig (tracklist per-release, Last.fm tag come 2a sorgente).
- **Playlist many-to-many.** Modello `playlist_tracks` (un brano in piu' playlist):
  l'import aggiunge membership invece di sovrascrivere `Track.playlist_id`. Oggi
  mitigato dal fix "scollega invece di cancellare", ma il modello resta 1:1.
- **Shazam fase 2.** `DjSetTrack` come corpus per suggerimenti di co-occorrenza.
- **SoundCloud import.** API chiusa a nuove app: rivalutare solo se riapre.
- **PostgreSQL.** Bassa priorita': SQLite basta per uso personale (servirebbe solo con
  un eventuale multi-utente).

## Rischi

| Rischio | Mitigazione |
|---|---|
| Provider con copertura disomogenea | chain multiprovider, cache, confidenza e stato `low_confidence` |
| Tracce senza BPM/key | stato `missing_features`, correzione manuale, score neutri dove possibile |
| Rate limit o errori rete | retry/backoff, job async, cache not-found |
| Output AI inventato | candidate cap, schema Pydantic, Validation Engine |
| Spotify recommendation non disponibile | Discovery basato su Last.fm e resolver Spotify `/search` |
| Spotify dev-mode limita la profondita' (5 utenti, search `label:` cap 10) | profondita' di genere/etichetta da Discogs (aperto); Spotify solo come resolver |
| Rename prodotto rompe path dati | path legacy mantenuti, migrazione solo se esplicita |

## Decisioni consolidate

- Cratory e' uno strumento personale/self-hosted, non un SaaS pubblico (muro policy Spotify).
- Rekordbox non torna nel progetto.
- Spotify e' fonte di identita'/metadata, non di feature musicali.
- Discovery: profondita' di genere/etichetta da Discogs (aperto); Spotify resta solo
  resolver di identita' (al salvataggio).
- Discovery non usa Spotify `/recommendations`.
- Discovery non suggerisce piu' tracce dai gap della playlist; quei gap restano analisi separata.
- Discovery lavora per gusto, non per compatibilita' tecnica: BPM/key/transizioni
  sono competenza del Set Builder.
- Il modulo Shazam non popola direttamente la libreria: produce un corpus separato.
- SQLite resta sufficiente per uso locale mono-utente.
