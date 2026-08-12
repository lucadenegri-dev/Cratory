# DjOrganizer — Chunk 6b: ISSUES + DUPLICATES

> Data: 2026-06-28 · Stato: design approvato (mockup validati), pronto per il plan.
> Secondo dei tre sub-chunk del Frontend (6a · 6b · 6c). Spec madre:
> [2026-06-27-djorganizer-design.md](2026-06-27-djorganizer-design.md) · precedente:
> [chunk 6a](2026-06-28-djorganizer-chunk6a-frontend-foundation-design.md).

## 1. Contesto

Il backend (chunk 1-4) e la fondazione frontend + SOURCES + FILES (6a) sono in `main`.
Il backend ha **già** i router `issues` (lista filtrabile, cambio status singolo/blocco) e
`duplicates` (lista gruppi, scelta keeper, dismiss). Questo sub-chunk costruisce le due
pagine che li consumano, più **una** aggiunta backend per la correzione manuale.

| # | Sub-chunk | Pagine |
|---|---|---|
| 6a | Fondazione + SOURCES + FILES | ✅ fatto |
| **6b** | **ISSUES + DUPLICATES** | revisione issue (triage + fix manuale) + doppioni |
| 6c | PLAN + HISTORY + SETTINGS | piano/apply, storico/undo, impostazioni (incl. `target_root`) |

## 2. Scope

**Dentro:**
- Pagina **ISSUES**: lista filtrabile, triage (accetta/ignora/riapri, singolo + blocco) e
  **correzione manuale inline** (plan-routed).
- Pagina **DUPLICATES**: gruppi come card, scelta keeper, scarta/ripristina gruppo.
- Backend: **`POST /api/issues/{id}/fix`** (correzione manuale → accettata, confluisce nel
  PLAN) + `root_id` aggiunto a `IssueRead` (abilita il filtro per radice lato client).
- Client API (`lib/api.ts`): tipi + funzioni per issues e duplicates.
- Refresh dei conteggi in nav al cambio pagina (le azioni 6b cambiano i totali).

**Fuori:** PLAN/HISTORY/SETTINGS e l'applicazione vera delle modifiche (6c). In 6b si
**decide** soltanto (accetta/ignora/keeper/dismiss); l'apply su disco è il 6c. Niente
modifica tag immediata su disco.

## 3. Design (validato coi mockup)

Estetica 6a (editorial, dark/paper, shell a 3 colonne, monospace, marginalia).

### ISSUES
- **Lista filtrabile** (filtri: severità / tipo / stato / radice). Filtro **lato client**:
  la pagina carica tutte le issue una volta e filtra in memoria, così la marginalia mostra
  conteggi coerenti gratis (le issue sono un sottoinsieme modesto).
- Tabella densa: `! (sev ▲/●/·) · TIPO · TRACCIA (artista—titolo + path) · CAMPO ·
  CORREZIONE · AZIONI`.
- **Correzione inline** nella colonna CORREZIONE:
  - issue auto-fixabile (es. `inconsistent_casing`): input **pre-riempito** col valore
    suggerito (`suggested_fix_json.to`), modificabile.
  - issue con campo mancante (es. `missing_metadata` su `genre`): input **vuoto** con
    placeholder "scrivi il …".
  - issue **non correggibile a mano** (campo non è un tag effettivo, es. `bad_bitrate`):
    nessun input, solo *ignora*.
- **Azioni per riga** (mappatura endpoint esplicita):
  - `✓ accetta` (solo righe con input) → **`fixIssue(id, valore_input)`** (`POST .../fix`):
    imposta `suggested_fix` al valore mostrato (suggerito o modificato/manuale) e accetta.
    Unico percorso d'accettazione per riga, sempre plan-routed.
  - `✕ ignora` → `setIssueStatus(id, "dismissed")`.
  - `↺ riapri` (righe già accettate/ignorate) → `setIssueStatus(id, "open")`.
  - Stato mostrato come badge (`accettata` / `ignorata`).
- **Azioni in blocco nella marginalia** (non in cima):
  - "✓ accetta tutti i fixabili" → `bulkIssues({status: "accepted"})` (usa i suggerimenti
    esistenti; il backend salta i non-fixabili).
  - "✕ ignora tutti gli info" → `bulkIssues({severity: "info", status: "dismissed"})`.
- **Marginalia**: totale issue + breakdown per severità (err/warn/info) e per tipo;
  conteggio "accettate → andranno nel PLAN"; i due bottoni blocco.

### DUPLICATES
- **Una card per gruppo**. Header: `GRUPPO #id · match: <kind>` + azione "non è un
  doppione" (dismiss). Membri come righe: marker `KEEP` (verde, bordo) / `REMOVE` (muto),
  `path · FMT · KBPS · DUR · hash` per confronto a colpo d'occhio.
- **Scelta keeper**: clic su una riga `REMOVE` la elegge keeper (le altre diventano
  REMOVE). Il backend ha già scelto un keeper di default (qualità migliore).
- **Dismiss / ripristina**: "non è un doppione" scarta il gruppo (tutti `keep`); i gruppi
  scartati restano visibili in stato attenuato con `↺ ripristina`.
- **Marginalia**: numero gruppi, file da rimuovere (membri `remove` nei gruppi non
  scartati), breakdown per match-kind; nota "le rimozioni → andranno nel PLAN".

## 4. Aggiunta backend

### `POST /api/issues/{id}/fix` — correzione manuale (plan-routed)
- Body: `{ "value": str }`.
- 404 se la issue non esiste; **400** se `issue.field` non è un tag effettivo
  (`artist|title|album|album_artist|genre|year|label|track_no|comment`) — non correggibile
  a mano; 400 se `value` è vuoto.
- Effetto: `issue.suggested_fix_json = {"field": issue.field, "action": "retag", "to":
  value}` e `issue.status = "accepted"`, `updated_at = utcnow()`. La forma combacia con ciò
  che `planner.effective_tags` consuma (legge `field` + `action` + `to`; il `before` lo
  ricava dal file). Ritorna `IssueRead` aggiornato.
- Niente scrittura su disco: la modifica vera avviene quando il PLAN (6c) viene applicato,
  con il giornale di undo del chunk 4.

### `IssueRead` — aggiunge `root_id`
- `_to_read` popola `root_id=file.root_id`. Abilita il filtro per radice lato client. Tutti
  i campi esistenti invariati.

Entrambi coperti da test pytest (TestClient), stile dei test esistenti.

## 5. Architettura frontend

```text
frontend/
  lib/api.ts            # + tipi Issue, DupGroup, DupMember; + funzioni issues/duplicates
  app/
    issues/page.tsx     # ISSUES (sostituisce il placeholder)
    duplicates/page.tsx # DUPLICATES (sostituisce il placeholder)
  components/
    issues-table.tsx    # tabella densa + riga con correzione inline
    dup-group.tsx       # card di un gruppo doppioni
    index-nav.tsx       # + refresh conteggi al cambio pagina (modifica minima)
```

- **`lib/api.ts`** aggiunge:
  - tipi: `Issue` (id, file_id, root_id, type, field, severity, detail, suggested_fix_json,
    status, file_path, artist, title), `DupMember` (file_id, action, path, ext, bitrate,
    duration_s, content_hash), `DupGroup` (id, match_kind, keeper_file_id, keeper_overridden,
    dismissed, members).
  - funzioni: `listIssues(filters?)`, `setIssueStatus(id, status)`, `bulkIssues(body)`,
    `fixIssue(id, value)` → `POST /api/issues/{id}/fix`; `listDuplicates()`,
    `setKeeper(groupId, fileId)`, `dismissDuplicate(groupId)`.
- **ISSUES page**: carica tutte le issue (`listIssues()`), filtra lato client, deriva i
  conteggi marginalia; ogni azione (status/fix/bulk) chiama il backend e poi ricarica.
- **DUPLICATES page**: carica i gruppi (`listDuplicates()`), render card; keeper/dismiss
  chiamano il backend e aggiornano lo stato locale del gruppo.
- **index-nav**: oltre al refresh su `scan.status === "done"` (6a), ricarica i conteggi al
  cambio `pathname`, così i totali nav riflettono le azioni 6b appena cambi sezione.
- Entrambe ricaricano i dati su `scan.status === "done"` (come FILES in 6a).

## 6. Errori, stati vuoti, resilienza

- **Backend irraggiungibile**: `Alert` "backend non raggiungibile" (come 6a); azioni in
  errore mostrano l'errore senza far crashare la UI (lezione 6a: niente errori silenziosi —
  ogni mutazione ha try/catch con feedback).
- **Stati vuoti**: nessuna issue → "Nessuna issue, la libreria è pulita"; nessun doppione →
  "Nessun doppione".
- **`accetta` non valido**: il backend rifiuta `accepted` su issue non auto-fixabili (400);
  la UI non offre `✓ accetta` dove non ha senso (solo *ignora*).

## 7. Test

Frontend: **`npm run lint` + `npm run build`** verdi (no unit test). Verifica live: con
backend + libreria scansionata, ISSUES filtra/accetta/ignora/corregge-a-mano e DUPLICATES
cambia keeper/scarta; i conteggi nav e marginalia si aggiornano. I due cambi backend
(`/fix`, `root_id`) hanno test pytest.

## 8. Convenzioni

- Frontend: pattern di 6a (client tipizzato, `useJobs`, `PageLayout`, `ui.tsx`, token
  `--c-*` incl. `--c-warning`). Comandi da `frontend/`.
- Backend: router sottili, Pydantic, SQLAlchemy 2.0, test pristine (`filterwarnings = error`).

## 9. Definition of Done (chunk 6b)

- `npm run lint` + `npm run build` verdi; `pytest` verde (coi nuovi test backend).
- Con backend avviato e libreria scansionata: in **ISSUES** filtro per severità/tipo/stato/
  radice, accetto un auto-fix, correggo a mano un campo mancante (diventa "accettata"),
  ignoro un info, uso le azioni in blocco dalla marginalia; in **DUPLICATES** vedo i gruppi
  come card, cambio il keeper con un clic, scarto e ripristino un gruppo; i conteggi
  (marginalia + nav) si aggiornano.
- Le accettate/rimozioni sono pronte per il PLAN (6c); nessuna scrittura su disco in 6b.
