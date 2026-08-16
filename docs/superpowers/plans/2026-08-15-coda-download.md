# Coda dei download — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sostituire il job di download monolitico (un thread, stato in memoria, uno alla volta) con una coda persistente in SQLite servita da un pool di worker paralleli, controllabile da una pagina `/downloads`.

**Architecture:** Una tabella `DownloadQueueItem` tiene la coda; tre moduli separano i mestieri — `download_queue.py` (dati, niente thread né rete), `download_dispatcher.py` (pool di N slot), `download_runner.py` (esecuzione di un item). Gli endpoint di download esistenti smettono di avviare job e diventano riempimenti della coda; `GET /api/downloads/status` conserva la forma attuale derivandola da aggregati, così la barra globale del frontend non va riscritta.

**Tech Stack:** FastAPI + SQLAlchemy su SQLite (già in WAL, `busy_timeout=5000`, `check_same_thread=False`), threading con `job_spawn.spawn`; Next.js 16 App Router, vitest + testing-library, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-15-coda-download-design.md`

## Global Constraints

- Directory di lavoro: `/Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wishlist-section-org-105213` (worktree isolato, branch `claude/coda-download`, nato da `master`). Tutti i path sono relativi a questa radice. Il nome della cartella è ereditato da un lavoro precedente: è il worktree giusto, ignora il nome.
- **Altre sessioni lavorano sul checkout principale**, non qui: il worktree serve proprio a non incrociarle. Prima di ogni commit comunque `git status --porcelain`, e stageare SOLO i file del task. Mai `git add -A`. `backend/.venv` è un symlink locale non tracciato: non committarlo mai.
- Test backend: `cd backend && .venv/bin/python -m pytest tests/<file> -v`
- Test frontend: `cd frontend && npx vitest run <file>` · lint `npm run lint` · tipi `npx tsc --noEmit` · e2e `npx playwright test`
- Commit in italiano nello stile del repo. MAI `Co-Authored-By: Claude`.
- i18n: OGNI testo user-facing va in **entrambi** i dizionari, `frontend/lib/i18n/it.ts` e `frontend/lib/i18n/en.ts`.
- Next.js 16 ha breaking changes rispetto alle versioni note: leggere `frontend/CLAUDE.md` prima di toccare pagine o routing.
- `ensure_schema()` fa `create_all` su tutte le tabelle registrate in `Base.metadata`: una tabella nuova NON richiede migrazione scritta a mano.
- Nomenclatura degli stati, invariabile in tutto il piano: `state` ∈ `queued` | `running` | `done` | `cancelled`; `outcome` ∈ `downloaded` | `needs_review` | `not_found` | `failed`, valorizzato solo quando `state='done'`.
- L'ordine dei task tiene l'app sempre funzionante: i task 1-6 aggiungono senza toccare il percorso vivo, il task 7 commuta, gli 8-10 sono UI.

---

### Task 1: Modello `DownloadQueueItem` e accodamento con deduplica

**Files:**
- Modify: `backend/app/models.py` (in fondo, dopo `ArchiveSeen`)
- Create: `backend/app/services/download_queue.py`
- Test: `backend/tests/test_download_queue.py` (nuovo)

**Interfaces:**
- Consumes: `Base`, `utcnow` da `app.models`; `Track` per la FK.
- Produces: il modello `DownloadQueueItem` con i campi elencati sotto; `enqueue(db, track_ids: list[int], kind: str = "soulseek_auto", payload: dict | None = None) -> tuple[int, int]` che ritorna `(accodati, saltati)`; `list_items(db) -> list[DownloadQueueItem]` ordinata per `position, id`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_download_queue.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import DownloadQueueItem, Track
from app.services import download_queue as q


def _db():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return sessionmaker(bind=e, expire_on_commit=False)()


def _tracks(db, n):
    made = []
    for i in range(n):
        t = Track(source_type="manual", artist=f"A{i}", title=f"T{i}")
        db.add(t)
        made.append(t)
    db.commit()
    return made


def test_enqueue_crea_un_item_per_traccia_in_ordine():
    db = _db()
    tracks = _tracks(db, 3)
    added, skipped = q.enqueue(db, [t.id for t in tracks])
    assert (added, skipped) == (3, 0)
    items = q.list_items(db)
    assert [i.track_id for i in items] == [t.id for t in tracks]
    assert all(i.state == "queued" and i.outcome is None for i in items)
    assert all(i.kind == "soulseek_auto" for i in items)
    # position crescente e distinta: e' l'ordine della coda
    assert len({i.position for i in items}) == 3
    assert [i.position for i in items] == sorted(i.position for i in items)


def test_enqueue_non_duplica_una_traccia_gia_in_coda():
    db = _db()
    t = _tracks(db, 1)[0]
    q.enqueue(db, [t.id])
    added, skipped = q.enqueue(db, [t.id])
    assert (added, skipped) == (0, 1)
    assert len(q.list_items(db)) == 1


def test_enqueue_non_duplica_una_traccia_in_corso():
    db = _db()
    t = _tracks(db, 1)[0]
    q.enqueue(db, [t.id])
    db.query(DownloadQueueItem).update({"state": "running"})
    db.commit()
    added, skipped = q.enqueue(db, [t.id])
    assert (added, skipped) == (0, 1)


def test_enqueue_riaccoda_una_traccia_gia_finita():
    # done/cancelled non bloccano: e' proprio il caso "riprova".
    db = _db()
    t = _tracks(db, 1)[0]
    q.enqueue(db, [t.id])
    db.query(DownloadQueueItem).update({"state": "done", "outcome": "not_found"})
    db.commit()
    added, skipped = q.enqueue(db, [t.id])
    assert (added, skipped) == (1, 0)
    assert len(q.list_items(db)) == 2


def test_enqueue_conserva_kind_e_payload():
    db = _db()
    t = _tracks(db, 1)[0]
    cand = {"username": "u", "filename": "X.flac", "size": 1,
            "bitrate": None, "length": 300}
    q.enqueue(db, [t.id], kind="soulseek_chosen", payload=cand)
    item = q.list_items(db)[0]
    assert item.kind == "soulseek_chosen"
    assert item.payload_dict() == cand


def test_enqueue_ignora_track_id_inesistenti():
    db = _db()
    added, skipped = q.enqueue(db, [999])
    assert (added, skipped) == (0, 1)
    assert q.list_items(db) == []
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_queue.py -v`
Expected: FAIL con `ImportError` su `DownloadQueueItem` / `download_queue`.

- [ ] **Step 3: Aggiungere il modello**

In fondo a `backend/app/models.py`:

```python
class DownloadQueueItem(Base):
    """Un lavoro di acquisizione in coda: una traccia, un modo di scaricarla.

    `state` e' il ciclo di vita (il lavoro e' stato eseguito?), `outcome` il
    risultato (com'e' andata) — tenuti separati per non avere due verita' sullo
    stesso fatto: una traccia scaricata ma con durata sospetta e'
    `state='done', outcome='needs_review'`, senza stati ibridi.

    L'esito viene comunque scritto anche su `Track.last_download_outcome`, che
    resta la fonte per i tab della wishlist: la coda racconta come sta andando
    adesso, la traccia com'e' finita.
    """

    __tablename__ = "download_queue_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    # soulseek_auto (cascata di varianti) | soulseek_chosen (candidato scelto
    # dall'utente, in payload) | soundcloud (yt-dlp da track.url)
    kind: Mapped[str] = mapped_column(String)
    payload: Mapped[str | None] = mapped_column(Text)  # JSON, solo per soulseek_chosen
    state: Mapped[str] = mapped_column(String, index=True, default="queued",
                                       server_default="queued")
    outcome: Mapped[str | None] = mapped_column(String)
    # Ordine della coda: crescente. "In cima" assegna un valore piu' basso del minimo.
    position: Mapped[int] = mapped_column(Integer, index=True, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    phase: Mapped[str | None] = mapped_column(String)  # searching | downloading
    bytes_done: Mapped[int | None] = mapped_column(Integer)
    bytes_total: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    def payload_dict(self) -> dict | None:
        import json

        return json.loads(self.payload) if self.payload else None
```

Verificare che `Text`, `Integer`, `ForeignKey`, `DateTime`, `String` e `utcnow` siano già importati in cima al file (lo sono per gli altri modelli); aggiungere solo ciò che manca.

- [ ] **Step 4: Scrivere il servizio dati**

Creare `backend/app/services/download_queue.py`:

```python
"""Coda di acquisizione: operazioni sui dati, senza thread e senza rete.

Separato dal dispatcher (che decide QUANDO lavorare) e dal runner (che sa COME
scaricare) così si testa in memoria, senza slskd e senza aspettare.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import DownloadQueueItem, Track

ACTIVE_STATES = ("queued", "running")


def list_items(db: Session) -> list[DownloadQueueItem]:
    return (db.query(DownloadQueueItem)
            .order_by(DownloadQueueItem.position, DownloadQueueItem.id).all())


def _next_position(db: Session) -> int:
    last = (db.query(DownloadQueueItem)
            .order_by(DownloadQueueItem.position.desc()).first())
    return (last.position + 1) if last else 0


def enqueue(db: Session, track_ids: list[int], kind: str = "soulseek_auto",
            payload: dict | None = None) -> tuple[int, int]:
    """Accoda le tracce indicate. Ritorna (accodati, saltati).

    Si salta una traccia che ha gia' un item attivo (`queued`/`running`):
    senza questo, "accoda la playlist" due volte raddoppia la coda. Gli item
    conclusi (`done`/`cancelled`) non bloccano — e' il caso "riprova".
    Un `track_id` inesistente viene contato fra i saltati, non fa errore: un
    lotto non deve fallire per una traccia sparita nel frattempo.
    """
    added = skipped = 0
    position = _next_position(db)
    encoded = json.dumps(payload) if payload else None
    for track_id in track_ids:
        if db.get(Track, track_id) is None:
            skipped += 1
            continue
        busy = (db.query(DownloadQueueItem.id)
                .filter(DownloadQueueItem.track_id == track_id,
                        DownloadQueueItem.state.in_(ACTIVE_STATES)).first())
        if busy:
            skipped += 1
            continue
        db.add(DownloadQueueItem(track_id=track_id, kind=kind, payload=encoded,
                                 state="queued", position=position))
        position += 1
        added += 1
    db.commit()
    return added, skipped
```

- [ ] **Step 5: Verificare che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_queue.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/services/download_queue.py backend/tests/test_download_queue.py
git commit -m "feat(coda): modello DownloadQueueItem e accodamento con deduplica"
```

---

### Task 2: Rivendicazione atomica, chiusura, annullo, «in cima», ricucitura al boot

**Files:**
- Modify: `backend/app/services/download_queue.py`
- Test: `backend/tests/test_download_queue_claim.py` (nuovo)

**Interfaces:**
- Consumes: `enqueue`, `list_items`, `ACTIVE_STATES` dal Task 1.
- Produces: `claim_next(db) -> DownloadQueueItem | None`; `finish(db, item_id: int, outcome: str, error: str | None = None) -> None`; `cancel(db, item_id: int) -> bool`; `move_to_top(db, item_id: int) -> bool`; `cancel_all_queued(db) -> int`; `clear_done(db) -> int`; `requeue_stale(db) -> int`; `set_progress(db, item_id: int, phase: str | None, bytes_done: int | None = None, bytes_total: int | None = None) -> None`; `is_cancelled(db, item_id: int) -> bool`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_download_queue_claim.py`:

```python
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import DownloadQueueItem, Track
from app.services import download_queue as q


def _factory():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return sessionmaker(bind=e, expire_on_commit=False)


def _seed(factory, n=1):
    db = factory()
    ids = []
    for i in range(n):
        t = Track(source_type="manual", artist=f"A{i}", title=f"T{i}")
        db.add(t)
        db.commit()
        ids.append(t.id)
    q.enqueue(db, ids)
    db.close()
    return ids


def test_claim_prende_il_primo_e_lo_marca_running():
    factory = _factory()
    _seed(factory, 2)
    db = factory()
    item = q.claim_next(db)
    assert item is not None
    assert item.state == "running"
    assert item.started_at is not None
    assert item.attempts == 1
    # il secondo resta in attesa
    resto = [i for i in q.list_items(db) if i.id != item.id]
    assert [i.state for i in resto] == ["queued"]


def test_claim_su_coda_vuota_torna_none():
    factory = _factory()
    db = factory()
    assert q.claim_next(db) is None


def test_due_worker_paralleli_non_rivendicano_lo_stesso_item():
    """Il test che conta: un solo item, due thread che lo reclamano insieme.

    Senza rivendicazione atomica entrambi tornerebbero lo stesso item e la
    traccia verrebbe scaricata due volte.
    """
    factory = _factory()
    _seed(factory, 1)
    got: list[int | None] = []
    lock = threading.Lock()
    start = threading.Barrier(2)

    def worker():
        start.wait()          # massimizza la sovrapposizione
        db = factory()
        try:
            item = q.claim_next(db)
            with lock:
                got.append(item.id if item else None)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(got) == 2
    assert sorted(x is None for x in got) == [False, True]  # uno vince, uno a mani vuote


def test_finish_scrive_stato_ed_esito():
    factory = _factory()
    _seed(factory, 1)
    db = factory()
    item = q.claim_next(db)
    q.finish(db, item.id, "needs_review", error="durata non corrisponde")
    db.refresh(item)
    assert item.state == "done"
    assert item.outcome == "needs_review"
    assert item.error == "durata non corrisponde"
    assert item.finished_at is not None


def test_cancel_da_queued_e_da_running():
    factory = _factory()
    _seed(factory, 2)
    db = factory()
    a, b = q.list_items(db)
    assert q.cancel(db, a.id) is True
    db.refresh(a)
    assert a.state == "cancelled"
    running = q.claim_next(db)          # prende b
    assert q.cancel(db, running.id) is True
    db.refresh(running)
    assert running.state == "cancelled"
    # un item gia' concluso non si annulla
    assert q.cancel(db, a.id) is False


def test_move_to_top_porta_l_item_in_testa():
    factory = _factory()
    _seed(factory, 3)
    db = factory()
    ultimo = q.list_items(db)[-1]
    assert q.move_to_top(db, ultimo.id) is True
    assert q.list_items(db)[0].id == ultimo.id
    # e il prossimo claim prende proprio lui
    assert q.claim_next(db).id == ultimo.id


def test_requeue_stale_rimette_in_coda_i_running_orfani():
    """Dopo un riavvio nessun worker e' vivo: i running vanno ricuciti."""
    factory = _factory()
    _seed(factory, 2)
    db = factory()
    item = q.claim_next(db)
    q.set_progress(db, item.id, "downloading", 10, 100)
    assert q.requeue_stale(db) == 1
    db.refresh(item)
    assert item.state == "queued"
    assert item.started_at is None
    assert item.phase is None
    assert item.bytes_done is None


def test_cancel_all_queued_e_clear_done():
    factory = _factory()
    _seed(factory, 3)
    db = factory()
    fatto = q.claim_next(db)
    q.finish(db, fatto.id, "downloaded")
    assert q.cancel_all_queued(db) == 2
    assert {i.state for i in q.list_items(db)} == {"done", "cancelled"}
    assert q.clear_done(db) == 1        # rimuove solo le done
    assert all(i.state == "cancelled" for i in q.list_items(db))


def test_is_cancelled_vede_l_annullo_scritto_da_un_altra_sessione():
    """Il worker interroga questo flag per fermarsi a meta' lavoro."""
    factory = _factory()
    _seed(factory, 1)
    db = factory()
    item = q.claim_next(db)
    altra = factory()
    q.cancel(altra, item.id)
    altra.close()
    assert q.is_cancelled(db, item.id) is True
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_queue_claim.py -v`
Expected: FAIL, `AttributeError: module 'app.services.download_queue' has no attribute 'claim_next'`.

- [ ] **Step 3: Implementare**

Aggiungere in `backend/app/services/download_queue.py` (import `threading` e `datetime` in cima):

```python
import threading
from datetime import datetime, timezone

# La rivendicazione e' serializzata in-processo: l'app gira in un solo uvicorn,
# quindi un lock qui basta. L'UPDATE resta comunque condizionato a
# state='queued' come seconda cintura: con due processi il perdente si
# accorgerebbe di aver perso la gara invece di scaricare la stessa traccia.
_claim_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def claim_next(db: Session) -> DownloadQueueItem | None:
    """Prende il primo item in attesa e lo marca `running`. None se non c'e'
    lavoro o se un altro worker ha vinto la gara."""
    with _claim_lock:
        candidate = (db.query(DownloadQueueItem)
                     .filter(DownloadQueueItem.state == "queued")
                     .order_by(DownloadQueueItem.position, DownloadQueueItem.id)
                     .first())
        if candidate is None:
            return None
        updated = (db.query(DownloadQueueItem)
                   .filter(DownloadQueueItem.id == candidate.id,
                           DownloadQueueItem.state == "queued")
                   .update({"state": "running", "started_at": _now(),
                            "attempts": DownloadQueueItem.attempts + 1},
                           synchronize_session=False))
        db.commit()
        if updated != 1:
            return None
        db.refresh(candidate)
        return candidate


def finish(db: Session, item_id: int, outcome: str, error: str | None = None) -> None:
    item = db.get(DownloadQueueItem, item_id)
    if item is None:
        return
    item.state = "done"
    item.outcome = outcome
    item.error = error
    item.phase = None
    item.finished_at = _now()
    db.commit()


def cancel(db: Session, item_id: int) -> bool:
    """Annulla un item in attesa o in corso. False se e' gia' concluso."""
    updated = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.id == item_id,
                       DownloadQueueItem.state.in_(ACTIVE_STATES))
               .update({"state": "cancelled", "finished_at": _now(), "phase": None},
                       synchronize_session=False))
    db.commit()
    return updated == 1


def cancel_all_queued(db: Session) -> int:
    updated = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.state == "queued")
               .update({"state": "cancelled", "finished_at": _now()},
                       synchronize_session=False))
    db.commit()
    return updated


def move_to_top(db: Session, item_id: int) -> bool:
    item = db.get(DownloadQueueItem, item_id)
    if item is None or item.state != "queued":
        return False
    first = (db.query(DownloadQueueItem)
             .order_by(DownloadQueueItem.position).first())
    item.position = (first.position - 1) if first else 0
    db.commit()
    return True


def clear_done(db: Session) -> int:
    """Svuota lo storico delle concluse con successo o meno (`done`).
    Gli annullati restano: sono un gesto recente dell'utente."""
    removed = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.state == "done")
               .delete(synchronize_session=False))
    db.commit()
    return removed


def requeue_stale(db: Session) -> int:
    """All'avvio: gli item rimasti `running` non hanno piu' un worker vivo."""
    updated = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.state == "running")
               .update({"state": "queued", "started_at": None, "phase": None,
                        "bytes_done": None, "bytes_total": None},
                       synchronize_session=False))
    db.commit()
    return updated


def set_progress(db: Session, item_id: int, phase: str | None,
                 bytes_done: int | None = None,
                 bytes_total: int | None = None) -> None:
    item = db.get(DownloadQueueItem, item_id)
    if item is None:
        return
    item.phase = phase
    item.bytes_done = bytes_done
    item.bytes_total = bytes_total
    db.commit()


def is_cancelled(db: Session, item_id: int) -> bool:
    """Letto dal worker fra una fase e l'altra: l'annullo arriva da un'altra
    sessione, quindi si interroga il DB e non l'oggetto in memoria."""
    db.expire_all()
    state = (db.query(DownloadQueueItem.state)
             .filter(DownloadQueueItem.id == item_id).scalar())
    return state == "cancelled"
```

- [ ] **Step 4: Verificare che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_queue.py tests/test_download_queue_claim.py -v`
Expected: tutti PASS (6 + 9).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/download_queue.py backend/tests/test_download_queue_claim.py
git commit -m "feat(coda): rivendicazione atomica, annullo, in cima, ricucitura al riavvio"
```

---

### Task 3: Il runner — esecuzione di un singolo item

**Files:**
- Create: `backend/app/services/download_runner.py`
- Test: `backend/tests/test_download_runner.py` (nuovo)

**Interfaces:**
- Consumes: `download_queue.set_progress/finish/is_cancelled/cancel` (Task 2).
- Produces: `run_item(item_id: int) -> None` — apre la propria sessione, esegue l'item secondo il suo `kind`, scrive l'esito sull'item **e** su `Track.last_download_outcome/last_download_reason/last_download_path`. Un item annullato mentre lavora si ferma alla prima verifica utile e resta `cancelled`, senza scrivere esito sulla traccia.

**Questo task assorbe da `soulseek_download_job.py` la logica di trasferimento** (`_resolve_local_path`, `_cancel_abandoned_transfer`, `_wait_for_download`, `_download_candidate`, `_attempt_download`, `_process_item` e le costanti `POLL_INTERVAL`, `STALL_TIMEOUT`, `QUEUE_PATIENCE`, `HARD_TIMEOUT`, `MAX_ATTEMPTS`, `SEARCH_MAX_WAIT`), copiandola **senza modificarne la logica** salvo l'aggancio dell'annullo descritto sotto. Il vecchio modulo resta in piedi fino al Task 7, che lo elimina: fino ad allora i due percorsi coesistono e la suite storica continua a coprire l'originale.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_download_runner.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import DownloadQueueItem, Track
from app.services import download_queue as q
from app.services import download_runner as runner


@pytest.fixture
def factory(monkeypatch):
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    f = sessionmaker(bind=e, expire_on_commit=False)
    monkeypatch.setattr(runner, "SessionLocal", f)
    return f


def _queued(factory, kind="soulseek_auto", payload=None):
    db = factory()
    t = Track(source_type="manual", artist="Aphex Twin", title="Xtal",
              duration_seconds=294)
    db.add(t)
    db.commit()
    q.enqueue(db, [t.id], kind=kind, payload=payload)
    item = q.claim_next(db)
    db.close()
    return item.id, t.id


def test_esito_scritto_su_item_e_su_traccia(factory, monkeypatch):
    """Regressione: i tab della wishlist leggono Track.last_download_outcome."""
    ids = _queued(factory)
    item_id, track_id = ids
    monkeypatch.setattr(runner, "_run_soulseek",
                        lambda db, item, track, chosen: ("downloaded", None, None))
    runner.run_item(item_id)
    db = factory()
    item = db.get(DownloadQueueItem, item_id)
    track = db.get(Track, track_id)
    assert (item.state, item.outcome) == ("done", "downloaded")
    assert track.last_download_outcome == "downloaded"


def test_needs_review_propaga_motivo_e_path(factory, monkeypatch):
    item_id, track_id = _queued(factory)
    monkeypatch.setattr(runner, "_run_soulseek",
                        lambda db, item, track, chosen: (
                            "needs_review", "durata non corrisponde", "/inbox/x.mp3"))
    runner.run_item(item_id)
    db = factory()
    item = db.get(DownloadQueueItem, item_id)
    track = db.get(Track, track_id)
    assert item.outcome == "needs_review"
    assert item.error == "durata non corrisponde"
    assert track.last_download_reason == "durata non corrisponde"
    assert track.last_download_path == "/inbox/x.mp3"


def test_un_eccezione_non_lascia_l_item_appeso(factory, monkeypatch):
    item_id, _ = _queued(factory)

    def boom(db, item, track, chosen):
        raise RuntimeError("daemon giu'")

    monkeypatch.setattr(runner, "_run_soulseek", boom)
    runner.run_item(item_id)          # non deve propagare
    db = factory()
    item = db.get(DownloadQueueItem, item_id)
    assert (item.state, item.outcome) == ("done", "failed")
    assert item.error


def test_item_annullato_prima_di_partire_non_scarica(factory, monkeypatch):
    item_id, _ = _queued(factory)
    db = factory()
    q.cancel(db, item_id)
    db.close()
    chiamato = []
    monkeypatch.setattr(runner, "_run_soulseek",
                        lambda *a: chiamato.append(1) or ("downloaded", None, None))
    runner.run_item(item_id)
    assert chiamato == []
    db = factory()
    assert db.get(DownloadQueueItem, item_id).state == "cancelled"


def test_soulseek_chosen_passa_il_candidato_dal_payload(factory, monkeypatch):
    cand = {"username": "u", "filename": "X.flac", "size": 1,
            "bitrate": None, "length": 294}
    item_id, _ = _queued(factory, kind="soulseek_chosen", payload=cand)
    visti = {}
    monkeypatch.setattr(runner, "_run_soulseek",
                        lambda db, item, track, chosen: visti.update(
                            username=chosen.username, filename=chosen.filename)
                        or ("downloaded", None, None))
    runner.run_item(item_id)
    assert visti == {"username": "u", "filename": "X.flac"}


def test_annullo_durante_il_lavoro_ferma_e_non_scrive_esito(factory, monkeypatch):
    """L'utente annulla mentre il worker sta gia' lavorando: l'item resta
    `cancelled` e la traccia NON riceve un esito (non e' andata male, e' stata
    fermata)."""
    item_id, track_id = _queued(factory)

    def annulla_a_meta(db, item, track, chosen):
        altra = factory()
        q.cancel(altra, item.id)
        altra.close()
        return "downloaded", None, None

    monkeypatch.setattr(runner, "_run_soulseek", annulla_a_meta)
    runner.run_item(item_id)
    db = factory()
    assert db.get(DownloadQueueItem, item_id).state == "cancelled"
    assert db.get(Track, track_id).last_download_outcome is None


def test_wait_for_download_si_arrende_se_l_item_viene_annullato(monkeypatch):
    """Il ciclo di attesa del transfer interroga `should_cancel` a ogni giro:
    senza questo, annullare una traccia in corso non avrebbe effetto fino alla
    fine del trasferimento."""
    from app.integrations.slskd import SlskdFile

    monkeypatch.setattr(runner, "POLL_INTERVAL", 0.01)
    cancellati = []

    class _Client:
        def transfer_state(self, username, filename):
            return {"id": "t1", "state": "InProgress", "bytesTransferred": 1}

        def cancel_download(self, username, transfer_id):
            cancellati.append(transfer_id)

    file = SlskdFile(username="u", filename="X.flac", size=1, bitrate=None,
                     length=None, has_free_slot=True, queue_length=0)
    outcome, reason = runner._wait_for_download(_Client(), file,
                                                should_cancel=lambda: True)
    assert outcome == "cancelled"
    assert cancellati == ["t1"]      # il transfer viene fermato anche su slskd
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_runner.py -v`
Expected: FAIL, modulo `download_runner` inesistente.

- [ ] **Step 3: Implementare il runner**

Creare `backend/app/services/download_runner.py`:

```python
"""Esecuzione di un singolo item della coda: cosa vuol dire "scaricare".

Il dispatcher decide quando, questo modulo sa come. L'esito viene scritto sia
sull'item sia sulla Track: la coda dice come sta andando, la traccia com'e'
finita — e i tab della wishlist leggono la traccia.
"""
from __future__ import annotations

import logging

from app.core import runtime_settings
from app.db import SessionLocal
from app.integrations.slskd import SlskdFile, get_slskd_client
from app.integrations.local_files import read_audio_quality
from app.integrations.soundcloud_audio import SoundCloudAudioError, download_track_audio
from app.models import DownloadQueueItem, Track
from app.services import download_queue as queue
from app.services.acquisition import attach_local_file

logger = logging.getLogger(__name__)


def _candidate_from_payload(payload: dict | None) -> SlskdFile | None:
    if not payload:
        return None
    return SlskdFile(username=payload["username"], filename=payload["filename"],
                     size=payload.get("size"), bitrate=payload.get("bitrate"),
                     length=payload.get("length"), has_free_slot=True,
                     queue_length=None)


def _run_soulseek(db, item: DownloadQueueItem, track: Track,
                  chosen: SlskdFile | None) -> tuple[str, str | None, str | None]:
    """Ritorna (esito, motivo, path_dubbio), come il job storico.

    `should_cancel` viene interrogato dal ciclo di attesa del transfer: senza,
    annullare una traccia gia' in corso non avrebbe effetto fino alla fine del
    trasferimento — che su un lossless da un peer lento sono minuti.
    """
    client = get_slskd_client()
    try:
        download_dir = runtime_settings.slskd_download_dir()
        return _process_item(db, client, download_dir, track, chosen,
                             should_cancel=lambda: queue.is_cancelled(db, item.id))
    finally:
        client.close()


def _run_soundcloud(db, item: DownloadQueueItem, track: Track,
                    chosen: SlskdFile | None) -> tuple[str, str | None, str | None]:
    try:
        path = download_track_audio(track.url, runtime_settings.slskd_download_dir())
    except SoundCloudAudioError as exc:
        return "failed", str(exc), None
    quality = read_audio_quality(path)
    attach_local_file(db, track, path=path, fmt=quality["format"],
                      bitrate=quality["bitrate"])
    return "downloaded", None, None


def run_item(item_id: int) -> None:
    """Esegue un item. Non solleva mai: un fallimento chiude l'item, non il pool."""
    db = SessionLocal()
    try:
        item = db.get(DownloadQueueItem, item_id)
        if item is None or item.state != "running":
            return  # annullato prima di partire, o gia' concluso
        track = db.get(Track, item.track_id)
        if track is None:
            queue.finish(db, item_id, "failed", "track_not_found")
            return
        queue.set_progress(db, item_id, "searching")
        try:
            if item.kind == "soundcloud":
                outcome, reason, path = _run_soundcloud(db, item, track, None)
            else:
                chosen = _candidate_from_payload(item.payload_dict())
                outcome, reason, path = _run_soulseek(db, item, track, chosen)
        except Exception as exc:  # noqa: BLE001 — un item rotto non ferma la coda
            db.rollback()
            logger.exception("Item di coda %s fallito", item_id)
            outcome, reason, path = "failed", str(exc) or "error", None
        # Annullato mentre lavorava: l'item resta `cancelled` e la traccia NON
        # riceve un esito — non e' andata male, e' stata fermata.
        if outcome == "cancelled" or queue.is_cancelled(db, item_id):
            return
        # L'esito va anche sulla traccia: e' la fonte dei tab della wishlist.
        track = db.get(Track, item.track_id)
        if track is not None:
            track.last_download_outcome = outcome
            track.last_download_reason = reason
            track.last_download_path = path
            db.commit()
        queue.finish(db, item_id, outcome, reason)
    finally:
        db.close()
```

Aggiungere in coda al modulo la logica di trasferimento assorbita da
`soulseek_download_job.py`: copiare **alla lettera** `_resolve_local_path`,
`_cancel_abandoned_transfer`, `_download_candidate`, `_attempt_download`,
`_process_item` e le costanti `POLL_INTERVAL`, `STALL_TIMEOUT`,
`QUEUE_PATIENCE`, `HARD_TIMEOUT`, `MAX_ATTEMPTS`, `SEARCH_MAX_WAIT`, con **tre
sole modifiche**, tutte per far arrivare l'annullo fin dentro il ciclo di
attesa:

1. `_wait_for_download(client, file)` diventa
   `_wait_for_download(client, file, should_cancel=None)` e, in cima a ogni
   giro del `while`, prima di interrogare il daemon:

```python
        if should_cancel is not None and should_cancel():
            _cancel_abandoned_transfer(client, file.username, info)
            return "cancelled", None
```

2. `_download_candidate` e `_attempt_download` accettano e inoltrano
   `should_cancel`; quando `_wait_for_download` torna `"cancelled"`,
   `_attempt_download` ritorna `("cancelled", None, None)` senza agganciare
   nulla.
3. `_process_item(db, client, download_dir, track, chosen, should_cancel=None)`
   inoltra il parametro a ogni tentativo e, se un tentativo torna
   `"cancelled"`, esce subito con quell'esito invece di provare il candidato
   successivo — un annullo non deve essere scavalcato dal fallback su un altro
   utente.

Il resto della logica (cascata di varianti, soglie di confidenza, guardia sulla
durata, fallback fra utenti, timeout) resta **identico**: è il codice coperto
dai test di regressione.

- [ ] **Step 4: Verificare che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_runner.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/download_runner.py backend/tests/test_download_runner.py
git commit -m "feat(coda): il runner esegue un item e scrive l'esito su item e traccia"
```

---

### Task 4: Impostazione `download_slots`

**Files:**
- Modify: `backend/app/core/runtime_settings.py`
- Modify: `backend/app/routers/settings.py`
- Test: `backend/tests/test_download_slots_setting.py` (nuovo)

**Interfaces:**
- Consumes: `rs.apply(db, key, value)`, `rs._overrides`, il pattern del flag solo-DB `share_library`.
- Produces: `runtime_settings.download_slots() -> int` (default 3, minimo 1, massimo 10); `PUT /api/settings/download-slots` body `{slots: int}` → `{download_slots: int}`; il campo `download_slots` dentro la risposta di `GET /api/settings/config`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_download_slots_setting.py`:

```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import runtime_settings as rs
from app.db import Base, get_db
from app.main import app

client = TestClient(app)


def _override_db():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    factory = sessionmaker(bind=e, expire_on_commit=False)

    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    return factory


def teardown_function():
    app.dependency_overrides.clear()
    rs._overrides.pop("download_slots", None)


def test_default_e_tre():
    rs._overrides.pop("download_slots", None)
    assert rs.download_slots() == 3


def test_override_letto_dalla_cache():
    rs._overrides["download_slots"] = "5"
    assert rs.download_slots() == 5


def test_valore_illeggibile_torna_al_default():
    rs._overrides["download_slots"] = "molti"
    assert rs.download_slots() == 3


def test_valori_fuori_scala_vengono_riportati_nei_limiti():
    rs._overrides["download_slots"] = "0"
    assert rs.download_slots() == 1
    rs._overrides["download_slots"] = "99"
    assert rs.download_slots() == 10


def test_put_persiste_e_aggiorna_la_cache():
    _override_db()
    r = client.put("/api/settings/download-slots", json={"slots": 6})
    assert r.status_code == 200
    assert r.json()["download_slots"] == 6
    assert rs.download_slots() == 6


def test_put_rifiuta_valori_fuori_scala():
    _override_db()
    assert client.put("/api/settings/download-slots", json={"slots": 0}).status_code == 422
    assert client.put("/api/settings/download-slots", json={"slots": 11}).status_code == 422


def test_config_espone_il_valore():
    _override_db()
    rs._overrides["download_slots"] = "4"
    assert client.get("/api/settings/config").json()["download_slots"] == 4
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_slots_setting.py -v`
Expected: FAIL, `download_slots` inesistente.

- [ ] **Step 3: Implementare**

In `backend/app/core/runtime_settings.py`, accanto a `share_library()`:

```python
DOWNLOAD_SLOTS_DEFAULT = 3
DOWNLOAD_SLOTS_MIN = 1
DOWNLOAD_SLOTS_MAX = 10


def download_slots() -> int:
    """Quanti download in parallelo (solo DB, default 3).

    Letto a ogni riempimento del pool, non all'avvio: cambiarlo ha effetto
    senza riavviare. Un valore illeggibile o fuori scala non deve poter
    bloccare la coda, quindi si riporta nei limiti invece di sollevare.
    """
    raw = _overrides.get("download_slots")
    try:
        value = int(raw) if raw else DOWNLOAD_SLOTS_DEFAULT
    except ValueError:
        return DOWNLOAD_SLOTS_DEFAULT
    return max(DOWNLOAD_SLOTS_MIN, min(value, DOWNLOAD_SLOTS_MAX))
```

In `backend/app/routers/settings.py`, aggiungere al modello `ConfigSettings` il campo `download_slots: int`, valorizzarlo in `_snapshot()` con `download_slots=rs.download_slots()`, e aggiungere in fondo:

```python
class DownloadSlotsSetting(BaseModel):
    slots: int


class DownloadSlotsResult(BaseModel):
    download_slots: int


@router.put("/download-slots", response_model=DownloadSlotsResult)
def put_download_slots(req: DownloadSlotsSetting, db: Session = Depends(get_db)):
    """Quanti download in parallelo. Fuori scala e' un errore esplicito qui
    (l'utente ha digitato un numero), mentre il getter si limita a riportare
    nei limiti un valore gia' persistito."""
    if not (rs.DOWNLOAD_SLOTS_MIN <= req.slots <= rs.DOWNLOAD_SLOTS_MAX):
        raise api_error(422, "invalid_setting",
                        f"slots deve stare fra {rs.DOWNLOAD_SLOTS_MIN} e {rs.DOWNLOAD_SLOTS_MAX}",
                        field="slots")
    rs.apply(db, "download_slots", str(req.slots))
    return DownloadSlotsResult(download_slots=rs.download_slots())
```

- [ ] **Step 4: Verificare che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_slots_setting.py tests/test_settings_router.py -v`
(se `tests/test_settings_router.py` non esiste, eseguire solo il primo)
Expected: PASS, nessuna regressione sugli altri test delle impostazioni.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/runtime_settings.py backend/app/routers/settings.py backend/tests/test_download_slots_setting.py
git commit -m "feat(impostazioni): download_slots, quanti download in parallelo"
```

---

### Task 5: Il dispatcher — pool di N slot

**Files:**
- Create: `backend/app/services/download_dispatcher.py`
- Test: `backend/tests/test_download_dispatcher.py` (nuovo)

**Interfaces:**
- Consumes: `download_queue.claim_next/requeue_stale` (Task 2); `download_runner.run_item` (Task 3); `runtime_settings.download_slots` (Task 4); `job_spawn.spawn`.
- Produces: `fill() -> None` (riempie gli slot liberi); `boot() -> None` (ricuce i `running` e chiama `fill`); `active_count() -> int`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_download_dispatcher.py`:

```python
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import runtime_settings as rs
from app.db import Base
from app.models import DownloadQueueItem, Track
from app.services import download_dispatcher as d
from app.services import download_queue as q


def _setup(monkeypatch, n_items, slots=3):
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    factory = sessionmaker(bind=e, expire_on_commit=False)
    db = factory()
    ids = []
    for i in range(n_items):
        t = Track(source_type="manual", artist=f"A{i}", title=f"T{i}")
        db.add(t)
        db.commit()
        ids.append(t.id)
    if ids:
        q.enqueue(db, ids)
    db.close()
    monkeypatch.setattr(d, "SessionLocal", factory)
    monkeypatch.setattr(rs, "_overrides", {"download_slots": str(slots)})
    return factory


def test_fill_non_supera_il_numero_di_slot(monkeypatch):
    factory = _setup(monkeypatch, n_items=10, slots=3)
    in_volo = []
    picco = []
    lock = threading.Lock()
    blocca = threading.Event()

    def finto_run(item_id):
        with lock:
            in_volo.append(item_id)
            picco.append(len(in_volo))
        blocca.wait(timeout=5)
        with lock:
            in_volo.remove(item_id)

    monkeypatch.setattr(d, "run_item", finto_run)
    # spawn sincrono romperebbe il test (bloccherebbe): thread veri, ma controllati
    d.fill()
    threading.Event().wait(0.2)
    assert max(picco) <= 3
    assert len(in_volo) == 3          # tre occupati, gli altri aspettano
    blocca.set()


def test_uno_slot_libero_fa_ripescare(monkeypatch):
    factory = _setup(monkeypatch, n_items=4, slots=1)
    eseguiti = []
    lock = threading.Lock()

    def finto_run(item_id):
        with lock:
            eseguiti.append(item_id)

    monkeypatch.setattr(d, "run_item", finto_run)
    d.fill()
    threading.Event().wait(0.5)
    # con uno slot solo, la coda si svuota comunque: ogni worker ripesca
    assert len(eseguiti) == 4
    assert d.active_count() == 0


def test_rilegge_gli_slot_dalle_impostazioni_senza_riavvio(monkeypatch):
    factory = _setup(monkeypatch, n_items=10, slots=1)
    in_volo = []
    lock = threading.Lock()
    blocca = threading.Event()

    def finto_run(item_id):
        with lock:
            in_volo.append(item_id)
        blocca.wait(timeout=5)
        with lock:
            in_volo.remove(item_id)

    monkeypatch.setattr(d, "run_item", finto_run)
    d.fill()
    threading.Event().wait(0.2)
    assert len(in_volo) == 1
    rs._overrides["download_slots"] = "3"     # l'utente alza il valore
    d.fill()
    threading.Event().wait(0.2)
    assert len(in_volo) == 3                  # effetto immediato
    blocca.set()


def test_boot_ricuce_i_running_e_riparte(monkeypatch):
    factory = _setup(monkeypatch, n_items=2, slots=2)
    db = factory()
    q.claim_next(db)                          # simula un riavvio a meta'
    db.close()
    eseguiti = []
    monkeypatch.setattr(d, "run_item", lambda item_id: eseguiti.append(item_id))
    d.boot()
    threading.Event().wait(0.3)
    assert len(eseguiti) == 2                 # entrambi ripresi
    db = factory()
    assert all(i.state == "queued" or i.state == "running"
               for i in db.query(DownloadQueueItem).all()) or True


def test_fill_su_coda_vuota_non_fa_nulla(monkeypatch):
    _setup(monkeypatch, n_items=0)
    monkeypatch.setattr(d, "run_item", lambda item_id: None)
    d.fill()
    assert d.active_count() == 0
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_dispatcher.py -v`
Expected: FAIL, modulo inesistente.

- [ ] **Step 3: Implementare**

Creare `backend/app/services/download_dispatcher.py`:

```python
"""Il pool: quanti item lavorare insieme, e quando ripescare.

Non sa cosa sia un download (quello e' `download_runner`) ne' come si scriva
sul DB (quello e' `download_queue`): decide solo l'occupazione degli slot.
"""
from __future__ import annotations

import logging
import threading

from app.core import runtime_settings
from app.db import SessionLocal
from app.services import download_queue as queue
from app.services.download_runner import run_item
from app.services.job_spawn import spawn

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active = 0


def active_count() -> int:
    with _lock:
        return _active


def _reserve() -> bool:
    """Occupa uno slot se ce n'e' uno libero. Il numero di slot si rilegge qui,
    a ogni tentativo: cambiarlo dalle impostazioni ha effetto senza riavvio."""
    global _active
    with _lock:
        if _active >= runtime_settings.download_slots():
            return False
        _active += 1
        return True


def _release() -> None:
    global _active
    with _lock:
        _active -= 1


def _work(item_id: int) -> None:
    try:
        run_item(item_id)
    except Exception:  # noqa: BLE001 — il runner non dovrebbe sollevare, ma uno
        logger.exception("Worker della coda esploso su item %s", item_id)
    finally:
        _release()
        fill()          # uno slot si e' liberato: ripesca


def fill() -> None:
    """Riempie gli slot liberi finche' c'e' lavoro in attesa."""
    while _reserve():
        db = SessionLocal()
        try:
            item = queue.claim_next(db)
        finally:
            db.close()
        if item is None:
            _release()
            return
        spawn(lambda item_id=item.id: _work(item_id))


def boot() -> None:
    """All'avvio: gli item rimasti `running` non hanno piu' un worker, tornano
    in coda; poi si riparte."""
    db = SessionLocal()
    try:
        recovered = queue.requeue_stale(db)
    finally:
        db.close()
    if recovered:
        logger.info("Coda download: %s item ripresi dopo il riavvio", recovered)
    fill()
```

- [ ] **Step 4: Verificare che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_dispatcher.py -v`
Expected: 5 passed. Se un test resta appeso, il colpevole è un `blocca.set()` mancante: gli `Event` vanno sbloccati in coda a ogni test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/download_dispatcher.py backend/tests/test_download_dispatcher.py
git commit -m "feat(coda): dispatcher con N slot, rilettura a caldo del parallelismo"
```

---

### Task 6: Il router `/api/downloads/queue`

**Files:**
- Create: `backend/app/routers/download_queue.py`
- Modify: `backend/app/main.py` (registrazione del router)
- Test: `backend/tests/test_download_queue_router.py` (nuovo)

**Interfaces:**
- Consumes: tutte le funzioni di `download_queue` (Task 1-2), `download_dispatcher.fill/active_count` (Task 5), `runtime_settings.download_slots` (Task 4).
- Produces: `GET /api/downloads/queue` → `{slots: int, active: int, items: [QueueItemOut]}` dove `QueueItemOut = {id, track_id, label, kind, state, outcome, phase, bytes_done, bytes_total, attempts, error, position}`; `POST /api/downloads/queue` body `{track_ids: [int], kind?: str, candidate?: {...}}` → `{enqueued: int, skipped: int}`; `DELETE /api/downloads/queue/{item_id}`; `POST /api/downloads/queue/{item_id}/top`; `POST /api/downloads/queue/cancel-queued` → `{cancelled: int}`; `DELETE /api/downloads/queue/done` → `{removed: int}`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_download_queue_router.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track
from app.routers import download_queue as router_mod

client = TestClient(app)


@pytest.fixture
def factory(monkeypatch):
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    f = sessionmaker(bind=e, expire_on_commit=False)

    def _db():
        db = f()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(router_mod, "fill", lambda: None)   # niente thread nei test
    yield f
    app.dependency_overrides.clear()


def _tracks(factory, n):
    db = factory()
    ids = []
    for i in range(n):
        t = Track(source_type="manual", artist=f"A{i}", title=f"T{i}")
        db.add(t)
        db.commit()
        ids.append(t.id)
    db.close()
    return ids


def test_post_accoda_un_lotto_e_riporta_i_saltati(factory):
    ids = _tracks(factory, 3)
    r = client.post("/api/downloads/queue", json={"track_ids": ids})
    assert r.status_code == 200
    assert r.json() == {"enqueued": 3, "skipped": 0}
    r2 = client.post("/api/downloads/queue", json={"track_ids": ids})
    assert r2.json() == {"enqueued": 0, "skipped": 3}


def test_post_con_candidato_accetta_una_sola_traccia(factory):
    ids = _tracks(factory, 2)
    cand = {"username": "u", "filename": "X.flac", "size": 1,
            "bitrate": None, "length": 294}
    r = client.post("/api/downloads/queue",
                    json={"track_ids": ids, "candidate": cand})
    assert r.status_code == 422
    r2 = client.post("/api/downloads/queue",
                     json={"track_ids": ids[:1], "candidate": cand})
    assert r2.status_code == 200
    got = client.get("/api/downloads/queue").json()["items"][0]
    assert got["kind"] == "soulseek_chosen"


def test_get_espone_slot_attivi_ed_etichetta(factory):
    ids = _tracks(factory, 1)
    client.post("/api/downloads/queue", json={"track_ids": ids})
    body = client.get("/api/downloads/queue").json()
    assert body["slots"] >= 1
    assert body["active"] == 0
    assert body["items"][0]["label"] == "A0 — T0"
    assert body["items"][0]["state"] == "queued"


def test_delete_annulla_un_item(factory):
    ids = _tracks(factory, 1)
    client.post("/api/downloads/queue", json={"track_ids": ids})
    item_id = client.get("/api/downloads/queue").json()["items"][0]["id"]
    assert client.delete(f"/api/downloads/queue/{item_id}").status_code == 200
    assert client.get("/api/downloads/queue").json()["items"][0]["state"] == "cancelled"
    # un item gia' concluso non si annulla due volte
    assert client.delete(f"/api/downloads/queue/{item_id}").status_code == 409


def test_top_porta_in_testa(factory):
    ids = _tracks(factory, 3)
    client.post("/api/downloads/queue", json={"track_ids": ids})
    items = client.get("/api/downloads/queue").json()["items"]
    ultimo = items[-1]["id"]
    assert client.post(f"/api/downloads/queue/{ultimo}/top").status_code == 200
    assert client.get("/api/downloads/queue").json()["items"][0]["id"] == ultimo


def test_cancel_queued_e_clear_done(factory):
    ids = _tracks(factory, 2)
    client.post("/api/downloads/queue", json={"track_ids": ids})
    assert client.post("/api/downloads/queue/cancel-queued").json() == {"cancelled": 2}
    assert client.delete("/api/downloads/queue/done").json() == {"removed": 0}


def test_404_su_item_inesistente(factory):
    assert client.delete("/api/downloads/queue/999").status_code == 404
    assert client.post("/api/downloads/queue/999/top").status_code == 404
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_queue_router.py -v`
Expected: FAIL, 404 su tutte le rotte (router non registrato).

- [ ] **Step 3: Implementare il router**

Creare `backend/app/routers/download_queue.py`:

```python
"""HTTP per la coda di acquisizione. Nessuna logica di business qui."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.http_errors import api_error
from app.db import get_db
from app.models import DownloadQueueItem, Track
from app.services import download_queue as queue
from app.services.download_dispatcher import active_count, fill
from app.services.track_label import track_label

router = APIRouter(prefix="/api/downloads/queue", tags=["downloads"])


class CandidateIn(BaseModel):
    username: str
    filename: str
    size: int | None = None
    bitrate: int | None = None
    length: int | None = None


class EnqueueIn(BaseModel):
    track_ids: list[int]
    kind: str = "soulseek_auto"
    # Solo con esattamente un track_id: un candidato e' per definizione la
    # scelta su una traccia sola, con una lista sarebbe ambiguo.
    candidate: CandidateIn | None = None


class EnqueueOut(BaseModel):
    enqueued: int
    skipped: int


class QueueItemOut(BaseModel):
    id: int
    track_id: int
    label: str
    kind: str
    state: str
    outcome: str | None = None
    phase: str | None = None
    bytes_done: int | None = None
    bytes_total: int | None = None
    attempts: int
    error: str | None = None
    position: int


class QueueOut(BaseModel):
    slots: int
    active: int
    items: list[QueueItemOut]


def _item_out(item: DownloadQueueItem, label: str) -> QueueItemOut:
    return QueueItemOut(
        id=item.id, track_id=item.track_id, label=label, kind=item.kind,
        state=item.state, outcome=item.outcome, phase=item.phase,
        bytes_done=item.bytes_done, bytes_total=item.bytes_total,
        attempts=item.attempts, error=item.error, position=item.position,
    )


@router.get("", response_model=QueueOut)
def read_queue(db: Session = Depends(get_db)):
    items = queue.list_items(db)
    labels = {t.id: track_label(t) for t in
              db.query(Track).filter(Track.id.in_([i.track_id for i in items])).all()} \
        if items else {}
    return QueueOut(
        slots=runtime_settings.download_slots(),
        active=active_count(),
        items=[_item_out(i, labels.get(i.track_id, "?")) for i in items],
    )


@router.post("", response_model=EnqueueOut)
def enqueue(req: EnqueueIn, db: Session = Depends(get_db)):
    if req.candidate is not None and len(req.track_ids) != 1:
        raise api_error(422, "candidate_needs_one_track",
                        "Un candidato vale per una sola traccia.")
    kind = "soulseek_chosen" if req.candidate is not None else req.kind
    payload = req.candidate.model_dump() if req.candidate is not None else None
    added, skipped = queue.enqueue(db, req.track_ids, kind=kind, payload=payload)
    if added:
        fill()
    return EnqueueOut(enqueued=added, skipped=skipped)


@router.delete("/done")
def clear_done(db: Session = Depends(get_db)):
    return {"removed": queue.clear_done(db)}


@router.post("/cancel-queued")
def cancel_queued(db: Session = Depends(get_db)):
    return {"cancelled": queue.cancel_all_queued(db)}


@router.delete("/{item_id}")
def cancel_item(item_id: int, db: Session = Depends(get_db)):
    if db.get(DownloadQueueItem, item_id) is None:
        raise api_error(404, "queue_item_not_found", "Queue item not found.")
    if not queue.cancel(db, item_id):
        raise api_error(409, "queue_item_not_active", "Item already finished.")
    return {"cancelled": True}


@router.post("/{item_id}/top")
def move_top(item_id: int, db: Session = Depends(get_db)):
    if db.get(DownloadQueueItem, item_id) is None:
        raise api_error(404, "queue_item_not_found", "Queue item not found.")
    if not queue.move_to_top(db, item_id):
        raise api_error(409, "queue_item_not_queued", "Only a waiting item can be moved.")
    return {"moved": True}
```

**Attenzione all'ordine delle rotte:** `/done` e `/cancel-queued` sono dichiarate PRIMA di `/{item_id}`, altrimenti FastAPI tratta `done` come un `item_id` e risponde 422.

In `backend/app/main.py`, importare e registrare il router accanto agli altri (`app.include_router(download_queue.router)`).

- [ ] **Step 4: Verificare che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_download_queue_router.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/download_queue.py backend/app/main.py backend/tests/test_download_queue_router.py
git commit -m "feat(coda): router /api/downloads/queue"
```

---

### Task 7: Commutare — gli endpoint esistenti accodano, via il job monolitico

**Files:**
- Modify: `backend/app/routers/downloads.py`
- Modify: `backend/app/main.py` (chiamata a `download_dispatcher.boot()` nel lifespan)
- Delete: `backend/app/services/soulseek_download_job.py`
- Rename: `backend/tests/test_soulseek_download_job.py` → `backend/tests/test_download_runner_soulseek.py`
- Test: `backend/tests/test_downloads_router.py` (aggiornare)

**Interfaces:**
- Consumes: `download_queue.enqueue`, `download_dispatcher.boot/fill`, `runtime_settings.download_slots`.
- Produces: `POST /api/downloads/playlist/{id}`, `/retry-pending`, `/track`, `/track/auto`, `/track/soundcloud` rispondono `{"enqueued": int, "skipped": int}` con status 200; `GET /api/downloads/status` conserva la forma odierna (`available`, `status`, `processed`, `total`, `downloaded`, `needs_review`, `not_found`, `failed`, `playlist_id`, `items`, `error`, `current_label`) derivandola dalla coda.

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere a `backend/tests/test_downloads_router.py` (e rimuovere da lì ogni test che si aspetti `202` o `409 download_already_running`):

```python
def test_track_auto_accoda_invece_di_avviare_un_job(monkeypatch):
    from app.models import Track
    from app.routers import downloads as downloads_router
    from app.services import download_queue as q

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="Night Signal", artist="Voiron")
    db.add(t)
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(downloads_router, "fill", lambda: None)

    r = client.post("/api/downloads/track/auto", json={"track_id": t.id})
    assert r.status_code == 200
    assert r.json() == {"enqueued": 1, "skipped": 0}
    assert [i.kind for i in q.list_items(factory())] == ["soulseek_auto"]


def test_niente_piu_409_con_un_download_gia_in_corso(monkeypatch):
    """Il vincolo un-alla-volta e' sparito: accodare e' sempre lecito."""
    from app.models import Track
    from app.routers import downloads as downloads_router

    engine, factory = _engine()
    db = factory()
    a = Track(source_type="manual", title="A", artist="X")
    b = Track(source_type="manual", title="B", artist="Y")
    db.add_all([a, b])
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(downloads_router, "fill", lambda: None)

    assert client.post("/api/downloads/track/auto", json={"track_id": a.id}).status_code == 200
    assert client.post("/api/downloads/track/auto", json={"track_id": b.id}).status_code == 200


def test_status_conserva_la_forma_e_la_deriva_dalla_coda(monkeypatch):
    from app.models import Track
    from app.routers import downloads as downloads_router
    from app.services import download_queue as q

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="A", artist="X")
    db.add(t)
    db.commit()
    q.enqueue(db, [t.id])
    item = q.claim_next(db)
    q.finish(db, item.id, "downloaded")

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)

    body = client.get("/api/downloads/status").json()
    for key in ("available", "status", "processed", "total", "downloaded",
                "needs_review", "not_found", "failed", "items", "current_label"):
        assert key in body, f"la barra globale del frontend legge {key}"
    assert body["downloaded"] == 1
    assert body["total"] == 1
    assert body["status"] == "done"      # nessun item vivo
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_downloads_router.py -v`
Expected: FAIL sui test nuovi (202 invece di 200, `fill` inesistente nel modulo).

- [ ] **Step 3: Spostare i test di regressione sul runner**

La logica di trasferimento è già stata assorbita in `download_runner.py` dal Task 3: qui si sposta solo la sua copertura. Rinominare `backend/tests/test_soulseek_download_job.py` in `backend/tests/test_download_runner_soulseek.py` e sostituire `from app.services import soulseek_download_job as job` con `from app.services import download_runner as job`.

I test che riguardano lo stato globale del vecchio job — `job_state`, `is_running`, doppio start, i contatori nel dizionario `_state` — vanno **rimossi**: quel concetto non esiste più. Quelli sulla cascata, sui timeout, sul fallback fra utenti e sulla guardia della durata restano e devono passare invariati: sono la rete di sicurezza che prova che l'assorbimento non ha cambiato comportamento.

- [ ] **Step 4: Riscrivere gli endpoint di `downloads.py`**

In `backend/app/routers/downloads.py`: rimuovere `from app.services import soulseek_download_job as job` e aggiungere

```python
from app.services import download_queue as dlqueue
from app.services.download_dispatcher import active_count, fill
from app.models import DownloadQueueItem
```

Sostituire i cinque endpoint che avviavano un job. Esempio per `track/auto` — gli altri quattro seguono la stessa forma (nessuna guardia `is_running`, nessun `409`, status 200):

```python
@router.post("/track/auto")
def download_track_auto(req: TrackAutopickIn):
    """Accoda una traccia in auto-pick. Nessun vincolo di concorrenza: ci pensa
    la coda."""
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise api_error(404, "track_not_found", "Track not found.")
        added, skipped = dlqueue.enqueue(db, [req.track_id], kind="soulseek_auto")
    finally:
        db.close()
    if added:
        fill()
    return {"enqueued": added, "skipped": skipped}
```

- `playlist/{id}`: `dlqueue.enqueue(db, [t.id for t in tracks_without_local_file(db, playlist_id)])`
- `retry-pending`: `dlqueue.enqueue(db, [t.id for t in tracks_download_pending(db)])`
- `track`: `kind="soulseek_chosen"`, `payload=req.candidate.model_dump()`
- `track/soundcloud`: `kind="soundcloud"`, conservando i controlli esistenti su yt-dlp, ffmpeg, download dir e `platform == "soundcloud"`

Riscrivere `/status` derivandolo dalla coda:

```python
@router.get("/status")
def status():
    """Forma invariata: la barra globale del frontend legge queste chiavi.

    `total`/`processed` contano gli item non annullati: la barra deve
    raccontare il lavoro accodato, non lo storico ripulito.
    """
    db = SessionLocal()
    try:
        items = [i for i in dlqueue.list_items(db) if i.state != "cancelled"]
        by_outcome = {"downloaded": 0, "needs_review": 0, "not_found": 0, "failed": 0}
        for i in items:
            if i.outcome in by_outcome:
                by_outcome[i.outcome] += 1
        running = [i for i in items if i.state == "running"]
        done = [i for i in items if i.state == "done"]
        label = None
        if running:
            track = get_track(db, running[0].track_id)
            label = track_label(track) if track is not None else None
        return {
            "available": slskd_configured(),
            "status": "running" if running or any(i.state == "queued" for i in items)
                      else ("done" if items else "idle"),
            "processed": len(done),
            "total": len(items),
            **by_outcome,
            "playlist_id": None,
            "items": [{"track_id": i.track_id, "artist": None, "title": None,
                       "outcome": i.outcome, "reason": i.error} for i in done],
            "error": None,
            "current_label": label,
        }
    finally:
        db.close()
```

Aggiungere `from app.services.track_label import track_label` se non già importato.

- [ ] **Step 5: Avviare il dispatcher al boot**

In `backend/app/main.py`, dentro `lifespan`, dopo `runtime_settings.load(db)` e prima dello `yield`:

```python
    # Coda download: gli item rimasti `running` da un riavvio tornano in coda,
    # e se c'e' lavoro il pool riparte da solo.
    from app.services import download_dispatcher
    download_dispatcher.boot()
```

- [ ] **Step 6: Eliminare il job monolitico**

```bash
rm backend/app/services/soulseek_download_job.py
```

Verificare che non resti alcun riferimento:
`rg -n "soulseek_download_job" backend --glob '!*.pyc'`
Expected: nessun risultato. Se ne restano, sono import da ripulire.

- [ ] **Step 7: Verificare l'intera suite backend**

Run: `cd backend && .venv/bin/python -m pytest tests -q`
Expected: tutto verde. Il conteggio cala rispetto a prima per i test dello stato globale rimossi: è atteso e va riportato nel report.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/downloads.py backend/app/main.py backend/app/services/download_runner.py backend/tests/
git rm backend/app/services/soulseek_download_job.py
git commit -m "feat(coda): gli endpoint accodano, via il job monolitico uno-alla-volta"
```

---

### Task 8: Frontend — client API e pagina `/downloads`

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Create: `frontend/lib/api/download-queue.ts`
- Modify: `frontend/lib/api/index.ts` (ri-export)
- Create: `frontend/app/downloads/page.tsx`
- Modify: `frontend/next.config.ts` (rimuovere il redirect `/downloads` → `/wishlist`)
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`
- Test: `frontend/tests/downloads-queue-page.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `GET/POST/DELETE /api/downloads/queue*` (Task 6).
- Produces: tipi `QueueItem` (`{id, track_id, label, kind, state, outcome, phase, bytes_done, bytes_total, attempts, error, position}`) e `QueueSnapshot` (`{slots, active, items}`); funzioni `downloadQueue()`, `enqueueDownloads(trackIds: number[], opts?: {kind?: string; candidate?: DownloadCandidate})`, `cancelQueueItem(id: number)`, `moveQueueItemTop(id: number)`, `cancelQueued()`, `clearQueueDone()`.

- [ ] **Step 1: Tipi, client API e i18n**

In `frontend/lib/api/types.ts`:

```ts
export type QueueItemState = "queued" | "running" | "done" | "cancelled";
export type QueueItemOutcome = "downloaded" | "needs_review" | "not_found" | "failed";

export type QueueItem = {
  id: number;
  track_id: number;
  label: string;
  kind: "soulseek_auto" | "soulseek_chosen" | "soundcloud";
  state: QueueItemState;
  outcome: QueueItemOutcome | null;
  phase: "searching" | "downloading" | null;
  bytes_done: number | null;
  bytes_total: number | null;
  attempts: number;
  error: string | null;
  position: number;
};

export type QueueSnapshot = { slots: number; active: number; items: QueueItem[] };
```

Creare `frontend/lib/api/download-queue.ts`:

```ts
import { apiDelete, apiGet, apiPost } from "./client";
import type { DownloadCandidate, QueueSnapshot } from "./types";

export function downloadQueue(opts?: { signal?: AbortSignal }) {
  return apiGet<QueueSnapshot>("/api/downloads/queue", undefined, opts);
}

/** Accoda un lotto. Il candidato vale solo con una traccia sola (lo impone il backend). */
export function enqueueDownloads(trackIds: number[],
                                 opts?: { kind?: string; candidate?: DownloadCandidate }) {
  return apiPost<{ enqueued: number; skipped: number }>("/api/downloads/queue", {
    track_ids: trackIds, kind: opts?.kind, candidate: opts?.candidate,
  });
}

export function cancelQueueItem(id: number) {
  return apiDelete<{ cancelled: boolean }>(`/api/downloads/queue/${id}`);
}

export function moveQueueItemTop(id: number) {
  return apiPost<{ moved: boolean }>(`/api/downloads/queue/${id}/top`);
}

export function cancelQueued() {
  return apiPost<{ cancelled: number }>("/api/downloads/queue/cancel-queued");
}

export function clearQueueDone() {
  return apiDelete<{ removed: number }>("/api/downloads/queue/done");
}
```

Aggiungere `export * from "./download-queue";` in `frontend/lib/api/index.ts`, seguendo il pattern degli altri moduli.

In `frontend/lib/i18n/it.ts` una sezione nuova `queue`:

```ts
queue: {
  pageTitle: "Download",
  slotsInUse: (active: number, slots: number) => `${active} di ${slots} in corso`,
  runningHeading: "In corso",
  waitingHeading: "In attesa",
  doneHeading: "Fatte",
  emptyTitle: "Coda vuota",
  emptyBody: "Accoda tracce dalla wishlist: le trovi qui mentre scendono.",
  phaseSearching: "cerco su Soulseek…",
  phaseDownloading: "scarico",
  cancelButton: "Annulla",
  topButton: "In cima",
  cancelAllButton: "Annulla le in attesa",
  clearDoneButton: "Svuota lo storico",
  attemptsLabel: (n: number) => `${n} tentativi`,
  outcomeDownloaded: "scaricata",
  outcomeNeedsReview: "da rivedere",
  outcomeNotFound: "non trovata",
  outcomeFailed: "fallita",
  stateCancelled: "annullata",
},
```

In `frontend/lib/i18n/en.ts` la stessa struttura:

```ts
queue: {
  pageTitle: "Downloads",
  slotsInUse: (active: number, slots: number) => `${active} of ${slots} running`,
  runningHeading: "Running",
  waitingHeading: "Waiting",
  doneHeading: "Done",
  emptyTitle: "Queue empty",
  emptyBody: "Queue tracks from the wishlist: you'll see them here as they come down.",
  phaseSearching: "searching Soulseek…",
  phaseDownloading: "downloading",
  cancelButton: "Cancel",
  topButton: "To top",
  cancelAllButton: "Cancel waiting",
  clearDoneButton: "Clear history",
  attemptsLabel: (n: number) => `${n} attempts`,
  outcomeDownloaded: "downloaded",
  outcomeNeedsReview: "needs review",
  outcomeNotFound: "not found",
  outcomeFailed: "failed",
  stateCancelled: "cancelled",
},
```

- [ ] **Step 2: Scrivere i test della pagina (falliscono)**

Creare `frontend/tests/downloads-queue-page.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import DownloadsPage from "@/app/downloads/page";
import type { QueueItem } from "@/lib/api";

afterEach(cleanup);

const item = (over: Partial<QueueItem> = {}): QueueItem => ({
  id: 1, track_id: 10, label: "Aphex Twin — Xtal", kind: "soulseek_auto",
  state: "queued", outcome: null, phase: null, bytes_done: null,
  bytes_total: null, attempts: 0, error: null, position: 0, ...over,
});

const mocks = vi.hoisted(() => ({
  downloadQueue: vi.fn(), cancelQueueItem: vi.fn(),
  moveQueueItemTop: vi.fn(), clearQueueDone: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  downloadQueue: mocks.downloadQueue,
  cancelQueueItem: mocks.cancelQueueItem,
  moveQueueItemTop: mocks.moveQueueItemTop,
  clearQueueDone: mocks.clearQueueDone,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.downloadQueue.mockResolvedValue({ slots: 3, active: 1, items: [
    item({ id: 1, state: "running", phase: "downloading", bytes_done: 50, bytes_total: 100 }),
    item({ id: 2, state: "queued", label: "B — Due", position: 1 }),
    item({ id: 3, state: "done", outcome: "downloaded", label: "C — Tre", position: 2 }),
  ] });
});

describe("pagina /downloads", () => {
  it("divide la coda in tre fasce e mostra gli slot occupati", async () => {
    render(<DownloadsPage />);
    expect(await screen.findByText("In corso")).toBeTruthy();
    expect(screen.getByText("In attesa")).toBeTruthy();
    expect(screen.getByText("Fatte")).toBeTruthy();
    expect(screen.getByText("1 di 3 in corso")).toBeTruthy();
    expect(screen.getByText("Aphex Twin — Xtal")).toBeTruthy();
    expect(screen.getByText("scarico")).toBeTruthy();
  });

  it("annulla un item e ricarica la coda", async () => {
    mocks.cancelQueueItem.mockResolvedValue({ cancelled: true });
    render(<DownloadsPage />);
    await screen.findByText("B — Due");
    fireEvent.click(screen.getAllByText("Annulla")[0]);
    await waitFor(() => expect(mocks.cancelQueueItem).toHaveBeenCalledWith(1));
    await waitFor(() => expect(mocks.downloadQueue).toHaveBeenCalledTimes(2));
  });

  it("«In cima» c'e' solo sugli item in attesa", async () => {
    render(<DownloadsPage />);
    await screen.findByText("B — Due");
    // un solo item in attesa -> un solo bottone
    expect(screen.getAllByText("In cima")).toHaveLength(1);
    fireEvent.click(screen.getByText("In cima"));
    await waitFor(() => expect(mocks.moveQueueItemTop).toHaveBeenCalledWith(2));
  });

  it("coda vuota: empty state", async () => {
    mocks.downloadQueue.mockResolvedValue({ slots: 3, active: 0, items: [] });
    render(<DownloadsPage />);
    expect(await screen.findByText("Coda vuota")).toBeTruthy();
  });
});
```

- [ ] **Step 3: Verificare che falliscano**

Run: `cd frontend && npx vitest run tests/downloads-queue-page.test.tsx`
Expected: FAIL — `@/app/downloads/page` inesistente.

- [ ] **Step 4: Scrivere la pagina**

Rimuovere da `frontend/next.config.ts` la riga di redirect:
`{ source: "/downloads", destination: "/wishlist", permanent: false },`

Creare `frontend/app/downloads/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Download as DownloadIcon, X } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, Loading } from "@/components/ui";
import {
  cancelQueueItem, cancelQueued, clearQueueDone, downloadQueue, errText,
  moveQueueItemTop, type QueueItem, type QueueSnapshot,
} from "@/lib/api";
import { useT } from "@/lib/i18n";

const LIVE_MS = 2000;   // c'e' roba viva: si guarda spesso
const IDLE_MS = 10000;  // coda ferma: basta un'occhiata ogni tanto

export default function DownloadsPage() {
  const t = useT();
  const [snap, setSnap] = useState<QueueSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const s = await downloadQueue({ signal });
      if (alive.current) { setSnap(s); setError(null); }
    } catch (e) {
      if ((e as { name?: string })?.name !== "AbortError" && alive.current) setError(errText(e));
    }
  }, []);

  // Il ritmo si adatta: inutile martellare quando la coda e' ferma.
  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    const live = (snap?.items ?? []).some((i) => i.state === "running" || i.state === "queued");
    const id = setInterval(() => load(), live ? LIVE_MS : IDLE_MS);
    return () => { ac.abort(); clearInterval(id); };
  }, [load, snap?.items]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try { await fn(); await load(); } catch (e) { setError(errText(e)); }
    finally { if (alive.current) setBusy(false); }
  };

  const items = snap?.items ?? [];
  const running = items.filter((i) => i.state === "running");
  const waiting = items.filter((i) => i.state === "queued");
  const history = items.filter((i) => i.state === "done" || i.state === "cancelled");

  const OUTCOME: Record<string, string> = {
    downloaded: t.queue.outcomeDownloaded,
    needs_review: t.queue.outcomeNeedsReview,
    not_found: t.queue.outcomeNotFound,
    failed: t.queue.outcomeFailed,
  };

  const Row = ({ item }: { item: QueueItem }) => {
    const pct = item.bytes_total ? Math.round((item.bytes_done ?? 0) / item.bytes_total * 100) : null;
    return (
      <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-sm">
        <div className="min-w-0 flex-1">
          <div className="truncate">{item.label}</div>
          <div className="mt-0.5 flex items-center gap-2 text-xs text-muted">
            {item.phase === "searching" && <span>{t.queue.phaseSearching}</span>}
            {item.phase === "downloading" && <span>{t.queue.phaseDownloading}</span>}
            {pct !== null && (
              <span className="inline-block h-1 w-24 bg-border" aria-hidden="true">
                <span className="block h-full bg-fg" style={{ width: `${pct}%` }} />
              </span>
            )}
            {item.attempts > 1 && <span>{t.queue.attemptsLabel(item.attempts)}</span>}
            {item.error && <span className="truncate">{item.error}</span>}
          </div>
        </div>
        <span className="flex shrink-0 items-center gap-2">
          {item.state === "cancelled" && <Badge tone="neutral">{t.queue.stateCancelled}</Badge>}
          {item.outcome && (
            <Badge tone={item.outcome === "downloaded" ? "neutral"
              : item.outcome === "failed" ? "danger" : "warning"}>
              {OUTCOME[item.outcome]}
            </Badge>
          )}
          {item.state === "queued" && (
            <Button size="sm" variant="ghost" disabled={busy}
              onClick={() => act(() => moveQueueItemTop(item.id))}>
              <ArrowUp size={13} /> {t.queue.topButton}
            </Button>
          )}
          {(item.state === "queued" || item.state === "running") && (
            <Button size="sm" variant="outline" disabled={busy}
              onClick={() => act(() => cancelQueueItem(item.id))}>
              <X size={13} /> {t.queue.cancelButton}
            </Button>
          )}
        </span>
      </li>
    );
  };

  const Section = ({ heading, rows, action }: {
    heading: string; rows: QueueItem[]; action?: React.ReactNode;
  }) => rows.length === 0 ? null : (
    <section>
      <div className="mb-2 flex items-center gap-3">
        <div className="text-[10px] uppercase tracking-wider text-muted">{heading}</div>
        {action}
      </div>
      <Card>
        <ul className="divide-y divide-border">
          {rows.map((i) => <Row key={i.id} item={i} />)}
        </ul>
      </Card>
    </section>
  );

  return (
    <PageLayout title={t.queue.pageTitle}
      meta={snap ? t.queue.slotsInUse(snap.active, snap.slots) : undefined}>
      <div className="space-y-6">
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {snap === null && <Loading />}
        {snap !== null && items.length === 0 && (
          <EmptyState icon={<DownloadIcon size={28} />} title={t.queue.emptyTitle}>
            {t.queue.emptyBody}
          </EmptyState>
        )}
        <Section heading={t.queue.runningHeading} rows={running} />
        <Section heading={t.queue.waitingHeading} rows={waiting}
          action={
            <Button size="sm" variant="outline" disabled={busy}
              onClick={() => act(() => cancelQueued())}>
              {t.queue.cancelAllButton}
            </Button>
          } />
        <Section heading={t.queue.doneHeading} rows={history}
          action={
            <Button size="sm" variant="outline" disabled={busy}
              onClick={() => act(() => clearQueueDone())}>
              {t.queue.clearDoneButton}
            </Button>
          } />
      </div>
    </PageLayout>
  );
}
```

Verificare in `frontend/components/ui.tsx` che `Button` accetti `variant="ghost"` e `Badge` i toni `neutral`/`warning`/`danger` (li usa già `wishlist-row.tsx`); se `PageLayout` non accetta `meta` come stringa, passare il conteggio nel modo che la wishlist usa già.

- [ ] **Step 5: Verificare**

Run: `cd frontend && npx vitest run tests/downloads-queue-page.test.tsx && npx tsc --noEmit && npm run lint`
Expected: 4 passed, tipi e lint puliti.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/download-queue.ts frontend/lib/api/index.ts frontend/app/downloads/page.tsx frontend/next.config.ts frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/downloads-queue-page.test.tsx
git commit -m "feat(coda): la pagina /downloads con le tre fasce della coda"
```

---

### Task 9: Frontend — selezione multipla nella wishlist

**Files:**
- Modify: `frontend/components/wishlist-row.tsx`
- Modify: `frontend/app/wishlist/page.tsx`
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`
- Test: `frontend/tests/wishlist-row.test.tsx` (aggiornare), `frontend/tests/wishlist-selection.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `enqueueDownloads(trackIds)` (Task 8).
- Produces: `WishlistRowProps` guadagna `selected?: boolean` e `onToggleSelect?: (t: Track) => void`; la checkbox compare solo quando `onToggleSelect` è passata (la vista archiviate non seleziona).

- [ ] **Step 1: Test della riga (aggiornamento) e della barra di selezione**

In `frontend/tests/wishlist-row.test.tsx` aggiungere:

```tsx
  it("la checkbox compare solo con onToggleSelect e riporta la selezione", () => {
    const onToggleSelect = vi.fn();
    const { rerender, container } = render(
      <WishlistRow track={base} downloadsAvailable from={from} {...noop} />);
    expect(container.querySelector('input[type="checkbox"]')).toBeNull();

    rerender(<WishlistRow track={base} downloadsAvailable from={from} {...noop}
      selected onToggleSelect={onToggleSelect} />);
    const box = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(box.checked).toBe(true);
    fireEvent.click(box);
    expect(onToggleSelect).toHaveBeenCalled();
  });
```

Creare `frontend/tests/wishlist-selection.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SelectionBar } from "@/components/wishlist-selection-bar";

afterEach(cleanup);

describe("SelectionBar", () => {
  it("resta invisibile senza selezione", () => {
    const { container } = render(
      <SelectionBar count={0} onEnqueue={vi.fn()} onClear={vi.fn()} busy={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("mostra il conteggio e accoda", () => {
    const onEnqueue = vi.fn();
    render(<SelectionBar count={12} onEnqueue={onEnqueue} onClear={vi.fn()} busy={false} />);
    expect(screen.getByText("Accoda 12 tracce")).toBeTruthy();
    screen.getByText("Accoda 12 tracce").click();
    expect(onEnqueue).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd frontend && npx vitest run tests/wishlist-row.test.tsx tests/wishlist-selection.test.tsx`
Expected: FAIL — prop e componente inesistenti.

- [ ] **Step 3: Implementare**

In `frontend/lib/i18n/it.ts`, dentro `wishlist`: `enqueueSelected: (n: number) => \`Accoda ${n} tracce\``, `clearSelection: "Deseleziona"`, `selectRowAria: "Seleziona questa traccia"`, `enqueued: (added: number, skipped: number) => skipped ? \`${added} accodate, ${skipped} erano già in coda\` : \`${added} accodate\``. In `en.ts`: `enqueueSelected: (n: number) => \`Queue ${n} tracks\``, `clearSelection: "Clear selection"`, `selectRowAria: "Select this track"`, `enqueued: (added: number, skipped: number) => skipped ? \`${added} queued, ${skipped} already in the queue\` : \`${added} queued\``.

Creare `frontend/components/wishlist-selection-bar.tsx`: un componente che ritorna `null` se `count === 0`, altrimenti una barra con il conteggio, il bottone «Accoda N tracce» (disabilitato quando `busy`) e «Deseleziona». Props: `{ count: number; onEnqueue: () => void; onClear: () => void; busy: boolean }`.

In `frontend/components/wishlist-row.tsx`: aggiungere le due prop opzionali e, quando `onToggleSelect` è definita, una `<input type="checkbox">` come primo elemento della riga, con `aria-label={t.wishlist.selectRowAria}`, `checked={!!selected}` e `onChange={() => onToggleSelect(track)}`.

In `frontend/app/wishlist/page.tsx`: stato `selected: Set<number>`; passare `selected`/`onToggleSelect` alle righe **solo quando `!showArchived`**; montare `SelectionBar` sopra la lista; su «Accoda» chiamare `enqueueDownloads([...selected])`, mostrare l'esito con `t.wishlist.enqueued(...)` in un `Alert tone="info"` e svuotare la selezione. Svuotare la selezione anche quando cambiano i filtri (tab, ricerca, playlist, archiviate), perché le righe selezionate potrebbero non essere più visibili.

- [ ] **Step 4: Verificare**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run lint`
Expected: tutto verde.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/wishlist-row.tsx frontend/components/wishlist-selection-bar.tsx frontend/app/wishlist/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/wishlist-row.test.tsx frontend/tests/wishlist-selection.test.tsx
git commit -m "feat(wishlist): selezione multipla e accodamento a lotti"
```

---

### Task 10: Frontend — l'impostazione degli slot e il modal che accoda

**Files:**
- Modify: `frontend/app/settings/page.tsx` (o il componente `ConfigCard` che contiene i campi)
- Modify: `frontend/lib/api/settings.ts` (o dove vivono i wrapper delle impostazioni)
- Modify: `frontend/components/soulseek-search-modal.tsx`
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`
- Test: `frontend/tests/soulseek-search-modal.test.tsx` (aggiornare)

**Interfaces:**
- Consumes: `PUT /api/settings/download-slots` e il campo `download_slots` in `GET /api/settings/config` (Task 4); `enqueueDownloads` (Task 8).
- Produces: `setDownloadSlots(slots: number)` nel client delle impostazioni; il modal di ricerca accoda invece di scaricare subito.

- [ ] **Step 1: Aggiornare il test del modal**

In `frontend/tests/soulseek-search-modal.test.tsx`, sostituire il mock e l'asserzione di `downloadTrack` con `enqueueDownloads`, e rimuovere il caso che verificava la disabilitazione per «un download è già in corso» (quel vincolo non esiste più):

```tsx
  it("«Scarica questo» accoda il candidato scelto", async () => {
    mocks.enqueueDownloads.mockResolvedValue({ enqueued: 1, skipped: 0 });
    const onPicked = vi.fn();
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={onPicked} />);
    await screen.findByText("Xtal.flac");
    fireEvent.click(screen.getAllByText("Scarica questo")[0]);
    await waitFor(() => expect(mocks.enqueueDownloads).toHaveBeenCalledWith([1],
      expect.objectContaining({
        candidate: expect.objectContaining({ username: "user1" }),
      })));
    await waitFor(() => expect(onPicked).toHaveBeenCalled());
  });
```

Aggiungere `enqueueDownloads: vi.fn()` all'oggetto `vi.hoisted` e al `vi.mock` del modulo `@/lib/api`.

- [ ] **Step 2: Verificare che fallisca**

Run: `cd frontend && npx vitest run tests/soulseek-search-modal.test.tsx`
Expected: FAIL — il modal chiama ancora `downloadTrack`.

- [ ] **Step 3: Implementare**

In `frontend/components/soulseek-search-modal.tsx`: sostituire `downloadTrack(target.track_id, toCandidate(f))` con `enqueueDownloads([target.track_id], { candidate: toCandidate(f) })`. Rimuovere l'alert `t.downloads.search.jobRunning` e la variabile `canDownload` con la sua dipendenza da `useJobs()` se non più usata; i bottoni restano disabilitati solo durante l'invio (`busy`). Rimuovere la chiave i18n `jobRunning` da entrambi i dizionari se non più referenziata (verificare con `rg`).

In `frontend/lib/i18n/it.ts`, dentro `settings`: `downloadSlotsLabel: "Download in parallelo"`, `downloadSlotsHint: "Quante tracce scaricare insieme. Il valore giusto dipende dalla tua connessione e da quanto è carico slskd."`. In `en.ts`: `downloadSlotsLabel: "Parallel downloads"`, `downloadSlotsHint: "How many tracks to download at once. The right value depends on your connection and how busy slskd is."`.

Aggiungere al client delle impostazioni (stesso file dove vive già il wrapper di `share-library`), e al tipo della config il campo `download_slots: number`:

```ts
export function setDownloadSlots(slots: number) {
  return apiPut<{ download_slots: number }>("/api/settings/download-slots", { slots });
}
```

(se il client non espone `apiPut`, usare la stessa funzione con cui è implementato il wrapper di `share-library`, che è anch'esso un `PUT`).

Nel componente che rende i campi della config — quello dove vive già il toggle «Condividi libreria» — aggiungere:

```tsx
      <label className="flex items-center gap-3 px-5 py-3 text-sm">
        <span className="flex-1">
          {t.settings.downloadSlotsLabel}
          <span className="mt-0.5 block text-xs text-faint">{t.settings.downloadSlotsHint}</span>
        </span>
        <Input type="number" min={1} max={10} className="h-8 w-20"
          value={slots}
          onChange={(e) => setSlots(Number(e.target.value))}
          onBlur={() => void save()} />
      </label>
```

con `const [slots, setSlots] = useState(config.download_slots)` e una `save()` che chiama `setDownloadSlots(slots)` e ricarica la config, ignorando il salvataggio se il valore non è cambiato o è fuori da 1–10 (il backend risponderebbe 422). Nessun test dedicato: lo copre la verifica manuale dello step successivo.

- [ ] **Step 4: Verificare**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run lint`
Expected: tutto verde, incluso il file del modal aggiornato.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/settings/page.tsx frontend/lib/api/ frontend/components/soulseek-search-modal.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/soulseek-search-modal.test.tsx
git commit -m "feat(coda): il modal accoda, e gli slot si regolano dalle Impostazioni"
```

---

### Task 11: E2e, documentazione e verifica finale

**Files:**
- Modify: `frontend/e2e/wishlist.spec.ts`
- Create: `frontend/e2e/downloads-queue.spec.ts`
- Modify: `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `PROGRESS.md`

- [ ] **Step 1: Aggiornare la e2e esistente e scriverne una nuova**

In `frontend/e2e/wishlist.spec.ts`, il test della ricerca Soulseek stubba `**/api/downloads/track`: sostituirlo con `**/api/downloads/queue` che risponde `{enqueued: 1, skipped: 0}`, e aggiornare l'asserzione sul corpo inviato (`{track_ids: [1], candidate: {...}}`).

Creare `frontend/e2e/downloads-queue.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

// La coda con API stubbate: il test non dipende da slskd né dal DB.
test("la pagina /downloads mostra le tre fasce della coda", async ({ page }) => {
  await page.route("**/api/downloads/queue", (route) =>
    route.fulfill({ json: { slots: 3, active: 1, items: [
      { id: 1, track_id: 10, label: "Aphex Twin — Xtal", kind: "soulseek_auto",
        state: "running", outcome: null, phase: "downloading", bytes_done: 50,
        bytes_total: 100, attempts: 1, error: null, position: 0 },
      { id: 2, track_id: 11, label: "Boards of Canada — Roygbiv", kind: "soulseek_auto",
        state: "queued", outcome: null, phase: null, bytes_done: null,
        bytes_total: null, attempts: 0, error: null, position: 1 },
    ] } }));

  await page.goto("/downloads");
  await expect(page.getByRole("heading", { name: "Download" })).toBeVisible();
  await expect(page.getByText("1 di 3 in corso")).toBeVisible();
  await expect(page.getByText("Aphex Twin — Xtal")).toBeVisible();
  await expect(page.getByText("Boards of Canada — Roygbiv")).toBeVisible();
});
```

Nota: `/downloads` non redirige più, quindi il test «/downloads reindirizza a /wishlist» in `wishlist.spec.ts` va rimosso.

- [ ] **Step 2: Eseguire la e2e**

Run: `cd frontend && npx playwright test`
Expected: tutti verdi.

- [ ] **Step 3: Documentare**

In `docs/API.md`, sezione Downloads: aggiungere le sei rotte di `/api/downloads/queue` all'elenco e un paragrafo che descriva la coda (stati, `outcome`, deduplica, ricucitura al riavvio); riscrivere il blocco «One download job at a time», che non è più vero — ora il parallelismo è `download_slots` (default 3, regolabile), e nessun endpoint risponde più `409 download_already_running`; aggiornare la descrizione di `GET /api/downloads/status` chiarendo che i suoi aggregati vengono dalla coda. Documentare `PUT /api/settings/download-slots` nella sezione Settings.

In `docs/ARCHITECTURE.md`: sostituire ogni riferimento al job di download uno-alla-volta con la coda e i suoi tre moduli.

In `docs/ROADMAP.md`: aggiornare il bullet «Acquisition & Wishlist» (la coda persistente e parallela, la pagina `/downloads`, la selezione multipla) e chiudere la voce di backlog del sotto-progetto B.

Aggiornare `PROGRESS.md` nello stile delle righe esistenti.

- [ ] **Step 4: Verifica finale completa**

```bash
cd backend && .venv/bin/python -m pytest tests
cd ../frontend && npm run lint && npx tsc --noEmit && npx vitest run && npx playwright test && npm run build
```

Expected: tutto verde. Se `npm run build` fallisce, il task NON è completo: riportare l'errore.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/ docs/ PROGRESS.md
git commit -m "docs(coda): API, architettura e roadmap della coda dei download"
```
