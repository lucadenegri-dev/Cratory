# Revisione generi AI su tutta la library (job in background)

Data: 2026-08-10 · Stato: approvata

## Obiettivo

I generi in tag sono spesso sbagliati o troppo approssimativi, ma oggi l'AI li
vede solo quando esiste una issue aperta (`missing_metadata` / `dirty_genre`):
un genere presente-ma-sbagliato non viene mai rivisto. Inoltre il suggerimento
attuale (`ai_tags.suggest_genres`) indovina da "Artista - Titolo" senza alcuna
fonte esterna.

Questa feature introduce un **job in background "Revisione generi"** che passa
**tutta la library** (o un sottoinsieme filtrato), raccoglie evidenza dai
provider (MusicBrainz/Discogs) e — solo nei casi dubbi — dalla **ricerca web**
(server tool Anthropic), e propone correzioni come issue da accettare/rifiutare
nel flusso standard ISSUES → PLAN → APPLY. Il vecchio bottone/endpoint
"Suggerisci generi" viene **rimosso**: il job lo sostituisce integralmente.

Decisioni prese in brainstorming:

- **Copertura**: tutta la library, inclusi i generi già "puliti" senza issue.
- **Vocabolario**: libero con normalizzazione (`genre_norm.normalize_genre`);
  nessuna lista canonica.
- **Fonti**: provider come contesto primario + web search AI come fallback sui
  casi in cui l'evidenza non basta.

## Non-obiettivi

- Nessun vocabolario controllato dei generi (potrà arrivare in futuro).
- Nessuna modifica al flusso PLAN/APPLY: le proposte restano issue normali.
- Nessuna scrittura diretta dei tag: vale il principio di sicurezza esistente
  (ogni modifica passa da un piano approvato).

## Architettura

### Backend — job

Pattern identico a `provider_rescan_job` (mono-job, stato in memoria con lock,
thread daemon, la UI fa polling):

- `app/services/genre_review.py` — logica pura, testabile, con `on_progress`.
- `app/services/genre_review_job.py` — `job_state()`, `is_running()`,
  `start_job(...)`; fasi: `looking_up` (provider) e `reviewing` (AI).
- `app/routers/genre_review.py` — `POST /api/genre-review` (start; body:
  `redo: bool = False`, `folder: str | None`, `genre: str | None`) e
  `GET /api/genre-review/status`. Un `GET /api/genre-review/preview` restituisce
  il conteggio dei file che il job processerebbe (per la conferma in UI).

### Selezione dei file e resumabilità

- Candidati: `AudioFile.status == "present"`, filtrabili per cartella/genere
  (come il rescan provider).
- Nuova colonna `AudioFile.genre_reviewed_at: datetime | None` (via
  `ensure_schema()`); di default il job salta i file già revisionati
  (`genre_reviewed_at IS NOT NULL`). `redo=True` li riprocessa tutti.
- Il campo si azzera se il file cambia contenuto? No: resta; una nuova passata
  completa si ottiene con `redo=True`. (Semplicità > automatismi.)

### Pipeline per file

1. **Evidenza provider.** Gli adapter `musicbrainz.py` e `discogs_meta.py`
   vengono estesi per restituire anche `genre_candidates: list[str]` (MB: tag
   della recording/release; Discogs: styles + genres completi, styles prima).
   Una lookup per file: mbid se presente, altrimenti testuale artist/title.
   Rate limit MB invariato (1 req/s) → ~3000 file ≈ 50 min: accettabile, è un
   job batch con barra di progresso.
2. **AI.** Nuova `ai_tags.review_genres(items) -> list[GenreReview]` con
   Claude Haiku 4.5 (`claude-haiku-4-5`, modello già in uso nel progetto):
   - server tool `web_search_20250305` (unica variante supportata da Haiku)
     con `max_uses` basso (default 3 per richiesta);
   - batch piccoli (~10 tracce per richiesta: la search allunga le risposte);
   - input per traccia: artista, titolo, album, label, genere attuale,
     `genre_candidates` dei provider;
   - prompt: scegli il genere primario più accurato; i candidati provider sono
     evidenza forte; usa la ricerca web **solo** se l'evidenza non basta; non
     inventare; output allineato per indice;
   - output strutturato via `messages.parse` (come le funzioni esistenti in
     `ai_tags.py`): gli structured output sono compatibili con i server tool —
     il blocco finale di testo rispetta lo schema anche quando la risposta
     contiene blocchi `server_tool_use`/`web_search_tool_result` intermedi;
   - campi per traccia: `genre: str | None`, `confidence: "high" | "low"`.
3. **Esito.** Proposta → `normalize_genre` → confronto col genere attuale
   (case-insensitive, dopo normalizzazione di entrambi):
   - **Diversa** → serve una issue col suggerimento
     `{"field": "genre", "action": "retag", "to": <proposta>, "source": "ai",
     "confidence": <"high"|"low">}`:
     - se esiste già una issue **aperta** su `genre` di tipo
       `missing_metadata` o `dirty_genre` → si riempie/aggiorna il suo
       `suggested_fix_json` (mai se il suggerimento esistente è
       `source == "provider"` con la issue già accettata — i fix manuali
       accettati non si toccano, regola invariata);
     - altrimenti → issue di **nuovo tipo `genre_review`** (field `genre`,
       status `open`). Mai due issue aperte sullo stesso campo dello stesso
       file.
   - **Uguale** → genere confermato: si chiude (dismiss) un'eventuale
     `genre_review` aperta e non si crea nulla.
   - **Nessuna risposta AI** (`genre is None`) → contato come `unresolved`,
     nessuna issue.
   - In ogni caso `genre_reviewed_at = utcnow()` e commit per-batch.
4. **Precedenza** (invariata): manual > provider > AI. Il job scrive sempre
   `source: "ai"`; un successivo provider-suggest può sovrascrivere il
   suggerimento come oggi.

### Rimozione del vecchio "Suggerisci generi"

- Backend: eliminati `POST /api/issues/ai-suggest-genre` e
  `ai_tags.suggest_genres` (+ `_GENRE_PROMPT`, `_GenreGuess*`).
- Frontend: eliminati il bottone in ISSUES, `aiSuggestGenres` in `lib/api.ts`
  e le chiavi i18n dedicate (`aiGenresBtn`, `aiGenresNote`, ecc.) da `en.ts` e
  `it.ts`.
- Test: quelli sul vecchio endpoint rimossi/sostituiti dai nuovi.

### Frontend

- In ISSUES, al posto del vecchio bottone: **"Revisione generi (AI)"**. Al
  click: fetch di `/api/genre-review/preview` → piccola conferma inline con
  numero file e nota costi ("usa ricerche web a pagamento") → start.
- Progresso nella barra jobs (`components/jobs-provider.tsx`), stesso pattern
  del rescan provider: polling di `/api/genre-review/status`, fasi
  `looking_up`/`reviewing`, contatore `processed/total`.
- Risultato a fine job (nel toast/nota della pagina): file processati,
  proposte di cambio, confermati, non risolti.
- Le issue `genre_review` compaiono nella tabella ISSUES con etichetta i18n
  (EN default + IT) e si gestiscono come le altre (accetta/ignora, fix
  manuale, bulk). Accettarle produce nel PLAN il retag + eventuale
  spostamento in `Library/{nuovo genere}/{artista}/`.

## Gestione errori

- `ANTHROPIC_API_KEY` assente → l'endpoint start risponde
  `{configured: false}` senza avviare il job (pattern del vecchio endpoint);
  la UI disabilita il bottone con tooltip.
- Errore AI/provider su un batch → il batch è contato come `unresolved`, il
  job prosegue; errore fatale → stato `error` nel job (pattern esistente).
- I file già processati restano marcati: un re-start riprende da dove si era
  interrotto (resumabilità via `genre_reviewed_at`).

## Costi indicativi

Per ~3.000 tracce: ~300 richieste Haiku, ≤900 web search nel caso peggiore
(≈ $9 di search a $10/1000 + ~$2-3 di token). Molto meno se i provider coprono
la maggior parte dei casi. Il `max_uses` per richiesta è il tetto di spesa.

## Test

- **Service** (AI e provider mockati con monkeypatch, pattern esistente):
  - selezione file: presenti, filtri, skip dei revisionati, `redo`;
  - proposta diversa → `genre_review` creata; issue genre aperta esistente →
    riempita, nessun duplicato;
  - proposta uguale → conferma, `genre_review` aperta chiusa;
  - `None` → unresolved; fix manuali accettati intoccati;
  - `genre_reviewed_at` aggiornato, commit per-batch.
- **Adapter**: `genre_candidates` estratti da payload MB/Discogs finti.
- **Router**: start/status/preview, `configured: false` senza chiave, job già
  in corso → snapshot senza doppio avvio.
- **Rimozione**: nessun riferimento residuo a `ai-suggest-genre` /
  `suggest_genres` in backend, frontend, i18n.

Suite completa: `backend/.venv/bin/python -m pytest backend/tests -q`
(`filterwarnings = error`).
