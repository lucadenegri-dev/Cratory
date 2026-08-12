# Fusione Sortory → Cratory — F4 (scanner unico) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una sola camminata sul disco, un solo job, un solo bottone: la lettura dei file produce le righe `AudioFile`, e l'aggancio alle `Track` parte da quelle righe invece di ripercorrere il disco.

**Architecture:** `index_library` smette di camminare `LIBRARY_ROOT` e diventa una fase 2 che itera le `AudioFile` con `location='library'` appena scritte dallo scanner. L'archivio resta una **passata separata**, perché `ARCHIVE_ROOT` non è nessuna delle due radici e `location` non ha un terzo valore. `scan_job` assorbe `library_index_job` e cresce a tre fasi — `scanning`, `linking`, `archive` — sotto un solo stato in memoria.

**Tech Stack:** Python 3.11.15, FastAPI, SQLAlchemy 2, SQLite, ffmpeg — Next 16, React 19, TypeScript.

**Spec di riferimento:** `docs/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md`, decisione **D5** e sezione "4. Scanner unico".

**Prerequisito:** F3b completa e il fix della `Track` duplicata per path chiuso (`b48c639`, `32b1d18`).

## Cosa si sa già, misurato

**I due walk producono lo stesso insieme.** Sulla libreria reale, `_iter_audio_files` dello scanner Organize e `scan_folder` di Cratory danno **625 file entrambi, differenza zero in entrambe le direzioni** (misurato 2026-08-12). È la premessa che rende la sostituzione sicura, ed è il primo passo del Task 1 rimisurarla: se un giorno divergessero, la fase 2 perderebbe file in silenzio.

**La fase 1 legge già ogni file per intero.** `_scan_file_fields` calcola `content_hash` (blake2b sullo stream) per ogni file a ogni scan — non è incrementale. Quindi unificare non aggiunge letture: ne toglie, perché oggi il disco viene percorso due volte.

**Il segnale incrementale della fase 2 resta `Track.local_mtime`/`local_size`.** L'`audio_hash` costa un processo ffmpeg per file e va evitato quando il file non è cambiato: uno `stat()` è cheap e il confronto è già scritto. Non si introducono colonne nuove per questo.

## Global Constraints

- Worktree **`.claude/worktrees/fusione-f1`**, branch `feat/fusione-f1`.
- **Commit senza `Co-Authored-By`.** Prima di ogni commit: `git status --porcelain` e `git branch --show-current`.
- **Ogni asserzione va provata rompendo il codice.** Quattro controlli vacui in tre fasi: nessun test di questo piano si dichiara verde senza aver visto il rosso corrispondente, e ogni invariante su dati reali conta anche il **denominatore**.
- **Le colonne derivate hanno un manutentore in ogni punto di scrittura.** `location` e `primary_file_id` sono già mantenute dallo scanner e da `file_link`: la riscrittura non deve perderle per strada — è il modo esatto in cui `location` si era degradata in F3a.
- **L'archivio resta una passata separata.** `location` continua ad avere due soli valori.
- Gli strumenti che toccano il DB stampano su quale DB lavorano.

---

## File Structure

```
backend/app/
  services/
    library_index.py        index_library() → collega_tracce() + indicizza_archivio();
                            via il walk della libreria, resta quello dell'archivio
    library_index_job.py    ELIMINATO (assorbito da scan_job)
  organize/services/
    scanner.py              scan() invoca la fase 2 dopo _reconcile
    scan_job.py             tre fasi: scanning | linking | archive; scrive last_index_at
  routers/
    tracks.py               POST /api/library/index → alias del job unico
  main.py                   il lifespan avvia il job unico
frontend/
  components/index-nav.tsx  il bottone RefreshCw punta al job unico
  lib/api.ts                startLibraryIndex → il job unico
```

---

### Task 1: La fase 2 consuma l'indice, non il disco

**Files:**
- Modify: `backend/app/services/library_index.py`
- Test: `backend/tests/test_collega_tracce.py`

**Interfaces:**
- Produces:
  - `collega_tracce(db, *, on_progress=None) -> dict` — itera le `AudioFile` con `location='library'` e `status='present'`; stesse chiavi di report di oggi (`matched`, `created`, `relinked`, `duplicates`, `lost`, `failed`, `unchanged`, `errors`, `created_ids`)
  - `indicizza_archivio(db, *, archive_root, on_progress=None) -> dict` — la passata archivio di oggi, estratta e invariata
- `index_library` resta come sottile wrapper delle due, per non rompere i chiamanti finché il Task 3 non li sposta

- [ ] **Step 1: Rimisurare che i due walk coincidano**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -c "
from app.core.config import settings
from app.organize.services.scanner import _iter_audio_files
from app.services.local_import import scan_folder
a = {p for p, _ in _iter_audio_files(settings.library_root)}
b = {str(p.resolve()) for p in scan_folder(settings.library_root)}
print('scanner:', len(a), '| scan_folder:', len(b))
print('solo scanner:', len(a - b), '| solo scan_folder:', len(b - a))
for p in sorted(a - b)[:5]: print('   A:', p)
for p in sorted(b - a)[:5]: print('   B:', p)
"
```

Atteso: due conteggi uguali e **zero** differenze. Se ci sono file solo in `scan_folder`, la fase 2 li perderebbe: **fermati** e riconcilia i filtri (estensioni da `settings.audio_exts`, esclusione dei path nascosti) prima di andare avanti.

- [ ] **Step 2: Scrivere i test che falliscono**

Crea `backend/tests/test_collega_tracce.py`. La fixture `fake_audio` va spostata da `tests/test_library_index.py` a `tests/conftest.py` (serve a tre file da qui in avanti).

```python
"""Fase 2: l'aggancio parte dalle righe AudioFile, non da una camminata sul disco."""

from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile
from app.organize.services.roots import radici
from app.services.library_index import collega_tracce


def _riga(db, path: str, *, location: str = "library") -> AudioFile:
    f = AudioFile(root_id=radici(db)[location].id, path=path, ext=".mp3", size_bytes=1,
                  hash_method="stream", status="present", location=location)
    db.add(f)
    db.flush()
    return f


def test_crea_la_traccia_partendo_dalla_riga(db, fake_audio):
    make, _root = fake_audio
    p = make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    _riga(db, str(p.resolve()))
    db.commit()

    report = collega_tracce(db)

    assert report["created"] == 1
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert t is not None and t.source_type == "local_files"


def test_non_guarda_i_file_dell_inbox(db, fake_audio):
    """La fase 2 aggancia solo la libreria: un file in inbox non è una traccia."""
    make, _root = fake_audio
    p = make("pack/x.mp3", digest="H8", artist="X", title="X")
    _riga(db, str(p.resolve()), location="inbox")
    db.commit()

    report = collega_tracce(db)

    assert report["created"] == 0
    assert db.scalars(select(Track)).all() == []


def test_non_guarda_un_file_marcato_missing(db, fake_audio):
    make, _root = fake_audio
    p = make("Techno/N/N - Gone.mp3", digest="H9", artist="N", title="Gone")
    f = _riga(db, str(p.resolve()))
    f.status = "missing"
    db.commit()

    assert collega_tracce(db)["created"] == 0


def test_e_idempotente(db, fake_audio):
    make, _root = fake_audio
    p = make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    _riga(db, str(p.resolve()))
    db.commit()

    collega_tracce(db)
    db.commit()
    secondo = collega_tracce(db)

    assert secondo["created"] == 0
    assert len(db.scalars(select(Track)).all()) == 1


def test_aggancia_la_riga_alla_traccia(db, fake_audio):
    """L'invariante di F3a deve reggere anche passando dalla fase 2."""
    make, _root = fake_audio
    p = make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    f = _riga(db, str(p.resolve()))
    db.commit()

    collega_tracce(db)
    db.commit()

    db.refresh(f)
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert f.track_id == t.id
    assert t.primary_file_id == f.id
```

- [ ] **Step 3: Lanciarli e vederli fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_collega_tracce.py -v
```

Atteso: `ImportError` su `collega_tracce`.

- [ ] **Step 4: Estrarre la passata archivio**

In `library_index.py`, spostare il blocco che tratta `archive_files` in una funzione a sé:

```python
def indicizza_archivio(db: Session, *, archive_root, on_progress=None) -> dict:
    """Passata separata sull'archivio delle scartate.

    Resta separata di proposito: ARCHIVE_ROOT non è nessuna delle due radici
    dello scanner, e `AudioFile.location` ha due soli valori. I file d'archivio
    non entrano nell'indice: si limitano a marcare come scartate le tracce
    corrispondenti.
    """
```

Corpo invariato rispetto a oggi, incluso l'uso di `ArchiveSeen`.

- [ ] **Step 5: Riscrivere la fase 2 sulle righe**

La nuova `collega_tracce` sostituisce le due passate su `files` con una query:

```python
def collega_tracce(db: Session, *, on_progress=None) -> dict:
    """Aggancia le tracce ai file già indicizzati dallo scanner.

    Fino a F4 questa funzione camminava LIBRARY_ROOT per conto proprio: due
    attraversamenti dello stesso disco, con la possibilità che i due indici
    divergessero. Ora legge le righe che la fase 1 ha appena scritto — le due
    camminate producevano lo stesso insieme (verificato sul disco reale), quindi
    la sostituzione non perde file.
    """
    righe = db.scalars(
        select(AudioFile)
        .where(AudioFile.location == "library", AudioFile.status == "present")
        .order_by(AudioFile.path)
    ).all()
    report = {"scanned": len(righe), "matched": 0, "created": 0, "relinked": 0,
              "duplicates": 0, "lost": 0, "orphans_removed": 0, "failed": 0,
              "unchanged": 0, "archived": 0, "errors": [], "created_ids": []}
    ...
```

> **Correzione a posteriori (dopo l'esecuzione del Task 1).** Lo scheletro qui sotto mostra **un ciclo unico**, e questo era sbagliato: l'`index_library` originale ha un disegno **a due passate** — prima il fast-path su tutte le righe, poi il flusso completo sulle sole `pending`. Collassarle rende l'ordine di `AudioFile.path` semanticamente rilevante, e un duplicato con lo stesso hash che ordina prima può rubare il `local_path` a un file già agganciato. Il disegno a due passate va conservato. Allo stesso modo, il wrapper dello Step 6 chiamava la riconciliazione dentro la fase 2, quindi **prima** dell'archivio: così una traccia il cui file passa in `ARCHIVE_ROOT` viene cancellata invece che marcata scartata. L'ordine corretto è **libreria → archivio → riconciliazione**, con quest'ultima estratta a sé e chiamata sull'unione dei path visti. Vedi `riconcilia_possessi` nel codice finale.

Il corpo del ciclo, con lo scheletro esplicito. I blocchi marcati «invariato» sono quelli di oggi, spostati senza modifiche: si trapiantano, non si riscrivono.

```python
    for indice, riga in enumerate(righe):
        path = Path(riga.path)
        try:
            stat = path.stat()
        except OSError as exc:
            # Sparito fra fase 1 e fase 2: si conta e si prosegue.
            report["failed"] += 1
            report["errors"].append({"path": riga.path, "error": str(exc)})
            continue

        # Fast-path. Si parte da riga.track_id — la relazione che F3a ha reso
        # esplicita — e solo in mancanza si ricade sulla ricerca per local_path,
        # che è ciò che il codice faceva prima di avere la colonna.
        known = db.get(Track, riga.track_id) if riga.track_id else None
        if known is None:
            known = db.scalar(select(Track).where(Track.local_path == riga.path))
        if (known is not None and known.local_mtime == stat.st_mtime
                and known.local_size == stat.st_size):
            report["unchanged"] += 1
            seen_paths.add(riga.path)
            if known.audio_hash:
                seen_digests.add(known.audio_hash)
            ...  # invariato: recupero added_at, righe ~248-251 di oggi
            continue

        # Flusso completo: qui e solo qui si paga ffmpeg.
        try:
            digest = audio_hash(path)
        except LocalFilesError as exc:
            report["failed"] += 1
            report["errors"].append({"path": riga.path, "error": str(exc)})
            continue
        ...  # invariato: guardia sui digest già visti nella stessa corsa
        tags = read_tags(path)
        track, how = _find_track(db, digest=digest, tags=tags, path=str(path.resolve()))
        ...  # invariato: _fill_identity, _own, aggiorna_primary, contatori
        if on_progress is not None:
            on_progress(indice + 1, len(righe), )
```

La spazzata finale delle tracce il cui file non c'è più resta com'è, con una sola differenza: il confronto è contro `seen_paths` costruito dalle righe, non dai file trovati sul disco.

**Attenzione al parametro di `on_progress`**: qui la firma è a due argomenti (come `library_index` oggi), mentre lo scanner ne usa tre. È il Task 2 ad adattarla — non anticiparlo qui.

- [ ] **Step 6: Ridurre `index_library` a wrapper**

```python
def index_library(db: Session, *, root=None, archive_root=None, on_progress=None) -> dict:
    """Compatibilità: chiama la fase 2 e, se configurato, l'archivio.

    `root` non è più usato — la fase 2 parte dall'indice. Il parametro resta
    per non rompere i chiamanti finché il Task 3 non li sposta sul job unico.
    """
```

- [ ] **Step 7: Test verdi e prova che sappiano fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_collega_tracce.py tests/test_library_index.py -v
```

Atteso: tutti verdi.

Poi la prova: togli il filtro `AudioFile.location == "library"` dalla query → **`test_non_guarda_i_file_dell_inbox` deve fallire**. Ripristina. E togli il filtro su `status` → **`test_non_guarda_un_file_marcato_missing` deve fallire**. Ripristina, e verifica con `git diff` che il file sia tornato identico.

- [ ] **Step 8: Suite e commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend && \
git commit -m "feat(f4): la fase 2 aggancia partendo dall'indice, non dal disco"
```

---

### Task 2: Una camminata sola

**Files:**
- Modify: `backend/app/organize/services/scanner.py`
- Test: `backend/tests/organize/test_scan_due_fasi.py`

**Interfaces:**
- `scanner.scan(db, roots, on_progress=None) -> ScanSummary` — invariata nella firma; `on_progress(processed, total, phase)` riceve ora anche `phase="linking"`
- `ScanSummary` guadagna il report della fase 2 in un campo `linking: dict | None`

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_scan_due_fasi.py`:

```python
"""Uno scan solo produce l'indice dei file E le tracce."""

from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile
from app.organize.services.roots import radici
from app.organize.services.scanner import scan


def test_uno_scan_produce_indice_e_tracce(db, fake_audio, monkeypatch):
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    summary = scan(db, [radici(db)["library"]])
    db.commit()

    assert summary.inserted == 1
    assert len(db.scalars(select(AudioFile)).all()) == 1
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert t is not None
    assert summary.linking is not None and summary.linking["created"] == 1


def test_le_fasi_sono_riportate_al_progresso(db, fake_audio, monkeypatch):
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    fasi = []
    scan(db, [radici(db)["library"]], on_progress=lambda p, t, phase: fasi.append(phase))
    db.commit()

    assert "scanning" in fasi
    assert "linking" in fasi


def test_il_secondo_scan_non_cambia_nulla(db, fake_audio, monkeypatch):
    """Idempotenza: è la milestone della fase."""
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    scan(db, [radici(db)["library"]])
    db.commit()
    secondo = scan(db, [radici(db)["library"]])
    db.commit()

    assert secondo.inserted == 0
    assert secondo.linking["created"] == 0
    assert len(db.scalars(select(Track)).all()) == 1
    assert len(db.scalars(select(AudioFile)).all()) == 1
```

- [ ] **Step 2: Lanciarli e vederli fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/organize/test_scan_due_fasi.py -v
```

Atteso: FAIL — `ScanSummary` non ha `linking`.

- [ ] **Step 3: Invocare la fase 2 dallo scanner**

In `scanner.scan`, dopo `_reconcile(...)` e prima del `db.commit()` finale:

```python
    # Fase 2: le tracce si agganciano ai file appena indicizzati. Una camminata
    # sola sul disco (D5 della spec): prima era library_index a ripercorrerlo.
    from app.services.library_index import collega_tracce

    def _progress_linking(processed: int, total: int) -> None:
        if on_progress is not None:
            on_progress(processed, total, "linking")

    summary.linking = collega_tracce(db, on_progress=_progress_linking)
```

L'import è **differito dentro la funzione**: `app/services/library_index.py` importa già da `app/organize/`, e un import a livello di modulo qui chiuderebbe il ciclo. È la stessa ragione per cui `file_link` deve restare piccolo.

Aggiungere `linking: dict | None = None` a `ScanSummary`.

- [ ] **Step 4: Test verdi e prova di fallimento**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/organize/test_scan_due_fasi.py -v
```

Atteso: 3 passed.

Poi commenta la chiamata a `collega_tracce` → **tutti e tre devono fallire**. Ripristina e verifica con `git diff`.

- [ ] **Step 5: Suite e commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend && \
git commit -m "feat(f4): una camminata sola, lo scan aggancia le tracce in fase 2"
```

---

### Task 3: Un solo job

**Files:**
- Delete: `backend/app/services/library_index_job.py`
- Modify: `backend/app/organize/services/scan_job.py`, `backend/app/main.py`, `backend/app/routers/tracks.py`
- Test: `backend/tests/organize/test_job_unico.py`

**Interfaces:**
- `scan_job.start_job(locations=None) -> dict` — invariata
- `scan_job.start_job_if_due() -> dict | None` — nuova, assorbe quella di `library_index_job` (avvio automatico al boot, con la stessa finestra)
- `scan_job.job_state()` — lo stato porta `phase` fra `scanning | linking | archive`

**Cosa forniva `library_index_job` prima di sparire** — inventario obbligatorio, non è cosa importa: lo stato in memoria con le chiavi del report, `start_job()`, `is_running()`, `start_job_if_due()` chiamata dal lifespan di `main.py`, e la scrittura di `app_state.last_index_at` a fine corsa. Ognuna deve ricomparire nel job unico.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_job_unico.py`:

```python
"""Un solo job per l'intera scansione."""

import pytest


def test_library_index_job_non_esiste_piu():
    with pytest.raises(ModuleNotFoundError):
        import app.services.library_index_job  # noqa: F401


def test_scan_job_espone_lavvio_automatico():
    from app.organize.services import scan_job

    assert hasattr(scan_job, "start_job_if_due")


def test_lo_stato_prevede_le_tre_fasi():
    from app.organize.services import scan_job

    stato = scan_job.job_state()
    assert "phase" in stato


def test_la_corsa_scrive_last_index_at(db, fake_audio, monkeypatch):
    """La data dell'ultima indicizzazione alimenta l'avvio automatico: se si
    perde, il job riparte a ogni reload di uvicorn."""
    from app.core.config import settings
    from app.organize.services import scan_job
    from app.services.app_state import get_state

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    scan_job._run(None)  # sincrono, senza thread

    # _run apre una SessionLocal propria: la sessione del test ha una vista
    # precedente al suo commit. Il rollback la rinfresca senza perdere nulla
    # (il seed è già committato sopra).
    db.rollback()
    assert get_state(db, "last_index_at") is not None
```

- [ ] **Step 2: Lanciarli e vederli fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/organize/test_job_unico.py -v
```

Atteso: i primi due FAIL.

- [ ] **Step 3: Portare l'avvio automatico e `last_index_at` in `scan_job`**

Spostare `_auto_index_due` e la logica di `start_job_if_due` da `library_index_job.py` a `scan_job.py`, invariate. In `_run`, a fine corsa riuscita:

```python
            set_state(db, "last_index_at", utcnow().isoformat())
```

- [ ] **Step 4: Spostare i chiamanti**

In `main.py`, il lifespan: `library_index_job.start_job_if_due()` → `scan_job.start_job_if_due()`, con l'import aggiornato. La condizione `if runtime_settings.library_root()` resta.

In `routers/tracks.py`, `POST /api/library/index` e `GET /api/library/index/status` passano al job unico. **Non si rimuovono le rotte**: le usa il frontend e le tocca il Task 4.

Poi:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git rm -q backend/app/services/library_index_job.py && \
grep -rn "library_index_job" backend/app backend/tests | head
```

Atteso dal `grep`: nessun output. Attenzione a `tests/conftest.py`, che elenca `library_index_job` fra i moduli di cui azzera lo stato: va sostituito con `scan_job`, altrimenti lo stato del job unico si contamina fra i test.

- [ ] **Step 5: Test verdi**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/organize/test_job_unico.py -v && \
.venv/bin/python -m pytest tests -q
```

Atteso: tutti verdi. Poi commenta la riga `set_state(db, "last_index_at", …)` → **`test_la_corsa_scrive_last_index_at` deve fallire**. Ripristina.

- [ ] **Step 6: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend && \
git commit -m "feat(f4): un solo job di scansione, library_index_job assorbito"
```

---

### Task 4: Un solo bottone

**Files:**
- Modify: `frontend/components/index-nav.tsx`, `frontend/lib/api.ts`, e il bottone di scan in `frontend/app/organize/`
- Test: `frontend/tests/scan-un-solo-avvio.test.ts`

**Prima di iniziare:** leggere `frontend/CLAUDE.md`.

Oggi ci sono due avvii: l'icona `RefreshCw` in `index-nav.tsx` che chiama `startLibraryIndex`, e il bottone di scan nella sezione Organize. Producono lo stesso lavoro e vanno unificati; la barra di avanzamento è una sola già dal `jobs-provider`.

- [ ] **Step 1: Trovare il perimetro**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
grep -rn "startLibraryIndex\|libraryIndexStatus\|/library/index\|startScan" app components lib
```

L'elenco che esce è il perimetro esatto. **Se compare un file non previsto, trattalo qui.**

- [ ] **Step 2: Scrivere il test che fallisce**

Crea `frontend/tests/scan-un-solo-avvio.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const nav = readFileSync(resolve(__dirname, "../components/index-nav.tsx"), "utf8");

describe("un solo avvio della scansione", () => {
  it("la nav non chiama più l'indicizzazione libreria separata", () => {
    expect(nav).not.toContain("startLibraryIndex");
  });

  it("la nav avvia il job unico", () => {
    expect(nav).toContain("startScan");
  });
});
```

- [ ] **Step 3: Lanciarlo, vederlo fallire, poi unificare**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx vitest run tests/scan-un-solo-avvio.test.ts
```

Atteso: FAIL su entrambe.

Poi: in `index-nav.tsx` sostituire `startLibraryIndex` con l'avvio del job unico; in `lib/api.ts` far puntare `startLibraryIndex` al job unico oppure rimuoverla se nessuno la usa più. Il bottone di Organize resta ma chiama lo stesso job.

- [ ] **Step 4: Typecheck, lint, build, test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx tsc --noEmit && npm run lint && npm run build && npm run test:unit
```

Atteso: tutti verdi.

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A frontend && \
git commit -m "feat(f4): un solo bottone avvia la scansione"
```

---

### Task 5: Verifica di fase

- [ ] **Step 1: Suite e frontend**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
cd ../frontend && npm run lint && npm run build && npm run test:unit && npm run test:e2e
```

- [ ] **Step 2: Backup prima di toccare il DB reale**

```bash
mkdir -p ~/Backup/fusione-f4 && \
cp ~/Develop/DJProject01/backend/data/djassistant.db ~/Backup/fusione-f4/djassistant-pre-f4.db && \
ls -la ~/Backup/fusione-f4/
```

- [ ] **Step 3: Una corsa vera, e la prova dell'idempotenza**

Avvia backend e frontend, lancia la scansione dal bottone unico e osserva che la barra attraversi `scanning` e `linking`. Poi, a corsa finita:

```bash
sqlite3 ~/Develop/DJProject01/backend/data/djassistant.db "
select 'audio_file', count(*) from audio_file
union all select 'location=library', count(*) from audio_file where location='library'
union all select 'location=inbox', count(*) from audio_file where location='inbox'
union all select 'tracks', count(*) from tracks
union all select 'asimmetrie', count(*) from tracks t where t.primary_file_id is not null
    and not exists (select 1 from audio_file f where f.id=t.primary_file_id and f.track_id=t.id)
union all select 'primary orfani', count(*) from tracks t where t.primary_file_id is not null
    and not exists (select 1 from audio_file f where f.id=t.primary_file_id)
union all select 'track_id orfani', count(*) from audio_file f where f.track_id is not null
    and not exists (select 1 from tracks t where t.id=f.track_id)
union all select 'duplicati per path', count(*) from
    (select local_path from tracks where has_local_file=1 and local_path is not null
     group by local_path having count(*)>1)
union all select 'location incoerente', count(*) from audio_file f join scan_root r on r.id=f.root_id
    where (f.location='library') != (r.label='Libreria');"
```

Annota i valori. Poi **lancia una seconda scansione** e ripeti la stessa query.

Atteso: `tracks` e `audio_file` **identici** fra le due corse, tutti i conteggi di errore a **0**, e il report della seconda corsa con `created: 0`. È la milestone della fase — una seconda corsa che non cambia niente.

- [ ] **Step 4: Verificare che il disco sia stato percorso una volta sola**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
grep -rn "scan_folder\|_iter_audio_files\|os.walk" app/services/library_index.py app/organize/services/scanner.py
```

Atteso: `_iter_audio_files` solo in `scanner.py`; in `library_index.py` `scan_folder` compare **solo** dentro `indicizza_archivio`. Se compare altrove, la fase 2 sta ancora camminando il disco.

- [ ] **Step 5: Spuntare la spec**

Nella tabella delle fasi, riga **F4**: annotare completamento, il conteggio dei test e l'esito dell'idempotenza dello Step 3.

- [ ] **Step 6: Commit e riepilogo**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && git add -A docs && \
git commit -m "docs(f4): F4 completata — una camminata, un job, un bottone"
```

Riporta: conteggio test, i valori delle due corse dello Step 3 affiancati, e se la barra ha mostrato entrambe le fasi.

---

## Definizione di "F4 completa"

- Il disco viene percorso **una volta sola**: `_iter_audio_files` in `scanner.py`, `scan_folder` solo per l'archivio.
- `library_index_job.py` non esiste più; `scan_job` porta `start_job_if_due` e scrive `last_index_at`.
- Un solo bottone avvia la scansione; la barra mostra `scanning` e `linking`.
- Una seconda corsa consecutiva non cambia una riga — né `audio_file`, né `tracks`.
- Tutti gli invarianti di F3a e F3b restano a 0 dopo una corsa reale.
- L'archivio resta una passata separata e `location` continua ad avere due valori.
