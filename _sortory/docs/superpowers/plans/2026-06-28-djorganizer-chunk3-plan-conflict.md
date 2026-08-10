# DjOrganizer Chunk 3 — Plan + Conflict — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Su una libreria scansionata + analizzata, produrre un *piano* deterministico di operazioni (RETAG da issue accettati, RENAME/MOVE di tutti i file tenuti sui template, DELETE per i removals dedup) con diff prima→dopo, e validarlo (collisioni, dati mancanti, fuori radice) — senza toccare i file.

**Architecture:** Due service **puri** (`planner.py`, `conflict.py`) che ricevono righe e ritornano strutture; un orchestratore `planning.py` che legge il DB, snapshotta i settings, scrive `plan`/`plan_op` e calcola conflitti+stats. Tabella `settings` (template globali) + colonna `scan_root.target_root` (per-radice, default in-place). Router sottili.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest. Nessuna nuova dipendenza.

**Spec di riferimento:** [docs/superpowers/specs/2026-06-28-djorganizer-chunk3-plan-conflict-design.md](../specs/2026-06-28-djorganizer-chunk3-plan-conflict-design.md)

## Global Constraints

- **SQLAlchemy 2.0**, no Alembic: tabelle nuove via `create_all`; **colonna nuova** `scan_root.target_root` via `ensure_schema` esteso con `ALTER TABLE … ADD COLUMN` se mancante.
- **`planner` e `conflict` PURI** (no DB), deterministici.
- **Nessuna mutazione dei file** in questo chunk.
- **Template default:** `naming_template = "{artist} - {title}"`, `folder_template = "{genre}/{artist}"`; `folder_template` vuoto = piatto.
- **`target_root` per-radice**, default = la radice stessa (in-place). Destinazione = `<target_root>/{folder}/{naming}.{ext}`, sotto la `target_root` della radice del file.
- **Ordine sicuro del piano:** RETAG → RENAME/MOVE → DELETE; `seq` globale crescente; dentro ogni gruppo ordina per `(path, file_id)`.
- **Sanitizzazione** dei valori nel path: `/ \ : * ? " < > |` → `_`, `..` neutralizzato, spazi/punti iniziali/finali rimossi.
- **File esclusi dal piano:** quelli con `scan_error` non nullo; i `removals` (dedup) ricevono solo DELETE.
- **Output pristine** sotto `filterwarnings = error`.
- Comandi: `cd backend && source .venv/bin/activate && python -m pytest tests`.
- Commit: prefisso conventional, italiano, footer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```text
backend/app/
  db.py                  # MOD: ensure_schema → ALTER scan_root.target_root se mancante
  models.py              # MOD: Settings, Plan, PlanOp; ScanRoot.target_root
  schemas.py             # MOD: SettingsRead, RootTargetRead, SettingsUpdate, RootTargetUpdate, PlanOpRead, ConflictRead, PlanStats, PlanRead
  services/
    planner.py           # NEW: PlanOpComputed, fixes_by_file, effective_tags, render_destination, build_plan (puro)
    conflict.py          # NEW: ConflictComputed, check (puro)
    planning.py          # NEW: get/update settings, set_root_target, root_targets, create_plan, load_plan
  routers/
    settings.py          # NEW: GET/PUT /api/settings, PUT /api/settings/roots/{id}/target
    plan.py              # NEW: POST /api/plan, GET /api/plan
  main.py                # MOD: include settings, plan
backend/tests/
  test_schema_chunk3.py · test_planner.py · test_conflict.py · test_planning.py · test_settings_api.py · test_plan_api.py
```

---

## Task 1: Modelli + colonna target_root + ensure_schema ALTER

**Files:**
- Modify: `backend/app/models.py`, `backend/app/db.py`
- Test: `backend/tests/test_schema_chunk3.py`

**Interfaces:**
- Produces: `app.models.Settings`, `app.models.Plan`, `app.models.PlanOp`; `ScanRoot.target_root: str | None`; `ensure_schema` che aggiunge `scan_root.target_root` se mancante.

- [ ] **Step 1: Aggiungi `target_root` a `ScanRoot` e i 3 modelli in `backend/app/models.py`**

Nella classe `ScanRoot`, dopo `last_scanned_at`, aggiungi:

```python
    target_root: Mapped[str | None] = mapped_column(String)
```

In fondo al file aggiungi:

```python
class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # riga singola, id=1
    naming_template: Mapped[str] = mapped_column(String, default="{artist} - {title}")
    folder_template: Mapped[str] = mapped_column(String, default="{genre}/{artist}")
    dedup_keep_rules_json: Mapped[dict | None] = mapped_column(JSON)
    cratory_base_url: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Plan(Base):
    __tablename__ = "plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String, default="draft", index=True)
    rules_json: Mapped[dict] = mapped_column(JSON)

    ops: Mapped[list["PlanOp"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanOp(Base):
    __tablename__ = "plan_op"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)
    file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"), index=True)
    before_json: Mapped[dict] = mapped_column(JSON)
    after_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="pending")

    plan: Mapped["Plan"] = relationship(back_populates="ops")
```

(`JSON`, `Integer`, `ForeignKey`, `String`, `DateTime`, `Mapped`, `mapped_column`, `relationship`, `utcnow` sono già importati dai chunk 1-2.)

- [ ] **Step 2: Estendi `ensure_schema` in `backend/app/db.py` con l'ALTER**

Sostituisci la funzione `ensure_schema` con:

```python
def ensure_schema(eng=None) -> None:
    """create_all + ALTER per colonne aggiunte dopo (niente Alembic: app locale)."""
    import app.models  # noqa: F401

    eng = eng or engine
    Base.metadata.create_all(eng)
    from sqlalchemy import inspect, text

    inspector = inspect(eng)
    if "scan_root" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("scan_root")}
        if "target_root" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE scan_root ADD COLUMN target_root VARCHAR"))
```

- [ ] **Step 3: Scrivi il test che fallisce — `backend/tests/test_schema_chunk3.py`**

```python
from sqlalchemy import create_engine, inspect, text

from app.db import engine, ensure_schema


def test_chunk3_tables_and_column():
    insp = inspect(engine)
    assert {"settings", "plan", "plan_op"} <= set(insp.get_table_names())
    assert "target_root" in {c["name"] for c in insp.get_columns("scan_root")}


def test_ensure_schema_adds_target_root_to_old_db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE scan_root (id INTEGER PRIMARY KEY, path VARCHAR, "
            "label VARCHAR, last_scanned_at DATETIME)"
        ))
    ensure_schema(eng)
    assert "target_root" in {c["name"] for c in inspect(eng).get_columns("scan_root")}
```

- [ ] **Step 4: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_schema_chunk3.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/tests/test_schema_chunk3.py
git commit -m "feat: modelli settings/plan/plan_op + scan_root.target_root + ALTER

Tre tabelle del chunk 3 e la colonna per-radice target_root; ensure_schema
aggiunge la colonna ai DB esistenti (niente Alembic).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Planner (service puro)

**Files:**
- Create: `backend/app/services/planner.py`
- Test: `backend/tests/test_planner.py`

**Interfaces:**
- Consumes: `app.models.AudioFile`, `app.models.Issue`, `make_audio_file` (test).
- Produces:
  - `planner.PlanOpComputed` (frozen dataclass: `kind:str, file_id:int, before:dict, after:dict`).
  - `planner.fixes_by_file(accepted_issues) -> dict[int, list[dict]]`.
  - `planner.effective_tags(file, fixes: list[dict]) -> dict`.
  - `planner.render_destination(file, tags: dict, settings_snapshot: dict, root_targets: dict) -> tuple[str | None, str | None]` (dest, missing_field).
  - `planner.build_plan(files, accepted_issues, removals, settings_snapshot, root_targets) -> list[PlanOpComputed]`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_planner.py`**

```python
from app.models import Issue
from app.services.planner import build_plan, render_destination, effective_tags
from tests.conftest import make_audio_file

SNAP = {"naming_template": "{artist} - {title}", "folder_template": "{genre}/{artist}"}
TARGETS = {1: "/lib"}


def _accepted(file_id, field, to=None, action="retag"):
    fix = {"field": field, "action": action}
    if to is not None:
        fix["to"] = to
    return Issue(file_id=file_id, type="x", field=field, severity="warning",
                 detail="", suggested_fix_json=fix, status="accepted")


def test_retag_aggregates_per_file():
    f = make_audio_file(1, root_id=1, artist="PINCO", title="bel titolo", genre="House",
                        path="/lib/x.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "artist", "Pinco")], set(), SNAP, TARGETS)
    retag = [o for o in ops if o.kind == "RETAG"]
    assert len(retag) == 1
    assert retag[0].before == {"artist": "PINCO"} and retag[0].after == {"artist": "Pinco"}


def test_effective_tags_used_in_rename():
    f = make_audio_file(1, root_id=1, artist="PINCO", title="T", genre="House",
                        path="/lib/old.mp3", ext="mp3")
    ops = build_plan([f], [_accepted(1, "artist", "Pinco")], set(), SNAP, TARGETS)
    move = [o for o in ops if o.kind in ("RENAME", "MOVE")][0]
    assert move.after["path"] == "/lib/House/Pinco/Pinco - T.mp3"  # usa l'artist corretto


def test_rename_vs_move():
    # già in /lib/House/A, cambia solo il nome → RENAME
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/House/A/vecchio.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGETS)
    assert ops[0].kind == "RENAME" and ops[0].after["path"] == "/lib/House/A/A - T.mp3"


def test_move_to_different_folder():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/varie/x.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGETS)
    assert ops[0].kind == "MOVE"


def test_removed_file_only_delete():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/varie/x.mp3", ext="mp3")
    ops = build_plan([f], [], {1}, SNAP, TARGETS)
    assert [o.kind for o in ops] == ["DELETE"]
    assert ops[0].before == {"path": "/lib/varie/x.mp3"}


def test_sanitize_path_chars():
    f = make_audio_file(1, root_id=1, artist="AC/DC", title="T", genre="Rock",
                        path="/lib/x.mp3", ext="mp3")
    dest, miss = render_destination(f, effective_tags(f, []), SNAP, TARGETS)
    assert "AC_DC" in dest and ".." not in dest


def test_missing_field_no_op():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre=None,
                        path="/lib/x.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGETS)
    assert ops == []  # genre mancante per {genre}/... → nessuna rinomina


def test_order_and_determinism():
    keep = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                           path="/lib/varie/a.mp3", ext="mp3")
    rem = make_audio_file(2, root_id=1, artist="B", title="U", genre="House",
                          path="/lib/varie/b.mp3", ext="mp3")
    ops = build_plan([keep, rem], [_accepted(1, "artist", "A")], {2}, SNAP, TARGETS)
    assert [o.kind for o in ops] == ["RETAG", "MOVE", "DELETE"]
    assert build_plan([rem, keep], [_accepted(1, "artist", "A")], {2}, SNAP, TARGETS) == ops
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_planner.py -v`
Expected: ImportError su `build_plan`.

- [ ] **Step 3: Implementa `backend/app/services/planner.py`**

```python
"""Planner: calcola le operazioni del piano. Puro, deterministico."""

import os
import re
from dataclasses import dataclass

_EFFECTIVE_FIELDS = ("artist", "title", "album", "album_artist", "genre", "year",
                     "label", "track_no", "comment")
_TEMPLATE_FIELD_RE = re.compile(r"\{(\w+)\}")
_SANITIZE_RE = re.compile(r'[/\\:*?"<>|]')


@dataclass(frozen=True)
class PlanOpComputed:
    kind: str
    file_id: int
    before: dict
    after: dict


def _sanitize(value: str) -> str:
    s = _SANITIZE_RE.sub("_", value).replace("..", "_")
    return s.strip(" .")


def _render(template: str, tags: dict) -> tuple[str | None, str | None]:
    """Ritorna (stringa_renderizzata, None) oppure (None, primo_campo_mancante)."""
    fields = _TEMPLATE_FIELD_RE.findall(template)
    for field in fields:
        v = tags.get(field)
        if v is None or (isinstance(v, str) and not v.strip()):
            return None, field
    out = template
    for field in fields:
        out = out.replace("{" + field + "}", _sanitize(str(tags[field]).strip()))
    return out, None


def fixes_by_file(accepted_issues) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for issue in accepted_issues:
        if issue.suggested_fix_json:
            out.setdefault(issue.file_id, []).append(issue.suggested_fix_json)
    return out


def effective_tags(file, fixes: list[dict]) -> dict:
    tags = {k: getattr(file, k) for k in _EFFECTIVE_FIELDS}
    for fix in fixes:
        field = fix.get("field")
        if field in _EFFECTIVE_FIELDS:
            tags[field] = None if fix.get("action") == "clear" else fix.get("to")
    return tags


def render_destination(file, tags: dict, settings_snapshot: dict,
                       root_targets: dict) -> tuple[str | None, str | None]:
    folder_tpl = settings_snapshot.get("folder_template", "") or ""
    folder_part, miss = (_render(folder_tpl, tags) if folder_tpl else ("", None))
    if miss is not None:
        return None, miss
    name_part, miss = _render(settings_snapshot["naming_template"], tags)
    if miss is not None:
        return None, miss
    target_root = root_targets.get(file.root_id) or os.path.dirname(file.path)
    dest_dir = os.path.join(target_root, folder_part) if folder_part else target_root
    return os.path.join(dest_dir, f"{name_part}.{file.ext}"), None


def build_plan(files, accepted_issues, removals, settings_snapshot,
               root_targets) -> list[PlanOpComputed]:
    removals = set(removals)
    by_file = fixes_by_file(accepted_issues)
    retag_ops: list[PlanOpComputed] = []
    move_ops: list[PlanOpComputed] = []
    del_ops: list[PlanOpComputed] = []

    for f in sorted(files, key=lambda x: (x.path, x.id)):
        fixes = by_file.get(f.id, [])
        if fixes:
            before, after = {}, {}
            for fix in fixes:
                field = fix.get("field")
                if field not in _EFFECTIVE_FIELDS:
                    continue
                new_val = None if fix.get("action") == "clear" else fix.get("to")
                before.setdefault(field, getattr(f, field))
                after[field] = new_val
            if before:
                retag_ops.append(PlanOpComputed("RETAG", f.id, before, after))

        if f.id in removals:
            del_ops.append(PlanOpComputed("DELETE", f.id, {"path": f.path}, {}))
            continue

        dest, _miss = render_destination(f, effective_tags(f, fixes),
                                         settings_snapshot, root_targets)
        if dest is None or dest == f.path:
            continue
        kind = "RENAME" if os.path.dirname(dest) == os.path.dirname(f.path) else "MOVE"
        move_ops.append(PlanOpComputed(kind, f.id, {"path": f.path}, {"path": dest}))

    return retag_ops + move_ops + del_ops
```

- [ ] **Step 4: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_planner.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/planner.py backend/tests/test_planner.py
git commit -m "feat: Planner — RETAG/RENAME/MOVE/DELETE dai template (puro)

Tag effettivi post-retag per la rinomina, sanitizzazione del path, ordine
sicuro RETAG->RENAME/MOVE->DELETE, deterministico.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Conflict (service puro)

**Files:**
- Create: `backend/app/services/conflict.py`
- Test: `backend/tests/test_conflict.py`

**Interfaces:**
- Consumes: `planner` (fixes_by_file, effective_tags, render_destination, PlanOpComputed), `app.models`.
- Produces:
  - `conflict.ConflictComputed` (frozen dataclass: `kind:str, file_id:int, detail:str`).
  - `conflict.check(plan_ops, files_by_id, accepted_issues, removals, settings_snapshot, root_targets) -> list[ConflictComputed]`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_conflict.py`**

```python
from app.services.conflict import check
from app.services.planner import PlanOpComputed, build_plan
from tests.conftest import make_audio_file

SNAP = {"naming_template": "{artist} - {title}", "folder_template": "{genre}/{artist}"}
TARGETS = {1: "/lib"}


def test_clean_plan_no_conflicts():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/varie/x.mp3", ext="mp3")
    ops = build_plan([f], [], set(), SNAP, TARGETS)
    assert check(ops, {1: f}, [], set(), SNAP, TARGETS) == []


def test_collision_two_same_dest():
    a = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/1.mp3", ext="mp3")
    b = make_audio_file(2, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/2.mp3", ext="mp3")  # stesso artist+title+genre → stessa dest
    ops = build_plan([a, b], [], set(), SNAP, TARGETS)
    conflicts = check(ops, {1: a, 2: b}, [], set(), SNAP, TARGETS)
    assert any(c.kind == "collision" for c in conflicts)


def test_missing_template_data():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre=None,
                        path="/lib/x.mp3", ext="mp3")
    conflicts = check([], {1: f}, [], set(), SNAP, TARGETS)
    assert any(c.kind == "missing_template_data" and c.file_id == 1 for c in conflicts)


def test_outside_root():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre="House",
                        path="/lib/x.mp3", ext="mp3")
    bad_op = PlanOpComputed("MOVE", 1, {"path": "/lib/x.mp3"}, {"path": "/altrove/A - T.mp3"})
    conflicts = check([bad_op], {1: f}, [], set(), SNAP, TARGETS)
    assert any(c.kind == "outside_root" for c in conflicts)


def test_removed_file_not_missing_data():
    f = make_audio_file(1, root_id=1, artist="A", title="T", genre=None,
                        path="/lib/x.mp3", ext="mp3")
    # rimosso: niente rinomina → niente conflitto missing_data
    assert check([], {1: f}, [], {1}, SNAP, TARGETS) == []
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_conflict.py -v`
Expected: ImportError su `check`.

- [ ] **Step 3: Implementa `backend/app/services/conflict.py`**

```python
"""Conflict: valida il piano. Puro, deterministico."""

import os
from dataclasses import dataclass

from app.services import planner


@dataclass(frozen=True)
class ConflictComputed:
    kind: str
    file_id: int
    detail: str


def _is_under(path: str, base: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(base)]) \
            == os.path.abspath(base)
    except ValueError:
        return False


def check(plan_ops, files_by_id, accepted_issues, removals, settings_snapshot,
          root_targets) -> list[ConflictComputed]:
    removals = set(removals)
    conflicts: list[ConflictComputed] = []

    move_ops = [op for op in plan_ops if op.kind in ("RENAME", "MOVE")]
    dest_count: dict[str, int] = {}
    for op in move_ops:
        dest = op.after["path"]
        dest_count[dest] = dest_count.get(dest, 0) + 1
    moved_ids = {op.file_id for op in move_ops}
    occupied = {f.path for fid, f in files_by_id.items() if fid not in moved_ids}

    for op in move_ops:
        dest = op.after["path"]
        if dest_count[dest] > 1 or dest in occupied:
            conflicts.append(ConflictComputed("collision", op.file_id,
                                              f"collisione destinazione: {dest}"))
        file = files_by_id.get(op.file_id)
        target = root_targets.get(file.root_id) if file else None
        if target is not None and not _is_under(dest, target):
            conflicts.append(ConflictComputed("outside_root", op.file_id,
                                              f"destinazione fuori radice: {dest}"))

    by_file = planner.fixes_by_file(accepted_issues)
    for fid, file in files_by_id.items():
        if fid in removals:
            continue
        tags = planner.effective_tags(file, by_file.get(fid, []))
        _dest, miss = planner.render_destination(file, tags, settings_snapshot, root_targets)
        if miss is not None:
            conflicts.append(ConflictComputed("missing_template_data", fid,
                                              f"campo mancante per il template: {miss}"))
    return conflicts
```

- [ ] **Step 4: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_conflict.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/conflict.py backend/tests/test_conflict.py
git commit -m "feat: Conflict — collisione, dati mancanti, fuori radice (puro)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Planning — settings (seed/update/target) + schemi

**Files:**
- Create: `backend/app/services/planning.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_planning.py`

**Interfaces:**
- Consumes: `app.models` (Settings, ScanRoot, utcnow), `app.db`.
- Produces:
  - `planning.get_settings(db) -> Settings` (seed coi default se assente), `planning.update_settings(db, naming_template=None, folder_template=None) -> Settings`, `planning.set_root_target(db, root_id, target_root) -> ScanRoot | None`, `planning.root_targets(db) -> dict[int, str]`.
  - `app.schemas.RootTargetRead`, `SettingsRead`, `SettingsUpdate`, `RootTargetUpdate`.

- [ ] **Step 1: Aggiungi gli schemi settings a `backend/app/schemas.py`**

```python
class RootTargetRead(BaseModel):
    id: int
    path: str
    label: str | None
    target_root: str | None


class SettingsRead(BaseModel):
    naming_template: str
    folder_template: str
    roots: list[RootTargetRead]


class SettingsUpdate(BaseModel):
    naming_template: str | None = None
    folder_template: str | None = None


class RootTargetUpdate(BaseModel):
    target_root: str | None = None
```

- [ ] **Step 2: Scrivi i test che falliscono — `backend/tests/test_planning.py`**

```python
from app.models import ScanRoot
from app.services import planning


def test_get_settings_seeds_defaults(db):
    s = planning.get_settings(db)
    assert s.naming_template == "{artist} - {title}"
    assert s.folder_template == "{genre}/{artist}"


def test_update_settings(db):
    planning.get_settings(db)
    s = planning.update_settings(db, folder_template="{genre}")
    assert s.folder_template == "{genre}" and s.naming_template == "{artist} - {title}"


def test_set_root_target_and_map(db):
    root = ScanRoot(id=1, path="/lib")
    db.add(root)
    db.commit()
    planning.set_root_target(db, 1, "/lib/Library")
    assert planning.root_targets(db) == {1: "/lib/Library"}
    planning.set_root_target(db, 1, None)  # in-place → la radice stessa
    assert planning.root_targets(db) == {1: "/lib"}
```

- [ ] **Step 3: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_planning.py -v`
Expected: ImportError su `planning`.

- [ ] **Step 4: Crea `backend/app/services/planning.py` (parte settings)**

```python
"""Orchestratore Plan/Conflict: settings + costruzione/lettura del piano."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScanRoot, Settings, utcnow

DEFAULT_NAMING = "{artist} - {title}"
DEFAULT_FOLDER = "{genre}/{artist}"


def get_settings(db: Session) -> Settings:
    s = db.get(Settings, 1)
    if s is None:
        s = Settings(id=1, naming_template=DEFAULT_NAMING, folder_template=DEFAULT_FOLDER)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def update_settings(db: Session, naming_template=None, folder_template=None) -> Settings:
    s = get_settings(db)
    if naming_template is not None:
        s.naming_template = naming_template
    if folder_template is not None:
        s.folder_template = folder_template
    s.updated_at = utcnow()
    db.commit()
    db.refresh(s)
    return s


def set_root_target(db: Session, root_id: int, target_root) -> ScanRoot | None:
    root = db.get(ScanRoot, root_id)
    if root is None:
        return None
    root.target_root = target_root
    db.commit()
    db.refresh(root)
    return root


def root_targets(db: Session) -> dict[int, str]:
    return {r.id: (r.target_root or r.path) for r in db.scalars(select(ScanRoot)).all()}
```

- [ ] **Step 5: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_planning.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/planning.py backend/app/schemas.py backend/tests/test_planning.py
git commit -m "feat: planning settings — seed/update template + target_root per-radice

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Planning — create_plan / load_plan + stats

**Files:**
- Modify: `backend/app/services/planning.py`, `backend/app/schemas.py`
- Test: `backend/tests/test_planning.py` (aggiunge casi plan)

**Interfaces:**
- Consumes: Task 4, `planner.build_plan`, `conflict.check`, `app.models` (AudioFile, Issue, DupMember, Plan, PlanOp).
- Produces:
  - `app.schemas.PlanOpRead`, `ConflictRead`, `PlanStats`, `PlanRead`.
  - `planning.create_plan(db) -> PlanRead`, `planning.load_plan(db) -> PlanRead | None`.

- [ ] **Step 1: Aggiungi gli schemi plan a `backend/app/schemas.py`**

```python
class PlanOpRead(BaseModel):
    id: int
    seq: int
    kind: str
    file_id: int
    file_path: str
    before: dict
    after: dict
    status: str


class ConflictRead(BaseModel):
    kind: str
    file_id: int
    detail: str


class PlanStats(BaseModel):
    n_retag: int = 0
    n_rename: int = 0
    n_move: int = 0
    n_delete: int = 0
    space_freed_bytes: int = 0
    n_conflicts: int = 0
    blocking: bool = False


class PlanRead(BaseModel):
    id: int
    status: str
    created_at: datetime
    rules: dict
    ops: list[PlanOpRead]
    conflicts: list[ConflictRead]
    stats: PlanStats
```

- [ ] **Step 2: Scrivi i test che falliscono in `backend/tests/test_planning.py`**

```python
from sqlalchemy import select

from app.models import AudioFile, Issue, Plan, PlanOp


def _file(db, fid, **kw):
    defaults = dict(id=fid, root_id=1, path=f"/lib/varie/{fid}.mp3", ext="mp3", size_bytes=1000,
                    hash_method="file", status="present", has_cover=False,
                    artist="A", title=f"T{fid}", genre="House")
    defaults.update(kw)
    f = AudioFile(**defaults)
    db.add(f)
    db.commit()
    return f


def test_create_plan_persists_and_replaces_draft(db):
    db.add(ScanRoot(id=1, path="/lib"))
    _file(db, 1)
    p1 = planning.create_plan(db)
    assert p1.stats.n_move == 1
    assert db.scalar(select(Plan)) is not None
    p2 = planning.create_plan(db)  # sostituisce il draft
    assert len(db.scalars(select(Plan)).all()) == 1  # un solo draft
    assert len(db.scalars(select(PlanOp)).all()) == p2.stats.n_move


def test_plan_includes_retag_and_delete_and_stats(db):
    db.add(ScanRoot(id=1, path="/lib"))
    _file(db, 1, artist="PINCO")
    _file(db, 2)
    db.add(Issue(file_id=1, type="inconsistent_casing", field="artist", severity="warning",
                 detail="", suggested_fix_json={"field": "artist", "action": "retag",
                 "to": "Pinco"}, status="accepted"))
    from app.models import DupMember, DupGroup
    db.add(DupGroup(id=1, match_kind="exact", keeper_file_id=1, signature="s"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    db.commit()
    p = planning.create_plan(db)
    assert p.stats.n_retag == 1 and p.stats.n_delete == 1
    assert p.stats.space_freed_bytes == 1000
    kinds = [o.kind for o in p.ops]
    assert kinds.index("RETAG") < kinds.index("DELETE")  # ordine


def test_load_plan_none_when_absent(db):
    assert planning.load_plan(db) is None
```

- [ ] **Step 3: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_planning.py -v`
Expected: i nuovi test falliscono (`create_plan`/`load_plan` assenti).

- [ ] **Step 4: Aggiungi `create_plan`/`load_plan` a `backend/app/services/planning.py`**

Aggiungi gli import e le funzioni:

```python
from app.models import AudioFile, DupMember, Issue, Plan, PlanOp
from app.schemas import ConflictRead, PlanOpRead, PlanRead, PlanStats
from app.services import conflict
from app.services.planner import PlanOpComputed, build_plan


def _inputs(db):
    files = db.scalars(
        select(AudioFile).where(AudioFile.status == "present", AudioFile.scan_error.is_(None))
    ).all()
    accepted = db.scalars(select(Issue).where(Issue.status == "accepted")).all()
    removals = {m.file_id for m in db.scalars(
        select(DupMember).where(DupMember.action == "remove")).all()}
    s = get_settings(db)
    snapshot = {"naming_template": s.naming_template, "folder_template": s.folder_template}
    return files, accepted, removals, snapshot, root_targets(db)


def create_plan(db: Session) -> PlanRead:
    files, accepted, removals, snapshot, targets = _inputs(db)
    computed = build_plan(files, accepted, removals, snapshot, targets)
    for old in db.scalars(select(Plan).where(Plan.status == "draft")).all():
        db.delete(old)
    db.flush()
    rules = {**snapshot, "targets": {str(k): v for k, v in targets.items()}}
    plan = Plan(status="draft", rules_json=rules)
    db.add(plan)
    db.flush()
    for seq, op in enumerate(computed):
        db.add(PlanOp(plan_id=plan.id, seq=seq, kind=op.kind, file_id=op.file_id,
                      before_json=op.before, after_json=op.after, status="pending"))
    db.commit()
    return load_plan(db)


def load_plan(db: Session) -> PlanRead | None:
    plan = db.scalar(select(Plan).where(Plan.status == "draft").order_by(Plan.id.desc()))
    if plan is None:
        return None
    ops = db.scalars(select(PlanOp).where(PlanOp.plan_id == plan.id)
                     .order_by(PlanOp.seq)).all()
    files, accepted, removals, snapshot, targets = _inputs(db)
    files_by_id = {f.id: f for f in files}
    op_computed = [PlanOpComputed(o.kind, o.file_id, o.before_json, o.after_json) for o in ops]
    conflicts = conflict.check(op_computed, files_by_id, accepted, removals, snapshot, targets)

    counts = {"RETAG": 0, "RENAME": 0, "MOVE": 0, "DELETE": 0}
    space = 0
    for o in ops:
        counts[o.kind] = counts.get(o.kind, 0) + 1
        if o.kind == "DELETE":
            f = files_by_id.get(o.file_id)
            space += (f.size_bytes or 0) if f else 0
    stats = PlanStats(n_retag=counts["RETAG"], n_rename=counts["RENAME"],
                      n_move=counts["MOVE"], n_delete=counts["DELETE"],
                      space_freed_bytes=space, n_conflicts=len(conflicts),
                      blocking=len(conflicts) > 0)
    op_reads = [PlanOpRead(id=o.id, seq=o.seq, kind=o.kind, file_id=o.file_id,
                           file_path=files_by_id[o.file_id].path if o.file_id in files_by_id else "",
                           before=o.before_json, after=o.after_json, status=o.status)
                for o in ops]
    conflict_reads = [ConflictRead(kind=c.kind, file_id=c.file_id, detail=c.detail)
                      for c in conflicts]
    return PlanRead(id=plan.id, status=plan.status, created_at=plan.created_at,
                    rules=plan.rules_json, ops=op_reads, conflicts=conflict_reads, stats=stats)
```

- [ ] **Step 5: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_planning.py -v`
Expected: tutti passano (settings + plan).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/planning.py backend/app/schemas.py backend/tests/test_planning.py
git commit -m "feat: planning create_plan/load_plan + stats + conflitti

Costruisce un draft (sostituendo il precedente), persiste plan/plan_op,
ricalcola i conflitti e le statistiche (conteggi + spazio liberato).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Router SETTINGS

**Files:**
- Create: `backend/app/routers/settings.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_settings_api.py`

**Interfaces:**
- Consumes: `planning` (get_settings, update_settings, set_root_target), `app.models.ScanRoot`, `app.schemas` (SettingsRead, SettingsUpdate, RootTargetUpdate, RootTargetRead).
- Produces: `app.routers.settings.router`: `GET /api/settings`, `PUT /api/settings`, `PUT /api/settings/roots/{root_id}/target`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_settings_api.py`**

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import ScanRoot


def test_get_settings_defaults(db):
    with TestClient(app) as client:
        body = client.get("/api/settings").json()
        assert body["naming_template"] == "{artist} - {title}"
        assert body["folder_template"] == "{genre}/{artist}"
        assert body["roots"] == []


def test_update_settings(db):
    with TestClient(app) as client:
        resp = client.put("/api/settings", json={"folder_template": "{genre}"})
        assert resp.status_code == 200 and resp.json()["folder_template"] == "{genre}"


def test_set_root_target(db):
    db.add(ScanRoot(id=1, path="/lib"))
    db.commit()
    with TestClient(app) as client:
        ok = client.put("/api/settings/roots/1/target", json={"target_root": "/lib/Library"})
        assert ok.status_code == 200
        roots = client.get("/api/settings").json()["roots"]
        assert roots[0]["target_root"] == "/lib/Library"


def test_set_target_non_absolute_rejected(db):
    db.add(ScanRoot(id=1, path="/lib"))
    db.commit()
    with TestClient(app) as client:
        assert client.put("/api/settings/roots/1/target",
                          json={"target_root": "relativo"}).status_code == 400
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_settings_api.py -v`
Expected: ImportError / 404.

- [ ] **Step 3: Implementa `backend/app/routers/settings.py`**

```python
"""Router SETTINGS: template globali + target_root per-radice. Sottile."""

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ScanRoot
from app.schemas import RootTargetRead, RootTargetUpdate, SettingsRead, SettingsUpdate
from app.services import planning

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _read(db: Session) -> SettingsRead:
    s = planning.get_settings(db)
    roots = [RootTargetRead(id=r.id, path=r.path, label=r.label, target_root=r.target_root)
             for r in db.scalars(select(ScanRoot)).all()]
    return SettingsRead(naming_template=s.naming_template,
                        folder_template=s.folder_template, roots=roots)


@router.get("", response_model=SettingsRead)
def get_settings(db: Session = Depends(get_db)):
    return _read(db)


@router.put("", response_model=SettingsRead)
def put_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    planning.update_settings(db, naming_template=body.naming_template,
                             folder_template=body.folder_template)
    return _read(db)


@router.put("/roots/{root_id}/target", response_model=SettingsRead)
def put_root_target(root_id: int, body: RootTargetUpdate, db: Session = Depends(get_db)):
    if body.target_root is not None and not os.path.isabs(body.target_root):
        raise HTTPException(status_code=400, detail="target_root deve essere un path assoluto")
    if planning.set_root_target(db, root_id, body.target_root) is None:
        raise HTTPException(status_code=404, detail="radice non trovata")
    return _read(db)
```

- [ ] **Step 4: Includi il router in `backend/app/main.py`**

```python
from app.routers import analyze, duplicates, issues, scan, settings, sources
```
```python
app.include_router(duplicates.router)
app.include_router(settings.router)
```

- [ ] **Step 5: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_settings_api.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/settings.py backend/app/main.py backend/tests/test_settings_api.py
git commit -m "feat: router SETTINGS — template globali + target_root per-radice

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Router PLAN

**Files:**
- Create: `backend/app/routers/plan.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_plan_api.py`

**Interfaces:**
- Consumes: `planning` (create_plan, load_plan), `app.schemas.PlanRead`.
- Produces: `app.routers.plan.router`: `POST /api/plan`, `GET /api/plan`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_plan_api.py`**

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, ScanRoot


def _seed(db):
    db.add(ScanRoot(id=1, path="/lib"))
    db.add(AudioFile(id=1, root_id=1, path="/lib/varie/x.mp3", ext="mp3", size_bytes=1000,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    db.commit()


def test_get_plan_404_when_absent(db):
    with TestClient(app) as client:
        assert client.get("/api/plan").status_code == 404


def test_post_then_get_plan(db):
    _seed(db)
    with TestClient(app) as client:
        created = client.post("/api/plan")
        assert created.status_code == 200
        body = created.json()
        assert body["stats"]["n_move"] == 1
        assert body["ops"][0]["after"]["path"] == "/lib/House/A/A - T.mp3"
        got = client.get("/api/plan").json()
        assert got["id"] == body["id"]


def test_plan_reports_conflict_on_missing_data(db):
    db.add(ScanRoot(id=1, path="/lib"))
    db.add(AudioFile(id=1, root_id=1, path="/lib/x.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre=None))  # genre mancante
    db.commit()
    with TestClient(app) as client:
        body = client.post("/api/plan").json()
        assert body["stats"]["blocking"] is True
        assert any(c["kind"] == "missing_template_data" for c in body["conflicts"])
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_plan_api.py -v`
Expected: 404 su `/api/plan` (POST non esiste).

- [ ] **Step 3: Implementa `backend/app/routers/plan.py`**

```python
"""Router PLAN: costruisce e legge il piano draft. Sottile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import PlanRead
from app.services import planning

router = APIRouter(prefix="/api/plan", tags=["plan"])


@router.post("", response_model=PlanRead)
def post_plan(db: Session = Depends(get_db)):
    return planning.create_plan(db)


@router.get("", response_model=PlanRead)
def get_plan(db: Session = Depends(get_db)):
    plan = planning.load_plan(db)
    if plan is None:
        raise HTTPException(status_code=404, detail="nessun piano draft")
    return plan
```

- [ ] **Step 4: Includi il router in `backend/app/main.py`**

```python
from app.routers import analyze, duplicates, issues, plan, scan, settings, sources
```
```python
app.include_router(settings.router)
app.include_router(plan.router)
```

- [ ] **Step 5: Esegui l'intera suite e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -v`
Expected: tutti i test passano (chunk 1 + 2 + 3), output pristine.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/plan.py backend/app/main.py backend/tests/test_plan_api.py
git commit -m "feat: router PLAN — POST /api/plan (build draft) + GET /api/plan

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verifica finale del chunk

- [ ] **Suite verde e pristine:** `cd backend && source .venv/bin/activate && python -m pytest tests -v`.
- [ ] **End-to-end reale:** `uvicorn app.main:app --port 8010`; scan di una cartella, accetta un issue + scegli un keeper, imposta i template/target in SETTINGS, `POST /api/plan`, `GET /api/plan` mostra ops (diff prima→dopo) + conflitti + stats; le destinazioni restano sotto la target_root della radice.
- [ ] **Definition of Done** della spec §12 soddisfatta.

## Self-Review (svolto in fase di scrittura)

- **Spec coverage:** modelli settings/plan/plan_op + scan_root.target_root + ensure_schema ALTER (Task 1) ✓; Planner con RETAG/effective-tags/RENAME-MOVE/DELETE/sanitize/missing-no-op/ordine (Task 2) ✓; Conflict collisione/missing/outside (Task 3) ✓; settings seed/update/target (Task 4) ✓; create_plan/load_plan + stats + conflitti (Task 5) ✓; router settings (Task 6) ✓; router plan (Task 7) ✓.
- **Placeholder scan:** nessun TODO/TBD; codice completo.
- **Type consistency:** `PlanOpComputed(kind,file_id,before,after)` e `ConflictComputed(kind,file_id,detail)` coerenti; `render_destination`/`effective_tags`/`fixes_by_file` firma condivisa tra planner e conflict; `build_plan`/`check` firme coerenti con `planning._inputs`; schemi `PlanRead`/`PlanOpRead`/`ConflictRead`/`PlanStats` allineati a `load_plan`.
```
