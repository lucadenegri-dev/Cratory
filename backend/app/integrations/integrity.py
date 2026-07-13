"""Controllo integrita' del contenuto audio via ffmpeg (stile plugin badfiles
di beets). Decodifica l'intero stream: cattura header rotti E corruzione a
meta' file. Opzionale: senza ffmpeg nel PATH degrada pulito (non disponibile)."""

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    detail: str | None = None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def parse_result(returncode: int, stderr: str) -> IntegrityResult:
    """returncode!=0 oppure stderr non vuoto (con -v error) => corrotto."""
    stderr = (stderr or "").strip()
    if returncode == 0 and not stderr:
        return IntegrityResult(ok=True, detail=None)
    detail = stderr[:200] if stderr else f"ffmpeg exit {returncode}"
    return IntegrityResult(ok=False, detail=detail)


def _subprocess_runner(path: str, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", path, "-f", "null", "-"],
        capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stderr


def check_file(path: str, *, runner=None, timeout: int = 60) -> IntegrityResult:
    """Decodifica il file e ritorna l'esito. runner iniettabile per i test."""
    runner = runner or _subprocess_runner
    try:
        rc, stderr = runner(path, timeout)
    except (subprocess.TimeoutExpired, TimeoutError):
        return IntegrityResult(ok=False, detail="timeout")
    return parse_result(rc, stderr)
