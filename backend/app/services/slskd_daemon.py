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
import time
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


def _yaml() -> YAML:
    yaml = YAML()  # round-trip: preserva commenti e formato
    yaml.preserve_quotes = True
    return yaml


def default_config_path() -> Path:
    """Il percorso configurato: `slskd_config_path()` ha un default non vuoto
    (`~/.config/slskd/slskd.yml`, espanso ad assoluto dal validator dei
    settings), quindi non torna mai vuoto in pratica — niente alternativa
    sotto `data/` da gestire qui."""
    return Path(runtime_settings.slskd_config_path())


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


def write_config(config_path: Path | str, *, username: str, password: str,
                 port: int, download_dir: str) -> None:
    """Scrive SOLO le quattro chiavi che ci servono. Il resto del file resta
    intatto: è dell'utente, e può contenere share, api key e commenti suoi."""
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    yaml = _yaml()

    if config_path.is_file():
        originale = config_path.read_text()
        data = yaml.load(originale) or {}
        modo = stat.S_IMODE(os.stat(config_path).st_mode)
        config_path.with_suffix(config_path.suffix + ".bak").write_text(originale)
    else:
        data = {}
        modo = 0o600  # il file contiene la password Soulseek in chiaro

    data.setdefault("soulseek", {})
    data["soulseek"]["username"] = username
    data["soulseek"]["password"] = password
    data.setdefault("web", {})
    data["web"]["port"] = port
    data.setdefault("directories", {})
    data["directories"]["downloads"] = download_dir

    buf = io.StringIO()
    yaml.dump(data, buf)
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.write_text(buf.getvalue())
    os.chmod(tmp, modo)
    os.replace(tmp, config_path)


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


def _riga_di_comando(pid: int) -> str:
    """La riga di comando del processo, o stringa vuota. Serve a distinguere
    'il nostro slskd' da 'un processo qualsiasi che ha ereditato quel PID':
    il sistema operativo riusa i PID, quindi un PID da solo non è mai prova
    di proprietà."""
    try:
        proc = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                              capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip()


def _processo_e_slskd(pid: int) -> bool:
    return "slskd" in _riga_di_comando(pid)


def _processo_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def owned_pid() -> int | None:
    """Il PID del demone che abbiamo avviato noi, se esiste ed è ancora lui.

    Un PID vecchio può essere stato riassegnato dal sistema a tutt'altro
    processo: prima di considerarlo nostro si controlla che la riga di
    comando parli davvero di slskd. Se non torna, il file è stantio (o punta
    a un estraneo) e va rimosso: non è più un titolo valido a fermare nulla.
    """
    f = pid_file()
    if not f.is_file():
        return None
    try:
        pid = int(f.read_text().strip())
    except ValueError:
        f.unlink(missing_ok=True)
        return None
    if not _processo_e_slskd(pid):
        f.unlink(missing_ok=True)
        return None
    return pid


def daemon_status(client: httpx.Client | None = None) -> dict:
    pid = owned_pid()
    return {"reachable": is_reachable(client), "owned": pid is not None, "pid": pid}


def start(client: httpx.Client | None = None) -> dict:
    """Avvia il demone come processo indipendente, poi verifica che risponda.

    `start_new_session=True`: il processo deve sopravvivere alla chiusura di
    Cratory, altrimenti chiudere la finestra interromperebbe una coda di
    download Soulseek in corso — peggio che non avere il demone affatto.
    """
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
    pid_file().write_text(str(proc.pid))

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
    os.kill(pid, signal.SIGTERM)
    scadenza = time.monotonic() + 10
    while time.monotonic() < scadenza and _processo_vivo(pid):
        time.sleep(_INTERVALLO_S)
    if _processo_vivo(pid):
        os.kill(pid, signal.SIGKILL)
    pid_file().unlink(missing_ok=True)
    return {"reachable": False, "owned": False, "pid": None}
