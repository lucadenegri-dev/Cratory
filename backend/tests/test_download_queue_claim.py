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
    assert q.finish(db, item.id, "needs_review", error="durata non corrisponde") is True
    db.refresh(item)
    assert item.state == "done"
    assert item.outcome == "needs_review"
    assert item.error == "durata non corrisponde"
    assert item.finished_at is not None


def test_finish_non_resuscita_un_item_annullato_da_un_altra_sessione():
    """Riproduce il rilievo: claim -> cancel da un'altra sessione -> finish.

    Un worker rivendica l'item, l'utente lo annulla da un'altra sessione
    mentre il worker sta ancora scaricando; quando il worker ignaro chiama
    finish() l'item deve restare cancelled, non tornare done/downloaded.
    """
    factory = _factory()
    _seed(factory, 1)
    db = factory()
    item = q.claim_next(db)
    altra = factory()
    assert q.cancel(altra, item.id) is True
    altra.close()

    assert q.finish(db, item.id, "downloaded") is False

    verifica = factory()
    ricaricato = verifica.get(DownloadQueueItem, item.id)
    assert ricaricato.state == "cancelled"
    assert ricaricato.outcome is None
    verifica.close()


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


def test_move_to_top_rifiuta_un_item_non_in_attesa():
    """'In cima' vale solo per un item in coda: running o concluso restano fermi."""
    factory = _factory()
    _seed(factory, 3)
    db = factory()
    ordine_prima = [i.id for i in q.list_items(db)]

    in_corso = q.claim_next(db)             # il primo, ora running
    assert q.move_to_top(db, in_corso.id) is False
    assert [i.id for i in q.list_items(db)] == ordine_prima

    assert q.finish(db, in_corso.id, "downloaded") is True
    assert q.move_to_top(db, in_corso.id) is False
    assert [i.id for i in q.list_items(db)] == ordine_prima


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
    db.refresh(fatto)
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
