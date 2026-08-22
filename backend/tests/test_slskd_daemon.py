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


def test_percorso_eseguibile_su_linux_legge_proc_exe(monkeypatch):
    """Su Linux `ps -o comm=` darebbe solo il basename troncato a 15
    caratteri (viene da /proc/[pid]/comm, non dall'intero percorso): il
    confronto esatto con l'eseguibile installato non incrocerebbe mai. Il
    percorso vero si legge dal link simbolico /proc/[pid]/exe."""
    monkeypatch.setattr(sd.sys, "platform", "linux")

    def _finto_readlink(path):
        assert path == "/proc/1234/exe"
        return "/app/data/bin/slskd/slskd"

    monkeypatch.setattr(sd.os, "readlink", _finto_readlink)
    assert sd._percorso_eseguibile(1234) == "/app/data/bin/slskd/slskd"


def test_percorso_eseguibile_su_linux_pid_inesistente_e_vuoto(monkeypatch):
    """/proc/[pid]/exe non esiste per un PID morto: niente stack trace,
    stringa vuota come sulle altre strade di fallimento."""
    monkeypatch.setattr(sd.sys, "platform", "linux")

    def _rompi(path):
        raise OSError(2, "No such file or directory")

    monkeypatch.setattr(sd.os, "readlink", _rompi)
    assert sd._percorso_eseguibile(999999) == ""


def test_percorso_eseguibile_su_macos_usa_ps_comm(monkeypatch):
    """Su macOS `ps -o comm=` riporta già il percorso assoluto: è la strada
    che il modulo usava prima del fix, e deve restare l'unica su questa
    piattaforma (niente /proc su macOS)."""
    monkeypatch.setattr(sd.sys, "platform", "darwin")

    def _finto_run(argv, **kw):
        assert argv == ["ps", "-p", "1234", "-o", "comm="]
        return sd.subprocess.CompletedProcess(argv, 0, stdout="/app/data/bin/slskd/slskd\n", stderr="")

    monkeypatch.setattr(sd.subprocess, "run", _finto_run)
    assert sd._percorso_eseguibile(1234) == "/app/data/bin/slskd/slskd"


def test_percorso_eseguibile_su_macos_ps_fallito_e_vuoto(monkeypatch):
    monkeypatch.setattr(sd.sys, "platform", "darwin")

    def _rompi(argv, **kw):
        raise OSError("ps non trovato")

    monkeypatch.setattr(sd.subprocess, "run", _rompi)
    assert sd._percorso_eseguibile(1234) == ""


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


def test_demone_nostro_vivo_ma_url_sbagliato_non_ne_avvia_un_secondo(_pid_isolato, monkeypatch):
    """Riproduce il finding B1: `slskd_url` punta altrove (typo, impostazione
    stantia) mentre il demone che abbiamo avviato noi è vivo per davvero.
    `is_reachable()` dice di no perché bussa all'URL sbagliato: senza il
    controllo su `owned_pid()`, `start()` ne spawnerebbe un secondo, che
    collide sulla porta del primo e muore — `StartFailed` cancellerebbe il
    pid file di QUESTO tentativo, mentre il primo demone, ancora vivo, resta
    senza un pid file che lo tracci: orfano, mai più fermabile da `stop()`."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://url-sbagliato:9999")
    _scrivi_pid(_pid_isolato, 4242, "/app/data/bin/slskd/slskd")
    monkeypatch.setattr(sd, "_percorso_eseguibile", lambda pid: "/app/data/bin/slskd/slskd")

    def esplodi(argv, **kw):
        raise AssertionError("non doveva lanciare un secondo processo")

    monkeypatch.setattr(sd.subprocess, "Popen", esplodi)
    with _client(lambda req: httpx.Response(503)) as c:
        with pytest.raises(sd.AlreadyOwned):
            sd.start(client=c)
    assert sd.pid_file().exists(), "il pid file del demone vivo non va toccato"


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


class _FintoProcessoOrfanoCheSparisceDaSolo:
    """Simula la stessa race già corretta in stop(): il processo spawnato
    muore da solo fra il controllo (`poll()`, che qui riporta ancora vivo) e
    l'invio del segnale — `terminate()` alza `ProcessLookupError`, come
    farebbe `os.kill` in quella finestra."""

    pid = 4321

    def poll(self):
        return None  # ancora vivo secondo l'ultimo controllo

    def terminate(self):
        raise ProcessLookupError(3, "No such process")

    def kill(self):
        raise AssertionError("non doveva tentare SIGKILL dopo un terminate() già a vuoto")

    def wait(self, timeout=None):
        raise AssertionError("non doveva aspettare un processo già sparito")


def test_avvio_scaduto_processo_orfano_gia_sparito_non_solleva(tmp_path, monkeypatch):
    """Riproduce il finding minore: senza guardia, `ProcessLookupError` da
    `terminate()` si propagherebbe grezzo al posto di `StartFailed`, la
    stessa classe di bug appena corretta in stop()."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")
    monkeypatch.setattr(sd.binary_installer, "installed_path",
                        lambda key: tmp_path / "slskd")
    monkeypatch.setattr(sd, "_ATTESA_AVVIO_S", 0.05)
    monkeypatch.setattr(sd, "_INTERVALLO_S", 0.01)

    finto = _FintoProcessoOrfanoCheSparisceDaSolo()
    monkeypatch.setattr(sd.subprocess, "Popen", lambda *a, **kw: finto)
    with _client(lambda req: httpx.Response(503)) as c:
        with pytest.raises(sd.StartFailed):
            sd.start(client=c)


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
    assert percorso == sd.paths.DATA_DIR / "data" / "slskd.yml"
    assert percorso != sd.Path("")
