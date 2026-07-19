# Shazam robustezza v2 — backoff, analisi parziale onesta, scarto degli smentiti

Data: 2026-07-19. Stato: approvato (a voce, sui tre punti; questa spec fissa i
dettagli). Segue e supera in parte
`2026-07-19-shazam-mix-robustness-design.md`.

## Evidenza sul campo (set Gelati, 2h08m, tetto 200)

1. **Troncamento silenzioso.** Dopo ~100+ chiamate ravvicinate l'endpoint
   shazamio ha iniziato a rifiutare; 8 errori consecutivi hanno interrotto la
   griglia a 46:09 su 2h08m, ma il set si e' salvato `done` senza alcun segnale.
2. **Falsi positivi che spezzano le run.** "Martinou — Don't Fall" confermata
   due volte (19:30 e 22:06) con un falso ("Viot — Carrie") in mezzo; "Total
   Eclipse of the Heart" vista due volte (16:15 e 18:51) con "Titanium" in
   mezzo: due campioni distanti e concordi sono un segnale forte, ma oggi
   restano tre voci dubbie.
3. **I singoli sono rumore.** Verifica a orecchio dell'utente: i match da
   campione singolo erano quasi tutti pezzi sbagliati; anche col passo a 39s i
   singoli restati singoli non sono stati promossi.

## Design

### 1. Pacing + backoff (integrations/shazam.py)

`ShazamioRecognizer` gestisce il ritmo verso l'endpoint, il core resta puro:

- **Pacing**: intervallo minimo di **1.0s** tra l'inizio di due riconoscimenti
  (`MIN_CALL_INTERVAL`); se la chiamata precedente e' finita da meno, dorme la
  differenza.
- **Backoff con ripresa**: su eccezione, ritenta internamente con attese
  crescenti **5s, 15s, 45s** (`BACKOFF_WAITS`); solleva `RecognizerError` solo
  a tentativi esauriti. Cosi' 8 `RecognizerError` consecutivi nel core
  significano un guasto persistente (~minuti), non una raffica di 429.
- Testabilita': `sleep` e `monotonic` iniettabili nel costruttore
  (default `time.sleep`/`time.monotonic`); i test passano finti.

`MAX_CONSECUTIVE_ERRORS = 8` nel core resta l'ultima rete di sicurezza.

### 2. Analisi parziale onesta (core → DB → UI)

- `identify_from_recognizer` ritorna **`(tracks, aborted_at)`**: `aborted_at` =
  offset (secondi) dell'ultimo campione tentato quando la griglia si interrompe
  per errori consecutivi, `None` a completamento normale. `identify_set`
  propaga: `(meta, tracks, aborted_at)`.
- Nuova colonna **`DjSet.aborted_at_seconds`** (Integer, nullable) con
  migrazione idempotente in `ensure_schema`; esposta in `DjSetOut` e nel
  router.
- UI: quando `status == done` e `aborted_at_seconds` presente, badge
  **PARZIALE** (tone `warning`, il tratteggio) in lista e dettaglio, con nota
  "interrotta a H:MM:SS" (i18n IT/EN).

### 3. Grouping v2: fusione temporale, conferma lontana, scarto (core)

Sostituisce la finestra a conteggio buchi (`MERGE_MAX_GAPS`):

- **`group_samples`**: collassa solo i campioni **strettamente consecutivi**
  con la stessa chiave (un buco spezza); tiene `last_offset`.
- **`merge_same_key_runs(runs, window=MERGE_WINDOW_SECONDS)`** con
  `MERGE_WINDOW_SECONDS = 240`: la stessa chiave che ricompare entro 240s
  dall'ultimo campione della sua run precedente si fonde con quella run
  (hit sommati), **anche se in mezzo c'e' un match diverso** — e' il caso
  reale del falso positivo dentro una traccia lunga (Titanium dentro Total
  Eclipse) e dell'overlap di mixaggio; il match in mezzo resta una voce sua.
  Oltre 240s, o con chiave diversa, la ricomparsa e' una voce nuova (il DJ
  l'ha rimessa). Due campioni distanti concordi fanno cosi' `hits >= 2` →
  confermata senza spendere chiamate.
- **Conferma lontana, a due lati**: per le run rimaste a `hits == 1`, campione
  a `offset + delta` e, se non concorde, `offset - delta`, con
  `delta = max(6, min(step // 2, 30))` — abbastanza lontano dalla transizione
  che ha generato il falso. Ogni tentativo consuma budget; candidati fuori
  dall'audio o coincidenti con l'offset originale si saltano.
- **Scarto degli smentiti**: una run singola la cui conferma **e' stata
  tentata** e non ha concordato viene **scartata** (era rumore). Una run
  singola **mai verificata** (budget esaurito, recognizer giu', audio troppo
  corto) resta in lista come **dubbia** (confidence 45, badge DUBBIA): assenza
  di prove, non prova contraria.
- Confidence invariata: `hits >= 2` → 90; dubbia → 45. I set gia' analizzati
  non cambiano.

## Fuori scope

Retry pitch-compensato; raffinamento dei confini; tetto oltre 200.

## Test

- Recognizer: pacing (seconda chiamata ravvicinata dorme ~1s), backoff (attese
  5/15/45 poi RecognizerError), successo al retry non solleva.
- Core: fusione entro finestra su soli buchi; fusione oltre il match diverso in
  mezzo (caso Total Eclipse); ricomparsa oltre 240s = voce nuova; conferma a
  due lati che salva una traccia vicina alla fine; smentito scartato; mai
  verificato resta dubbio; `aborted_at` valorizzato all'interruzione e `None`
  a completamento; budget e progresso coerenti.
- Job: persiste `aborted_at_seconds`; serializer/router lo espongono.
- Frontend: badge PARZIALE renderizzato solo con `aborted_at_seconds` presente.
