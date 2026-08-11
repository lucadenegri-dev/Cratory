# DjOrganizer — Chunk 6c: PLAN + HISTORY + SETTINGS

> Data: 2026-06-28 · Stato: design approvato (mockup validati), pronto per il plan.
> Terzo e ultimo sub-chunk del Frontend (6a · 6b · 6c). Spec madre:
> [2026-06-27-djorganizer-design.md](2026-06-27-djorganizer-design.md) · precedenti:
> [6a](2026-06-28-djorganizer-chunk6a-frontend-foundation-design.md) ·
> [6b](2026-06-28-djorganizer-chunk6b-issues-duplicates-design.md).

## 1. Contesto

Backend (chunk 1-4) + frontend 6a (SOURCES, FILES) + 6b (ISSUES, DUPLICATES) sono in
`main`. Il backend ha **già tutti** gli endpoint che servono: `plan` (costruisce/legge il
draft), `apply` (job di applicazione con giornale di undo + quarantena per i delete),
`history` (run + undo), `settings` (template + `target_root` per radice). Quindi **questo
sub-chunk è solo frontend** — nessuna aggiunta backend.

| # | Sub-chunk | Pagine |
|---|---|---|
| 6a | Fondazione + SOURCES + FILES | ✅ |
| 6b | ISSUES + DUPLICATES | ✅ |
| **6c** | **PLAN + HISTORY + SETTINGS** | piano+apply, storico+undo, impostazioni |

Con il 6c il giro si chiude: **SOURCES → FILES → ISSUES → DUPLICATES → PLAN → apply →
HISTORY**.

## 2. Scope

**Dentro (tutto frontend):**
- Pagina **PLAN**: costruisci/ricostruisci il piano, anteprima operazioni raggruppate per
  tipo, conflitti, statistiche, **Applica** con modale di conferma → job di apply con
  progresso.
- Pagina **HISTORY**: run applicate/annullate, **annulla** (undo) sulle applicate.
- Pagina **SETTINGS**: template naming/cartelle con anteprima live + `target_root` per radice.
- Client API (`lib/api.ts`): tipi + funzioni per plan/apply/history/settings.
- **jobs-provider** esteso: oltre allo scan, fa polling anche del job di **apply**
  (estensione retro-compatibile).

**Fuori:** nessuna aggiunta backend. Nessuna nuova feature oltre il completamento delle 3
pagine placeholder.

## 3. Design (validato coi mockup)

Estetica 6a/6b (editorial, dark/paper, shell a 3 colonne, marginalia, token `--c-ok`/`--c-warning`).

### PLAN
- **Costruzione**: al load `GET /api/plan` carica il draft esistente; se 404 → stato "nessun
  piano, costruiscilo". Bottone **↻ ricostruisci** → `POST /api/plan` (ricalcola dalle
  decisioni correnti di ISSUES/DUPLICATES + SETTINGS).
- **Operazioni raggruppate per tipo** — sezioni Retag / Rinomina / Sposta / Elimina, ogni op
  con before→after (`PlanOpRead`: kind, file_path, before, after). I DELETE (doppioni)
  evidenziati, destinazione "quarantena".
- **Conflitti**: se `stats.blocking`, banner rosso in cima che elenca i conflitti
  (`ConflictRead`: kind, file_id, detail) e **Applica disabilitato** finché non risolvi
  (tornando in ISSUES/DUPLICATES/SETTINGS e ricostruendo).
- **Marginalia**: statistiche (`PlanStats`: n_retag/n_rename/n_move/n_delete,
  space_freed_bytes, n_conflicts) + bottone **Applica**.
- **Apply (l'utente ha scelto: conferma con riepilogo)**: click su Applica → **modale**
  (`ui.tsx` `Modal`) che riepiloga (12 retag, 5 sposta, 3 elimina, ~40 MB) + rassicura
  ("tutto annullabile da HISTORY, gli eliminati vanno in quarantena"). Conferma →
  `POST /api/apply` → job di apply con barra di progresso (EqMeter via jobs-provider).
- **Post-apply**: a job `done`, mostra il risultato (`ApplyResult`: applied_ops, e se
  `partial` il `failed_op_seq`, oppure `error`); il piano non è più draft → invita a
  ricostruire e rimanda a HISTORY. Conteggi nav/marginalia aggiornati.

### HISTORY
- `GET /api/history` → tabella run (newest first): `#id · quando · n operazioni · stato`
  (applicata/annullata). Le **applicate** hanno **↺ annulla** → `POST /api/history/{id}/undo`
  (`UndoResult`: reversed_ops) che ripristina dalla quarantena e rimette tag/percorsi; dopo
  l'undo la run diventa "annullata" e resta come storico (nessuna riapplicazione).
- Ricarica quando un apply finisce (compare la nuova run).

### SETTINGS
- `GET /api/settings` → `{naming_template, folder_template, roots[{id, path, label,
  target_root}]}`.
- **Template** nome file (`{artist} - {title}`) e cartelle (`{genre}/{artist}`) con
  **anteprima live** (sostituzione client-side di valori d'esempio — approssimata; la resa
  reale con sanitizzazione è lato planner). Salva → `PUT /api/settings`.
- **Target per radice**: tabella radici con `target_root` editabile per ognuna (vuoto =
  organizza nella stessa cartella del file; un path assoluto sposta là i file di quella
  radice). Salva per riga → `PUT /api/settings/roots/{id}/target` (il backend valida
  path assoluto → 400 altrimenti).

## 4. Backend

**Nessuna modifica.** Endpoint consumati (già esistenti):
`POST/GET /api/plan` · `POST /api/apply` + `GET /api/apply/status` · `GET /api/history` +
`POST /api/history/{id}/undo` · `GET/PUT /api/settings` + `PUT /api/settings/roots/{id}/target`.
La suite backend resta verde/pristine, invariata.

## 5. Architettura frontend

```text
frontend/
  lib/api.ts                 # + tipi e funzioni plan/apply/history/settings
  components/
    jobs-provider.tsx        # + polling job apply (retro-compatibile)
    plan-ops.tsx             # sezioni operazioni raggruppate per tipo
    apply-modal.tsx          # modale di conferma apply
  app/
    plan/page.tsx            # PLAN (sostituisce il placeholder)
    history/page.tsx         # HISTORY (sostituisce il placeholder)
    settings/page.tsx        # SETTINGS (sostituisce il placeholder)
```

- **`lib/api.ts`** aggiunge:
  - tipi: `PlanOp` (id, seq, kind, file_id, file_path, before, after, status), `Conflict`
    (kind, file_id, detail), `PlanStats` (n_retag, n_rename, n_move, n_delete,
    space_freed_bytes, n_conflicts, blocking), `Plan` (id, status, created_at, rules, ops,
    conflicts, stats), `ApplyResult` (run_id, applied_ops, refused, stale, partial,
    failed_op_seq, error, reason, …), `ApplyJobState` (= shape di `ScanJobState`, `result:
    ApplyResult|null`), `HistoryItem` (id, status, created_at, n_ops), `RootTarget` (id,
    path, label, target_root), `Settings` (naming_template, folder_template, roots).
  - funzioni: `buildPlan()`→POST /api/plan, `getPlan()`→GET /api/plan, `startApply()`,
    `applyStatus()`, `listHistory()`, `undoRun(id)`, `getSettings()`,
    `updateSettings(body)`, `setRootTarget(rootId, target)`.
- **`jobs-provider`**: oltre a `scan`, fa polling di `applyStatus()` ed espone
  `{ scan, apply, startScan, startApply, refresh }`. La barra `GlobalProgress` in basso
  compare se **scan O apply** è in corso, con etichetta adeguata. I consumer esistenti che
  leggono `scan` restano invariati (estensione additiva). Scan e apply sono mutuamente
  esclusivi (il backend ritorna 409).
- **PLAN page** consuma `apply` dal provider per il progresso inline e reagisce ad
  `apply.status === "done"`; le altre due pagine usano l'API diretta. Tutte ricaricano su
  `scan.status === "done"` o `apply.status === "done"` dove rilevante.
- Ogni mutazione (build/apply/undo/save) ha **try/catch con feedback** `Alert` (lezione 6a).

## 6. Errori, stati vuoti, resilienza

- **Backend irraggiungibile**: `Alert` come 6a/6b.
- **Stati vuoti**: PLAN senza draft → invito a costruirlo; piano con 0 operazioni → "niente
  da applicare, accetta issue o scegli doppioni"; HISTORY vuota → "nessuna run"; SETTINGS
  sempre presente.
- **Apply rifiutato/parziale**: `ApplyResult` con `refused`/`stale`/`partial` mostrato
  chiaramente (es. "applicate 18/23, fermato all'op #19: <error>").
- **`target_root` non assoluto**: il backend torna 400; la riga SETTINGS mostra l'errore.

## 7. Test

Frontend: **`npm run lint` + `npm run build` verdi** (no unit test). Verifica live: con
libreria scansionata + decisioni prese, in PLAN costruisco il piano, lo applico (modale →
job → risultato), in HISTORY annullo una run, in SETTINGS cambio template/target e
ricostruisco il piano per vederne l'effetto. Backend invariato (suite resta verde).

## 8. Convenzioni

- Frontend: pattern di 6a/6b (client tipizzato, `useJobs`, `PageLayout`, `ui.tsx` incl.
  `Modal`, token `--c-*`). Comandi da `frontend/`.
- Nessuna modifica backend; non rompere la suite esistente.

## 9. Definition of Done (chunk 6c)

- `npm run lint` + `npm run build` verdi; `pytest` resta verde (backend invariato).
- Con backend avviato e libreria scansionata + decisioni prese: **PLAN** costruisce e mostra
  le operazioni raggruppate (con conflitti/stat), **Applica** apre il modale e poi esegue il
  job mostrando il risultato; **HISTORY** elenca le run e **annulla** una applicata;
  **SETTINGS** salva template (con anteprima) e `target_root` per radice, e ricostruendo il
  piano se ne vede l'effetto.
- Le 3 sezioni placeholder sono ora complete: l'app copre l'intero flusso end-to-end.
