# Fusione Sortory → Cratory — F3b (via `scan_root`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Togliere `scan_root` dal dominio — dal codice, dall'API e dalla UI — sostituendolo con le due cartelle canoniche di Settings, senza toccare lo schema del database.

**Architecture:** Le sorgenti smettono di essere entità gestite dall'utente e diventano derivate da `LIBRARY_ROOT` e `SLSKD_DOWNLOAD_DIR`. `root_targets(db) -> dict[int, str]` collassa in `target_root() -> str`, perché nei dati reali entrambe le radici puntano già alla stessa destinazione. La tabella `scan_root` e la colonna `audio_file.root_id` **restano nel database** come schema morto, mantenute allineate da una funzione interna: SQLite non può droppare `root_id` senza un rebuild di `audio_file`, ed è l'unica operazione dell'intera fusione che non vale il rischio.

**Tech Stack:** Python 3.11.15, FastAPI, SQLAlchemy 2, SQLite — Next 16, React 19, TypeScript.

**Spec di riferimento:** `docs/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md`, decisione **D7**.

**Prerequisito:** F3a completa su `feat/fusione-f1` (commit `a58b2e1`).

## Perché lo schema non si tocca

Lo schema live di `audio_file`:

```sql
CONSTRAINT uq_audio_root_path UNIQUE (root_id, path),
FOREIGN KEY(root_id) REFERENCES scan_root (id)
```

`ALTER TABLE ... DROP COLUMN` di SQLite rifiuta una colonna che sia indicizzata, dentro un `UNIQUE`, o dentro una foreign key: `root_id` è tutte e tre. L'indice `ix_audio_file_root_id` si droppa, ma il vincolo `uq_audio_root_path` è materializzato come `sqlite_autoindex_audio_file_1`, che non è droppabile. Resterebbe solo il rebuild della tabella.

Quel rebuild è l'operazione più rischiosa disponibile in tutta la fusione:

- `audio_file` ha **quattro** tabelle figlie — `issue`, `dup_member`, `plan_op`, `undo_journal` — e F2 ha appena finito di ripulire 158 riferimenti orfani da due di esse;
- il docstring di `_migrate_drop_legacy` (`app/db.py:153`) documenta il modo esatto in cui questo è già andato storto una volta: con le foreign key attive, il `RENAME` riscrive le clausole `REFERENCES` dei figli verso il nome temporaneo;
- esiste un precedente esplicito nel codice per la scelta opposta: `Track.playlist_id`, tenuta come colonna morta perché non droppabile.

E c'è una ragione di tempismo: **F4 riscrive lo scanner**, e potrebbe cambiare la forma di `audio_file` per conto suo. Se un rebuild servirà davvero, farne uno solo dopo F4 è meglio che farne due.

Quindi F3b consegna la rimozione **di prodotto** — nessuna pagina Sources, nessuna API, nessun concetto utente — e rimanda quella **di schema**, dichiarandola invece di dimenticarla.

## Global Constraints

- Worktree **`.claude/worktrees/fusione-f1`**, branch `feat/fusione-f1`.
- **Commit senza `Co-Authored-By`.** Prima di ogni commit: `git status --porcelain` e `git branch --show-current`.
- **Ogni strumento che tocca il DB stampa su quale DB sta lavorando** — il worktree ha un proprio `.env` e un proprio `djassistant.db`, ed è già costato una diagnosi sbagliata in F3a.
- **`location` è la colonna che sostituisce `root_id` nel dominio.** Ogni filtro, ogni conteggio, ogni raggruppamento che oggi usa `root_id` passa a `location`.
- **Invarianti sulla correttezza, non sulla presenza.** La lezione di F3a: `location vuota = 0` era verde mentre i valori erano sbagliati. Ogni invariante di questa fase confronta il valore col suo ricalcolo.
- **Frontend prima, backend dopo** (Task 4 prima del Task 5): togliere le chiamate prima degli endpoint non rompe mai nulla; il contrario sì.

---

## File Structure

```
backend/app/organize/
  services/
    planning.py          root_targets() → target_root(); set_root_target() eliminata
    planner.py           firma: root_targets dict → target_root str
    conflict.py          idem
    scanner.py           root_id derivato da location
    roots.py             NUOVO: le due radici derivate da Settings
  routers/
    sources.py           ELIMINATO
    settings.py          via PUT /roots/{root_id}/target
    issues.py            filtro root_id → location
    library.py           filtro root_id → location; conteggio sorgenti da Settings
  schemas.py             via ScanRootCreate/ScanRootRead/RootTargetRead/RootTargetUpdate
  models.py              ScanRoot e AudioFile.root_id marcate come schema morto
frontend/
  app/organize/sources/  ELIMINATA
  components/organize/   via add-source.tsx, source-menu.tsx
  lib/organize/api.ts    via listSources/addSource/deleteSource/setRootTarget
```

---

### Task 1: `root_targets` collassa in un solo target

**Files:**
- Modify: `backend/app/organize/services/planning.py`, `planner.py`, `conflict.py`
- Test: `backend/tests/organize/test_target_unico.py`

**Interfaces:**
- Produces: `planning.target_root() -> str` — restituisce `settings.library_root`
- Consumes: `app.core.config.settings.library_root`
- Le firme `planner.render_destination(file, tags, settings_snapshot, target_root: str)` e `planner.build_plan(..., target_root: str)` e `conflict.compute(..., target_root: str)` sostituiscono il parametro `root_targets: dict`

**Perché collassa.** `root_targets(db)` restituisce `{root.id: root.target_root or root.path}`. Nei dati reali: la radice Downloads ha `target_root = /Music/Library`, la radice Library ha `target_root` nullo e quindi cade sul proprio path, `/Music/Library`. **Entrambe danno la stessa destinazione**, ed è strutturale, non un caso: la destinazione di un Apply è sempre la libreria. Un file dell'inbox ci arriva, un file della libreria ci resta e si riorganizza dentro.

- [ ] **Step 1: Verificare l'assunto sui dati reali prima di scrivere codice**

```bash
sqlite3 ~/Develop/DJProject01/backend/data/djassistant.db \
  "select id, path, coalesce(target_root, path) as destinazione from scan_root;"
```

Atteso: due righe, **stessa** `destinazione`, uguale a `LIBRARY_ROOT` in `backend/.env`.

**Se le destinazioni differiscono, fermati**: l'intero task poggia su questo, e un target per-radice diverso va discusso, non appiattito.

- [ ] **Step 2: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_target_unico.py`:

```python
"""La destinazione di un Apply è una sola: la libreria."""

from app.organize.services import planning


def test_target_root_e_library_root(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "library_root", "/Users/x/Music/Library")
    assert planning.target_root() == "/Users/x/Music/Library"


def test_root_targets_non_esiste_piu():
    assert not hasattr(planning, "root_targets")
    assert not hasattr(planning, "set_root_target")
```

- [ ] **Step 3: Lanciarlo e vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_target_unico.py -v
```

Atteso: FAIL — `planning.target_root` non esiste e `root_targets` sì.

- [ ] **Step 4: Sostituire in `planning.py`**

Eliminare `set_root_target` (righe ~57-64) e `root_targets` (righe ~67-68), e mettere al loro posto:

```python
def target_root() -> str:
    """Destinazione di ogni operazione di Apply: la libreria.

    Fino a F3b esisteva un target per ScanRoot (`root_targets`), ma le due
    radici davano già la stessa destinazione — ed è strutturale: un file
    dell'inbox arriva in libreria, un file della libreria ci resta e si
    riorganizza dentro. Non c'è un secondo posto dove un Apply possa portare
    qualcosa.
    """
    from app.core.config import settings

    return settings.library_root
```

In `_inputs`, l'ultimo elemento della tupla diventa `target_root()`.

- [ ] **Step 5: Adeguare `planner.py`**

Riga ~79, la firma di `render_destination` perde `root_targets: dict` e prende `target_root: str`. Riga ~87:

```python
    base = target_root or os.path.dirname(file.path)
```

Riga ~93 e ~120: stessa sostituzione su `build_plan` e sulla chiamata interna.

- [ ] **Step 6: Adeguare `conflict.py`**

Righe ~46, ~69 e ~79: stesso cambio di parametro. La riga 69 diventa:

```python
        target = target_root if file else None
```

- [ ] **Step 7: Test e suite**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/organize/test_target_unico.py -v && \
.venv/bin/python -m pytest tests -q
```

Atteso: il test nuovo verde; nella suite, i test che passavano un dict a `build_plan`/`compute` falliscono per la firma cambiata. **Aggiornali**: è un cambio voluto, e sono il modo in cui ti accorgi di aver coperto tutti i chiamanti.

- [ ] **Step 8: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend && \
git commit -m "refactor(f3b): un solo target di Apply, via root_targets per-radice"
```

---

### Task 2: Le due radici derivate da Settings

**Files:**
- Create: `backend/app/organize/services/roots.py`
- Modify: `backend/app/organize/services/scanner.py`
- Modify: `backend/app/organize/models.py` (commenti di schema morto)
- Test: `backend/tests/organize/test_roots_derivate.py`

**Interfaces:**
- Produces:
  - `radici(db) -> dict[str, ScanRoot]` — chiavi `"library"` e `"inbox"`; crea o riallinea le righe per farle corrispondere a `settings.library_root` e `settings.slskd_download_dir`; salta la chiave la cui cartella non è configurata
  - `root_id_per(db, location: str) -> int` — l'id da scrivere su `audio_file.root_id`

**Il contratto dello schema morto.** `scan_root` e `audio_file.root_id` non spariscono dal database, quindi devono restare *coerenti*: `root_id` è `NOT NULL` con una FK viva, perciò ogni `AudioFile` nuovo deve puntare a una riga esistente. Da qui in avanti quella riga non la sceglie l'utente: la deriva `location`.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_roots_derivate.py`:

```python
"""Le radici non sono più gestite dall'utente: si derivano da Settings."""

import pytest
from sqlalchemy import select

from app.organize.models import ScanRoot
from app.organize.services.roots import radici, root_id_per

LIB = "/Users/x/Music/Library"
INBOX = "/Users/x/Music/Downloads"


@pytest.fixture(autouse=True)
def _cartelle(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "library_root", LIB)
    monkeypatch.setattr(settings, "slskd_download_dir", INBOX)


def test_crea_le_due_radici_se_mancano(db):
    esito = radici(db)
    db.flush()

    assert set(esito) == {"library", "inbox"}
    assert esito["library"].path == LIB
    assert esito["inbox"].path == INBOX
    assert db.scalar(select(ScanRoot).where(ScanRoot.path == LIB)) is not None


def test_e_idempotente(db):
    radici(db)
    db.flush()
    radici(db)
    db.flush()

    assert len(db.scalars(select(ScanRoot)).all()) == 2


def test_adotta_una_radice_storica_senza_label(db):
    """Sul DB reale le due righe hanno label NULL: vanno adottate, non duplicate.

    È il caso che su un DB di test fresco non si presenta mai — e proprio per
    questo è quello che va testato."""
    storica = ScanRoot(path=LIB, label=None)
    db.add(storica)
    db.flush()
    id_storico = storica.id

    esito = radici(db)
    db.flush()

    assert esito["library"].id == id_storico
    assert esito["library"].label == "Libreria"
    assert len(db.scalars(select(ScanRoot).where(ScanRoot.path == LIB)).all()) == 1


def test_riallinea_una_radice_esistente_se_la_cartella_cambia(db, monkeypatch):
    """Cambiare LIBRARY_ROOT in .env non deve creare una terza radice orfana."""
    from app.core.config import settings

    prima = radici(db)["library"]
    db.flush()
    id_prima = prima.id

    monkeypatch.setattr(settings, "library_root", "/Users/x/Music/Library2")
    dopo = radici(db)["library"]
    db.flush()

    assert dopo.id == id_prima          # stessa riga, non una nuova
    assert dopo.path == "/Users/x/Music/Library2"
    assert len(db.scalars(select(ScanRoot)).all()) == 2


def test_salta_la_radice_non_configurata(db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "slskd_download_dir", "")
    esito = radici(db)
    db.flush()

    assert set(esito) == {"library"}


def test_root_id_per_location(db):
    esito = radici(db)
    db.flush()

    assert root_id_per(db, "library") == esito["library"].id
    assert root_id_per(db, "inbox") == esito["inbox"].id
```

- [ ] **Step 2: Lanciarlo e vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_roots_derivate.py -v
```

Atteso: `ModuleNotFoundError: No module named 'app.organize.services.roots'`.

- [ ] **Step 3: Scrivere il modulo**

Crea `backend/app/organize/services/roots.py`:

```python
"""Le due radici canoniche, derivate da Settings.

`scan_root` non è più un'entità gestita dall'utente: da F3b esistono esattamente
due cartelle, `LIBRARY_ROOT` e `SLSKD_DOWNLOAD_DIR`, e la tabella le rispecchia.

La tabella sopravvive come **schema morto**: `audio_file.root_id` è NOT NULL con
una FK viva e SQLite non può droppare la colonna (è dentro `uq_audio_root_path`),
quindi ogni file nuovo deve comunque puntare a una riga esistente. Qui c'è
l'unico posto che le scrive. Vedi la spiegazione in testa al piano F3b.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.organize.models import ScanRoot

# label -> lettura della cartella dalle Settings. La label identifica la riga
# nel tempo: cambiare la cartella in .env riallinea la riga, non ne crea una nuova.
_LABEL = {"library": "Libreria", "inbox": "Inbox"}


def _cartella(location: str) -> str:
    return settings.library_root if location == "library" else settings.slskd_download_dir


def radici(db: Session) -> dict[str, ScanRoot]:
    """Le radici esistenti e allineate alle cartelle configurate.

    Idempotente. Una cartella non configurata (stringa vuota) non produce riga:
    quella metà dello scan è semplicemente inattiva, come già fa Cratory con
    LIBRARY_ROOT vuoto. Non fa commit.
    """
    esito: dict[str, ScanRoot] = {}
    for location, label in _LABEL.items():
        cartella = _cartella(location)
        if not cartella:
            continue
        riga = db.scalar(select(ScanRoot).where(ScanRoot.label == label))
        if riga is None:
            # ADOZIONE. Sul DB reale le due righe storiche hanno label NULL (le
            # sorgenti le aveva create l'utente, senza etichetta): cercarle solo
            # per label ne creerebbe due nuove e lascerebbe i 1778 file
            # esistenti agganciati a righe che nessuno mantiene più. Si adotta
            # la riga che punta già alla cartella giusta, stampandole la label —
            # da lì in avanti è la label a identificarla, così un cambio di
            # cartella in .env riallinea invece di duplicare.
            riga = db.scalar(select(ScanRoot).where(ScanRoot.path == cartella,
                                                    ScanRoot.label.is_(None)))
        if riga is None:
            riga = ScanRoot(path=cartella, label=label)
            db.add(riga)
        else:
            riga.label = label
            riga.path = cartella
        # target_root resta NULL: la destinazione ora la dà planning.target_root().
        riga.target_root = None
        esito[location] = riga
    db.flush()
    return esito


def root_id_per(db: Session, location: str) -> int:
    """L'id da scrivere su `audio_file.root_id` per un file di quella collocazione."""
    riga = radici(db).get(location)
    if riga is None:
        raise ValueError(f"cartella non configurata per location={location!r}")
    return riga.id
```

- [ ] **Step 4: Far usare `roots` allo scanner**

In `scanner.py`, dove oggi si crea un `AudioFile` (riga ~116) si passa già `location=_location_per(path)`. Aggiungere accanto:

```python
                root_id=root_id_per(db, _location_per(path)),
```

sostituendo l'assegnazione attuale che prende l'id dalla `ScanRoot` in ingresso. Nel ramo `moved` (riga ~168), accanto a `row.location = _location_per(moved_path)`:

```python
                row.root_id = root_id_per(db, row.location)
```

— perché un file che attraversa il confine inbox↔library cambia anche radice, ed è esattamente ciò che fa un Apply.

Import in testa: `from app.organize.services.roots import root_id_per`.

- [ ] **Step 5: Marcare lo schema morto nel modello**

In `backend/app/organize/models.py`, sopra `class ScanRoot` e sopra `AudioFile.root_id`:

```python
# SCHEMA MORTO (F3b). Le sorgenti non sono più un'entità di dominio: esistono
# due cartelle, LIBRARY_ROOT e SLSKD_DOWNLOAD_DIR, e queste righe le
# rispecchiano soltanto. La tabella e la colonna audio_file.root_id restano
# perché SQLite non può droppare root_id: è dentro uq_audio_root_path (indice
# interno non droppabile) e in una FK, quindi servirebbe un rebuild di
# audio_file — che ha quattro tabelle figlie. Stessa scelta, e stessa ragione,
# di Track.playlist_id. Le scrive solo app/organize/services/roots.py.
```

- [ ] **Step 6: Test e suite**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/organize/test_roots_derivate.py -v && \
.venv/bin/python -m pytest tests -q
```

Atteso: 5 passed sul nuovo, suite verde.

- [ ] **Step 7: Allineare le radici sul DB reale e verificare la coerenza**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -c "
from app.core.config import settings
from app.db import SessionLocal, engine
from app.organize.services.roots import radici
print('DB:', engine.url)
with SessionLocal() as db:
    for loc, r in radici(db).items():
        print(f'{loc:<8} id={r.id} path={r.path}')
    db.commit()
"
```

Atteso: due righe con gli id **già esistenti** (1 e 2) e i path delle due cartelle. Poi l'invariante di correttezza:

```bash
sqlite3 ~/Develop/DJProject01/backend/data/djassistant.db "
select count(*) from audio_file f join scan_root r on r.id=f.root_id
where (f.location='library') != (r.label='Libreria');"
```

Atteso: `0` — nessun file la cui radice contraddica la sua `location`.

- [ ] **Step 8: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend && \
git commit -m "feat(f3b): le radici si derivano da Settings, scan_root diventa schema morto"
```

---

### Task 3: I filtri passano da `root_id` a `location`

**Files:**
- Modify: `backend/app/organize/routers/issues.py` (righe ~30, ~41, ~51)
- Modify: `backend/app/organize/routers/library.py` (righe ~43, ~67, ~120, ~165)
- Modify: `backend/app/organize/schemas.py`
- Test: `backend/tests/organize/test_filtro_location.py`

**Interfaces:**
- L'API cambia: il query param `root_id: int | None` diventa `location: str | None` su `GET /api/organize/issues` e `GET /api/organize/files`; `IssueRead.root_id` diventa `IssueRead.location`; `FileRead.root_id` diventa `FileRead.location`

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_filtro_location.py`:

```python
"""I filtri dell'API Organize ragionano per collocazione, non per sorgente."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_files_filtra_per_location():
    res = client.get("/api/organize/files", params={"location": "library"})
    assert res.status_code == 200


def test_files_rifiuta_una_location_inventata():
    res = client.get("/api/organize/files", params={"location": "altrove"})
    assert res.status_code == 422


def test_root_id_non_e_piu_un_filtro_riconosciuto():
    """Non deve restare un parametro morto che finge di filtrare."""
    res = client.get("/api/organize/files", params={"root_id": 1})
    assert res.status_code in (200, 422)
    if res.status_code == 200:
        # accettato ma ignorato: verifica che non sia rimasto nella firma
        import inspect

        from app.organize.routers import library

        assert "root_id" not in inspect.signature(library.list_files).parameters
```

- [ ] **Step 2: Lanciarlo e vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_filtro_location.py -v
```

Atteso: FAIL sul filtro `location` (parametro non riconosciuto) e sulla firma.

- [ ] **Step 3: Sostituire nei router**

In `library.py`, il parametro `root_id: int | None = None` diventa:

```python
    location: Literal["inbox", "library"] | None = None,
```

e il filtro (riga ~165):

```python
    if location is not None:
        stmt = stmt.where(AudioFile.location == location)
```

`Literal` dà il 422 gratis su un valore inventato. Stessa sostituzione in `issues.py` (righe ~41 e ~51-52) e nella costruzione di `IssueRead` alla riga ~30 (`root_id=file.root_id` → `location=file.location`), e in `library.py` riga ~67 (`root_id=f.root_id` → `location=f.location`).

In `schemas.py`: `root_id: int` diventa `location: str` nelle due classi (righe ~51 e ~256).

- [ ] **Step 4: Il conteggio delle sorgenti in `library.py`**

Riga ~43, `sources = db.scalar(select(func.count()).select_from(ScanRoot)) or 0` diventa:

```python
    # Le "sorgenti" non sono più righe di tabella: sono le cartelle configurate.
    sources = len(radici(db))
```

con `from app.organize.services.roots import radici` in testa, e via l'import di `ScanRoot`.

- [ ] **Step 5: Test e suite**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/organize/test_filtro_location.py -v && \
.venv/bin/python -m pytest tests -q
```

Atteso: nuovo verde, suite verde. I test che passavano `root_id` come filtro vanno aggiornati a `location`.

- [ ] **Step 6: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend && \
git commit -m "refactor(f3b): i filtri Organize passano da root_id a location"
```

---

### Task 4: Il frontend smette di parlare di sorgenti

**Files:**
- Delete: `frontend/app/organize/sources/page.tsx`, `frontend/components/organize/add-source.tsx`, `frontend/components/organize/source-menu.tsx`
- Modify: `frontend/lib/organize/api.ts`, `frontend/components/organize/index-nav.tsx`, `frontend/lib/organize/i18n/en.ts` e `it.ts`
- Test: `frontend/tests/organize-no-sources.test.ts`

**Prima di iniziare:** leggere `frontend/CLAUDE.md`.

**Ordine voluto: il frontend prima del backend.** Togliere le chiamate prima degli endpoint non rompe niente in nessun istante intermedio; il contrario lascerebbe una UI che chiama rotte inesistenti.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `frontend/tests/organize-no-sources.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { existsSync } from "node:fs";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const api = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");

describe("le sorgenti non sono più un concetto della UI", () => {
  it("la pagina /organize/sources non esiste", () => {
    expect(existsSync(resolve(__dirname, "../app/organize/sources/page.tsx"))).toBe(false);
  });

  it("il client API non espone più le funzioni sulle sorgenti", () => {
    for (const fn of ["listSources", "addSource", "deleteSource", "setRootTarget"]) {
      expect(api).not.toContain(`export function ${fn}`);
    }
  });

  it("nessuna chiamata residua a /sources o /settings/roots", () => {
    expect(api).not.toContain("/sources");
    expect(api).not.toContain("/settings/roots");
  });
});
```

- [ ] **Step 2: Lanciarlo e vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npx vitest run tests/organize-no-sources.test.ts
```

Atteso: tutti e tre falliscono.

- [ ] **Step 3: Trovare chi usa quelle funzioni**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
grep -rn "listSources\|addSource\|deleteSource\|setRootTarget\|/organize/sources" app components lib
```

L'elenco che esce è il perimetro esatto di questo task. **Se compare un file non previsto dal piano, trattalo qui**: la pagina Impostazioni di Organize potrebbe mostrare i target per-radice.

- [ ] **Step 4: Rimuovere**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git rm -r -q frontend/app/organize/sources && \
git rm -q frontend/components/organize/add-source.tsx frontend/components/organize/source-menu.tsx
```

Poi, a mano:
- in `lib/organize/api.ts`: via `listSources`, `addSource`, `deleteSource` (righe ~159-166), `setRootTarget` (riga ~545) e le interfacce `ScanRoot`/`RootTarget` che restano senza usi;
- in `components/organize/index-nav.tsx`: via la voce di menu Sources;
- in `lib/organize/i18n/en.ts` e `it.ts`: via le chiavi della sezione sources. `en.ts` è la fonte di verità e `it.ts` è tipizzato su `typeof en`, quindi una chiave dimenticata in uno dei due è un errore di compilazione — è la rete che rende questa rimozione sicura.

- [ ] **Step 5: Sostituire con la sola informazione utile**

Le due cartelle vanno comunque mostrate da qualche parte. Sono già in Impostazioni di Cratory (`components/settings/config-card.tsx`, che espone `LIBRARY_ROOT` e `SLSKD_DOWNLOAD_DIR`): **non aggiungere una seconda UI**. In `app/organize/page.tsx`, dove oggi si rimanda a Sources, mettere un rimando a `/settings`.

- [ ] **Step 6: Typecheck, lint, build, test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
npx tsc --noEmit && npm run lint && npm run build && npm run test:unit
```

Atteso: tutti verdi, e nella lista delle rotte della build **non** compare `/organize/sources`.

- [ ] **Step 7: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A frontend && \
git commit -m "feat(f3b): via la pagina Sources, le cartelle stanno in Impostazioni"
```

---

### Task 5: Via l'API delle sorgenti

**Files:**
- Delete: `backend/app/organize/routers/sources.py`
- Modify: `backend/app/main.py`, `backend/app/organize/routers/settings.py`, `backend/app/organize/schemas.py`
- Test: `backend/tests/organize/test_api_sources_rimossa.py`

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_api_sources_rimossa.py`:

```python
"""Le sorgenti non sono più un'entità esposta dall'API."""

from app.main import app


def _paths() -> set[str]:
    return {r.path for r in app.routes}


def test_le_rotte_sources_non_esistono_piu():
    paths = _paths()
    assert "/api/organize/sources" not in paths
    assert not any(p.startswith("/api/organize/sources/") for p in paths)


def test_la_rotta_target_per_radice_non_esiste_piu():
    assert "/api/organize/settings/roots/{root_id}/target" not in _paths()


def test_le_altre_rotte_organize_sono_intatte():
    paths = _paths()
    assert "/api/organize/issues" in paths
    assert "/api/organize/plan" in paths
    assert "/api/organize/settings" in paths
```

- [ ] **Step 2: Lanciarlo e vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_api_sources_rimossa.py -v
```

Atteso: i primi due FAIL.

- [ ] **Step 3: Rimuovere il router e l'endpoint dei target**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git rm -q backend/app/organize/routers/sources.py
```

In `backend/app/main.py`: togliere `sources as organize_sources` dall'import e `organize_sources` dalla tupla degli `include_router`.

In `backend/app/organize/routers/settings.py`: togliere l'endpoint `PUT /roots/{root_id}/target` (righe ~51-56), l'import di `ScanRoot` e la lista `roots` costruita alla riga ~22 dentro `SettingsRead`.

In `backend/app/organize/schemas.py`: via `ScanRootCreate`, `ScanRootRead`, `RootTargetRead`, `RootTargetUpdate` e il campo `roots` di `SettingsRead`.

- [ ] **Step 4: Verificare che non resti nulla appeso**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
grep -rn "ScanRootCreate\|ScanRootRead\|RootTarget\|organize_sources" app tests | head
```

Atteso: nessun output.

E il conteggio finale dei riferimenti di dominio:

```bash
grep -rn "ScanRoot\|root_id\|target_root" app | grep -v "services/roots.py" | grep -v "models.py" | grep -v "tools/migrate_organize_db.py"
```

Atteso: **nessun output**. `ScanRoot` sopravvive solo dove è schema morto — il modello, il modulo che lo mantiene, e il controllo FK dello script di migrazione di F2.

- [ ] **Step 5: Suite completa**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: verde. I test che chiamavano `/api/organize/sources` vanno cancellati, non aggiustati: testavano una feature che non esiste più.

- [ ] **Step 6: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend && \
git commit -m "feat(f3b): via l'API delle sorgenti e il target per-radice"
```

---

### Task 6: Verifica di fase

- [ ] **Step 1: Gli invarianti di correttezza sul DB reale**

```bash
sqlite3 ~/Develop/DJProject01/backend/data/djassistant.db "
select 'radici', count(*) from scan_root
union all select 'file con root incoerente', count(*) from audio_file f
    join scan_root r on r.id=f.root_id
    where (f.location='library') != (r.label='Libreria')
union all select 'root_id orfani', count(*) from audio_file f
    where not exists (select 1 from scan_root r where r.id=f.root_id)
union all select 'location=library', count(*) from audio_file where location='library'
union all select 'location=inbox', count(*) from audio_file where location='inbox'
union all select 'asimmetrie track/file', count(*) from tracks t
    where t.primary_file_id is not null
      and not exists (select 1 from audio_file f where f.id=t.primary_file_id and f.track_id=t.id);"
```

Atteso: `radici` **2**, tutti gli altri conteggi di errore **0**, e le due `location` sui valori di F3a (650 / 1128, salvo scan nel frattempo).

- [ ] **Step 2: Suite e frontend**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
cd ../frontend && npm run lint && npm run build && npm run test:unit && npm run test:e2e
```

Atteso: tutti verdi (l'e2e con il fallimento pre-esistente su `/discovery`).

- [ ] **Step 3: Esercitare il percorso che questa fase ha cambiato davvero**

Non basta che le pagine carichino: qui è cambiata **la destinazione di ogni Apply**. Con backend e frontend avviati:

1. Da `/organize` lancia uno scan e verifica che i conteggi non cambino in modo anomalo.
2. Vai su `/organize/plan` e **costruisci un piano**: le destinazioni proposte devono puntare dentro `LIBRARY_ROOT`.
3. Verifica che nessuna destinazione sia finita fuori. **Due conteggi, non uno**: solo le op `MOVE` e `RENAME` portano un path in `after_json` (una `RETAG` ha `{"comment": null}`, e `json_extract` su una chiave assente dà NULL, che in un `NOT LIKE` non conta — il controllo tornerebbe `0` anche senza aver guardato niente).

```bash
sqlite3 ~/Develop/DJProject01/backend/data/djassistant.db "
select 'op con destinazione', count(*) from plan_op o join plan p on p.id=o.plan_id
  where p.status='draft' and o.kind in ('MOVE','RENAME')
union all
select 'fuori da LIBRARY_ROOT', count(*) from plan_op o join plan p on p.id=o.plan_id
  where p.status='draft' and o.kind in ('MOVE','RENAME')
    and json_extract(o.after_json,'\$.path') not like
        (select path || '/%' from scan_root where label='Libreria');"
```

Atteso: la prima riga **maggiore di 0** (altrimenti il controllo è vacuo e non hai verificato nulla: torna al punto 2 e costruisci un piano che contenga davvero degli spostamenti), la seconda **0**.

Se la seconda non è 0, `target_root()` non sta arrivando fino a `render_destination`.

4. Ricontrolla l'invariante dello Step 1 **dopo** lo scan: uno scan non deve creare file con radice incoerente.

- [ ] **Step 4: Aggiornare la spec**

Nella tabella delle fasi, riga **F3**: annotare che è stata eseguita in due tempi, F3a (modello) e F3b (via `scan_root`), e che la rimozione **di schema** — la colonna `audio_file.root_id` e la tabella `scan_root` — è **rimandata**, con il rimando a rivalutarla dopo F4 se lo scanner richiederà comunque un rebuild di `audio_file`.

- [ ] **Step 5: Commit e riepilogo**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && git add -A docs && \
git commit -m "docs(f3b): F3b completata — scan_root fuori dal dominio, schema morto dichiarato"
```

Riporta: conteggio dei test, i valori degli invarianti dello Step 1, e se il piano costruito allo Step 3 puntava tutto dentro `LIBRARY_ROOT`.

---

## Definizione di "F3b completa"

- Nessun riferimento di dominio a `ScanRoot`, `root_id` o `target_root` fuori da `models.py`, `services/roots.py` e lo script di migrazione di F2.
- `GET/POST/DELETE /api/organize/sources` e `PUT /api/organize/settings/roots/{id}/target` non esistono più.
- La pagina `/organize/sources` non esiste; le due cartelle si vedono solo in Impostazioni.
- I filtri dell'API ragionano per `location`.
- `target_root()` restituisce `LIBRARY_ROOT` e le destinazioni di un piano vero ci cadono dentro.
- `scan_root` ha esattamente due righe, allineate alle cartelle, e nessun file ha una radice che contraddica la sua `location`.
- La tabella `scan_root` e la colonna `audio_file.root_id` **esistono ancora nel database** — è corretto e dichiarato: rimandato a dopo F4.
