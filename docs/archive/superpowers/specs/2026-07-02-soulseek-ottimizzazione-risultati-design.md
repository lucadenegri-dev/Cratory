# Soulseek — ottimizzazione dei risultati (design)

> Migliora la qualità dei candidati e dei download Soulseek. Tutto deterministico
> (zero AI), stesso stile di `soulseek_select.py`. Deciso in sessione il 2026-07-02.

## Problema

Oggi la selezione usa: similarità del nome (SequenceMatcher + containment), tier
qualità (lossless/320/256) e disponibilità (slot/coda). Tre debolezze osservate:

1. La **durata** — il discriminatore più forte — è ignorata, benché `SlskdFile.length`
   arrivi già da slskd e `Track.duration_seconds` sia noto da Spotify.
2. La **query è unica e letterale** (`"{artist} {title}"`): i token accessori del
   titolo Spotify (`feat.`, parentesi, ` - Extended Mix`) fanno match AND su Soulseek
   ed escludono file validi; a zero risultati ci si arrende subito.
3. Le **versioni** (remix/extended/radio/live…) pesano solo dentro la similarità
   generica: il radio edit al posto dell'extended è un fallimento silenzioso.

Più due lacune: nessuna verifica post-download (un file sbagliato viene collegato
alla Track senza controlli) e la velocità di upload dell'utente non è considerata.

## Design

### 1. Durata nel ranking

- `rank_candidates(..., expected_duration: int | None = None)`.
- Punteggio durata da `Δ = |file.length − expected_duration|`:
  `Δ ≤ 3s → +1.0` · `Δ ≤ 10s → +0.5` · `Δ ≤ 20s → 0` · `Δ > 20s → −1.0` ·
  durata ignota (uno dei due `None`) → 0 (neutra, mai penalizzante).
- Peso nello `score`: `+ dur * 35` (sotto il nome=100, sopra availability=30).
- Confidenza: `+0.10` se `Δ ≤ 3s`, `−0.25` se `Δ > 20s`, clamp `[0, 1]`.
  L'ignoto non tocca la confidenza (Soulseek spesso non riporta `length`).
- Chiamanti aggiornati: job per-playlist/per-traccia e endpoint candidates passano
  `track.duration_seconds`.

### 2. Cascata di varianti di query

- Nuova funzione pura `query_variants(artist, title) -> list[str]` (dedup, in ordine):
  1. completa: `"{artist} {title}"` (comportamento attuale);
  2. pulita: senza contenuto di `(...)`/`[...]`, senza `feat./ft./featuring …`,
     senza suffisso versione dopo `" - "` (es. `" - Extended Mix"`);
  3. essenziale: artista + titolo-nucleo (la pulita, ulteriormente senza token di
     versione residui).
- Nuovo orchestratore `search_candidates(client, *, artist, title, expected_duration,
  pref, min_name_score) -> list[ScoredCandidate]` in `soulseek_select.py`: prova le
  varianti in ordine e si ferma alla prima che produce **almeno un candidato**
  (post-filtro). Il ranking confronta sempre col titolo/artista ORIGINALI (la
  pulizia riguarda solo la query, non la verifica).
- Job e router usano `search_candidates` al posto di `client.search` + `rank_candidates`.

### 3. Version-matching esplicito

- `_VERSION_TOKENS = {"remix", "extended", "edit", "radio", "live", "instrumental",
  "acoustic", "dub", "vip", "rework", "bootleg", "mashup", "acapella", "club"}`.
  Esclusi deliberatamente `original` e `mix` ("Original Mix" = versione di default,
  equivale a nessun token).
- Confronto insiemi: `wanted` = token nel titolo normalizzato; `got` = token nel
  basename normalizzato del candidato.
  - `wanted ∩ got ≠ ∅` → bonus `+0.15` sul name_score (già cappato a 1.0);
  - `wanted ≠ ∅` e `wanted ∩ got = ∅` → penalità `−0.20`;
  - `wanted = ∅` e `got ≠ ∅` → penalità `−0.20` (probabile versione indesiderata).
- Trade-off accettato: un titolo che contiene "live" come parola normale può subire
  una penalità impropria — deterministico e raro, va bene così.

### 4. Verifica post-download

- Dopo il download riuscito, PRIMA di `attach_local_file`: leggere la durata reale
  del file (mutagen, già usato) e confrontarla con `track.duration_seconds`.
- `Δ > 20s` → esito **`needs_review`**: il file resta in inbox, la Track NON viene
  marcata posseduta, l'item del job porta `reason: "durata non corrisponde
  (attesa Xs, file Ys)"`. Durata attesa o reale ignota → nessun blocco.
- Vale per il flusso per-playlist e per-traccia. La ricerca manuale (`_process_manual`)
  resta senza blocco: l'utente ha scelto a vista, si cataloga comunque.
- Gli item dello stato del job (`{track_id, artist, title, outcome}`) guadagnano il
  campo `reason: str | None` (oggi assente); la pagina Download lo mostra accanto
  all'esito `needs_review`.

### 5. uploadSpeed nel ranking

- `SlskdFile.upload_speed: int | None` catturato da `uploadSpeed` della risposta slskd.
- Contributo allo score: `min(upload_speed / 1_000_000, 1.0) * 10` (0–10 punti,
  1 MB/s = pieno); `None` → 0 (neutro). Non tocca la confidenza.

## Fuori scope

- Retry su altri utenti a metà download (già esiste, MAX_ATTEMPTS=4).
- Apprendimento dai pick manuali (tuning pesi da feedback): ipotesi futura.
- Fingerprint audio pre-download: impossibile (il file non c'è ancora).

## Test (criteri di accettazione)

- Durata: match esatto batte lossless-con-durata-sbagliata a parità di nome;
  ignota resta neutra (non scende sotto auto-pick un candidato altrimenti forte).
- Varianti: titolo con `(feat. X) - Extended Mix` produce fino a 3 varianti
  (deduplicate: pulita ed essenziale possono coincidere); la cascata si ferma alla
  prima variante con candidati; esaurite tutte, lista vuota.
- Versioni: cercato "Song Extended Mix" → file "Song (Radio Edit)" penalizzato e
  file "Song (Extended Mix)" premiato; cercato "Song" → file "Song (Live)" penalizzato.
- Post-download: file con durata fuori soglia → `needs_review` con reason, Track
  non posseduta; durata ignota → collegato normalmente.
- uploadSpeed: a parità di tutto, utente più veloce davanti; `None` neutro.
- Suite intera verde (333 baseline), nessuna regressione sui test slskd esistenti.

## Fette di implementazione

Piccola: **una fetta unica** (`feat/soulseek-risultati`), ~6 task TDD sul pattern
del piano fetta 1.
