"""Controllo integrita' del contenuto audio via ffmpeg (stile plugin badfiles
di beets). Decodifica l'intero stream: cattura header rotti E corruzione a
meta' file. Opzionale: senza ffmpeg nel PATH degrada pulito (non disponibile)."""

import re
import subprocess
from dataclasses import dataclass

from app.services import system_probe

# Pattern che indicano corruzione REALE dei frame audio. Distinguono i veri
# corrotti (frame FLAC/MP3 danneggiati) dagli intoppi benigni non-fatali —
# 'Header missing' a inizio MP3 (ID3/padding, ffmpeg si risincronizza) o gli
# errori sullo stream copertina — che NON vanno segnalati come corruzione.
_REAL_CORRUPTION = re.compile(
    r"invalid residual|invalid sync code|invalid frame header|"
    r"decode_frame\(\) failed|error while decoding", re.IGNORECASE)


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    detail: str | None = None


def ffmpeg_available() -> bool:
    """Delega al seam unico di system_probe (env override, CRATORY_BIN_DIR,
    PATH): stessa fonte di verita' del probe del wizard."""
    return system_probe.resolve_binary("ffmpeg") is not None


def parse_result(returncode: int, stderr: str) -> IntegrityResult:
    """Corrotto se ffmpeg non decodifica (exit!=0) OPPURE se emette errori di
    decodifica-frame reali. Gli errori benigni (Header missing, copertine) su
    un file che si decodifica fino in fondo (exit 0) NON sono corruzione."""
    stderr = (stderr or "").strip()
    if returncode != 0:
        return IntegrityResult(ok=False, detail=stderr[:200] or f"ffmpeg exit {returncode}")
    real = [ln for ln in stderr.splitlines() if _REAL_CORRUPTION.search(ln)]
    if real:
        return IntegrityResult(ok=False, detail=real[0][:200])
    return IntegrityResult(ok=True, detail=None)


def _subprocess_runner(path: str, timeout: int) -> tuple[int, str]:
    # -map 0:a:0 = decodifica SOLO lo stream audio (ignora le copertine
    # incorporate); niente -xerror = decodifica tutto il file, così un
    # intoppo transitorio non aborta il controllo.
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-f", "null", "-"],
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
