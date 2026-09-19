# Set manuale, tappa 3 (sequenze, banco, annulla) — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il DJ raggruppa tracce contigue in una sequenza con un nome, la sposta intera, la separa, la parcheggia su un banco fuori dal percorso; e qualunque gesto strutturale si annulla e si ripete.

**Architecture:** Una tabella nuova, `SetlistRevision`, che dopo ogni gesto salva uno snapshot JSON dell'intera struttura (blocchi, righe, alternative, con i loro id). Annullare significa ripristinare lo snapshot precedente: si cancella la struttura e si ricrea dallo snapshot con gli id originali, così i riferimenti del client restano validi. Le sequenze non hanno modello nuovo: sono i `SetlistBlock` già esistenti, finora usati uno solo per set, con `placement` `main` o `bench`.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy 2 (SQLite, migrazioni idempotenti in `db.py`), Pydantic v2, pytest. Next.js 16 App Router, React, Tailwind, vitest + @testing-library/react, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-15-set-builder-workbench.md` ("Tappa 3" per il perimetro, sezione 3 per il modello e le regole di salvataggio/annulla).

## Global Constraints

- Backend: `cd backend && .venv/bin/python -m pytest tests -q` deve restare verde. Baseline a inizio tappa: **2544 passed, 4 deselected**.
- Frontend baseline: **621 test in 102 file**, `npx tsc --noEmit` pulito, `npm run lint` senza errori (4 warning pre-esistenti non correlati), `npm run build` verde, e2e `set-builder.spec.ts` verde.
- Migrazioni: solo dentro `ensure_schema` in `backend/app/db.py`, idempotenti. La tabella nuova la crea `create_all`; la colonna nuova la aggiunge `_migrate_add_model_columns`. Nessun rebuild.
- Errori HTTP: sempre `api_error(status, code, message, **params)`; ogni `code` nuovo tradotto in `frontend/lib/i18n/en.ts` **e** `it.ts` sotto `errors`.
- I set `manual` non passano mai da `assign_roles`, `_reassign_roles`, `recompute_transitions`.
- Ogni mutazione controlla `expected_revision`, muta, salva uno snapshot e committa nella stessa transazione. Un conflitto lascia il database intatto.
- Le righe e i blocchi si identificano per id, mai per posizione.
- Frontend: leggere `frontend/CLAUDE.md`. Nessuna stringa user-facing fuori dai dizionari; chiavi in `en.ts` prima, poi `it.ts`. Spazi fra elementi inline: `{" "}` esplicito.
- Commit in italiano, stile `feat(sets): …`, nessun `Co-Authored-By`. Prima di ogni commit `git status --porcelain`, stage dei soli file del task; revertare `frontend/package-lock.json` e `frontend/tsconfig.json` se risultano modificati.
- Nessuna chiamata AI, nessun pacchetto nuovo.

## Decisione di progetto che si discosta dalla spec

La spec (sezione 3, tabella del modello) dice che `Setlist.revision` sia insieme «controllo di concorrenza e cursore annulla». I due ruoli sono incompatibili e vanno separati, perché insieme aprono un buco silenzioso:

> Il client legge `revision = 5`. Il DJ annulla: la revisione tornerebbe a 4. Fa una modifica nuova: torna a 5, ma lo stato non è più quello di prima. Il client, fermo a 5, si crede aggiornato e la sua mutazione passa il controllo pur basandosi su uno stato che non esiste più.

Quindi: **`Setlist.revision` cresce e basta** — ogni gesto la incrementa, annulla e ripeti compresi — e resta l'unico controllo di concorrenza. Il cursore dell'annulla è una colonna nuova, `Setlist.undo_seq`, che dice a quale snapshot corrisponde lo stato attuale. È l'intento della spec, senza il buco.

## Cosa questa tappa NON fa

Note di coppia e stato «provato», `play_bpm` e percentuale di pitch, durata pianificata, export dedicati, «riempi il varco». Sono le tappe 4-6. L'annulla copre la **struttura** (blocchi, righe, alternative, note di riga), non la selezione, i filtri o l'ascolto.

---

## File structure

| File | Responsabilità |
|---|---|
| `backend/app/models.py` | `SetlistRevision`; `Setlist.undo_seq`; relazione `Setlist.revisions` |
| `backend/app/services/manual_history.py` (nuovo) | Snapshot, ripristino, annulla, ripeti, potatura, accorpamento delle note |
| `backend/app/services/manual_set.py` | Aggancio dello snapshot a ogni mutazione; le mutazioni delle sequenze |
| `backend/app/tools/clean_user_data.py` | `setlist_revisions` in `DATA_TABLES` |
| `backend/app/schemas.py` | `ManualSetOut.can_undo`/`can_redo`; richieste dei blocchi |
| `backend/app/serializers.py` | I due flag nel documento |
| `backend/app/routers/sets.py` | Endpoint di blocchi, banco, annulla e ripeti |
| `backend/tests/test_set_manual_history.py` | Snapshot, ripristino, annulla/ripeti, limite, accorpamento |
| `backend/tests/test_set_manual_blocks.py` | Sequenze e banco |
| `frontend/lib/api/{types,manual-sets}.ts`, `frontend/lib/i18n/{en,it}.ts` | Tipi, client, testi |
| `frontend/components/set-builder/path-panel.tsx` | Selezione multipla, intestazione di sequenza, comandi |
| `frontend/components/set-builder/bench-panel.tsx` (nuovo) | Il banco |
| `frontend/app/sets/manual/page.tsx` | Stato, annulla/ripeti, scorciatoie da tastiera |
| `frontend/tests/set-builder-blocks.test.tsx` (nuovo) | Gesti di sequenze, banco, annulla |
| `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`, `frontend/e2e/set-builder.spec.ts` | Documentazione e verifica |

---

### Task 1: Il modello della cronologia

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/tools/clean_user_data.py`
- Test: `backend/tests/test_set_manual_history.py` (nuovo), `backend/tests/test_clean_user_data.py` (in coda)

**Interfaces:**
- Produces: `SetlistRevision(id, setlist_id, seq, kind, snapshot, created_at, setlist)`; `Setlist.undo_seq: int` (default 0); `Setlist.revisions: list[SetlistRevision]` (cascade all/delete-orphan, ordinata per `seq`).

- [ ] **Step 1: Scrivi i test che falliscono**

`backend/tests/test_set_manual_history.py`:

```python
"""Cronologia del set manuale (tappa 3): snapshot, ripristino, annulla e ripeti."""
import pytest
from sqlalchemy import select

from app.models import Setlist, SetlistBlock, SetlistRevision, SetlistTrack, Track


def test_una_revisione_appartiene_al_suo_set_e_porta_lo_snapshot(db):
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistRevision(setlist_id=s.id, seq=0, kind="create", snapshot={"blocks": [], "rows": []}))
    db.commit()
    db.refresh(s)
    assert s.undo_seq == 0
    assert [r.seq for r in s.revisions] == [0]
    assert s.revisions[0].snapshot == {"blocks": [], "rows": []}


def test_cancellare_il_set_cancella_la_sua_cronologia(db):
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistRevision(setlist_id=s.id, seq=0, kind="create", snapshot={}))
    db.commit()
    db.delete(s)
    db.commit()
    assert db.scalars(select(SetlistRevision)).all() == []
```

In coda a `backend/tests/test_clean_user_data.py`:

```python
def test_pulizia_libreria_svuota_anche_la_cronologia(db_su_file):
    """`setlist_revisions` e' figlia di `setlists`: senza di lei in DATA_TABLES
    la DELETE sulla madre va in IntegrityError con le foreign key accese."""
    s = Setlist(name="M", kind="manual")
    db_su_file.add(s)
    db_su_file.flush()
    db_su_file.add(SetlistRevision(setlist_id=s.id, seq=0, kind="create", snapshot={}))
    db_su_file.commit()

    report = clean_user_data.clean("library", preserve_tokens=True,
                                   include_backups=False, dry_run=False)

    assert report["after"]["setlists"] == 0
    assert db_su_file.execute(
        text("SELECT COUNT(*) FROM setlist_revisions")).scalar_one() == 0
```

Aggiungi `SetlistRevision` agli import di entrambi i file.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_history.py tests/test_clean_user_data.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError: cannot import name 'SetlistRevision'`.

- [ ] **Step 3: Il modello**

In `backend/app/models.py`, dentro `class Setlist`, accanto a `revision`:

```python
    # Cursore della cronologia: a quale snapshot corrisponde lo stato attuale.
    # NON e' `revision`, che cresce e basta e serve solo alla concorrenza: se
    # il cursore tornasse indietro con l'annulla, una modifica successiva
    # riporterebbe `revision` a un valore gia' visto da un client, che si
    # crederebbe aggiornato su uno stato che non esiste piu'.
    undo_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

e fra le relazioni di `Setlist`:

```python
    revisions: Mapped[list["SetlistRevision"]] = relationship(
        back_populates="setlist", cascade="all, delete-orphan",
        order_by="SetlistRevision.seq",
    )
```

Dopo `class SetlistAlternative`:

```python
class SetlistRevision(Base):
    """Uno stato della struttura di un set manuale, per annulla e ripeti.

    `snapshot` contiene blocchi, righe e alternative con i loro id: ripristinare
    significa ricreare esattamente quelle righe, cosi' gli id che il client ha
    in mano restano validi. Non contiene i metadati delle tracce, che vivono in
    `tracks` e non sono mai oggetto dell'annulla.
    """

    __tablename__ = "setlist_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    setlist_id: Mapped[int] = mapped_column(ForeignKey("setlists.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    # Etichetta del gesto ("rows", "note:12", "block"…): serve ad accorpare gli
    # edit consecutivi della stessa nota in una revisione sola.
    kind: Mapped[str] = mapped_column(String)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    setlist: Mapped[Setlist] = relationship(back_populates="revisions")
```

In `backend/app/tools/clean_user_data.py`, `DATA_TABLES` guadagna `"setlist_revisions"` subito dopo `"setlist_alternatives"` (figlie prima delle madri).

- [ ] **Step 4: Esegui e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_history.py tests/test_clean_user_data.py -q -p no:cacheprovider` → verdi.

- [ ] **Step 5: Suite completa e commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → 2547 passed.

```bash
git add backend/app/models.py backend/app/tools/clean_user_data.py backend/tests/test_set_manual_history.py backend/tests/test_clean_user_data.py
git commit -m "feat(sets): il modello della cronologia del set manuale"
```

---

### Task 2: Snapshot e ripristino

**Files:**
- Create: `backend/app/services/manual_history.py`
- Test: `backend/tests/test_set_manual_history.py` (in coda)

**Interfaces:**
- Consumes: Task 1.
- Produces:

```python
MAX_REVISIONS = 50

def snapshot_of(setlist: Setlist) -> dict
    """Struttura corrente: {"blocks": [...], "rows": [...], "alts": [...]},
    ogni voce con il proprio id. Deterministico e ordinato, così due snapshot
    uguali confrontano uguali."""

def restore(db: Session, setlist: Setlist, snapshot: dict) -> None
    """Riporta la struttura a `snapshot`: cancella alternative, righe e blocchi
    e li ricrea con gli id originali. Non committa, non tocca `revision`."""

def record(db: Session, setlist: Setlist, kind: str) -> None
    """Salva lo stato corrente come revisione successiva al cursore, scarta il
    ramo «ripeti», accorpa un `kind` uguale a quello dell'ultima revisione e
    pota oltre MAX_REVISIONS. Non committa."""
```

- [ ] **Step 1: Scrivi i test che falliscono**

In coda a `backend/tests/test_set_manual_history.py`:

```python
from app.services.manual_history import MAX_REVISIONS, record, restore, snapshot_of


def _set_con_struttura(db):
    """Un set con due blocchi, tre righe (una varco) e una alternativa."""
    from app.models import SetlistAlternative
    t1 = Track(source_type="spotify", title="T1", has_local_file=True)
    t2 = Track(source_type="spotify", title="T2", has_local_file=True)
    db.add_all([t1, t2])
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    b1 = SetlistBlock(setlist_id=s.id, placement="main", position=1, name="Apertura")
    b2 = SetlistBlock(setlist_id=s.id, placement="bench", position=1)
    db.add_all([b1, b2])
    db.flush()
    r1 = SetlistTrack(setlist_id=s.id, block_id=b1.id, position=1, track_id=t1.id, note="ciao")
    r2 = SetlistTrack(setlist_id=s.id, block_id=b1.id, position=2, slot_kind="gap")
    r3 = SetlistTrack(setlist_id=s.id, block_id=b2.id, position=1, track_id=t2.id)
    db.add_all([r1, r2, r3])
    db.flush()
    db.add(SetlistAlternative(setlist_track_id=r1.id, track_id=t2.id, position=1))
    db.commit()
    db.refresh(s)
    return s, (t1, t2), (b1, b2), (r1, r2, r3)


def test_lo_snapshot_descrive_tutta_la_struttura(db):
    s, _, (b1, b2), (r1, r2, r3) = _set_con_struttura(db)
    snap = snapshot_of(s)
    assert [b["id"] for b in snap["blocks"]] == sorted([b1.id, b2.id])
    assert {b["placement"] for b in snap["blocks"]} == {"main", "bench"}
    assert [r["id"] for r in snap["rows"]] == sorted([r1.id, r2.id, r3.id])
    assert any(r["slot_kind"] == "gap" and r["track_id"] is None for r in snap["rows"])
    assert any(r["note"] == "ciao" for r in snap["rows"])
    assert len(snap["alts"]) == 1


def test_ripristinare_riporta_la_struttura_con_gli_stessi_id(db):
    s, (t1, t2), (b1, b2), (r1, r2, r3) = _set_con_struttura(db)
    prima = snapshot_of(s)
    ids_prima = {"blocks": [b.id for b in s.blocks], "rows": sorted(r.id for r in s.tracks)}

    # Sfascia: togli una riga, rinomina un blocco, sposta l'altra riga.
    s.tracks.remove(next(r for r in s.tracks if r.id == r2.id))
    next(b for b in s.blocks if b.id == b1.id).name = "Altro"
    db.commit()
    db.refresh(s)
    assert sorted(r.id for r in s.tracks) != ids_prima["rows"]

    restore(db, s, prima)
    db.commit()
    db.refresh(s)
    assert sorted(r.id for r in s.tracks) == ids_prima["rows"]
    assert [b.id for b in s.blocks] == ids_prima["blocks"]
    assert next(b for b in s.blocks if b.id == b1.id).name == "Apertura"
    assert next(r for r in s.tracks if r.id == r1.id).note == "ciao"
    assert len(next(r for r in s.tracks if r.id == r1.id).alternatives) == 1


def test_lo_snapshot_di_uno_stato_ripristinato_e_identico(db):
    """Se ripristinare non fosse fedele, i due snapshot divergerebbero."""
    s, *_ = _set_con_struttura(db)
    prima = snapshot_of(s)
    restore(db, s, prima)
    db.commit()
    db.refresh(s)
    assert snapshot_of(s) == prima


def test_record_scarta_il_ramo_ripeti(db):
    s, *_ = _set_con_struttura(db)
    for i in range(3):
        record(db, s, kind=f"g{i}")
        s.undo_seq = s.revisions[-1].seq
        db.commit()
    assert [r.seq for r in s.revisions] == [0, 1, 2]

    s.undo_seq = 0  # come dopo due annulla
    db.commit()
    record(db, s, kind="nuovo")
    db.commit()
    db.refresh(s)
    assert [r.seq for r in s.revisions] == [0, 1]
    assert s.revisions[-1].kind == "nuovo"


def test_record_accorpa_due_gesti_dello_stesso_tipo(db):
    s, *_ = _set_con_struttura(db)
    record(db, s, kind="note:7")
    s.undo_seq = s.revisions[-1].seq
    db.commit()
    quante = len(s.revisions)
    record(db, s, kind="note:7")
    db.commit()
    db.refresh(s)
    assert len(s.revisions) == quante  # sovrascritta, non aggiunta
    record(db, s, kind="note:8")
    db.commit()
    db.refresh(s)
    assert len(s.revisions) == quante + 1  # riga diversa: revisione nuova


def test_record_pota_oltre_il_limite(db):
    s, *_ = _set_con_struttura(db)
    for i in range(MAX_REVISIONS + 10):
        record(db, s, kind=f"g{i}")
        s.undo_seq = s.revisions[-1].seq
        db.commit()
    db.refresh(s)
    assert len(s.revisions) == MAX_REVISIONS
    # Le piu' vecchie sono quelle cadute.
    assert s.revisions[0].seq == s.revisions[-1].seq - (MAX_REVISIONS - 1)
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_history.py -q -p no:cacheprovider`
Expected: FAIL con `ModuleNotFoundError: app.services.manual_history`.

- [ ] **Step 3: Implementa**

```python
# backend/app/services/manual_history.py
"""Cronologia del set manuale: snapshot della struttura, ripristino, potatura.

Lo snapshot e' la struttura intera con gli id: ripristinarlo significa ricreare
esattamente quelle righe, cosi' gli id che il client ha in mano restano validi.
Cancella-e-ricrea invece di un confronto incrementale: un set manuale ha decine
di righe, non migliaia, e questa forma e' molto piu' facile da verificare.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistAlternative, SetlistBlock, SetlistRevision, SetlistTrack

MAX_REVISIONS = 50


def snapshot_of(setlist: Setlist) -> dict:
    """Struttura corrente, ordinata per id: due stati uguali danno snapshot uguali."""
    return {
        "blocks": [
            {"id": b.id, "name": b.name, "placement": b.placement, "position": b.position}
            for b in sorted(setlist.blocks, key=lambda b: b.id)
        ],
        "rows": [
            {"id": r.id, "block_id": r.block_id, "position": r.position,
             "slot_kind": r.slot_kind, "track_id": r.track_id, "note": r.note}
            for r in sorted(setlist.tracks, key=lambda r: r.id)
        ],
        "alts": [
            {"id": a.id, "setlist_track_id": a.setlist_track_id, "track_id": a.track_id,
             "position": a.position, "note": a.note}
            for r in setlist.tracks for a in sorted(r.alternatives, key=lambda a: a.id)
        ],
    }


def restore(db: Session, setlist: Setlist, snapshot: dict) -> None:
    """Riporta la struttura allo snapshot. Non committa, non tocca `revision`."""
    # Figlie prima delle madri: le alternative puntano alle righe, le righe ai blocchi.
    for row in list(setlist.tracks):
        row.alternatives.clear()
    setlist.tracks.clear()
    setlist.blocks.clear()
    db.flush()

    for b in snapshot.get("blocks", []):
        db.add(SetlistBlock(id=b["id"], setlist_id=setlist.id, name=b["name"],
                            placement=b["placement"], position=b["position"]))
    db.flush()
    for r in snapshot.get("rows", []):
        db.add(SetlistTrack(id=r["id"], setlist_id=setlist.id, block_id=r["block_id"],
                            position=r["position"], slot_kind=r["slot_kind"],
                            track_id=r["track_id"], note=r["note"]))
    db.flush()
    for a in snapshot.get("alts", []):
        db.add(SetlistAlternative(id=a["id"], setlist_track_id=a["setlist_track_id"],
                                  track_id=a["track_id"], position=a["position"], note=a["note"]))
    db.flush()
    db.refresh(setlist)


def record(db: Session, setlist: Setlist, kind: str) -> None:
    """Salva lo stato corrente come revisione dopo il cursore. Non committa."""
    revisioni = sorted(setlist.revisions, key=lambda r: r.seq)
    # Il ramo «ripeti» muore appena si fa qualcosa di nuovo dopo un annulla.
    for vecchia in [r for r in revisioni if r.seq > setlist.undo_seq]:
        setlist.revisions.remove(vecchia)
    revisioni = sorted(setlist.revisions, key=lambda r: r.seq)

    ultima = revisioni[-1] if revisioni else None
    if ultima is not None and ultima.kind == kind and ultima.seq == setlist.undo_seq:
        # Stesso gesto di fila (la stessa nota mentre si scrive): una revisione
        # sola, altrimenti annullare tornerebbe indietro di un carattere.
        ultima.snapshot = snapshot_of(setlist)
        return

    seq = (ultima.seq + 1) if ultima is not None else 0
    nuova = SetlistRevision(setlist_id=setlist.id, seq=seq, kind=kind,
                            snapshot=snapshot_of(setlist))
    db.add(nuova)
    setlist.revisions.append(nuova)
    setlist.undo_seq = seq

    troppe = len(setlist.revisions) - MAX_REVISIONS
    if troppe > 0:
        for vecchia in sorted(setlist.revisions, key=lambda r: r.seq)[:troppe]:
            setlist.revisions.remove(vecchia)
    db.flush()
```

Nota per chi implementa: `record` imposta `undo_seq` da sé; i test del Task 2 che lo impostano a mano stanno simulando l'annulla, che arriva nel Task 3.

- [ ] **Step 4: Esegui i test**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_history.py -q -p no:cacheprovider` → verdi.

Poi dimostra che mordono: togli `db.flush()` dopo `setlist.blocks.clear()` in `restore` e verifica che `test_ripristinare_riporta_la_struttura_con_gli_stessi_id` fallisca (senza il flush, SQLAlchemy prova a inserire i blocchi ricreati prima di aver cancellato i vecchi e viola la chiave primaria). Ripristina il flush.

- [ ] **Step 5: Suite completa e commit**

```bash
git add backend/app/services/manual_history.py backend/tests/test_set_manual_history.py
git commit -m "feat(sets): snapshot e ripristino della struttura del set manuale"
```

---

### Task 3: Annulla e ripeti nel servizio

**Files:**
- Modify: `backend/app/services/manual_set.py`
- Test: `backend/tests/test_set_manual_history.py` (in coda)

**Interfaces:**
- Consumes: Task 2 (`record`, `restore`, `snapshot_of`).
- Produces:

```python
def undo(db, setlist_id, *, expected_revision) -> Setlist
def redo(db, setlist_id, *, expected_revision) -> Setlist
def can_undo(setlist) -> bool   # esiste una revisione prima del cursore
def can_redo(setlist) -> bool   # esiste una revisione dopo il cursore
```

`_commit_bumped` guadagna un parametro `kind: str` e chiama `record` prima del commit. `create_manual_set` salva la revisione 0 (il set vuoto), altrimenti la prima mutazione non sarebbe annullabile. `NothingToUndo`/`NothingToRedo` (sottoclassi di `ManualSetError`) per i due estremi.

- [ ] **Step 1: Scrivi i test**

In coda a `backend/tests/test_set_manual_history.py`:

```python
from app.services.manual_set import (
    NothingToRedo, NothingToUndo, add_alternatives, create_manual_set, insert_rows,
    path_rows, redo, remove_row, undo, update_row_note,
)


def _tre_tracce(db):
    out = []
    for i in range(3):
        t = Track(source_type="spotify", title=f"T{i}", bpm=124.0, duration_seconds=300,
                  has_local_file=True)
        db.add(t)
        out.append(t)
    db.commit()
    return out


def test_annulla_riporta_il_percorso_a_prima(db):
    t = _tre_tracce(db)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[1].id], gap=False, after_row_id=None)
    assert [r.track_id for r in path_rows(s)] == [t[0].id, t[1].id]

    s = undo(db, s.id, expected_revision=2)
    assert [r.track_id for r in path_rows(s)] == [t[0].id]
    assert s.revision == 3  # la revisione CRESCE anche annullando


def test_ripeti_rimette_quello_che_si_era_annullato(db):
    t = _tre_tracce(db)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    s = undo(db, s.id, expected_revision=1)
    assert path_rows(s) == []
    s = redo(db, s.id, expected_revision=2)
    assert [r.track_id for r in path_rows(s)] == [t[0].id]


def test_una_riga_annullata_torna_con_lo_stesso_id(db):
    t = _tre_tracce(db)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    id_originale = path_rows(s)[0].id
    s = remove_row(db, s.id, id_originale, expected_revision=1)
    assert path_rows(s) == []
    s = undo(db, s.id, expected_revision=2)
    assert path_rows(s)[0].id == id_originale  # il client puo' ancora riferirla


def test_annulla_ripristina_anche_le_alternative(db):
    t = _tre_tracce(db)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    row = path_rows(s)[0]
    s = add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[t[1].id])
    assert len(path_rows(s)[0].alternatives) == 1
    s = undo(db, s.id, expected_revision=2)
    assert path_rows(s)[0].alternatives == []


def test_una_modifica_dopo_annulla_chiude_il_ripeti(db):
    t = _tre_tracce(db)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    s = undo(db, s.id, expected_revision=1)
    s = insert_rows(db, s.id, expected_revision=2, track_ids=[t[1].id], gap=False, after_row_id=None)
    with pytest.raises(NothingToRedo):
        redo(db, s.id, expected_revision=3)


def test_agli_estremi_annulla_e_ripeti_si_rifiutano(db):
    s = create_manual_set(db, name="M", playlist_id=None)
    with pytest.raises(NothingToUndo):
        undo(db, s.id, expected_revision=0)
    with pytest.raises(NothingToRedo):
        redo(db, s.id, expected_revision=0)


def test_scrivere_la_stessa_nota_due_volte_si_annulla_in_un_colpo(db):
    t = _tre_tracce(db)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    row = path_rows(s)[0]
    s = update_row_note(db, s.id, row.id, expected_revision=1, note="pri")
    s = update_row_note(db, s.id, row.id, expected_revision=2, note="primo giro")
    s = undo(db, s.id, expected_revision=3)
    assert path_rows(s)[0].note is None  # non "pri": i due edit sono una revisione sola


def test_la_revisione_sbagliata_non_annulla(db):
    t = _tre_tracce(db)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    from app.services.manual_set import RevisionConflict
    with pytest.raises(RevisionConflict):
        undo(db, s.id, expected_revision=0)
    assert len(path_rows(s)) == 1
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_history.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError` su `undo`.

- [ ] **Step 3: Implementa**

In `backend/app/services/manual_set.py`, importa `from app.services.manual_history import record, restore` e aggiungi le eccezioni:

```python
class NothingToUndo(ManualSetError):
    pass


class NothingToRedo(ManualSetError):
    pass
```

`_commit_bumped` diventa:

```python
def _commit_bumped(db: Session, setlist: Setlist, kind: str) -> Setlist:
    """Incrementa la revisione, salva lo snapshot e committa, in una transazione.
    `kind` etichetta il gesto: due gesti uguali di fila si accorpano in una
    revisione sola (vedi manual_history.record)."""
    setlist.revision += 1
    record(db, setlist, kind)
    db.commit()
    return get_setlist(db, setlist.id)
```

Ogni chiamante passa la propria etichetta: `insert_rows` → `"rows"`, `move_row` → `"move"`, `remove_row` → `"remove"`, `update_row_note` → `f"note:{row.id}"`, `add_alternatives` → `"alts"`, `remove_alternative` → `"alts"`, `choose_alternative` → `"choose"`.

`create_manual_set` salva la revisione iniziale prima di committare, così la prima mutazione è annullabile:

```python
    setlist = Setlist(name=clean, kind="manual", source_playlist_id=playlist_id, generated_by="manual")
    db.add(setlist)
    db.flush()
    record(db, setlist, "create")  # la revisione 0 e' il set vuoto
    db.commit()
```

In fondo al file:

```python
def can_undo(setlist: Setlist) -> bool:
    return any(r.seq < setlist.undo_seq for r in setlist.revisions)


def can_redo(setlist: Setlist) -> bool:
    return any(r.seq > setlist.undo_seq for r in setlist.revisions)


def _muovi_cursore(db: Session, setlist_id: int, expected_revision: int, avanti: bool) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    candidate = [r for r in setlist.revisions
                 if (r.seq > setlist.undo_seq if avanti else r.seq < setlist.undo_seq)]
    if not candidate:
        raise NothingToRedo("Nothing to redo") if avanti else NothingToUndo("Nothing to undo")
    bersaglio = min(candidate, key=lambda r: r.seq) if avanti else max(candidate, key=lambda r: r.seq)
    restore(db, setlist, bersaglio.snapshot)
    setlist.undo_seq = bersaglio.seq
    # La revisione cresce anche qui: annullare E' una modifica, e un client
    # fermo alla precedente deve vedersi rifiutare la sua mutazione.
    setlist.revision += 1
    db.commit()
    return get_setlist(db, setlist.id)


def undo(db: Session, setlist_id: int, *, expected_revision: int) -> Setlist:
    return _muovi_cursore(db, setlist_id, expected_revision, avanti=False)


def redo(db: Session, setlist_id: int, *, expected_revision: int) -> Setlist:
    return _muovi_cursore(db, setlist_id, expected_revision, avanti=True)
```

- [ ] **Step 4: Esegui e verifica**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_history.py tests/test_set_manual_service.py tests/test_set_manual_alternatives.py tests/test_set_manual_reserve.py -q -p no:cacheprovider` → verdi.
Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/manual_set.py backend/tests/test_set_manual_history.py
git commit -m "feat(sets): annulla e ripeti sul set manuale"
```

---

### Task 4: Le sequenze nel servizio

**Files:**
- Modify: `backend/app/services/manual_set.py`
- Test: `backend/tests/test_set_manual_blocks.py` (nuovo)

**Interfaces:**
- Produces:

```python
class BlockNotFound(ManualSetError): ...

def blocks_of(setlist, placement: str) -> list[SetlistBlock]   # ordinati per position
def group_rows(db, setlist_id, *, expected_revision, row_ids: list[int], name: str | None) -> Setlist
    """Raggruppa righe CONTIGUE dello stesso blocco in una sequenza nuova, al
    loro posto. Righe non contigue, di blocchi diversi o meno di due: rifiuto."""
def rename_block(db, setlist_id, block_id, *, expected_revision, name: str | None) -> Setlist
def move_block(db, setlist_id, block_id, *, expected_revision, position: int,
               to_bench: bool | None = None) -> Setlist
def split_block(db, setlist_id, block_id, *, expected_revision) -> Setlist
    """Scioglie la sequenza: le righe restano, nell'ordine, nel blocco che la
    precede (o nel primo blocco `main` se era la prima)."""
```

- [ ] **Step 1: Scrivi i test**

`backend/tests/test_set_manual_blocks.py`:

```python
"""Sequenze e banco del set manuale (tappa 3)."""
import pytest

from app.models import Track
from app.services.manual_set import (
    BlockNotFound, ManualSetError, blocks_of, create_manual_set, group_rows, insert_rows,
    load_manual_set, move_block, path_rows, rename_block, split_block,
)


def _set_con_quattro(db):
    tracce = []
    for i in range(4):
        t = Track(source_type="spotify", title=f"T{i}", bpm=124.0, duration_seconds=300,
                  has_local_file=True)
        db.add(t)
        tracce.append(t)
    db.commit()
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t.id for t in tracce],
                    gap=False, after_row_id=None)
    return s, tracce


def test_raggruppa_due_righe_contigue(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[1].id, righe[2].id],
                   name="Salita")
    main = blocks_of(s, "main")
    assert len(main) == 3                       # prima · nuova · dopo
    assert main[1].name == "Salita"
    assert [r.track_id for r in main[1].rows] == [t[1].id, t[2].id]
    # L'ordine del percorso non cambia: raggruppare non sposta nulla.
    assert [r.track_id for r in path_rows(s)] == [x.id for x in t]


def test_un_raggruppamento_rifiutato_non_lascia_niente_a_meta(db):
    """Verifica dichiarata dalla spec: «un comando fallito non lascia meta'
    spostamento». Il rifiuto arriva prima di toccare qualunque cosa."""
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    blocchi_prima = [(b.id, b.name, b.position) for b in blocks_of(s, "main")]
    with pytest.raises(ManualSetError):
        group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[2].id], name=None)
    db.expire_all()
    s = load_manual_set(db, s.id)
    assert [(b.id, b.name, b.position) for b in blocks_of(s, "main")] == blocchi_prima
    assert [r.track_id for r in path_rows(s)] == [x.id for x in t]
    assert s.revision == 1  # nessuna revisione bruciata da un comando rifiutato


def test_non_si_raggruppa_una_riga_sola(db):
    s, t = _set_con_quattro(db)
    with pytest.raises(ManualSetError):
        group_rows(db, s.id, expected_revision=1, row_ids=[path_rows(s)[0].id], name=None)


def test_rinomina_una_sequenza(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[1].id], name="A")
    blocco = blocks_of(s, "main")[0]
    s = rename_block(db, s.id, blocco.id, expected_revision=2, name="  Apertura  ")
    assert blocks_of(s, "main")[0].name == "Apertura"
    s = rename_block(db, s.id, blocco.id, expected_revision=3, name="")
    assert blocks_of(s, "main")[0].name is None  # vuoto = senza nome


def test_sposta_una_sequenza_intera_conservando_l_ordine_interno(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[2].id, righe[3].id], name="Coda")
    coda = next(b for b in blocks_of(s, "main") if b.name == "Coda")
    s = move_block(db, s.id, coda.id, expected_revision=2, position=1)
    assert [r.track_id for r in path_rows(s)] == [t[2].id, t[3].id, t[0].id, t[1].id]


def test_parcheggia_una_sequenza_sul_banco_e_la_riprende(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[1].id], name="Idea")
    idea = next(b for b in blocks_of(s, "main") if b.name == "Idea")

    s = move_block(db, s.id, idea.id, expected_revision=2, position=1, to_bench=True)
    assert [b.name for b in blocks_of(s, "bench")] == ["Idea"]
    assert [r.track_id for r in path_rows(s)] == [t[2].id, t[3].id]  # fuori dal percorso

    s = move_block(db, s.id, idea.id, expected_revision=3, position=1, to_bench=False)
    assert blocks_of(s, "bench") == []
    assert [r.track_id for r in path_rows(s)] == [t[0].id, t[1].id, t[2].id, t[3].id]


def test_separare_una_sequenza_lascia_le_righe_in_ordine(db):
    s, t = _set_con_quattro(db)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[1].id, righe[2].id], name="X")
    x = next(b for b in blocks_of(s, "main") if b.name == "X")
    s = split_block(db, s.id, x.id, expected_revision=2)
    assert all(b.name != "X" for b in blocks_of(s, "main"))
    assert [r.track_id for r in path_rows(s)] == [x.id for x in t]


def test_una_sequenza_di_un_altro_set_non_si_tocca(db):
    s, t = _set_con_quattro(db)
    altro = create_manual_set(db, name="Altro", playlist_id=None)
    righe = path_rows(s)
    s = group_rows(db, s.id, expected_revision=1, row_ids=[righe[0].id, righe[1].id], name="A")
    blocco = blocks_of(s, "main")[0]
    with pytest.raises(BlockNotFound):
        rename_block(db, altro.id, blocco.id, expected_revision=0, name="Rubato")
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_blocks.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError` su `group_rows`.

- [ ] **Step 3: Implementa**

In `backend/app/services/manual_set.py`:

```python
class BlockNotFound(ManualSetError):
    pass


def blocks_of(setlist: Setlist, placement: str) -> list[SetlistBlock]:
    return sorted((b for b in setlist.blocks if b.placement == placement),
                  key=lambda b: b.position)


def _block_of(setlist: Setlist, block_id: int) -> SetlistBlock:
    for block in setlist.blocks:
        if block.id == block_id:
            return block
    raise BlockNotFound("Block not found")


def _renumber_blocks(blocks: list[SetlistBlock]) -> None:
    for i, block in enumerate(blocks, start=1):
        block.position = i


def group_rows(db: Session, setlist_id: int, *, expected_revision: int,
               row_ids: list[int], name: str | None) -> Setlist:
    """Raggruppa righe contigue dello stesso blocco in una sequenza nuova, al
    loro posto: l'ordine del percorso non cambia, cambia come e' diviso."""
    if len(row_ids) < 2:
        raise ManualSetError("A sequence needs at least two rows")
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    righe = [_row_of(setlist, rid) for rid in row_ids]
    blocchi = {r.block_id for r in righe}
    if len(blocchi) != 1 or None in blocchi:
        raise ManualSetError("Rows must belong to one and the same block")
    origine = _block_of(setlist, righe[0].block_id)
    tutte = sorted((r for r in setlist.tracks if r.block_id == origine.id),
                   key=lambda r: r.position)
    indici = sorted(tutte.index(r) for r in righe)
    if indici != list(range(indici[0], indici[0] + len(indici))):
        raise ManualSetError("Rows must be contiguous")

    prima = tutte[:indici[0]]
    gruppo = [tutte[i] for i in indici]
    dopo = tutte[indici[-1] + 1:]

    fratelli = blocks_of(setlist, origine.placement)
    at = fratelli.index(origine)

    def nuovo_blocco(sue_righe: list[SetlistTrack], nome: str | None) -> SetlistBlock:
        blocco = SetlistBlock(setlist_id=setlist.id, placement=origine.placement,
                              name=nome, position=0)
        db.add(blocco)
        setlist.blocks.append(blocco)
        db.flush()
        for r in sue_righe:
            r.block_id = blocco.id
        _renumber(sue_righe)
        return blocco

    # Il blocco di origine si spezza in tre: cio' che precede (resta suo), il
    # gruppo (blocco nuovo, col nome), cio' che segue (blocco nuovo senza nome).
    # Ricostruito come lista, non a colpi di slice annidati: qui un indice
    # sbagliato riordinerebbe il percorso in silenzio.
    sostituzione: list[SetlistBlock] = []
    if prima:
        _renumber(prima)
        sostituzione.append(origine)
    sostituzione.append(nuovo_blocco(gruppo, (name or "").strip() or None))
    if dopo:
        sostituzione.append(nuovo_blocco(dopo, None))
    if not prima:
        # Il blocco di origine e' rimasto vuoto: sciolto, non lasciato in giro.
        setlist.blocks.remove(origine)

    _renumber_blocks(fratelli[:at] + sostituzione + fratelli[at + 1:])
    return _commit_bumped(db, setlist, "block")


def rename_block(db: Session, setlist_id: int, block_id: int, *, expected_revision: int,
                 name: str | None) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    block = _block_of(setlist, block_id)
    block.name = (name or "").strip() or None
    return _commit_bumped(db, setlist, "block")


def move_block(db: Session, setlist_id: int, block_id: int, *, expected_revision: int,
               position: int, to_bench: bool | None = None) -> Setlist:
    """Sposta la sequenza intera: l'ordine interno non si tocca mai."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    block = _block_of(setlist, block_id)
    destinazione = block.placement if to_bench is None else ("bench" if to_bench else "main")
    origine = blocks_of(setlist, block.placement)
    if destinazione != block.placement:
        origine = [b for b in origine if b.id != block.id]
        _renumber_blocks(origine)
        block.placement = destinazione
        fratelli = [b for b in blocks_of(setlist, destinazione) if b.id != block.id]
    else:
        fratelli = [b for b in origine if b.id != block.id]
    if not 1 <= position <= len(fratelli) + 1:
        raise ManualSetError(f"Position {position} out of range 1..{len(fratelli) + 1}")
    fratelli.insert(position - 1, block)
    _renumber_blocks(fratelli)
    return _commit_bumped(db, setlist, "block")


def split_block(db: Session, setlist_id: int, block_id: int, *, expected_revision: int) -> Setlist:
    """Scioglie la sequenza: le righe passano al blocco che la precede, in coda,
    nell'ordine che avevano. Se era la prima, vanno in testa a quella dopo."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    block = _block_of(setlist, block_id)
    fratelli = blocks_of(setlist, block.placement)
    if len(fratelli) == 1:
        raise ManualSetError("The only sequence cannot be split")
    at = fratelli.index(block)
    ospite = fratelli[at - 1] if at > 0 else fratelli[1]
    mie = sorted((r for r in setlist.tracks if r.block_id == block.id), key=lambda r: r.position)
    sue = sorted((r for r in setlist.tracks if r.block_id == ospite.id), key=lambda r: r.position)
    unite = (sue + mie) if at > 0 else (mie + sue)
    for r in mie:
        r.block_id = ospite.id
    _renumber(unite)
    setlist.blocks.remove(block)
    _renumber_blocks([b for b in fratelli if b.id != block.id])
    return _commit_bumped(db, setlist, "block")
```

- [ ] **Step 4: Esegui e verifica**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_blocks.py -q -p no:cacheprovider` → verdi.
Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde. In particolare `main_block` (tappa 1) deve continuare a funzionare: crea il primo blocco `main` se non esiste, e ora i blocchi possono essere più d'uno — verifica che `insert_rows` continui a inserire nel **primo** blocco `main`, non in uno a caso.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/manual_set.py backend/tests/test_set_manual_blocks.py
git commit -m "feat(sets): sequenze e banco del set manuale"
```

---

### Task 5: API

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/serializers.py`, `backend/app/routers/sets.py`
- Test: `backend/tests/test_set_manual_api.py` (in coda)

**Interfaces:**
- Produces (HTTP), tutti su `ManualSetOut`:
  - `POST /api/sets/{id}/blocks` body `{expected_revision, row_ids, name?}` — raggruppa
  - `PATCH /api/sets/{id}/blocks/{block_id}` body `{expected_revision, name}` — rinomina
  - `POST /api/sets/{id}/blocks/{block_id}/move` body `{expected_revision, position, to_bench?}`
  - `POST /api/sets/{id}/blocks/{block_id}/split` body `{expected_revision}`
  - `POST /api/sets/{id}/undo` e `POST /api/sets/{id}/redo` body `{expected_revision}`
  - `ManualSetOut` guadagna `can_undo`, `can_redo` e i blocchi `bench` in `blocks` (già ci sono: `placement` li distingue)
  - Codici errore nuovi: `set_block_not_found` (404), `set_nothing_to_undo` (409), `set_nothing_to_redo` (409)

- [ ] **Step 1: Scrivi i test** (in coda a `test_set_manual_api.py`)

```python
def test_sequenze_e_banco_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=4)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [x.id for x in t]}).json()
    righe = _rows(doc)

    r = client.post(f"/api/sets/{sid}/blocks", json={
        "expected_revision": 1, "row_ids": [righe[1]["id"], righe[2]["id"]], "name": "Salita"})
    assert r.status_code == 200, r.text
    doc = r.json()
    main = [b for b in doc["blocks"] if b["placement"] == "main"]
    assert [b["name"] for b in main] == [None, "Salita", None]

    blocco = main[1]["id"]
    r = client.post(f"/api/sets/{sid}/blocks/{blocco}/move",
                    json={"expected_revision": 2, "position": 1, "to_bench": True})
    doc = r.json()
    assert [b["name"] for b in doc["blocks"] if b["placement"] == "bench"] == ["Salita"]
    assert [x["track"]["id"] for x in _rows(doc)] == [t[0].id, t[3].id]

    r = client.patch(f"/api/sets/{sid}/blocks/{blocco}", json={"expected_revision": 3, "name": "Idea"})
    assert [b["name"] for b in r.json()["blocks"] if b["placement"] == "bench"] == ["Idea"]

    r = client.patch(f"/api/sets/{sid}/blocks/999999", json={"expected_revision": 4, "name": "X"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "set_block_not_found"


def test_annulla_e_ripeti_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=3)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id]}).json()
    assert doc["can_undo"] is True and doc["can_redo"] is False

    r = client.post(f"/api/sets/{sid}/undo", json={"expected_revision": 1})
    doc = r.json()
    assert _rows(doc) == []
    assert doc["can_undo"] is False and doc["can_redo"] is True
    assert doc["revision"] == 2  # cresce anche annullando

    r = client.post(f"/api/sets/{sid}/undo", json={"expected_revision": 2})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "set_nothing_to_undo"

    r = client.post(f"/api/sets/{sid}/redo", json={"expected_revision": 2})
    assert [x["track"]["id"] for x in _rows(r.json())] == [t[0].id]

    r = client.post(f"/api/sets/{sid}/redo", json={"expected_revision": 3})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "set_nothing_to_redo"
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_api.py -q -p no:cacheprovider` → FAIL (404 sugli endpoint, `KeyError: 'can_undo'`).

- [ ] **Step 3: Schemi**

In `backend/app/schemas.py`, accanto agli altri del set manuale:

```python
class BlockGroupRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    row_ids: list[int] = Field(min_length=2, max_length=200)
    name: str | None = Field(default=None, max_length=120)


class BlockRenameRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    name: str | None = Field(default=None, max_length=120)


class BlockMoveRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    position: int = Field(ge=1)
    to_bench: bool | None = None


class HistoryStepRequest(BaseModel):
    expected_revision: int = Field(ge=0)
```

`ManualSetOut` guadagna, dopo `reserve`:

```python
    can_undo: bool = False
    can_redo: bool = False
```

- [ ] **Step 4: Serializer**

In `manual_set_out`, importa `can_redo`, `can_undo` da `app.services.manual_set` e passali:

```python
        can_undo=can_undo(setlist), can_redo=can_redo(setlist),
```

- [ ] **Step 5: Endpoint**

In `backend/app/routers/sets.py`, aggiungi gli import (`BlockGroupRequest`, `BlockMoveRequest`, `BlockRenameRequest`, `HistoryStepRequest`; `BlockNotFound`, `NothingToRedo`, `NothingToUndo`, `group_rows`, `move_block`, `redo`, `rename_block`, `split_block`, `undo`), tre righe in `_manual_error`:

```python
    if isinstance(exc, BlockNotFound):
        return api_error(404, "set_block_not_found", "Block not found")
    if isinstance(exc, NothingToUndo):
        return api_error(409, "set_nothing_to_undo", "Nothing to undo")
    if isinstance(exc, NothingToRedo):
        return api_error(409, "set_nothing_to_redo", "Nothing to redo")
```

e i sei endpoint, accanto a quelli delle alternative (stessa forma: `try`, `manual_set_out(...)`, `except ManualSetError` → `_manual_error`):

```python
@router.post("/{setlist_id}/blocks", response_model=ManualSetOut)
def blocks_group(setlist_id: int, req: BlockGroupRequest, db: Session = Depends(get_db)):
    """Raggruppa righe contigue in una sequenza: l'ordine del percorso non
    cambia, cambia come e' diviso."""
    try:
        return manual_set_out(group_rows(
            db, setlist_id, expected_revision=req.expected_revision,
            row_ids=req.row_ids, name=req.name), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
```

più `blocks_rename` (PATCH), `blocks_move`, `blocks_split`, `history_undo`, `history_redo` sulla stessa falsariga.

- [ ] **Step 6: Esegui, suite, commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

```bash
git add backend/app/schemas.py backend/app/serializers.py backend/app/routers/sets.py backend/tests/test_set_manual_api.py
git commit -m "feat(sets): endpoint di sequenze, banco, annulla e ripeti"
```

---

### Task 6: Frontend — client, testi, pagina

**Files:**
- Modify: `frontend/lib/api/types.ts`, `frontend/lib/api/manual-sets.ts`, `frontend/lib/i18n/{en,it}.ts`
- Create: `frontend/components/set-builder/bench-panel.tsx`
- Modify: `frontend/components/set-builder/path-panel.tsx`, `frontend/app/sets/manual/page.tsx`
- Test: `frontend/tests/set-builder-blocks.test.tsx` (nuovo)

**Interfaces:**

```ts
// ManualBlock esiste già (id, name, placement, position, rows)
// ManualSet guadagna: can_undo: boolean; can_redo: boolean
groupRows(id, body: { expected_revision: number; row_ids: number[]; name?: string | null }): Promise<ManualSet>
renameBlock(id, blockId, body: { expected_revision: number; name: string | null }): Promise<ManualSet>
moveBlock(id, blockId, body: { expected_revision: number; position: number; to_bench?: boolean | null }): Promise<ManualSet>
splitBlock(id, blockId, body: { expected_revision: number }): Promise<ManualSet>
undoSet(id, body: { expected_revision: number }): Promise<ManualSet>
redoSet(id, body: { expected_revision: number }): Promise<ManualSet>
```

Comportamento della pagina:
- Due comandi in testa, «Annulla» e «Ripeti», disabilitati quando `can_undo`/`can_redo` sono falsi, con le scorciatoie `cmd/ctrl+z` e `cmd/ctrl+shift+z` registrate su `window` e rimosse allo smontaggio. Le scorciatoie non scattano mentre il fuoco è in un campo di testo (il campo dell'appunto ha il suo annulla nativo).
- Nel percorso, ogni sequenza ha un'intestazione col nome (o «senza nome»), il conteggio, e i comandi: rinomina, su, giù, al banco, separa.
- Selezione multipla delle righe con la casella accanto a ciascuna; quando due o più righe contigue dello stesso blocco sono selezionate compare «Raggruppa».
- Il banco sta sotto il percorso, sopra la riserva: ogni sequenza con nome, conteggio e «Rimetti nel percorso».
- Ogni mutazione manda `expected_revision`, rimpiazza lo stato con la risposta, ricarica il materiale; un 409 di conflitto mostra il banner esistente, un 409 `set_nothing_to_undo`/`redo` non è un errore da mostrare (i pulsanti erano già disabilitati): si ignora ricaricando.

- [ ] **Step 1: Testi**

Chiavi nuove sotto `sets.manual` in `en.ts` poi `it.ts`: `undoButton`/`redoButton`, `groupButton`, `sequenceUnnamed`, `renameSequenceTitle`, `sequenceNamePlaceholder`, `toBenchTitle`, `splitSequenceTitle`, `benchTitle`, `benchEmpty`, `benchToPathTitle`, `sequenceMeta(n)`, `selectRowLabel`. In `errors`: `set_block_not_found`, `set_nothing_to_undo`, `set_nothing_to_redo`.

Traduzioni italiane: «Annulla», «Ripeti», «Raggruppa», «senza nome», «Rinomina la sequenza», «Nome della sequenza», «Sposta sul banco», «Separa la sequenza», «Banco», «Niente sul banco. Raggruppa delle righe e spostale qui per provarle fuori dal percorso.», «Rimetti nel percorso», `(n) => n === 1 ? "1 traccia" : n + " tracce"`, «Seleziona la riga».

- [ ] **Step 2: Tipi e client** — come da blocco Interfaces sopra, sullo stesso stile dei metodi esistenti in `manual-sets.ts`.

- [ ] **Step 3: Scrivi il test**

`frontend/tests/set-builder-blocks.test.tsx`, sulla falsariga di `set-builder-alternatives.test.tsx` (stessi mock di `@/lib/api` e `next/navigation`, stesso `mount()` dentro `PlayerProvider`, fixture con due blocchi `main` e uno `bench`). Casi:

1. selezionando due righe contigue compare «Raggruppa», e il clic chiama `groupRows` con i due id e `expected_revision`;
2. «Annulla» chiama `undoSet` con la revisione corrente; con `can_undo: false` il pulsante è disabilitato e non chiama nulla;
3. `cmd+z` sulla finestra chiama `undoSet`, ma non lo fa se il fuoco è dentro la textarea dell'appunto;
4. «Sposta sul banco» chiama `moveBlock` con `to_bench: true`, e dal banco «Rimetti nel percorso» chiama `moveBlock` con `to_bench: false`;
5. «Separa» chiama `splitBlock`.

Per il caso 3, il test deve mettere davvero il fuoco nella textarea (`fireEvent.focus`) prima di sparare l'evento da tastiera, altrimenti verifica una cosa diversa da quella che dice.

- [ ] **Step 4: Componenti e pagina** — `bench-panel.tsx` sul modello di `reserve-panel.tsx` (stessa forma, `data-testid="bench-panel"`); `path-panel.tsx` guadagna le caselle di selezione e le intestazioni di sequenza; la pagina tiene `selectedRowIds`, i due comandi di cronologia e le scorciatoie.

- [ ] **Step 5: Verifica**

Run: `cd frontend && npm run test:unit -- tests/set-builder-blocks.test.tsx`, poi `npx tsc --noEmit && npm run lint && npm run test:unit && npm run build`.
Attenzione: i fixture dei test già esistenti (`set-builder-workbench.test.tsx`, `set-builder-alternatives.test.tsx`) vanno aggiornati con `can_undo`/`can_redo`, altrimenti la pagina non si disegna e i loro test cadono **solo nella suite intera**, non da soli — è già successo nella tappa 2.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib frontend/components/set-builder frontend/app/sets/manual/page.tsx frontend/tests
git commit -m "feat(frontend): sequenze, banco e annulla nella pagina del set manuale"
```

---

### Task 7: Documentazione e verifica integrata

**Files:**
- Modify: `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`, `frontend/e2e/set-builder.spec.ts`

- [ ] **Step 1: Documentazione**

`docs/API.md`: i sei endpoint nuovi con i loro corpi, i tre codici errore, `can_undo`/`can_redo`, e la regola che `revision` cresce sempre mentre il cursore dell'annulla è `undo_seq`, interno e non esposto.

`docs/ARCHITECTURE.md`: un paragrafo su `manual_history.py` — snapshot completo della struttura con gli id, ripristino per cancella-e-ricrea, ramo «ripeti» scartato dalla prima modifica nuova, accorpamento dei gesti uguali consecutivi, limite di 50 — e la ragione per cui `revision` e `undo_seq` sono due cose distinte.

`PROGRESS.md`: voce datata con cosa esiste e cosa no (mancano le tappe 4-6).

Vale la regola del progetto: ogni parentesi e ogni rimando va verificato per conto proprio.

- [ ] **Step 2: E2E**

Estendi `frontend/e2e/set-builder.spec.ts` con un secondo test: crea un set con quattro tracce, raggruppa le due centrali, spostale sul banco, verifica che il percorso ne abbia due, annulla due volte e verifica di essere tornato a quattro righe in un blocco solo, ricarica e verifica che lo stato annullato sia quello salvato.

Run: `cd frontend && npm run test:e2e -- set-builder.spec.ts`

- [ ] **Step 3: Verifica finale**

```bash
cd backend && .venv/bin/python -m pytest tests -q
```

```bash
cd frontend && npm run lint && npm run test:unit && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add docs PROGRESS.md frontend/e2e
git commit -m "docs(sets): sequenze, banco e annulla del set manuale"
```
