# DjOrganizer — Chunk 4: Apply + Undo

> Data: 2026-06-28 · Stato: design approvato, pronto per il plan.
> Quarto sub-progetto (alto rischio: muta il filesystem). Spec madre:
> [2026-06-27-djorganizer-design.md](2026-06-27-djorganizer-design.md) ·
> Chunk 3: [plan-conflict](2026-06-28-djorganizer-chunk3-plan-conflict-design.md).

## 1. Contesto

Chunk 1-3 (Scanner, Inspector+Dedup, Plan+Conflict) sono in `main`. Esiste un `plan`
draft con `plan_op` (RETAG/RENAME/MOVE/DELETE, `before_json`/`after_json`) e i suoi
conflitti. Finora **nessun file è stato toccato**.

Questo è il **chunk 4**: esegue il piano sui file veri (**Apply**) e sa annullarlo
(**Undo**). È il **primo chunk che muta il filesystem** e introduce la **prima scrittura
di tag** (finora `tagio` era sola lettura). Stage successivi: 5 Bridge, 6 Frontend.

Vincoli di progettazione già raccolti nella memoria `apply-transaction-model`: commit
per-operazione (mai una mega-transazione), DELETE-prima-del-MOVE sugli slot dei rimossi,
ri-validazione pre-mutazione, snapshot-vs-live.

## 2. Scope

**Dentro:** scrittura tag (`tagio.write_tags`), operazioni FS sicure
(`integrations/fsops.py`), motore **Apply** (`services/apply.py`) + job, motore **Undo**
(`services/undo.py`), tabella `undo_journal`, transizioni `plan.status`, router
`apply`/`history`, suite pytest incluso il **property test dell'invariante**.

**Fuori:** Bridge, frontend, tabella `settings` template (già nel chunk 3).

## 3. Decisioni chiave (approvate)

1. **Invariante cardine:** per ogni piano, `apply` poi `undo` riporta il filesystem
   **esattamente** allo stato iniziale (path, nomi, tag a livello *logico*). Per
   garantirla, **ogni op scrive una riga di journal con lo stato precedente prima di
   mutare**; l'Undo inverte in ordine inverso. **Mai hard-delete:** DELETE = sposta in
   quarantena (recuperabile).
2. **Quarantena `.quarantine/` per-radice**, preservando il path relativo:
   `<root>/.quarantine/<path-relativo-alla-root>` → niente collisioni di nome, recupero
   ovvio.
3. **Riordino DELETE-prima-del-MOVE:** se la destinazione di un MOVE è occupata da un file
   in DELETE, quel DELETE va in quarantena *prima* del MOVE. Mantiene "mai overwrite".
4. **Snapshot + ri-validazione:** l'Apply usa la *foto* del piano (`plan.rules_json` +
   i `plan_op` persistiti). Prima di mutare ri-valida che il piano non sia **stale** (ogni
   file esiste e combacia col `before`); se stale → **abort senza mutare**.
5. **Apply = job async** (come lo scan). **Undo = sincrono** (di norma più piccolo;
   jobificabile dopo).
6. **Move cross-disco:** `os.rename` (atomico, stesso disco); se fallisce per dischi
   diversi → **copy + verifica (`content_hash`) + delete dell'originale**.

## 4. Struttura file

```text
backend/app/
  models.py              # MOD: UndoJournal; plan.status già esiste (draft/applied/undone)
  schemas.py             # MOD: ApplyResult, HistoryItem, ...
  integrations/
    tagio.py             # MOD: write_tags(path, changes) (prima scrittura)
    fsops.py             # NEW: safe_move(src, dst), to_quarantine(path, root), from_quarantine(...)
  services/
    apply.py             # NEW: apply_plan(db, plan, on_progress) -> ApplyResult (motore)
    apply_job.py         # NEW: job shell (thread + stato), port da scan_job
    undo.py              # NEW: undo_run(db, plan) -> UndoResult
  routers/
    apply.py             # NEW: POST /api/apply, GET /api/apply/status
    history.py           # NEW: GET /api/history, POST /api/history/{plan_id}/undo
  main.py                # MOD: include apply, history
backend/tests/
  test_tagio_write.py · test_fsops.py · test_apply.py · test_undo.py · test_apply_undo_invariant.py · test_apply_api.py
```

## 5. Data model

**`undo_journal`** (run_id = plan_id; una run = un'applicazione del piano):

| Campo | Tipo | Note |
|---|---|---|
| `id` | int PK | |
| `run_id` | int, indexed | = `plan.id` |
| `op_seq` | int | ordine effettivo di esecuzione (per invertire) |
| `kind` | str | `RETAG` \| `RENAME` \| `MOVE` \| `DELETE` |
| `file_id` | int, indexed | |
| `from_path` | str, nullable | path prima (RENAME/MOVE/DELETE) |
| `to_path` | str, nullable | path dopo (RENAME/MOVE); per DELETE = `quarantine_path` |
| `prior_tags_json` | JSON, nullable | valori tag *letti dal file vivo* prima del RETAG |
| `quarantine_path` | str, nullable | dove è finito il file (DELETE) |
| `applied_at` | datetime | |
| `reversed` | bool | true dopo l'undo |

**`plan.status`** transita `draft → applied → undone`. (La colonna esiste già dal chunk 3.)

## 6. Integrazioni

### `tagio.write_tags(path, changes: dict)` (nuova — prima scrittura)
`changes = {field: nuovo_valore_o_None}`. Usa mutagen easy mode: imposta i campi; `None`
→ rimuove la chiave del tag; `save()`. Solleva `TagWriteError` in caso di errore.
**`content_hash` non cambia** (è hash dello stream, non dei tag) → l'identità del file
resta stabile dopo il retag (verificato nel chunk 1).

### `integrations/fsops.py`
- `safe_move(src, dst)`: crea le cartelle di `dst`; **rifiuta se `dst` esiste già**
  (mai overwrite); prova `os.rename`; su `OSError` cross-device (EXDEV) → `copy2` in
  `dst.tmp`, verifica che `content_hash(dst.tmp) == content_hash(src)`, `os.replace(tmp,
  dst)`, `os.remove(src)`.
- `to_quarantine(path, root_path) -> quarantine_path`: `q = root_path/.quarantine/
  relpath(path, root_path)`; se esiste, aggiunge un suffisso univoco; `safe_move(path,
  q)`; ritorna `q`.
- `from_quarantine(quarantine_path, original_path)`: `safe_move(quarantine_path,
  original_path)`.

## 7. Apply (`services/apply.py`, motore)

`apply_plan(db, plan, on_progress=None) -> ApplyResult`.

**Pre-volo (nessuna mutazione):**
1. Ricalcola i conflitti del piano riusando il chunk 3, **con lo snapshot del piano**
   (`plan.rules_json`: template + target) sui **file vivi** — coerente con "applica la
   foto", ma intercetta nuove collisioni emerse sul disco. Se ci sono conflitti
   **bloccanti** → `ApplyResult(refused=True, reason="conflitti")`.
2. **Ri-validazione stale** per ogni `plan_op`:
   - RENAME/MOVE/DELETE: il file (`file_id`) esiste su disco e il suo path attuale ==
     `before_json["path"]`.
   - RETAG: il file esiste e i valori attuali dei campi in `before_json` combaciano.
   - Mismatch → `ApplyResult(stale=True, op_seq=…)`, **niente mutazioni**.

**Esecuzione** (ordine sicuro RETAG → RENAME/MOVE → DELETE, col riordino):
- **RETAG:** leggi dal file vivo i valori attuali dei campi (`prior_tags`), `journal`,
  poi `tagio.write_tags(path, after)`.
- **RENAME/MOVE:** per ogni op, se la destinazione è **occupata da un file con un'op
  DELETE non ancora eseguita** → esegui prima quel DELETE (quarantena + journal,
  marcandolo fatto). Poi `journal`, `safe_move(before, after)`.
- **DELETE** rimanenti (non già fatti come blocker): `q = to_quarantine(path, root)`,
  `journal` (`quarantine_path=q`).
- `on_progress(i, n, "applying")` per op.

**Per-op:** ogni riga di journal è **scritta e committata prima** della mutazione FS
(commit per-op, niente mega-transazione). `plan_op.status` → `applied`.

**Fallimento a metà:** la prima op che lancia ferma la run; le op già fatte restano nel
journal (recuperabili con undo); `ApplyResult(partial=True, failed_op_seq=…, error=…)`.

**Successo pieno:** `plan.status = applied`. (Una run parziale lascia comunque il journal
e marca `plan.status = applied` con `ApplyResult.partial=True`.)

`ApplyResult` (Pydantic): `run_id, applied_ops, refused, stale, partial, failed_op_seq,
error, started_at, finished_at`.

## 8. Undo (`services/undo.py`, sincrono)

`undo_run(db, plan) -> UndoResult`. Rilegge le righe `undo_journal` della run con
`reversed=False`, **in ordine `op_seq` decrescente**, e inverte:
- RETAG → `tagio.write_tags(path, prior_tags)` (ripristina i vecchi valori).
- RENAME/MOVE → `safe_move(to_path, from_path)` (rimette al vecchio path).
- DELETE → `from_quarantine(quarantine_path, from_path)` (ripesca dalla quarantena).
Ogni riga invertita → `reversed=True` (commit per-op). A fine: `plan.status = undone`.
`UndoResult`: `run_id, reversed_ops, error` (su errore: stop, lascia il resto invertibile).

## 9. Job + endpoint

- **`apply_job.py`** (port da `scan_job`): thread + stato in memoria + lock; `start_job()`
  applica il draft corrente; `job_state()`. Un solo apply alla volta.
- `POST /api/apply` → avvia il job sul draft corrente; 400 se non c'è draft o se ci sono
  conflitti bloccanti (verifica rapida prima di avviare). `GET /api/apply/status` →
  polling.
- `GET /api/history` → i `plan` con `status ∈ {applied, undone}`, con timestamp e
  conteggi op (per la pagina HISTORY).
- `POST /api/history/{plan_id}/undo` → `undo_run` (sincrono); 400 se il piano non è
  `applied` o è già `undone`.

## 10. Errori e sicurezza

- **Mai overwrite:** `safe_move` rifiuta una destinazione esistente; il riordino e il
  conflict-check riducono i casi; guardia a runtime come backstop.
- **Mai hard-delete:** sempre quarantena.
- **Commit per-op:** un crash a metà lascia FS e DB coerenti fino all'ultima op
  committata; l'undo riparte dal journal.
- **Stale → abort pre-mutazione:** non si muta su presupposti vecchi.
- **Cross-device move:** copy+verifica+delete; se la verifica hash fallisce → abort senza
  cancellare l'originale.
- **Idempotenza undo:** righe `reversed=True` non si re-invertono.

## 11. Test (pytest, su filesystem temporaneo coi fixture)

- **`test_tagio_write.py`:** scrive tag su una copia di un fixture e li rilegge;
  `content_hash` invariato dopo il retag; rimozione (`None`).
- **`test_fsops.py`:** `safe_move` rinomina; rifiuta dst esistente; quarantena preserva il
  path relativo ed è recuperabile; (simulazione cross-device via monkeypatch di
  `os.rename` che lancia EXDEV → fallback copy+verifica).
- **`test_apply.py`:** applica un piano con RETAG/RENAME/MOVE/DELETE su file temporanei →
  i file sono nei posti giusti, i tag scritti, i rimossi in quarantena, il journal
  popolato; il riordino delete-prima-di-move (keeper nello slot di un rimosso) funziona;
  pre-volo **stale** → abort senza mutazioni; conflitto bloccante → refused.
- **`test_undo.py`:** dopo un apply, l'undo riporta ogni cosa al suo posto; idempotente.
- **`test_apply_undo_invariant.py` (il test cardine):** costruisce uno stato iniziale
  (file con tag e path noti), genera un piano, `apply` poi `undo`, e asserisce che **path,
  nomi e tag logici siano identici allo stato iniziale**. Più un caso di **fallimento a
  metà** (monkeypatch che fa fallire l'op N) → undo del parziale → stato iniziale.
- **`test_apply_api.py`:** TestClient — POST /api/apply (job) + polling status; GET
  /api/history; POST undo; 400 sui casi (no draft, conflitti, undo di non-applied).

Output pristine (`filterwarnings = error`).

## 12. Convenzioni (dai chunk 1-3)

SQLAlchemy 2.0, no Alembic (`create_all`/`ensure_schema`), Pydantic v2, router sottili,
motore deterministico, `utcnow()` tz-aware, job stile `scan_job`. Comandi:
`cd backend && source .venv/bin/activate && python -m pytest tests`.

## 13. Definition of Done (chunk 4)

- `pytest tests` verde e pristine, incluso il **property test apply→undo == stato
  iniziale** (happy path + fallimento a metà).
- Con un piano draft reale: `POST /api/apply` esegue (retag/rename/move/delete-in-
  quarantena), `GET /api/apply/status` mostra il progresso; `GET /api/history` elenca la
  run; `POST .../undo` la annulla riportando i file al loro posto.
- Mai overwrite, mai hard-delete, abort pulito su piano stale.
