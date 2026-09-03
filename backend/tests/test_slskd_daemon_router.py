"""Gli endpoint del demone traducono in HTTP le due regole del servizio."""
import httpx
import pytest
from ruamel.yaml import YAML
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import runtime_settings as rs
from app.db import Base, get_db
from app.main import app
from app.services import slskd_daemon as sd


@pytest.fixture()
def db():
    """`StaticPool` invece del `db` generico di conftest: una sola connessione
    in-memory condivisa fra il thread del test e il threadpool di TestClient.
    Serve da quando `daemon_config` scrive per davvero nel DB (write-back
    delle impostazioni su config nuova) — senza `StaticPool`, il default
    `SingletonThreadPool` di SQLite in-memory dà al thread di TestClient una
    connessione (quindi un database) tutta sua, vuota: "no such table:
    app_state" anche se lo schema è stato creato un attimo prima nel thread
    del test. Stesso rimedio già in uso in `test_settings_config_router.py`."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_stato(db, monkeypatch):
    monkeypatch.setattr(sd, "daemon_status",
                        lambda client=None: {"reachable": False, "owned": False, "pid": None})
    assert _client(db).get("/api/slskd/daemon/status").json()["reachable"] is False
    app.dependency_overrides.clear()


def test_start_quando_e_gia_acceso(db, monkeypatch):
    def gia_su(client=None):
        raise sd.AlreadyUp("già acceso")

    monkeypatch.setattr(sd, "start", gia_su)
    assert _client(db).post("/api/slskd/daemon/start").status_code == 409
    app.dependency_overrides.clear()


def test_start_quando_un_nostro_demone_e_gia_vivo_ma_irraggiungibile(db, monkeypatch):
    def gia_nostro(client=None):
        raise sd.AlreadyOwned("un demone nostro è già in esecuzione")

    monkeypatch.setattr(sd, "start", gia_nostro)
    res = _client(db).post("/api/slskd/daemon/start")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "slskd_already_owned"
    app.dependency_overrides.clear()


def test_start_senza_binario(db, monkeypatch):
    def non_installato(client=None):
        raise sd.NotInstalled("manca")

    monkeypatch.setattr(sd, "start", non_installato)
    assert _client(db).post("/api/slskd/daemon/start").status_code == 409
    app.dependency_overrides.clear()


def test_start_che_non_risponde(db, monkeypatch):
    def fallisce(client=None):
        raise sd.StartFailed("porta occupata")

    monkeypatch.setattr(sd, "start", fallisce)
    res = _client(db).post("/api/slskd/daemon/start")
    assert res.status_code == 502
    assert "porta occupata" in res.text
    app.dependency_overrides.clear()


def test_stop_di_un_demone_non_nostro(db, monkeypatch):
    def non_nostro():
        raise sd.NotOurs("non nostro")

    monkeypatch.setattr(sd, "stop", non_nostro)
    assert _client(db).post("/api/slskd/daemon/stop").status_code == 409
    app.dependency_overrides.clear()


def test_la_password_non_torna_indietro(db, monkeypatch, tmp_path):
    """Stessa regola delle altre credenziali: entra, non esce."""
    monkeypatch.setattr(sd, "default_config_path", lambda: tmp_path / "slskd.yml")
    res = _client(db).put("/api/slskd/daemon/config", json={
        "username": "io", "password": "segretissima",
        "port": 5030, "download_dir": "/tmp/dl"})
    assert res.status_code == 200
    assert "segretissima" not in res.text
    assert res.json()["username"] == "io"
    app.dependency_overrides.clear()


def test_config_da_zero_allinea_le_impostazioni_di_cratory(db, monkeypatch, tmp_path):
    """Il finding B2: `write_config` scrive solo `slskd.yml`. Su una config
    nata da zero (nessun file preesistente) la porta e la cartella scelte —
    qui i default, perché il chiamante non ne passa — devono finire scritte
    ANCHE nelle impostazioni di Cratory (`slskd_url`/`slskd_download_dir`),
    o `is_reachable()` resta cieco al demone appena configurato."""
    monkeypatch.setattr(sd, "default_config_path", lambda: tmp_path / "nuova" / "slskd.yml")
    # Isolato dalla vera backend/data/: senza cartella download già scelta,
    # write_config ricadrebbe sulla cartella di default vera e la creerebbe
    # per davvero fuori da tmp_path.
    monkeypatch.setattr(sd, "_cartella_download_default", lambda: tmp_path / "download-default")
    res = _client(db).put("/api/slskd/daemon/config", json={
        "username": "io", "password": "segreta"})
    assert res.status_code == 200
    assert rs.slskd_url() == f"http://127.0.0.1:{sd.DEFAULT_PORT}"
    assert rs.slskd_download_dir(), "la cartella scelta va scritta anche nelle impostazioni"
    app.dependency_overrides.clear()


class _FintoProcessoVivo:
    """Popen finto per il giro end-to-end di `start()`: resta vivo per tutta
    la finestra di polling, non serve altro — `start()` deve trovare il
    demone raggiungibile ben prima del timeout."""
    pid = 4242

    def poll(self):
        return None


def test_avvio_su_configurazione_nuova_raggiunge_un_demone_raggiungibile(db, monkeypatch, tmp_path):
    """L'invariante che mancava (B2): prima del write-back, `slskd_url()`
    restava vuoto anche dopo `PUT /daemon/config` su una config nuova, e
    `is_reachable()` — il criterio con cui `start()` giudica l'avvio
    riuscito — ritornava sempre False per quel solo motivo: download,
    installazione e spawn del processo tutti riusciti, e vent'secondi dopo
    Cratory manda SIGTERM al proprio demone e dice all'utente che non è
    partito. Riproduce il giro intero: configura da zero, poi avvia con un
    client finto che risponde `/health` solo all'URL che il write-back
    avrebbe dovuto scrivere — se `start()` lo raggiunge, il write-back ha
    funzionato per davvero, non solo sulla carta di `runtime_settings`."""
    cfg = tmp_path / "slskd.yml"
    monkeypatch.setattr(sd, "default_config_path", lambda: cfg)
    monkeypatch.setattr(sd, "pid_file", lambda: tmp_path / "slskd.pid")
    monkeypatch.setattr(sd, "log_file", lambda: tmp_path / "slskd.log")
    monkeypatch.setattr(sd.binary_installer, "installed_path",
                        lambda key: tmp_path / "slskd")
    monkeypatch.setattr(sd.subprocess, "Popen", lambda *a, **kw: _FintoProcessoVivo())
    # owned_pid() a fine start() chiede di chi è l'eseguibile dietro al PID:
    # senza questo chiamerebbe `ps` per davvero (o, peggio, `subprocess.run`
    # userebbe lo stesso `Popen` finto appena sopra, rompendosi con un
    # TypeError che non ha niente a che fare con l'invariante testata qui).
    monkeypatch.setattr(sd, "_percorso_eseguibile", lambda pid: str(tmp_path / "slskd"))
    # Isolato dalla vera backend/data/, stesso motivo del test sopra.
    monkeypatch.setattr(sd, "_cartella_download_default", lambda: tmp_path / "download-default")

    res = _client(db).put("/api/slskd/daemon/config", json={
        "username": "io", "password": "segreta"})
    assert res.status_code == 200
    app.dependency_overrides.clear()

    url_atteso = f"http://127.0.0.1:{sd.DEFAULT_PORT}/health"
    chiamate = []

    def _health(req):
        chiamate.append(str(req.url))
        # La prima chiamata è il controllo "c'è già qualcosa?" di start(),
        # PRIMA dello spawn: deve fallire, altrimenti start() si fermerebbe
        # su AlreadyUp senza mai testare il write-back. Da lì in poi il
        # demone (mai avviato per davvero: `Popen` è finto) risponde.
        if len(chiamate) == 1:
            return httpx.Response(503)
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(_health)) as c:
        stato = sd.start(client=c)

    assert stato["reachable"] is True
    assert chiamate[0] == url_atteso


def test_ruotare_solo_le_credenziali_non_tocca_porta_e_cartella(db, monkeypatch, tmp_path):
    """Riproduce lo scenario del finding critico: config esistente con porta
    e cartella download personalizzate, richiesta che porta solo username e
    password. Entrambe devono sopravvivere intatte - non tornare al default
    dell'app (porta 5030, cartella di Cratory)."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(
        "soulseek:\n"
        "  username: vecchio\n"
        "  password: vecchia\n"
        "web:\n"
        "  port: 6033\n"
        "directories:\n"
        "  downloads: /mio/download/custom\n"
    )
    monkeypatch.setattr(sd, "default_config_path", lambda: cfg)
    # Si fotografa il valore PRIMA, invece di darlo per vuoto: su una macchina
    # con un `.env` reale `slskd_url()` è popolato, e un test che pretende ""
    # fallisce per l'ambiente e non per il codice. L'invariante da provare è
    # "non è cambiato", non "è vuoto".
    url_prima = rs.slskd_url()
    dir_prima = rs.slskd_download_dir()

    res = _client(db).put("/api/slskd/daemon/config", json={
        "username": "nuovo", "password": "nuova"})

    assert res.status_code == 200
    testo = cfg.read_text()
    assert "port: 6033" in testo
    assert "/mio/download/custom" in testo
    # Config già esistente: niente write-back. Solo `created=True` lo
    # innesca — riscrivere le impostazioni di Cratory anche qui vorrebbe dire
    # sovrascrivere silenziosamente uno `slskd_url()`/`slskd_download_dir()`
    # che l'utente può aver scelto apposta diversi da quel che c'è nel file.
    assert rs.slskd_url() == url_prima
    assert rs.slskd_download_dir() == dir_prima
    app.dependency_overrides.clear()


def test_stato_owned_null_quando_non_si_puo_sapere(db, monkeypatch):
    """Tristate `owned`: None significa "non lo si puo' proprio sapere su
    questa piattaforma" (Windows) - diverso sia da True (nostro) sia da
    False (demone acceso ma non nostro). Va provato sul giro HTTP vero,
    non solo sulla funzione di servizio: un domani che lo collassasse a
    False nella serializzazione passerebbe inosservato altrimenti."""
    monkeypatch.setattr(sd, "daemon_status",
                        lambda client=None: {"reachable": True, "owned": None, "pid": None})
    res = _client(db).get("/api/slskd/daemon/status")
    assert res.status_code == 200
    assert res.json()["owned"] is None
    app.dependency_overrides.clear()


def test_start_su_piattaforma_non_supportata(db, monkeypatch):
    def non_supportato(client=None):
        raise sd.UnsupportedPlatform("la gestione del demone slskd non è disponibile su questa piattaforma")

    monkeypatch.setattr(sd, "start", non_supportato)
    assert _client(db).post("/api/slskd/daemon/start").status_code == 501
    app.dependency_overrides.clear()


def test_stop_su_piattaforma_non_supportata(db, monkeypatch):
    def non_supportato():
        raise sd.UnsupportedPlatform("la gestione del demone slskd non è disponibile su questa piattaforma")

    monkeypatch.setattr(sd, "stop", non_supportato)
    assert _client(db).post("/api/slskd/daemon/stop").status_code == 501
    app.dependency_overrides.clear()


def _chiave_nel_file(cfg):
    return YAML().load(cfg.read_text())["web"]["authentication"]["api_keys"][sd.API_KEY_NAME]["key"]


def test_la_chiave_api_finisce_anche_nelle_impostazioni(db, monkeypatch, tmp_path):
    """Le due copie della chiave — quella dentro slskd.yml e quella con cui
    Cratory firma le richieste — non possono divergere: se il file ne ha una
    e le impostazioni no, il demone risponde 401 a tutto. È esattamente il
    bug su installazione fresca, dove di chiavi non ce n'era nessuna delle
    due e l'errore si vedeva solo al click su "Connetti"."""
    cfg = tmp_path / "nuova" / "slskd.yml"
    monkeypatch.setattr(sd, "default_config_path", lambda: cfg)
    monkeypatch.setattr(sd, "_cartella_download_default", lambda: tmp_path / "download-default")
    res = _client(db).put("/api/slskd/daemon/config", json={
        "username": "io", "password": "segreta"})
    assert res.status_code == 200
    chiave = _chiave_nel_file(cfg)
    assert rs.slskd_api_key() == chiave
    assert chiave not in res.text, "la chiave è una credenziale: non torna al frontend"
    app.dependency_overrides.clear()


def test_la_chiave_api_si_allinea_anche_su_config_esistente(db, monkeypatch, tmp_path):
    """`created` governa il write-back di porta e cartella (che l'utente può
    aver scelto apposta diversi dal file), ma NON quello della chiave: quella
    scritta nelle impostazioni è sempre e solo quella che sta nel file, quindi
    riallinearla non sovrascrive nessuna scelta — mentre non farlo lascia il
    401 in piedi su ogni configurazione preesistente."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text("soulseek:\n  username: vecchio\n  password: vecchia\n"
                   "web:\n  port: 6033\n  authentication:\n    api_keys:\n"
                   "      cratory:\n        key: chiave-scritta-a-mano-lunga\n"
                   "directories:\n  downloads: /mio/download/custom\n")
    monkeypatch.setattr(sd, "default_config_path", lambda: cfg)
    res = _client(db).put("/api/slskd/daemon/config", json={
        "username": "nuovo", "password": "nuova"})
    assert res.status_code == 200
    assert rs.slskd_api_key() == "chiave-scritta-a-mano-lunga"
    app.dependency_overrides.clear()


class _Riavvio:
    """Registra stop e start senza toccare processi veri."""

    def __init__(self):
        self.eventi = []

    def stop(self):
        self.eventi.append("stop")
        return {"reachable": False, "owned": False, "pid": None}

    def start(self, client=None):
        self.eventi.append("start")
        return {"reachable": True, "owned": True, "pid": 4243}


def test_riparazione_scrive_la_chiave_e_riavvia_il_demone_nostro(db, monkeypatch, tmp_path):
    """Il recupero di chi si è configurato slskd prima di questa versione: ha
    un demone acceso che ci risponde 401, e la riga non gli offre più la
    configurazione (quella fase si vede solo a demone spento). Una sola
    azione deve bastare — chiave e riavvio insieme, perché slskd legge le
    `api_keys` una volta sola, all'avvio."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text("soulseek:\n  username: vecchio\n  password: vecchia\nweb:\n  port: 5030\n")
    monkeypatch.setattr(sd, "default_config_path", lambda: cfg)
    monkeypatch.setattr(sd, "owned_pid", lambda: 4242)
    riavvio = _Riavvio()
    monkeypatch.setattr(sd, "stop", riavvio.stop)
    monkeypatch.setattr(sd, "start", riavvio.start)

    res = _client(db).post("/api/slskd/daemon/api-key")

    assert res.status_code == 200
    assert res.json() == {"configured": True, "restarted": True, "needs_restart": False}
    assert riavvio.eventi == ["stop", "start"], "senza riavvio la chiave nuova non viene letta"
    assert rs.slskd_api_key() == _chiave_nel_file(cfg)
    app.dependency_overrides.clear()


def test_riparazione_non_ferma_un_demone_non_nostro(db, monkeypatch, tmp_path):
    """La regola del modulo vale anche qui: non si ferma un processo che non
    abbiamo avviato noi. La chiave si scrive lo stesso, ma il riavvio lo deve
    fare l'utente — e la risposta deve dirlo, o resterebbe col 401 senza
    sapere che gli manca un passo."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text("soulseek:\n  username: vecchio\n  password: vecchia\nweb:\n  port: 5030\n")
    monkeypatch.setattr(sd, "default_config_path", lambda: cfg)
    monkeypatch.setattr(sd, "owned_pid", lambda: None)
    riavvio = _Riavvio()
    monkeypatch.setattr(sd, "stop", riavvio.stop)
    monkeypatch.setattr(sd, "start", riavvio.start)

    res = _client(db).post("/api/slskd/daemon/api-key")

    assert res.status_code == 200
    assert res.json() == {"configured": True, "restarted": False, "needs_restart": True}
    assert riavvio.eventi == [], "non è nostro: non lo si tocca"
    assert rs.slskd_api_key() == _chiave_nel_file(cfg)
    app.dependency_overrides.clear()


def test_riparazione_su_piattaforma_senza_gestione_del_processo(db, monkeypatch, tmp_path):
    """Su Windows non si può sapere di chi è un PID (vedi `UnsupportedPlatform`):
    la chiave si scrive comunque — è solo un file YAML — e il riavvio resta
    all'utente. Un 501 qui negherebbe anche la parte che funziona."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text("soulseek:\n  username: vecchio\n  password: vecchia\nweb:\n  port: 5030\n")
    monkeypatch.setattr(sd, "default_config_path", lambda: cfg)

    def non_supportato():
        raise sd.UnsupportedPlatform("niente ps né SIGKILL")

    monkeypatch.setattr(sd, "owned_pid", non_supportato)
    res = _client(db).post("/api/slskd/daemon/api-key")
    assert res.status_code == 200
    assert res.json()["needs_restart"] is True
    assert rs.slskd_api_key() == _chiave_nel_file(cfg)
    app.dependency_overrides.clear()


def test_riparazione_senza_configurazione(db, monkeypatch, tmp_path):
    """Niente file, niente da riparare: va prima configurato l'account, e il
    codice d'errore deve dirlo (la riga rimanda alla fase giusta)."""
    monkeypatch.setattr(sd, "default_config_path", lambda: tmp_path / "manca.yml")
    res = _client(db).post("/api/slskd/daemon/api-key")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "slskd_not_configured"
    app.dependency_overrides.clear()
