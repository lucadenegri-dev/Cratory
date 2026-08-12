# DjOrganizer — "Risolvi con AI": suggerimenti artist/title da nome file

> Data: 2026-06-28 · Stato: design approvato, pronto per il plan.
> Estensione opzionale sull'app completa (backend 1-4 + frontend 6a/6b/6c in `main`).

## 1. Contesto

Dopo lo scan, la causa numero uno di **errori** sono i `missing_required_tag` (artista o
titolo mancante): nel dato reale dell'utente, 104 errori su 72 file. Quasi sempre l'artista
e il titolo **sono già nel nome del file** (`Artista - Titolo.ext`), ma una regex inciampa
sui casi sporchi (prefissi numero traccia, separatori multipli, `(Original Mix)`, `_Final`).
Un LLM economico li estrae bene. Questa feature aggiunge un'azione **on-demand** che usa
**Claude Haiku 4.5** per ricavare artist/title dai nomi file e proporli come correzioni.

## 2. Scope

**Dentro:**
- Azione **"Risolvi con AI"** nella pagina ISSUES: per le issue *artista/titolo mancante*,
  l'AI ricava il valore dal **nome file** e lo mette nel `suggested_fix` della issue (status
  resta `open`).
- Backend: dipendenza `anthropic`, endpoint `POST /api/issues/ai-suggest`, servizio
  `ai_tags` (mockabile nei test).
- L'AI è un **riempitore di suggerimenti**: riusa il campo inline e il `✓ accetta` esistenti
  di ISSUES (→ `/fix` → PLAN → apply → undo). Nessun nuovo percorso d'accettazione.

**Fuori:**
- Genere / anno / label (l'AI li tirerebbe a memoria → allucinazioni; un anno/label sbagliati
  sono peggio di un campo vuoto).
- Modelli locali (Ollama). Scrittura su disco. Auto-accettazione (l'utente rivede sempre).
- Esecuzione automatica durante lo scan (è sempre on-demand, esplicita).

## 3. Design (approvato)

### Modello "riempitore di suggerimenti"
L'AI non scrive né accetta nulla d'autorità. Per ogni issue `missing_required_tag` (campo
`artist` o `title`) imposta `suggested_fix_json = {"field": <field>, "action": "retag",
"to": <valore AI>}` lasciando `status = "open"`. In ISSUES il campo inline si **pre-riempie**
con la proposta (la UI 6b legge `suggested_fix_json.to`); l'utente rivede, eventualmente
corregge, e accetta col `✓` esistente → `fixIssue` → PLAN.

### Flusso
```
ISSUES "✨ Risolvi con AI"
  → POST /api/issues/ai-suggest
      → seleziona le issue open missing_required_tag (field artist|title) senza suggested_fix
      → raggruppa per file; manda i NOMI FILE a Haiku (batch, structured output)
      → per ogni issue setta suggested_fix_json al valore AID del suo campo (status resta open)
      → ritorna { configured, files, suggested, unresolved }
  → la pagina ricarica: i campi inline mostrano i valori AI
  → l'utente accetta col ✓ (→ /fix → PLAN → apply → undo)
```

### Backend
- **Dipendenza:** `anthropic` (SDK ufficiale Python) in `requirements`.
- **Config:** `ANTHROPIC_API_KEY` da variabile d'ambiente (default dell'SDK). Modello
  `claude-haiku-4-5`. Se la key non è impostata, l'endpoint non chiama l'API e ritorna
  `{"configured": false, ...}` (nessun crash).
- **Servizio `app/services/ai_tags.py`:** funzione `suggest(filenames: list[str]) ->
  list[dict]` che, data una lista di nomi file (stem, senza estensione), chiama Haiku con
  **structured output** (schema Pydantic `{"items": [{"artist": str|None, "title": str|None}]}`
  preservando l'ordine) e ritorna le coppie. Chunk da ~80 nomi per chiamata. Prompt:
  estrai artista e titolo da ciascun nome file di traccia musicale (di solito
  "Artista - Titolo"), gestendo prefissi numero traccia e suffissi come "(Original Mix)";
  ritorna `null` per un campo se non determinabile. La funzione è **mockabile**: i test
  pytest monkeypatchano `ai_tags.suggest` e non toccano la rete.
- **Endpoint sottile `POST /api/issues/ai-suggest`** (in `routers/issues.py`):
  - se `ANTHROPIC_API_KEY` assente → `{"configured": false, "files": 0, "suggested": 0,
    "unresolved": 0}`.
  - altrimenti: prende le issue `open` di tipo `missing_required_tag` con `field ∈
    {artist, title}` e `suggested_fix_json is None`; raggruppa per `file_id`; chiama
    `ai_tags.suggest` con i nomi file; per ogni issue, se l'AI ha prodotto un valore non
    vuoto per il suo campo, imposta `suggested_fix_json = {"field", "action":"retag",
    "to":value}` + `updated_at`; commit. Ritorna `{configured:true, files, suggested,
    unresolved}` (`unresolved` = issue per cui l'AI non ha dato un valore).
- **Privacy/costo:** manda **solo i nomi file** (stem), non l'audio. ~1 cent per la
  libreria dell'utente. On-demand.

### Frontend
- **`lib/api.ts`:** `aiSuggestTags()` → `POST /api/issues/ai-suggest` → `{ configured,
  files, suggested, unresolved }`.
- **Pagina ISSUES:** bottone **"✨ Risolvi con AI"** nella marginalia (accanto ai bulk).
  Click → busy → `aiSuggestTags()`:
  - `configured === false` → `Alert` "Imposta `ANTHROPIC_API_KEY` nel backend per usare l'AI".
  - successo → ricarica le issue (i campi inline si pre-riempiono) + messaggio "N suggerimenti
    pronti, rivedi e accetta" (`unresolved` mostrato se > 0).
  - errore → `Alert` con il messaggio (try/catch, come le altre azioni).

## 4. Errori, edge case, resilienza

- **Key assente:** gestita come stato esplicito (`configured:false`), niente eccezioni.
- **AI non determina un campo:** quella issue resta senza suggerimento (input vuoto,
  fix manuale come prima); conteggiata in `unresolved`.
- **File con solo un campo mancante:** si imposta solo l'issue del campo mancante (l'AID
  per l'altro campo si ignora).
- **Errore API/rete:** l'endpoint propaga un errore gestito; la UI mostra un `Alert`.
- **Idempotente per ri-esecuzione:** salta le issue che hanno già un `suggested_fix`.
- **Libreria grande:** chunk da ~80 per chiamata; l'endpoint resta sincrono (per decine/
  centinaia di file è questione di pochi secondi). Se in futuro servisse, può diventare un job.

## 5. Test

- **Backend (pytest):** `ai_tags.suggest` **mockato** (monkeypatch) — nessuna chiamata
  reale. Test: l'endpoint imposta i `suggested_fix` giusti sulle issue artist/title;
  rispetta `status=open`; salta quelle già con suggerimento; gestione `configured:false`
  quando manca la key; `unresolved` corretto. Output pristine.
- **Frontend:** `npm run lint` + `npm run build` verdi. Verifica live (best-effort): con
  `ANTHROPIC_API_KEY` impostata e issue artist/title aperte, "Risolvi con AI" pre-riempie i
  campi e l'accettazione confluisce nel PLAN.

## 6. Convenzioni & DoD

- Backend: router sottile, servizio isolato e mockabile, Pydantic, test pristine
  (`filterwarnings = error`). Frontend: pattern 6a/6b (client tipizzato, `useJobs` non
  necessario qui, `Alert`, try/catch).
- **DoD:** `pytest` verde (col mock AI), `npm run lint`+`build` verdi. Con la key impostata,
  "Risolvi con AI" in ISSUES pre-riempie artist/title dai nomi file; le proposte si
  rivedono e accettano col flusso esistente → PLAN; senza key, messaggio chiaro e nessun
  crash; non vengono toccati genere/anno/label né scritto nulla su disco.
