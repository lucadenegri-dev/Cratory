import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import runtime_settings as rs
from app.db import Base
from app.models import Track
from app.services import download_dispatcher as d
from app.services import download_queue as q
from app.services import download_runner as runner


@pytest.fixture(autouse=True)
def _attendi_thread_del_dispatcher(monkeypatch):
    """Ogni test lancia thread daemon veri (`d.spawn`, anche a cascata da
    `_work`/`fill`). Senza attenderli, un thread puo' sopravvivere al
    `monkeypatch` del proprio test e, dopo lo smontaggio, chiamare il vero
    `download_runner.run_item` sul DB di sessione condiviso dagli altri test
    (vedi test_boot_ricuce_i_running_e_riparte per come si crea questo DB).
    Si intercetta lo spawn per tracciare ogni thread — anche quelli nati
    durante il join, la lista cresce e l'iterazione li raccoglie comunque —
    e si attende la loro fine a fine test (timeout cosi' un thread bloccato
    non appende la suite), poi si azzera `_active` perche' nessun test lasci
    slot occupati o lavoro in volo per il successivo."""
    threads: list[threading.Thread] = []
    lock = threading.Lock()

    def _spawn_tracciato(fn):
        th = threading.Thread(target=fn, daemon=True)
        with lock:
            threads.append(th)
        th.start()

    monkeypatch.setattr(d, "spawn", _spawn_tracciato)
    yield
    for th in threads:
        th.join(timeout=5)
    d._active = 0


def _setup(monkeypatch, n_items, slots=3, slskd_available=True):
    """`slskd_available=True` di default: questi test coprono la meccanica
    degli slot, non il gate su slskd (quello e' `test_boot_...slskd_spento`),
    quindi tengono `slskd_configured()` finto-vero cosi' `claim_next` non
    esclude gli item `soulseek_auto` di prova a prescindere dal reale
    SLSKD_URL della macchina che lancia i test."""
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
    # raising=False: cosi' questo helper resta utilizzabile anche puntando a
    # una copia di download_dispatcher precedente alla correzione del rilievo
    # 1 (che non importava ancora slskd_configured), per riprodurne il bug.
    monkeypatch.setattr(d, "slskd_configured", lambda: slskd_available, raising=False)
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
    rimasto_running = q.claim_next(db)        # simula un riavvio a meta'
    db.close()
    eseguiti = []
    monkeypatch.setattr(d, "run_item", lambda item_id: eseguiti.append(item_id))
    d.boot()
    threading.Event().wait(0.3)
    assert len(eseguiti) == 2                 # entrambi ripresi
    # non solo il conteggio: proprio l'item rimasto "running" dal riavvio
    # precedente deve essere stato ricucito (rimesso "queued" da
    # requeue_stale) e ripescato da fill() — senza la ricucitura resterebbe
    # "running" per sempre e non finirebbe mai in `eseguiti`.
    assert rimasto_running.id in eseguiti


def test_boot_non_brucia_la_coda_se_slskd_non_e_configurato(monkeypatch):
    """Riproduce il rilievo: la coda ha item soulseek in attesa e l'app
    riparte con slskd non configurato (`SLSKD_URL` vuoto in produzione,
    qui `slskd_configured()` finto-falso).

    Prima della correzione `boot()`/`fill()` li rivendicava comunque
    (`running`) e il vero `run_item` chiamava `get_slskd_client()`, che
    fallisce all'istante: gli item finivano tutti `done`/`failed` e le
    tracce si beccavano un `last_download_outcome="failed"` con dentro una
    stringa tecnica come motivo — una coda intera bruciata a un riavvio
    ordinario col daemon spento. Uso apposta il vero `run_item` (non un
    finto): e' proprio la sua interazione con slskd spento che il rilievo
    contesta, un `run_item` finto non la eserciterebbe.

    Dopo la correzione gli item restano `queued`, intatti — pronti a
    ripartire da soli non appena slskd torna disponibile e qualcosa
    richiama `fill()` (un nuovo accodamento, o un altro riavvio) — e le
    tracce non ricevono alcun esito.

    `slots=1`: un solo worker alla volta, cosi' `run_item` vero non tocca
    mai il DB da due thread in contemporanea — la concorrenza reale non è
    ciò che questo test vuole esercitare, e su SQLite in-memory con
    `check_same_thread=False` produrrebbe fallimenti spuri indipendenti dal
    rilievo (la connessione condivisa non è thread-safe per accessi davvero
    simultanei)."""
    factory = _setup(monkeypatch, n_items=5, slots=1, slskd_available=False)
    # `_setup` monkeypatcha SessionLocal solo nel dispatcher: il vero
    # `run_item`, usato apposta qui, apre le sue sessioni tramite il
    # `SessionLocal` del modulo `download_runner`, che va ripuntato a parte.
    monkeypatch.setattr(runner, "SessionLocal", factory)
    d.boot()
    threading.Event().wait(0.3)
    db = factory()
    items = q.list_items(db)
    assert len(items) == 5
    assert all(i.state == "queued" for i in items)      # non bruciati a done/failed
    assert all(i.outcome is None for i in items)
    tracks = db.query(Track).all()
    assert all(t.last_download_outcome is None for t in tracks)  # nessun esito finto


def test_slskd_spento_non_blocca_un_item_soundcloud(monkeypatch):
    """`kind="soundcloud"` non passa da slskd (usa yt-dlp): la guardia del
    rilievo 1 non deve bloccarlo insieme agli item soulseek solo perche' e'
    globale sul pool. Verifica che un item soundcloud parta comunque mentre
    quello soulseek, in coda insieme a lui, resta `queued`."""
    factory = _setup(monkeypatch, n_items=0, slots=3, slskd_available=False)
    db = factory()
    t_sc = Track(source_type="manual", artist="A", title="SC", url="https://soundcloud.com/a/b")
    t_sl = Track(source_type="manual", artist="B", title="SL")
    db.add_all([t_sc, t_sl])
    db.commit()
    q.enqueue(db, [t_sc.id], kind="soundcloud")
    q.enqueue(db, [t_sl.id], kind="soulseek_auto")
    db.close()

    eseguiti = []
    monkeypatch.setattr(d, "run_item", lambda item_id: eseguiti.append(item_id))
    d.fill()
    threading.Event().wait(0.2)

    db = factory()
    items = {i.track_id: i for i in q.list_items(db)}
    assert eseguiti == [items[t_sc.id].id]           # solo il soundcloud e' partito
    assert items[t_sl.id].state == "queued"           # il soulseek resta in coda, intatto


def test_fill_su_coda_vuota_non_fa_nulla(monkeypatch):
    _setup(monkeypatch, n_items=0)
    monkeypatch.setattr(d, "run_item", lambda item_id: None)
    d.fill()
    assert d.active_count() == 0
