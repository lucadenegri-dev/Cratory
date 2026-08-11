# Forza ricerca provider (riclassificazione tracce già taggate) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere una ricerca provider "per traccia" (MusicBrainz→Discogs, con fingerprint AcoustID automatico) che propone override di `genre/album/label/year` **anche su tracce già taggate**, con due livelli di confidenza per-campo, revisionabili nel flusso esistente accept → PLAN → apply.

**Architecture:** Un core sincrono testabile (`provider_rescan.rescan`) fa il loop per-traccia (fingerprint → lookup con confidenza → upsert/delete di issue sintetiche `provider_override`). Un job in background (`provider_rescan_job`, sullo stampo di `scan_job`) lo esegue costruendo i provider reali. Nuovi endpoint in `issues.py` avviano il job, ne espongono lo stato e accettano in blocco le proposte ad alta confidenza. Il frontend aggiunge un pannello nella pagina ISSUES e mostra `vecchio → proposta` + badge di confidenza.

**Tech Stack:** Python 3 · FastAPI · SQLAlchemy 2 (Mapped) · Pydantic v2 · pytest + TestClient · Next.js (React, TypeScript) · Tailwind.

## Global Constraints

- **Test pristine:** pytest gira con `filterwarnings = error`; nessun warning tollerato.
- **JSON-null filtrato in Python:** la colonna JSON serializza `None` come `'null'`; i filtri su `suggested_fix_json is None` / `.get("source")` si fanno in Python, non in SQL (convenzione del codebase).
- **Router sottili:** la logica sta nei service; i router validano e delegano.
- **Mai override di `artist`/`title`:** i campi ammessi sono esattamente `{"genre","album","label","year"}`.
- **Marker `suggested_fix_json` degli override:** `{"field": <field>, "action": "retag", "to": <str>, "source": "provider", "confidence": "high"|"text"}`.
- **Issue override:** `type="provider_override"`, `severity="info"`, `status="open"`, `field ∈ {genre,album,label,year}`. UniqueConstraint `(file_id, type, field)` → una riga per `(file, campo)`.
- **Confidenza:** `high` = match MusicBrainz per MBID/ISRC esatto (`confidence >= 95`); `text` = match testuale MusicBrainz o qualunque campo da Discogs.
- **Mono-job:** il job rescan ha stato in memoria con lock (come `scan_job`); rifiuta l'avvio se un altro rescan è `running`, e l'endpoint rifiuta (409) se scan o apply sono in corso.
- **Import lazy dei provider:** `MusicBrainzProvider`/`DiscogsMetaClient`/`AcoustIDClient` si importano dentro le funzioni che li costruiscono (come già fa `provider_suggest`), mai a modulo.

---

### Task 1: `text_providers.lookup_with_conf()` — lookup con confidenza per-campo

**Files:**
- Modify: `backend/app/services/text_providers.py`
- Test: `backend/tests/test_text_providers_conf.py` (create)

**Interfaces:**
- Consumes: `MusicBrainzProvider.lookup()` (ritorna dict con chiavi `canonical_artist/title/album`, `label`, `genre_primary`, `release_date`, `mbid`, `confidence`), `DiscogsMetaClient.lookup()`, `normalize_genre()`.
- Produces: `lookup_with_conf(file, *, mb=None, discogs=None) -> dict[str, tuple[Any, str]]` — mappa `campo → (valore, confidenza)` con confidenza `"high"|"text"`. `lookup()` resta invariato nel comportamento (stessa mappa `campo → valore`), ora delega a `lookup_with_conf`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_text_providers_conf.py
from app.services import text_providers
from tests.conftest import make_audio_file


class FakeMB:
    def __init__(self, res):
        self.res = res

    def lookup(self, **kw):
        return self.res


class FakeDiscogs:
    def __init__(self, res):
        self.res = res

    def lookup(self, **kw):
        return self.res


def test_high_confidence_from_exact_mb_match():
    f = make_audio_file(1, artist="SLV", title="Dreamscapes", mbid="mb-1")
    mb = FakeMB({"canonical_artist": "SLV", "genre_primary": "Tech House",
                 "confidence": 95})
    out = text_providers.lookup_with_conf(f, mb=mb, discogs=None)
    assert out["genre"] == ("Tech House", "high")
    assert out["artist"] == ("SLV", "high")


def test_text_confidence_from_fuzzy_mb_match():
    f = make_audio_file(2, artist="SLV", title="Dreamscapes")
    mb = FakeMB({"genre_primary": "House", "confidence": 70})
    out = text_providers.lookup_with_conf(f, mb=mb, discogs=None)
    assert out["genre"] == ("House", "text")


def test_discogs_gap_fill_is_text_even_with_high_mb():
    f = make_audio_file(3, artist="SLV", title="Dreamscapes", mbid="mb-3")
    mb = FakeMB({"canonical_title": "Dreamscapes", "confidence": 95})  # no genre/label
    discogs = FakeDiscogs({"label": "Drumcode", "genre_primary": "Techno"})
    out = text_providers.lookup_with_conf(f, mb=mb, discogs=discogs)
    assert out["title"] == ("Dreamscapes", "high")
    assert out["label"] == ("Drumcode", "text")
    assert out["genre"] == ("Techno", "text")


def test_lookup_still_returns_flat_values():
    f = make_audio_file(4, artist="SLV", title="Dreamscapes", mbid="mb-4")
    mb = FakeMB({"genre_primary": "House", "confidence": 95})
    assert text_providers.lookup(f, mb=mb, discogs=None) == {"genre": "House"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_text_providers_conf.py -v`
Expected: FAIL — `AttributeError: module 'app.services.text_providers' has no attribute 'lookup_with_conf'`.

- [ ] **Step 3: Write minimal implementation**

Replace the body of `backend/app/services/text_providers.py` from `def lookup(...)` to the end with:

```python
def lookup_with_conf(file, *, mb=None, discogs=None) -> dict[str, tuple[Any, str]]:
    """Come lookup() ma ogni campo porta la confidenza con cui è stato ottenuto:
    'high' = match MusicBrainz esatto (MBID/ISRC, confidence >= 95), 'text' =
    match testuale MusicBrainz o qualunque campo da Discogs (che cerca per testo)."""
    out: dict[str, tuple[Any, str]] = {}
    mb_res = mb.lookup(title=file.title, artist=file.artist,
                       isrc=(file.isrc.strip() or None) if file.isrc else None,
                       mbid=getattr(file, "mbid", None)) if mb else None
    if mb_res:
        conf = "high" if (mb_res.get("confidence") or 0) >= 95 else "text"
        if mb_res.get("canonical_artist"):
            out["artist"] = (mb_res["canonical_artist"], conf)
        if mb_res.get("canonical_title"):
            out["title"] = (mb_res["canonical_title"], conf)
        if mb_res.get("canonical_album"):
            out["album"] = (mb_res["canonical_album"], conf)
        if mb_res.get("label"):
            out["label"] = (mb_res["label"], conf)
        if mb_res.get("genre_primary") and (g := normalize_genre(mb_res["genre_primary"])) is not None:
            out["genre"] = (g, conf)
        if (y := _year(mb_res.get("release_date"))) is not None:
            out["year"] = (y, conf)

    # Discogs riempie SOLO i buchi (MusicBrainz ha precedenza) ed è sempre 'text'.
    needs = "label" not in out or "genre" not in out
    if discogs and needs:
        dg_res = discogs.lookup(artist=file.artist, title=file.title)
        if dg_res:
            if "label" not in out and dg_res.get("label"):
                out["label"] = (dg_res["label"], "text")
            if "genre" not in out and dg_res.get("genre_primary") \
                    and (g := normalize_genre(dg_res["genre_primary"])) is not None:
                out["genre"] = (g, "text")
            if "year" not in out and (y := _year(dg_res.get("release_date"))) is not None:
                out["year"] = (y, "text")
    return out


def lookup(file, *, mb=None, discogs=None) -> dict[str, Any]:
    """Compat: mappa campo→valore (senza confidenza). Delegata a lookup_with_conf."""
    return {k: v for k, (v, _c) in lookup_with_conf(file, mb=mb, discogs=discogs).items()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_text_providers_conf.py tests/ -k "text_provider or provider_suggest" -v`
Expected: PASS (nuovi test verdi + i test provider esistenti ancora verdi).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/text_providers.py backend/tests/test_text_providers_conf.py
git commit -m "feat(providers): lookup_with_conf con confidenza per-campo (high/text)"
```

---

### Task 2: `fingerprint.fingerprint_one()` — fingerprint di un singolo file

**Files:**
- Modify: `backend/app/services/fingerprint.py`
- Test: `backend/tests/test_fingerprint_one.py` (create)

**Interfaces:**
- Consumes: `client.identify(path) -> list[dict{mbid,score}]` (può sollevare `AcoustIDError`).
- Produces: `fingerprint_one(file, client, *, threshold=0.5) -> str | None` — se trova un candidato sopra soglia con `mbid`, imposta `file.mbid` (senza commit) e ritorna l'mbid; altrimenti `None`. Non solleva: cattura `AcoustIDError` e ritorna `None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_fingerprint_one.py
from app.integrations.acoustid import AcoustIDError
from app.services.fingerprint import fingerprint_one
from tests.conftest import make_audio_file


class FakeClient:
    def __init__(self, candidates=None, error=False):
        self.candidates = candidates or []
        self.error = error

    def identify(self, path):
        if self.error:
            raise AcoustIDError("boom")
        return self.candidates


def test_sets_mbid_when_above_threshold():
    f = make_audio_file(1)
    client = FakeClient([{"mbid": "mb-1", "score": 0.9}])
    assert fingerprint_one(f, client) == "mb-1"
    assert f.mbid == "mb-1"


def test_none_when_below_threshold():
    f = make_audio_file(2)
    client = FakeClient([{"mbid": "mb-2", "score": 0.2}])
    assert fingerprint_one(f, client) is None
    assert f.mbid is None


def test_none_and_no_raise_on_error():
    f = make_audio_file(3)
    client = FakeClient(error=True)
    assert fingerprint_one(f, client) is None
    assert f.mbid is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_fingerprint_one.py -v`
Expected: FAIL — `ImportError: cannot import name 'fingerprint_one'`.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/services/fingerprint.py` (after the imports, before or after `fingerprint_files`):

```python
def fingerprint_one(file, client, *, threshold: float = 0.5) -> str | None:
    """Fingerprint di un singolo file: imposta file.mbid (senza commit) e lo
    ritorna se c'è un candidato sopra soglia; None altrimenti. Non solleva."""
    from app.integrations.acoustid import AcoustIDError
    try:
        candidates = client.identify(file.path)
    except AcoustIDError as exc:
        logger.warning("Fingerprint %s fallito: %s", file.path, exc)
        return None
    if not candidates:
        return None
    best = candidates[0]
    if best.get("score", 0) >= threshold and best.get("mbid"):
        file.mbid = best["mbid"]
        return best["mbid"]
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_fingerprint_one.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/fingerprint.py backend/tests/test_fingerprint_one.py
git commit -m "feat(fingerprint): fingerprint_one per singolo file (no commit)"
```

---

### Task 3: `provider_rescan.rescan()` — core sincrono della ricerca forzata

**Files:**
- Create: `backend/app/services/provider_rescan.py`
- Test: `backend/tests/test_provider_rescan_core.py` (create)

**Interfaces:**
- Consumes: `text_providers.lookup_with_conf` (Task 1), `fingerprint.fingerprint_one` (Task 2), modelli `AudioFile`/`Issue`, `utcnow`.
- Produces:
  - `RESCAN_FIELDS = ("genre", "album", "label", "year")`
  - `rescan(db, *, folder=None, genre=None, fields=None, mb, discogs, ac_client=None, on_progress=None) -> dict` — result: `{"configured": True, "acoustid_available": bool, "scanned": int, "fingerprinted": int, "matched": int, "no_match": int, "proposed_high": int, "proposed_text": int}`.
  - Helper riusabili: `upsert_override(db, file_id, field, value, confidence)`, `delete_stale_override(db, file_id, field)`, `has_open_inspector_issue(db, file_id, field) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_provider_rescan_core.py
from app.models import AudioFile, Issue, ScanRoot
from app.services import provider_rescan


class FakeMB:
    def __init__(self, by_title):
        self.by_title = by_title

    def lookup(self, *, title, artist, isrc=None, mbid=None):
        return self.by_title.get(title)


class FakeDiscogs:
    def lookup(self, *, artist, title):
        return None


def _add(db, **over):
    root = db.query(ScanRoot).first()
    if root is None:
        root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, ext="mp3", size_bytes=1, hash_method="file",
                  status="present", **over)
    db.add(f); db.flush()
    return f


def test_proposes_override_when_genre_differs(db):
    _add(db, path="/m/House/a.mp3", title="A", artist="X", genre="house")
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    res = provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    iss = db.query(Issue).filter_by(type="provider_override").one()
    assert iss.field == "genre" and iss.status == "open"
    assert iss.suggested_fix_json == {"field": "genre", "action": "retag",
                                      "to": "House", "source": "provider",
                                      "confidence": "high"}
    assert res["proposed_high"] == 1 and res["proposed_text"] == 0


def test_no_override_when_genre_equal(db):
    _add(db, path="/m/a.mp3", title="A", artist="X", genre="House")
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    assert db.query(Issue).filter_by(type="provider_override").count() == 0


def test_folder_filter_scopes_files(db):
    _add(db, path="/m/House/a.mp3", title="A", artist="X", genre="x")
    _add(db, path="/m/Techno/b.mp3", title="B", artist="Y", genre="x")
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 80},
                 "B": {"genre_primary": "Techno", "confidence": 80}})
    res = provider_rescan.rescan(db, folder="House", fields=["genre"],
                                 mb=mb, discogs=FakeDiscogs())
    assert res["scanned"] == 1
    assert db.query(Issue).filter_by(type="provider_override").count() == 1


def test_skips_field_with_open_inspector_issue(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="house")
    db.add(Issue(file_id=f.id, type="dirty_genre", field="genre",
                 severity="warning", detail="sporco", status="open"))
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    assert db.query(Issue).filter_by(type="provider_override").count() == 0


def test_deletes_stale_open_override_when_now_equal(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="House")
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="old",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "House", "source": "provider",
                                     "confidence": "high"}, status="open"))
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    assert db.query(Issue).filter_by(type="provider_override").count() == 0


def test_keeps_accepted_override_untouched(db):
    f = _add(db, path="/m/a.mp3", title="A", artist="X", genre="house")
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="old",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Deep House", "source": "provider",
                                     "confidence": "text"}, status="accepted"))
    db.commit()
    mb = FakeMB({"A": {"genre_primary": "House", "confidence": 95}})
    provider_rescan.rescan(db, fields=["genre"], mb=mb, discogs=FakeDiscogs())
    iss = db.query(Issue).filter_by(type="provider_override").one()
    assert iss.status == "accepted" and iss.suggested_fix_json["to"] == "Deep House"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_provider_rescan_core.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.provider_rescan'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/provider_rescan.py
"""Core della ricerca provider 'per traccia' (riclassificazione). Sincrono e
testabile: i provider (mb/discogs/ac_client) sono iniettati. Produce/aggiorna
issue sintetiche 'provider_override' che confluiscono nel flusso accept/PLAN/apply."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AudioFile, Issue, utcnow
from app.services import text_providers
from app.services.fingerprint import fingerprint_one

RESCAN_FIELDS = ("genre", "album", "label", "year")
_OVERRIDE_TYPE = "provider_override"


def has_open_inspector_issue(db: Session, file_id: int, field: str) -> bool:
    """True se c'è già una issue APERTA non-override su quel (file, campo):
    in quel caso il flusso normale la gestisce, l'override non deve duplicare."""
    row = db.scalar(
        select(Issue.id).where(Issue.file_id == file_id, Issue.field == field,
                               Issue.type != _OVERRIDE_TYPE, Issue.status == "open")
    )
    return row is not None


def _get_override(db: Session, file_id: int, field: str) -> Issue | None:
    return db.scalar(select(Issue).where(
        Issue.file_id == file_id, Issue.type == _OVERRIDE_TYPE, Issue.field == field))


def upsert_override(db: Session, file_id: int, field: str, value: Any, confidence: str) -> None:
    fix = {"field": field, "action": "retag", "to": str(value),
           "source": "provider", "confidence": confidence}
    detail = f"provider: {field} → {value}"
    row = _get_override(db, file_id, field)
    if row is None:
        db.add(Issue(file_id=file_id, type=_OVERRIDE_TYPE, field=field,
                     severity="info", detail=detail, suggested_fix_json=fix, status="open"))
    elif row.status == "open":  # le decisioni utente (accepted/dismissed) restano
        row.suggested_fix_json = fix
        row.detail = detail
        row.updated_at = utcnow()


def delete_stale_override(db: Session, file_id: int, field: str) -> None:
    row = _get_override(db, file_id, field)
    if row is not None and row.status == "open":
        db.delete(row)


def _differs(current: Any, value: Any) -> bool:
    if current is None:
        return True
    if isinstance(value, int):
        return current != value
    return str(current).strip() != str(value).strip()


def rescan(db: Session, *, folder: str | None = None, genre: str | None = None,
           fields: list[str] | None = None, mb, discogs, ac_client=None,
           on_progress=None) -> dict:
    fields = [f for f in (fields or ["genre"]) if f in RESCAN_FIELDS] or ["genre"]
    stmt = select(AudioFile).where(AudioFile.status == "present")
    if folder:
        stmt = stmt.where(AudioFile.path.ilike(f"%{folder}%"))
    if genre:
        stmt = stmt.where(AudioFile.genre == genre)
    files = db.scalars(stmt).all()
    total = len(files)
    res = {"configured": True, "acoustid_available": ac_client is not None,
           "scanned": total, "fingerprinted": 0, "matched": 0, "no_match": 0,
           "proposed_high": 0, "proposed_text": 0}

    for idx, f in enumerate(files):
        if on_progress is not None:
            on_progress(idx, total, "looking_up")
        if not f.mbid and ac_client is not None and fingerprint_one(f, ac_client):
            res["fingerprinted"] += 1
        found = text_providers.lookup_with_conf(f, mb=mb, discogs=discogs)
        res["matched" if found else "no_match"] += 1
        for field in fields:
            if field not in found:
                delete_stale_override(db, f.id, field)
                continue
            value, conf = found[field]
            if not _differs(getattr(f, field), value):
                delete_stale_override(db, f.id, field)
                continue
            if has_open_inspector_issue(db, f.id, field):
                continue
            upsert_override(db, f.id, field, value, conf)
            res["proposed_high" if conf == "high" else "proposed_text"] += 1
        db.commit()

    if on_progress is not None:
        on_progress(total, total, "looking_up")
    return res
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_provider_rescan_core.py -v`
Expected: PASS (tutti e 6).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/provider_rescan.py backend/tests/test_provider_rescan_core.py
git commit -m "feat(rescan): core provider_rescan.rescan con override sintetiche"
```

---

### Task 4: `_merge_issues` preserva le `provider_override` dal re-scan

**Files:**
- Modify: `backend/app/services/analysis.py:35-37`
- Test: `backend/tests/test_merge_preserves_override.py` (create)

**Interfaces:**
- Consumes: `analysis.recompute` / `_merge_issues`.
- Produces: nessuna nuova firma; cambia solo il comportamento del delete-sweep (salta `type == "provider_override"`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_merge_preserves_override.py
from app.models import AudioFile, Issue, ScanRoot
from app.services import analysis


def test_recompute_keeps_provider_override(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", artist="X", title="A",
                  genre="House")
    db.add(f); db.flush()
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="override",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Tech House", "source": "provider",
                                     "confidence": "high"}, status="open"))
    db.commit()

    analysis.recompute(db)  # l'Inspector NON produce provider_override

    assert db.query(Issue).filter_by(type="provider_override").count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_merge_preserves_override.py -v`
Expected: FAIL — l'override viene cancellato dal delete-sweep (`count == 0`).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/analysis.py`, cambia il loop finale di `_merge_issues`:

```python
    for key, row in existing.items():
        # Le 'provider_override' non sono prodotte dall'Inspector: gestite solo
        # dal job di rescan. Non cancellarle nel merge, o un re-scan azzererebbe
        # gli override pendenti.
        if key not in seen and row.type != "provider_override":
            db.delete(row)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_merge_preserves_override.py tests/ -k "analysis or merge or inspector" -v`
Expected: PASS (nuovo test + test analisi esistenti verdi).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/analysis.py backend/tests/test_merge_preserves_override.py
git commit -m "fix(analysis): _merge_issues non cancella le provider_override"
```

---

### Task 5: Job in background `provider_rescan_job`

**Files:**
- Create: `backend/app/services/provider_rescan_job.py`
- Test: `backend/tests/test_provider_rescan_job.py` (create)

**Interfaces:**
- Consumes: `provider_rescan.rescan` (Task 3), `settings`, `acoustid`, `SessionLocal`, `utcnow`.
- Produces: `start_job(folder=None, genre=None, fields=None) -> dict`, `job_state() -> dict`, `is_running() -> bool`. Stato: `{status, phase, processed, total, result, error, started_at, finished_at}` (stessa forma di `scan_job`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_provider_rescan_job.py
import time

from app.models import AudioFile, ScanRoot
from app.services import provider_rescan_job


def _wait_done(timeout=5.0):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        st = provider_rescan_job.job_state()
        if st["status"] in ("done", "error"):
            return st
        time.sleep(0.02)
    raise AssertionError("job non terminato")


def test_job_runs_and_reports_done(db, monkeypatch):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    db.add(AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", title="A", genre="x"))
    db.commit()

    # provider + fingerprint neutralizzati: niente rete nel test
    monkeypatch.setattr("app.services.provider_rescan.text_providers.lookup_with_conf",
                        lambda f, **kw: {})
    monkeypatch.setattr(provider_rescan_job.acoustid, "acoustid_configured", lambda: False)

    provider_rescan_job.start_job(fields=["genre"])
    st = _wait_done()
    assert st["status"] == "done"
    assert st["result"]["scanned"] == 1
    assert st["result"]["acoustid_available"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_provider_rescan_job.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.provider_rescan_job'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/provider_rescan_job.py
"""Job di rescan provider in background. Mono-job con stato in memoria (come
scan_job): la UI lancia e poi fa polling di job_state()."""

import logging
import threading

from app.core.config import settings
from app.db import SessionLocal
from app.integrations import acoustid
from app.models import utcnow
from app.services import provider_rescan

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle", "phase": None, "processed": 0, "total": 0,
    "result": None, "error": None, "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def _run(folder, genre, fields) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int, phase: str) -> None:
        with _lock:
            _state.update(processed=processed, total=total, phase=phase)

    try:
        from app.integrations.discogs_meta import DiscogsMetaClient
        from app.integrations.musicbrainz import MusicBrainzProvider

        mb = MusicBrainzProvider(user_agent=settings.musicbrainz_user_agent)
        discogs = DiscogsMetaClient()
        ac_client = None
        if acoustid.acoustid_configured() and acoustid.fpcalc_available():
            try:
                ac_client = acoustid.get_acoustid_client()
            except acoustid.AcoustIDError:
                ac_client = None
        result = provider_rescan.rescan(
            db, folder=folder, genre=genre, fields=fields,
            mb=mb, discogs=discogs, ac_client=ac_client, on_progress=on_progress)
        with _lock:
            _state.update(status="done", phase=None, result=result,
                          finished_at=utcnow().isoformat())
        logger.info("Rescan provider completato: %s", result)
    except Exception as exc:  # noqa: BLE001 — il job non deve propagare
        logger.exception("Rescan provider fallito")
        with _lock:
            _state.update(status="error", error=str(exc), finished_at=utcnow().isoformat())
    finally:
        db.close()


def start_job(folder=None, genre=None, fields=None) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(
            status="running", phase="looking_up", processed=0, total=0,
            result=None, error=None, started_at=utcnow().isoformat(), finished_at=None,
        )
        snapshot = dict(_state)
    threading.Thread(target=_run, args=(folder, genre, fields), daemon=True).start()
    return snapshot
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_provider_rescan_job.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/provider_rescan_job.py backend/tests/test_provider_rescan_job.py
git commit -m "feat(rescan): job in background provider_rescan_job"
```

---

### Task 6: Endpoint start/status + accept-high + `ProviderRescanBody`

**Files:**
- Modify: `backend/app/schemas.py` (aggiungi `ProviderRescanBody`)
- Modify: `backend/app/routers/issues.py` (3 route nuove)
- Test: `backend/tests/test_provider_rescan_api.py` (create)

**Interfaces:**
- Consumes: `provider_rescan_job` (Task 5), `scan_job.is_running`, `apply_job.is_running`.
- Produces:
  - `ProviderRescanBody{folder: str|None, genre: str|None, fields: list[str]=["genre"]}` — validator rifiuta con 422 campi fuori da `{genre,album,label,year}` (quindi artist/title).
  - `POST /api/issues/provider-rescan` → avvia il job (409 se scan/apply in corso), ritorna lo stato.
  - `GET /api/issues/provider-rescan/status` → `job_state()`.
  - `POST /api/issues/provider-override/accept-high` → `{"updated": int}` (accetta le override open con `confidence == "high"`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_provider_rescan_api.py
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _override(db, file_id, conf, status="open"):
    db.add(Issue(file_id=file_id, type="provider_override", field="genre",
                 severity="info", detail="x",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "House", "source": "provider",
                                     "confidence": conf}, status=status))


def _file(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", genre="x")
    db.add(f); db.flush()
    return f


def test_rejects_artist_title_fields():
    r = client.post("/api/issues/provider-rescan", json={"fields": ["artist"]})
    assert r.status_code == 422


def test_status_endpoint_returns_state():
    r = client.get("/api/issues/provider-rescan/status")
    assert r.status_code == 200
    assert set(r.json()) >= {"status", "phase", "processed", "total", "result"}


def test_accept_high_only_accepts_high(db):
    f = _file(db)
    _override(db, f.id, "high")
    f2 = AudioFile(root_id=f.root_id, path="/m/b.mp3", ext="mp3", size_bytes=1,
                   hash_method="file", status="present", genre="y")
    db.add(f2); db.flush()
    _override(db, f2.id, "text")
    db.commit()

    r = client.post("/api/issues/provider-override/accept-high")
    assert r.status_code == 200 and r.json()["updated"] == 1
    highs = db.query(Issue).filter_by(type="provider_override").all()
    by_conf = {i.suggested_fix_json["confidence"]: i.status for i in highs}
    assert by_conf == {"high": "accepted", "text": "open"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_provider_rescan_api.py -v`
Expected: FAIL — 404 sulle route inesistenti / nessun `ProviderRescanBody`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas.py` aggiungi (dopo `IssueFixBody`):

```python
from pydantic import field_validator  # in cima al file, con gli altri import pydantic


class ProviderRescanBody(BaseModel):
    folder: str | None = None
    genre: str | None = None
    fields: list[str] = ["genre"]

    @field_validator("fields")
    @classmethod
    def _only_allowed(cls, v: list[str]) -> list[str]:
        allowed = {"genre", "album", "label", "year"}
        bad = [f for f in v if f not in allowed]
        if bad:
            raise ValueError(f"campi non ammessi: {bad}")
        return v or ["genre"]
```

In `backend/app/routers/issues.py`:
- aggiorna gli import: `from app.schemas import (..., ProviderRescanBody)` e `from app.services import ai_tags, apply_job, provider_rescan_job, scan_job, text_providers`.
- aggiungi in fondo:

```python
@router.post("/provider-rescan", response_model=dict)
def provider_rescan_start(body: ProviderRescanBody | None = None):
    if scan_job.is_running() or apply_job.is_running():
        raise HTTPException(status_code=409, detail="scan o apply in corso")
    b = body or ProviderRescanBody()
    return provider_rescan_job.start_job(folder=b.folder, genre=b.genre, fields=b.fields)


@router.get("/provider-rescan/status", response_model=dict)
def provider_rescan_status():
    return provider_rescan_job.job_state()


@router.post("/provider-override/accept-high", response_model=dict)
def accept_high_overrides(db: Session = Depends(get_db)):
    rows = db.scalars(select(Issue).where(
        Issue.type == "provider_override", Issue.status == "open")).all()
    updated = 0
    for issue in rows:
        if (issue.suggested_fix_json or {}).get("confidence") == "high":
            issue.status = "accepted"
            issue.updated_at = utcnow()
            updated += 1
    db.commit()
    return {"updated": updated}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_provider_rescan_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/issues.py backend/tests/test_provider_rescan_api.py
git commit -m "feat(issues): endpoint provider-rescan start/status + accept-high"
```

---

### Task 7: `bulk()` cieco alle override quando filtra per sola severità

**Files:**
- Modify: `backend/app/routers/issues.py` (funzione `bulk`, ~riga 63-80)
- Test: `backend/tests/test_bulk_skips_override.py` (create)

**Interfaces:**
- Consumes: endpoint `POST /api/issues/bulk`.
- Produces: nessuna nuova firma; `bulk()` salta le `provider_override` a meno che `body.type == "provider_override"`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bulk_skips_override.py
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", genre="x")
    db.add(f); db.flush()
    db.add(Issue(file_id=f.id, type="missing_metadata", field="comment",
                 severity="info", detail="normale info", status="open"))
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="override",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "House", "source": "provider",
                                     "confidence": "high"}, status="open"))
    db.commit()


def test_dismiss_all_info_spares_override(db):
    _seed(db)
    r = client.post("/api/issues/bulk", json={"severity": "info", "status": "dismissed"})
    assert r.status_code == 200
    ov = db.query(Issue).filter_by(type="provider_override").one()
    assert ov.status == "open"  # non toccata


def test_bulk_targeting_override_type_still_works(db):
    _seed(db)
    r = client.post("/api/issues/bulk",
                    json={"type": "provider_override", "status": "dismissed"})
    assert r.status_code == 200 and r.json()["updated"] == 1
    ov = db.query(Issue).filter_by(type="provider_override").one()
    assert ov.status == "dismissed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_bulk_skips_override.py -v`
Expected: FAIL — `test_dismiss_all_info_spares_override` fallisce (l'override viene dismessa).

- [ ] **Step 3: Write minimal implementation**

Nella funzione `bulk` in `issues.py`, dentro il `for issue in db.scalars(stmt).all():`, aggiungi in cima al corpo del loop:

```python
    for issue in db.scalars(stmt).all():
        # Le override si toccano in blocco solo se targetizzate per tipo, mai per
        # sola severità (così "ignora tutti gli info" non cancella le proposte).
        if issue.type == "provider_override" and body.type != "provider_override":
            continue
        if body.status == "accepted" and issue.suggested_fix_json is None:
            continue
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_bulk_skips_override.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/issues.py backend/tests/test_bulk_skips_override.py
git commit -m "fix(issues): bulk per severità non tocca le provider_override"
```

---

### Task 8: `IssueRead.current_value` per il diff vecchio→nuovo

**Files:**
- Modify: `backend/app/schemas.py` (`IssueRead`)
- Modify: `backend/app/routers/issues.py` (`_to_read`)
- Test: `backend/tests/test_issue_current_value.py` (create)

**Interfaces:**
- Produces: `IssueRead.current_value: str | None` — valore attuale del tag del campo della issue (stringa) o `None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_issue_current_value.py
from fastapi.testclient import TestClient

from app.main import app
from app.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def test_current_value_reflects_file_tag(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", genre="house")
    db.add(f); db.flush()
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="x",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "House", "source": "provider",
                                     "confidence": "high"}, status="open"))
    db.commit()
    row = next(i for i in client.get("/api/issues").json()
               if i["type"] == "provider_override")
    assert row["current_value"] == "house"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_issue_current_value.py -v`
Expected: FAIL — `KeyError: 'current_value'`.

- [ ] **Step 3: Write minimal implementation**

In `schemas.py`, aggiungi a `IssueRead`:

```python
class IssueRead(BaseModel):
    ...
    artist: str | None
    title: str | None
    current_value: str | None = None
```

In `issues.py`, `_to_read`:

```python
def _to_read(issue: Issue, file: AudioFile) -> IssueRead:
    cur = getattr(file, issue.field, None) if issue.field else None
    return IssueRead(
        id=issue.id, file_id=issue.file_id, root_id=file.root_id, type=issue.type,
        field=issue.field, severity=issue.severity, detail=issue.detail,
        suggested_fix_json=issue.suggested_fix_json, status=issue.status,
        file_path=file.path, artist=file.artist, title=file.title,
        current_value=None if cur is None else str(cur),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_issue_current_value.py tests/ -k "issues" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/issues.py backend/tests/test_issue_current_value.py
git commit -m "feat(issues): IssueRead.current_value per diff vecchio→proposta"
```

---

### Task 9: Full backend suite verde

**Files:** nessuna modifica — gate di verifica.

- [ ] **Step 1: Run the whole backend suite**

Run: `cd backend && python -m pytest -q`
Expected: tutti verdi, nessun warning (`filterwarnings = error`). Se qualcosa fallisce, correggere il task relativo prima di procedere al frontend.

- [ ] **Step 2: Commit (solo se servono fix)**

```bash
git add -A && git commit -m "test: suite backend verde dopo provider-rescan"
```

---

### Task 10: API client frontend — tipi e funzioni

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces: `Issue.current_value: string | null`; `ProviderRescanBody`, `ProviderRescanResult`, `ProviderRescanJobState`; `providerRescan(body)`, `providerRescanStatus()`, `acceptHighOverrides()`.

- [ ] **Step 1: Extend the Issue interface**

In `frontend/lib/api.ts`, dentro `export interface Issue { ... }`, aggiungi dopo `title`:

```typescript
  title: string | null;
  current_value: string | null;
```

- [ ] **Step 2: Add rescan types + functions**

Dopo `providerSuggest()` (~riga 206) aggiungi:

```typescript
export interface ProviderRescanBody {
  folder?: string | null;
  genre?: string | null;
  fields: string[];
}
export interface ProviderRescanResult {
  configured: boolean;
  acoustid_available: boolean;
  scanned: number;
  fingerprinted: number;
  matched: number;
  no_match: number;
  proposed_high: number;
  proposed_text: number;
}
export interface ProviderRescanJobState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  result: ProviderRescanResult | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}
export function providerRescan(body: ProviderRescanBody) {
  return apiSend<ProviderRescanJobState>("POST", "/api/issues/provider-rescan", body);
}
export function providerRescanStatus() {
  return apiGet<ProviderRescanJobState>("/api/issues/provider-rescan/status");
}
export function acceptHighOverrides() {
  return apiSend<{ updated: number }>("POST", "/api/issues/provider-override/accept-high");
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore TypeScript/lint.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(api): tipi e funzioni provider-rescan + current_value"
```

---

### Task 11: `IssuesTable` — diff `vecchio → proposta` + badge di confidenza

**Files:**
- Modify: `frontend/components/issues-table.tsx`

**Interfaces:**
- Consumes: `Issue.current_value`, `Issue.suggested_fix_json.confidence` (Task 10).
- Produces: rendering della colonna "Correzione" con `current_value → input` e, se presente, un badge `alta`/`testuale`.

- [ ] **Step 1: Add a confidence badge helper**

In `issues-table.tsx`, dopo `SevMark`, aggiungi:

```tsx
function ConfBadge({ conf }: { conf: unknown }) {
  if (conf !== "high" && conf !== "text") return null;
  const high = conf === "high";
  return (
    <span className={cn(
      "border px-1 py-0.5 text-[9px] uppercase tracking-wider",
      high ? "border-ok text-ok" : "border-warning text-warning")}>
      {high ? "alta" : "testuale"}
    </span>
  );
}
```

- [ ] **Step 2: Show old→new in the correction cell**

In `IssueRow`, calcola la confidenza e il valore attuale e mostra il diff sopra l'input, solo per le issue `open` fixabili:

```tsx
  const fixable = issue.field != null && RETAGGABLE.has(issue.field);
  const suggested = typeof issue.suggested_fix_json?.to === "string"
    ? (issue.suggested_fix_json.to as string) : "";
  const conf = issue.suggested_fix_json?.confidence;
  const [value, setValue] = useState(suggested);
```

Nel `td` della colonna "Correzione", quando `issue.status === "open"` e `fixable`, avvolgi l'input:

```tsx
          fixable ? (
            <div className="flex flex-col gap-1">
              {(issue.current_value || conf === "high" || conf === "text") && (
                <div className="flex items-center gap-1.5 text-[10px]">
                  <span className="text-faint line-through">{issue.current_value || "∅"}</span>
                  <span className="text-faint">→</span>
                  <ConfBadge conf={conf} />
                </div>
              )}
              <input
                className="w-36 border border-border bg-bg px-2 py-1 text-[11px] text-fg-strong placeholder:text-faint focus:border-border-strong focus:outline-none"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={`scrivi ${issue.field}…`}
              />
            </div>
          ) : (
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/issues-table.tsx
git commit -m "feat(issues-table): diff vecchio→proposta + badge di confidenza"
```

---

### Task 12: Pagina ISSUES — pannello rescan, polling, accept-high

**Files:**
- Modify: `frontend/app/issues/page.tsx`

**Interfaces:**
- Consumes: `providerRescan`, `providerRescanStatus`, `acceptHighOverrides` (Task 10).
- Produces: pannello nella marginalia (input cartella/genere, checkbox campi, bottone "⇄ Forza ricerca provider"), polling locale dello stato con nota di progresso, bottone "✓ accetta tutte le alta confidenza".

- [ ] **Step 1: Add imports and state**

In `frontend/app/issues/page.tsx`, estendi l'import da `@/lib/api`:

```typescript
import {
  listIssues, listSources, setIssueStatus, fixIssue, bulkIssues, aiSuggestTags, aiSuggestGenres,
  providerSuggest, providerRescan, providerRescanStatus, acceptHighOverrides,
  type Issue, type ScanRoot, type ProviderRescanJobState,
} from "@/lib/api";
```

Dentro `IssuesPage`, aggiungi stato (vicino agli altri `useState`):

```typescript
  const [rescanFolder, setRescanFolder] = useState("");
  const [rescanGenre, setRescanGenre] = useState("");
  const [rescanFields, setRescanFields] = useState<string[]>(["genre"]);
  const [rescan, setRescan] = useState<ProviderRescanJobState | null>(null);
```

- [ ] **Step 2: Add start + polling + accept-high handlers**

Dopo `onProviderSuggest`, aggiungi:

```typescript
  const toggleField = (f: string) =>
    setRescanFields((cur) => (cur.includes(f) ? cur.filter((x) => x !== f) : [...cur, f]));

  const onProviderRescan = async () => {
    setActionError(null);
    setAiNote(null);
    try {
      const st = await providerRescan({
        folder: rescanFolder || null,
        genre: rescanGenre || null,
        fields: rescanFields.length ? rescanFields : ["genre"],
      });
      setRescan(st);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Errore");
    }
  };

  const onAcceptHigh = () =>
    act(async () => {
      const r = await acceptHighOverrides();
      setAiNote(`${r.updated} proposte ad alta confidenza accettate → andranno nel PLAN.`);
    });

  useEffect(() => {
    if (rescan?.status !== "running") return;
    const id = setInterval(async () => {
      try {
        const st = await providerRescanStatus();
        setRescan(st);
        if (st.status === "done") {
          load();
          const r = st.result;
          setAiNote(
            r
              ? `Rescan: ${r.proposed_high} proposte alta confidenza, ${r.proposed_text} testuali su ${r.scanned} tracce${r.acoustid_available ? "" : " (fingerprint off: nessuna alta confidenza)"}.`
              : "Rescan completato.",
          );
        }
        if (st.status === "error") setActionError(st.error || "Rescan fallito");
      } catch { /* backend offline */ }
    }, 1500);
    return () => clearInterval(id);
  }, [rescan?.status, load]);
```

- [ ] **Step 3: Pass props to Marginalia and render the panel**

Nel JSX passa le props nuove al componente `Marginalia`:

```tsx
        <Marginalia
          total={issues.length} bySev={bySev} byType={byType} accepted={accepted}
          onAcceptFixable={acceptAllFixable} onDismissInfo={dismissAllInfo}
          onAiSuggest={onAiSuggest} aiBusy={aiBusy}
          onAiGenres={onAiGenres} genreBusy={genreBusy}
          onProviderSuggest={onProviderSuggest} providerBusy={providerBusy}
          rescanFolder={rescanFolder} setRescanFolder={setRescanFolder}
          rescanGenre={rescanGenre} setRescanGenre={setRescanGenre}
          rescanFields={rescanFields} toggleField={toggleField}
          onProviderRescan={onProviderRescan}
          rescanRunning={rescan?.status === "running"}
          onAcceptHigh={onAcceptHigh}
        />
```

Estendi la firma e il corpo di `Marginalia`. Aggiungi ai props del tipo:

```tsx
  onProviderSuggest: () => void;
  providerBusy: boolean;
  rescanFolder: string;
  setRescanFolder: (v: string) => void;
  rescanGenre: string;
  setRescanGenre: (v: string) => void;
  rescanFields: string[];
  toggleField: (f: string) => void;
  onProviderRescan: () => void;
  rescanRunning: boolean;
  onAcceptHigh: () => void;
```

e destrutturali nella firma della funzione. Poi, dentro il blocco dei bottoni (dopo il bottone "⇄ Suggerisci da provider"), aggiungi il pannello:

```tsx
        <div className="mt-2 flex flex-col gap-1.5 border-t border-surface-2 pt-2">
          <div className="text-[10px] uppercase tracking-wider text-muted">forza ricerca provider</div>
          <input
            className="border border-border bg-bg px-2 py-1 text-[11px] text-fg-strong placeholder:text-faint"
            placeholder="cartella (es. House)…" value={rescanFolder}
            onChange={(e) => setRescanFolder(e.target.value)} />
          <input
            className="border border-border bg-bg px-2 py-1 text-[11px] text-fg-strong placeholder:text-faint"
            placeholder="genere attuale (opz.)…" value={rescanGenre}
            onChange={(e) => setRescanGenre(e.target.value)} />
          <div className="flex flex-wrap gap-2 text-[11px] text-muted">
            {["genre", "album", "label", "year"].map((f) => (
              <label key={f} className="flex items-center gap-1">
                <input type="checkbox" checked={rescanFields.includes(f)}
                  onChange={() => toggleField(f)} />
                {f}
              </label>
            ))}
          </div>
          <Button variant="primary" size="sm" onClick={onProviderRescan} disabled={rescanRunning}>
            {rescanRunning ? "rescan in corso…" : "⇄ Forza ricerca provider"}
          </Button>
          <Button variant="outline" size="sm" onClick={onAcceptHigh}>✓ accetta tutte le alta confidenza</Button>
        </div>
```

- [ ] **Step 4: Verify build + run**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/issues/page.tsx
git commit -m "feat(issues-page): pannello forza ricerca provider + polling + accept-high"
```

---

### Task 13: Verifica end-to-end nel browser

**Files:** nessuna modifica — gate di verifica manuale/preview.

- [ ] **Step 1: Avvia backend + frontend** (via i comandi/preview del progetto) e apri la pagina ISSUES.
- [ ] **Step 2:** Con almeno una traccia `present` che ha già un genere, imposta un filtro cartella, spunta `genre`, clicca **"⇄ Forza ricerca provider"**. Verifica la barra/nota di progresso e, a fine job, la comparsa di issue `provider_override` con `vecchio → proposta` e badge di confidenza.
- [ ] **Step 3:** Clicca **"✓ accetta tutte le alta confidenza"**, verifica che solo le `alta` passino ad `accepted`. Costruisci il PLAN e controlla che generino RETAG coerenti.
- [ ] **Step 4:** Lancia un re-scan e verifica che le override ancora `open` **non** vengano cancellate.
- [ ] **Step 5:** Segnala l'esito (screenshot/logs) senza commit.

---

## Note di integrazione (non-task)

- **Configurazione:** `musicbrainz_user_agent` ha un default → il provider è sempre "configured"; la confidenza `high` dipende invece da AcoustID+fpcalc (`acoustid_available`). Senza AcoustID il rescan funziona ma produce solo proposte `text`.
- **Concorrenza:** il rescan rifiuta se scan/apply sono in corso; scan/apply NON controllano il rescan (single-user, rischio trascurabile). Il rescan ha `_state` indipendente da scan_job.
- **Durata/rate-limit:** nessun tetto di righe; il filtro cartella/genere tiene i batch gestibili. MusicBrainz ~1 req/s + fingerprint: un rescan ampio può durare minuti (per questo è un job in background con progress).
- **Pulizia post-apply:** un override accettato-e-applicato resta in storico come `accepted` finché un rescan successivo non lo elimina (il provider confermerebbe il valore ormai scritto) — stesso comportamento delle issue normali.

## Self-Review

- **Copertura spec:** ambito per-traccia (Task 3), filtro cartella/genere (Task 3), campi selezionabili genre/album/label/year (Task 3/6), fingerprint auto (Task 2+3), due confidenze per-campo (Task 1+3), issue `provider_override` nel flusso accept/PLAN/apply (Task 3, planner invariato), esclusione dal merge (Task 4), job background+progress (Task 5, polling Task 12), endpoint start/status (Task 6), diff `vecchio→proposta` + badge (Task 8+11), bulk accept-high (Task 6+12), `bulk` non distrugge le override (Task 7). ✓
- **Placeholder:** nessuno — ogni step ha codice reale.
- **Coerenza tipi:** `rescan(...)` result e `ProviderRescanResult` combaciano; `suggested_fix_json.confidence` `"high"|"text"` usato coerentemente in backend (Task 3), accept-high (Task 6) e badge (Task 11); `provider_override` come stringa di tipo in Task 3/4/6/7.
