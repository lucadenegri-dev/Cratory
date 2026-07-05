# Fingerprinting AcoustID/Chromaprint (identita' certa per i file posseduti)

Data: 2026-07-05 · Stato: approvato a voce, in implementazione

## Obiettivo

Per le tracce possedute (`has_local_file`), ricavare dall'audio stesso il
MusicBrainz Recording MBID via fingerprinting AcoustID. L'identita' smette di
dipendere dai tag sporchi: MusicBrainz fa lookup diretto per MBID (niente fuzzy),
AcousticBrainz riceve l'MBID giusto, e MusicBrainz puo' backfillare l'ISRC dei
file locali che non ce l'hanno (sbloccando anche Deezer per il BPM).

Non rende obsoleto nulla: la catena fuzzy resta il percorso per le lead
streaming senza file e il fallback per i file assenti dal database AcoustID.
Shazam resta per i segmenti dentro i mix (AcoustID lavora su tracce intere).
`audio_hash` resta l'identita' esatta del file (riaggancio/dedup) e diventa la
chiave di cache del fingerprint.

## Decisioni

- **Persistenza**: nuova colonna `tracks.mbid` (VARCHAR, nullable, index),
  migrazione idempotente in `db.py` come le altre.
- **Soglia**: si applica il candidato migliore con `score >= 0.85`; sotto soglia
  l'esito resta in cache ma non si applica.
- **Cache**: `EnrichmentCache` provider `"acoustid"`, chiave `hash:{audio_hash}`
  (fallback `path:{local_path}`), `result_json={"candidates":[{mbid,score},...]}`.
  Si cacheano solo esiti definitivi (inclusa lista vuota = "non nel DB AcoustID").
  Errori di trasporto/fingerprint NON si cacheano: ritentabili (lezione della
  cache negativa dell'enrichment).
- **Dipendenze**: `pyacoustid` (pip, import lazy), binario `fpcalc` di Chromaprint
  (brew install chromaprint / exe su Windows), `ACOUSTID_API_KEY` gratuita in
  `backend/.env`. Il job e' "configurato" solo con chiave presente E fpcalc nel
  PATH (o env `FPCALC`).
- **Rate limit**: AcoustID ~3 req/s -> throttle 0.4s tra lookup nel servizio.

## Componenti

1. `core/config.py`: `acoustid_api_key: str = ""`.
2. `models.py` + `db.py`: colonna `mbid`.
3. `integrations/_http.py`: `post_with_retries` (il fingerprint e' troppo lungo
   per una query string GET).
4. `integrations/acoustid.py`: `AcoustIDError/NotConfigured`,
   `parse_lookup(payload)` puro (candidati {mbid, score} ordinati per score,
   dedup per mbid), `AcoustIDClient(api_key, fingerprinter=None, http=None)`
   con `identify(path)` (fingerprinter iniettabile: default pyacoustid/fpcalc),
   `acoustid_configured()`, `fpcalc_available()`.
5. `services/fingerprint.py`: `fingerprint_tracks(db, client, *, force,
   track_ids, on_progress)` — selezione `has_local_file AND local_path AND
   (mbid IS NULL OR force)`, cache-first, applica sopra soglia, report
   `{total, identified, not_found, below_threshold, cache_hits, errors,
   missing_files}`, fase progress `"fingerprint"`.
6. `services/fingerprint_job.py`: job thread singolo, pattern `enrichment_job`.
7. Router libreria: `POST /api/library/fingerprint` (409 se non configurato),
   `GET /api/library/fingerprint/status`.
8. Catena enrichment: `enrich_features` passa `context={"mbid": track.mbid}`
   quando presente; `MusicBrainzProvider` con mbid nel context fa lookup diretto
   `/recording/{mbid}?inc=releases+tags` (confidence 95, fallback su
   ISRC/search in caso di errore). AcousticBrainz legge gia' l'mbid dal context.
9. Frontend minimo: `api.ts` (start/status + tipi), poll in `jobs-provider`
   (GlobalProgress), bottone nella sezione Libreria di settings.

## Test (TDD)

- Colonna mbid su schema nuovo e DB migrato (stile `test_audio_hash_column`).
- `parse_lookup`: ordinamento per score, dedup mbid, payload malformati.
- `AcoustIDClient.identify`: fingerprinter e http finti, parametri richiesti,
  errori -> `AcoustIDError`.
- Servizio: selezione, soglia, cache hit al secondo run (zero chiamate), cache
  della lista vuota, errore non cachato e ritentato, force, report, progress.
- Router: 409 non configurato, shape di start/status.
- Catena: context mbid passato dal servizio enrichment; MusicBrainz by-mbid
  senza search; fallback su errore.
