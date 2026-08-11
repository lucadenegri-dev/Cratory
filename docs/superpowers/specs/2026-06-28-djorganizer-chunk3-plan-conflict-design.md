# DjOrganizer — Chunk 3: Plan + Conflict

> Data: 2026-06-28 · Stato: design approvato, pronto per il plan.
> Terzo sub-progetto. Spec madre:
> [2026-06-27-djorganizer-design.md](2026-06-27-djorganizer-design.md) ·
> Chunk 1: [scanner](2026-06-27-djorganizer-chunk1-scanner-design.md) ·
> Chunk 2: [inspector-dedup](2026-06-27-djorganizer-chunk2-inspector-dedup-design.md).

## 1. Contesto

Chunk 1 (Scanner) e 2 (Inspector + Dedup) sono completi e in `main`. Esistono righe
`audio_file`, `issue` (con `status` open/accepted/dismissed) e `dup_group`/`dup_member`
(con `action` keep/remove). Vedi il "Contratto per il chunk 3" nella spec del chunk 2:
gli issue `accepted` e le azioni dedup sono una **coda di lavoro pendente** che questo
chunk trasforma in un piano.

Questo è il **chunk 3**: due stage **puri** che producono e validano un *piano* di
operazioni, più la tabella `settings` (i template, introdotti qui).

- **Plan** — calcola le operazioni (RETAG/RENAME/MOVE/DELETE) da fare, con diff
  prima→dopo.
- **Conflict** — valida il piano (collisioni, dati mancanti, destinazioni fuori radice).

**Nessuna mutazione dei file** in questo chunk: il piano è un *progetto* di modifiche;
l'esecuzione è il chunk 4 (Apply). Stage successivi: 4 Apply+Undo, 5 Bridge, 6 Frontend.

## 2. Scope

**Dentro:** `services/planner.py` + `services/conflict.py` (puri), orchestratore
`services/planning.py` (scrive il piano nel DB), tabella `settings` + colonna
`scan_root.target_root`, tabelle `plan`/`plan_op`, router `settings` e `plan`, suite
pytest.

**Fuori:** Apply/Undo (esecuzione + quarantena + undo_journal), Bridge, frontend. Il
Plan **non** tocca i file; produce solo `plan_op` con `before`/`after`.

## 3. Decisioni chiave (approvate)

1. **Template globali, default** `naming_template = "{artist} - {title}"`,
   `folder_template = "{genre}/{artist}"`. Configurabili in SETTINGS. `folder_template`
   vuoto → niente sottocartelle (piatto sotto la radice target).
2. **La rinomina/spostamento riguarda *tutti* i file tenuti**, non solo quelli con un
   issue: il piano riorganizza l'intera libreria sui template.
3. **`target_root` per-radice** (colonna su `scan_root`), **default = in-place** (la
   radice stessa). Ogni file si riorganizza dentro la `target_root` della *sua* radice →
   niente spostamenti cross-disco a sorpresa, nessun path personale nel codice.
   Configurabile in SETTINGS (es. radice interna → `/Users/.../Music/Library`).
4. **Ordine sicuro** del piano (come l'Apply): RETAG → RENAME/MOVE → DELETE.
5. **Plan puro/deterministico**, validato Pydantic. **Conflict puro**, blocca l'Apply.

## 4. Struttura file

```text
backend/app/
  db.py                  # MODIFICA: ensure_schema ALTER per scan_root.target_root
  models.py              # MODIFICA: Settings, Plan, PlanOp; scan_root.target_root
  schemas.py             # MODIFICA: SettingsRead/Update, RootTargetUpdate, PlanRead, PlanOpRead, ConflictRead, PlanStats
  services/
    planner.py           # NEW — build_plan(...) -> list[PlanOpComputed] (puro) + render/sanitize template
    conflict.py          # NEW — check(...) -> list[ConflictComputed] (puro)
    planning.py          # NEW — orchestratore: get/seed/update settings; create_plan; load_plan (+ conflitti + stats)
  routers/
    settings.py          # NEW — GET/PUT /api/settings, PUT /api/settings/roots/{id}/target
    plan.py              # NEW — POST /api/plan, GET /api/plan
  main.py                # MODIFICA: include settings, plan
backend/tests/
  test_planner.py · test_conflict.py · test_planning.py · test_settings_api.py · test_plan_api.py
```

`planner` e `conflict` sono puri (ricevono righe/oggetti, ritornano strutture). `planning`
fa da orchestratore impuro (legge audio_file/issue/dup, snapshot settings, scrive
plan/plan_op, calcola conflitti+stats). Router sottili.

## 5. Data model

Pattern chunk 1: `ensure_schema()` crea le tabelle nuove; per la **colonna aggiunta**
`scan_root.target_root` si estende `ensure_schema` con un `ALTER TABLE … ADD COLUMN` se
mancante (gli `audio_file`/`scan_root` esistenti sopravvivono).

**`scan_root` (modifica)** — nuova colonna `target_root` (str, nullable). `null` →
in-place (= `scan_root.path`).

**`settings`** (riga singola, `id=1`, seed al primo accesso):

| Campo | Tipo | Note |
|---|---|---|
| `id` | int PK | sempre 1 |
| `naming_template` | str | default `"{artist} - {title}"` |
| `folder_template` | str | default `"{genre}/{artist}"`; `""` = piatto |
| `dedup_keep_rules_json` | JSON, nullable | riservato (regole keeper override) |
| `cratory_base_url` | str, nullable | riservato (chunk 5) |
| `created_at` / `updated_at` | datetime | |

**`plan`**:

| Campo | Tipo | Note |
|---|---|---|
| `id` | int PK | |
| `created_at` | datetime | |
| `status` | str | `draft` \| `applied` \| `undone` (chunk 3 crea solo `draft`) |
| `rules_json` | JSON | snapshot `{naming_template, folder_template, targets:{root_id:path}}` |

**`plan_op`** (cascade delete dal plan):

| Campo | Tipo | Note |
|---|---|---|
| `id` | int PK | |
| `plan_id` | FK → plan.id, indexed | |
| `seq` | int | ordine globale (rispetta RETAG→RENAME/MOVE→DELETE) |
| `kind` | str | `RETAG` \| `RENAME` \| `MOVE` \| `DELETE` |
| `file_id` | FK → audio_file.id, indexed | |
| `before_json` | JSON | stato prima |
| `after_json` | JSON | stato dopo |
| `status` | str | `pending` (chunk 3); l'Apply lo aggiorna |

## 6. Plan (`services/planner.py`, puro)

`build_plan(files, accepted_issues, removals, settings_snapshot, root_targets) ->
list[PlanOpComputed]`, dove:
- `files`: gli `audio_file` `status='present'` e **senza `scan_error`** (i corrotti non si
  riorganizzano: vanno risolti/rimossi prima — restano fuori dal piano).
- `accepted_issues`: gli `issue` `status='accepted'` con `suggested_fix_json` (per file).
- `removals`: i `file_id` con `dup_member.action == 'remove'`.
- `settings_snapshot`: `{naming_template, folder_template}`.
- `root_targets`: `{root_id: target_root}` (default = path della radice).

`PlanOpComputed` (dataclass frozen): `kind, file_id, before, after` (dict). L'orchestratore
assegna `seq`/`plan_id`.

**Generazione (in ordine):**

1. **RETAG** (per ogni file con issue accettati): aggrega i `suggested_fix` del file in un
   solo op. `before = {field: valore_attuale, …}`, `after = {field: valore_nuovo|null, …}`
   (`action:"clear"` → null; `action:"retag"` → `to`).
2. **Tag effettivi**: applica i retag accettati in memoria (copia dei campi del file).
3. **RENAME/MOVE** (per ogni file *tenuto*, cioè non in `removals`): renderizza la
   destinazione `<target_root>/{folder_template}/{naming_template}.{ext}` dai **tag
   effettivi**, con sanitizzazione (vedi sotto). Confronto col path attuale:
   - destinazione == attuale → nessun op;
   - stessa cartella, basename diverso → **RENAME**;
   - cartella diversa → **MOVE** (porta anche il nuovo nome).
   `before = {path: attuale}`, `after = {path: destinazione}`. Se un campo richiesto dal
   template manca nei tag effettivi → **nessun op** per quel file (il Conflict lo segnala,
   §7).
4. **DELETE** (per ogni `file_id` in `removals`): `before = {path}`, `after = {}`. I file
   rimossi **non** ricevono RENAME/MOVE.

`seq` cresce nell'ordine RETAG → RENAME/MOVE → DELETE; dentro ogni gruppo, ordine
deterministico per `path` poi `file_id`.

**Sanitizzazione dei valori nel path:** ogni campo renderizzato nel path
(`{artist}`, `{title}`, `{genre}`, …) è sanitizzato: separatori (`/`, `\`) e caratteri
riservati (`:*?"<>|`) → `_`; `..` neutralizzato; spazi/punti iniziali e finali rimossi.
Evita che un tag tipo `AC/DC` crei sottocartelle o un `..` esca dalla radice.

## 7. Conflict (`services/conflict.py`, puro)

`check(plan_ops, files_by_id, root_targets, settings_snapshot) -> list[ConflictComputed]`
(`root_targets` = `{root_id: target_root}`). `ConflictComputed`: `kind, file_id, detail`.
Tipi:

- **`collision`**: due op (RENAME/MOVE) producono la **stessa destinazione**; oppure una
  destinazione coincide col path attuale di un file *presente che non viene spostato*
  (sovrascrittura). "Mai sovrascrivere" → bloccante.
- **`missing_template_data`**: un file tenuto non-rimosso ha, nei tag effettivi, un campo
  richiesto dal template **vuoto** → destinazione non renderizzabile → bloccante.
- **`outside_root`**: una destinazione non è sotto la `target_root` della **radice del
  file** (`root_targets[file.root_id]`) → bloccante. (Backstop oltre la sanitizzazione.)

I conflitti bloccanti impediscono l'Apply (chunk 4). Il Conflict è ricalcolabile a ogni
`GET /api/plan` sui `plan_op` persistiti + i dati file correnti.

## 8. Orchestratore + endpoint

`services/planning.py`:
- `get_settings(db)` (seed con i default se assente) · `update_settings(db, ...)` ·
  `set_root_target(db, root_id, target_root)`.
- `create_plan(db) -> PlanRead`: legge i file/issue/removals, snapshot settings+targets,
  chiama `build_plan`, **sostituisce** il `draft` esistente (cascade delete dei suoi
  `plan_op`), persiste plan+plan_op, ritorna il piano con conflitti+stats.
- `load_plan(db) -> PlanRead | None`: il `draft` corrente con conflitti (ricalcolati) +
  stats.

`PlanStats`: `n_retag, n_rename, n_move, n_delete, space_freed_bytes` (somma `size_bytes`
dei file in DELETE), `n_conflicts`, `blocking` (bool).

**Endpoint** (router sottili):
- `GET /api/settings` → `{naming_template, folder_template, roots:[{id,path,label,target_root}]}`.
- `PUT /api/settings` → `{naming_template, folder_template}`.
- `PUT /api/settings/roots/{root_id}/target` → `{target_root: str|null}` (path assoluto;
  `null` = in-place; non serve che esista ancora).
- `POST /api/plan` → costruisce un draft fresco + ritorna piano (ops + conflitti + stats).
- `GET /api/plan` → il draft corrente (ops + conflitti + stats) o 404 se assente.

## 9. Errori e casi limite

- File con `scan_error` → esclusi dal piano (corrotti; si risolvono/rimuovono prima).
- File con `dup_member.action == 'remove'` → solo DELETE, mai RENAME/MOVE.
- Template che richiede un campo mancante → niente op di rinomina per quel file +
  conflitto `missing_template_data` (così è visibile, non silenzioso).
- Due file diversi che renderizzano alla stessa destinazione (anche non doppioni) →
  `collision`, bloccante (mai overwrite).
- `set_root_target` con path non assoluto → 400.
- Determinismo: stesso stato → stesso piano (stessi `seq`, stesse ops).

## 10. Test (pytest)

- **`test_planner.py`:** RETAG da issue accettati (aggregazione multi-campo); tag
  effettivi usati nella rinomina (retag artist → nuovo nome usa il valore corretto);
  RENAME vs MOVE secondo cartella; DELETE per i removals (e niente rinomina sui rimossi);
  sanitizzazione (`AC/DC` → `AC_DC`, niente `..`); campo template mancante → nessun op;
  ordine `seq` RETAG→RENAME/MOVE→DELETE; determinismo.
- **`test_conflict.py`:** collisione (due destinazioni uguali; destinazione = file
  esistente non spostato); `missing_template_data`; `outside_root`; piano pulito → nessun
  conflitto.
- **`test_planning.py`:** seed settings default; update settings; set_root_target;
  `create_plan` persiste plan+plan_op e sostituisce il draft precedente; stats corrette
  (conteggi + space_freed); conflitti ricalcolati su `load_plan`.
- **`test_settings_api.py` / `test_plan_api.py`:** TestClient — get/put settings, set
  target (+ 400 path non assoluto), POST/GET plan end-to-end (scan fixtures → accept un
  issue + dedup → plan mostra le ops attese).

Output pristine (`filterwarnings = error`).

## 11. Convenzioni (dai chunk 1–2)

SQLAlchemy 2.0, no Alembic (`create_all` + `ensure_schema` con ALTER per colonne nuove),
Pydantic v2, router sottili, motore deterministico, `utcnow()` tz-aware. Comandi:
`cd backend && source .venv/bin/activate && python -m pytest tests`.

## 12. Definition of Done (chunk 3)

- `pytest tests` verde e pristine, inclusi i test di tag-effettivi-nella-rinomina,
  sanitizzazione, collisione e missing-data.
- Con una libreria scansionata + qualche issue accettato + scelte dedup: `POST /api/plan`
  produce un draft con RETAG/RENAME/MOVE/DELETE coerenti e diff prima→dopo; `GET /api/plan`
  mostra ops + conflitti + stats; le destinazioni restano sotto la `target_root` di ogni
  radice.
- SETTINGS gestisce template globali e `target_root` per-radice.
