# Modifica manuale dei metadati in FILES — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettere di modificare a mano i metadati testuali di un file dalla schermata FILES, con scrittura immediata su disco e reversibile via History/undo.

**Architecture:** Un nuovo servizio `manual_edit.edit_tags` scrive i tag subito (ricalcando il pattern RETAG di `apply.py`): valida i campi, cattura i valori precedenti dal disco, crea un `Plan` sintetico + una voce `UndoJournal` RETAG (journal-first), scrive col `tagio.write_tags`, allinea la riga `AudioFile` al disco e chiude le issue aperte sui campi toccati (`source:"manual"`). Un endpoint sottile `POST /api/files/{id}/tags` lo espone e ritorna il `FileRow` aggiornato. Il frontend apre un `Modal` per riga con i 9 campi editabili.

**Tech Stack:** FastAPI + SQLAlchemy + mutagen (backend, Python 3.11); Next.js 16 + React 19 + Tailwind v4 + TypeScript (frontend).

## Global Constraints

- **Backend venv obbligatorio:** i test girano con `backend/.venv/bin/python -m pytest backend/tests -q` (Python 3.11; il 3.9 di sistema rompe su `X | None`).
- **`pytest.ini` ha `filterwarnings = error`:** un nuovo warning fa fallire la suite.
- **Commenti/docstring backend in italiano** (stile esistente del file che si tocca).
- **i18n:** aggiungere la chiave prima in `frontend/lib/i18n/en.ts` (fonte di verità), poi tradurre in `it.ts` (una chiave mancante è un errore di tipo).
- **Campi editabili (whitelist):** `artist, title, album, album_artist, genre, year, label, track_no, comment` (= `planner._EFFECTIVE_FIELDS` = `issues._RETAGGABLE`).
- **Precedenza metadati:** `manual > cleaned file tag > provider > ai`. Una modifica manuale vince e chiude le issue sul campo.
- **Errori HTTP:** usare `app.core.http_errors.api_error(status, code, message)`; il frontend traduce `code` con `translateApiError`.

---

### Task 1: Servizio `manual_edit` (scrittura, undo, riconciliazione issue)

**Files:**
- Create: `backend/app/services/manual_edit.py`
- Test: `backend/tests/test_manual_edit.py`

**Interfaces:**
- Consumes: `tagio.read_tags(path) -> TagData`, `tagio.write_tags(path, changes: dict)` (già esistenti); modelli `AudioFile`, `Issue`, `Plan`, `UndoJournal`, `utcnow`.
- Produces:
  - `manual_edit.edit_tags(db: Session, file: AudioFile, changes: dict[str, str | None]) -> None` — applica le modifiche; idempotente (campi già uguali al DB ignorati; se nulla cambia è un no-op senza run).
  - `manual_edit.ManualEditError(Exception)` con attributi `.status: int`, `.code: str`, `.message: str` — sollevata su input non valido / file non scrivibile; il router (Task 2) la converte in `api_error`.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/test_manual_edit.py`:

```python
import os

import pytest
from sqlalchemy import select

from app.integrations import tagio
from app.models import AudioFile, Issue, Plan, ScanRoot, UndoJournal
from app.services import manual_edit
from app.services.planner import build_plan
from app.services.undo import undo_run


def _seed(db, path, **kw):
    """ScanRoot(id=1) + un AudioFile 'present' su un file reale."""
    if db.get(ScanRoot, 1) is None:
        db.add(ScanRoot(id=1, path=os.path.dirname(path)))
    d = dict(id=1, root_id=1, path=path, ext="flac", size_bytes=10, hash_method="file",
             status="present", has_cover=False, artist="Old", title="T", genre="House")
    d.update(kw)
    db.add(AudioFile(**d))
    db.commit()
    return db.get(AudioFile, 1)


def test_edit_writes_disk_and_db(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old", "title": "T"})
    file = _seed(db, f, artist="Old", title="T")
    manual_edit.edit_tags(db, file, {"artist": "New Artist", "genre": "Techno"})
    assert tagio.read_tags(f).artist == "New Artist"      # disco
    assert tagio.read_tags(f).genre == "Techno"
    assert db.get(AudioFile, 1).artist == "New Artist"    # DB allineato
    assert db.get(AudioFile, 1).genre == "Techno"


def test_edit_creates_undoable_manual_run(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old"})
    file = _seed(db, f, artist="Old")
    manual_edit.edit_tags(db, file, {"artist": "New"})
    plan = db.scalar(select(Plan))
    assert plan.status == "applied"
    assert plan.rules_json["kind"] == "manual_edit"
    j = db.scalar(select(UndoJournal).where(UndoJournal.run_id == plan.id))
    assert j.kind == "RETAG" and j.prior_tags_json == {"artist": "Old"}  # prior dal disco


def test_undo_restores_manual_edit(db, tmp_path, copy_fixture):
    # reversibilità end-to-end: l'undo della run manuale riporta il tag sul file.
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old"})
    file = _seed(db, f, artist="Old")
    manual_edit.edit_tags(db, file, {"artist": "New"})
    assert tagio.read_tags(f).artist == "New"
    plan = db.scalar(select(Plan))
    undo_run(db, plan)
    assert tagio.read_tags(f).artist == "Old"     # tag ripristinato sul disco
    assert plan.status == "undone"


def test_edit_empty_string_clears_tag(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old", "label": "ClearMe"})
    file = _seed(db, f, artist="Old", label="ClearMe")
    manual_edit.edit_tags(db, file, {"label": ""})
    assert tagio.read_tags(f).label is None
    assert db.get(AudioFile, 1).label is None


def test_edit_coerces_year_and_track(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f)
    manual_edit.edit_tags(db, file, {"year": "2003", "track_no": "5"})
    assert db.get(AudioFile, 1).year == 2003
    assert db.get(AudioFile, 1).track_no == 5


def test_edit_rejects_bad_year(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f)
    with pytest.raises(manual_edit.ManualEditError) as e:
        manual_edit.edit_tags(db, file, {"year": "notayear"})
    assert e.value.status == 400 and e.value.code == "value_invalid"


def test_edit_rejects_unknown_field(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f)
    with pytest.raises(manual_edit.ManualEditError) as e:
        manual_edit.edit_tags(db, file, {"bpm": "128"})
    assert e.value.status == 400 and e.value.code == "field_not_editable"


def test_edit_rejects_missing_file(db, tmp_path):
    file = _seed(db, str(tmp_path / "gone.flac"), status="present")
    with pytest.raises(manual_edit.ManualEditError) as e:
        manual_edit.edit_tags(db, file, {"artist": "X"})
    assert e.value.status == 409 and e.value.code == "file_not_writable"


def test_edit_noop_when_unchanged(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f, artist="Same")
    manual_edit.edit_tags(db, file, {"artist": "Same"})
    assert db.scalar(select(Plan)) is None            # nessuna run creata


def test_edit_closes_open_issue_on_field(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f, artist=None, genre="House")
    db.add(Issue(file_id=1, type="missing_required_tag", field="artist",
                 severity="error", detail="no artist", status="open"))
    db.add(Issue(file_id=1, type="dirty_genre", field="genre",
                 severity="info", detail="dirty", status="open"))
    db.commit()
    manual_edit.edit_tags(db, file, {"artist": "Fixed"})
    art = db.scalar(select(Issue).where(Issue.field == "artist"))
    gen = db.scalar(select(Issue).where(Issue.field == "genre"))
    assert art.status == "accepted"
    assert art.suggested_fix_json == {"field": "artist", "action": "retag",
                                      "to": "Fixed", "source": "manual"}
    assert gen.status == "open"                        # campo non toccato: invariato


def test_edit_leaves_no_phantom_retag(db, tmp_path, copy_fixture):
    # dopo l'edit, il DB è allineato: build_plan non deve rigenerare un RETAG.
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    file = _seed(db, f, artist=None)
    db.add(Issue(file_id=1, type="missing_required_tag", field="artist",
                 severity="error", detail="no artist", status="open"))
    db.commit()
    manual_edit.edit_tags(db, file, {"artist": "Fixed"})
    accepted = db.scalars(select(Issue).where(Issue.status == "accepted")).all()
    ops = build_plan([db.get(AudioFile, 1)], accepted, removals=[],
                     settings_snapshot={"naming_template": "{artist} - {title}",
                                        "folder_template": ""},
                     root_targets={})
    assert not any(o.kind == "RETAG" for o in ops)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_manual_edit.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.manual_edit'`.

- [ ] **Step 3: Write the service**

Create `backend/app/services/manual_edit.py`:

```python
"""Modifica manuale dei metadati di un file dalla schermata FILES.

A differenza dei fix da issue (che aspettano l'Apply), scrive i tag SUBITO sul
disco ed è reversibile: crea un Plan sintetico + una voce UndoJournal RETAG, così
la modifica compare in History e si annulla come una run qualsiasi. Ricalca il
pattern RETAG di services/apply.py: journal-first, poi mutazione, poi DB."""

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import tagio
from app.models import AudioFile, Issue, Plan, UndoJournal, utcnow

# Campi tag correggibili a mano (= planner._EFFECTIVE_FIELDS = issues._RETAGGABLE).
_EDITABLE = {"artist", "title", "album", "album_artist", "genre", "year",
             "label", "track_no", "comment"}
_INT_FIELDS = {"year", "track_no"}


class ManualEditError(Exception):
    """Errore di modifica manuale con codice/stato HTTP; il router lo traduce."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _coerce(field: str, raw):
    """Normalizza un valore: stringa vuota/None → None (pulisce il tag);
    year/track_no → intero non negativo. Solleva ManualEditError(400)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if raw == "":
            return None
    if field in _INT_FIELDS:
        try:
            n = int(raw)
        except (TypeError, ValueError):
            raise ManualEditError(400, "value_invalid", f"'{field}' must be a number")
        if n < 0:
            raise ManualEditError(400, "value_invalid", f"'{field}' must be positive")
        return n
    return str(raw)


def _norm(v):
    return None if v is None else str(v)


def edit_tags(db: Session, file: AudioFile, changes: dict) -> None:
    """Applica le modifiche manuali (field→valore) a `file`.
    Idempotente: i campi già uguali al DB sono ignorati; se nulla cambia è un
    no-op (nessuna scrittura, nessuna run)."""
    unknown = set(changes) - _EDITABLE
    if unknown:
        raise ManualEditError(400, "field_not_editable",
                              f"Field not editable: {', '.join(sorted(unknown))}")
    if file.status != "present" or file.scan_error or not os.path.exists(file.path):
        raise ManualEditError(409, "file_not_writable", "File is not writable")

    coerced = {f: _coerce(f, changes[f]) for f in changes}
    # solo i campi il cui valore normalizzato differisce davvero da quello nel DB
    effective = {f: v for f, v in coerced.items() if _norm(getattr(file, f)) != _norm(v)}
    if not effective:
        return

    # prior letti dal DISCO (come apply.py): l'undo ripristina lo stato reale.
    disk = tagio.read_tags(file.path)
    prior = {f: getattr(disk, f) for f in effective}

    # journal-first: Plan sintetico + voce RETAG PRIMA di toccare il file.
    plan = Plan(status="applied",
                rules_json={"kind": "manual_edit", "file_id": file.id,
                            "fields": sorted(effective)})
    db.add(plan)
    db.flush()
    db.add(UndoJournal(run_id=plan.id, op_seq=0, kind="RETAG", file_id=file.id,
                       from_path=file.path, prior_tags_json=prior))
    db.commit()

    tagio.write_tags(file.path, effective)          # poi muta il disco
    for f, v in effective.items():                  # allinea il DB al disco
        setattr(file, f, v)
    _reconcile_issues(db, file.id, effective)
    db.commit()


def _reconcile_issues(db: Session, file_id: int, effective: dict) -> None:
    """Chiude le issue aperte sui campi appena modificati: manual vince su tutto
    (precedenza). Specchio di routers.issues.fix_issue."""
    issues = db.scalars(select(Issue).where(
        Issue.file_id == file_id, Issue.status == "open",
        Issue.field.in_(list(effective)))).all()
    for iss in issues:
        v = effective[iss.field]
        if v is None:
            iss.suggested_fix_json = {"field": iss.field, "action": "clear",
                                      "source": "manual"}
        else:
            iss.suggested_fix_json = {"field": iss.field, "action": "retag",
                                      "to": str(v), "source": "manual"}
        iss.status = "accepted"
        iss.updated_at = utcnow()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_manual_edit.py -q`
Expected: PASS (11 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/manual_edit.py backend/tests/test_manual_edit.py
git commit -m "feat(manual-edit): servizio edit_tags con undo e riconciliazione issue"
```

---

### Task 2: Schemi, helper `build_file_row`, endpoint `POST /api/files/{id}/tags`

**Files:**
- Modify: `backend/app/schemas.py` (estende `FileRow`; aggiunge `FileTagsUpdate`)
- Modify: `backend/app/routers/library.py` (estrae `build_file_row`, lo usa in `list_files`)
- Create: `backend/app/routers/files.py`
- Modify: `backend/app/main.py` (registra il router)
- Test: `backend/tests/test_manual_edit_api.py`

**Interfaces:**
- Consumes: `manual_edit.edit_tags`, `manual_edit.ManualEditError` (Task 1); `api_error`.
- Produces:
  - `library.build_file_row(db: Session, f: AudioFile) -> FileRow` — costruisce il `FileRow` di un singolo file (issue_count/worst/dup/cover ricalcolati).
  - `schemas.FileTagsUpdate` — body dei 9 campi opzionali (`str | None`, valori grezzi; year/track parsati lato server).
  - `FileRow` esteso con `album_artist: str | None`, `track_no: int | None`, `comment: str | None`.
  - Endpoint `POST /api/files/{file_id}/tags` → `FileRow`.

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/test_manual_edit_api.py`:

```python
import os

from fastapi.testclient import TestClient

from app.integrations import tagio
from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db, path, **kw):
    if db.get(ScanRoot, 1) is None:
        db.add(ScanRoot(id=1, path=os.path.dirname(path)))
    d = dict(id=1, root_id=1, path=path, ext="flac", size_bytes=10, hash_method="file",
             status="present", has_cover=False, artist="Old", title="T")
    d.update(kw)
    db.add(AudioFile(**d))
    db.commit()


def test_post_tags_returns_updated_row(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old"})
    _seed(db, f, artist="Old")
    r = client.post("/api/files/1/tags", json={"artist": "New", "year": "2003"})
    assert r.status_code == 200
    body = r.json()
    assert body["artist"] == "New" and body["year"] == 2003
    assert body["album_artist"] is None and body["track_no"] is None
    assert tagio.read_tags(f).artist == "New"


def test_post_tags_closes_issue_and_updates_count(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    _seed(db, f, artist=None)
    db.add(Issue(file_id=1, type="missing_required_tag", field="artist",
                 severity="error", detail="no artist", status="open"))
    db.commit()
    r = client.post("/api/files/1/tags", json={"artist": "Fixed"})
    assert r.status_code == 200
    assert r.json()["issue_count"] == 0


def test_post_tags_404_when_missing(db):
    r = client.post("/api/files/999/tags", json={"artist": "X"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "file_not_found"


def test_post_tags_409_when_file_gone(db, tmp_path):
    _seed(db, str(tmp_path / "gone.flac"))
    r = client.post("/api/files/1/tags", json={"artist": "X"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "file_not_writable"


def test_post_tags_400_on_bad_year(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    _seed(db, f)
    r = client.post("/api/files/1/tags", json={"year": "abc"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "value_invalid"
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_manual_edit_api.py -q`
Expected: FAIL (404 su tutte le POST perché la route non esiste ancora, o `KeyError` su `album_artist`).

- [ ] **Step 3: Extend `FileRow` and add `FileTagsUpdate` in `schemas.py`**

In `backend/app/schemas.py`, dentro `class FileRow`, aggiungi i tre campi (dopo `title`, per raggruppare i tag):

```python
class FileRow(BaseModel):
    id: int
    root_id: int
    path: str
    ext: str
    artist: str | None
    title: str | None
    album: str | None = None
    album_artist: str | None = None
    genre: str | None = None
    year: int | None = None
    label: str | None = None
    track_no: int | None = None
    comment: str | None = None
    bitrate: int | None
    duration_s: float | None
    status: str
    issue_count: int
    worst_severity: str | None
    in_dup_group: bool
    # "embedded" = artwork nei tag, "provider" = solo una proposta in cache,
    # None = niente da mostrare (il frontend salta del tutto la richiesta).
    cover_source: str | None = None
```

Poi aggiungi (vicino a `IssueFixBody`) il body dell'endpoint. I valori arrivano grezzi dal frontend (input di testo); year/track_no sono stringhe parsate lato server:

```python
class FileTagsUpdate(BaseModel):
    """Modifica manuale dei tag da FILES: solo i campi presenti vengono toccati
    (il router usa `exclude_unset`). Valori grezzi; year/track parsati dal service."""
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    album_artist: str | None = None
    genre: str | None = None
    year: str | None = None
    label: str | None = None
    track_no: str | None = None
    comment: str | None = None
```

- [ ] **Step 4: Extract `build_file_row` in `library.py` and reuse it in `list_files`**

In `backend/app/routers/library.py`, aggiungi l'helper dopo le costanti `_SORT_COLS` (usa `case`, `func`, `select`, `Issue`, `DupGroup`, `DupMember`, `FileRow`, già importati):

```python
def _file_row(f: AudioFile, n_issues: int, rank: int, dup_n: int, cover_n: int) -> FileRow:
    return FileRow(
        id=f.id, root_id=f.root_id, path=f.path, ext=f.ext,
        artist=f.artist, title=f.title, album=f.album, album_artist=f.album_artist,
        genre=f.genre, year=f.year, label=f.label, track_no=f.track_no,
        comment=f.comment, bitrate=f.bitrate, duration_s=f.duration_s,
        status=f.status, issue_count=n_issues,
        worst_severity=_RANK_SEV.get(rank), in_dup_group=bool(dup_n),
        cover_source="embedded" if f.has_cover else ("provider" if cover_n else None),
    )


def build_file_row(db: Session, f: AudioFile) -> FileRow:
    """FileRow di un singolo file (per l'endpoint di modifica manuale): stesse
    quattro metriche di `list_files`, ma calcolate per un solo `f`."""
    n_issues = db.scalar(select(func.count()).select_from(Issue).where(
        Issue.file_id == f.id, Issue.status == "open")) or 0
    rank = db.scalar(select(func.max(case(_SEV_RANK, value=Issue.severity, else_=0)))
                     .select_from(Issue).where(Issue.file_id == f.id,
                                               Issue.status == "open")) or 0
    dup_n = db.scalar(select(func.count()).select_from(DupMember)
                      .join(DupGroup, DupGroup.id == DupMember.group_id)
                      .where(DupMember.file_id == f.id,
                             DupGroup.dismissed.is_(False))) or 0
    cover_n = db.scalar(select(func.count()).select_from(Issue).where(
        Issue.file_id == f.id, Issue.type == "missing_cover",
        Issue.status == "open")) or 0
    return _file_row(f, n_issues, rank, dup_n, cover_n)
```

Poi, nel corpo di `list_files`, sostituisci il blocco finale che costruisce le righe:

```python
    rows = []
    for f, n_issues, rank, dup_n, cover_n in db.execute(stmt).all():
        rows.append(_file_row(f, n_issues or 0, rank or 0, dup_n, cover_n))
    return rows
```

- [ ] **Step 5: Create the router `routers/files.py`**

Create `backend/app/routers/files.py`:

```python
"""Router FILES (scrittura): modifica manuale dei metadati. Sottile."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.models import AudioFile
from app.routers.library import build_file_row
from app.schemas import FileRow, FileTagsUpdate
from app.services import manual_edit

router = APIRouter(prefix="/api", tags=["files"])


@router.post("/files/{file_id}/tags", response_model=FileRow)
def update_file_tags(file_id: int, body: FileTagsUpdate,
                     db: Session = Depends(get_db)):
    file = db.get(AudioFile, file_id)
    if file is None:
        raise api_error(404, "file_not_found", "File not found")
    try:
        manual_edit.edit_tags(db, file, body.model_dump(exclude_unset=True))
    except manual_edit.ManualEditError as exc:
        raise api_error(exc.status, exc.code, exc.message)
    return build_file_row(db, file)
```

- [ ] **Step 6: Wire the router in `main.py`**

In `backend/app/main.py`, aggiungi `files` all'import da `app.routers` (riga 16) e la registrazione. Nell'import multilinea aggiungi `files,` in ordine; dopo `app.include_router(library.router)` (riga 48) aggiungi:

```python
app.include_router(files.router)
```

- [ ] **Step 7: Run the API tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_manual_edit_api.py -q`
Expected: PASS (5 test).

- [ ] **Step 8: Run the files-filters test to confirm no regression on `FileRow`**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_files_filters.py -q`
Expected: PASS (i nuovi campi hanno default e non rompono le asserzioni esistenti).

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/library.py \
        backend/app/routers/files.py backend/app/main.py \
        backend/tests/test_manual_edit_api.py
git commit -m "feat(manual-edit): endpoint POST /api/files/{id}/tags + FileRow esteso"
```

---

### Task 3: History distingue le run manuali (`kind`)

**Files:**
- Modify: `backend/app/schemas.py` (`HistoryItem.kind`)
- Modify: `backend/app/routers/history.py` (popola `kind`)
- Test: `backend/tests/test_history_kind.py`

**Interfaces:**
- Consumes: `manual_edit.edit_tags` (Task 1), `Plan.rules_json`.
- Produces: `HistoryItem.kind: str | None` — `"manual_edit"` per le run manuali, `None` per gli Apply normali.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_history_kind.py`:

```python
import os

from fastapi.testclient import TestClient

from app.integrations import tagio
from app.main import app
from app.models import AudioFile, Plan, PlanOp, ScanRoot
from app.services import manual_edit

client = TestClient(app)


def test_history_marks_manual_edit_runs(db, tmp_path, copy_fixture):
    f = copy_fixture("flac", tmp_path / "lib" / "x.flac")
    tagio.write_tags(f, {"artist": "Old"})
    db.add(ScanRoot(id=1, path=str(tmp_path / "lib")))
    db.add(AudioFile(id=1, root_id=1, path=f, ext="flac", size_bytes=10,
                     hash_method="file", status="present", artist="Old"))
    # una run "normale" applicata, senza kind
    normal = Plan(id=99, status="applied", rules_json={"naming_template": "{artist}"})
    db.add(normal)
    db.add(PlanOp(plan_id=99, seq=0, kind="RETAG", file_id=1,
                  before_json={}, after_json={}, status="applied"))
    db.commit()
    manual_edit.edit_tags(db, db.get(AudioFile, 1), {"artist": "New"})

    rows = client.get("/api/history").json()
    by_kind = {r["kind"]: r for r in rows}
    assert by_kind["manual_edit"]["n_ops"] == 0        # nessun PlanOp per l'edit manuale
    assert None in by_kind                             # la run normale non ha kind
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_history_kind.py -q`
Expected: FAIL con `KeyError: 'kind'` (il campo non è ancora nella risposta).

- [ ] **Step 3: Add `kind` to `HistoryItem`**

In `backend/app/schemas.py`, `class HistoryItem`:

```python
class HistoryItem(BaseModel):
    id: int
    status: str
    created_at: datetime
    n_ops: int
    kind: str | None = None
```

- [ ] **Step 4: Populate `kind` in `history.list_history`**

In `backend/app/routers/history.py`, dentro il ciclo di `list_history`, sostituisci l'`append`:

```python
        out.append(HistoryItem(id=p.id, status=p.status, created_at=p.created_at,
                               n_ops=n or 0, kind=(p.rules_json or {}).get("kind")))
```

- [ ] **Step 5: Run to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_history_kind.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite (no new warnings, no regressions)**

Run: `backend/.venv/bin/python -m pytest backend/tests -q`
Expected: PASS (tutti i test, inclusi i ~295 esistenti + i nuovi).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/history.py \
        backend/tests/test_history_kind.py
git commit -m "feat(manual-edit): History distingue le run manuali via kind"
```

---

### Task 4: Frontend — API client, tipi e label History

**Files:**
- Modify: `frontend/lib/api.ts` (`FileRow` + `EditableTags` + `updateFileTags` + `HistoryItem.kind`)
- Modify: `frontend/app/history/page.tsx` (mostra "Manual edit")
- Modify: `frontend/lib/i18n/en.ts` e `frontend/lib/i18n/it.ts` (chiavi editor + `history.manualEdit`)

**Interfaces:**
- Consumes: endpoint `POST /api/files/{id}/tags` (Task 2), `HistoryItem.kind` (Task 3).
- Produces:
  - `api.EditableTags` — i 9 campi come stringhe.
  - `api.updateFileTags(fileId: number, changes: Partial<EditableTags>): Promise<FileRow>`.
  - `FileRow` (TS) esteso con `album_artist`, `track_no`, `comment`; `HistoryItem` con `kind`.
  - Chiavi i18n `files.editTitle`, `files.field.*` (9), `files.numHint`; `history.manualEdit`.

- [ ] **Step 1: Extend `FileRow`, add `EditableTags` + `updateFileTags` in `api.ts`**

In `frontend/lib/api.ts`, dentro `export interface FileRow`, aggiungi i tre campi:

```ts
export interface FileRow {
  id: number;
  root_id: number;
  path: string;
  ext: string;
  artist: string | null;
  title: string | null;
  album: string | null;
  album_artist: string | null;
  genre: string | null;
  year: number | null;
  label: string | null;
  track_no: number | null;
  comment: string | null;
  bitrate: number | null;
  duration_s: number | null;
  status: string;
  issue_count: number;
  worst_severity: Severity | null;
  in_dup_group: boolean;
  cover_source: "embedded" | "provider" | null;
}
```

Poi, subito dopo la funzione `libraryFacets` (o accanto agli altri helper `files`/`library`), aggiungi:

```ts
export interface EditableTags {
  artist: string;
  title: string;
  album: string;
  album_artist: string;
  genre: string;
  year: string;
  label: string;
  track_no: string;
  comment: string;
}

// Modifica manuale dei tag da FILES: manda solo i campi cambiati; ritorna la
// riga aggiornata (issue_count ricalcolato) da rimettere in-place nella tabella.
export function updateFileTags(fileId: number, changes: Partial<EditableTags>) {
  return apiSend<FileRow>("POST", `/api/files/${fileId}/tags`, changes);
}
```

E in `export interface HistoryItem` aggiungi `kind`:

```ts
export interface HistoryItem {
  id: number;
  status: string; // applied | undone
  created_at: string;
  n_ops: number;
  kind: string | null; // "manual_edit" per le modifiche manuali, altrimenti null
}
```

- [ ] **Step 2: Show "Manual edit" in the History table**

In `frontend/app/history/page.tsx`, la cella delle operazioni (oggi `{r.n_ops}`) deve mostrare l'etichetta per le run manuali (che hanno `n_ops === 0`). Sostituisci la cella:

```tsx
                    <td className="tnum px-3 py-2 text-right text-fg">
                      {r.kind === "manual_edit" ? t.history.manualEdit : r.n_ops}
                    </td>
```

- [ ] **Step 3: Add the i18n keys (en first, then it)**

In `frontend/lib/i18n/en.ts`, dentro il blocco `files: {`, aggiungi (prima di `dupTitle`):

```ts
    editTitle: "Edit tags",
    field: {
      artist: "Artist",
      title: "Title",
      album: "Album",
      album_artist: "Album artist",
      genre: "Genre",
      year: "Year",
      label: "Label",
      track_no: "Track",
      comment: "Comment",
    },
    numHint: "Numbers only",
```

E dentro il blocco `history: {`, aggiungi:

```ts
    manualEdit: "manual edit",
```

In `frontend/lib/i18n/it.ts`, aggiungi le stesse chiavi tradotte. Dentro `files: {`:

```ts
    editTitle: "Modifica tag",
    field: {
      artist: "Artista",
      title: "Titolo",
      album: "Album",
      album_artist: "Artista album",
      genre: "Genere",
      year: "Anno",
      label: "Etichetta",
      track_no: "Traccia",
      comment: "Commento",
    },
    numHint: "Solo numeri",
```

Dentro `history: {`:

```ts
    manualEdit: "modifica manuale",
```

- [ ] **Step 4: Typecheck and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: nessun errore. (Se `it.ts` manca una chiave presente in `en.ts`, `tsc` fallisce: è il controllo che le traduzioni siano complete.)

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/history/page.tsx \
        frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts
git commit -m "feat(manual-edit): client API, tipi e label History per la modifica manuale"
```

---

### Task 5: Frontend — pannello di modifica e integrazione in FILES

**Files:**
- Create: `frontend/components/file-edit-panel.tsx`
- Modify: `frontend/components/files-table.tsx` (riga cliccabile → `onEdit`)
- Modify: `frontend/app/files/page.tsx` (stato `editing`, monta il pannello)

**Interfaces:**
- Consumes: `updateFileTags`, `EditableTags`, `FileRow`, `LibraryFacets` (Task 4); `Modal`, `Button`, `Input`, `Field`, `Alert` da `components/ui`.
- Produces: `FileEditPanel({ row, facets, onClose, onSaved })` — pannello modale; `FilesTable` guadagna la prop `onEdit(row: FileRow) => void`.

- [ ] **Step 1: Create the edit panel component**

Create `frontend/components/file-edit-panel.tsx`:

```tsx
"use client";

import { useState } from "react";
import { updateFileTags, type FileRow, type LibraryFacets, type EditableTags } from "@/lib/api";
import { Modal, Button, Input, Field, Alert } from "@/components/ui";
import { useT } from "@/lib/i18n";

const FIELDS: (keyof EditableTags)[] = [
  "artist", "title", "album", "album_artist", "genre", "year", "label", "track_no", "comment",
];
// campi con autocomplete dai facet della libreria (riusa quelli già caricati)
const FACET_FIELDS = new Set<keyof EditableTags>(["genre", "artist", "album", "label"]);
const NUM_FIELDS = new Set<keyof EditableTags>(["year", "track_no"]);

function initial(row: FileRow): EditableTags {
  return {
    artist: row.artist ?? "",
    title: row.title ?? "",
    album: row.album ?? "",
    album_artist: row.album_artist ?? "",
    genre: row.genre ?? "",
    year: row.year != null ? String(row.year) : "",
    label: row.label ?? "",
    track_no: row.track_no != null ? String(row.track_no) : "",
    comment: row.comment ?? "",
  };
}

export function FileEditPanel({ row, facets, onClose, onSaved }: {
  row: FileRow;
  facets: LibraryFacets | null;
  onClose: () => void;
  onSaved: (updated: FileRow) => void;
}) {
  const t = useT();
  const base = initial(row);
  const [form, setForm] = useState<EditableTags>(base);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const badNum = (f: keyof EditableTags) =>
    NUM_FIELDS.has(f) && form[f].trim() !== "" && !/^\d+$/.test(form[f].trim());
  const anyBadNum = FIELDS.some(badNum);
  const changed = FIELDS.filter((f) => form[f].trim() !== base[f].trim());

  const facetFor = (f: keyof EditableTags): string[] =>
    facets && FACET_FIELDS.has(f)
      ? (facets[f as keyof LibraryFacets] as (string | number)[]).map(String)
      : [];

  const save = async () => {
    if (changed.length === 0 || anyBadNum) return;
    setSaving(true);
    setError(null);
    try {
      const patch: Partial<EditableTags> = {};
      for (const f of changed) patch[f] = form[f].trim();
      const updated = await updateFileTags(row.id, patch);
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={t.files.editTitle}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{t.common.cancel}</Button>
          <Button onClick={save} disabled={saving || changed.length === 0 || anyBadNum}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="truncate text-[11px] text-faint" dir="rtl" title={row.path}>{row.path}</p>
        {error && <Alert>{error}</Alert>}
        {FIELDS.map((f) => {
          const opts = facetFor(f);
          const listId = `edit-${f}`;
          return (
            <Field key={f} label={t.files.field[f]} hint={badNum(f) ? t.files.numHint : undefined}>
              <Input
                list={opts.length ? listId : undefined}
                value={form[f]}
                aria-invalid={badNum(f) || undefined}
                onChange={(e) => setForm((s) => ({ ...s, [f]: e.target.value }))}
              />
              {opts.length > 0 && (
                <datalist id={listId}>
                  {opts.map((o) => <option key={o} value={o} />)}
                </datalist>
              )}
            </Field>
          );
        })}
      </div>
    </Modal>
  );
}
```

- [ ] **Step 2: Make the FILES rows clickable in `files-table.tsx`**

In `frontend/components/files-table.tsx`, aggiungi `onEdit` alla firma della prop e rendi la riga cliccabile. Modifica la firma del componente:

```tsx
export function FilesTable({
  rows, sort, dir, onSort, onEdit,
}: {
  rows: FileRow[];
  sort: SortKey;
  dir: SortDir;
  onSort: (col: SortKey) => void;
  onEdit: (row: FileRow) => void;
}) {
```

E la riga (`<tr key={r.id} …>`) diventa:

```tsx
            <tr
              key={r.id}
              onClick={() => onEdit(r)}
              className="cursor-pointer border-b border-surface-2 last:border-0 hover:bg-surface"
            >
```

- [ ] **Step 3: Mount the panel from `app/files/page.tsx`**

In `frontend/app/files/page.tsx`:

1. Aggiorna l'import da `@/components`:

```tsx
import { FilesTable } from "@/components/files-table";
import { FileEditPanel } from "@/components/file-edit-panel";
```

2. Aggiungi lo stato (accanto agli altri `useState`):

```tsx
  const [editing, setEditing] = useState<FileRow | null>(null);
```

3. Passa `onEdit` alla tabella:

```tsx
          <FilesTable rows={rows} sort={sort} dir={dir} onSort={onSort} onEdit={setEditing} />
```

4. Monta il pannello prima della chiusura di `</PageLayout>` (dopo il blocco `<div className="flex flex-col gap-4">…</div>`):

```tsx
        {editing && (
          <FileEditPanel
            row={editing}
            facets={facets}
            onClose={() => setEditing(null)}
            onSaved={(updated) => {
              setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
              setEditing(null);
            }}
          />
        )}
```

- [ ] **Step 4: Typecheck and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: nessun errore.

- [ ] **Step 5: Browser verification**

Avvia backend e frontend, poi verifica nel Browser pane:

1. `preview_start` col dev server frontend (`.claude/launch.json`), assicurandoti che il backend giri su :8010 (`backend/.venv/bin/uvicorn app.main:app --reload --port 8010`).
2. Vai su `/files`, clicca una riga → si apre il pannello coi campi pre-riempiti.
3. Cambia `Artist` e `Genre`, salva → il pannello si chiude, la riga in tabella riflette i nuovi valori; `read_console_messages` senza errori.
4. Vai su `/history` → compare una run con etichetta "manual edit"; l'undo la riporta indietro.
5. `computer {action:"screenshot"}` come prova del pannello aperto.

Se emergono errori, correggi i sorgenti e ripeti dallo Step 4.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/file-edit-panel.tsx frontend/components/files-table.tsx \
        frontend/app/files/page.tsx
git commit -m "feat(manual-edit): pannello di modifica tag nella schermata FILES"
```

---

## Note di integrazione finale

- Al termine, la suite backend completa deve restare verde: `backend/.venv/bin/python -m pytest backend/tests -q`.
- Comportamento noto e voluto: una modifica manuale **non** rilancia il rilevamento issue (chiude quelle esistenti sui campi toccati, ma svuotare un campo obbligatorio non ne crea di nuove finché non si ri-scansiona). Documentato nella spec.
- Fuori scope confermato: rating (stelline) e cover; edit inline e bulk.
