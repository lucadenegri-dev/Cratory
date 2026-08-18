"""Installazione dei componenti che stanno nel perimetro dell'app (il venv).

Perimetro stretto per scelta: si installa solo ciò che è `auto_installable` nel
registry del probe — oggi `yt-dlp` ed `essentia`. I componenti di sistema
(ffmpeg, fpcalc) e il demone slskd non si installano da qui: il wizard mostra
il comando e lascia fare all'utente.

`run_recipe` è l'UNICO punto in cui questo modulo esegue un processo esterno:
in Tauri sarà quello da sostituire, non i suoi chiamanti.
"""
from __future__ import annotations

import logging
import subprocess
import threading
from typing import Iterator

from app.services import system_probe
from app.services.job_spawn import spawn

log = logging.getLogger(__name__)

MAX_LOG_LINES = 500


class InstallError(Exception):
    pass


class UnknownComponent(InstallError):
    pass


class NotAutoInstallable(InstallError):
    pass


class AlreadyRunning(InstallError):
    pass


class InstallFailed(InstallError):
    pass


_lock = threading.Lock()
_state: dict = {"key": None, "status": "idle", "log": [], "detail": None}


def reset() -> None:
    """Riporta l'installer a riposo (usato dai test)."""
    with _lock:
        _state.update({"key": None, "status": "idle", "log": [], "detail": None})


def status() -> dict:
    with _lock:
        return {**_state, "log": list(_state["log"])}


def run_recipe(argv: list[str]) -> Iterator[str]:
    """Esegue una ricetta e produce le righe di output.

    `shell=False` (default di Popen) e `argv` come lista: nessuna stringa viene
    mai interpretata da una shell, e nessun input utente entra qui — le ricette
    arrivano solo dal registry.
    """
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        yield line.rstrip()
    returncode = proc.wait()
    if returncode != 0:
        raise InstallFailed(f"{argv[0]} è uscito con codice {returncode}")


def _append(line: str) -> None:
    with _lock:
        _state["log"].append(line)
        if len(_state["log"]) > MAX_LOG_LINES:
            del _state["log"][0:len(_state["log"]) - MAX_LOG_LINES]


def start(key: str) -> dict:
    """Avvia l'installazione di un componente. Solo ricette del registry."""
    component = system_probe.get(key)
    if component is None:
        raise UnknownComponent(key)
    if not component.auto_installable:
        raise NotAutoInstallable(key)
    recipe = system_probe.recipe_for(component)
    if recipe is None:
        raise NotAutoInstallable(key)

    with _lock:
        if _state["status"] == "running":
            raise AlreadyRunning(_state["key"])
        _state.update({"key": key, "status": "running", "log": [], "detail": None})

    def run() -> None:
        try:
            for line in run_recipe(recipe):
                _append(line)
        except (InstallFailed, OSError) as exc:
            log.warning("installazione di %s fallita: %s", key, exc)
            with _lock:
                _state.update({"status": "error", "detail": str(exc)})
            return
        # Invalida la cache del probe (variabile privata di system_probe, non
        # una ri-esecuzione live): il prossimo GET /api/setup/probe deve
        # vedere il componente appena installato, ma questo thread non deve
        # a sua volta lanciare ffmpeg/fpcalc/essentia/slskd — sarebbe lavoro
        # non necessario qui e renderebbe l'installer accoppiato ai
        # sottoprocessi (e all'host) del probe.
        system_probe._cache = None
        with _lock:
            _state.update({"status": "done", "detail": None})

    spawn(run)
    return status()
