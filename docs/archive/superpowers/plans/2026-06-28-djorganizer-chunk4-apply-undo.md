# DjOrganizer Chunk 4 — Apply + Undo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eseguire un piano draft sui file veri (retag, rinomina/sposta atomico con fallback cross-disco, delete-in-quarantena) registrando un undo-journal per ogni operazione, e saperlo annullare — con l'invariante `apply` poi `undo` == stato iniziale.

**Architecture:** Integrazioni di basso livello (`tagio.write_tags`, `fsops.safe_move`/`quarantine_path_for`) + motore `apply.py` (pre-volo: ricalcolo conflitti sullo snapshot + ri-validazione stale; esecuzione in ordine sicuro col riordino delete-prima-di-move; **journal subito dopo ogni mutazione riuscita**, commit per-op) + motore `undo.py` (inverte il journal in ordine inverso). Apply è un job async (port da `scan_job`); Undo sincrono.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2, mutagen, pytest. Nessuna nuova dipendenza.

**Spec di riferimento:** [docs/superpowers/specs/2026-06-28-djorganizer-chunk4-apply-undo-design.md](../specs/2026-06-28-djorganizer-chunk4-apply-undo-design.md)

## Global Constraints

- **Mai overwrite** (`safe_move` rifiuta una destinazione esistente) e **mai hard-delete** (DELETE = quarantena).
- **Journal subito dopo la mutazione riuscita** (non prima): se un'op solleva, non lascia una riga di journal per un'op non avvenuta → l'undo resta coerente. Commit per-op (niente mega-transazione).
- **Ordine sicuro** RETAG → RENAME/MOVE → DELETE, col **riordino**: un MOVE la cui destinazione è occupata da un file in DELETE → quel DELETE va in quarantena prima.
- **Pre-volo:** ricalcolo conflitti con lo **snapshot del piano** (`plan.rules_json`) sui file vivi (riusa `conflict.check`); ri-validazione **stale** (file esiste + path/tag combaciano col `before`) → su mismatch **abort senza mutare**.
- **Quarantena** `<root>/.quarantine/<relpath>`; nome univocizzato se esiste.
- **Move cross-disco:** `os.rename`; su EXDEV → `copy2` + verifica `content_hash` + `os.replace` + `remove(src)`.
- **`content_hash` invariato dopo un retag** (hash dello stream, non dei tag).
- **Undo** inverte le righe `reversed=False` in `op_seq` decrescente, marcandole `reversed=True`.
- `plan.status`: `draft → applied → undone` (anche una run parziale → `applied` con `partial=True`).
- **Output pristine** sotto `filterwarnings = error`. SQLAlchemy 2.0, no Alembic, router sottili, `utcnow()` tz-aware, job stile `scan_job`.
- Comandi: `cd backend && source .venv/bin/activate && python -m pytest tests`.
- Commit: prefisso conventional, italiano, footer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```text
backend/app/
  models.py              # MOD: UndoJournal
  schemas.py             # MOD: ApplyResult, UndoResult, HistoryItem
  integrations/
    tagio.py             # MOD: write_tags + TagWriteError
    fsops.py             # NEW: FsOpError, safe_move, quarantine_path_for
  services/
    apply.py             # NEW: apply_plan(db, plan, on_progress) -> ApplyResult
    apply_job.py         # NEW: job shell (port da scan_job)
    undo.py              # NEW: undo_run(db, plan) -> UndoResult
  routers/
    apply.py             # NEW: POST /api/apply, GET /api/apply/status
    history.py           # NEW: GET /api/history, POST /api/history/{plan_id}/undo
  main.py                # MOD: include apply, history
backend/tests/
  test_undo_journal_schema.py · test_tagio_write.py · test_fsops.py · test_apply_preflight.py
  test_apply_exec.py · test_undo.py · test_apply_undo_invariant.py · test_apply_api.py
```

---

## Task 1: Modello UndoJournal

**Files:** Modify `backend/app/models.py` · Test `backend/tests/test_undo_journal_schema.py`

**Interfaces:**
- Produces: `app.models.UndoJournal` (run_id, op_seq, kind, file_id, from_path, to_path, prior_tags_json, quarantine_path, applied_at, reversed).

- [ ] **Step 1: Aggiungi il modello in `backend/app/models.py`** (in fondo)

```python
class UndoJournal(Base):
    __tablename__ = "undo_journal"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("plan.id"), index=True)
    op_seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)
    file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"), index=True)
    from_path: Mapped[str | None] = mapped_column(String)
    to_path: Mapped[str | None] = mapped_column(String)
    prior_tags_json: Mapped[dict | None] = mapped_column(JSON)
    quarantine_path: Mapped[str | None] = mapped_column(String)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 2: Test che fallisce — `backend/tests/test_undo_journal_schema.py`**

```python
from sqlalchemy import inspect

from app.db import engine


def test_undo_journal_table():
    cols = {c["name"] for c in inspect(engine).get_columns("undo_journal")}
    assert {"run_id", "op_seq", "kind", "file_id", "from_path", "to_path",
            "prior_tags_json", "quarantine_path", "reversed"} <= cols
```

- [ ] **Step 3: Esegui e verifica PASS** · Run: `python -m pytest tests/test_undo_journal_schema.py -v` · Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py backend/tests/test_undo_journal_schema.py
git commit -m "feat: modello undo_journal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: tagio.write_tags (prima scrittura)

**Files:** Modify `backend/app/integrations/tagio.py` · Test `backend/tests/test_tagio_write.py`

**Interfaces:**
- Consumes: fixtures, `content_hash.compute`.
- Produces: `tagio.write_tags(path: str, changes: dict) -> None`, `tagio.TagWriteError`.

- [ ] **Step 1: Test che fallisce — `backend/tests/test_tagio_write.py`**

```python
from app.integrations import tagio
from app.integrations.content_hash import compute


def test_write_then_read(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_tags(f, {"artist": "Pinco", "title": "Titolo"})
    tags = tagio.read_tags(f)
    assert tags.artist == "Pinco" and tags.title == "Titolo"


def test_content_hash_stable_after_write(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    before = compute(f, ".flac")[0]
    tagio.write_tags(f, {"artist": "Nuovo Artista"})
    assert compute(f, ".flac")[0] == before  # hash dello stream invariato


def test_clear_field(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_tags(f, {"artist": "X"})
    tagio.write_tags(f, {"artist": None})
    assert tagio.read_tags(f).artist is None
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO** · Run: `python -m pytest tests/test_tagio_write.py -v` · Expected: AttributeError (`write_tags` assente).

- [ ] **Step 3: Implementa in `backend/app/integrations/tagio.py`**

Aggiungi (in cima all'`import` mutagen c'è già `MutagenError`):

```python
class TagWriteError(Exception):
    """Scrittura tag fallita."""


_EASY_WRITE_KEY = {
    "artist": "artist", "title": "title", "album": "album",
    "album_artist": "albumartist", "genre": "genre", "year": "date",
    "label": "organization", "track_no": "tracknumber", "comment": "comment",
}


def write_tags(path: str, changes: dict) -> None:
    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            raise TagWriteError(f"formato non scrivibile: {path}")
        if audio.tags is None:
            audio.add_tags()
        for field, value in changes.items():
            key = _EASY_WRITE_KEY.get(field, field)
            try:
                if value is None or (isinstance(value, str) and not value.strip()):
                    if key in audio:
                        del audio[key]
                else:
                    audio[key] = str(value)
            except (KeyError, ValueError):
                continue  # campo non supportato dal formato easy → best-effort, salta
        audio.save()
    except MutagenError as exc:
        raise TagWriteError(str(exc)) from exc
```

- [ ] **Step 4: Esegui e verifica PASS** · Run: `python -m pytest tests/test_tagio_write.py -v` · Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/tagio.py backend/tests/test_tagio_write.py
git commit -m "feat: tagio.write_tags — scrittura tag (best-effort per campo), content_hash invariato

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: fsops — spostamenti sicuri + quarantena

**Files:** Create `backend/app/integrations/fsops.py` · Test `backend/tests/test_fsops.py`

**Interfaces:**
- Consumes: `content_hash.compute`.
- Produces: `fsops.FsOpError`, `fsops.safe_move(src, dst) -> None`, `fsops.quarantine_path_for(path, root_path) -> str`.

- [ ] **Step 1: Test che fallisce — `backend/tests/test_fsops.py`**

```python
import errno
import os

import pytest

from app.integrations import fsops


def test_safe_move_renames(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    dst = tmp_path / "sub" / "b.txt"
    fsops.safe_move(str(src), str(dst))
    assert dst.read_text() == "x" and not src.exists()


def test_safe_move_refuses_existing_dst(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("x")
    dst = tmp_path / "b.txt"; dst.write_text("y")
    with pytest.raises(fsops.FsOpError):
        fsops.safe_move(str(src), str(dst))
    assert src.exists() and dst.read_text() == "y"


def test_quarantine_path_preserves_relpath(tmp_path):
    root = tmp_path / "lib"
    f = root / "House" / "x.mp3"
    f.parent.mkdir(parents=True)
    f.write_text("z")
    q = fsops.quarantine_path_for(str(f), str(root))
    assert q == str(root / ".quarantine" / "House" / "x.mp3")


def test_cross_device_fallback(copy_fixture, tmp_path, monkeypatch):
    src = copy_fixture("flac", tmp_path / "a.flac")
    dst = tmp_path / "moved.flac"
    real_rename = os.rename

    def fake_rename(a, b):
        raise OSError(errno.EXDEV, "cross-device")
    monkeypatch.setattr(os, "rename", fake_rename)
    fsops.safe_move(src, str(dst))
    monkeypatch.setattr(os, "rename", real_rename)
    assert dst.exists() and not os.path.exists(src)
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO** · Run: `python -m pytest tests/test_fsops.py -v` · Expected: ModuleNotFoundError.

- [ ] **Step 3: Implementa `backend/app/integrations/fsops.py`**

```python
"""Operazioni filesystem sicure per Apply/Undo: mai overwrite, fallback cross-disco."""

import errno
import os
import shutil

from app.integrations.content_hash import compute


class FsOpError(Exception):
    """Operazione FS rifiutata o fallita."""


def safe_move(src: str, dst: str) -> None:
    if os.path.exists(dst):
        raise FsOpError(f"destinazione già esistente: {dst}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.rename(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        ext = os.path.splitext(src)[1]
        tmp = dst + ".tmp"
        shutil.copy2(src, tmp)
        if compute(tmp, ext)[0] != compute(src, ext)[0]:
            os.remove(tmp)
            raise FsOpError(f"verifica hash fallita copiando {src}") from exc
        os.replace(tmp, dst)
        os.remove(src)


def quarantine_path_for(path: str, root_path: str) -> str:
    rel = os.path.relpath(path, root_path)
    q = os.path.join(root_path, ".quarantine", rel)
    base, i = q, 1
    while os.path.exists(q):
        q = f"{base}.{i}"
        i += 1
    return q
```

- [ ] **Step 4: Esegui e verifica PASS** · Run: `python -m pytest tests/test_fsops.py -v` · Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/fsops.py backend/tests/test_fsops.py
git commit -m "feat: fsops — safe_move (no overwrite, fallback cross-disco) + quarantine_path_for

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Apply — pre-volo (conflitti snapshot + stale)

**Files:** Create `backend/app/services/apply.py` · Modify `backend/app/schemas.py` · Test `backend/tests/test_apply_preflight.py`

**Interfaces:**
- Consumes: `app.models` (PlanOp, AudioFile, Issue, DupMember, Plan, ScanRoot, utcnow), `app.services.conflict`, `app.services.planner.PlanOpComputed`, `tagio`.
- Produces:
  - `app.schemas.ApplyResult` (`run_id, applied_ops, refused, stale, partial, failed_op_seq, error, reason, started_at, finished_at`).
  - `apply.apply_plan(db, plan, on_progress=None) -> ApplyResult` (in questo task: solo pre-volo; l'esecuzione arriva nel Task 5).
  - `apply._stale_op(ops, files_by_id) -> int | None`, `apply._root_path(db, root_id) -> str`, `apply._tag_value(tags, field)`.

- [ ] **Step 1: Aggiungi `ApplyResult` a `backend/app/schemas.py`**

```python
class ApplyResult(BaseModel):
    run_id: int | None = None
    applied_ops: int = 0
    refused: bool = False
    stale: bool = False
    partial: bool = False
    failed_op_seq: int | None = None
    error: str | None = None
    reason: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

- [ ] **Step 2: Test che fallisce — `backend/tests/test_apply_preflight.py`**

```python
from app.models import AudioFile, Plan, PlanOp, ScanRoot
from app.services.apply import apply_plan


def _setup(db, tmp_path, *, before_path):
    root = tmp_path / "lib"
    root.mkdir()
    db.add(ScanRoot(id=1, path=str(root)))
    db.add(AudioFile(id=1, root_id=1, path=str(root / "x.flac"), ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    plan = Plan(id=1, status="draft",
                rules_json={"naming_template": "{artist} - {title}",
                            "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": before_path},
                  after_json={"path": str(root / "House" / "A" / "A - T.flac")}, status="pending"))
    db.commit()
    return plan


def test_refused_on_blocking_conflict(db, tmp_path, copy_fixture):
    # due file che renderizzano alla stessa destinazione → collisione bloccante
    root = tmp_path / "lib"; root.mkdir()
    for i in (1, 2):
        copy_fixture("flac", root / f"{i}.flac")
    db.add(ScanRoot(id=1, path=str(root)))
    db.add(AudioFile(id=1, root_id=1, path=str(root / "1.flac"), ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    db.add(AudioFile(id=2, root_id=1, path=str(root / "2.flac"), ext="flac", size_bytes=1,
                     hash_method="file", status="present", has_cover=False,
                     artist="A", title="T", genre="House"))
    plan = Plan(id=1, status="draft",
                rules_json={"naming_template": "{artist} - {title}",
                            "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    dest = str(root / "House" / "A" / "A - T.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": str(root / "1.flac")}, after_json={"path": dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="MOVE", file_id=2,
                  before_json={"path": str(root / "2.flac")}, after_json={"path": dest}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.refused is True


def test_stale_when_before_path_mismatch(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    plan = _setup(db, tmp_path, before_path=str(tmp_path / "lib" / "ALTRO.flac"))  # before ≠ path reale
    res = apply_plan(db, plan)
    assert res.stale is True and res.failed_op_seq == 0
```

- [ ] **Step 3: Esegui e verifica che FALLISCANO** · Run: `python -m pytest tests/test_apply_preflight.py -v` · Expected: ImportError su `apply_plan`.

- [ ] **Step 4: Implementa `backend/app/services/apply.py` (solo pre-volo)**

```python
"""Motore Apply: pre-volo (conflitti snapshot + stale) e — nel Task 5 — esecuzione."""

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import tagio
from app.models import AudioFile, DupMember, Issue, Plan, PlanOp, ScanRoot, utcnow
from app.schemas import ApplyResult
from app.services import conflict
from app.services.planner import PlanOpComputed


def _root_path(db: Session, root_id: int) -> str:
    root = db.get(ScanRoot, root_id)
    return root.path if root else ""


def _tag_value(tags, field):
    return getattr(tags, field, None)


def _stale_op(ops, files_by_id) -> int | None:
    for o in ops:
        f = files_by_id.get(o.file_id)
        if f is None or not os.path.exists(f.path):
            return o.seq
        if o.kind in ("RENAME", "MOVE", "DELETE"):
            if o.before_json.get("path") != f.path:
                return o.seq
        elif o.kind == "RETAG":
            tags = tagio.read_tags(f.path)
            for field, old in o.before_json.items():
                if _tag_value(tags, field) != old:
                    return o.seq
    return None


def _inputs(db: Session, plan: Plan):
    ops = db.scalars(select(PlanOp).where(PlanOp.plan_id == plan.id)
                     .order_by(PlanOp.seq)).all()
    files = {f.id: f for f in db.scalars(
        select(AudioFile).where(AudioFile.status == "present",
                                AudioFile.scan_error.is_(None))).all()}
    snapshot = {"naming_template": plan.rules_json["naming_template"],
                "folder_template": plan.rules_json["folder_template"]}
    targets = {int(k): v for k, v in plan.rules_json.get("targets", {}).items()}
    accepted = db.scalars(select(Issue).where(Issue.status == "accepted")).all()
    removals = {m.file_id for m in db.scalars(
        select(DupMember).where(DupMember.action == "remove")).all()}
    return ops, files, snapshot, targets, accepted, removals


def apply_plan(db: Session, plan: Plan, on_progress=None) -> ApplyResult:
    started = utcnow()
    ops, files, snapshot, targets, accepted, removals = _inputs(db, plan)
    op_computed = [PlanOpComputed(o.kind, o.file_id, o.before_json, o.after_json) for o in ops]
    if conflict.check(op_computed, files, accepted, removals, snapshot, targets):
        return ApplyResult(refused=True, reason="conflitti bloccanti",
                           started_at=started, finished_at=utcnow())
    stale = _stale_op(ops, files)
    if stale is not None:
        return ApplyResult(stale=True, failed_op_seq=stale, reason="piano stale",
                           started_at=started, finished_at=utcnow())
    # Task 5 inserisce qui l'esecuzione; per ora ritorna un risultato "nessuna op".
    return ApplyResult(run_id=plan.id, applied_ops=0,
                       started_at=started, finished_at=utcnow())
```

- [ ] **Step 5: Esegui e verifica PASS** · Run: `python -m pytest tests/test_apply_preflight.py -v` · Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/apply.py backend/app/schemas.py backend/tests/test_apply_preflight.py
git commit -m "feat: apply pre-volo — conflitti su snapshot + ri-validazione stale

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Apply — esecuzione (journal-dopo, riordino, parziale)

**Files:** Modify `backend/app/services/apply.py` · Test `backend/tests/test_apply_exec.py`

**Interfaces:**
- Consumes: Task 4, `fsops`, `tagio`, `app.models.UndoJournal`.
- Produces: `apply_plan` estesa (esegue RETAG/RENAME/MOVE/DELETE, scrive `undo_journal`, riordina delete-prima-di-move, gestisce il fallimento parziale, setta `plan.status='applied'`).

- [ ] **Step 1: Test che fallisce — `backend/tests/test_apply_exec.py`**

```python
import os

from sqlalchemy import select

from app.models import AudioFile, DupGroup, DupMember, Issue, Plan, PlanOp, ScanRoot, UndoJournal
from app.services.apply import apply_plan


def _af(db, fid, path, **kw):
    d = dict(id=fid, root_id=1, path=path, ext="flac", size_bytes=10, hash_method="file",
             status="present", has_cover=False, artist="A", title=f"T{fid}", genre="House")
    d.update(kw)
    db.add(AudioFile(**d))


def test_apply_move_and_delete_with_reorder(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    keeper = copy_fixture("flac", root / "varie" / "k.flac")
    dup = copy_fixture("flac", root / "House" / "A" / "A - T1.flac")  # occupa lo slot del keeper
    db.add(ScanRoot(id=1, path=str(root)))
    _af(db, 1, keeper, title="T1")   # keeper → House/A/A - T1.flac
    _af(db, 2, dup, title="T1")      # dup rimosso, è nello slot destinazione
    db.add(DupGroup(id=1, match_kind="fuzzy", keeper_file_id=1, signature="s"))
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    dest = str(root / "House" / "A" / "A - T1.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": keeper}, after_json={"path": dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="DELETE", file_id=2,
                  before_json={"path": dup}, after_json={}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.partial is False and res.applied_ops == 2
    assert os.path.exists(dest)                      # keeper spostato nello slot
    assert not os.path.exists(keeper)
    q = str(root / ".quarantine" / "House" / "A" / "A - T1.flac")
    assert os.path.exists(q)                         # dup in quarantena (delete avvenuto prima del move)
    assert plan.status == "applied"
    rows = db.scalars(select(UndoJournal).where(UndoJournal.run_id == 1)).all()
    assert {r.kind for r in rows} == {"MOVE", "DELETE"} and len(rows) == 2


def test_apply_retag(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    f = copy_fixture("flac", root / "x.flac")
    from app.integrations import tagio
    tagio.write_tags(f, {"artist": "PINCO", "title": "T"})
    db.add(ScanRoot(id=1, path=str(root)))
    _af(db, 1, f, artist="PINCO", title="T")
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "", "targets": {"1": str(root)}})  # folder vuoto → niente move
    db.add(plan)
    db.add(PlanOp(plan_id=1, seq=0, kind="RETAG", file_id=1,
                  before_json={"artist": "PINCO"}, after_json={"artist": "Pinco"}, status="pending"))
    db.commit()
    res = apply_plan(db, plan)
    assert res.applied_ops == 1
    assert tagio.read_tags(f).artist == "Pinco"
    row = db.scalar(select(UndoJournal).where(UndoJournal.kind == "RETAG"))
    assert row.prior_tags_json == {"artist": "PINCO"}  # prior letto dal file vivo
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO** · Run: `python -m pytest tests/test_apply_exec.py -v` · Expected: i due test falliscono (apply non esegue ancora).

- [ ] **Step 3: Estendi `apply_plan` in `backend/app/services/apply.py`**

Aggiungi gli import e sostituisci la riga placeholder finale con l'esecuzione:

```python
from app.integrations import fsops
from app.models import UndoJournal
```

Sostituisci il `return ApplyResult(run_id=plan.id, applied_ops=0, ...)` placeholder con:

```python
    retag_ops = [o for o in ops if o.kind == "RETAG"]
    move_ops = [o for o in ops if o.kind in ("RENAME", "MOVE")]
    del_ops = [o for o in ops if o.kind == "DELETE"]
    del_by_path = {o.before_json["path"]: o for o in del_ops}
    done: set = set()
    state = {"seq": 0, "applied": 0}
    total = len(ops)

    def _journal(kind, file_id, from_path=None, to_path=None, prior_tags=None, quarantine_path=None):
        db.add(UndoJournal(run_id=plan.id, op_seq=state["seq"], kind=kind, file_id=file_id,
                           from_path=from_path, to_path=to_path, prior_tags_json=prior_tags,
                           quarantine_path=quarantine_path))
        db.commit()
        state["seq"] += 1

    def _progress():
        state["applied"] += 1
        if on_progress is not None:
            on_progress(state["applied"], total, "applying")

    def _do_delete(o):
        f = files[o.file_id]
        q = fsops.quarantine_path_for(f.path, _root_path(db, f.root_id))
        fsops.safe_move(f.path, q)                              # muta
        _journal("DELETE", o.file_id, from_path=f.path, quarantine_path=q)  # journal dopo
        o.status = "applied"
        db.commit()
        done.add(o.file_id)
        _progress()

    try:
        for o in retag_ops:
            f = files[o.file_id]
            prior = {field: _tag_value(tagio.read_tags(f.path), field) for field in o.after_json}
            tagio.write_tags(f.path, o.after_json)              # muta
            _journal("RETAG", o.file_id, from_path=f.path, prior_tags=prior)
            o.status = "applied"
            db.commit()
            _progress()
        for o in move_ops:
            f = files[o.file_id]
            dest = o.after_json["path"]
            blocker = del_by_path.get(dest)
            if blocker is not None and blocker.file_id not in done:
                _do_delete(blocker)                            # delete-prima-di-move
            fsops.safe_move(f.path, dest)                      # muta
            _journal(o.kind, o.file_id, from_path=f.path, to_path=dest)
            o.status = "applied"
            db.commit()
            _progress()
        for o in del_ops:
            if o.file_id not in done:
                _do_delete(o)
    except Exception as exc:  # noqa: BLE001 — stop pulito, journal intatto
        plan.status = "applied"
        db.commit()
        return ApplyResult(run_id=plan.id, applied_ops=state["applied"], partial=True,
                           failed_op_seq=state["seq"], error=str(exc),
                           started_at=started, finished_at=utcnow())

    plan.status = "applied"
    db.commit()
    return ApplyResult(run_id=plan.id, applied_ops=state["applied"],
                       started_at=started, finished_at=utcnow())
```

- [ ] **Step 4: Esegui e verifica PASS** · Run: `python -m pytest tests/test_apply_exec.py tests/test_apply_preflight.py -v` · Expected: tutti passano.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/apply.py backend/tests/test_apply_exec.py
git commit -m "feat: apply esecuzione — retag/move/delete-in-quarantena, journal-dopo, riordino, parziale

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Undo

**Files:** Create `backend/app/services/undo.py` · Modify `backend/app/schemas.py` · Test `backend/tests/test_undo.py`

**Interfaces:**
- Consumes: `app.models.UndoJournal`, `app.models.Plan`, `fsops`, `tagio`.
- Produces: `app.schemas.UndoResult` (`run_id, reversed_ops, error`); `undo.undo_run(db, plan) -> UndoResult`.

- [ ] **Step 1: Aggiungi `UndoResult` a `backend/app/schemas.py`**

```python
class UndoResult(BaseModel):
    run_id: int
    reversed_ops: int = 0
    error: str | None = None
```

- [ ] **Step 2: Test che fallisce — `backend/tests/test_undo.py`**

```python
import os

from app.models import AudioFile, Plan, PlanOp, ScanRoot
from app.services.apply import apply_plan
from app.services.undo import undo_run


def test_undo_restores_move_and_delete(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    keeper = copy_fixture("flac", root / "varie" / "k.flac")
    dup = copy_fixture("flac", root / "House" / "A" / "A - T1.flac")
    db.add(ScanRoot(id=1, path=str(root)))
    for fid, p in ((1, keeper), (2, dup)):
        db.add(AudioFile(id=fid, root_id=1, path=p, ext="flac", size_bytes=10,
                         hash_method="file", status="present", has_cover=False,
                         artist="A", title="T1", genre="House"))
    from app.models import DupGroup, DupMember
    db.add(DupGroup(id=1, match_kind="fuzzy", keeper_file_id=1, signature="s"))
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    dest = str(root / "House" / "A" / "A - T1.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1,
                  before_json={"path": keeper}, after_json={"path": dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="DELETE", file_id=2,
                  before_json={"path": dup}, after_json={}, status="pending"))
    db.commit()
    apply_plan(db, plan)
    res = undo_run(db, plan)
    assert res.reversed_ops == 2
    assert os.path.exists(keeper) and os.path.exists(dup)  # tutto al suo posto
    assert plan.status == "undone"
```

- [ ] **Step 3: Esegui e verifica che FALLISCA** · Run: `python -m pytest tests/test_undo.py -v` · Expected: ImportError su `undo_run`.

- [ ] **Step 4: Implementa `backend/app/services/undo.py`**

```python
"""Motore Undo: inverte l'undo_journal di una run in ordine inverso."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import fsops, tagio
from app.models import Plan, UndoJournal
from app.schemas import UndoResult


def undo_run(db: Session, plan: Plan) -> UndoResult:
    rows = db.scalars(
        select(UndoJournal).where(UndoJournal.run_id == plan.id,
                                  UndoJournal.reversed.is_(False))
        .order_by(UndoJournal.op_seq.desc())
    ).all()
    reversed_ops = 0
    try:
        for r in rows:
            if r.kind == "RETAG":
                tagio.write_tags(r.from_path, r.prior_tags_json or {})
            elif r.kind in ("RENAME", "MOVE"):
                fsops.safe_move(r.to_path, r.from_path)
            elif r.kind == "DELETE":
                fsops.safe_move(r.quarantine_path, r.from_path)
            r.reversed = True
            db.commit()
            reversed_ops += 1
    except Exception as exc:  # noqa: BLE001
        return UndoResult(run_id=plan.id, reversed_ops=reversed_ops, error=str(exc))
    plan.status = "undone"
    db.commit()
    return UndoResult(run_id=plan.id, reversed_ops=reversed_ops)
```

- [ ] **Step 5: Esegui e verifica PASS** · Run: `python -m pytest tests/test_undo.py -v` · Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/undo.py backend/app/schemas.py backend/tests/test_undo.py
git commit -m "feat: undo — inverte l'undo_journal in ordine inverso

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Property test dell'invariante (cardine)

**Files:** Test `backend/tests/test_apply_undo_invariant.py`

**Interfaces:** Consumes `apply.apply_plan`, `undo.undo_run`, e tutta la pipeline (planner via dati persistiti).

- [ ] **Step 1: Scrivi il test — `backend/tests/test_apply_undo_invariant.py`**

```python
import os

import pytest

from app.integrations import tagio
from app.models import AudioFile, DupGroup, DupMember, Issue, Plan, PlanOp, ScanRoot
from app.services.apply import apply_plan
from app.services.undo import undo_run


def _snapshot(paths):
    """Mappa path → (esiste, artist, title) per confronto."""
    out = {}
    for p in paths:
        if os.path.exists(p):
            t = tagio.read_tags(p)
            out[p] = (True, t.artist, t.title)
        else:
            out[p] = (False, None, None)
    return out


def _build(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    keep = copy_fixture("flac", root / "varie" / "keep.flac")
    rem = copy_fixture("flac", root / "House" / "A" / "A - T.flac")
    plain = copy_fixture("flac", root / "varie" / "plain.flac")
    tagio.write_tags(keep, {"artist": "PINCO", "title": "T"})   # casing da correggere
    tagio.write_tags(rem, {"artist": "A", "title": "T"})
    tagio.write_tags(plain, {"artist": "B", "title": "U"})
    db.add(ScanRoot(id=1, path=str(root)))
    db.add(AudioFile(id=1, root_id=1, path=keep, ext="flac", size_bytes=10, hash_method="file",
                     status="present", has_cover=False, artist="PINCO", title="T", genre="House"))
    db.add(AudioFile(id=2, root_id=1, path=rem, ext="flac", size_bytes=10, hash_method="file",
                     status="present", has_cover=False, artist="A", title="T", genre="House"))
    db.add(AudioFile(id=3, root_id=1, path=plain, ext="flac", size_bytes=10, hash_method="file",
                     status="present", has_cover=False, artist="B", title="U", genre="House"))
    db.add(DupGroup(id=1, match_kind="fuzzy", keeper_file_id=1, signature="s"))
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    plan = Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}})
    db.add(plan)
    # ops: RETAG keep (PINCO→Pinco), MOVE keep nello slot del rimosso, MOVE plain, DELETE rem
    keep_dest = str(root / "House" / "Pinco" / "Pinco - T.flac")
    plain_dest = str(root / "House" / "B" / "B - U.flac")
    db.add(PlanOp(plan_id=1, seq=0, kind="RETAG", file_id=1,
                  before_json={"artist": "PINCO"}, after_json={"artist": "Pinco"}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=1, kind="MOVE", file_id=1,
                  before_json={"path": keep}, after_json={"path": keep_dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=2, kind="MOVE", file_id=3,
                  before_json={"path": plain}, after_json={"path": plain_dest}, status="pending"))
    db.add(PlanOp(plan_id=1, seq=3, kind="DELETE", file_id=2,
                  before_json={"path": rem}, after_json={}, status="pending"))
    db.commit()
    return plan, [keep, rem, plain]


def test_apply_then_undo_equals_initial(db, tmp_path, copy_fixture):
    plan, paths = _build(db, tmp_path, copy_fixture)
    initial = _snapshot(paths)
    apply_plan(db, plan)
    assert _snapshot(paths) != initial            # apply ha cambiato qualcosa
    undo_run(db, plan)
    assert _snapshot(paths) == initial            # INVARIANTE: tutto com'era


def test_partial_failure_then_undo_restores(db, tmp_path, copy_fixture, monkeypatch):
    plan, paths = _build(db, tmp_path, copy_fixture)
    initial = _snapshot(paths)
    from app.integrations import fsops
    real = fsops.safe_move
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:                       # fa fallire la 2ª mutazione FS
            raise fsops.FsOpError("boom")
        return real(src, dst)
    monkeypatch.setattr("app.services.apply.fsops.safe_move", flaky)
    res = apply_plan(db, plan)
    monkeypatch.setattr("app.services.apply.fsops.safe_move", real)
    assert res.partial is True
    undo_run(db, plan)
    assert _snapshot(paths) == initial            # anche dopo un parziale, l'undo ripristina
```

- [ ] **Step 2: Esegui e verifica PASS** · Run: `python -m pytest tests/test_apply_undo_invariant.py -v` · Expected: 2 passed. (Se il parziale non torna allo stato iniziale, controlla l'ordine inverso e che il journal sia scritto solo dopo una mutazione riuscita.)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_apply_undo_invariant.py
git commit -m "test: invariante apply->undo == stato iniziale (happy path + parziale)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Job Apply + router APPLY

**Files:** Create `backend/app/services/apply_job.py`, `backend/app/routers/apply.py` · Modify `backend/app/main.py` · Test `backend/tests/test_apply_api.py`

**Interfaces:**
- Consumes: `apply.apply_plan`, `app.db.SessionLocal`, `app.models.Plan`, `app.main.app`.
- Produces: `apply_job` (`start_job() -> dict`, `job_state() -> dict`); `app.routers.apply.router` (`POST /api/apply`, `GET /api/apply/status`).

- [ ] **Step 1: Test che fallisce — `backend/tests/test_apply_api.py`** (parte apply)

```python
import time

from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Plan, PlanOp, ScanRoot


def _seed_plan(db, tmp_path, copy_fixture):
    root = tmp_path / "lib"
    f = copy_fixture("flac", root / "varie" / "x.flac")
    db.add(ScanRoot(id=1, path=str(root)))
    db.add(AudioFile(id=1, root_id=1, path=f, ext="flac", size_bytes=10, hash_method="file",
                     status="present", has_cover=False, artist="A", title="T", genre="House"))
    db.add(Plan(id=1, status="draft", rules_json={"naming_template": "{artist} - {title}",
                "folder_template": "{genre}/{artist}", "targets": {"1": str(root)}}))
    db.add(PlanOp(plan_id=1, seq=0, kind="MOVE", file_id=1, before_json={"path": f},
                  after_json={"path": str(root / "House" / "A" / "A - T.flac")}, status="pending"))
    db.commit()
    return f


def _wait(client, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get("/api/apply/status").json()
        if st["status"] in ("done", "error"):
            return st
        time.sleep(0.02)
    raise AssertionError("apply non terminato")


def test_apply_no_draft_400(db):
    with TestClient(app) as client:
        assert client.post("/api/apply").status_code == 400


def test_apply_job_runs(db, tmp_path, copy_fixture):
    _seed_plan(db, tmp_path, copy_fixture)
    with TestClient(app) as client:
        assert client.post("/api/apply").status_code == 200
        st = _wait(client)
        assert st["status"] == "done"
        assert st["result"]["applied_ops"] == 1
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO** · Run: `python -m pytest tests/test_apply_api.py -v` · Expected: 404 (no route).

- [ ] **Step 3: Implementa `backend/app/services/apply_job.py`** (port da `scan_job`)

```python
"""Job Apply in background. App locale: un apply alla volta, stato in memoria + lock."""

import logging
import threading

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Plan, utcnow
from app.services.apply import apply_plan

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_state: dict = {"status": "idle", "phase": None, "processed": 0, "total": 0,
                "result": None, "error": None, "started_at": None, "finished_at": None}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run() -> None:
    db = SessionLocal()

    def on_progress(processed, total, phase):
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        plan = db.scalar(select(Plan).where(Plan.status == "draft").order_by(Plan.id.desc()))
        if plan is None:
            with _lock:
                _state.update(status="error", error="nessun piano draft",
                              finished_at=utcnow().isoformat())
            return
        result = apply_plan(db, plan, on_progress=on_progress)
        with _lock:
            _state.update(status="done", phase=None,
                          result=result.model_dump(mode="json"),
                          finished_at=utcnow().isoformat())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Apply fallito")
        with _lock:
            _state.update(status="error", error=str(exc), finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job() -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(status="running", phase="applying", processed=0, total=0,
                      result=None, error=None, started_at=utcnow().isoformat(), finished_at=None)
        snapshot = dict(_state)
    threading.Thread(target=_run, daemon=True).start()
    return snapshot
```

- [ ] **Step 4: Implementa `backend/app/routers/apply.py`**

```python
"""Router APPLY: avvia/segue il job di applicazione. Sottile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Plan
from app.services import apply_job

router = APIRouter(prefix="/api/apply", tags=["apply"])


@router.post("")
def start_apply(db: Session = Depends(get_db)):
    if db.scalar(select(Plan).where(Plan.status == "draft")) is None:
        raise HTTPException(status_code=400, detail="nessun piano draft da applicare")
    return apply_job.start_job()


@router.get("/status")
def apply_status():
    return apply_job.job_state()
```

- [ ] **Step 5: Includi in `backend/app/main.py`**

```python
from app.routers import analyze, apply, duplicates, issues, plan, scan, settings, sources
```
```python
app.include_router(plan.router)
app.include_router(apply.router)
```
(Il router `history` arriva nel Task 9 — NON aggiungerlo qui, `history.py` non esiste ancora.)

- [ ] **Step 6: Esegui e verifica PASS** · Run: `python -m pytest tests/test_apply_api.py -v` · Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/apply_job.py backend/app/routers/apply.py backend/app/main.py backend/tests/test_apply_api.py
git commit -m "feat: job Apply + router APPLY (start/status)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Router HISTORY + undo endpoint

**Files:** Create `backend/app/routers/history.py` · Modify `backend/app/schemas.py`, `backend/app/main.py` · Test `backend/tests/test_apply_api.py` (aggiunge i casi history/undo)

**Interfaces:**
- Consumes: `app.models.Plan`, `app.services.undo.undo_run`, `app.db.get_db`.
- Produces: `app.schemas.HistoryItem` (`id, status, created_at, n_ops`); `app.routers.history.router` (`GET /api/history`, `POST /api/history/{plan_id}/undo`).

- [ ] **Step 1: Aggiungi `HistoryItem` a `backend/app/schemas.py`**

```python
class HistoryItem(BaseModel):
    id: int
    status: str
    created_at: datetime
    n_ops: int
```

- [ ] **Step 2: Aggiungi i test a `backend/tests/test_apply_api.py`**

```python
from app.services.undo import undo_run  # noqa: E402 (top del file)


def test_history_and_undo(db, tmp_path, copy_fixture):
    f = _seed_plan(db, tmp_path, copy_fixture)
    with TestClient(app) as client:
        client.post("/api/apply")
        _wait(client)
        hist = client.get("/api/history").json()
        assert len(hist) == 1 and hist[0]["status"] == "applied"
        undo = client.post(f"/api/history/{hist[0]['id']}/undo")
        assert undo.status_code == 200 and undo.json()["reversed_ops"] == 1
        assert client.get("/api/history").json()[0]["status"] == "undone"


def test_undo_non_applied_400(db, tmp_path, copy_fixture):
    _seed_plan(db, tmp_path, copy_fixture)  # piano draft, non applied
    with TestClient(app) as client:
        assert client.post("/api/history/1/undo").status_code == 400
```

- [ ] **Step 3: Esegui e verifica che FALLISCANO** · Run: `python -m pytest tests/test_apply_api.py -k "history or undo" -v` · Expected: 404.

- [ ] **Step 4: Implementa `backend/app/routers/history.py`**

```python
"""Router HISTORY: run applicate/annullate + undo. Sottile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Plan, PlanOp
from app.schemas import HistoryItem, UndoResult
from app.services import undo

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistoryItem])
def list_history(db: Session = Depends(get_db)):
    plans = db.scalars(select(Plan).where(Plan.status.in_(("applied", "undone")))
                       .order_by(Plan.id.desc())).all()
    out = []
    for p in plans:
        n = db.scalar(select(func.count()).select_from(PlanOp).where(PlanOp.plan_id == p.id))
        out.append(HistoryItem(id=p.id, status=p.status, created_at=p.created_at, n_ops=n or 0))
    return out


@router.post("/{plan_id}/undo", response_model=UndoResult)
def undo_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="run non trovata")
    if plan.status != "applied":
        raise HTTPException(status_code=400, detail="la run non è in stato 'applied'")
    return undo.undo_run(db, plan)
```

- [ ] **Step 5: Includi in `backend/app/main.py`**

Aggiungi `history` all'import dei router e l'include:

```python
from app.routers import analyze, apply, duplicates, history, issues, plan, scan, settings, sources
```
```python
app.include_router(apply.router)
app.include_router(history.router)
```

- [ ] **Step 6: Esegui l'INTERA suite** · Run: `python -m pytest tests -v` · Expected: tutto verde (chunk 1+2+3+4), pristine.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/history.py backend/app/schemas.py backend/app/main.py backend/tests/test_apply_api.py
git commit -m "feat: router HISTORY — run applicate/annullate + POST .../undo

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verifica finale del chunk

- [ ] **Suite verde e pristine:** `python -m pytest tests -v`, incluso il property test dell'invariante (happy + parziale).
- [ ] **End-to-end reale:** scan → accetta issue + keeper → PLAN → `POST /api/apply` → i file vengono retaggati/spostati, i doppioni in `.quarantine/`; `GET /api/history` mostra la run; `POST .../undo` riporta tutto al suo posto.
- [ ] **Definition of Done** della spec §13 soddisfatta.

## Self-Review (svolto in fase di scrittura)

- **Spec coverage:** UndoJournal (Task 1) ✓; write_tags + content_hash stabile (Task 2) ✓; fsops safe_move/quarantine/cross-device (Task 3) ✓; pre-volo conflitti-snapshot + stale (Task 4) ✓; esecuzione + journal-dopo + riordino + parziale (Task 5) ✓; undo (Task 6) ✓; invariante apply→undo + parziale (Task 7) ✓; job + router apply (Task 8) ✓; history + undo endpoint (Task 9) ✓.
- **Placeholder scan:** nessun TODO/TBD; codice completo. (Deviazione consapevole dalla spec: il journal è scritto **dopo** la mutazione riuscita, non prima, per la coerenza dell'undo su fallimento — annotata nei Global Constraints.)
- **Type consistency:** `ApplyResult`/`UndoResult`/`HistoryItem` coerenti tra apply/undo/router; `apply_plan(db, plan, on_progress)` invariato tra Task 4 e 5; `_journal`/`_do_delete`/`_stale_op` coerenti; `fsops.safe_move`/`quarantine_path_for` e `tagio.write_tags` con le firme usate da apply/undo.
```
