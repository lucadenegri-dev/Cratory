# DjOrganizer — Chunk 2: Inspector + Dedup

> Data: 2026-06-27 · Stato: design approvato, pronto per il plan.
> Secondo sub-progetto. Spec madre:
> [2026-06-27-djorganizer-design.md](2026-06-27-djorganizer-design.md) ·
> Chunk 1: [2026-06-27-djorganizer-chunk1-scanner-design.md](2026-06-27-djorganizer-chunk1-scanner-design.md).

## 1. Contesto

DjOrganizer è costruito backend-first in 6 chunk (vedi spec chunk 1 §1). Il chunk 1
(Fondazione + Scanner) è completo e in `main`: scansiona le cartelle e persiste righe
`audio_file` (con tag, info tecniche, `content_hash`, `scan_error`).

Questo è il **chunk 2**: due stage **puri e read-only** che girano sopra le righe
`audio_file` già scansionate.

- **Inspector** — rileva problemi per-file → tabella `issue`.
- **Dedup** — raggruppa i doppioni → `dup_group` / `dup_member`, propone un *keeper*.

**Nessuna mutazione dei file** in questo chunk: accettare un fix o marcare una rimozione
registra solo la *decisione*; il cambiamento vero lo esegue l'Apply (chunk 4) tramite il
Plan (chunk 3). Stage successivi: 3 Plan+Conflict, 4 Apply+Undo, 5 Bridge, 6 Frontend.

## 2. Scope

**Dentro:** `services/inspector.py` + `services/dedup.py` (puri), tabelle `issue`,
`dup_group`, `dup_member`, logica di merge che preserva le decisioni utente al ricalcolo,
analisi in coda al job di scan + endpoint `POST /api/analyze`, router `issues` e
`duplicates`, suite pytest.

**Fuori:** Plan, Conflict, Apply/Undo, Bridge, tabella `settings`, frontend. L'Inspector
**non** rinomina e **non** riempie i metadata: propone solo, l'esecuzione è del Plan/Apply.

## 3. Decisioni chiave (con motivazione)

1. **Match fuzzy conservativo + guardia durata.** Due file sono lo stesso brano solo se
   `artist+title` normalizzati sono **uguali** E la durata è entro tolleranza (default
   ±2s). I marcatori (`Extended Mix`, `Radio Edit`, `feat.`) **non** vengono rimossi → le
   versioni distinte restano separate. Per un DJ il falso positivo (fondere un remix) è il
   rischio peggiore; questo lo elimina.
2. **Tassonomia issue su 3 severità.** error (blocca un piano pulito), warning (da
   sistemare, spesso auto-fixabile), info (proprietà del file, non auto-fixabile).
3. **Il ricalcolo preserva le decisioni utente.** Issue *dismissed* non riappaiono,
   *accepted* restano; keeper scelti a mano restano. Robusto per il loop
   rivedi → ri-scansiona. (Schema con identità stabili per il merge.)
4. **`issue.status` (open/accepted/dismissed) + colonna `field`** affinano il `resolved`
   booleano della spec madre: distinguono *accettato* da *ignorato* e permettono più
   issue dello stesso tipo su campi diversi dello stesso file.
5. **Dedup a due passaggi, un gruppo per file.** Fuzzy primario (cattura flac+mp3 dello
   stesso brano) + esatto di recupero (byte-identici con tag diversi/assenti).
6. **lossless = `flac/wav/aiff/aif`.** m4a/ALAC trattato come lossy per ora (mutagen di
   norma lo riporta come AAC; rivedibile in un chunk successivo).
7. **Trigger duplice.** Analisi in coda al job di scan (scan → inspect → dedup) **+**
   `POST /api/analyze` per ri-analizzare i dati esistenti senza ri-camminare il disco.

## 4. Struttura file

```text
backend/app/
  models.py            # MODIFICA: aggiunge Issue, DupGroup, DupMember
  schemas.py           # MODIFICA: IssueRead, DupGroupRead, DupMemberRead, AnalyzeSummary, ...
  services/
    inspector.py       # NEW — inspect(files) -> list[IssueComputed] (puro)
    dedup.py           # NEW — find_duplicates(files) -> list[DupGroupComputed] (puro)
    analysis.py        # NEW — orchestratore + merge che preserva le decisioni (scrive DB)
    scan_job.py        # MODIFICA: dopo lo scan chiama analysis.recompute (fasi inspect/dedup)
  routers/
    issues.py          # NEW — GET /api/issues, POST /api/issues/{id}/status, /bulk
    duplicates.py      # NEW — GET /api/duplicates, POST .../keeper, .../dismiss
    analyze.py         # NEW — POST /api/analyze
  core/config.py       # MODIFICA: soglie (low_bitrate, durata min/max, fuzzy_dur_tol)
backend/tests/
  test_inspector.py · test_dedup.py · test_analysis_merge.py · test_issues_api.py · test_duplicates_api.py
```

I service puri (`inspector`, `dedup`) non toccano il DB: ricevono oggetti/righe e
ritornano strutture calcolate. `analysis.py` fa da orchestratore impuro (legge
`audio_file`, chiama i puri, fa il merge che preserva le decisioni, scrive issue/dup).
Router sottili.

## 5. Data model (3 tabelle nuove)

Pattern chunk 1: `ensure_schema()` (`create_all`) crea le nuove tabelle; niente Alembic.

**`issue`** — un problema rilevato su un file. Chiave di merge `(file_id, type, field)`.

| Campo | Tipo | Note |
|---|---|---|
| `id` | int PK | |
| `file_id` | FK → audio_file.id, indexed | |
| `type` | str, indexed | es. `missing_required_tag`, `scan_error`, `missing_metadata`, `inconsistent_casing`, `filename_tag_mismatch`, `junk_tag`, `low_quality`, `suspicious_duration` |
| `field` | str, nullable | campo tag interessato (`artist`/`title`/`genre`/…); null per issue non legati a un campo |
| `severity` | str | `error` \| `warning` \| `info` |
| `detail` | text | messaggio leggibile |
| `suggested_fix_json` | JSON, nullable | presente solo per gli auto-fixabili |
| `status` | str, indexed | `open` \| `accepted` \| `dismissed` (default `open`) |
| `created_at` / `updated_at` | datetime | |

Vincolo unico `(file_id, type, field)`.

**`dup_group`** — un gruppo di doppioni.

| Campo | Tipo | Note |
|---|---|---|
| `id` | int PK | |
| `match_kind` | str | `exact` \| `fuzzy` |
| `keeper_file_id` | FK → audio_file.id | il file da tenere |
| `keeper_overridden` | bool | true se il keeper è stato scelto a mano (default false) |
| `dismissed` | bool | true se l'utente ha dichiarato "non sono doppioni" (default false) |
| `signature` | str, indexed | hash deterministico dei `file_id` membri ordinati → identità stabile per il merge |
| `created_at` | datetime | |

**`dup_member`** — appartenenza file→gruppo. Unico `(group_id, file_id)`.

| Campo | Tipo | Note |
|---|---|---|
| `id` | int PK | |
| `group_id` | FK → dup_group.id, indexed, cascade delete | |
| `file_id` | FK → audio_file.id, indexed | |
| `action` | str | `keep` (keeper) \| `remove` |

## 6. Inspector (`services/inspector.py`, puro)

`inspect(files: list[AudioFile]) -> list[IssueComputed]`. Per ogni file applica i
controlli; ogni `IssueComputed` ha `(file_id, type, field, severity, detail,
suggested_fix)`. Controlli e regole MVP:

| type | severity | field | auto-fix | regola |
|---|---|---|---|---|
| `missing_required_tag` | error | artist/title | no | tag artist o title vuoto/nullo |
| `scan_error` | error | – | no | `audio_file.scan_error` non nullo (promozione dal chunk 1); `detail` = il messaggio |
| `missing_metadata` | warning | genre/year/label | no | il campo è vuoto/nullo (un issue per campo) |
| `inconsistent_casing` | warning | artist/title/album | **sì** | valore tutto MAIUSCOLO o tutto minuscolo (multi-parola) → fix `{field, from, to=Title Case}` |
| `filename_tag_mismatch` | warning | – | no | lo stem del file (normalizzato) non contiene né artist né title |
| `junk_tag` | warning | title/comment | **sì** | title ~ `^track\s*\d+$`/`^\d+$`; oppure comment con marcatori spam (URL, "ripped by", lunghezza eccessiva) → fix `{field, action:"clear"}` |
| `low_quality` | info | – | no | file lossy (`mp3/m4a/aac`) con `bitrate` < soglia (default 256 kbps); i lossless non si flaggano mai |
| `suspicious_duration` | info | – | no | durata < min (default 30s) o > max (default 15min) |

**Casing conservativo:** si segnala solo tutto-maiuscolo / tutto-minuscolo (casi netti),
per non flaggare nomi stilizzati legittimi (`deadmau5`, `MK`). `suggested_fix` per gli
auto-fixabili è una proposta di RETAG che il Plan (chunk 3) consumerà. Soglie in
`core/config.py`.

## 7. Dedup (`services/dedup.py`, puro)

`find_duplicates(files) -> list[DupGroupComputed]`. Ogni file in **al più un gruppo**.

**Normalizzazione** (`_norm`): NFKD + rimozione diacritici, minuscole, spazi collassati,
trim. **Niente** rimozione di marcatori/parentesi.

**Passo 1 — primario (fuzzy)** sui file con artist *e* title non vuoti:
1. Raggruppa per chiave `(_norm(artist), _norm(title))`.
2. Dentro ogni key-group, **clusterizza per durata**: ordina per `duration_s`, cluster
   greedy con i membri entro tolleranza (`fuzzy_dur_tol`, default 2.0s) dal primo membro
   del cluster. File senza durata → non clusterizzano (restano soli).
3. Ogni cluster con ≥2 membri → gruppo. `match_kind='exact'` se tutti i membri
   condividono lo stesso `content_hash` non nullo, altrimenti `'fuzzy'`.

**Passo 2 — esatto di recupero** sui file rimasti **soli** dopo il passo 1: raggruppa per
`content_hash` uguale (non nullo); cluster con ≥2 membri → gruppo `match_kind='exact'`.
Cattura byte-identici con tag diversi/assenti.

**Keeper (deterministico)** per ogni gruppo, precedenza:
1. **lossless** (`ext ∈ {flac,wav,aiff,aif}`) prima dei lossy
2. **bitrate** più alto
3. **completezza tag** più alta = n. di campi non vuoti tra
   `{artist,title,album,album_artist,genre,year,label,track_no,has_cover}`
4. **path più pulito** = minore penalità marcatori (`(\d+)`, `copy`, `duplicate`), poi
   più corto
5. **`id` minore** (tie-break finale, deterministico)

`keeper_file_id` = vincitore; `dup_member.action`: `keep` per il keeper, `remove` per gli
altri.

## 8. Ricalcolo che preserva le decisioni (`services/analysis.py`)

`recompute(db, on_progress=None) -> AnalyzeSummary`. Legge tutte le `audio_file`
`status='present'`, chiama `inspect` e `find_duplicates`, poi fa il **merge**:

**Issue** — per ogni `IssueComputed`:
- esiste una riga con stessa `(file_id, type, field)` → aggiorna `severity/detail/
  suggested_fix`, **preserva `status`** (un *dismissed* resta dismissed, un *accepted*
  resta accepted);
- non esiste → insert con `status='open'`.
- Le righe `issue` esistenti **non più** tra i calcolati (file sistemato/sparito) →
  cancellate.

**Dedup** — calcola i nuovi gruppi e la loro `signature` (hash dei `file_id` ordinati).
Se esiste un vecchio gruppo con la **stessa `signature`** si preservano le decisioni
utente:
- `dismissed=true` → il nuovo gruppo resta `dismissed` (tutti i membri `keep`);
- altrimenti `keeper_overridden=true` con keeper ancora membro → eredita
  `keeper_file_id` e `keeper_overridden=true`;
- altrimenti keeper automatico per precedenza.
- Composizione cambiata → `signature` diversa → gruppo nuovo (keeper automatico, non
  dismesso).
- I vecchi gruppi/membri vengono sostituiti dai nuovi (drop+insert), preservando
  `dismissed`/override via `signature`.

`AnalyzeSummary` (Pydantic): `issues_total, issues_by_severity{error,warning,info},
dup_groups, dup_files, started_at, finished_at`.

## 9. Trigger ed endpoint

- **Job di scan (modifica chunk 1):** dopo `scan(...)` il `scan_job` chiama
  `analysis.recompute(...)` con fasi `on_progress` (`phase='inspecting'`, `'deduping'`),
  così a fine scan issue e doppioni sono già pronti.
- **`POST /api/analyze`** (`routers/analyze.py`): esegue `recompute` sui dati esistenti
  (nessun walk del FS); sincrono (computazione pura, veloce) e ritorna `AnalyzeSummary`.
- **`routers/issues.py`:** `GET /api/issues` (filtri `severity/type/status/root_id`, join
  con path/tag del file per la UI) · `POST /api/issues/{id}/status` `{status}` ·
  `POST /api/issues/bulk` `{filter:{type?,severity?}, status}` (accetta/ignora in blocco).
- **`routers/duplicates.py`:** `GET /api/duplicates` (gruppi con membri + dati file) ·
  `POST /api/duplicates/{id}/keeper` `{file_id}` (override → ricalcola le action, setta
  `keeper_overridden`) · `POST /api/duplicates/{id}/dismiss` (setta `dismissed=true`,
  tutti i membri `keep`: "non sono doppioni"). Entrambe le decisioni sopravvivono al
  ricalcolo via `signature`.

Router sottili; la logica sta in `analysis.py` e nei service puri.

## 10. Errori e casi limite

- File con `scan_error` (no hash/tag): l'Inspector emette solo `scan_error`; il Dedup li
  ignora nel passo fuzzy (niente artist/title) e nel passo esatto se `content_hash` nullo.
- File senza durata → non clusterizzano per durata (restano soli nel passo 1).
- `set_keeper` con un `file_id` non membro del gruppo → 400.
- `dismissed`/keeper override sopravvivono al ricalcolo solo a **composizione invariata**
  (stessa `signature`); se la composizione cambia il gruppo è nuovo e va rivisto —
  comportamento atteso (è effettivamente un gruppo diverso).
- Determinismo: a parità di input il keeper e i gruppi sono identici (test di stabilità).

## 11. Test (pytest)

- **`test_inspector.py`:** ogni `type` su `AudioFile` costruiti ad hoc; severità corretta;
  `suggested_fix` per casing/junk; casing **non** flagga nomi stilizzati; promozione di
  `scan_error`.
- **`test_dedup.py`:** flac+mp3 stesso brano → un gruppo, keeper=flac; **guardia durata**:
  stesso titolo ma durate lontane (extended vs radio edit) → gruppi separati; marcatori
  diversi (`(Radio Edit)` vs `(Extended Mix)`) → non raggruppati; esatto di recupero su
  byte-identici con tag diversi; precedenza keeper e tie-break; determinismo.
- **`test_analysis_merge.py`:** dismiss che sopravvive al ri-calcolo; accepted preservato;
  issue non più valido cancellato; keeper override preservato a parità di `signature`;
  composizione cambiata → gruppo nuovo con keeper automatico.
- **`test_issues_api.py` / `test_duplicates_api.py`:** TestClient — liste con filtri,
  set status singolo/bulk, set keeper (+ 400 su file non membro), dismiss; `POST
  /api/analyze` end-to-end.

Output pristine (policy `filterwarnings = error` ereditata dal chunk 1).

## 12. Convenzioni (dal chunk 1)

SQLAlchemy 2.0 (`Mapped`/`mapped_column`), no Alembic (`create_all`/`ensure_schema`),
Pydantic v2, router sottili, motore deterministico, `utcnow()` tz-aware. Comandi:
`cd backend && source .venv/bin/activate && python -m pytest tests`.

## 13. Definition of Done (chunk 2)

- `pytest tests` verde e pristine, inclusi i test di guardia durata e di merge che
  preserva le decisioni.
- Uno scan reale popola `issue` e `dup_group`/`dup_member`; `POST /api/analyze` ricalcola
  senza ri-scansionare; le decisioni (dismiss/accept, keeper override) sopravvivono al
  ricalcolo.
- Endpoint `issues`/`duplicates`/`analyze` funzionanti via TestClient.
