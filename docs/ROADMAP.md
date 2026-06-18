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

## Prossimi passi

1. **Shazam fase 2.** Usare `DjSetTrack` come corpus per suggerimenti di co-occorrenza
   e confronto con la libreria.
2. **SoundCloud import.** Prima valutare API, auth e limiti reali; poi implementare.
3. **PostgreSQL.** Low priority finche' l'app resta mono-utente locale.
4. **Rename tecnico opzionale.** Decidere se migrare anche database/log path legacy o
   lasciarli stabili.

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
- Il modulo Shazam non popola direttamente la libreria: produce un corpus separato.
- SQLite resta sufficiente per uso locale mono-utente.
