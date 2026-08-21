"""Le due regole della deroga: non si avvia un secondo demone se ce n'è già
uno, e non si ferma mai un processo che non abbiamo avviato noi."""
import httpx
import pytest

from app.services import slskd_daemon as sd


@pytest.fixture(autouse=True)
def _pid_isolato(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "pid_file", lambda: tmp_path / "slskd.pid")
    return tmp_path


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gia_in_ascolto_non_avvia_un_secondo_processo(monkeypatch):
    """Il caso normale è che slskd ci sia già, installato dall'utente: non
    dobbiamo scaricarlo né avviarlo, e soprattutto non affiancargliene un altro."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")

    def esplodi(argv, **kw):
        raise AssertionError("non doveva lanciare niente")

    monkeypatch.setattr(sd.subprocess, "Popen", esplodi)
    with _client(lambda req: httpx.Response(200)) as c:
        with pytest.raises(sd.AlreadyUp):
            sd.start(client=c)


def test_pid_di_un_processo_inesistente_e_stantio(_pid_isolato, monkeypatch):
    sd.pid_file().write_text("999999")
    monkeypatch.setattr(sd, "_processo_e_slskd", lambda pid: False)
    assert sd.owned_pid() is None
    assert not sd.pid_file().exists(), "il file stantio va rimosso"


def test_pid_riassegnato_a_un_altro_processo_non_e_nostro(_pid_isolato, monkeypatch):
    """Un PID può essere stato riciclato dal sistema: fermarlo alla cieca
    significherebbe uccidere un processo qualsiasi dell'utente."""
    sd.pid_file().write_text("1234")
    monkeypatch.setattr(sd, "_riga_di_comando", lambda pid: "/usr/bin/qualcosaltro")
    assert sd.owned_pid() is None


def test_pid_valido_e_nostro(_pid_isolato, monkeypatch):
    sd.pid_file().write_text("1234")
    monkeypatch.setattr(sd, "_riga_di_comando", lambda pid: "/app/data/bin/slskd/slskd")
    assert sd.owned_pid() == 1234


def test_stop_rifiutato_senza_pid_nostro(_pid_isolato):
    with pytest.raises(sd.NotOurs):
        sd.stop()


def test_stop_termina_solo_il_nostro(_pid_isolato, monkeypatch):
    sd.pid_file().write_text("1234")
    monkeypatch.setattr(sd, "_riga_di_comando", lambda pid: "/app/data/bin/slskd/slskd")
    uccisi = []
    monkeypatch.setattr(sd.os, "kill", lambda pid, sig: uccisi.append((pid, sig)))
    monkeypatch.setattr(sd, "_processo_vivo", lambda pid: False)  # muore subito
    sd.stop()
    assert uccisi[0][0] == 1234
    assert not sd.pid_file().exists()


def test_avvio_senza_binario_installato(monkeypatch):
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "")
    monkeypatch.setattr(sd.binary_installer, "installed_path", lambda key: None)
    with pytest.raises(sd.NotInstalled):
        sd.start()


def test_avvio_che_non_risponde_e_un_fallimento(tmp_path, monkeypatch):
    """Non ci si fida dello spawn: se /health non risponde mai, l'avvio è
    fallito e va mostrata la coda del log, dove si legge la porta occupata."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")
    monkeypatch.setattr(sd.binary_installer, "installed_path",
                        lambda key: tmp_path / "slskd")
    monkeypatch.setattr(sd, "_ATTESA_AVVIO_S", 0.05)
    monkeypatch.setattr(sd, "_INTERVALLO_S", 0.01)

    class FintoProc:
        pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr(sd.subprocess, "Popen", lambda *a, **kw: FintoProc())
    with _client(lambda req: httpx.Response(503)) as c:
        with pytest.raises(sd.StartFailed):
            sd.start(client=c)


def test_stato_riporta_raggiungibile_e_proprieta(_pid_isolato, monkeypatch):
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")
    with _client(lambda req: httpx.Response(200)) as c:
        stato = sd.daemon_status(client=c)
    assert stato == {"reachable": True, "owned": False, "pid": None}
