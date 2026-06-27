# DjOrganizer Chunk 2 — Inspector + Dedup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Su una libreria già scansionata, rilevare i problemi per-file (Inspector → tabella `issue`) e raggruppare i doppioni proponendo un keeper (Dedup → `dup_group`/`dup_member`), con ricalcolo che preserva le decisioni utente, esposto via endpoint e agganciato alla coda del job di scan.

**Architecture:** Due service **puri** (`inspector.py`, `dedup.py`) che ricevono righe `AudioFile` e ritornano strutture calcolate, senza toccare il DB. Un orchestratore impuro `analysis.py` legge `audio_file`, chiama i puri e fa il **merge** (upsert preservando `status`/`dismissed`/keeper override per chiave stabile). L'analisi gira in coda al job di scan e via `POST /api/analyze`. Router sottili.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest, httpx (TestClient). Nessuna nuova dipendenza.

**Spec di riferimento:** [docs/superpowers/specs/2026-06-27-djorganizer-chunk2-inspector-dedup-design.md](../specs/2026-06-27-djorganizer-chunk2-inspector-dedup-design.md)

## Global Constraints

- **SQLAlchemy 2.0** (`Mapped`/`mapped_column`), niente Alembic: nuove tabelle via `create_all`/`ensure_schema`.
- **Service `inspector` e `dedup` puri**: nessun accesso al DB, deterministici.
- **Nessuna mutazione dei file audio**: si registrano solo decisioni.
- **Match fuzzy conservativo**: artist+title normalizzati UGUALI **e** durata entro `fuzzy_dur_tol_s` (default 2.0s); i marcatori NON si rimuovono.
- **lossless** = `ext ∈ {flac, wav, aiff, aif}`.
- **`issue.status`** ∈ `{open, accepted, dismissed}`; chiave di merge `(file_id, type, field)`. **`accepted`** valido solo se l'issue ha un `suggested_fix_json`.
- **Keeper precedenza**: lossless > bitrate più alto > più tag completi > path più pulito (`(\d+)`/`copy`/`duplicate` penalizzati, poi più corto) > `id` minore.
- **`dup_group.signature`** = hash blake2b dei `file_id` membri ordinati; preserva `dismissed`/`keeper_overridden` al ricalcolo.
- **Output test pristine**: `backend/pytest.ini` ha `filterwarnings = error`.
- Comandi: `cd backend && source .venv/bin/activate && python -m pytest tests`.
- Commit message: prefisso conventional, italiano, footer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```text
backend/app/
  core/config.py        # MOD: low_bitrate_kbps, duration_min_s, duration_max_s, fuzzy_dur_tol_s
  models.py             # MOD: Issue, DupGroup, DupMember
  schemas.py            # MOD: AnalyzeSummary, IssueRead, DupMemberRead, DupGroupRead, request bodies
  services/
    inspector.py        # NEW: IssueComputed, inspect(files)
    dedup.py            # NEW: DupGroupComputed, find_duplicates(files)
    analysis.py         # NEW: recompute(db, on_progress), _merge_issues, _merge_dups, _signature
    scan_job.py         # MOD: dopo scan() chiama analysis.recompute, aggrega nel result
  routers/
    analyze.py          # NEW: POST /api/analyze
    issues.py           # NEW: GET /api/issues, POST /{id}/status, POST /bulk
    duplicates.py       # NEW: GET /api/duplicates, POST /{id}/keeper, POST /{id}/dismiss
  main.py               # MOD: include analyze, issues, duplicates router
backend/tests/
  conftest.py           # MOD: helper make_audio_file
  test_schema_chunk2.py · test_inspector.py · test_dedup.py
  test_analysis_issues.py · test_analysis_dedup.py
  test_analyze_api.py · test_issues_api.py · test_duplicates_api.py
```

---

## Task 1: Modelli + soglie config + helper di test

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/models.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_schema_chunk2.py`

**Interfaces:**
- Produces:
  - `app.models.Issue`, `app.models.DupGroup`, `app.models.DupMember`.
  - `app.core.config.settings.low_bitrate_kbps:int`, `.duration_min_s:float`, `.duration_max_s:float`, `.fuzzy_dur_tol_s:float`.
  - `tests/conftest.py::make_audio_file(id:int, **overrides) -> AudioFile` (istanza non persistita con default sensati).

- [ ] **Step 1: Aggiungi le soglie a `backend/app/core/config.py`**

Nella classe `Settings`, dopo `audio_exts`, aggiungi:

```python
    # Soglie Inspector / Dedup (chunk 2)
    low_bitrate_kbps: int = 256
    duration_min_s: float = 30.0
    duration_max_s: float = 900.0
    fuzzy_dur_tol_s: float = 2.0
```

- [ ] **Step 2: Aggiungi i modelli a `backend/app/models.py`**

In fondo al file:

```python
class Issue(Base):
    __tablename__ = "issue"
    __table_args__ = (UniqueConstraint("file_id", "type", "field", name="uq_issue_file_type_field"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"), index=True)
    type: Mapped[str] = mapped_column(String, index=True)
    field: Mapped[str | None] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String, index=True)
    detail: Mapped[str] = mapped_column(Text)
    suggested_fix_json: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DupGroup(Base):
    __tablename__ = "dup_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_kind: Mapped[str] = mapped_column(String)
    keeper_file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"))
    keeper_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    signature: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    members: Mapped[list["DupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class DupMember(Base):
    __tablename__ = "dup_member"
    __table_args__ = (UniqueConstraint("group_id", "file_id", name="uq_dupmember_group_file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("dup_group.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("audio_file.id"), index=True)
    action: Mapped[str] = mapped_column(String)

    group: Mapped["DupGroup"] = relationship(back_populates="members")
```

Verifica che l'import in cima a `models.py` includa `JSON` e `Boolean` (già presenti dal chunk 1: `from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint`). **Aggiungi `JSON`** a quell'import se manca: `from sqlalchemy import JSON, Boolean, ...`.

- [ ] **Step 3: Aggiungi `make_audio_file` a `backend/tests/conftest.py`**

In fondo al file:

```python
from app.models import AudioFile  # noqa: E402


def make_audio_file(id: int, **overrides) -> AudioFile:
    """AudioFile NON persistito con default sensati, per i test puri.
    I service puri leggono solo gli attributi; l'id va passato esplicito."""
    defaults = dict(
        root_id=1, path=f"/music/{id}.mp3", ext="mp3", size_bytes=1000,
        content_hash=f"hash{id}", hash_method="file", status="present",
        artist=None, title=None, album=None, album_artist=None, genre=None,
        year=None, label=None, track_no=None, comment=None, has_cover=False,
        bitrate=None, sample_rate=None, channels=None, duration_s=None, scan_error=None,
    )
    defaults.update(overrides)
    return AudioFile(id=id, **defaults)
```

- [ ] **Step 4: Scrivi il test che fallisce — `backend/tests/test_schema_chunk2.py`**

```python
from sqlalchemy import inspect

from app.db import engine
from app.models import DupGroup, DupMember, Issue


def test_chunk2_tables_exist():
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"issue", "dup_group", "dup_member"} <= tables


def test_issue_columns():
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("issue")}
    assert {"file_id", "type", "field", "severity", "suggested_fix_json", "status"} <= cols


def test_dup_group_columns():
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("dup_group")}
    assert {"match_kind", "keeper_file_id", "keeper_overridden", "dismissed", "signature"} <= cols
```

- [ ] **Step 5: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_schema_chunk2.py -v`
Expected: 3 passed (la fixture autouse `_fresh_db` crea le tabelle da `ensure_schema`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/app/models.py backend/tests/conftest.py backend/tests/test_schema_chunk2.py
git commit -m "feat: modelli issue/dup_group/dup_member + soglie Inspector/Dedup

Tre tabelle del chunk 2 (issue con status+field, dup_group con signature/
dismissed/keeper_overridden, dup_member), soglie in config, helper di test
make_audio_file.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Inspector (service puro)

**Files:**
- Create: `backend/app/services/inspector.py`
- Test: `backend/tests/test_inspector.py`

**Interfaces:**
- Consumes: `app.core.config.settings`, `app.models.AudioFile`, `make_audio_file` (test).
- Produces:
  - `app.services.inspector.IssueComputed` (dataclass frozen: `file_id:int, type:str, field:str|None, severity:str, detail:str, suggested_fix:dict|None`).
  - `app.services.inspector.inspect(files: list[AudioFile]) -> list[IssueComputed]`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_inspector.py`**

```python
from app.services.inspector import inspect
from tests.conftest import make_audio_file


def _types(issues):
    return {(i.type, i.field) for i in issues}


def test_scan_error_only(make=make_audio_file):
    f = make(1, scan_error="corrotto", artist=None, title=None)
    issues = inspect([f])
    assert _types(issues) == {("scan_error", None)}
    assert issues[0].severity == "error"


def test_missing_artist_title():
    f = make_audio_file(1, artist="", title=None, genre="House", year=2020, label="X",
                        duration_s=200.0, bitrate=320000, ext="mp3")
    issues = inspect([f])
    assert ("missing_required_tag", "artist") in _types(issues)
    assert ("missing_required_tag", "title") in _types(issues)
    assert all(i.severity == "error" for i in issues if i.type == "missing_required_tag")


def test_missing_metadata():
    f = make_audio_file(1, artist="A", title="T", genre=None, year=None, label=None,
                        duration_s=200.0, bitrate=320000, path="/music/A - T.mp3")
    issues = inspect([f])
    assert {("missing_metadata", "genre"), ("missing_metadata", "year"),
            ("missing_metadata", "label")} <= _types(issues)


def test_casing_fix():
    f = make_audio_file(1, artist="PINCO PALLINO", title="Bel Titolo", genre="House",
                        year=2020, label="X", duration_s=200.0, bitrate=320000,
                        path="/music/PINCO PALLINO - Bel Titolo.mp3")
    issues = inspect([f])
    casing = [i for i in issues if i.type == "inconsistent_casing"]
    assert len(casing) == 1 and casing[0].field == "artist"
    assert casing[0].suggested_fix == {"field": "artist", "action": "retag",
                                       "from": "PINCO PALLINO", "to": "Pinco Pallino"}


def test_casing_ignores_single_word_stylized():
    f = make_audio_file(1, artist="deadmau5", title="Strobe", genre="House", year=2020,
                        label="X", duration_s=200.0, bitrate=320000,
                        path="/music/deadmau5 - Strobe.mp3")
    assert not [i for i in inspect([f]) if i.type == "inconsistent_casing"]


def test_junk_title_and_comment():
    f = make_audio_file(1, artist="A", title="Track 01", comment="ripped by xyz",
                        genre="House", year=2020, label="X", duration_s=200.0,
                        bitrate=320000, path="/music/A - Track 01.mp3")
    issues = inspect([f])
    assert ("junk_tag", "title") in _types(issues)
    assert ("junk_tag", "comment") in _types(issues)


def test_low_quality_and_duration():
    f = make_audio_file(1, artist="A", title="T", genre="House", year=2020, label="X",
                        ext="mp3", bitrate=128000, duration_s=5.0, path="/music/A - T.mp3")
    issues = inspect([f])
    assert ("low_quality", None) in _types(issues)
    assert ("suspicious_duration", None) in _types(issues)


def test_lossless_not_low_quality():
    f = make_audio_file(1, artist="A", title="T", genre="House", year=2020, label="X",
                        ext="flac", bitrate=1000, duration_s=200.0,
                        path="/music/A - T.flac")
    assert not [i for i in inspect([f]) if i.type == "low_quality"]


def test_filename_mismatch():
    f = make_audio_file(1, artist="Pinco", title="Titolo", genre="House", year=2020,
                        label="X", duration_s=200.0, bitrate=320000, path="/music/track03.mp3")
    assert ("filename_tag_mismatch", None) in _types(inspect([f]))
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_inspector.py -v`
Expected: ImportError su `inspect`.

- [ ] **Step 3: Implementa `backend/app/services/inspector.py`**

```python
"""Inspector: rileva problemi per-file. Puro (nessun DB), deterministico."""

import os
import re
from dataclasses import dataclass

from app.core.config import settings
from app.models import AudioFile

_LOSSLESS = {"flac", "wav", "aiff", "aif"}
_JUNK_TITLE_RE = re.compile(r"^(track\s*\d+|\d+)$", re.IGNORECASE)
_SPAM_RE = re.compile(r"https?://|www\.|ripped by|encoded by|\.com\b", re.IGNORECASE)


@dataclass(frozen=True)
class IssueComputed:
    file_id: int
    type: str
    field: str | None
    severity: str
    detail: str
    suggested_fix: dict | None


def inspect(files: list[AudioFile]) -> list[IssueComputed]:
    out: list[IssueComputed] = []
    for f in files:
        out.extend(_inspect_one(f))
    return out


def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _casing_fix(value):
    if not isinstance(value, str):
        return None
    s = value.strip()
    if len(s.split()) < 2:  # solo multi-parola, per non toccare nomi stilizzati
        return None
    if s.isupper() or s.islower():
        proposed = s.title()
        if proposed != s:
            return proposed
    return None


def _norm_basic(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _inspect_one(f: AudioFile) -> list[IssueComputed]:
    out: list[IssueComputed] = []
    if f.scan_error:
        return [IssueComputed(f.id, "scan_error", None, "error", f.scan_error, None)]

    for field in ("artist", "title"):
        if not _present(getattr(f, field)):
            out.append(IssueComputed(f.id, "missing_required_tag", field, "error",
                                     f"{field} mancante", None))

    for field in ("genre", "year", "label"):
        if not _present(getattr(f, field)):
            out.append(IssueComputed(f.id, "missing_metadata", field, "warning",
                                     f"{field} mancante", None))

    for field in ("artist", "title", "album"):
        value = getattr(f, field)
        fix = _casing_fix(value)
        if fix is not None:
            out.append(IssueComputed(f.id, "inconsistent_casing", field, "warning",
                                     f"casing incoerente in {field}",
                                     {"field": field, "action": "retag", "from": value, "to": fix}))

    if f.title and _JUNK_TITLE_RE.match(f.title.strip()):
        out.append(IssueComputed(f.id, "junk_tag", "title", "warning", "title spazzatura",
                                 {"field": "title", "action": "clear"}))
    if f.comment and (_SPAM_RE.search(f.comment) or len(f.comment.strip()) > 200):
        out.append(IssueComputed(f.id, "junk_tag", "comment", "warning", "commento spazzatura",
                                 {"field": "comment", "action": "clear"}))

    if _present(f.artist) and _present(f.title):
        stem = _norm_basic(os.path.splitext(os.path.basename(f.path))[0])
        if _norm_basic(f.artist) not in stem and _norm_basic(f.title) not in stem:
            out.append(IssueComputed(f.id, "filename_tag_mismatch", None, "warning",
                                     "il nome file non riflette i tag", None))

    if f.ext not in _LOSSLESS and f.bitrate is not None \
            and f.bitrate < settings.low_bitrate_kbps * 1000:
        out.append(IssueComputed(f.id, "low_quality", None, "info",
                                 f"bitrate basso ({f.bitrate} bps)", None))

    if f.duration_s is not None and (f.duration_s < settings.duration_min_s
                                     or f.duration_s > settings.duration_max_s):
        out.append(IssueComputed(f.id, "suspicious_duration", None, "info",
                                 f"durata sospetta ({f.duration_s}s)", None))
    return out
```

- [ ] **Step 4: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_inspector.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/inspector.py backend/tests/test_inspector.py
git commit -m "feat: Inspector — rilevamento issue per-file (puro)

8 tipi di issue su 3 severità; casing/junk con suggested_fix; casing
conservativo (solo multi-parola tutto maiuscolo/minuscolo).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Dedup (service puro)

**Files:**
- Create: `backend/app/services/dedup.py`
- Test: `backend/tests/test_dedup.py`

**Interfaces:**
- Consumes: `app.core.config.settings`, `app.models.AudioFile`, `make_audio_file` (test).
- Produces:
  - `app.services.dedup.DupGroupComputed` (dataclass frozen: `match_kind:str, member_ids:tuple[int,...], keeper_id:int`).
  - `app.services.dedup.find_duplicates(files: list[AudioFile]) -> list[DupGroupComputed]`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_dedup.py`**

```python
from app.services.dedup import find_duplicates
from tests.conftest import make_audio_file


def test_fuzzy_flac_plus_mp3_same_track():
    flac = make_audio_file(1, artist="Pinco", title="Song", ext="flac", bitrate=1000,
                           duration_s=200.0, content_hash="a")
    mp3 = make_audio_file(2, artist="pinco", title="song", ext="mp3", bitrate=320000,
                          duration_s=200.5, content_hash="b")
    groups = find_duplicates([flac, mp3])
    assert len(groups) == 1
    g = groups[0]
    assert g.member_ids == (1, 2)
    assert g.match_kind == "fuzzy"
    assert g.keeper_id == 1  # lossless vince


def test_duration_guard_splits_versions():
    radio = make_audio_file(1, artist="A", title="Song", ext="mp3", bitrate=320000,
                            duration_s=200.0, content_hash="a")
    extended = make_audio_file(2, artist="A", title="Song", ext="mp3", bitrate=320000,
                               duration_s=360.0, content_hash="b")
    assert find_duplicates([radio, extended]) == []


def test_distinct_markers_not_grouped():
    a = make_audio_file(1, artist="A", title="Song (Radio Edit)", ext="mp3",
                        duration_s=200.0, content_hash="a")
    b = make_audio_file(2, artist="A", title="Song (Extended Mix)", ext="mp3",
                        duration_s=200.0, content_hash="b")
    assert find_duplicates([a, b]) == []


def test_exact_fallback_untagged():
    a = make_audio_file(1, artist=None, title=None, ext="mp3", content_hash="same")
    b = make_audio_file(2, artist=None, title=None, ext="mp3", content_hash="same")
    groups = find_duplicates([a, b])
    assert len(groups) == 1 and groups[0].match_kind == "exact"
    assert groups[0].member_ids == (1, 2)


def test_keeper_precedence_bitrate_then_completeness():
    low = make_audio_file(1, artist="A", title="T", ext="mp3", bitrate=128000,
                          duration_s=200.0, content_hash="a")
    high = make_audio_file(2, artist="A", title="T", ext="mp3", bitrate=320000,
                           duration_s=200.0, content_hash="b")
    groups = find_duplicates([low, high])
    assert groups[0].keeper_id == 2  # bitrate più alto


def test_deterministic():
    a = make_audio_file(1, artist="A", title="T", ext="mp3", bitrate=320000,
                        duration_s=200.0, content_hash="a")
    b = make_audio_file(2, artist="A", title="T", ext="mp3", bitrate=320000,
                        duration_s=200.0, content_hash="b")
    assert find_duplicates([a, b]) == find_duplicates([b, a])
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_dedup.py -v`
Expected: ImportError su `find_duplicates`.

- [ ] **Step 3: Implementa `backend/app/services/dedup.py`**

```python
"""Dedup: raggruppa i doppioni e propone un keeper. Puro, deterministico."""

import re
import unicodedata
from dataclasses import dataclass

from app.core.config import settings
from app.models import AudioFile

_LOSSLESS = {"flac", "wav", "aiff", "aif"}
_PATH_MARKER_RE = re.compile(r"\(\d+\)|copy|duplicate", re.IGNORECASE)
_TAG_FIELDS = ("artist", "title", "album", "album_artist", "genre", "year",
               "label", "track_no", "has_cover")


@dataclass(frozen=True)
class DupGroupComputed:
    match_kind: str
    member_ids: tuple[int, ...]
    keeper_id: int


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().lower())


def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _completeness(f: AudioFile) -> int:
    return sum(1 for k in _TAG_FIELDS if _present(getattr(f, k)))


def _path_penalty(f: AudioFile):
    return (1 if _PATH_MARKER_RE.search(f.path or "") else 0, len(f.path or ""))


def _pick_keeper(files: list[AudioFile]) -> AudioFile:
    def key(f: AudioFile):
        return (
            0 if f.ext in _LOSSLESS else 1,
            -(f.bitrate or 0),
            -_completeness(f),
            _path_penalty(f),
            f.id,
        )
    return sorted(files, key=key)[0]


def _cluster_by_duration(files: list[AudioFile]) -> list[list[AudioFile]]:
    with_dur = sorted((f for f in files if f.duration_s is not None),
                      key=lambda f: f.duration_s)
    clusters: list[list[AudioFile]] = []
    cur: list[AudioFile] = []
    anchor = None
    for f in with_dur:
        if not cur:
            cur, anchor = [f], f.duration_s
        elif f.duration_s - anchor <= settings.fuzzy_dur_tol_s:
            cur.append(f)
        else:
            clusters.append(cur)
            cur, anchor = [f], f.duration_s
    if cur:
        clusters.append(cur)
    for f in files:  # file senza durata: ognuno per sé (non clusterizzabili)
        if f.duration_s is None:
            clusters.append([f])
    return clusters


def _all_same_hash(files: list[AudioFile]) -> bool:
    hashes = {f.content_hash for f in files}
    return len(hashes) == 1 and None not in hashes


def _make_group(members: list[AudioFile], force_exact: bool = False) -> DupGroupComputed:
    match_kind = "exact" if force_exact or _all_same_hash(members) else "fuzzy"
    ids = tuple(sorted(m.id for m in members))
    return DupGroupComputed(match_kind, ids, _pick_keeper(members).id)


def find_duplicates(files: list[AudioFile]) -> list[DupGroupComputed]:
    groups: list[DupGroupComputed] = []
    used: set[int] = set()

    # Passo 1: fuzzy primario (richiede artist e title)
    by_key: dict[tuple[str, str], list[AudioFile]] = {}
    for f in files:
        if _present(f.artist) and _present(f.title):
            by_key.setdefault((_norm(f.artist), _norm(f.title)), []).append(f)
    for _key, group_files in by_key.items():
        for cluster in _cluster_by_duration(group_files):
            if len(cluster) >= 2:
                groups.append(_make_group(cluster))
                used.update(m.id for m in cluster)

    # Passo 2: esatto di recupero sui file rimasti soli
    by_hash: dict[str, list[AudioFile]] = {}
    for f in files:
        if f.id in used or not f.content_hash:
            continue
        by_hash.setdefault(f.content_hash, []).append(f)
    for _h, group_files in by_hash.items():
        if len(group_files) >= 2:
            groups.append(_make_group(group_files, force_exact=True))

    return sorted(groups, key=lambda g: g.member_ids)
```

- [ ] **Step 4: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_dedup.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dedup.py backend/tests/test_dedup.py
git commit -m "feat: Dedup — fuzzy con guardia durata + esatto di recupero (puro)

Match conservativo (artist+title normalizzati + durata entro tolleranza, niente
strip dei marcatori); keeper deterministico per precedenza lossless>bitrate>
completezza>path>id.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Analysis — merge degli issue

**Files:**
- Create: `backend/app/services/analysis.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_analysis_issues.py`

**Interfaces:**
- Consumes: `inspector.inspect`, `app.models` (AudioFile, Issue, utcnow), `app.db`.
- Produces:
  - `app.schemas.AnalyzeSummary` (Pydantic): `issues_total:int`, `issues_by_severity:dict[str,int]`, `dup_groups:int`, `dup_files:int`, `started_at/finished_at: datetime|None`.
  - `app.services.analysis.recompute(db, on_progress=None) -> AnalyzeSummary`.
  - `app.services.analysis._merge_issues(db, computed: list[IssueComputed]) -> None`.

- [ ] **Step 1: Aggiungi `AnalyzeSummary` a `backend/app/schemas.py`**

In fondo al file:

```python
class AnalyzeSummary(BaseModel):
    issues_total: int = 0
    issues_by_severity: dict[str, int] = {}
    dup_groups: int = 0
    dup_files: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

- [ ] **Step 2: Scrivi i test che falliscono — `backend/tests/test_analysis_issues.py`**

```python
from sqlalchemy import select

from app.models import AudioFile, Issue
from app.services.analysis import recompute


def _add_file(db, **kw):
    defaults = dict(root_id=1, path="/m/x.mp3", ext="mp3", size_bytes=1, hash_method="file",
                    status="present", has_cover=False)
    defaults.update(kw)
    f = AudioFile(**defaults)
    db.add(f)
    db.commit()
    return f


def test_recompute_creates_issues(db):
    _add_file(db, path="/m/a.mp3", artist="", title="", content_hash="a")
    summary = recompute(db)
    issues = db.scalars(select(Issue)).all()
    assert any(i.type == "missing_required_tag" for i in issues)
    assert summary.issues_total == len(issues)


def test_dismissed_survives_recompute(db):
    _add_file(db, path="/m/a.mp3", artist="A", title="T", genre=None, year=2020, label="X",
              duration_s=200.0, bitrate=320000, content_hash="a")
    recompute(db)
    genre_issue = db.scalar(select(Issue).where(Issue.type == "missing_metadata",
                                                Issue.field == "genre"))
    genre_issue.status = "dismissed"
    db.commit()
    recompute(db)
    again = db.scalar(select(Issue).where(Issue.type == "missing_metadata",
                                          Issue.field == "genre"))
    assert again.status == "dismissed"


def test_stale_issue_deleted(db):
    f = _add_file(db, path="/m/a.mp3", artist="A", title="T", genre=None, year=2020,
                  label="X", duration_s=200.0, bitrate=320000, content_hash="a")
    recompute(db)
    assert db.scalar(select(Issue).where(Issue.field == "genre")) is not None
    f.genre = "House"  # buco riempito
    db.commit()
    recompute(db)
    assert db.scalar(select(Issue).where(Issue.field == "genre")) is None
```

- [ ] **Step 3: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_analysis_issues.py -v`
Expected: ImportError su `recompute`.

- [ ] **Step 4: Implementa `backend/app/services/analysis.py`**

```python
"""Orchestratore dell'analisi: legge audio_file, chiama Inspector/Dedup, fa il merge
preservando le decisioni utente. Impuro (scrive il DB)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AudioFile, Issue, utcnow
from app.schemas import AnalyzeSummary
from app.services.inspector import inspect


def _merge_issues(db: Session, computed) -> None:
    existing = {(i.file_id, i.type, i.field): i for i in db.scalars(select(Issue)).all()}
    seen: set = set()
    for c in computed:
        key = (c.file_id, c.type, c.field)
        seen.add(key)
        row = existing.get(key)
        if row is None:
            db.add(Issue(file_id=c.file_id, type=c.type, field=c.field, severity=c.severity,
                         detail=c.detail, suggested_fix_json=c.suggested_fix, status="open"))
        else:
            row.severity = c.severity
            row.detail = c.detail
            row.suggested_fix_json = c.suggested_fix
            row.updated_at = utcnow()
    for key, row in existing.items():
        if key not in seen:
            db.delete(row)


def _summary(db: Session) -> AnalyzeSummary:
    by_sev = dict(db.execute(
        select(Issue.severity, func.count()).group_by(Issue.severity)
    ).all())
    total = sum(by_sev.values())
    return AnalyzeSummary(issues_total=total, issues_by_severity=by_sev)


def recompute(db: Session, on_progress=None) -> AnalyzeSummary:
    started = utcnow()
    files = db.scalars(select(AudioFile).where(AudioFile.status == "present")).all()
    if on_progress is not None:
        on_progress(0, 1, "inspecting")
    _merge_issues(db, inspect(files))
    db.commit()
    summary = _summary(db)
    summary.started_at = started
    summary.finished_at = utcnow()
    return summary
```

- [ ] **Step 5: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_analysis_issues.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/analysis.py backend/app/schemas.py backend/tests/test_analysis_issues.py
git commit -m "feat: analysis.recompute — merge issue che preserva lo status

Upsert per (file_id, type, field): nuovi issue open, esistenti aggiornati con
status preservato (dismissed/accepted restano), issue non piu' validi cancellati.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Analysis — merge del dedup (estende `recompute`)

**Files:**
- Modify: `backend/app/services/analysis.py`
- Test: `backend/tests/test_analysis_dedup.py`

**Interfaces:**
- Consumes: Task 4, `dedup.find_duplicates`, `app.models` (DupGroup, DupMember).
- Produces: `recompute` aggiornata (popola dup_group/dup_member e i conteggi); `app.services.analysis._merge_dups(db, computed) -> None`; `app.services.analysis._signature(member_ids) -> str`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_analysis_dedup.py`**

```python
from sqlalchemy import select

from app.models import AudioFile, DupGroup, DupMember
from app.services.analysis import recompute


def _add(db, id, **kw):
    defaults = dict(id=id, root_id=1, path=f"/m/{id}.mp3", ext="mp3", size_bytes=1,
                    hash_method="file", status="present", has_cover=False,
                    artist="A", title="T", duration_s=200.0, bitrate=320000,
                    content_hash=f"h{id}")
    defaults.update(kw)
    f = AudioFile(**defaults)
    db.add(f)
    db.commit()
    return f


def test_recompute_creates_groups(db):
    _add(db, 1, ext="flac", content_hash="a")
    _add(db, 2, ext="mp3", content_hash="b")
    summary = recompute(db)
    groups = db.scalars(select(DupGroup)).all()
    assert len(groups) == 1
    assert summary.dup_groups == 1 and summary.dup_files == 2
    assert {m.action for m in db.scalars(select(DupMember)).all()} == {"keep", "remove"}


def test_keeper_override_preserved(db):
    _add(db, 1, ext="flac", content_hash="a")  # keeper automatico = flac (id 1)
    _add(db, 2, ext="mp3", content_hash="b")
    recompute(db)
    grp = db.scalar(select(DupGroup))
    grp.keeper_file_id = 2
    grp.keeper_overridden = True
    for m in db.scalars(select(DupMember).where(DupMember.group_id == grp.id)).all():
        m.action = "keep" if m.file_id == 2 else "remove"
    db.commit()
    recompute(db)
    grp2 = db.scalar(select(DupGroup))
    assert grp2.keeper_file_id == 2 and grp2.keeper_overridden is True


def test_dismissed_preserved(db):
    _add(db, 1, ext="flac", content_hash="a")
    _add(db, 2, ext="mp3", content_hash="b")
    recompute(db)
    grp = db.scalar(select(DupGroup))
    grp.dismissed = True
    for m in db.scalars(select(DupMember).where(DupMember.group_id == grp.id)).all():
        m.action = "keep"
    db.commit()
    recompute(db)
    grp2 = db.scalar(select(DupGroup))
    assert grp2.dismissed is True
    assert {m.action for m in db.scalars(select(DupMember)).all()} == {"keep"}


def test_composition_change_new_group(db):
    _add(db, 1, ext="flac", content_hash="a")
    _add(db, 2, ext="mp3", content_hash="b")
    recompute(db)
    db.scalar(select(DupGroup)).keeper_overridden = True
    db.commit()
    _add(db, 3, ext="mp3", content_hash="c")  # entra nel gruppo → signature cambia
    recompute(db)
    grp = db.scalar(select(DupGroup))
    assert grp.keeper_overridden is False  # gruppo nuovo, keeper automatico
    assert len(db.scalars(select(DupMember)).all()) == 3
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_analysis_dedup.py -v`
Expected: FAIL (recompute non crea ancora gruppi; `dup_groups`/`dup_files` restano 0).

- [ ] **Step 3: Aggiorna `backend/app/services/analysis.py`**

Aggiungi gli import e le funzioni, e sostituisci `recompute` e `_summary`:

```python
import hashlib

from app.models import AudioFile, DupGroup, DupMember, Issue, utcnow
from app.services.dedup import find_duplicates
```

```python
def _signature(member_ids) -> str:
    joined = ",".join(str(i) for i in sorted(member_ids))
    return hashlib.blake2b(joined.encode()).hexdigest()


def _merge_dups(db: Session, computed) -> None:
    old_groups = db.scalars(select(DupGroup)).all()
    decisions = {g.signature: (g.dismissed, g.keeper_overridden, g.keeper_file_id)
                 for g in old_groups}
    for g in old_groups:
        db.delete(g)  # la cascade all/delete-orphan rimuove anche i membri
    db.flush()
    for c in computed:
        sig = _signature(c.member_ids)
        dismissed, overridden, keeper = False, False, c.keeper_id
        if sig in decisions:
            d_dismissed, d_overridden, d_keeper = decisions[sig]
            if d_dismissed:
                dismissed = True
            elif d_overridden and d_keeper in c.member_ids:
                overridden, keeper = True, d_keeper
        grp = DupGroup(match_kind=c.match_kind, keeper_file_id=keeper,
                       keeper_overridden=overridden, dismissed=dismissed, signature=sig)
        db.add(grp)
        db.flush()
        for fid in c.member_ids:
            action = "keep" if (dismissed or fid == keeper) else "remove"
            db.add(DupMember(group_id=grp.id, file_id=fid, action=action))


def _summary(db: Session) -> AnalyzeSummary:
    by_sev = dict(db.execute(
        select(Issue.severity, func.count()).group_by(Issue.severity)
    ).all())
    dup_groups = db.scalar(select(func.count()).select_from(DupGroup)) or 0
    dup_files = db.scalar(select(func.count()).select_from(DupMember)) or 0
    return AnalyzeSummary(issues_total=sum(by_sev.values()), issues_by_severity=by_sev,
                          dup_groups=dup_groups, dup_files=dup_files)


def recompute(db: Session, on_progress=None) -> AnalyzeSummary:
    started = utcnow()
    files = db.scalars(select(AudioFile).where(AudioFile.status == "present")).all()
    if on_progress is not None:
        on_progress(0, 2, "inspecting")
    _merge_issues(db, inspect(files))
    if on_progress is not None:
        on_progress(1, 2, "deduping")
    _merge_dups(db, find_duplicates(files))
    db.commit()
    summary = _summary(db)
    summary.started_at = started
    summary.finished_at = utcnow()
    return summary
```

(Rimuovi il vecchio `_summary` e il vecchio `recompute` sostituiti; lascia `_merge_issues` invariato.)

- [ ] **Step 4: Esegui l'intera analisi e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_analysis_issues.py tests/test_analysis_dedup.py -v`
Expected: tutti passano (3 issue + 4 dedup).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/analysis.py backend/tests/test_analysis_dedup.py
git commit -m "feat: analysis.recompute — merge dedup con preservazione decisioni

dup_group/dup_member ricreati per signature; dismissed e keeper override
preservati a composizione invariata.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Trigger — job di scan + `POST /api/analyze`

**Files:**
- Modify: `backend/app/services/scan_job.py`
- Create: `backend/app/routers/analyze.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_analyze_api.py`

**Interfaces:**
- Consumes: `analysis.recompute`, `app.main.app`, `scan_job`.
- Produces: `scan_job._run` esegue anche `recompute` e mette il suo summary nel result sotto la chiave `"analysis"`; `app.routers.analyze.router` con `POST /api/analyze`.

- [ ] **Step 1: Scrivi i test che falliscono — `backend/tests/test_analyze_api.py`**

```python
import time

from fastapi.testclient import TestClient

from app.main import app


def test_analyze_endpoint(tmp_path, copy_fixture):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        root_id = client.post("/api/sources", json={"path": str(lib)}).json()["id"]
        # scan popola audio_file; poi analyze ricalcola
        client.post("/api/scan", json={"root_ids": [root_id]})
        deadline = time.time() + 5
        while time.time() < deadline:
            if client.get("/api/scan/status").json()["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        resp = client.post("/api/analyze")
        assert resp.status_code == 200
        body = resp.json()
        assert "issues_total" in body and "dup_groups" in body


def test_scan_job_runs_analysis(tmp_path, copy_fixture):
    lib = tmp_path / "lib"
    copy_fixture("mp3", lib / "a.mp3")
    with TestClient(app) as client:
        root_id = client.post("/api/sources", json={"path": str(lib)}).json()["id"]
        client.post("/api/scan", json={"root_ids": [root_id]})
        deadline = time.time() + 5
        status = {}
        while time.time() < deadline:
            status = client.get("/api/scan/status").json()
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.02)
        assert status["status"] == "done"
        assert status["result"]["inserted"] == 1          # campo scan invariato (compat chunk 1)
        assert "analysis" in status["result"]             # analisi agganciata
        assert "issues_total" in status["result"]["analysis"]
```

- [ ] **Step 2: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_analyze_api.py -v`
Expected: 404 su `/api/analyze` e `KeyError 'analysis'`.

- [ ] **Step 3: Aggiorna `backend/app/services/scan_job.py`**

Nel modulo, aggiungi l'import in cima:

```python
from app.services import analysis
```

Nella funzione `_run`, dopo `summary = scan(db, roots, on_progress=on_progress)`, sostituisci il blocco di successo. La versione attuale è:

```python
        summary = scan(db, roots, on_progress=on_progress)
        with _lock:
            _state.update(
                status="done", phase=None,
                result=summary.model_dump(mode="json"),
                finished_at=utcnow().isoformat(),
            )
        logger.info("Scan completato: %s", summary.model_dump(mode="json"))
```

Sostituiscila con (aggancia l'analisi e mantieni i campi scan al top level per compatibilità):

```python
        summary = scan(db, roots, on_progress=on_progress)
        analysis_summary = analysis.recompute(db, on_progress=on_progress)
        result = summary.model_dump(mode="json")
        result["analysis"] = analysis_summary.model_dump(mode="json")
        with _lock:
            _state.update(
                status="done", phase=None, result=result,
                finished_at=utcnow().isoformat(),
            )
        logger.info("Scan+analisi completati: %s", result)
```

- [ ] **Step 4: Crea `backend/app/routers/analyze.py`**

```python
"""Router ANALYZE: ricalcola Inspector+Dedup sui dati esistenti (no walk FS)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import analysis

router = APIRouter(prefix="/api/analyze", tags=["analyze"])


@router.post("")
def analyze(db: Session = Depends(get_db)):
    return analysis.recompute(db).model_dump(mode="json")
```

- [ ] **Step 5: Includi il router in `backend/app/main.py`**

Modifica l'import dei router e aggiungi l'include:

```python
from app.routers import analyze, scan, sources
```
```python
app.include_router(sources.router)
app.include_router(scan.router)
app.include_router(analyze.router)
```

- [ ] **Step 6: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_analyze_api.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/scan_job.py backend/app/routers/analyze.py backend/app/main.py backend/tests/test_analyze_api.py
git commit -m "feat: analisi in coda allo scan + POST /api/analyze

Il job di scan esegue recompute dopo lo scan e aggrega il summary nel result
(campi scan invariati per compat); endpoint /api/analyze per il ricalcolo.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Router ISSUES

**Files:**
- Create: `backend/app/routers/issues.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_issues_api.py`

**Interfaces:**
- Consumes: `app.db.get_db`, `app.models` (Issue, AudioFile, utcnow).
- Produces:
  - `app.schemas.IssueRead` (`id, file_id, type, field, severity, detail, suggested_fix_json, status, file_path, artist, title`), `IssueStatusBody` (`status:str`), `IssueBulkBody` (`type:str|None, severity:str|None, status:str`).
  - `app.routers.issues.router`: `GET /api/issues`, `POST /api/issues/{id}/status`, `POST /api/issues/bulk`.

- [ ] **Step 1: Aggiungi gli schemi a `backend/app/schemas.py`**

```python
class IssueRead(BaseModel):
    id: int
    file_id: int
    type: str
    field: str | None
    severity: str
    detail: str
    suggested_fix_json: dict | None
    status: str
    file_path: str
    artist: str | None
    title: str | None


class IssueStatusBody(BaseModel):
    status: str


class IssueBulkBody(BaseModel):
    type: str | None = None
    severity: str | None = None
    status: str
```

- [ ] **Step 2: Scrivi i test che falliscono — `backend/tests/test_issues_api.py`**

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue


def _seed(db):
    f = AudioFile(id=1, root_id=1, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", has_cover=False, artist="A", title="T")
    db.add(f)
    db.add(Issue(file_id=1, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante", suggested_fix_json=None, status="open"))
    db.add(Issue(file_id=1, type="inconsistent_casing", field="artist", severity="warning",
                 detail="casing", suggested_fix_json={"field": "artist", "action": "retag",
                 "from": "a", "to": "A"}, status="open"))
    db.commit()


def test_list_and_filter(db):
    _seed(db)
    with TestClient(app) as client:
        all_issues = client.get("/api/issues").json()
        assert len(all_issues) == 2
        assert all_issues[0]["file_path"] == "/m/a.mp3"
        warn = client.get("/api/issues", params={"severity": "warning"}).json()
        assert len(warn) == 2
        casing = client.get("/api/issues", params={"type": "inconsistent_casing"}).json()
        assert len(casing) == 1


def test_set_status(db):
    _seed(db)
    with TestClient(app) as client:
        casing_id = client.get("/api/issues",
                               params={"type": "inconsistent_casing"}).json()[0]["id"]
        ok = client.post(f"/api/issues/{casing_id}/status", json={"status": "accepted"})
        assert ok.status_code == 200 and ok.json()["status"] == "accepted"


def test_accept_non_fixable_rejected(db):
    _seed(db)
    with TestClient(app) as client:
        genre_id = client.get("/api/issues",
                              params={"type": "missing_metadata"}).json()[0]["id"]
        resp = client.post(f"/api/issues/{genre_id}/status", json={"status": "accepted"})
        assert resp.status_code == 400


def test_bulk_dismiss(db):
    _seed(db)
    with TestClient(app) as client:
        resp = client.post("/api/issues/bulk", json={"severity": "warning",
                                                     "status": "dismissed"})
        assert resp.json()["updated"] == 2
        assert all(i["status"] == "dismissed" for i in client.get("/api/issues").json())
```

- [ ] **Step 3: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_issues_api.py -v`
Expected: ImportError / 404.

- [ ] **Step 4: Implementa `backend/app/routers/issues.py`**

```python
"""Router ISSUES: lista filtrabile + cambio status (singolo e in blocco). Sottile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, Issue, utcnow
from app.schemas import IssueBulkBody, IssueRead, IssueStatusBody

router = APIRouter(prefix="/api/issues", tags=["issues"])
_VALID = {"open", "accepted", "dismissed"}


def _to_read(issue: Issue, file: AudioFile) -> IssueRead:
    return IssueRead(
        id=issue.id, file_id=issue.file_id, type=issue.type, field=issue.field,
        severity=issue.severity, detail=issue.detail,
        suggested_fix_json=issue.suggested_fix_json, status=issue.status,
        file_path=file.path, artist=file.artist, title=file.title,
    )


@router.get("", response_model=list[IssueRead])
def list_issues(severity: str | None = None, type: str | None = None,
                status: str | None = None, root_id: int | None = None,
                db: Session = Depends(get_db)):
    stmt = select(Issue, AudioFile).join(AudioFile, Issue.file_id == AudioFile.id)
    if severity:
        stmt = stmt.where(Issue.severity == severity)
    if type:
        stmt = stmt.where(Issue.type == type)
    if status:
        stmt = stmt.where(Issue.status == status)
    if root_id:
        stmt = stmt.where(AudioFile.root_id == root_id)
    return [_to_read(i, f) for i, f in db.execute(stmt).all()]


@router.post("/{issue_id}/status", response_model=dict)
def set_status(issue_id: int, body: IssueStatusBody, db: Session = Depends(get_db)):
    if body.status not in _VALID:
        raise HTTPException(status_code=400, detail="status non valido")
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="issue non trovato")
    if body.status == "accepted" and issue.suggested_fix_json is None:
        raise HTTPException(status_code=400, detail="issue non auto-fixabile")
    issue.status = body.status
    issue.updated_at = utcnow()
    db.commit()
    return {"id": issue.id, "status": issue.status}


@router.post("/bulk", response_model=dict)
def bulk(body: IssueBulkBody, db: Session = Depends(get_db)):
    if body.status not in _VALID:
        raise HTTPException(status_code=400, detail="status non valido")
    stmt = select(Issue)
    if body.type:
        stmt = stmt.where(Issue.type == body.type)
    if body.severity:
        stmt = stmt.where(Issue.severity == body.severity)
    updated = 0
    for issue in db.scalars(stmt).all():
        if body.status == "accepted" and issue.suggested_fix_json is None:
            continue
        issue.status = body.status
        issue.updated_at = utcnow()
        updated += 1
    db.commit()
    return {"updated": updated}
```

- [ ] **Step 5: Includi il router in `backend/app/main.py`**

```python
from app.routers import analyze, issues, scan, sources
```
```python
app.include_router(analyze.router)
app.include_router(issues.router)
```

- [ ] **Step 6: Esegui e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_issues_api.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/issues.py backend/app/schemas.py backend/app/main.py backend/tests/test_issues_api.py
git commit -m "feat: router ISSUES — lista filtrabile + status singolo/bulk

GET /api/issues con filtri e dati file; POST .../status e /bulk con guardia
'accepted solo se auto-fixabile'.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Router DUPLICATES

**Files:**
- Create: `backend/app/routers/duplicates.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_duplicates_api.py`

**Interfaces:**
- Consumes: `app.db.get_db`, `app.models` (DupGroup, DupMember, AudioFile).
- Produces:
  - `app.schemas.DupMemberRead` (`file_id, action, path, ext, bitrate, duration_s, content_hash`), `DupGroupRead` (`id, match_kind, keeper_file_id, keeper_overridden, dismissed, members:list[DupMemberRead]`), `KeeperBody` (`file_id:int`).
  - `app.routers.duplicates.router`: `GET /api/duplicates`, `POST /api/duplicates/{id}/keeper`, `POST /api/duplicates/{id}/dismiss`.

- [ ] **Step 1: Aggiungi gli schemi a `backend/app/schemas.py`**

```python
class DupMemberRead(BaseModel):
    file_id: int
    action: str
    path: str
    ext: str
    bitrate: int | None
    duration_s: float | None
    content_hash: str | None


class DupGroupRead(BaseModel):
    id: int
    match_kind: str
    keeper_file_id: int
    keeper_overridden: bool
    dismissed: bool
    members: list[DupMemberRead]


class KeeperBody(BaseModel):
    file_id: int
```

- [ ] **Step 2: Scrivi i test che falliscono — `backend/tests/test_duplicates_api.py`**

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, DupGroup, DupMember


def _seed(db):
    for i, ext in ((1, "flac"), (2, "mp3")):
        db.add(AudioFile(id=i, root_id=1, path=f"/m/{i}.{ext}", ext=ext, size_bytes=1,
                         hash_method="file", status="present", has_cover=False,
                         artist="A", title="T", duration_s=200.0, bitrate=320000,
                         content_hash=f"h{i}"))
    grp = DupGroup(id=1, match_kind="fuzzy", keeper_file_id=1, keeper_overridden=False,
                   dismissed=False, signature="sig")
    db.add(grp)
    db.add(DupMember(group_id=1, file_id=1, action="keep"))
    db.add(DupMember(group_id=1, file_id=2, action="remove"))
    db.commit()


def test_list_duplicates(db):
    _seed(db)
    with TestClient(app) as client:
        groups = client.get("/api/duplicates").json()
        assert len(groups) == 1
        assert {m["file_id"] for m in groups[0]["members"]} == {1, 2}
        assert groups[0]["keeper_file_id"] == 1


def test_set_keeper(db):
    _seed(db)
    with TestClient(app) as client:
        resp = client.post("/api/duplicates/1/keeper", json={"file_id": 2})
        assert resp.status_code == 200
        g = client.get("/api/duplicates").json()[0]
        assert g["keeper_file_id"] == 2 and g["keeper_overridden"] is True
        actions = {m["file_id"]: m["action"] for m in g["members"]}
        assert actions == {2: "keep", 1: "remove"}


def test_set_keeper_non_member_rejected(db):
    _seed(db)
    with TestClient(app) as client:
        assert client.post("/api/duplicates/1/keeper", json={"file_id": 99}).status_code == 400


def test_dismiss(db):
    _seed(db)
    with TestClient(app) as client:
        assert client.post("/api/duplicates/1/dismiss").status_code == 200
        g = client.get("/api/duplicates").json()[0]
        assert g["dismissed"] is True
        assert all(m["action"] == "keep" for m in g["members"])
```

- [ ] **Step 3: Esegui e verifica che FALLISCANO**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_duplicates_api.py -v`
Expected: ImportError / 404.

- [ ] **Step 4: Implementa `backend/app/routers/duplicates.py`**

```python
"""Router DUPLICATES: lista gruppi + scelta keeper / dismiss. Sottile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, DupGroup, DupMember
from app.schemas import DupGroupRead, DupMemberRead, KeeperBody

router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])


def _group_read(db: Session, grp: DupGroup) -> DupGroupRead:
    rows = db.execute(
        select(DupMember, AudioFile)
        .join(AudioFile, DupMember.file_id == AudioFile.id)
        .where(DupMember.group_id == grp.id)
    ).all()
    members = [DupMemberRead(file_id=m.file_id, action=m.action, path=a.path, ext=a.ext,
                             bitrate=a.bitrate, duration_s=a.duration_s,
                             content_hash=a.content_hash) for m, a in rows]
    return DupGroupRead(id=grp.id, match_kind=grp.match_kind,
                        keeper_file_id=grp.keeper_file_id,
                        keeper_overridden=grp.keeper_overridden, dismissed=grp.dismissed,
                        members=members)


@router.get("", response_model=list[DupGroupRead])
def list_duplicates(db: Session = Depends(get_db)):
    return [_group_read(db, g) for g in db.scalars(select(DupGroup)).all()]


@router.post("/{group_id}/keeper", response_model=DupGroupRead)
def set_keeper(group_id: int, body: KeeperBody, db: Session = Depends(get_db)):
    grp = db.get(DupGroup, group_id)
    if grp is None:
        raise HTTPException(status_code=404, detail="gruppo non trovato")
    members = db.scalars(select(DupMember).where(DupMember.group_id == group_id)).all()
    if body.file_id not in {m.file_id for m in members}:
        raise HTTPException(status_code=400, detail="file_id non membro del gruppo")
    grp.keeper_file_id = body.file_id
    grp.keeper_overridden = True
    grp.dismissed = False
    for m in members:
        m.action = "keep" if m.file_id == body.file_id else "remove"
    db.commit()
    return _group_read(db, grp)


@router.post("/{group_id}/dismiss", response_model=DupGroupRead)
def dismiss(group_id: int, db: Session = Depends(get_db)):
    grp = db.get(DupGroup, group_id)
    if grp is None:
        raise HTTPException(status_code=404, detail="gruppo non trovato")
    grp.dismissed = True
    for m in db.scalars(select(DupMember).where(DupMember.group_id == group_id)).all():
        m.action = "keep"
    db.commit()
    return _group_read(db, grp)
```

- [ ] **Step 5: Includi il router in `backend/app/main.py`**

```python
from app.routers import analyze, duplicates, issues, scan, sources
```
```python
app.include_router(issues.router)
app.include_router(duplicates.router)
```

- [ ] **Step 6: Esegui l'intera suite e verifica PASS**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -v`
Expected: tutti i test passano (chunk 1 + chunk 2), output pristine.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/duplicates.py backend/app/schemas.py backend/app/main.py backend/tests/test_duplicates_api.py
git commit -m "feat: router DUPLICATES — lista gruppi + keeper/dismiss

GET /api/duplicates coi dati dei membri; POST .../keeper (override + 400 su non
membro) e .../dismiss.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verifica finale del chunk

- [ ] **Suite verde e pristine:** `cd backend && source .venv/bin/activate && python -m pytest tests -v`.
- [ ] **End-to-end reale:** `uvicorn app.main:app --port 8010`; aggiungi una radice, lancia lo scan, poi `GET /api/issues` e `GET /api/duplicates` mostrano i risultati; `POST /api/analyze` ricalcola; una decisione (dismiss/keeper) sopravvive a un secondo `POST /api/analyze`.
- [ ] **Definition of Done** della spec §13 soddisfatta.

## Self-Review (svolto in fase di scrittura)

- **Spec coverage:** modelli issue/dup_group/dup_member + dismissed/status/field (Task 1) ✓; Inspector e tassonomia/severità/suggested_fix (Task 2) ✓; Dedup fuzzy+guardia durata+esatto+keeper (Task 3) ✓; merge issue che preserva status (Task 4) ✓; merge dedup che preserva dismissed/keeper override per signature (Task 5) ✓; trigger in coda allo scan + /api/analyze (Task 6) ✓; router issues con bulk e guardia accepted (Task 7) ✓; router duplicates con keeper/dismiss (Task 8) ✓; soglie config (Task 1) ✓.
- **Placeholder scan:** nessun TODO/TBD; codice completo in ogni step.
- **Type consistency:** `IssueComputed(file_id,type,field,severity,detail,suggested_fix)` e `DupGroupComputed(match_kind,member_ids,keeper_id)` usati coerentemente; `recompute(db,on_progress)->AnalyzeSummary` invariato tra Task 4 e 6; `_signature`/`_merge_dups`/`_merge_issues` coerenti; schemi `IssueRead`/`DupGroupRead` allineati ai router.
```
