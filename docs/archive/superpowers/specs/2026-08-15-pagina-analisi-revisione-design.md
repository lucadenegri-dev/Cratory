# Revisione pagina Analisi — scarto divergenze, analisi al centro, testi asciutti

Data: 2026-08-15
Stato: approvata (brainstorming con l'utente)

## Problema

Tre difetti emersi dall'uso reale della pagina `/analysis`:

1. **L'uso reale è un bottone solo.** La pagina mette in cima l'import Rekordbox
   (fonte primaria sulla carta), ma nell'uso quotidiano si preme solo «Avvia
   analisi». La gerarchia visiva non riflette la frequenza d'uso.
2. **Le divergenze sono eterne.** `diverges()` è un confronto puro
   `analysis_* ≠ canonico`: se l'utente decide che il valore attuale va bene,
   la riga non ha modo di sparire — resta in tabella per sempre.
3. **Testi prolissi in stile AI.** Hint e note spiegano troppo
   (`scopeHintMissingHalf`, `scopeHintAll`, `startedNote`, `ledeHint`…): vanno
   asciugati a tono da etichetta.

## Decisioni (con l'utente)

- **Forma pagina**: analisi in-app al centro come azione principale; import
  Rekordbox resta in pagina ma ripiegato/secondario. Il selettore d'ambito resta.
- **Semantica dello scarto**: lo scarto fotografa i valori `analysis_*`
  scartati; la riga resta nascosta finché una nuova analisi produce lo stesso
  risultato e **ricompare solo se l'analisi dà un valore diverso** dallo
  snapshot scartato.
- **Nessun recupero**: niente UI per rivedere/ripristinare le scartate. Una
  riga scartata ricompare solo via ri-analisi con esito diverso.
- **«Ignora» senza conferma**: non sovrascrive nulla (tiene il canonico), non
  serve modale.

## Backend

### Modello e migrazione

Due colonne nuove su `Track` (`backend/app/models.py`), migrazione idempotente
in `db.py` con lo stesso pattern delle altre:

- `analysis_dismissed_bpm: float | None`
- `analysis_dismissed_camelot: str | None`

### Servizio (`services/audio_analysis.py`)

- `is_dismissed(track) -> bool`: True se lo snapshot scartato coincide con i
  valori `analysis_*` correnti, **alla stessa precisione di `diverges()`**:
  BPM confrontato a 1 decimale (None==None), camelot confrontato esatto
  (vuoto==vuoto). Se una nuova analisi cambia uno dei due campi, la funzione
  torna False e la divergenza riappare da sola.
- `diverges()` resta puro (analisi ↔ canonico, invariato).
- Il concetto esposto da router/overview diventa la **divergenza aperta**:
  `diverges(t) and not is_dismissed(t)`.

### Router (`routers/analysis.py`)

- `GET /api/analysis/divergences`: filtra le scartate (solo divergenze aperte).
- `GET /api/analysis/overview`: il conteggio `divergent` conta solo le aperte.
- **Nuovo** `POST /api/analysis/dismiss`, body `{track_ids: [int]}`: per ogni
  traccia posseduta indicata scrive lo snapshot (= `analysis_*` correnti);
  risponde `{dismissed: n}`. Nessuna guardia sul fatto che la traccia diverga:
  lo snapshot è idempotente e innocuo.
- `POST /api/analysis/apply` con `mode='divergent'`: opera solo sulle
  divergenze **aperte**, coerente con ciò che la tabella mostra.
  `mode='all'`+`force` resta com'è (riscrive tutte le analizzate, anche
  scartate: il force è già la scelta esplicita di ignorare ogni guardia).

### Schemi (`schemas.py`)

`AnalysisDismissIn {track_ids: list[int]}`, `AnalysisDismissOut {dismissed: int}`.

## Frontend

### Struttura pagina (`app/analysis/page.tsx`)

Ordine nuovo:

1. **Lede** invariata («N tracce non pronte» + link Libreria).
2. **Card «Analisi in-app»** promossa a card propria in cima: ambito +
   «Avvia analisi» + hint di una riga.
3. **Divergenze** subito sotto:
   - per riga: ghost **«Ignora»** accanto ad «Applica», senza conferma;
   - in testata: **«Ignora selezionate (n)»** accanto ad «Applica selezionate»;
   - «Forza su tutte» resta il link in fondo alla card.
4. **Import Rekordbox** ripiegato in fondo (`<details>`, summary
   «Import Rekordbox — fonte primaria»): aperto è la card di oggi. La riga di
   precedenza `manuale > rekordbox > cratory` migra lì dentro come nota; la
   striscia dedicata sparisce.

Marginalia statistiche: invariata.

### API client (`lib/api.ts`)

`dismissAnalysis(track_ids: number[])` → `POST /api/analysis/dismiss`; dopo lo
scarto la pagina fa `reload()` come per l'apply.

### Testi (`lib/i18n/it.ts` + `en.ts`)

Tono da etichetta, entrambe le lingue:

- `scopeHintMissingHalf`: **eliminata** (e con lei il calcolo `missingHalf`
  nella pagina).
- `scopeHintAll`: «Rianalizza tutte le N possedute; le differenze finiscono in
  Divergenze.»
- `startedNote`: «Analisi avviata: progresso nella barra in basso.»
- `ledeHint`: «Pronta = BPM + tonalità presenti.»
- `sourcesSubtitle`: sparisce con la card unica.
- `divergencesEmpty`: «Nessuna divergenza.»
- Nuove: `ignoreRow` («Ignora»), `ignoreSelected(n)`, e la voce del summary
  Rekordbox.

## Test

Backend (estendono `test_audio_analysis.py`, `test_analysis_router.py`):

- dismiss nasconde la riga da `/divergences` e dal conteggio `divergent`;
- ri-analisi con valore diverso (BPM oltre 1 decimale, o key diversa) la fa
  ricomparire; ri-analisi con valore identico no;
- `apply mode='divergent'` non tocca le scartate; `mode='all'`+`force` sì;
- BPM a precisione 1 decimale: snapshot 128.04 vs nuova analisi 128.0 non
  riappare (stesso arrotondamento di `diverges()`).

Frontend (`tests/analysis-page.test.tsx`): bottone «Ignora» chiama l'API e
ricarica; «Ignora selezionate» idem; la card Rekordbox è dentro un `<details>`
chiuso di default.

Verifica: `pytest` (venv del checkout principale, cwd backend del worktree),
`npm run lint`, `npm test`.

## Fuori scope

- Recupero/ripristino delle divergenze scartate.
- Qualunque modifica al job di analisi (`audio_analysis_job.py`) o a
  `auto_apply_missing`.
- Riduzione della marginalia statistiche.
