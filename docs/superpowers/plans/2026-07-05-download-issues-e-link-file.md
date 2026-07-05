# Archivio download problematici + collegamento manuale file locale — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pagina persistente `/downloads/issues` con tutte le tracce dal download problematico (non trovate / da rivedere / fallite) e collegamento manuale di un file su disco alla Track dal dettaglio traccia e dall'archivio.

**Architecture:** Nessuna migrazione: i dati sono gia' su `Track` (`last_download_outcome`, `last_download_reason`). Tre endpoint nuovi (DELETE ignora-esito, GET ricerca file su disco, POST link-file che riusa `attach_local_file`), un router nuovo (`files.py`), un servizio nuovo (`file_search.py`). Frontend: pagina nuova `/downloads/issues`, due modal condivisi (revisione Soulseek estratta dalla pagina download + nuovo modal file locale), sezione "Da sistemare" ridotta a riassunto.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic (backend), Next.js 16 App Router + React 19 + Tailwind (frontend), pytest con `TestClient` + override di `get_db`.

**Spec:** `docs/superpowers/specs/2026-07-05-download-issues-e-link-file-design.md`

## Global Constraints

- Regole CLAUDE.md: router = solo HTTP, logica nei services; Cratory legge i file ma non li muta mai.
- Percorsi fuori da `LIBRARY_ROOT`/`slskd_download_dir` sono ammessi nel link manuale (pattern gia' usato dai download slskd; l'audio-hash e' la chiave di riaggancio).
- Estensioni audio: usare `AUDIO_EXTENSIONS` da `app/integrations/local_files.py`, non ridefinirle.
- Frontend: Next.js 16 ha breaking changes — prima di scrivere pagine leggere la guida pertinente in `frontend/node_modules/next/dist/docs/` se si esce dai pattern gia' presenti nel repo (le pagine nuove qui ricalcano pagine esistenti).
- Commit: messaggi in italiano, prefissi `feat:`/`test:`/`docs:`, MAI `Co-Authored-By`.
- Comandi backend: `cd backend && source .venv/bin/activate` poi `python -m pytest tests`. Comandi frontend: `cd frontend && npm run lint && npm run build`.

---

### Task 1: Endpoint "Ignora" — `DELETE /api/downloads/pending/{track_id}`

**Files:**
- Modify: `backend/app/routers/downloads.py` (dopo `download_pending`, riga ~74)
- Test: `backend/tests/test_downloads_ignore.py` (nuovo)

**Interfaces:**
- Consumes: `get_track`, `tracks_download_pending` (gia' importati in `downloads.py`), `track_out`, `TrackOut`.
- Produces: `DELETE /api/downloads/pending/{track_id}` → 200 con `TrackOut` (esito azzerato), 404 se traccia inesistente. Il frontend (Task 5) lo chiama come `ignoreDownload(trackId)`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_downloads_ignore.py`:

```python
"""Ignora (azzera esito) una traccia dall'archivio download problematici."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_ignora_azzera_esito():
    db = _db()
    t = Track(source_type="spotify", spotify_id="i1", platform_track_id="i1",
              title="T", artist="A", last_download_outcome="not_found",
              last_download_reason="nessun risultato")
    db.add(t); db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).delete(f"/api/downloads/pending/{t.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["last_download_outcome"] is None
        assert body["last_download_reason"] is None
        db.refresh(t)
        assert t.last_download_outcome is None
        assert t.last_download_reason is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_ignora_404_su_traccia_inesistente():
    db = _db()
    app.dependency_overrides[get_db] = lambda: db
    try:
        assert TestClient(app).delete("/api/downloads/pending/9999").status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Verificare che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_downloads_ignore.py -v`
Expected: FAIL — 405 Method Not Allowed (la rotta DELETE non esiste).

- [ ] **Step 3: Implementare l'endpoint**

In `backend/app/routers/downloads.py`, subito dopo la funzione `download_pending` (riga ~74):

```python
@router.delete("/pending/{track_id}", response_model=TrackOut)
def ignore_pending(track_id: int, db: Session = Depends(get_db)):
    """Ignora una "da sistemare": azzera l'esito e la traccia esce dall'archivio."""
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata.")
    track.last_download_outcome = None
    track.last_download_reason = None
    db.commit()
    db.refresh(track)
    return track_out(track)
```

Import gia' presenti nel file: `get_track`, `track_out`, `TrackOut`, `Session`, `Depends`, `HTTPException`, `get_db`. Nessun import nuovo.

- [ ] **Step 4: Verificare che passi**

Run: `python -m pytest tests/test_downloads_ignore.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_downloads_ignore.py backend/app/routers/downloads.py
git commit -m "feat: endpoint Ignora per l'archivio download (azzera esito)"
```

---

### Task 2: Servizio `file_search` + `GET /api/files/search`

**Files:**
- Create: `backend/app/services/file_search.py`
- Create: `backend/app/routers/files.py`
- Modify: `backend/app/main.py:11-25` (import router) e riga ~79 (include_router)
- Test: `backend/tests/test_file_search.py` (nuovo)

**Interfaces:**
- Consumes: `settings.library_root`, `settings.slskd_download_dir` (`app/core/config.py`), `AUDIO_EXTENSIONS` (`app/integrations/local_files.py`).
- Produces: `search_audio_files(query, *, roots=None, cap=50) -> list[dict]` con chiavi `path, name, format, size, source`; endpoint `GET /api/files/search?q=...` → `list[LocalFileOut]`. Il frontend (Task 5) lo chiama come `searchLocalFiles(q)`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_file_search.py`:

```python
"""Ricerca file audio locali per nome (servizio + endpoint)."""
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.file_search import search_audio_files


def _mk(root, rel):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def test_match_case_insensitive_e_termini_in_and(tmp_path):
    _mk(tmp_path, "Artist - Amazing Title.mp3")
    _mk(tmp_path, "sub/artist - amazing title (remix).flac")
    _mk(tmp_path, "Other - Song.mp3")
    _mk(tmp_path, "Artist - Amazing Notes.txt")  # non audio: fuori

    hits = search_audio_files("amazing artist", roots=[("library", str(tmp_path))])
    names = {h["name"] for h in hits}
    assert names == {"Artist - Amazing Title.mp3", "artist - amazing title (remix).flac"}
    assert all(h["source"] == "library" for h in hits)
    assert all(h["size"] == 1 for h in hits)


def test_query_corta_o_vuota(tmp_path):
    _mk(tmp_path, "a.mp3")
    assert search_audio_files("", roots=[("library", str(tmp_path))]) == []
    assert search_audio_files("a", roots=[("library", str(tmp_path))]) == []


def test_cap_risultati(tmp_path):
    for i in range(60):
        _mk(tmp_path, f"track {i:02d}.mp3")
    assert len(search_audio_files("track", roots=[("library", str(tmp_path))], cap=50)) == 50


def test_endpoint_usa_le_radici_configurate(tmp_path, monkeypatch):
    _mk(tmp_path / "lib", "Deep Cut.mp3")
    _mk(tmp_path / "dl", "Deep Cut (edit).mp3")
    monkeypatch.setattr(settings, "library_root", str(tmp_path / "lib"))
    monkeypatch.setattr(settings, "slskd_download_dir", str(tmp_path / "dl"))

    r = TestClient(app).get("/api/files/search", params={"q": "deep cut"})
    assert r.status_code == 200
    rows = r.json()
    assert {x["source"] for x in rows} == {"library", "downloads"}
    assert all(x["format"] == "mp3" for x in rows)


def test_radici_non_configurate_o_inesistenti(monkeypatch):
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "slskd_download_dir", "/percorso/inesistente")
    r = TestClient(app).get("/api/files/search", params={"q": "qualcosa"})
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_file_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.file_search'`.

- [ ] **Step 3: Implementare servizio, router e registrazione**

Creare `backend/app/services/file_search.py`:

```python
"""Ricerca file audio per nome nelle cartelle note (libreria e download slskd).

Modulo deterministico, sola lettura: nessun DB, nessuna scrittura su disco.
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.integrations.local_files import AUDIO_EXTENSIONS

MAX_RESULTS = 50
MIN_QUERY_LEN = 2


def search_roots() -> list[tuple[str, str]]:
    """Coppie (source, radice) configurate ed esistenti. Cartelle mancanti: saltate."""
    roots: list[tuple[str, str]] = []
    if settings.library_root and Path(settings.library_root).is_dir():
        roots.append(("library", settings.library_root))
    if settings.slskd_download_dir and Path(settings.slskd_download_dir).is_dir():
        roots.append(("downloads", settings.slskd_download_dir))
    return roots


def search_audio_files(query: str, *, roots: list[tuple[str, str]] | None = None,
                       cap: int = MAX_RESULTS) -> list[dict]:
    """Match in AND dei termini sul nome file (case-insensitive), max `cap` risultati."""
    terms = [t for t in query.strip().lower().split() if t]
    if not terms or len(query.strip()) < MIN_QUERY_LEN:
        return []
    hits: list[dict] = []
    for source, root in roots if roots is not None else search_roots():
        for path in sorted(Path(root).rglob("*")):
            if len(hits) >= cap:
                return hits
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            name = path.name.lower()
            if not all(t in name for t in terms):
                continue
            hits.append({
                "path": str(path),
                "name": path.name,
                "format": path.suffix.lower().lstrip(".") or None,
                "size": path.stat().st_size,
                "source": source,
            })
    return hits
```

Creare `backend/app/routers/files.py`:

```python
"""HTTP per la ricerca di file audio locali. Nessuna logica di business qui."""
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.file_search import search_audio_files

router = APIRouter(prefix="/api/files", tags=["files"])


class LocalFileOut(BaseModel):
    path: str
    name: str
    format: str | None = None
    size: int | None = None
    source: str


@router.get("/search", response_model=list[LocalFileOut])
def search_files(q: str = Query(default="")):
    """Cerca file audio per nome in LIBRARY_ROOT e nella cartella download slskd."""
    return [LocalFileOut(**h) for h in search_audio_files(q)]
```

In `backend/app/main.py` aggiungere `files` all'import (righe 11–25, ordine alfabetico):

```python
from app.routers import (
    ai,
    discovery,
    dj_sets,
    downloads,
    enrichment,
    files,
    labels,
    pipeline,
    playlists,
    services,
    sets,
    spotify,
    tracks,
    transitions,
)
```

e dopo `app.include_router(downloads.router)` (riga ~79):

```python
app.include_router(files.router)
```

- [ ] **Step 4: Verificare che passino**

Run: `python -m pytest tests/test_file_search.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/file_search.py backend/app/routers/files.py backend/app/main.py backend/tests/test_file_search.py
git commit -m "feat: ricerca file audio locali per nome (/api/files/search)"
```

---

### Task 3: `link_local_file` + `POST /api/tracks/{track_id}/link-file`

**Files:**
- Modify: `backend/app/services/acquisition.py`
- Modify: `backend/app/schemas.py` (dopo `TrackUpdateIn`, riga ~90)
- Modify: `backend/app/routers/tracks.py` (dopo `patch_track`, riga ~145)
- Test: `backend/tests/test_link_file.py` (nuovo)

**Interfaces:**
- Consumes: `attach_local_file` (stesso modulo), `AUDIO_EXTENSIONS` e `read_audio_quality` da `app/integrations/local_files.py`, `TrackDetailOut`/`track_detail_out` (gia' importati in `tracks.py`).
- Produces: `link_local_file(db, track, *, path: str) -> Track` che solleva `LinkFileError` (sottoclasse di `ValueError`) su path invalido; endpoint `POST /api/tracks/{track_id}/link-file` body `{"path": str}` → 200 `TrackDetailOut`, 400 su path invalido, 404 su traccia inesistente. Il frontend (Task 5) lo chiama come `linkLocalFile(trackId, path)`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_link_file.py`:

```python
"""Collegamento manuale di un file locale alla traccia."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _track(db, **kw):
    t = Track(source_type="spotify", spotify_id="l1", platform_track_id="l1",
              title="T", artist="A", **kw)
    db.add(t); db.commit()
    return t


def test_collega_file_e_azzera_esito(tmp_path):
    db = _db()
    t = _track(db, last_download_outcome="not_found", last_download_reason="x")
    f = tmp_path / "song.mp3"
    f.write_bytes(b"finto audio")

    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post(f"/api/tracks/{t.id}/link-file", json={"path": str(f)})
        assert r.status_code == 200
        body = r.json()
        assert body["has_local_file"] is True
        assert body["local_path"] == str(f)
        assert body["local_format"] == "mp3"
        assert body["last_download_outcome"] is None
        assert body["last_download_reason"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_400_su_file_inesistente(tmp_path):
    db = _db()
    t = _track(db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post(f"/api/tracks/{t.id}/link-file",
                                 json={"path": str(tmp_path / "manca.mp3")})
        assert r.status_code == 400
        assert "non trovato" in r.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_400_su_estensione_non_audio(tmp_path):
    db = _db()
    t = _track(db)
    f = tmp_path / "note.txt"
    f.write_text("no")
    app.dependency_overrides[get_db] = lambda: db
    try:
        r = TestClient(app).post(f"/api/tracks/{t.id}/link-file", json={"path": str(f)})
        assert r.status_code == 400
        assert "non audio" in r.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_404_su_traccia_inesistente(tmp_path):
    db = _db()
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    app.dependency_overrides[get_db] = lambda: db
    try:
        assert TestClient(app).post("/api/tracks/9999/link-file",
                                    json={"path": str(f)}).status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
```

Nota: `audio_hash` su un file finto fallisce (ffmpeg non decodifica) ma `attach_local_file` lo tratta gia' come warning non bloccante — il test passa con o senza ffmpeg installato.

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_link_file.py -v`
Expected: FAIL — i primi tre test falliscono (404: la rotta non esiste ancora); `test_404_su_traccia_inesistente` passa per coincidenza, va bene cosi'.

- [ ] **Step 3: Implementare servizio, schema ed endpoint**

In `backend/app/services/acquisition.py` sostituire il blocco import (righe 7–14) con:

```python
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.integrations.local_files import (
    AUDIO_EXTENSIONS, LocalFilesError, audio_hash, read_audio_quality,
)
from app.models import Track
```

e aggiungere in fondo al file:

```python
class LinkFileError(ValueError):
    """Percorso non valido per il collegamento manuale (inesistente o non audio)."""


def link_local_file(db: Session, track: Track, *, path: str) -> Track:
    """Collegamento manuale di un file su disco: valida e azzera l'esito download.

    L'uscita dall'archivio "da sistemare" avviene qui, qualunque sia la pagina
    da cui si collega (dettaglio traccia o archivio).
    """
    p = Path(path).expanduser()
    if not p.is_file():
        raise LinkFileError(f"File non trovato: {p}")
    if p.suffix.lower() not in AUDIO_EXTENSIONS:
        raise LinkFileError(f"Estensione non audio: {p.suffix or '(nessuna)'}")
    quality = read_audio_quality(p)
    track = attach_local_file(db, track, path=str(p), fmt=quality["format"],
                              bitrate=quality["bitrate"])
    track.last_download_outcome = None
    track.last_download_reason = None
    db.commit()
    db.refresh(track)
    return track
```

In `backend/app/schemas.py`, dopo `TrackUpdateIn` (riga ~90):

```python
class TrackLinkFileIn(BaseModel):
    """Collegamento manuale di un file su disco alla traccia."""
    path: str
```

In `backend/app/routers/tracks.py`: aggiungere `TrackLinkFileIn` all'import da `app.schemas` (righe 14–21), aggiungere l'import del servizio dopo gli altri import di services (riga ~26):

```python
from app.services.acquisition import LinkFileError, link_local_file
```

e dopo `patch_track` (riga ~145):

```python
@router.post("/tracks/{track_id}/link-file", response_model=TrackDetailOut)
def link_file(track_id: int, payload: TrackLinkFileIn, db: Session = Depends(get_db)):
    """Collega manualmente un file su disco alla traccia (possesso senza download)."""
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata")
    try:
        track = link_local_file(db, track, path=payload.path)
    except LinkFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return track_detail_out(track)
```

- [ ] **Step 4: Verificare che passino, con regressione sull'intera suite**

Run: `python -m pytest tests/test_link_file.py -v && python -m pytest tests`
Expected: 4 passed sul nuovo file, nessuna regressione sulla suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/acquisition.py backend/app/schemas.py backend/app/routers/tracks.py backend/tests/test_link_file.py
git commit -m "feat: collegamento manuale file locale alla traccia (link-file)"
```

---

### Task 4: API client frontend (`lib/api.ts`)

**Files:**
- Modify: `frontend/lib/api.ts` (in fondo alla sezione `--- Download (Soulseek/slskd) ---`, dopo `downloadManual`, riga ~793)

**Interfaces:**
- Consumes: `apiGet`, `apiPost`, `apiDelete`, tipi `Track`/`TrackDetail` (stesso file).
- Produces: `ignoreDownload(trackId: number): Promise<Track>`, `searchLocalFiles(q: string): Promise<LocalFileHit[]>`, `linkLocalFile(trackId: number, path: string): Promise<TrackDetail>`, `interface LocalFileHit { path; name; format; size; source }`. Usati dai Task 5–8.

- [ ] **Step 1: Aggiungere tipi e funzioni**

In fondo a `frontend/lib/api.ts`:

```typescript
/** "Ignora": azzera l'esito download, la traccia esce dall'archivio da sistemare. */
export function ignoreDownload(trackId: number) {
  return apiDelete<Track>(`/api/downloads/pending/${trackId}`);
}

// --- File locali (collegamento manuale) ---------------------------------------

export interface LocalFileHit {
  path: string;
  name: string;
  format: string | null;
  size: number | null;
  source: "library" | "downloads";
}

/** Cerca file audio per nome in LIBRARY_ROOT e nella cartella download slskd. */
export function searchLocalFiles(q: string) {
  return apiGet<LocalFileHit[]>("/api/files/search", { q });
}

/** Collega manualmente un file su disco alla traccia (possesso senza download). */
export function linkLocalFile(trackId: number, path: string) {
  return apiPost<TrackDetail>(`/api/tracks/${trackId}/link-file`, { path });
}
```

- [ ] **Step 2: Verificare lint e tipi**

Run: `cd frontend && npm run lint`
Expected: nessun errore (warning preesistenti a parte).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: client API per ignora download, ricerca file locali e link-file"
```

---

### Task 5: `DownloadReviewModal` condiviso + pagina `/downloads` con riassunto

**Files:**
- Create: `frontend/components/download-review-modal.tsx`
- Modify: `frontend/app/downloads/page.tsx` (riscrittura: estrazione modal + sezione "Da sistemare" ridotta a riassunto)

**Interfaces:**
- Consumes: `apiGet`, `downloadCandidates`, `downloadTrack`, `fmtDuration`, tipi `DownloadCandidate`/`TrackDetail` da `@/lib/api`; componenti `Modal`, `Alert`, `Button`, `Loading`, `Spinner` da `@/components/ui`.
- Produces: `DownloadReviewModal({ target, onClose, onPicked })` con `export type ReviewTarget = { track_id: number; artist: string | null; title: string | null }`. Usato anche dal Task 7.

- [ ] **Step 1: Creare il componente condiviso**

Creare `frontend/components/download-review-modal.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Download as DownloadIcon } from "lucide-react";
import { Alert, Button, Loading, Modal, Spinner } from "@/components/ui";
import {
  apiGet, downloadCandidates, downloadTrack, fmtDuration,
  type DownloadCandidate, type TrackDetail,
} from "@/lib/api";

export type ReviewTarget = { track_id: number; artist: string | null; title: string | null };

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

/** Modal "Scegli il file": candidati Soulseek per una traccia da sistemare. */
export function DownloadReviewModal({ target, onClose, onPicked }: {
  target: ReviewTarget | null;
  onClose: () => void;
  onPicked: () => void;
}) {
  const [candidates, setCandidates] = useState<DownloadCandidate[] | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!target) return;
    setCandidates(null);
    setDuration(null);
    setError(null);
    (async () => {
      try {
        // La durata attesa aiuta il ranking dei candidati (bonus/penalita' via backend).
        const track = await apiGet<TrackDetail>(`/api/tracks/${target.track_id}`);
        setDuration(track.duration_seconds);
        setCandidates(await downloadCandidates(
          track.artist ?? target.artist ?? "", track.title ?? target.title ?? "",
          track.duration_seconds));
      } catch (e) {
        setError(err(e));
        setCandidates([]);
      }
    })();
  }, [target]);

  const pick = async (c: DownloadCandidate) => {
    if (!target) return;
    setPicking(true);
    setError(null);
    try {
      await downloadTrack(target.track_id, c);
      onPicked();
    } catch (e) {
      // 409 tipico: "Un download e' gia' in corso" — riprova a job finito.
      setError(err(e));
    } finally {
      setPicking(false);
    }
  };

  return (
    <Modal open={target !== null} onClose={onClose} title="Scegli il file" size="lg">
      {target && (
        <div className="p-4">
          <p className="mb-3 text-sm text-muted">
            {target.artist ?? "?"} — {target.title ?? "?"}
            {duration != null && (
              <span className="ml-2 text-xs text-faint">durata attesa {fmtDuration(duration)}</span>
            )}
          </p>
          {error && <Alert tone="danger">⚠ {error}</Alert>}
          {candidates === null && <Loading label="Cerco i candidati su Soulseek…" />}
          {candidates?.length === 0 && (
            <p className="py-6 text-center text-sm text-muted">
              Nessun candidato in questo momento: riprova più tardi (dipende da chi è online).
            </p>
          )}
          {candidates && candidates.length > 0 && (
            <ul className="max-h-80 divide-y divide-border overflow-y-auto border border-border">
              {candidates.map((c, i) => (
                <li key={`${c.username}-${i}`} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-xs">{c.filename.split("\\").pop()}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {(c.format ?? "?").toUpperCase()}
                      {c.bitrate ? ` · ${c.bitrate} kbps` : ""}
                      {c.length ? ` · ${fmtDuration(c.length)}` : ""}
                      {" · "}{c.username}
                      {" · "}<span className="tnum">{c.confidence}</span>/100
                    </div>
                  </div>
                  <Button size="sm" onClick={() => pick(c)} disabled={picking}>
                    {picking ? <Spinner /> : <DownloadIcon size={13} />} Scarica
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
}
```

- [ ] **Step 2: Riscrivere la pagina download**

Sostituire l'intero contenuto di `frontend/app/downloads/page.tsx` con:

```tsx
"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Download as DownloadIcon, Search, Wrench } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, Input, Select, Loading } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import { DownloadReviewModal, type ReviewTarget } from "@/components/download-review-modal";
import {
  downloadManual,
  downloadPending,
  retryPending,
  listImportedPlaylists,
  searchDownloads,
  startPlaylistDownload,
  type DownloadCandidate,
  type Playlist,
  type Track,
} from "@/lib/api";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

const OUTCOME_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  downloaded: "success",
  needs_review: "warning",
  not_found: "neutral",
  failed: "danger",
};

const OUTCOME_LABEL: Record<string, string> = {
  downloaded: "scaricata",
  needs_review: "da rivedere",
  not_found: "non trovata",
  failed: "fallita",
};

export default function DownloadsPage() {
  // Lo stato del job arriva dal poller globale (JobsProvider): niente polling qui.
  const { download: status, refresh } = useJobs();
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DownloadCandidate[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [pending, setPending] = useState<Track[] | null>(null);
  const alive = useRef(true);

  const refreshPending = useCallback(() => {
    downloadPending()
      .then((rows) => alive.current && setPending(rows))
      .catch(() => {
        /* backend offline: ignora */
      });
  }, []);

  // Le "da sistemare" cambiano man mano che il job produce esiti.
  useEffect(() => { refreshPending(); }, [refreshPending, status?.status, status?.processed]);

  useEffect(() => {
    alive.current = true;
    listImportedPlaylists()
      .then((p) => alive.current && setPlaylists(p))
      .catch(() => undefined);
    return () => {
      alive.current = false;
    };
  }, []);

  const retryAll = async () => {
    setError(null);
    try {
      await retryPending();
      refresh();
    } catch (e) {
      setError(err(e));
    }
  };

  const start = async () => {
    if (!selected) return;
    setError(null);
    try {
      await startPlaylistDownload(Number(selected));
      refresh();
    } catch (e) {
      setError(err(e));
    }
  };

  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setError(null);
    setResults(null);
    try {
      setResults(await searchDownloads(q));
    } catch (e) {
      setError(err(e));
    } finally {
      setSearching(false);
    }
  };

  const grab = async (c: DownloadCandidate) => {
    setError(null);
    try {
      await downloadManual(c);
      refresh();
    } catch (e) {
      setError(err(e));
    }
  };

  const available = status?.available ?? true;
  const running = status?.status === "running";
  const count = (k: string) =>
    (pending ?? []).filter((t) => t.last_download_outcome === k).length;

  return (
    <PageLayout title="Download" meta={status?.total || undefined}>
      <div className="space-y-3">
        {!available && (
          <Alert tone="info">
            slskd non e&apos; configurato. Imposta SLSKD_URL, SLSKD_API_KEY e
            SLSKD_DOWNLOAD_DIR in backend/.env per abilitare i download.
          </Alert>
        )}

        <Card className="flex items-center gap-3 p-3">
          <Select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={!available || running}
          >
            <option value="">Scegli una playlist…</option>
            {playlists.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <Button onClick={start} disabled={!available || running || !selected}>
            <DownloadIcon size={14} /> Scarica playlist
          </Button>
        </Card>

        <Card className="p-3">
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">Ricerca manuale</div>
          <div className="flex items-center gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") runSearch();
              }}
              placeholder="Cerca su Soulseek (artista, titolo…)"
              disabled={!available}
            />
            <Button
              variant="outline"
              onClick={runSearch}
              disabled={!available || searching || !query.trim()}
            >
              <Search size={14} /> Cerca
            </Button>
          </div>
          {searching && <Loading label="Ricerca su Soulseek…" />}
          {results && results.length === 0 && !searching && (
            <p className="mt-2 text-sm text-faint">Nessun risultato per «{query}».</p>
          )}
          {results && results.length > 0 && (
            <ul className="mt-3 divide-y divide-border">
              {results.slice(0, 40).map((c, i) => (
                <li key={`${c.username}-${i}`} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm">{c.filename.split(/[\\/]/).pop()}</div>
                    <div className="text-xs text-faint">
                      {c.format?.toUpperCase()}
                      {c.bitrate ? ` · ${c.bitrate}kbps` : ""} · {c.username}
                    </div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => grab(c)} disabled={running}>
                    <DownloadIcon size={13} /> Scarica
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {pending && pending.length > 0 && (
          <Card className="p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-wider text-muted">
                Da sistemare ({pending.length})
              </span>
              <span className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={retryAll} disabled={running || !available}>
                  <DownloadIcon size={13} /> Riprova tutte
                </Button>
                <Link href="/downloads/issues">
                  <Button size="sm" variant="outline">
                    <Wrench size={13} /> Vai all&apos;archivio
                  </Button>
                </Link>
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge tone="neutral">{count("not_found")} non trovate</Badge>
              <Badge tone="warning">{count("needs_review")} da rivedere</Badge>
              <Badge tone="danger">{count("failed")} fallite</Badge>
            </div>
          </Card>
        )}

        {status && status.total > 0 && (
          <Card className="p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="tnum">{status.processed}/{status.total}</span>
              <Badge tone="success">{status.downloaded} scaricate</Badge>
              <Badge tone="warning">{status.needs_review} da rivedere</Badge>
              <Badge tone="neutral">{status.not_found} non trovate</Badge>
              <Badge tone="danger">{status.failed} fallite</Badge>
            </div>
            <ul className="mt-3 divide-y divide-border text-sm">
              {status.items.map((it) => (
                <li key={it.track_id} className="flex items-center justify-between gap-3 py-1.5">
                  <span className="truncate">
                    {it.artist ?? "Artista sconosciuto"} — {it.title ?? "Senza titolo"}
                    {it.reason && <span className="ml-2 text-xs text-muted">({it.reason})</span>}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {it.outcome !== "downloaded" && it.track_id != null && (
                      <Button size="sm" variant="outline" onClick={() => setReview(it)}>
                        <Search size={13} /> Scegli file
                      </Button>
                    )}
                    <Badge tone={OUTCOME_TONE[it.outcome] ?? "neutral"}>{OUTCOME_LABEL[it.outcome] ?? it.outcome}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        {status && status.total === 0 && available && (
          <EmptyState icon={<DownloadIcon size={28} />} title="Nessun download">
            Scegli una playlist e avvia il download.
          </EmptyState>
        )}
      </div>

      <DownloadReviewModal
        target={review}
        onClose={() => setReview(null)}
        onPicked={() => {
          refresh();
          setReview(null);
          refreshPending();
        }}
      />
    </PageLayout>
  );
}
```

- [ ] **Step 3: Verificare lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/download-review-modal.tsx frontend/app/downloads/page.tsx
git commit -m "feat: modal revisione Soulseek condiviso, Da sistemare come riassunto"
```

---

### Task 6: Componente `LinkLocalFileModal`

**Files:**
- Create: `frontend/components/link-local-file-modal.tsx`

**Interfaces:**
- Consumes: `searchLocalFiles`, `linkLocalFile`, tipi `LocalFileHit`/`TrackDetail` da `@/lib/api` (Task 4); `Modal`, `Alert`, `Button`, `Input`, `Loading`, `Spinner` da `@/components/ui`.
- Produces: `LinkLocalFileModal({ target, onClose, onLinked })` con `export type LinkTarget = { id: number; artist: string | null; title: string | null }`; `onLinked` riceve la `TrackDetail` aggiornata. Usato dai Task 7 e 8.

- [ ] **Step 1: Creare il componente**

Creare `frontend/components/link-local-file-modal.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { FolderOpen, Link2, Search } from "lucide-react";
import { Alert, Button, Input, Loading, Modal, Spinner } from "@/components/ui";
import {
  linkLocalFile, searchLocalFiles,
  type LocalFileHit, type TrackDetail,
} from "@/lib/api";

export type LinkTarget = { id: number; artist: string | null; title: string | null };

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

function fmtSize(bytes: number | null): string {
  if (!bytes) return "";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const SOURCE_LABEL: Record<string, string> = {
  library: "libreria",
  downloads: "download",
};

/** Modal "Collega file locale": ricerca per nome sul disco + percorso esatto. */
export function LinkLocalFileModal({ target, onClose, onLinked }: {
  target: LinkTarget | null;
  onClose: () => void;
  onLinked: (track: TrackDetail) => void;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<LocalFileHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [manualPath, setManualPath] = useState("");
  const [linking, setLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!target) return;
    // Precompilata con "artista titolo": di solito basta per trovare il file.
    setQuery(`${target.artist ?? ""} ${target.title ?? ""}`.trim());
    setHits(null);
    setManualPath("");
    setError(null);
  }, [target]);

  const runSearch = async () => {
    const q = query.trim();
    if (q.length < 2) return;
    setSearching(true);
    setError(null);
    try {
      setHits(await searchLocalFiles(q));
    } catch (e) {
      setError(err(e));
    } finally {
      setSearching(false);
    }
  };

  const link = async (path: string) => {
    if (!target) return;
    setLinking(true);
    setError(null);
    try {
      const track = await linkLocalFile(target.id, path);
      onLinked(track);
      onClose();
    } catch (e) {
      // 400 tipico: file inesistente o estensione non audio.
      setError(err(e));
    } finally {
      setLinking(false);
    }
  };

  return (
    <Modal open={target !== null} onClose={onClose} title="Collega file locale" size="lg">
      {target && (
        <div className="space-y-4 p-4">
          <p className="text-sm text-muted">{target.artist ?? "?"} — {target.title ?? "?"}</p>
          {error && <Alert tone="danger">⚠ {error}</Alert>}

          <div className="flex items-center gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") runSearch();
              }}
              placeholder="Cerca per nome file…"
            />
            <Button variant="outline" onClick={runSearch}
              disabled={searching || query.trim().length < 2}>
              <Search size={14} /> Cerca
            </Button>
          </div>
          {searching && <Loading label="Cerco sul disco…" />}
          {hits && hits.length === 0 && !searching && (
            <p className="text-sm text-faint">
              Nessun file trovato: prova con meno parole o incolla il percorso qui sotto.
            </p>
          )}
          {hits && hits.length > 0 && (
            <ul className="max-h-64 divide-y divide-border overflow-y-auto border border-border">
              {hits.map((h) => (
                <li key={h.path} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-xs">{h.name}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      <FolderOpen size={11} className="mr-1 inline" />
                      {SOURCE_LABEL[h.source] ?? h.source}
                      {h.format ? ` · ${h.format.toUpperCase()}` : ""}
                      {h.size ? ` · ${fmtSize(h.size)}` : ""}
                    </div>
                  </div>
                  <Button size="sm" onClick={() => link(h.path)} disabled={linking}>
                    {linking ? <Spinner /> : <Link2 size={13} />} Collega
                  </Button>
                </li>
              ))}
            </ul>
          )}

          <div className="border-t border-border pt-3">
            <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">
              Percorso esatto
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
                placeholder="/percorso/assoluto/del/file.mp3"
              />
              <Button variant="outline" onClick={() => link(manualPath.trim())}
                disabled={linking || !manualPath.trim()}>
                <Link2 size={14} /> Collega
              </Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
```

- [ ] **Step 2: Verificare lint**

Run: `cd frontend && npm run lint`
Expected: nessun errore.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/link-local-file-modal.tsx
git commit -m "feat: modal Collega file locale (ricerca su disco + percorso esatto)"
```

---

### Task 7: Pagina archivio `/downloads/issues`

**Files:**
- Create: `frontend/app/downloads/issues/page.tsx`

**Interfaces:**
- Consumes: `downloadPending`, `ignoreDownload`, `retryPending`, `trackLabel`, tipo `Track` da `@/lib/api`; `DownloadReviewModal`/`ReviewTarget` (Task 5); `LinkLocalFileModal`/`LinkTarget` (Task 6); `useJobs` da `@/components/jobs-provider`.
- Produces: rotta `/downloads/issues` (linkata dal riassunto del Task 5).

- [ ] **Step 1: Creare la pagina**

Creare `frontend/app/downloads/issues/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Download as DownloadIcon, EyeOff, Link2, Search } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, Loading } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import { DownloadReviewModal, type ReviewTarget } from "@/components/download-review-modal";
import { LinkLocalFileModal, type LinkTarget } from "@/components/link-local-file-modal";
import { downloadPending, ignoreDownload, retryPending, trackLabel, type Track } from "@/lib/api";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type Outcome = "not_found" | "needs_review" | "failed";
type Filter = "all" | Outcome;

const OUTCOME_TONE: Record<Outcome, "warning" | "danger" | "neutral"> = {
  not_found: "neutral",
  needs_review: "warning",
  failed: "danger",
};

const OUTCOME_LABEL: Record<Outcome, string> = {
  not_found: "non trovata",
  needs_review: "da rivedere",
  failed: "fallita",
};

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Tutti" },
  { key: "not_found", label: "Non trovate" },
  { key: "needs_review", label: "Da rivedere" },
  { key: "failed", label: "Fallite" },
];

export default function DownloadIssuesPage() {
  const { download: status, refresh } = useJobs();
  const [pending, setPending] = useState<Track[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [linking, setLinking] = useState<LinkTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refreshPending = useCallback(() => {
    downloadPending()
      .then((rows) => alive.current && setPending(rows))
      .catch((e) => alive.current && setError(err(e)));
  }, []);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  // Gli esiti cambiano man mano che il job li produce.
  useEffect(() => { refreshPending(); }, [refreshPending, status?.status, status?.processed]);

  const ignore = async (t: Track) => {
    if (!window.confirm(`Ignorare «${trackLabel(t)}»? Uscirà da questo archivio.`)) return;
    setError(null);
    try {
      await ignoreDownload(t.id);
      refreshPending();
    } catch (e) {
      setError(err(e));
    }
  };

  const retryAll = async () => {
    setError(null);
    try {
      await retryPending();
      refresh();
    } catch (e) {
      setError(err(e));
    }
  };

  const running = status?.status === "running";
  const available = status?.available ?? true;
  const rows = (pending ?? []).filter(
    (t) => filter === "all" || t.last_download_outcome === filter);
  const count = (k: Filter) => k === "all"
    ? (pending?.length ?? 0)
    : (pending ?? []).filter((t) => t.last_download_outcome === k).length;

  return (
    <PageLayout title="Download da sistemare" meta={pending?.length || undefined}>
      <Link href="/downloads" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Download
      </Link>

      <div className="space-y-3">
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <Button key={f.key} size="sm"
                variant={filter === f.key ? "primary" : "outline"}
                onClick={() => setFilter(f.key)}>
                {f.label} ({count(f.key)})
              </Button>
            ))}
          </div>
          <Button size="sm" variant="outline" onClick={retryAll} disabled={running || !available}>
            <DownloadIcon size={13} /> Riprova tutte
          </Button>
        </div>

        {pending === null && <Loading />}
        {pending !== null && rows.length === 0 && (
          <EmptyState icon={<DownloadIcon size={28} />} title="Niente da sistemare">
            Le tracce con download non trovato, da rivedere o fallito compariranno qui.
          </EmptyState>
        )}
        {rows.length > 0 && (
          <Card>
            <ul className="divide-y divide-border text-sm">
              {rows.map((t) => (
                <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
                  <div className="min-w-0 flex-1">
                    <Link href={`/tracks/${t.id}`} className="truncate hover:text-fg-strong">
                      {trackLabel(t)}
                    </Link>
                    {t.last_download_reason && (
                      <div className="text-xs text-muted">{t.last_download_reason}</div>
                    )}
                  </div>
                  <span className="flex shrink-0 flex-wrap items-center gap-2">
                    <Badge tone={OUTCOME_TONE[t.last_download_outcome as Outcome] ?? "neutral"}>
                      {OUTCOME_LABEL[t.last_download_outcome as Outcome] ?? t.last_download_outcome}
                    </Badge>
                    <Button size="sm" variant="outline"
                      onClick={() => setReview({ track_id: t.id, artist: t.artist, title: t.title })}>
                      <Search size={13} /> Scegli file
                    </Button>
                    <Button size="sm" variant="outline"
                      onClick={() => setLinking({ id: t.id, artist: t.artist, title: t.title })}>
                      <Link2 size={13} /> Collega file
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => ignore(t)}>
                      <EyeOff size={13} /> Ignora
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      <DownloadReviewModal
        target={review}
        onClose={() => setReview(null)}
        onPicked={() => {
          refresh();
          setReview(null);
          refreshPending();
        }}
      />
      <LinkLocalFileModal
        target={linking}
        onClose={() => setLinking(null)}
        onLinked={() => refreshPending()}
      />
    </PageLayout>
  );
}
```

- [ ] **Step 2: Verificare lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore; nella build compare la rotta `/downloads/issues`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/downloads/issues/page.tsx
git commit -m "feat: pagina archivio download da sistemare con filtri e azioni"
```

---

### Task 8: "Collega file" nel dettaglio traccia

**Files:**
- Modify: `frontend/app/tracks/[id]/page.tsx`

**Interfaces:**
- Consumes: `LinkLocalFileModal` (Task 6); `CardHeader` accetta la prop `action` (`frontend/components/ui.tsx:17`).
- Produces: pulsante "Collega file" / "Sostituisci file" nella card Disco; al successo la traccia si ricarica via `setTrack`.

- [ ] **Step 1: Modificare la pagina**

In `frontend/app/tracks/[id]/page.tsx`:

1. Aggiungere `Link2` all'import lucide (riga 5):

```tsx
import { ArrowLeft, ExternalLink, Link2, Music4, ArrowRightLeft, Pencil, Sparkles } from "lucide-react";
```

2. Aggiungere l'import del modal dopo quello di `TrackEditModal` (riga 9):

```tsx
import { LinkLocalFileModal } from "@/components/link-local-file-modal";
```

3. Aggiungere lo stato dopo `const [enrichErr, setEnrichErr] = ...` (riga 37):

```tsx
const [linking, setLinking] = useState(false);
```

4. Sostituire `<CardHeader title="Disco" />` (riga 118) con:

```tsx
<CardHeader
  title="Disco"
  action={
    <Button size="sm" variant="outline" onClick={() => setLinking(true)}>
      <Link2 size={14} /> {track.has_local_file ? "Sostituisci file" : "Collega file"}
    </Button>
  }
/>
```

5. Aggiungere il modal accanto a `<TrackEditModal ... />` in fondo (riga ~154):

```tsx
<LinkLocalFileModal
  target={linking ? { id: track.id, artist: track.artist, title: track.title } : null}
  onClose={() => setLinking(false)}
  onLinked={(t) => setTrack(t)}
/>
```

- [ ] **Step 2: Verificare lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/tracks/[id]/page.tsx"
git commit -m "feat: Collega file locale dal dettaglio traccia"
```

---

### Task 9: Documentazione + verifica finale

**Files:**
- Modify: `docs/API.md` (sezioni download e tracks: seguire il formato gia' usato dal file)
- Modify: `PROGRESS.md` (nuova voce in cima al diario, stesso formato delle voci esistenti)

**Interfaces:**
- Consumes: gli endpoint dei Task 1–3.
- Produces: documentazione allineata (regola del progetto: `docs/API.md` e' la fonte di verita' degli endpoint).

- [ ] **Step 1: Aggiornare docs/API.md**

Aprire `docs/API.md`, individuare le sezioni degli endpoint download e tracks e aggiungere, nello stesso formato delle voci esistenti, le tre rotte:

- `DELETE /api/downloads/pending/{track_id}` — Ignora una "da sistemare": azzera `last_download_outcome`/`last_download_reason`; 404 se la traccia non esiste. Risposta: Track aggiornata.
- `GET /api/files/search?q=...` — Cerca file audio per nome (match AND dei termini, case-insensitive) in `LIBRARY_ROOT` e `SLSKD_DOWNLOAD_DIR`; max 50 risultati; query sotto 2 caratteri → lista vuota. Risposta: `[{path, name, format, size, source}]` con `source` = `library` | `downloads`.
- `POST /api/tracks/{track_id}/link-file` body `{"path": "..."}` — Collega manualmente un file su disco alla traccia: valida esistenza ed estensione audio, imposta possesso (`has_local_file`, `local_path`, formato, bitrate, audio-hash best-effort) e azzera l'esito download. 400 su path invalido, 404 su traccia inesistente. Risposta: Track aggiornata.

- [ ] **Step 2: Aggiornare PROGRESS.md**

Aggiungere in cima al diario (stesso formato delle voci esistenti, data 2026-07-05) una voce che riassume: pagina archivio `/downloads/issues` (filtri per esito, Scegli file / Collega file / Ignora, Riprova tutte), "Da sistemare" ridotta a riassunto con link, collegamento manuale file locale dal dettaglio traccia e dall'archivio (ricerca su disco + percorso esatto), tre endpoint nuovi.

- [ ] **Step 3: Verifica finale completa**

Run:

```bash
cd backend && source .venv/bin/activate && python -m pytest tests
cd ../frontend && npm run lint && npm run build
```

Expected: tutta la suite backend verde; lint e build senza errori.

- [ ] **Step 4: Commit**

```bash
git add docs/API.md PROGRESS.md
git commit -m "docs: API e diario per archivio download e link-file"
```
