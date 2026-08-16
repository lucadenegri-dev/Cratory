import threading
import time

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import runtime_settings as rs
from app.db import Base
from app.integrations.slskd import SlskdError
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
    slot occupati o lavoro in volo per il successivo.

    Stesso trattamento per il riaggancio periodico (`start_retry_loop`), che
    non nasce da `spawn` ma da un `threading.Thread` proprio (serve l'handle
    per fermarlo): lo si spegne PRIMA del test, cosi' un loop acceso da un
    altro file di test non rivendica gli item di questo, e DOPO, prima dei
    join, cosi' smette di generare nuovi worker mentre li si attende. Si
    azzera anche l'interruttore su slskd: e' un global di modulo come
    `_active`, e un test che lo lascia aperto congelerebbe il successivo."""
    d.stop_retry_loop()
    d._slskd_blocked_until = 0.0
    d._consecutive_failures = 0
    d._last_failure_reason = None
    threads: list[threading.Thread] = []
    lock = threading.Lock()

    def _spawn_tracciato(fn):
        th = threading.Thread(target=fn, daemon=True)
        with lock:
            threads.append(th)
        th.start()

    monkeypatch.setattr(d, "spawn", _spawn_tracciato)
    yield
    d.stop_retry_loop()
    for th in threads:
        th.join(timeout=5)
    d._active = 0
    d._slskd_blocked_until = 0.0
    d._consecutive_failures = 0
    d._last_failure_reason = None


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
    ordinario col daemon spento.

    Dopo l'arrivo dell'interruttore (rilievo separato) questo test non
    discriminava piu': mutare solo il gate (`slskd_configured`) non basta a
    dimostrare che `claim_next` esclude l'item PRIMA che `run_item` tocchi
    slskd, perche' se per regressione l'item venisse comunque rivendicato,
    `get_slskd_client()` vero leggerebbe lo `SLSKD_URL` reale del `.env` dello
    sviluppatore — spesso valorizzato (slskd locale su :5030, vedi memoria di
    progetto) — aprirebbe un client reale, fallirebbe la ricerca contro un
    daemon spento o irraggiungibile, e l'interruttore rimetterebbe comunque
    l'item `queued`: stesso stato osservabile di oggi, ma passando da una
    VERA chiamata di rete invece che dall'esclusione a monte che il rilievo
    originale voleva verificare. Si sostituisce percio' `get_slskd_client`
    con qualcosa che fa fallire il test se viene invocato: cosi' l'assenza di
    chiamate di rete e' garantita, e la regressione (item rivendicato quando
    non dovrebbe) fa fallire il test sul posto giusto, non per un effetto
    collaterale dell'interruttore.

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

    def _client_non_atteso():
        raise AssertionError(
            "get_slskd_client() chiamato: claim_next avrebbe dovuto escludere "
            "l'item PRIMA, senza toccare slskd — nessuna chiamata di rete attesa qui.")

    monkeypatch.setattr(runner, "get_slskd_client", _client_non_atteso)
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


# --- L'interruttore su slskd e il riaggancio periodico ---------------------


class _ClientSpento:
    """slskd configurato (URL in `.env`, cartella impostata) ma il processo non
    c'e': httpx alza `ConnectError` e il client la avvolge in `SlskdError`
    con `raise ... from exc`, esattamente come `SlskdClient._post`. E' lo
    scenario reale dell'utente, che tiene slskd in locale e l'URL sempre
    valorizzato: quello che manca, quando manca, e' il daemon."""

    def search(self, artist, title, **kw):
        try:
            raise httpx.ConnectError("[Errno 61] Connection refused")
        except httpx.ConnectError as exc:
            raise SlskdError(
                "slskd POST /searches fallita: [Errno 61] Connection refused") from exc

    def close(self):
        pass


class _ClientChe409Scollegato:
    """Daemon vivo ma non collegato alla rete Soulseek: e' cio' che slskd
    risponde a `POST /searches` dopo un riavvio o un blip di rete. Lo status
    da solo direbbe "richiesta sbagliata", ma il testo dice chiaramente che il
    problema e' il daemon — e con 300 item in coda trattarlo come colpa della
    traccia le brucia tutte."""

    def search(self, artist, title, **kw):
        exc = SlskdError('slskd 409: "must be connected (currently: Disconnected)"')
        exc.status_code = 409
        raise exc

    def close(self):
        pass


class _ClientChe409Conflitto:
    """L'altro 409: un conflitto vero sulla singola richiesta (il file e' gia'
    in coda da quell'utente). Riguarda la traccia, non l'infrastruttura."""

    def search(self, artist, title, **kw):
        exc = SlskdError('slskd 409: "file already queued"')
        exc.status_code = 409
        raise exc

    def close(self):
        pass


class _ClientCheFallisceSempreUguale:
    """Daemon vivo che risponde in un modo che nessuno ha classificato come
    infrastruttura, sempre lo stesso. E' il caso che la rete di sicurezza dei
    fallimenti consecutivi deve prendere."""

    def search(self, artist, title, **kw):
        exc = SlskdError("slskd 418: sono una teiera")
        exc.status_code = 418
        raise exc

    def close(self):
        pass


class _ClientChe401:
    """Daemon vivo ma con chiave API sbagliata o ruotata: `raise_for_status`
    attacca `.status_code=401` all'errore (nessuna causa httpx, come il 409),
    ma qui e' infrastruttura — la chiave sbagliata blocca OGNI richiesta, non
    solo quella traccia."""

    def search(self, artist, title, **kw):
        exc = SlskdError('slskd 401: "unauthorized"')
        exc.status_code = 401
        raise exc

    def close(self):
        pass


class _ClientChe500:
    """Daemon vivo ma che risponde 500 (es. appena riavviato, stato interno
    non ancora pronto): come 401, e' infrastruttura, non colpa della traccia."""

    def search(self, artist, title, **kw):
        exc = SlskdError('slskd 500: "internal error"')
        exc.status_code = 500
        raise exc

    def close(self):
        pass


def test_daemon_irraggiungibile_lascia_gli_item_in_coda(monkeypatch):
    """Il danno del rilievo 1: tre item accodati, URL valido ma porta chiusa.

    Prima della correzione la guardia guardava solo `slskd_configured()` — vera,
    l'URL c'e' — quindi gli item venivano rivendicati e bruciati uno dopo
    l'altro: tutti `failed`, e le tracce con un `last_download_outcome="failed"`
    che riportava "[Errno 61] Connection refused" come motivo. Dopo: gli item
    restano `queued`, le tracce non ricevono alcun esito, e l'interruttore si
    apre cosi' i successivi non vengono nemmeno rivendicati.

    `slots=1` come nel test gemello su slskd non configurato: un solo worker
    alla volta sul `run_item` vero, che qui serve davvero (e' la sua
    interazione con slskd spento a essere in discussione).
    """
    factory = _setup(monkeypatch, n_items=3, slots=1, slskd_available=True)
    monkeypatch.setattr(runner, "SessionLocal", factory)
    monkeypatch.setattr(runner, "get_slskd_client", lambda: _ClientSpento())
    d.fill()
    threading.Event().wait(0.4)

    db = factory()
    items = q.list_items(db)
    assert len(items) == 3
    assert all(i.state == "queued" for i in items)     # non bruciati a done/failed
    assert all(i.outcome is None for i in items)
    # Il tentativo rinviato non e' un tentativo: `claim_next` aveva incrementato
    # `attempts`, `requeue` lo riporta indietro (con un daemon spento per un'ora
    # il contatore crescerebbe di decine di unita' mai avvenute).
    assert all(i.attempts == 0 for i in items)
    tracks = db.query(Track).all()
    assert len(tracks) == 3
    assert all(t.last_download_outcome is None for t in tracks)
    assert all(t.last_download_reason is None for t in tracks)
    db.close()
    assert d.slskd_ready() is False                    # interruttore aperto


@pytest.mark.parametrize("client_cls", [_ClientChe401, _ClientChe500])
def test_daemon_vivo_ma_401_o_5xx_mette_in_pausa_la_coda(monkeypatch, client_cls):
    """Il rilievo: un daemon vivo che risponde 401 (chiave API sbagliata o
    ruotata) o un 5xx qualsiasi e' infrastruttura tanto quanto una connessione
    rifiutata — non colpa della traccia. Prima della correzione questi due
    casi cadevano nel ramo "colpa della traccia" (nessuna causa httpx, come il
    409): il riaggancio periodico che ripesca un daemon in questo stato
    avrebbe bruciato l'intera coda invece di mettersi in pausa. Gemello di
    `test_daemon_irraggiungibile_lascia_gli_item_in_coda`, stesse asserzioni."""
    factory = _setup(monkeypatch, n_items=3, slots=1, slskd_available=True)
    monkeypatch.setattr(runner, "SessionLocal", factory)
    monkeypatch.setattr(runner, "get_slskd_client", lambda: client_cls())
    d.fill()
    threading.Event().wait(0.4)

    db = factory()
    items = q.list_items(db)
    assert len(items) == 3
    assert all(i.state == "queued" for i in items)     # non bruciati a done/failed
    assert all(i.outcome is None for i in items)
    assert all(i.attempts == 0 for i in items)
    tracks = db.query(Track).all()
    assert all(t.last_download_outcome is None for t in tracks)
    assert all(t.last_download_reason is None for t in tracks)
    db.close()
    assert d.slskd_ready() is False                    # interruttore aperto


def test_il_409_da_rete_soulseek_scollegata_non_brucia_la_coda(monkeypatch):
    """Il rilievo: il 409 "must be connected" e' daemon vivo ma non collegato
    alla rete Soulseek — la condizione piu' frequente dopo un riavvio o un blip
    di rete. Prima della correzione i worker marcavano `failed` ogni item e
    scrivevano l'esito su ogni traccia; con 300 in coda, 300 tracce bruciate
    per un daemon da riconnettere. Adesso apre l'interruttore come le altre
    condizioni di infrastruttura."""
    factory = _setup(monkeypatch, n_items=3, slots=1, slskd_available=True)
    monkeypatch.setattr(runner, "SessionLocal", factory)
    monkeypatch.setattr(runner, "get_slskd_client", lambda: _ClientChe409Scollegato())
    d.fill()
    threading.Event().wait(0.4)

    db = factory()
    items = q.list_items(db)
    assert len(items) == 3
    assert all(i.state == "queued" for i in items)     # non bruciati a done/failed
    assert all(i.outcome is None for i in items)
    assert all(i.attempts == 0 for i in items)
    tracks = db.query(Track).all()
    assert all(t.last_download_outcome is None for t in tracks)
    db.close()
    assert d.slskd_ready() is False                    # interruttore aperto


def test_un_errore_della_singola_traccia_resta_un_fallimento_vero(monkeypatch):
    """L'altra faccia: un daemon vivo che rifiuta *quella* richiesta riguarda
    quella traccia. L'item deve concludersi `failed` col motivo leggibile — non
    essere rinviato all'infinito — e l'interruttore deve restare chiuso, cosi'
    la coda continua a scorrere. Due item soli: sotto la soglia della rete di
    sicurezza sui fallimenti consecutivi, che qui non deve entrare in gioco."""
    factory = _setup(monkeypatch, n_items=2, slots=1, slskd_available=True)
    monkeypatch.setattr(runner, "SessionLocal", factory)
    monkeypatch.setattr(runner, "get_slskd_client", lambda: _ClientChe409Conflitto())
    d.fill()
    threading.Event().wait(0.5)

    db = factory()
    items = q.list_items(db)
    assert [i.state for i in items] == ["done", "done"]   # conclusi entrambi
    assert all(i.outcome == "failed" for i in items)
    tracks = db.query(Track).all()
    assert all(t.last_download_outcome == "failed" for t in tracks)
    assert all("already queued" in (t.last_download_reason or "") for t in tracks)
    db.close()
    assert d.slskd_ready() is True                       # nessun interruttore aperto


def test_troppi_fallimenti_uguali_di_fila_aprono_comunque_l_interruttore(monkeypatch):
    """La rete di sicurezza dietro la classificazione: un modo di fallire che
    nessuno ha previsto scavalcherebbe `slskd_unreachable` e brucerebbe tutta
    la coda una traccia alla volta. Alla soglia l'interruttore si apre lo
    stesso, e gli item che restano non vengono nemmeno rivendicati."""
    n = d.CONSECUTIVE_FAILURE_LIMIT + 3
    factory = _setup(monkeypatch, n_items=n, slots=1, slskd_available=True)
    monkeypatch.setattr(runner, "SessionLocal", factory)
    monkeypatch.setattr(runner, "get_slskd_client",
                        lambda: _ClientCheFallisceSempreUguale())
    d.fill()
    threading.Event().wait(0.6)

    db = factory()
    items = q.list_items(db)
    bruciati = [i for i in items if i.state == "done"]
    risparmiati = [i for i in items if i.state == "queued"]
    # La soglia va rispettata in entrambi i versi: si brucia fino a li' (non
    # meno, altrimenti la classificazione normale non funzionerebbe piu') e non
    # oltre (e' tutto il punto della rete).
    assert len(bruciati) == d.CONSECUTIVE_FAILURE_LIMIT
    assert len(risparmiati) == n - d.CONSECUTIVE_FAILURE_LIMIT
    db.close()
    assert d.slskd_ready() is False


def test_un_successo_azzera_il_contatore_dei_fallimenti(monkeypatch):
    """Motivi diversi, o un download riuscito in mezzo, non devono sommarsi:
    una manciata di tracce introvabili sparse non e' un daemon rotto."""
    assert d._record_outcome("failed", "x") is False
    assert d._record_outcome("failed", "x") is False
    assert d._record_outcome("downloaded", None) is False
    for _ in range(d.CONSECUTIVE_FAILURE_LIMIT - 1):
        assert d._record_outcome("failed", "x") is False
    assert d._record_outcome("failed", "x") is True


def test_motivi_diversi_non_si_sommano(monkeypatch):
    for i in range(d.CONSECUTIVE_FAILURE_LIMIT * 2):
        assert d._record_outcome("failed", f"motivo-{i}") is False


def test_a_interruttore_aperto_un_item_soundcloud_parte_comunque(monkeypatch):
    """Gemello di `test_slskd_spento_non_blocca_un_item_soundcloud`, ma per la
    pausa dell'interruttore invece che per la mancata configurazione: yt-dlp
    non passa da slskd, quindi un daemon giu' non deve fermarlo."""
    factory = _setup(monkeypatch, n_items=0, slots=3, slskd_available=True)
    db = factory()
    t_sc = Track(source_type="manual", artist="A", title="SC",
                 url="https://soundcloud.com/a/b")
    t_sl = Track(source_type="manual", artist="B", title="SL")
    db.add_all([t_sc, t_sl])
    db.commit()
    q.enqueue(db, [t_sc.id], kind="soundcloud")
    q.enqueue(db, [t_sl.id], kind="soulseek_auto")
    db.close()

    d._trip_slskd_breaker()
    eseguiti = []
    monkeypatch.setattr(d, "run_item", lambda item_id: eseguiti.append(item_id))
    d.fill()
    threading.Event().wait(0.2)

    db = factory()
    items = {i.track_id: i for i in q.list_items(db)}
    assert eseguiti == [items[t_sc.id].id]            # solo il soundcloud e' partito
    assert items[t_sl.id].state == "queued"           # il soulseek resta intatto
    db.close()


def test_dopo_il_raffreddamento_l_interruttore_si_richiude(monkeypatch):
    """L'interruttore e' una pausa, non un blocco definitivo: scaduto il
    raffreddamento l'item viene ritentato, senza che nessuno debba dichiarare
    che il daemon e' tornato."""
    factory = _setup(monkeypatch, n_items=1, slots=1, slskd_available=True)
    monkeypatch.setattr(d, "SLSKD_COOLDOWN", 0.15)    # niente attese vere nei test
    eseguiti = []
    monkeypatch.setattr(d, "run_item", lambda item_id: eseguiti.append(item_id))

    d._trip_slskd_breaker()
    d.fill()
    threading.Event().wait(0.05)
    assert eseguiti == []                             # in pausa: nulla rivendicato

    time.sleep(0.2)                                   # raffreddamento scaduto
    d.fill()
    threading.Event().wait(0.2)

    db = factory()
    item_id = q.list_items(db)[0].id
    db.close()
    assert eseguiti == [item_id]                      # ritentato


def test_il_riaggancio_periodico_rimette_in_moto_una_coda_ferma(monkeypatch):
    """Il rilievo 2: `fill()` lo chiamano solo gli endpoint di download e
    `boot()`. Una coda ferma perche' slskd era giu' ripartirebbe solo
    accodando qualcos'altro — un gesto che l'utente non ha ragione di fare,
    visto che quello che ha gia' accodato non e' andato da nessuna parte.

    Qui nessuno accoda e nessuno chiama `fill()` dopo il ritorno del daemon:
    solo il riaggancio periodico puo' far ripartire l'item. Senza di lui
    `eseguiti` resta vuoto per sempre.
    """
    factory = _setup(monkeypatch, n_items=1, slots=1, slskd_available=False)
    monkeypatch.setattr(d, "RETRY_INTERVAL", 0.05)
    eseguiti = []
    monkeypatch.setattr(d, "run_item", lambda item_id: eseguiti.append(item_id))

    d.boot()                                    # fill() non trova nulla di lavorabile
    threading.Event().wait(0.2)
    assert eseguiti == []

    monkeypatch.setattr(d, "slskd_configured", lambda: True)   # il daemon torna
    threading.Event().wait(0.6)

    db = factory()
    item_id = q.list_items(db)[0].id
    db.close()
    assert eseguiti == [item_id]


def test_il_riaggancio_periodico_non_si_avvia_due_volte(monkeypatch):
    """`boot()` viene chiamato piu' volte nello stesso processo (reload di
    uvicorn, test): due loop significherebbero due `fill()` concorrenti a ogni
    intervallo."""
    _setup(monkeypatch, n_items=0)
    monkeypatch.setattr(d, "run_item", lambda item_id: None)
    d.boot()
    primo = d._retry_thread
    d.boot()
    assert d._retry_thread is primo
    assert primo is not None and primo.is_alive()
