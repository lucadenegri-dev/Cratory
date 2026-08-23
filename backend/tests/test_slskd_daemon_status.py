"""Lo stato del demone deve dire a che punto è il percorso, non solo se
risponde: la riga che lo mostra sceglie l'unica azione sensata a partire da
questi campi, e senza `installed`/`configured` non può distinguere "da
scaricare" da "da configurare"."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import slskd_daemon

client = TestClient(app)


def _stato() -> dict:
    risposta = client.get("/api/slskd/daemon/status")
    assert risposta.status_code == 200
    return risposta.json()


def test_binario_assente_lo_dice(monkeypatch):
    monkeypatch.setattr("app.services.binary_installer.installed_path", lambda k: None)
    assert _stato()["installed"] is False


def test_binario_presente_lo_dice(monkeypatch):
    monkeypatch.setattr(
        "app.services.binary_installer.installed_path", lambda k: Path("/finto/slskd")
    )
    assert _stato()["installed"] is True


def test_configurazione_assente_lo_dice(monkeypatch, tmp_path):
    monkeypatch.setattr(slskd_daemon, "default_config_path", lambda: tmp_path / "manca.yml")
    stato = _stato()
    assert stato["configured"] is False
    assert stato["username"] is None


def test_configurazione_presente_porta_lo_username(monkeypatch, tmp_path):
    config = tmp_path / "slskd.yml"
    config.write_text("soulseek:\n  username: dj_test\n  password: segreta\n")
    monkeypatch.setattr(slskd_daemon, "default_config_path", lambda: config)
    stato = _stato()
    assert stato["configured"] is True
    assert stato["username"] == "dj_test"


def test_la_password_non_esce_mai(monkeypatch, tmp_path):
    """Il file la contiene, la risposta no: nessun campo la trasporta, e
    nemmeno per sbaglio dentro un altro."""
    config = tmp_path / "slskd.yml"
    config.write_text("soulseek:\n  username: dj_test\n  password: segretissima\n")
    monkeypatch.setattr(slskd_daemon, "default_config_path", lambda: config)
    assert "segretissima" not in client.get("/api/slskd/daemon/status").text


def test_anche_stop_dice_a_che_punto_siamo(monkeypatch, tmp_path):
    """`/daemon/status`, `/daemon/start` e `/daemon/stop` rispondono con lo
    STESSO modello, costruito da tre dict diversi del servizio. Se i campi
    nuovi avessero solo un default, dopo un avvio riuscito l'app leggerebbe
    `installed: false` — e la riga tornerebbe a offrire il download di un
    binario che ha appena eseguito."""
    config = tmp_path / "slskd.yml"
    config.write_text("soulseek:\n  username: dj_test\n")
    monkeypatch.setattr(slskd_daemon, "default_config_path", lambda: config)
    monkeypatch.setattr(
        "app.services.binary_installer.installed_path", lambda k: Path("/finto/slskd")
    )
    monkeypatch.setattr(
        slskd_daemon, "stop", lambda: {"reachable": False, "owned": None, "pid": None}
    )
    stato = client.post("/api/slskd/daemon/stop").json()
    assert stato["installed"] is True
    assert stato["configured"] is True
