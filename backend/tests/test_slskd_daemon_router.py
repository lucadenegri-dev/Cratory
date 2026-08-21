"""Gli endpoint del demone traducono in HTTP le due regole del servizio."""
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import slskd_daemon as sd


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

    res = _client(db).put("/api/slskd/daemon/config", json={
        "username": "nuovo", "password": "nuova"})

    assert res.status_code == 200
    testo = cfg.read_text()
    assert "port: 6033" in testo
    assert "/mio/download/custom" in testo
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
