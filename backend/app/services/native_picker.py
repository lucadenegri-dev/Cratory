"""Dialog nativo macOS (Finder) per scegliere cartelle o file, via osascript.

Solo macOS: `picker_available()` fa da guardia. Il dialog è un'interazione
utente sulla macchina del backend: un lock di modulo impedisce due dialog
contemporanei, il timeout evita worker appesi se il dialog resta ignorato.
Annullo e timeout diventano `None` (nessuna scelta), mai eccezioni.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path

TIMEOUT_SECONDS = 300.0

_lock = threading.Lock()


class PickerBusyError(Exception):
    """Un dialog di scelta è già aperto."""


class PickerUnavailableError(Exception):
    """Piattaforma non macOS oppure osascript assente."""


def picker_available() -> bool:
    return sys.platform == "darwin" and shutil.which("osascript") is not None


def _escape(text: str) -> str:
    """Escape per stringhe AppleScript tra doppi apici."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_script(kind: str, start: str | None, prompt: str | None) -> str:
    """AppleScript `choose folder`/`choose file` dentro System Events attivato:
    porta il dialog in primo piano anche se il backend gira in background.
    `start` diventa `default location` solo se è una directory esistente."""
    choose = "choose folder" if kind == "folder" else "choose file"
    if prompt:
        choose += f' with prompt "{_escape(prompt)}"'
    if start:
        start_dir = Path(start).expanduser()
        if start_dir.is_dir():
            choose += f' default location (POSIX file "{_escape(str(start_dir))}")'
    return (
        'tell application "System Events"\n'
        "activate\n"
        f"POSIX path of ({choose})\n"
        "end tell"
    )


def pick_path(kind: str, start: str | None = None, prompt: str | None = None,
              *, runner=subprocess.run) -> str | None:
    """Percorso scelto nel dialog, o `None` se l'utente annulla o il dialog scade.

    `runner` ha la firma di `subprocess.run` ed è iniettabile nei test:
    osascript reale mai eseguito in CI."""
    if not picker_available():
        raise PickerUnavailableError
    if not _lock.acquire(blocking=False):
        raise PickerBusyError
    try:
        try:
            proc = runner(
                ["osascript", "-e", build_script(kind, start, prompt)],
                capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return None
        if proc.returncode != 0:  # annullo utente (error -128) o errore script
            return None
        path = proc.stdout.strip()
        if kind == "folder":
            path = path.rstrip("/") or "/"  # `choose folder` termina con "/"
        return path or None
    finally:
        _lock.release()
