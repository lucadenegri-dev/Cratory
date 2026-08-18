"""L'installer esegue solo ricette del registry, mai una stringa di shell."""
import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.db import get_db
from app.main import app
from app.services import component_installer as ci
from app.services import system_probe as sp


class _FakeProc:
    def __init__(self, righe, returncode=0):
        self.stdout = iter(righe)
        self.returncode = returncode

    def wait(self):
        return self.returncode


@pytest.fixture(autouse=True)
def _reset_installer():
    ci.reset()
    # Anche la cache di system_probe: alcuni test qui la scaldano per provare
    # l'invalidazione, e va ripulita prima/dopo perché nessun altro file di
    # test (es. test_system_probe.py) diventi order-dependent su di essa.
    sp.invalidate_cache()
    yield
    ci.reset()
    sp.invalidate_cache()


@pytest.fixture(autouse=True)
def _no_slskd_network_call(monkeypatch):
    """Come in test_system_probe.py: niente chiamate di rete a un demone
    slskd quando questi test finiscono per invocare probe_all()."""
    monkeypatch.setattr(config.settings, "slskd_url", "")


def test_chiave_sconosciuta(db):
    app.dependency_overrides[get_db] = lambda: db
    res = TestClient(app).post("/api/setup/install/rm-rf")
    assert res.status_code == 400
    app.dependency_overrides.clear()


def test_componente_non_auto_installabile(db):
    """ffmpeg si installa a mano: il wizard mostra il comando, non lo esegue."""
    app.dependency_overrides[get_db] = lambda: db
    res = TestClient(app).post("/api/setup/install/ffmpeg")
    assert res.status_code == 400
    app.dependency_overrides.clear()


def test_esecuzione_mai_via_shell(monkeypatch):
    visti = {}

    def fake_popen(argv, **kwargs):
        visti["argv"] = argv
        visti["kwargs"] = kwargs
        return _FakeProc(["riga 1", "riga 2"])

    monkeypatch.setattr(ci.subprocess, "Popen", fake_popen)
    righe = list(ci.run_recipe(["echo", "ciao"]))

    assert righe == ["riga 1", "riga 2"]
    assert isinstance(visti["argv"], list), "argv deve restare una lista"
    assert visti["kwargs"].get("shell") in (None, False)


def test_returncode_non_zero_solleva(monkeypatch):
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["boom"], returncode=1))
    with pytest.raises(ci.InstallFailed):
        list(ci.run_recipe(["pip", "install", "niente"]))


def test_installazione_riuscita(monkeypatch):
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["Collecting yt-dlp", "Successfully installed"]))
    monkeypatch.setattr(ci, "spawn", lambda fn: fn())  # sincrono nei test
    ci.start("yt-dlp")
    stato = ci.status()
    assert stato["status"] == "done"
    assert stato["key"] == "yt-dlp"
    assert "Successfully installed" in stato["log"]


def test_installazione_fallita_registra_l_errore(monkeypatch):
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["ERROR: no matching distribution"], returncode=1))
    monkeypatch.setattr(ci, "spawn", lambda fn: fn())
    ci.start("essentia")
    stato = ci.status()
    assert stato["status"] == "error"
    assert stato["detail"]


def test_una_installazione_alla_volta(monkeypatch):
    monkeypatch.setattr(ci, "spawn", lambda fn: None)  # resta "running"
    ci.start("yt-dlp")
    with pytest.raises(ci.AlreadyRunning):
        ci.start("essentia")


def test_il_log_e_limitato(monkeypatch):
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc([f"riga {i}" for i in range(2000)]))
    monkeypatch.setattr(ci, "spawn", lambda fn: fn())
    ci.start("yt-dlp")
    assert len(ci.status()["log"]) <= ci.MAX_LOG_LINES


def test_installazione_riuscita_invalida_la_cache_del_probe(monkeypatch):
    """Un'installazione riuscita deve invalidare la cache di system_probe
    tramite il suo seam pubblico (`invalidate_cache`), non toccando la sua
    variabile privata: qui lo si prova sull'effetto osservabile, contando
    quante volte il rilevamento gira davvero."""
    chiamate = {"n": 0}

    def conta(name):
        chiamate["n"] += 1
        return None

    monkeypatch.setattr(sp.shutil, "which", conta)
    monkeypatch.setattr(sp, "_run_version", lambda argv: None)

    # Scalda la cache: la prossima probe_all() senza force userebbe questa.
    sp.probe_all(force=True)
    dopo_warm = chiamate["n"]
    sp.probe_all()
    assert chiamate["n"] == dopo_warm, "prima dell'installazione la cache deve essere calda"

    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["Successfully installed"]))
    monkeypatch.setattr(ci, "spawn", lambda fn: fn())  # sincrono nei test
    ci.start("yt-dlp")
    assert ci.status()["status"] == "done"

    # La cache non deve più essere calda: probe_all() senza force ri-rileva.
    sp.probe_all()
    assert chiamate["n"] > dopo_warm, "dopo l'installazione la cache doveva essere invalidata"


def test_eccezione_inattesa_non_incastra_l_installer(monkeypatch):
    """Un'eccezione fuori da (InstallFailed, OSError) — es. sollevata dentro
    Popen — non deve lasciare lo stato bloccato su 'running' per sempre:
    altrimenti start() risponderebbe AlreadyRunning a ogni richiesta
    successiva finché non si riavvia il backend."""
    def popen_esplode(argv, **kw):
        raise ValueError("qualcosa di inatteso, non un OSError")

    monkeypatch.setattr(ci.subprocess, "Popen", popen_esplode)
    monkeypatch.setattr(ci, "spawn", lambda fn: fn())  # sincrono nei test

    ci.start("yt-dlp")
    stato = ci.status()
    assert stato["status"] == "error"
    assert stato["detail"]

    # Una richiesta successiva deve poter ripartire, non sollevare AlreadyRunning.
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["Successfully installed"]))
    ci.start("yt-dlp")
    assert ci.status()["status"] == "done"


def test_eccezione_nella_coda_della_run_non_incastra_l_installer(monkeypatch):
    """Se la coda della run() (invalidate_cache o state update) solleva
    un'eccezione, lo stato non deve rimanere bloccato su 'running':
    dev'essere marchiato come 'error' in modo che start() possa ripartire."""
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["Successfully installed"]))
    monkeypatch.setattr(ci, "spawn", lambda fn: fn())  # sincrono nei test

    # Fai fallire invalidate_cache, mentre run_recipe riesce
    def invalidate_esplode():
        raise RuntimeError("invalidate_cache è esplosa")

    monkeypatch.setattr(ci.system_probe, "invalidate_cache", invalidate_esplode)

    ci.start("yt-dlp")
    stato = ci.status()
    assert stato["status"] == "error", "uno stato di errore nella coda deve marcare 'error'"
    assert stato["detail"], "l'errore deve avere un messaggio"

    # Una richiesta successiva deve poter ripartire, non sollevare AlreadyRunning.
    monkeypatch.setattr(ci.system_probe, "invalidate_cache", lambda: None)
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["Successfully installed"]))
    ci.start("yt-dlp")
    assert ci.status()["status"] == "done"
