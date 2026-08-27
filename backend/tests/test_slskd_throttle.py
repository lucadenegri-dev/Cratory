"""Il 429 di slskd: una strozzatura del daemon, non colpa della traccia.

slskd serializza a livello di processo le due POST che avviano un lavoro, e
non mette in attesa chi arriva secondo: risponde 429 all'istante.

    SearchesController:   SemaphoreSlim(1, 1) + Wait(0)  -> POST /searches
    TransfersController:  SemaphoreSlim(2, 2) + Wait(0)  -> POST /transfers/downloads/{u}

Il messaggio e' lo stesso per entrambe ("Only one concurrent operation is
permitted. Wait until the previous request completes") ed e' quello che
compariva sulle tracce: con tre slot di download, i worker partivano insieme e
due su tre prendevano un 429 sulla prima POST della loro vita — la ricerca —
che risaliva fino a `run_item` e veniva scritto sulla traccia come esito
`failed`. Un lotto accodato da una playlist si bruciava in un secondo, senza
che nessun download fosse mai stato tentato.

Qui si copre la difesa a tre strati: il cancello (Cratory non fa da sola piu'
richieste concorrenti di quante slskd ne accetti), il ritentativo (un 429 da
un altro client — la web UI di slskd — non deve arrivare al chiamante) e la
classificazione (un 429 che sopravvive a tutto e' infrastruttura: l'item torna
in coda, la traccia non riceve esito).
"""
from __future__ import annotations

import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.integrations import slskd
from app.integrations.slskd import (
    SlskdClient, SlskdError, SlskdFile, slskd_unreachable,
)
from app.models import DownloadQueueItem, Track
from app.services import download_queue as q
from app.services import download_runner as runner


class _Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text
        self.content = b"x"

    def json(self):
        return self._payload


def _file() -> SlskdFile:
    return SlskdFile(username="bob", filename="bob\\x.flac", size=1, bitrate=None,
                     length=None, has_free_slot=True, queue_length=None)


class _ConcurrencyProbe:
    """http fake che misura quante POST si sovrappongono davvero.

    La POST dorme un istante: senza attesa i thread potrebbero attraversarla
    in fila indiana per caso, e il test passerebbe anche senza cancello.
    """

    def __init__(self, *, hold: float = 0.05):
        self.hold = hold
        self._lock = threading.Lock()
        self._dentro = 0
        self.massimo = 0

    def post(self, url, json=None):
        with self._lock:
            self._dentro += 1
            self.massimo = max(self.massimo, self._dentro)
        try:
            threading.Event().wait(self.hold)
            return _Resp(200, {"id": "s1"})
        finally:
            with self._lock:
                self._dentro -= 1

    def get(self, url, params=None):
        if url.endswith("/responses"):
            return _Resp(200, [])
        return _Resp(200, {"isComplete": True})

    def delete(self, url, params=None):
        return _Resp(200, {})

    def close(self):
        pass


def _in_parallelo(fn, n: int) -> None:
    threads = [threading.Thread(target=fn) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)


def test_le_ricerche_non_si_sovrappongono_mai():
    """slskd ne accetta UNA per volta: farne due insieme e' un 429 garantito."""
    probe = _ConcurrencyProbe()

    def cerca():
        SlskdClient(url="http://slskd.local:5030", api_key="k", http=probe) \
            .search("Aphex Twin", "Xtal", max_wait=0.0)

    _in_parallelo(cerca, 3)
    assert probe.massimo == 1


def test_gli_accodamenti_concorrenti_restano_due():
    """Il tetto degli accodamenti e' due, non uno: si rispecchia quello di
    slskd invece di serializzare piu' del necessario."""
    probe = _ConcurrencyProbe()

    def accoda():
        SlskdClient(url="http://slskd.local:5030", api_key="k", http=probe) \
            .enqueue_download(_file())

    _in_parallelo(accoda, 5)
    assert probe.massimo == 2


class _ThrottlingHttp:
    """Risponde 429 alle prime `quanti` POST, poi normalmente. Simula l'unico
    429 che il cancello non puo' evitare: un altro client (la web UI di slskd)
    che occupa il semaforo del daemon."""

    def __init__(self, quanti: int):
        self.rimasti = quanti
        self.tentativi = 0

    def post(self, url, json=None):
        self.tentativi += 1
        if self.rimasti > 0:
            self.rimasti -= 1
            return _Resp(429, text="Only one concurrent operation is permitted. "
                                   "Wait until the previous request completes")
        return _Resp(200, {"id": "s1"})

    def get(self, url, params=None):
        if url.endswith("/responses"):
            return _Resp(200, [])
        return _Resp(200, {"isComplete": True})

    def delete(self, url, params=None):
        return _Resp(200, {})

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _niente_attese_vere(monkeypatch):
    monkeypatch.setattr("app.integrations.slskd.THROTTLE_BACKOFF", 0.0)


def test_un_429_di_passaggio_viene_ritentato_senza_disturbare_il_chiamante():
    http = _ThrottlingHttp(quanti=2)
    client = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    assert client.search("Aphex Twin", "Xtal", max_wait=0.0) == []
    assert http.tentativi == 3          # due rifiuti, poi la buona


def test_un_429_di_passaggio_non_fa_fallire_l_accodamento():
    http = _ThrottlingHttp(quanti=1)
    client = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    client.enqueue_download(_file())    # non deve sollevare
    assert http.tentativi == 2


def test_un_429_che_non_passa_mai_e_infrastruttura():
    """Ritentato invano: allora non e' un incidente, e' il daemon che non e' in
    grado. Deve valere `slskd_unreachable` — l'item torna in coda intatto e la
    traccia NON riceve un `failed` col messaggio di slskd dentro."""
    http = _ThrottlingHttp(quanti=99)
    client = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    with pytest.raises(SlskdError) as exc_info:
        client.search("Aphex Twin", "Xtal", max_wait=0.0)
    exc = exc_info.value
    assert exc.status_code == 429
    assert slskd_unreachable(exc) is True


def test_i_tentativi_sono_limitati():
    http = _ThrottlingHttp(quanti=99)
    client = SlskdClient(url="http://slskd.local:5030", api_key="k", http=http)
    with pytest.raises(SlskdError):
        client.search("Aphex Twin", "Xtal", max_wait=0.0)
    assert http.tentativi == slskd.THROTTLE_RETRIES


# --- La coda, davanti a un 429 che non passa ------------------------------


@pytest.fixture
def factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    f = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(runner, "SessionLocal", f)
    return f


def test_una_traccia_non_si_brucia_su_un_429(factory, monkeypatch):
    """Il rilievo, per intero: la ricerca prende 429, l'item torna in coda
    INTATTO e la traccia non riceve alcun esito.

    Prima, il messaggio di slskd risaliva fino a `run_item`, che non lo
    riconosceva come infrastruttura: `failed` sull'item e sulla traccia, col
    testo del daemon dentro. Con tre slot, un lotto accodato da una playlist
    si bruciava cosi' in un secondo.
    """
    db = factory()
    track = Track(source_type="manual", artist="Bliss Inc", title="Mind 2 Mind")
    db.add(track)
    db.commit()
    q.enqueue(db, [track.id])
    item_id, track_id = q.claim_next(db).id, track.id
    db.close()

    http = _ThrottlingHttp(quanti=99)
    monkeypatch.setattr(runner, "get_slskd_client",
                        lambda: SlskdClient(url="http://slskd.local:5030",
                                            api_key="k", http=http))
    with pytest.raises(runner.SlskdUnreachable) as exc_info:
        runner.run_item(item_id)

    # Il motivo mostrato dice quale ostacolo e', non un generico "non risponde".
    assert exc_info.value.reason == "throttled"
    db = factory()
    item = db.get(DownloadQueueItem, item_id)
    track = db.get(Track, track_id)
    assert item.state == "queued"           # in attesa, non concluso
    assert item.outcome is None
    assert item.attempts == 0               # il tentativo mai avvenuto non conta
    assert track.last_download_outcome is None
    assert track.last_download_reason is None
    db.close()
