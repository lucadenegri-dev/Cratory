"""Le due regole della deroga: non si avvia un secondo demone se ce n'è già
uno, e non si ferma mai un processo che non abbiamo avviato noi."""
import httpx
import pytest

from app.services import slskd_daemon as sd


@pytest.fixture(autouse=True)
def _pid_isolato(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "pid_file", lambda: tmp_path / "slskd.pid")
    # Isolato allo stesso modo del pid file: senza questo un test che spawna
    # un finto slskd scriverebbe nel log reale sotto backend/data/, che può
    # contenere l'output di un'esecuzione vera dell'utente.
    monkeypatch.setattr(sd, "log_file", lambda: tmp_path / "slskd.log")
    return tmp_path


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _scrivi_pid(tmp_path, pid: int, eseguibile: str):
    sd.pid_file().write_text(f"{pid}\n{eseguibile}\n")


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
    _scrivi_pid(_pid_isolato, 999999, "/app/data/bin/slskd/slskd")
    monkeypatch.setattr(sd, "_percorso_eseguibile", lambda pid: "")
    assert sd.owned_pid() is None
    assert not sd.pid_file().exists(), "il file stantio va rimosso"


def test_pid_riassegnato_a_un_altro_processo_non_e_nostro(_pid_isolato, monkeypatch):
    """Un PID può essere stato riciclato dal sistema: fermarlo alla cieca
    significherebbe uccidere un processo qualsiasi dell'utente."""
    _scrivi_pid(_pid_isolato, 1234, "/app/data/bin/slskd/slskd")
    monkeypatch.setattr(sd, "_percorso_eseguibile", lambda pid: "/usr/bin/qualcosaltro")
    assert sd.owned_pid() is None


def test_riga_di_comando_con_slskd_a_caso_non_basta(_pid_isolato, monkeypatch):
    """Riproduce il finding critico: l'utente sta editando la config di
    slskd con vim (`/usr/bin/vim /Users/x/.config/slskd/slskd.yml`), una
    riga di comando plausibilissima che contiene la sottostringa "slskd" pur
    non essendo affatto il nostro demone. Un PID riassegnato a questo
    processo non deve MAI essere giudicato nostro: solo l'eseguibile esatto
    che abbiamo lanciato conta come prova, non una sottostringa da qualche
    parte nella riga di comando."""
    _scrivi_pid(_pid_isolato, 1234, "/app/data/bin/slskd/slskd")
    monkeypatch.setattr(
        sd, "_percorso_eseguibile",
        lambda pid: "/usr/bin/vim /Users/x/.config/slskd/slskd.yml",
    )
    assert sd.owned_pid() is None
    assert not sd.pid_file().exists()


def test_pid_valido_e_nostro(_pid_isolato, monkeypatch):
    _scrivi_pid(_pid_isolato, 1234, "/app/data/bin/slskd/slskd")
    monkeypatch.setattr(sd, "_percorso_eseguibile", lambda pid: "/app/data/bin/slskd/slskd")
    assert sd.owned_pid() == 1234


def test_pid_file_con_una_sola_riga_e_stantio(_pid_isolato):
    """Formato vecchio/corrotto (solo il PID, senza l'eseguibile atteso): non
    c'è modo di provare la proprietà, quindi non è un titolo valido."""
    sd.pid_file().write_text("1234")
    assert sd.owned_pid() is None
    assert not sd.pid_file().exists()


def test_stop_rifiutato_senza_pid_nostro(_pid_isolato):
    with pytest.raises(sd.NotOurs):
        sd.stop()


def test_stop_termina_solo_il_nostro(_pid_isolato, monkeypatch):
    _scrivi_pid(_pid_isolato, 1234, "/app/data/bin/slskd/slskd")
    monkeypatch.setattr(sd, "_percorso_eseguibile", lambda pid: "/app/data/bin/slskd/slskd")
    uccisi = []
    monkeypatch.setattr(sd.os, "kill", lambda pid, sig: uccisi.append((pid, sig)))
    monkeypatch.setattr(sd, "_processo_vivo", lambda pid: False)  # muore subito
    sd.stop()
    assert uccisi[0][0] == 1234
    assert not sd.pid_file().exists()


def test_stop_su_processo_gia_morto_non_solleva(_pid_isolato, monkeypatch):
    """Il processo può essere uscito da solo fra il controllo di proprietà e
    l'invio del segnale (race intrinseca a qualunque kill-by-pid): stop()
    voleva comunque arrivare a "demone fermo", non propagare un'eccezione
    grezza e lasciare il pid file in giro."""
    _scrivi_pid(_pid_isolato, 1234, "/app/data/bin/slskd/slskd")
    monkeypatch.setattr(sd, "_percorso_eseguibile", lambda pid: "/app/data/bin/slskd/slskd")

    def muori(pid, sig):
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(sd.os, "kill", muori)
    esito = sd.stop()
    assert esito == {"reachable": False, "owned": False, "pid": None}
    assert not sd.pid_file().exists()


def test_avvio_senza_binario_installato(monkeypatch):
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "")
    monkeypatch.setattr(sd.binary_installer, "installed_path", lambda key: None)
    with pytest.raises(sd.NotInstalled):
        sd.start()


class _FintoProcessoOrfano:
    """Simula lo spawn di `subprocess.Popen`: `/health` non risponderà mai,
    quindi `start()` dovrà arrendersi e tentare di fermare questo processo."""

    pid = 4321

    def __init__(self):
        self.terminato = False
        self.ucciso = False
        self._vivo = True

    def poll(self):
        return None if self._vivo else 0

    def terminate(self):
        self.terminato = True
        self._vivo = False  # risponde subito al SIGTERM

    def kill(self):
        self.ucciso = True
        self._vivo = False

    def wait(self, timeout=None):
        if self._vivo:
            raise sd.subprocess.TimeoutExpired(cmd="slskd", timeout=timeout)
        return 0


def test_avvio_che_non_risponde_e_un_fallimento(tmp_path, monkeypatch):
    """Non ci si fida dello spawn: se /health non risponde mai, l'avvio è
    fallito e va mostrata la coda del log, dove si legge la porta occupata."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")
    monkeypatch.setattr(sd.binary_installer, "installed_path",
                        lambda key: tmp_path / "slskd")
    monkeypatch.setattr(sd, "_ATTESA_AVVIO_S", 0.05)
    monkeypatch.setattr(sd, "_INTERVALLO_S", 0.01)

    monkeypatch.setattr(sd.subprocess, "Popen", lambda *a, **kw: _FintoProcessoOrfano())
    with _client(lambda req: httpx.Response(503)) as c:
        with pytest.raises(sd.StartFailed):
            sd.start(client=c)


def test_avvio_scaduto_ferma_il_processo_orfano(tmp_path, monkeypatch):
    """Se lo spawn non risponde mai in tempo, `start()` non deve solo
    cancellare il pid file: il processo che ha lanciato lui va fermato,
    altrimenti resta un demone detached vivo e permanentemente fuori dalla
    portata di stop() (nessun pid file lo indica più)."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")
    monkeypatch.setattr(sd.binary_installer, "installed_path",
                        lambda key: tmp_path / "slskd")
    monkeypatch.setattr(sd, "_ATTESA_AVVIO_S", 0.05)
    monkeypatch.setattr(sd, "_INTERVALLO_S", 0.01)

    finto = _FintoProcessoOrfano()
    monkeypatch.setattr(sd.subprocess, "Popen", lambda *a, **kw: finto)
    with _client(lambda req: httpx.Response(503)) as c:
        with pytest.raises(sd.StartFailed):
            sd.start(client=c)
    assert finto.terminato, "il processo spawnato e mai confermato va terminato"


def test_stato_riporta_raggiungibile_e_proprieta(_pid_isolato, monkeypatch):
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")
    with _client(lambda req: httpx.Response(200)) as c:
        stato = sd.daemon_status(client=c)
    assert stato == {"reachable": True, "owned": False, "pid": None}


def test_piattaforma_non_posix_rifiuta_owned_pid(monkeypatch):
    """Su Windows non c'è `ps`: niente modo di provare la proprietà di un
    PID. Meglio rifiutare in modo esplicito che tornare `None` per finta e
    cancellare in silenzio un pid file valido (il bug del finding)."""
    monkeypatch.setattr(sd.os, "name", "nt")
    with pytest.raises(sd.UnsupportedPlatform):
        sd.owned_pid()


def test_piattaforma_non_posix_rifiuta_start(monkeypatch):
    monkeypatch.setattr(sd.os, "name", "nt")
    with pytest.raises(sd.UnsupportedPlatform):
        sd.start()


def test_piattaforma_non_posix_rifiuta_stop(_pid_isolato, monkeypatch):
    _scrivi_pid(_pid_isolato, 1234, "/app/data/bin/slskd/slskd")
    monkeypatch.setattr(sd.os, "name", "nt")
    with pytest.raises(sd.UnsupportedPlatform):
        sd.stop()


def test_piattaforma_non_posix_stato_riporta_owned_sconosciuto(_pid_isolato, monkeypatch):
    """`daemon_status` non deve propagare l'errore di piattaforma: uno stato
    letto (non un'azione di gestione) riporta un `owned` esplicitamente
    sconosciuto (`None`), non `False` — che si leggerebbe come "nessun
    demone nostro" quando in realtà non lo si può proprio sapere."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "")
    monkeypatch.setattr(sd.os, "name", "nt")
    stato = sd.daemon_status()
    assert stato["owned"] is None
    assert stato["pid"] is None


def test_config_path_esplicitamente_vuoto_non_risolve_alla_cwd(monkeypatch):
    """Un .env con `SLSKD_CONFIG_PATH=` fa risolvere il setting a stringa
    vuota: `Path("")` risolverebbe silenziosamente alla cwd del processo
    (dove è stato lanciato uvicorn), un posto arbitrario e non sotto il
    controllo dell'app. Deve degradare a un percorso fisso sotto data/."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_config_path", lambda: "")
    percorso = sd.default_config_path()
    assert percorso == sd.BACKEND_DIR / "data" / "slskd.yml"
    assert percorso != sd.Path("")
