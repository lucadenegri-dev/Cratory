# Download Unificato — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unificare la sezione Download in un'unica pagina di lavoro (acquisisci → monitora → sistema), rimuovendo `/downloads/issues`, e rendere la revisione dei `needs_review`-per-durata capace di mostrare il file già scaricato con azioni Tieni / Scarta / Sostituisci.

**Architecture:** Backend FastAPI/SQLAlchemy: si persiste il path del file dubbio (`last_download_path`) e si aggiungono tre endpoint sotto `/api/downloads` (review detail, keep, discard) che riusano `attach_local_file`. Frontend Next.js: la pagina `/downloads` diventa una superficie unica con barra acquisizione, striscia job effimera e work-list persistito azionabile inline; il modal di revisione confronta atteso vs scaricato.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy (SQLite, migrazioni idempotenti in `db.py`, no Alembic) + pytest; Next.js 16 App Router + React + Tailwind (design system in `frontend/components/ui.tsx`).

## Global Constraints

- **Design system invariato** (DESIGN.md): monocromo, un solo rosso (`danger`) per errori/distruzione, geometria squadrata (`rounded: 0`), filetti 1px, monospace, `.tnum` sui conteggi. Nessun colore nuovo.
- **Rekordbox è fonte di BPM/key; DjOrganizer scrive i tag.** Questo lavoro non tocca metadati testuali né tag su disco. `attach_local_file` marca solo il possesso.
- **Commit style:** niente `Co-Authored-By`. Messaggi in italiano, imperativi, coerenti con la history.
- **Next.js 16:** leggere `frontend/CLAUDE.md` prima di toccare pagine/routing.
- **Backend test runner:** `cd backend && source .venv/bin/activate && python -m pytest`. **Frontend gate:** `cd frontend && npm run lint && npm run build` (nessun test runner FE nel repo) + verifica nel browser con i preview tool.
- **slskd inbox** = `settings.slskd_download_dir` (`SLSKD_DOWNLOAD_DIR`). I file dubbi restano lì finché keep/discard.

---

### Task 1: Backend — persistere `last_download_path`

Quando un download va in `needs_review` per durata incoerente, il file è già nell'inbox ma il suo path non viene salvato (è una variabile locale). Lo persistiamo sulla `Track` così la revisione potrà offrire "Tieni comunque".

**Files:**
- Modify: `backend/app/models.py:60-61` (aggiungere colonna dopo `last_download_reason`)
- Modify: `backend/app/db.py:71-73` (additions `tracks`)
- Modify: `backend/app/schemas.py:44-45` (TrackOut)
- Modify: `backend/app/serializers.py:49-50` (track_out)
- Modify: `backend/app/services/soulseek_download_job.py` (`_attempt_download`, `_process_item`, `_run`)
- Test: `backend/tests/test_soulseek_download_job.py`

**Interfaces:**
- Produces: `Track.last_download_path: str | None`; `_attempt_download(...) -> tuple[str, str | None, str | None]` (outcome, reason, path); `_process_item(...) -> tuple[str, str | None, str | None]`; `TrackOut.last_download_path: str | None`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_soulseek_download_job.py`, dentro `test_durata_incoerente_va_in_needs_review` aggiungere, dopo `assert st["downloaded"] == 0` (riga ~187), l'asserzione sul path; e in `test_durata_coerente_viene_collegata` asserire che è None. Sostituire le due funzioni con:

```python
def test_durata_incoerente_va_in_needs_review(patch_job):
    from pathlib import Path

    TestSession, fake = patch_job
    fake._filename = "bob\\Da Funk.wav"
    _write_wav(Path(job.settings.slskd_download_dir) / "Da Funk.wav", secs=2)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s9", source_type="spotify",
              title="Da Funk", artist="Daft Punk", duration_seconds=300)
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    job._run([(track_id, None)], None)
    st = job.job_state()
    assert st["needs_review"] == 1
    assert st["downloaded"] == 0
    assert "durata" in (st["items"][0]["reason"] or "")
    db = TestSession()
    t2 = db.get(Track, track_id)
    assert t2.has_local_file is False
    # Il path del file dubbio è persistito per la revisione "Tieni comunque".
    assert t2.last_download_path is not None
    assert t2.last_download_path.endswith("Da Funk.wav")
    db.close()


def test_durata_coerente_viene_collegata(patch_job):
    from pathlib import Path

    TestSession, fake = patch_job
    fake._filename = "bob\\Da Funk.wav"
    _write_wav(Path(job.settings.slskd_download_dir) / "Da Funk.wav", secs=2)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="s10", source_type="spotify",
              title="Da Funk", artist="Daft Punk", duration_seconds=2)
    db.add(t)
    db.commit()
    track_id = t.id
    db.close()

    job._run([(track_id, None)], None)
    st = job.job_state()
    assert st["downloaded"] == 1
    db = TestSession()
    t2 = db.get(Track, track_id)
    assert t2.has_local_file is True
    assert t2.last_download_path is None  # nessun residuo dopo il collegamento
    db.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_download_job.py::test_durata_incoerente_va_in_needs_review -v`
Expected: FAIL con `AttributeError: 'Track' object has no attribute 'last_download_path'`.

- [ ] **Step 3: Add the model column**

In `backend/app/models.py`, subito dopo la riga 61 (`last_download_reason`), aggiungere:

```python
    # Path del file dubbio nell'inbox slskd quando l'esito è needs_review-per-durata:
    # alimenta la revisione "Tieni comunque / Scarta". None se non c'è file da rivedere.
    last_download_path: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 4: Add the idempotent migration**

In `backend/app/db.py`, nel dict `additions["tracks"]`, subito dopo `"last_download_reason": "VARCHAR",` (riga 73) aggiungere:

```python
            "last_download_path": "TEXT",
```

- [ ] **Step 5: Expose it in the schema and serializer**

In `backend/app/schemas.py`, in `TrackOut` dopo la riga 45 (`last_download_reason`):

```python
    last_download_path: str | None = None
```

In `backend/app/serializers.py`, in `track_out(...)` dopo la riga 50 (`last_download_reason=...`):

```python
        last_download_path=track.last_download_path,
```

- [ ] **Step 6: Thread the path through the job**

In `backend/app/services/soulseek_download_job.py`:

`_attempt_download` (righe 115-134) — cambiare firma e return in tripla:

```python
def _attempt_download(db, client, download_dir, track, file: SlskdFile,
                      expected_duration: int | None = None) -> tuple[str, str | None, str | None]:
    """Scarica un candidato e lo collega a una Track. Ritorna (esito, motivo, path_dubbio).

    Verifica post-download: se la durata reale del file non e' coerente con quella
    attesa (>20s di scarto) e' quasi certamente la versione sbagliata → il file
    resta in inbox per revisione, il suo path viene restituito e la Track NON viene
    marcata posseduta.
    """
    path = _download_candidate(client, download_dir, file)
    if not path:
        return "failed", None, None
    real = read_tags(path).get("duration_seconds")
    if expected_duration and real and abs(real - expected_duration) > 20:
        return "needs_review", (
            f"durata non corrisponde (attesa {expected_duration}s, file {real}s)"
        ), path
    quality = read_audio_quality(path)
    attach_local_file(db, track, path=path, fmt=quality["format"],
                      bitrate=quality["bitrate"])
    return "downloaded", None, None
```

`_process_item` (righe 177-203) — propagare la tripla su tutti i return:

```python
def _process_item(db, client, download_dir, track,
                  chosen: SlskdFile | None) -> tuple[str, str | None, str | None]:
    expected = track.duration_seconds
    # Discovery/singola: candidato gia' scelto dall'utente, un solo tentativo.
    if chosen is not None:
        return _attempt_download(db, client, download_dir, track, chosen, expected)

    # Cascata di varianti di query (la letterale spesso esclude file validi).
    ranked = search_candidates(client, artist=track.artist or "",
                               title=track.title or "", expected_duration=expected)
    if not ranked:
        return "not_found", None, None
    if ranked[0].confidence < AUTO_PICK_MIN_CONFIDENCE:
        return "needs_review", "confidenza sotto soglia per l'auto-pick", None
    # Fallback: prova i migliori candidati, un utente diverso alla volta, finche' uno riesce.
    tried: set[str] = set()
    for cand in ranked:
        if len(tried) >= MAX_ATTEMPTS:
            break
        if cand.file.username in tried:
            continue
        tried.add(cand.file.username)
        outcome, reason, path = _attempt_download(db, client, download_dir, track,
                                                  cand.file, expected)
        if outcome != "failed":
            return outcome, reason, path
    return "failed", None, None
```

`_run` (righe 206-255) — inizializzare `path` e persisterlo. Sostituire il blocco `track = None / reason = None` (righe 213-214) e la persistenza (righe 234-247):

```python
        for i, (track_id, chosen) in enumerate(items, start=1):
            track = None
            reason = None
            path = None
```

e nel ramo `else` (traccia reale) sostituire `outcome, reason = _process_item(...)` con `outcome, reason, path = _process_item(...)`:

```python
                    try:
                        outcome, reason, path = _process_item(db, client, download_dir, track, chosen)
```

e nella persistenza sulla traccia (righe 242-247):

```python
            if track is not None:
                # Persisti l'esito sulla traccia: la sezione "da sistemare"
                # deve sopravvivere a job e riavvii. path != None solo per un
                # needs_review-per-durata (file dubbio in inbox da rivedere).
                track.last_download_outcome = outcome
                track.last_download_reason = reason
                track.last_download_path = path
                db.commit()
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_download_job.py -v`
Expected: PASS (tutti, inclusi i due modificati).

- [ ] **Step 8: Run the full backend suite (no regressions)**

Run: `cd backend && source .venv/bin/activate && python -m pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/app/schemas.py backend/app/serializers.py backend/app/services/soulseek_download_job.py backend/tests/test_soulseek_download_job.py
git commit -m "feat(downloads): persisti last_download_path per la revisione dei needs_review"
```

---

### Task 2: Backend — review detail + keep + discard

Tre endpoint per la revisione del file dubbio. `review` legge i tag reali del file scaricato per il confronto atteso-vs-scaricato; `keep` lo aggancia alla traccia; `discard` lo elimina e sgancia la traccia dall'archivio.

**Files:**
- Create: `backend/app/services/download_review.py`
- Modify: `backend/app/routers/downloads.py` (nuovi endpoint + import)
- Test: `backend/tests/test_download_review.py`

**Interfaces:**
- Consumes: `Track.last_download_path` (Task 1); `attach_local_file(db, track, *, path, fmt, bitrate)`; `read_tags(path) -> dict`; `read_audio_quality(path) -> {"format","bitrate"}`; `get_track(db, id)`.
- Produces: service `review_detail(db, track) -> dict`, `keep_downloaded(db, track) -> Track`, `discard_downloaded(db, track) -> Track`; endpoint `GET /api/downloads/review/{track_id}`, `POST /api/downloads/keep-review`, `POST /api/downloads/discard-review`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_download_review.py`:

```python
"""Revisione dei needs_review-per-durata: review detail, keep, discard."""
import math
import struct
import wave

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


def _write_wav(path, *, secs=2, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * 440 * i / rate)))
            for i in range(int(rate * secs))
        ))


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _needs_review_track(db, tmp_path, *, secs=2, duration=300):
    f = tmp_path / "Da Funk.wav"
    _write_wav(f, secs=secs)
    t = Track(platform="spotify", spotify_id="r1", source_type="spotify",
              title="Da Funk", artist="Daft Punk", duration_seconds=duration,
              last_download_outcome="needs_review",
              last_download_reason="durata non corrisponde (attesa 300s, file 2s)",
              last_download_path=str(f))
    db.add(t)
    db.commit()
    return t


def test_review_detail_confronta_atteso_e_scaricato(client_db, tmp_path):
    client, db = client_db
    t = _needs_review_track(db, tmp_path)
    r = client.get(f"/api/downloads/review/{t.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["expected"]["duration_seconds"] == 300
    assert body["downloaded"]["name"] == "Da Funk.wav"
    assert body["downloaded"]["duration_seconds"] == 2


def test_review_detail_senza_file(client_db, tmp_path):
    # needs_review-per-confidenza: nessun file da rivedere.
    client, db = client_db
    t = Track(platform="spotify", spotify_id="r2", source_type="spotify",
              title="X", artist="Y", last_download_outcome="needs_review",
              last_download_reason="confidenza sotto soglia per l'auto-pick")
    db.add(t)
    db.commit()
    r = client.get(f"/api/downloads/review/{t.id}")
    assert r.status_code == 200
    assert r.json()["downloaded"] is None


def test_keep_aggancia_il_file_e_svuota_l_archivio(client_db, tmp_path):
    client, db = client_db
    t = _needs_review_track(db, tmp_path)
    r = client.post("/api/downloads/keep-review", json={"track_id": t.id})
    assert r.status_code == 200
    db.expire_all()
    t2 = db.get(Track, t.id)
    assert t2.has_local_file is True
    assert t2.last_download_outcome is None
    assert t2.last_download_path is None


def test_discard_elimina_il_file_e_sgancia(client_db, tmp_path):
    import os
    client, db = client_db
    t = _needs_review_track(db, tmp_path)
    path = t.last_download_path
    r = client.post("/api/downloads/discard-review", json={"track_id": t.id})
    assert r.status_code == 200
    assert not os.path.exists(path)  # file rimosso dall'inbox
    db.expire_all()
    t2 = db.get(Track, t.id)
    assert t2.has_local_file is not True
    assert t2.last_download_outcome is None


def test_keep_404_su_traccia_inesistente(client_db):
    client, _ = client_db
    assert client.post("/api/downloads/keep-review", json={"track_id": 9999}).status_code == 404


def test_keep_409_se_nessun_file_dubbio(client_db):
    client, db = client_db
    t = Track(platform="spotify", spotify_id="r3", source_type="spotify",
              title="X", artist="Y", last_download_outcome="needs_review")
    db.add(t)
    db.commit()
    assert client.post("/api/downloads/keep-review", json={"track_id": t.id}).status_code == 409
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_download_review.py -v`
Expected: FAIL con 404 su tutte le POST/GET (endpoint inesistenti).

- [ ] **Step 3: Write the service**

Create `backend/app/services/download_review.py`:

```python
"""Revisione di un download andato in needs_review-per-durata.

Il file dubbio è già nell'inbox slskd (path in Track.last_download_path). L'utente
può tenerlo (aggancio come possesso) o scartarlo (cancellazione + sgancio). La
lettura dei tag reali serve al confronto atteso-vs-scaricato in UI.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.integrations.local_files import read_audio_quality, read_tags
from app.models import Track
from app.services.acquisition import attach_local_file

logger = logging.getLogger(__name__)


def review_detail(db: Session, track: Track) -> dict:
    """Atteso (dalla Track) + file scaricato (tag reali dall'inbox), per il confronto."""
    downloaded = None
    path = track.last_download_path
    if path and Path(path).is_file():
        quality = read_audio_quality(path)
        downloaded = {
            "path": path,
            "name": Path(path).name,
            "format": quality.get("format"),
            "bitrate": quality.get("bitrate"),
            "duration_seconds": read_tags(path).get("duration_seconds"),
            "size": Path(path).stat().st_size,
        }
    return {
        "expected": {
            "artist": track.artist,
            "title": track.title,
            "duration_seconds": track.duration_seconds,
        },
        "downloaded": downloaded,
        "reason": track.last_download_reason,
    }


class NoReviewFileError(ValueError):
    """La traccia non ha un file dubbio da tenere/scartare."""


def keep_downloaded(db: Session, track: Track) -> Track:
    """Tieni il file dubbio: aggancialo come possesso e svuota l'esito."""
    path = track.last_download_path
    if not path or not Path(path).is_file():
        raise NoReviewFileError("Nessun file dubbio da tenere.")
    quality = read_audio_quality(path)
    track = attach_local_file(db, track, path=path, fmt=quality["format"],
                              bitrate=quality["bitrate"])
    track.last_download_outcome = None
    track.last_download_reason = None
    track.last_download_path = None
    db.commit()
    db.refresh(track)
    return track


def discard_downloaded(db: Session, track: Track) -> Track:
    """Scarta il file dubbio: cancellalo dall'inbox e sgancia la traccia dall'archivio."""
    path = track.last_download_path
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as exc:  # file lockato / permessi: non bloccare lo sgancio
            logger.warning("Rimozione file dubbio fallita per %s: %s", path, exc)
    track.last_download_outcome = None
    track.last_download_reason = None
    track.last_download_path = None
    db.commit()
    db.refresh(track)
    return track
```

- [ ] **Step 4: Wire the endpoints**

In `backend/app/routers/downloads.py`, aggiungere agli import (dopo la riga 15):

```python
from app.services.download_review import (
    NoReviewFileError, discard_downloaded, keep_downloaded, review_detail,
)
```

Aggiungere un modello di input dopo `ManualDownloadIn` (riga 50):

```python
class ReviewActionIn(BaseModel):
    track_id: int
```

Aggiungere gli endpoint in fondo al file (dopo `download_manual`, riga 165):

```python
@router.get("/review/{track_id}")
def review(track_id: int, db: Session = Depends(get_db)):
    """Confronto atteso-vs-scaricato per un needs_review-per-durata."""
    track = get_track(db, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata.")
    return review_detail(db, track)


@router.post("/keep-review", response_model=TrackOut)
def keep_review(req: ReviewActionIn, db: Session = Depends(get_db)):
    """Tieni il file dubbio già scaricato: lo aggancia e svuota l'esito."""
    track = get_track(db, req.track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata.")
    try:
        track = keep_downloaded(db, track)
    except NoReviewFileError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return track_out(track)


@router.post("/discard-review", response_model=TrackOut)
def discard_review(req: ReviewActionIn, db: Session = Depends(get_db)):
    """Scarta il file dubbio: lo elimina dall'inbox e sgancia la traccia."""
    track = get_track(db, req.track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Traccia non trovata.")
    return track_out(discard_downloaded(db, track))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_download_review.py -v`
Expected: PASS (tutti e 6).

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && source .venv/bin/activate && python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/download_review.py backend/app/routers/downloads.py backend/tests/test_download_review.py
git commit -m "feat(downloads): endpoint review/keep/discard per il file dubbio"
```

---

### Task 3: Frontend — API client per la revisione

**Files:**
- Modify: `frontend/lib/api.ts` (Track type + nuove funzioni, dopo la riga 734)

**Interfaces:**
- Consumes: endpoint Task 2; `Track` type (riga ~20-33), `apiGet`/`apiPost`.
- Produces: `Track.last_download_path`; type `DownloadReview`; `downloadReview(trackId)`, `keepReview(trackId)`, `discardReview(trackId)`.

- [ ] **Step 1: Add `last_download_path` to the Track type**

In `frontend/lib/api.ts`, nella interface `Track`, dopo la riga 32 (`last_download_reason: string | null;`):

```typescript
  last_download_path: string | null;
```

- [ ] **Step 2: Add the review types and client functions**

In `frontend/lib/api.ts`, dopo `linkLocalFile` (riga 734), aggiungere:

```typescript
// --- Revisione file dubbio (needs_review-per-durata) --------------------------

export type DownloadReview = {
  expected: { artist: string | null; title: string | null; duration_seconds: number | null };
  downloaded: {
    path: string; name: string; format: string | null; bitrate: number | null;
    duration_seconds: number | null; size: number | null;
  } | null;
  reason: string | null;
};

/** Atteso vs file già scaricato per una traccia da rivedere. */
export function downloadReview(trackId: number) {
  return apiGet<DownloadReview>(`/api/downloads/review/${trackId}`);
}

/** Tieni il file dubbio: lo aggancia come possesso e svuota l'esito. */
export function keepReview(trackId: number) {
  return apiPost<Track>("/api/downloads/keep-review", { track_id: trackId });
}

/** Scarta il file dubbio: lo elimina dall'inbox e sgancia la traccia. */
export function discardReview(trackId: number) {
  return apiPost<Track>("/api/downloads/discard-review", { track_id: trackId });
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run lint`
Expected: nessun errore nuovo su `lib/api.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(downloads): client API review/keep/discard"
```

---

### Task 4: Frontend — modal di revisione con confronto atteso-vs-scaricato

Estende `DownloadReviewModal`: quando esiste un file dubbio, mostra in cima "atteso vs scaricato" con **Tieni comunque / Scarta**; sotto resta la lista candidati per **Sostituisci** (comportamento attuale). Quando non c'è file (needs_review-confidenza / not_found), il modal resta la sola lista candidati.

**Files:**
- Modify: `frontend/components/download-review-modal.tsx`

**Interfaces:**
- Consumes: `downloadReview`, `keepReview`, `discardReview`, `downloadCandidates`, `downloadTrack`, `fmtDuration` (Task 3 + esistenti).
- Produces: `DownloadReviewModal` con `onPicked` invariato (chiamato anche dopo keep/discard).

- [ ] **Step 1: Rewrite the modal**

Sostituire l'intero `frontend/components/download-review-modal.tsx` con:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Check, Download as DownloadIcon, Trash2 } from "lucide-react";
import { Alert, Button, Loading, Modal, Spinner } from "@/components/ui";
import {
  discardReview, downloadCandidates, downloadReview, downloadTrack, fmtDuration,
  keepReview, type DownloadCandidate, type DownloadReview,
} from "@/lib/api";

export type ReviewTarget = { track_id: number; artist: string | null; title: string | null };

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

function fmtSize(bytes: number | null): string {
  if (!bytes) return "";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Wrapper: monta il dialog solo con un target e lo rigenera per ogni traccia. */
export function DownloadReviewModal({ target, onClose, onPicked }: {
  target: ReviewTarget | null;
  onClose: () => void;
  onPicked: () => void;
}) {
  if (!target) return null;
  return <ReviewDialog key={target.track_id} target={target} onClose={onClose} onPicked={onPicked} />;
}

/** Modal di revisione: file dubbio (Tieni/Scarta) + candidati Soulseek (Sostituisci). */
function ReviewDialog({ target, onClose, onPicked }: {
  target: ReviewTarget;
  onClose: () => void;
  onPicked: () => void;
}) {
  const [review, setReview] = useState<DownloadReview | null>(null);
  const [candidates, setCandidates] = useState<DownloadCandidate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const rev = await downloadReview(target.track_id);
        if (!alive) return;
        setReview(rev);
        const found = await downloadCandidates(
          rev.expected.artist ?? target.artist ?? "",
          rev.expected.title ?? target.title ?? "",
          rev.expected.duration_seconds);
        if (!alive) return;
        setCandidates(found);
      } catch (e) {
        if (!alive) return;
        setError(err(e));
        setCandidates([]);
      }
    })();
    return () => { alive = false; };
  }, [target]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onPicked();
    } catch (e) {
      // 409 tipico: "Un download e' gia' in corso" — riprova a job finito.
      setError(err(e));
    } finally {
      setBusy(false);
    }
  };

  const exp = review?.expected;
  const dl = review?.downloaded;
  const expDur = exp?.duration_seconds ?? null;
  const dlDur = dl?.duration_seconds ?? null;
  const delta = expDur != null && dlDur != null ? dlDur - expDur : null;

  return (
    <Modal open onClose={onClose} title="Rivedi il download" size="lg">
      <div className="space-y-4 p-4">
        <p className="text-sm text-muted">
          {exp?.artist ?? target.artist ?? "?"} — {exp?.title ?? target.title ?? "?"}
          {expDur != null && (
            <span className="ml-2 text-xs text-faint">durata attesa {fmtDuration(expDur)}</span>
          )}
        </p>
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {dl && (
          <div className="border border-border-strong p-3">
            <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">
              File già scaricato
            </div>
            <div className="truncate font-mono text-xs">{dl.name}</div>
            <div className="mt-0.5 text-xs text-muted">
              {(dl.format ?? "?").toUpperCase()}
              {dl.bitrate ? ` · ${dl.bitrate} kbps` : ""}
              {dl.duration_seconds != null ? ` · ${fmtDuration(dl.duration_seconds)}` : ""}
              {delta != null && (
                <span className="ml-1 text-fg-strong">
                  ({delta > 0 ? "+" : ""}{delta}s vs atteso)
                </span>
              )}
              {dl.size ? ` · ${fmtSize(dl.size)}` : ""}
            </div>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => run(() => keepReview(target.track_id))} disabled={busy}>
                {busy ? <Spinner /> : <Check size={13} />} Tieni comunque
              </Button>
              <Button size="sm" variant="danger"
                onClick={() => run(() => discardReview(target.track_id))} disabled={busy}>
                <Trash2 size={13} /> Scarta
              </Button>
            </div>
          </div>
        )}

        <div>
          <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">
            {dl ? "Oppure sostituisci con" : "Scegli un file"}
          </div>
          {candidates === null && <Loading label="Cerco i candidati su Soulseek…" />}
          {candidates?.length === 0 && (
            <p className="py-6 text-center text-sm text-muted">
              Nessun candidato in questo momento: riprova più tardi (dipende da chi è online).
            </p>
          )}
          {candidates && candidates.length > 0 && (
            <ul className="max-h-72 divide-y divide-border overflow-y-auto border border-border">
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
                  <Button size="sm" variant="outline"
                    onClick={() => run(() => downloadTrack(target.track_id, c))} disabled={busy}>
                    {busy ? <Spinner /> : <DownloadIcon size={13} />} Scarica
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  );
}
```

- [ ] **Step 2: Lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: build OK. Se `variant="danger"` non esiste su `Button`, verificare le varianti in `frontend/components/ui.tsx:48` e usare quella corretta (`danger` è documentata in DESIGN.md §5).

- [ ] **Step 3: Browser-verify**

Con backend + frontend attivi (preview tool), aprire `/downloads`, aprire il modal su una traccia da rivedere. Verificare che il blocco "File già scaricato" appaia con il delta durata e i due bottoni, e che la lista candidati sia sotto. (Questa verifica dipende da avere una traccia `needs_review` con `last_download_path`; in assenza di slskd si può testare solo il ramo senza file.)

- [ ] **Step 4: Commit**

```bash
git add frontend/components/download-review-modal.tsx
git commit -m "feat(downloads): revisione con confronto atteso-vs-scaricato e Tieni/Scarta"
```

---

### Task 5: Frontend — pagina Download unificata + rimozione /issues

Una sola pagina: barra acquisizione (primaria), striscia job effimera (`EqMeter`), work-list persistito azionabile inline (chip-filtro + azioni per riga), blocco ricerca manuale in evidenza, empty/offline state. Rimuove `/downloads/issues` e assorbe `LinkLocalFileModal`.

**Files:**
- Modify (rewrite): `frontend/app/downloads/page.tsx`
- Delete: `frontend/app/downloads/issues/page.tsx` (e la cartella `issues` se resta vuota)

**Interfaces:**
- Consumes: `useJobs()` (`download`, `refresh`), `DownloadReviewModal`, `LinkLocalFileModal`, `EqMeter`, `downloadPending`, `retryPending`, `ignoreDownload`, `startPlaylistDownload`, `listImportedPlaylists`, `searchDownloads`, `downloadManual`, `trackLabel`, `Track.last_download_path`.

- [ ] **Step 1: Verify no other references to /downloads/issues**

Run: `cd frontend && grep -rn "downloads/issues" app components lib`
Expected: solo la definizione della pagina (`app/downloads/issues/page.tsx`) e il link in `app/downloads/page.tsx` (che sparisce col rewrite). Se compaiono altri link, annotarli e rimuoverli in questo task.

- [ ] **Step 2: Rewrite the page**

Sostituire l'intero `frontend/app/downloads/page.tsx` con:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download as DownloadIcon, EyeOff, Link2, Search } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, EqMeter, Input, Loading, Select } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import { DownloadReviewModal, type ReviewTarget } from "@/components/download-review-modal";
import { LinkLocalFileModal, type LinkTarget } from "@/components/link-local-file-modal";
import {
  downloadManual, downloadPending, ignoreDownload, listImportedPlaylists,
  retryPending, searchDownloads, startPlaylistDownload, trackLabel,
  type DownloadCandidate, type Playlist, type Track,
} from "@/lib/api";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type Outcome = "not_found" | "needs_review" | "failed";
type Filter = "all" | Outcome;

const OUTCOME_LABEL: Record<Outcome, string> = {
  not_found: "non trovata",
  needs_review: "da rivedere",
  failed: "fallita",
};
const OUTCOME_TONE: Record<Outcome, "warning" | "danger" | "neutral"> = {
  not_found: "neutral",
  needs_review: "warning",
  failed: "danger",
};
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Tutte" },
  { key: "needs_review", label: "Da rivedere" },
  { key: "not_found", label: "Non trovate" },
  { key: "failed", label: "Fallite" },
];

export default function DownloadsPage() {
  // Un solo poller (JobsProvider) per lo stato job; il work-list è persistito.
  const { download: status, refresh } = useJobs();
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selected, setSelected] = useState("");
  const [pending, setPending] = useState<Track[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DownloadCandidate[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [linking, setLinking] = useState<LinkTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refreshPending = useCallback(() => {
    downloadPending()
      .then((rows) => alive.current && setPending(rows))
      .catch(() => alive.current && setPending([]));
  }, []);

  useEffect(() => {
    alive.current = true;
    listImportedPlaylists().then((p) => alive.current && setPlaylists(p)).catch(() => undefined);
    return () => { alive.current = false; };
  }, []);

  // Il work-list cambia man mano che il job produce esiti.
  useEffect(() => { refreshPending(); }, [refreshPending, status?.status, status?.processed]);

  const available = status?.available ?? true;
  const running = status?.status === "running";
  const rows = (pending ?? []).filter((t) => filter === "all" || t.last_download_outcome === filter);
  const count = (k: Filter) => k === "all"
    ? (pending?.length ?? 0)
    : (pending ?? []).filter((t) => t.last_download_outcome === k).length;

  const start = async () => {
    if (!selected) return;
    setError(null);
    try { await startPlaylistDownload(Number(selected)); refresh(); }
    catch (e) { setError(err(e)); }
  };
  const retryAll = async () => {
    setError(null);
    try { await retryPending(); refresh(); }
    catch (e) { setError(err(e)); }
  };
  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true); setError(null); setResults(null);
    try { setResults(await searchDownloads(q)); }
    catch (e) { setError(err(e)); }
    finally { setSearching(false); }
  };
  const grab = async (c: DownloadCandidate) => {
    setError(null);
    try { await downloadManual(c); refresh(); }
    catch (e) { setError(err(e)); }
  };
  const ignore = async (t: Track) => {
    if (!window.confirm(`Ignorare «${trackLabel(t)}»? Uscirà da questo elenco.`)) return;
    setError(null);
    try { await ignoreDownload(t.id); refreshPending(); }
    catch (e) { setError(err(e)); }
  };

  return (
    <PageLayout title="Download" meta={pending?.length || status?.total || undefined}>
      <div className="space-y-6">
        {!available && (
          <Alert tone="info">
            slskd non e&apos; configurato. Imposta SLSKD_URL, SLSKD_API_KEY e
            SLSKD_DOWNLOAD_DIR in backend/.env per abilitare i download.
          </Alert>
        )}
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {/* 1. Acquisizione (azione primaria) */}
        <section>
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">Acquisizione</div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={selected} onChange={(e) => setSelected(e.target.value)} disabled={!available || running}>
              <option value="">Scegli una playlist…</option>
              {playlists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Button onClick={start} disabled={!available || running || !selected}>
              <DownloadIcon size={14} /> Scarica playlist
            </Button>
          </div>
          {status && status.total > 0 && (
            <div className="mt-3 border border-border p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                <span className="tnum">{status.processed}/{status.total}</span>
                {status.current_label && <span className="truncate">· {status.current_label}</span>}
                <span className="tnum ml-auto">{status.downloaded} scaricate · {status.needs_review + status.not_found + status.failed} da sistemare</span>
              </div>
              <EqMeter value={running ? status.processed / Math.max(status.total, 1) : null} />
            </div>
          )}
        </section>

        {/* 2. Work-list persistito (il cuore) */}
        <section>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filtra per esito">
              {FILTERS.map((f) => (
                <Button key={f.key} size="sm" role="tab" aria-selected={filter === f.key}
                  variant={filter === f.key ? "primary" : "outline"} onClick={() => setFilter(f.key)}>
                  {f.label} ({count(f.key)})
                </Button>
              ))}
            </div>
            {(pending?.length ?? 0) > 0 && (
              <Button size="sm" variant="outline" onClick={retryAll} disabled={running || !available}>
                <DownloadIcon size={13} /> Riprova tutte
              </Button>
            )}
          </div>

          {pending === null && <Loading />}
          {pending !== null && rows.length === 0 && (
            <EmptyState icon={<DownloadIcon size={28} />} title="Niente da sistemare">
              Scegli una playlist e avvia il download; le tracce non trovate, da rivedere o fallite compariranno qui.
            </EmptyState>
          )}
          {rows.length > 0 && (
            <Card>
              <ul className="divide-y divide-border text-sm">
                {rows.map((t) => {
                  const outcome = t.last_download_outcome as Outcome;
                  const hasFile = outcome === "needs_review" && !!t.last_download_path;
                  return (
                    <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
                      <div className="min-w-0 flex-1">
                        <a href={`/tracks/${t.id}`} className="truncate hover:text-fg-strong">{trackLabel(t)}</a>
                        {t.last_download_reason && <div className="text-xs text-muted">{t.last_download_reason}</div>}
                      </div>
                      <span className="flex shrink-0 flex-wrap items-center gap-2">
                        <Badge tone={OUTCOME_TONE[outcome] ?? "neutral"}>{OUTCOME_LABEL[outcome] ?? outcome}</Badge>
                        <Button size="sm" onClick={() => setReview({ track_id: t.id, artist: t.artist, title: t.title })}>
                          <Search size={13} /> {hasFile ? "Rivedi" : "Scegli file"}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setLinking({ id: t.id, artist: t.artist, title: t.title })}>
                          <Link2 size={13} /> Collega file
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => ignore(t)}>
                          <EyeOff size={13} /> Ignora
                        </Button>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </section>

        {/* 3. Ricerca manuale (blocco di pari livello, in evidenza) */}
        <section>
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">
            Ricerca manuale — pesca un file e aggiungilo alla collezione
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Input value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
              placeholder="Cerca su Soulseek (artista, titolo…)" disabled={!available} />
            <Button variant="outline" onClick={runSearch} disabled={!available || searching || !query.trim()}>
              <Search size={14} /> Cerca
            </Button>
          </div>
          {searching && <Loading label="Ricerca su Soulseek…" />}
          {results && results.length === 0 && !searching && (
            <p className="mt-2 text-sm text-faint">Nessun risultato per «{query}».</p>
          )}
          {results && results.length > 0 && (
            <ul className="mt-3 divide-y divide-border border border-border">
              {results.slice(0, 40).map((c, i) => (
                <li key={`${c.username}-${i}`} className="flex items-center justify-between gap-3 px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm">{c.filename.split(/[\\/]/).pop()}</div>
                    <div className="text-xs text-faint">
                      {c.format?.toUpperCase()}{c.bitrate ? ` · ${c.bitrate}kbps` : ""} · {c.username}
                    </div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => grab(c)} disabled={running}>
                    <DownloadIcon size={13} /> Scarica
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <DownloadReviewModal
        target={review}
        onClose={() => setReview(null)}
        onPicked={() => { refresh(); setReview(null); refreshPending(); }}
      />
      <LinkLocalFileModal
        target={linking}
        onClose={() => setLinking(null)}
        onLinked={() => { setLinking(null); refreshPending(); }}
      />
    </PageLayout>
  );
}
```

- [ ] **Step 3: Delete the issues page**

Run: `git rm frontend/app/downloads/issues/page.tsx`
Se la cartella `frontend/app/downloads/issues/` resta vuota, rimuoverla.

- [ ] **Step 4: Lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: build OK, nessun import rotto verso la pagina rimossa. Verificare che `EqMeter` accetti `value: number | null` (firma in `ui.tsx:172`). Se `Button` non ha `variant="ghost"`, usare la variante ghost documentata in DESIGN.md §5.

- [ ] **Step 5: Browser-verify the full surface**

Con backend + frontend attivi, aprire `/downloads`:
- barra Acquisizione in alto; con slskd non configurato l'alert compare e i controlli sono disabilitati;
- i chip-filtro mostrano i conteggi e filtrano il work-list;
- ogni riga mostra badge esito + azioni (Rivedi/Scegli file, Collega file, Ignora);
- il blocco Ricerca manuale è sotto, chiaramente etichettato;
- empty state quando non c'è nulla.
Fare screenshot in dark e paper (`preview_resize` colorScheme) per confermare entrambi i temi.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/downloads/page.tsx
git rm frontend/app/downloads/issues/page.tsx
git commit -m "feat(downloads): pagina unica con work-list azionabile inline, rimuove /issues"
```

---

### Task 6: Frontend — contatore "da sistemare" nella nav

L'archivio separato non esiste più: la voce "Download" nella sidebar porta un conteggio delle tracce da sistemare per la scopribilità.

**Files:**
- Modify: `frontend/components/index-nav.tsx`

**Interfaces:**
- Consumes: `downloadPending()` (già in `lib/api.ts`), `usePathname`.
- Produces: badge-conteggio accanto al link `/downloads`.

- [ ] **Step 1: Add the pending count**

In `frontend/components/index-nav.tsx`, aggiungere `downloadPending` all'import da `@/lib/api` (riga 8) e, dentro `IndexNav`, dopo `const pathname = usePathname();` (riga 42):

```tsx
  const [pendingCount, setPendingCount] = useState(0);
  useEffect(() => {
    let alive = true;
    downloadPending()
      .then((rows) => { if (alive) setPendingCount(rows.length); })
      .catch(() => undefined);
    return () => { alive = false; };
  }, [pathname]);  // rivaluta a ogni navigazione (es. dopo aver sistemato tracce)
```

Aggiungere `useEffect` all'import da react (riga 3): `import { useEffect, useState } from "react";`.

- [ ] **Step 2: Render the count next to the Download link**

Nel render del link (riga 87-96), sostituire il contenuto testuale `{label}` per mostrare il conteggio solo su Download:

```tsx
                  <Link
                    href={href}
                    aria-current={isActive(href) ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-1.5 whitespace-nowrap py-1 text-xs uppercase tracking-wider transition-colors",
                      isActive(href) ? "text-fg-strong underline underline-offset-4" : "text-muted hover:text-fg",
                    )}
                  >
                    {label}
                    {href === "/downloads" && pendingCount > 0 && (
                      <span className="tnum text-[10px] text-faint">({pendingCount})</span>
                    )}
                  </Link>
```

- [ ] **Step 3: Lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: build OK.

- [ ] **Step 4: Browser-verify**

Aprire l'app: la voce "Download" nella sidebar mostra `(N)` quando ci sono tracce da sistemare; il numero scompare quando l'elenco si svuota (dopo aver navigato). Verificare che il layout della nav non si rompa (dark e paper).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/index-nav.tsx
git commit -m "feat(downloads): contatore da sistemare sulla voce Download della nav"
```

---

## Known limitations (fuori scope, da annotare)

- **File orfano su "Sostituisci":** scegliendo un nuovo candidato per una traccia con file dubbio, il vecchio file resta nell'inbox slskd (non viene cancellato). Accettabile per uno strumento personale; un cleanup opzionale può arrivare in un secondo giro.
- **Virtualizzazione work-list:** oltre ~200 righe la lista non è paginata. Introdurre paginazione solo se emerge lentezza reale.

## Self-Review (esito)

- **Copertura spec:** IA una-pagina → Task 5; ricerca manuale in evidenza → Task 5 (sezione 3); Tieni/Scarta/Sostituisci → Task 2+4; contatore nav → Task 6; persistenza path (prerequisito backend) → Task 1. Stati offline/empty → Task 5.
- **Placeholder:** nessuno; tutto il codice è completo. I due punti condizionali (`variant="danger"`/`"ghost"`, firma `EqMeter`) rimandano a file esistenti con riferimento di riga, non a decisioni aperte.
- **Coerenza tipi:** `last_download_path` coerente backend (models/schema/serializer/job) ↔ frontend (`Track`); `_attempt_download`/`_process_item` triple coerenti; `DownloadReview` FE ↔ `review_detail` BE (`expected`/`downloaded`/`reason`).
