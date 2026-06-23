# Roadmap

## Naming

Nome scelto: **SetArc**.

Perche':

- mette al centro l'arco narrativo/energetico del set;
- e' piu' specifico di "DJ Assistant";
- funziona sia per la generazione tecnica sia per la modalita' creativa;
- resta breve e facile da usare nell'interfaccia.

I path tecnici legacy (`djassistant.db`, log file) restano invariati per compatibilita'
locale, salvo futura migrazione esplicita.

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
- Rename prodotto a SetArc in documentazione e stringhe user-facing principali.
- Reset documentazione 2026-06-18.
- Rebranding UI "editorial archive" (monocromo, IBM Plex Mono, tema dark/paper).
- Dashboard command center (figure, istogramma BPM, attivita', copertura, azioni).
- Sezione Etichette: backfill da copyright Spotify + normalizzazione nomi.
- Discovery con etichette: Radar Etichette (`label:`) + segnale-etichetta su expand;
  rimossa la "compatibilita' tecnica" dal Discovery (resta del Set Builder).
- Import Spotify: solo playlist possedute; sync/aggiorna delle gia' importate.

## Prossimi passi

Direzione concordata (dettaglio operativo e ordine in `PROGRESS.md`):

1. **Multi-account (admin + users).** Autenticazione e separazione dati: oggi l'app
   e' mono-utente con stato globale (token Spotify, job, sessioni) -> da portare
   per-utente. E' il cambio architetturale piu' grande e abilita PostgreSQL.
2. **Miglioramento Discovery.** Qualita' candidati, segnali di gusto, spiegazioni.
3. **Sistemazione testi (pagina per pagina).** Copy/microcopy coerente.
4. **Multi-lingua (inglese).** i18n: estrazione stringhe + switch lingua.
5. **Rifacimento documentazione.** Dopo che multi-account stabilizza l'architettura.
6. **Audit codice + sicurezza.** Legato al punto 1 (authz). Vedi note sotto.
7. **Cambio nome app** (SetArc gia' esistente) + eventuale rename path legacy.
8. **Preparazione pitch.**

Backlog tecnico (non bloccante):

- **Shazam fase 2.** `DjSetTrack` come corpus per suggerimenti di co-occorrenza.
- **SoundCloud import.** Valutare prima API, auth e limiti reali.
- **PostgreSQL.** Diventa prioritario col multi-account (oggi SQLite basta).

## Rischi

| Rischio | Mitigazione |
|---|---|
| Provider con copertura disomogenea | chain multiprovider, cache, confidenza e stato `low_confidence` |
| Tracce senza BPM/key | stato `missing_features`, correzione manuale, score neutri dove possibile |
| Rate limit o errori rete | retry/backoff, job async, cache not-found |
| Output AI inventato | candidate cap, schema Pydantic, Validation Engine |
| Spotify recommendation non disponibile | Discovery basato su Last.fm e resolver Spotify `/search` |
| Rename prodotto rompe path dati | path legacy mantenuti, migrazione solo se esplicita |

## Decisioni consolidate

- Rekordbox non torna nel progetto.
- Spotify e' fonte di identita'/metadata, non di feature musicali.
- Discovery non usa Spotify `/recommendations`.
- Discovery non suggerisce piu' tracce dai gap della playlist; quei gap restano analisi separata.
- Discovery lavora per gusto, non per compatibilita' tecnica: BPM/key/transizioni
  sono competenza del Set Builder.
- Il modulo Shazam non popola direttamente la libreria: produce un corpus separato.
- SQLite resta sufficiente per uso locale mono-utente.
