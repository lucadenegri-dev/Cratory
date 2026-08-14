# DjOrganizer — "Suggerisci generi (AI)": genere da artista+titolo

> Data: 2026-06-28 · Stato: design approvato, pronto per il plan.
> Estensione della feature AI esistente ([[ai-tag-suggestions]]). App in `main` @ `227bcfe`.

## 1. Contesto

Nella libreria reale **100 tracce sono senza genere** (issue `missing_metadata` / campo
`genre`, severità *warning*, stato *open*). Sono poco visibili in ISSUES (sepolte tra 390
`missing_metadata`), ma il **PLAN** le segnala come conflitti `missing_template_data`
("campo mancante per il template: genre"): il folder template di default è
**`{genre}/{artist}`**, quindi senza genere il planner **salta lo spostamento** del file.
L'utente fa molta fatica a mettere il genere a mano. Questa feature aggiunge un'azione
on-demand che usa **Claude Haiku** per proporre un genere a partire da **artista + titolo**.

## 2. Scope

**Dentro:**
- Secondo bottone in ISSUES, **"✨ Suggerisci generi"**, accanto a "Risolvi con AI".
- L'AI propone **un genere a bassa confidenza** che finisce nel `suggested_fix` della issue
  genere (status resta `open`); l'utente rivede il campo inline e accetta col `✓` → `/fix`
  → PLAN. Riusa il percorso d'accettazione esistente (genere è già in `_RETAGGABLE`).
- Segnale dato ad Haiku: **artista + titolo effettivi** (tag del file, oppure i
  `suggested_fix` di artista/titolo ottenuti dalla feature precedente, oppure in ultima
  istanza il nome file). Vocabolario **libero ma normalizzato** (un solo genere, casing
  pulito).
- Backend: funzione `ai_tags.suggest_genres()` + endpoint `POST /api/issues/ai-suggest-genre`.

**Fuori:**
- Anno / label (l'AI li tira a memoria → dannosi se sbagliati).
- Più generi per traccia / blob (cartelle pulite = un genere principale).
- Lista canonica fissa (scelta: libero ma normalizzato).
- Scrittura su disco, auto-accettazione, esecuzione automatica nello scan.

## 3. Design (approvato)

### Descrizione effettiva per file
Per dare ad Haiku il miglior contesto, l'endpoint costruisce per ogni file una stringa:
1. se artista **e** titolo sono noti → `"<artista> - <titolo>"`;
2. altrimenti se ne è noto uno → quello;
3. altrimenti → lo **stem del nome file**.

"Noto" = valore nel tag del file (`AudioFile.artist`/`title`) **oppure**, se il tag è vuoto,
il `to` del `suggested_fix_json` della issue artista/titolo *aperta o accettata* dello stesso
file (così i suggerimenti appena ottenuti contano anche se non ancora applicati al file).

### Servizio
`ai_tags.suggest_genres(descriptions: list[str]) -> list[str | None]` — data una lista di
descrizioni traccia, chiama Haiku con **structured output** (Pydantic
`{"items": [{"genre": str | None}]}`, ordine preservato) e ritorna un genere per descrizione.
Chunk ~80. Import `anthropic` **lazy**. Prompt: «dato artista e titolo, restituisci il
**genere principale più probabile**, normalizzato (musica elettronica/DJ; un solo genere, non
una lista; casing canonico tipo "Tech House"); `null` se non sei ragionevolmente sicuro; non
inventare valori spazzatura». Mockabile nei test.

### Endpoint `POST /api/issues/ai-suggest-genre`
- se `ANTHROPIC_API_KEY` assente → `{"configured": false, "files": 0, "suggested": 0,
  "unresolved": 0}`.
- altrimenti: seleziona le issue `open`, `type == "missing_metadata"`, `field == "genre"`,
  con `suggested_fix_json is None` (filtro JSON-null **in Python**, come da convenzione). Se
  vuoto → `{configured:true, files:0, ...}`.
- raccoglie i `file_id` coinvolti, carica le issue `artist`/`title` di quei file per ricavare
  i valori effettivi, costruisce la descrizione per file, chiama `ai_tags.suggest_genres`.
- per ogni issue genere, se l'AI ha prodotto un genere non vuoto → `suggested_fix_json =
  {"field": "genre", "action": "retag", "to": genre}` + `updated_at` (status resta `open`),
  `suggested += 1`; altrimenti `unresolved += 1`. Commit.
- ritorna `{configured: true, files, suggested, unresolved}`.

### Frontend
- `lib/api.ts`: `aiSuggestGenres()` → `POST /api/issues/ai-suggest-genre` → riusa
  `AiSuggestResult` (`{configured, files, suggested, unresolved}`).
- Pagina ISSUES: secondo bottone **"✨ Suggerisci generi"** nella marginalia (stato `busy`
  proprio). Click → `aiSuggestGenres()`:
  - `configured === false` → Alert "Imposta ANTHROPIC_API_KEY nel backend per usare l'AI".
  - successo → ricarica le issue (i campi genere si pre-riempiono) + nota es. *"42 generi
    suggeriti (bassa confidenza, rivedi), 8 non ricavabili"* (riusa lo stato `aiNote`).
  - errore → Alert (try/catch).

## 4. Errori, edge case, resilienza

- **Key assente:** `configured:false`, nessuna eccezione.
- **AI ritorna null:** issue senza suggerimento (fix manuale come prima), conteggiata in
  `unresolved`.
- **Artista/titolo entrambi ignoti:** descrizione = nome file (fallback).
- **Idempotente:** salta le issue genere che hanno già un `suggested_fix`.
- **Errore API/rete:** propagato e mostrato come Alert.
- **Bassa confidenza esplicita:** il testo del bottone e della nota chiariscono che sono
  ipotesi da rivedere.

## 5. Test

- **Backend (pytest):** `ai_tags.suggest_genres` **mockato**. Test: l'endpoint imposta i
  `suggested_fix` sulle issue genere; costruisce la descrizione usando il `suggested_fix` di
  artista/titolo quando i tag del file sono vuoti; `status` resta `open`; salta le issue già
  suggerite; `configured:false` senza key; `unresolved` corretto. Output pristine.
- **Frontend:** `npm run lint` + `npm run build` verdi.

## 6. Convenzioni & DoD

- Backend: router sottile, servizio isolato/mockabile, Pydantic, test pristine
  (`filterwarnings = error`), JSON-null filtrato in Python.
- **DoD:** `pytest` verde (Haiku mockato); lint+build verdi. Con la key, "Suggerisci generi"
  pre-riempie il genere delle issue `missing_metadata`/`genre` usando artista+titolo; le
  proposte si rivedono e accettano col flusso esistente → PLAN (e sbloccano lo spostamento);
  senza key, Alert e nessun crash; non vengono toccati anno/label né scritto su disco.
