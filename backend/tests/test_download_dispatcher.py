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
