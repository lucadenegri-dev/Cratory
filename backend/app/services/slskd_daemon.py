"""Configurazione, avvio, arresto e stato del demone slskd.

Deroga consapevole al confine "slskd è un servizio esterno raggiunto via
HTTP": qui Cratory lo configura e lo avvia. Due regole tengono la deroga
sotto controllo — non si distrugge la configurazione dell'utente, e non si
ferma mai un processo che non abbiamo avviato noi.
"""
from __future__ import annotations

import io
import logging
import os
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from ruamel.yaml import YAML

from app.core import runtime_settings
from app.core.config import BACKEND_DIR
from app.services import binary_installer

log = logging.getLogger(__name__)

DEFAULT_PORT = 5030

# Quanto aspettare che /health risponda dopo lo spawn, e ogni quanto ricontrollare.
_ATTESA_AVVIO_S = 20.0
_INTERVALLO_S = 0.5
_TIMEOUT_HTTP_S = 3.0


class DaemonError(Exception):
    pass


class NotInstalled(DaemonError):
    pass


class AlreadyUp(DaemonError):
    """Qualcosa risponde già all'URL: non ne avviamo un secondo."""


class NotOurs(DaemonError):
    """Non abbiamo un PID nostro valido: non fermiamo processi altrui."""


class StartFailed(DaemonError):
    pass


class UnsupportedPlatform(DaemonError):
    """Windows non ha `ps` (per verificare di chi è un PID) né `SIGKILL`: senza
    un modo per provare che un PID è ancora il processo che abbiamo avviato,
    gestire il ciclo di vita significherebbe o non funzionare mai (il bug che
    questa eccezione sostituisce: `owned_pid()` tornava sempre `None` e
    cancellava il pid file ad ogni chiamata) o rischiare di firmare processi
    altrui. Meglio rifiutarsi esplicitamente che fingere di funzionare."""


def _yaml() -> YAML:
    yaml = YAML()  # round-trip: preserva commenti e formato
    yaml.preserve_quotes = True
    return yaml


def default_config_path() -> Path:
    """Il percorso configurato: `slskd_config_path()` ha un default non vuoto
    (`~/.config/slskd/slskd.yml`, espanso ad assoluto dal validator dei
    settings), ma un `.env` può azzerarlo esplicitamente (`SLSKD_CONFIG_PATH=`):
    in quel caso il setting risolto è `""`, e `Path("")` risolverebbe alla
    cwd del processo — un posto che dipende da dove è stato lanciato
    uvicorn, non da dove sta l'app. Si degrada invece a un percorso fisso
    sotto `data/`, come `pid_file()`/`log_file()`."""
    valore = runtime_settings.slskd_config_path()
    if not valore:
        return BACKEND_DIR / "data" / "slskd.yml"
    return Path(valore)


def read_username(config_path: Path | str) -> str | None:
    """L'username non è un segreto come la password: si può rileggere e
    mostrare, così l'utente vede con quale account è configurato."""
    config_path = Path(config_path)
    if not config_path.is_file():
        return None
    try:
        data = _yaml().load(config_path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001 - un yaml rotto non deve dare 500
        log.warning("slskd.yml illeggibile: %s", exc)
        return None
    return (data.get("soulseek") or {}).get("username")


def _cartella_download_default() -> Path:
    """Cartella di download proposta quando l'utente non ne ha scelta una e
    nemmeno le impostazioni di Cratory ne hanno già una (primo avvio, campo
    lasciato vuoto): deve pur esistere qualcosa da scrivere in slskd.yml.
    Stesso trattamento di `pid_file()`/`log_file()`/`default_config_path()`,
    sotto la cartella dati dell'app."""
    return BACKEND_DIR / "data" / "slskd-downloads"


@dataclass(frozen=True)
class ConfigWritten:
    """Cosa è stato effettivamente scritto in slskd.yml, per chi deve
    allineare le impostazioni di Cratory quando il file nasce da zero (vedi
    `write_config`)."""
    created: bool
    port: int
    download_dir: str


def write_config(config_path: Path | str, *, username: str, password: str,
                 port: int | None = None, download_dir: str | None = None) -> ConfigWritten:
    """Scrive SOLO le quattro chiavi che ci servono. Il resto del file resta
    intatto: è dell'utente, e può contenere share, api key e commenti suoi.

    `port` e `download_dir` sono opzionali: `None` vuol dire "il chiamante
    non l'ha specificato, lascia stare quel che c'è già nel file". I default
    (`DEFAULT_PORT`, la cartella download dell'app) si applicano SOLO quando
    il file non esiste ancora — un primo setup, dove il valore deve pur
    venire da qualche parte. Non vanno risolti prima, nel chiamante: se il
    router riempisse qui un default per un campo omesso, non ci sarebbe più
    modo di distinguerlo da un valore scelto davvero dall'utente, e ogni
    giro riscriverebbe silenziosamente porta e cartella — la corruzione che
    il finding critico ha trovato. Non "semplificare" via questo `None`
    risolvendo i default a monte: è la distinzione che serve.

    Ritorna cosa è stato scritto per davvero (`ConfigWritten`): il chiamante
    (il router) ne ha bisogno per scrivere anche nelle impostazioni di
    Cratory quando il file è nuovo. `slskd_url()` è vuoto di default, ed è il
    criterio con cui `is_reachable()`/`start()` decidono se il demone ha
    risposto: senza riportare qui la porta scelta, un `start()` su una
    configurazione appena creata scarica, installa e avvia slskd per davvero
    e lo giudica comunque fallito, perché non sa a quale URL bussare.
    """
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    yaml = _yaml()

    file_nuovo = not config_path.is_file()
    if not file_nuovo:
        originale = config_path.read_text()
        data = yaml.load(originale) or {}
        modo = stat.S_IMODE(os.stat(config_path).st_mode)
        _scrivi_backup(config_path, originale, modo)
    else:
        data = {}
        modo = 0o600  # il file contiene la password Soulseek in chiaro

    data.setdefault("soulseek", {})
    data["soulseek"]["username"] = username
    data["soulseek"]["password"] = password

    data.setdefault("web", {})
    if port is not None:
        data["web"]["port"] = port
    elif file_nuovo:
        data["web"]["port"] = DEFAULT_PORT

    data.setdefault("directories", {})
    if download_dir is not None:
        data["directories"]["downloads"] = download_dir
    elif file_nuovo:
        proposta = runtime_settings.slskd_download_dir()
        if not proposta:
            proposta = str(_cartella_download_default())
            Path(proposta).mkdir(parents=True, exist_ok=True)
        data["directories"]["downloads"] = proposta

    buf = io.StringIO()
    yaml.dump(data, buf)
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.write_text(buf.getvalue())
    os.chmod(tmp, modo)
    os.replace(tmp, config_path)

    return ConfigWritten(created=file_nuovo, port=data["web"]["port"],
                         download_dir=data["directories"]["downloads"])


def _scrivi_backup(config_path: Path, contenuto: str, modo: int) -> None:
    """Salva l'originale prima di sovrascriverlo. Stessa cautela del file
    vero: contiene la stessa password in chiaro, quindi non può finire con
    permessi più larghi solo perché `Path.write_text()` applica lo umask
    invece di rispettare `modo` — il file principale dodici righe sotto lo
    fa apposta (`os.chmod`), il backup deve fare lo stesso o la password
    resta leggibile da chiunque altro sulla macchina."""
    config_path.with_suffix(config_path.suffix + ".bak").write_text(contenuto)
    os.chmod(config_path.with_suffix(config_path.suffix + ".bak"), modo)


def pid_file() -> Path:
    return BACKEND_DIR / "data" / "slskd.pid"


def log_file() -> Path:
    return BACKEND_DIR / "data" / "slskd.log"


def is_reachable(client: httpx.Client | None = None) -> bool:
    """Qualcosa risponde già all'URL configurato? Non ci interessa CHI: può
    essere il nostro demone, o quello che l'utente gestisce da sé — in
    entrambi i casi non se ne avvia un secondo."""
    url = runtime_settings.slskd_url()
    if not url:
        return False
    owned = client is None
    client = client or httpx.Client()
    try:
        res = client.get(f"{url.rstrip('/')}/health", timeout=_TIMEOUT_HTTP_S)
        return res.status_code < 500
    except httpx.HTTPError:
        return False
    finally:
        if owned:
            client.close()


def _piattaforma_supportata() -> bool:
    """`ps` e `SIGKILL` esistono solo su POSIX: su Windows non c'è modo, con
    la sola libreria standard, di chiedere al sistema quale eseguibile sta
    dietro a un PID."""
    return os.name == "posix"


def _richiedi_piattaforma_supportata() -> None:
    if not _piattaforma_supportata():
        raise UnsupportedPlatform(
            "la gestione del demone slskd (avvio/arresto) non è disponibile "
            "su questa piattaforma"
        )


def _percorso_eseguibile(pid: int) -> str:
    """Il percorso assoluto dell'eseguibile del processo, o stringa vuota se
    il PID non esiste più o la lettura fallisce.

    Seam unico per le due piattaforme POSIX supportate: il resto del modulo
    chiama solo questa funzione e non deve sapere quale sistema operativo è
    sotto. `ps -o comm=` NON significa la stessa cosa sulle due: su macOS
    stampa il percorso assoluto dell'eseguibile (quello che serve al
    confronto esatto in `_processo_e_slskd`), ma su Linux `comm` viene da
    `/proc/[pid]/comm`, che contiene SOLO il basename dell'eseguibile,
    troncato a 15 caratteri — mai un percorso. Con `ps` anche su Linux il
    confronto esatto non incrocerebbe MAI per nessun processo: la prima
    `owned_pid()` dopo uno `start()` riuscito cancellerebbe il pid file
    appena scritto, e ogni `stop()` successivo solleverebbe `NotOurs` mentre
    il demone che abbiamo lanciato resta vivo, non tracciato e non fermabile.
    Linux espone invece il percorso vero del proprio eseguibile come link
    simbolico in `/proc/[pid]/exe`: lo si legge con `os.readlink`, senza `ps`.
    """
    if sys.platform.startswith("linux"):
        return _percorso_eseguibile_linux(pid)
    return _percorso_eseguibile_macos(pid)


def _percorso_eseguibile_linux(pid: int) -> str:
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return ""  # PID non esiste più, o /proc/[pid]/exe non leggibile


def _percorso_eseguibile_macos(pid: int) -> str:
    """Si usa `comm` e non `command` (che include gli argomenti) perché quello
    che va confrontato con l'eseguibile installato è SOLO il binario
    lanciato, non il resto della riga: `slskd --config /path/vim.yml` e
    `vim /path/slskd.yml` condividono la sottostringa "slskd" da qualche
    parte nella riga, ma solo il primo ha lanciato il nostro eseguibile.
    Funziona perché `start()` lancia sempre l'eseguibile con il suo percorso
    assoluto (mai per nome via PATH): `comm` su un processo avviato così
    riporta quello stesso percorso assoluto, non solo il basename — a
    differenza di Linux, dove `comm` è sempre e solo un basename tronco.
    """
    try:
        proc = subprocess.run(["ps", "-p", str(pid), "-o", "comm="],
                              capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip()


def _processo_e_slskd(pid: int, atteso: Path) -> bool:
    """Il processo `pid` è ancora, davvero, l'eseguibile slskd che abbiamo
    installato e lanciato noi?

    Un PID da solo non è mai prova: il sistema operativo li riusa, quindi un
    PID vecchio può oggi appartenere a un processo qualsiasi dell'utente — il
    caso concreto che questo controllo deve escludere è l'utente che apre
    `vim ~/.config/slskd/slskd.yml` per modificare la config, la cui riga di
    comando contiene "slskd" pur non essendo affatto il nostro demone.
    Una sottostringa nella riga di comando non è evidenza: lo è invece sapere
    quale eseguibile abbiamo lanciato (`atteso`, scritto nel pid file da
    `start()`) e verificare che il processo vivo sotto quel PID sia ancora
    esattamente quello — non "un programma il cui nome contiene slskd", ma
    bit per bit lo stesso percorso su disco che abbiamo avviato.
    """
    percorso = _percorso_eseguibile(pid)
    if not percorso:
        return False
    return Path(percorso).resolve() == atteso.resolve()


def _processo_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def owned_pid() -> int | None:
    """Il PID del demone che abbiamo avviato noi, se esiste ed è ancora lui.

    Il pid file contiene due righe: il PID e il percorso assoluto
    dell'eseguibile lanciato da `start()`. Un PID vecchio può essere stato
    riassegnato dal sistema a tutt'altro processo: prima di considerarlo
    nostro si controlla che il processo vivo sotto quel PID sia ancora
    esattamente quell'eseguibile (`_processo_e_slskd`). Se non torna, il
    file è stantio (o punta a un estraneo) e va rimosso: non è più un titolo
    valido a fermare nulla.
    """
    _richiedi_piattaforma_supportata()
    f = pid_file()
    if not f.is_file():
        return None
    righe = f.read_text().splitlines()
    if len(righe) < 2:
        f.unlink(missing_ok=True)
        return None
    try:
        pid = int(righe[0].strip())
    except ValueError:
        f.unlink(missing_ok=True)
        return None
    atteso = Path(righe[1].strip())
    if not _processo_e_slskd(pid, atteso):
        f.unlink(missing_ok=True)
        return None
    return pid


def daemon_status(client: httpx.Client | None = None) -> dict:
    """`owned` è un tristate: `True`/`False` quando sappiamo rispondere,
    `None` quando la piattaforma non lo consente (Windows) — mai `False` per
    finta, che verrebbe letto come "nessun demone nostro" quando in realtà
    non lo si può proprio sapere."""
    try:
        pid = owned_pid()
        owned: bool | None = pid is not None
    except UnsupportedPlatform:
        pid = None
        owned = None
    return {"reachable": is_reachable(client), "owned": owned, "pid": pid}


def _termina_orfano(proc: subprocess.Popen) -> None:
    """Il processo spawnato non ha mai risposto in tempo: `start()` sta per
    rinunciare e cancellare il pid file, ma quel che abbiamo lanciato noi
    resta comunque una nostra responsabilità. Senza questo, resterebbe un
    demone detached vivo e fuori dalla portata di `stop()` per sempre — un
    orfano permanente, non un errore che si può ritentare pulito."""
    if proc.poll() is not None:
        return  # già morto da solo
    try:
        proc.terminate()
    except ProcessLookupError:
        # Stessa race già gestita in stop(): morto da solo fra il poll() e
        # l'invio del segnale. Non è un errore, è lo stato che si voleva.
        return
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.kill()
    except ProcessLookupError:
        return  # morto nell'istante fra il timeout e SIGKILL
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log.warning("slskd (pid %s) non ha risposto neanche a SIGKILL", proc.pid)


def start(client: httpx.Client | None = None) -> dict:
    """Avvia il demone come processo indipendente, poi verifica che risponda.

    `start_new_session=True`: il processo deve sopravvivere alla chiusura di
    Cratory, altrimenti chiudere la finestra interromperebbe una coda di
    download Soulseek in corso — peggio che non avere il demone affatto.
    """
    _richiedi_piattaforma_supportata()
    if is_reachable(client):
        raise AlreadyUp("slskd risponde già all'URL configurato")
    exe = binary_installer.installed_path("slskd")
    if exe is None:
        raise NotInstalled("slskd non è installato nella cartella dell'app")

    config = default_config_path()
    with log_file().open("ab") as out:
        proc = subprocess.Popen(
            [str(exe), "--config", str(config)],
            stdout=out, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    # Due righe: PID ed eseguibile lanciato. `owned_pid()` non si fida del
    # solo PID (riassegnabile dal sistema) e verifica che il processo vivo
    # sotto quel PID sia ancora esattamente questo binario.
    pid_file().write_text(f"{proc.pid}\n{exe}\n")

    # Non ci si fida dello spawn: il processo può partire e morire subito
    # dopo (porta occupata, credenziali sbagliate). Si aspetta che risponda
    # davvero su HTTP prima di dichiarare l'avvio riuscito.
    scadenza = time.monotonic() + _ATTESA_AVVIO_S
    while time.monotonic() < scadenza:
        if is_reachable(client):
            return daemon_status(client)
        if proc.poll() is not None:
            break
        time.sleep(_INTERVALLO_S)

    pid_file().unlink(missing_ok=True)
    _termina_orfano(proc)
    coda = ""
    if log_file().is_file():
        coda = "\n".join(log_file().read_text(errors="replace").splitlines()[-15:])
    raise StartFailed(coda or "slskd non ha risposto entro il tempo previsto")


def stop() -> dict:
    """Ferma SOLO il demone che abbiamo avviato noi: `owned_pid()` è l'unico
    titolo che autorizza a inviare un segnale, perché un PID riciclato dal
    sistema potrebbe altrimenti far terminare un processo qualsiasi
    dell'utente."""
    pid = owned_pid()
    if pid is None:
        raise NotOurs("nessun demone avviato da Cratory")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        # Già finito da solo fra la verifica di proprietà e il segnale: non è
        # un errore, è esattamente lo stato che stop() voleva raggiungere.
        pid_file().unlink(missing_ok=True)
        return {"reachable": False, "owned": False, "pid": None}
    scadenza = time.monotonic() + 10
    while time.monotonic() < scadenza and _processo_vivo(pid):
        time.sleep(_INTERVALLO_S)
    if _processo_vivo(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # morto nell'istante fra il controllo e il segnale
    pid_file().unlink(missing_ok=True)
    return {"reachable": False, "owned": False, "pid": None}
