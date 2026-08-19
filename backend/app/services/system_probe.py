"""Rilevamento dei componenti esterni di cui Cratory ha bisogno.

Un registry dichiarativo, una voce per componente: come si rileva, che cosa
sblocca, se è installabile in automatico e con quale comando. Il registry NON
contiene prosa — solo chiavi: descrizioni e istruzioni vivono nei dizionari
i18n del frontend.

Confine Tauri: `resolve_binary` guarda prima `CRATORY_BIN_DIR`, poi (per i
componenti `kind="venv"`) la cartella dell'interprete in esecuzione, poi il
PATH. Quando i binari arriveranno impacchettati nel bundle basterà far
partire il processo con quella variabile impostata — qui non cambia nulla.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.core import runtime_settings

log = logging.getLogger(__name__)

BIN_DIR_ENV = "CRATORY_BIN_DIR"
_CACHE_TTL_S = 10.0
_PROBE_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class Component:
    key: str
    kind: Literal["system", "venv", "daemon"]
    severity: Literal["required", "optional"]
    # Chiavi di feature, non prosa: il frontend le traduce.
    unlocks: tuple[str, ...]
    auto_installable: bool
    # `sys.platform` -> argv. La chiave "*" vale per ogni piattaforma.
    recipes: dict[str, list[str]] = field(default_factory=dict)
    binary: str | None = None
    version_flag: str = "--version"
    env_override: str | None = None
    # Componente che nel codice si usa come `import X`, non come eseguibile:
    # va rilevato importandolo, perche' un binario omonimo nel PATH non dice
    # niente sulla presenza del modulo nel venv.
    python_module: str | None = None
    # Dove leggere se la ricetta non fa al caso proprio (o non esiste).
    docs: str = ""


REGISTRY: tuple[Component, ...] = (
    Component(
        key="ffmpeg", kind="system", severity="required",
        unlocks=("audio_hash", "shazam", "soundcloud_download"),
        auto_installable=False,
        recipes={
            "darwin": ["brew", "install", "ffmpeg"],
            "linux": ["sudo", "apt", "install", "-y", "ffmpeg"],
            "win32": ["winget", "install", "-e", "--id", "Gyan.FFmpeg"],
        },
        binary="ffmpeg", version_flag="-version",
        docs="https://ffmpeg.org/download.html",
    ),
    Component(
        key="fpcalc", kind="system", severity="optional",
        unlocks=("acoustid_fingerprint",),
        auto_installable=False,
        recipes={
            "darwin": ["brew", "install", "chromaprint"],
            "linux": ["sudo", "apt", "install", "-y", "libchromaprint-tools"],
            "win32": ["winget", "install", "-e", "--id", "AcoustID.Chromaprint"],
        },
        binary="fpcalc", version_flag="-version", env_override="FPCALC",
        docs="https://acoustid.org/chromaprint",
    ),
    Component(
        key="yt-dlp", kind="venv", severity="optional",
        unlocks=("soundcloud_import", "soundcloud_download", "shazam"),
        auto_installable=True,
        recipes={"*": [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"]},
        python_module="yt_dlp",
        docs="https://github.com/yt-dlp/yt-dlp#installation",
    ),
    Component(
        key="essentia", kind="venv", severity="optional",
        unlocks=("analysis_bpm_key",),
        auto_installable=True,
        # `--only-binary=:all:`: il pin ha wheel solo per cp311/macOS-arm64.
        # Senza il flag, altrove pip compilerebbe da sorgente e l'installazione
        # resterebbe appesa; così fallisce subito e la UI mostra la ricetta.
        recipes={"*": [sys.executable, "-m", "pip", "install",
                       "--only-binary=:all:", "essentia==2.1b6.dev1389"]},
        python_module="essentia",
        docs="https://essentia.upf.edu/installing.html",
    ),
    Component(
        key="slskd", kind="daemon", severity="optional",
        unlocks=("soulseek_download", "library_share"),
        auto_installable=False,
        # Nessuna ricetta: e' un demone separato, si scarica dalle sue release
        # e si configura a parte. Il link e' l'unica indicazione che possiamo
        # dare, e va data.
        docs="https://github.com/slskd/slskd/releases",
    ),
)

_BY_KEY = {c.key: c for c in REGISTRY}


def get(key: str) -> Component | None:
    return _BY_KEY.get(key)


def resolve_binary(name: str, env_override: str | None = None, *, venv: bool = False) -> str | None:
    """Percorso del binario, o None. Ordine: env specifica del componente →
    CRATORY_BIN_DIR (bundle) → interprete del venv (solo se `venv=True`) → PATH.

    `venv=True` va passato solo per i componenti `kind="venv"` (es. yt-dlp):
    vivono nel virtualenv dell'app, non nel PATH del processo. Se il backend
    parte con `<venv>/bin/python -m uvicorn …` senza `source .venv/bin/activate`,
    `<venv>/bin` non finisce mai nel PATH e `shutil.which` non lo trova — pur
    essendo il binario installato e funzionante. `sys.executable` è sempre
    l'interprete che sta effettivamente girando, quindi il suo parent
    (`<venv>/bin`, o `<venv>\\Scripts` su Windows) è la posizione giusta a
    prescindere da come il processo è stato lanciato: niente più dipendenza
    dall'attivazione della shell, condizione che vale anche per il futuro
    bundle Tauri, dove nessuno attiva nulla."""
    if env_override:
        custom = os.environ.get(env_override)
        if custom and Path(custom).is_file():
            return custom
    bundled = os.environ.get(BIN_DIR_ENV)
    if bundled:
        candidate = Path(bundled) / name
        if candidate.is_file():
            return str(candidate)
    if venv:
        candidate = Path(sys.executable).parent / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def recipe_for(component: Component) -> list[str] | None:
    """Comando di installazione per la piattaforma corrente, o None se non
    esiste (es. slskd, che è un demone da installare a parte)."""
    if not component.recipes:
        return None
    return component.recipes.get(sys.platform) or component.recipes.get("*")


def _run_version(argv: list[str]) -> str | None:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=_PROBE_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("probe: %s non eseguibile (%s)", argv[0], exc)
        return None
    if proc.returncode != 0:
        # Senza questo, lo stderr di un fallimento (il "Traceback (most recent
        # call last):" di un ImportError) veniva restituito come se fosse una
        # versione, e il componente risultava presente.
        log.debug("probe: %s uscito con %s", argv[0], proc.returncode)
        return None
    output = (proc.stdout or proc.stderr or "").strip()
    return output.splitlines()[0][:120] if output else None


def _probe_binary(c: Component) -> dict:
    path = resolve_binary(c.binary or c.key, c.env_override, venv=c.kind == "venv")
    if not path:
        return {"present": False, "version": None, "source": None}
    resolved = Path(path)
    # Confronto per directory/percorso esatto, non prefisso di stringa: con
    # CRATORY_BIN_DIR="/opt/bin" un prefisso di stringa etichetterebbe come
    # bundle anche "/opt/binaries/ffmpeg", che non ci vive affatto.
    override = os.environ.get(c.env_override) if c.env_override else None
    bundled = os.environ.get(BIN_DIR_ENV)
    if override and resolved == Path(override):
        source = "override"
    elif bundled and resolved.parent == Path(bundled):
        source = "bundle"
    elif c.kind == "venv" and resolved.parent == Path(sys.executable).parent:
        source = "venv"
    else:
        source = "path"
    return {"present": True, "version": _run_version([path, c.version_flag]),
            "source": source}


# Il nome del modulo arriva come argomento, non interpolato nel sorgente:
# viene dal registry, ma il codice eseguito resta una costante.
_VERSION_SNIPPET = (
    "import importlib, sys\n"
    "m = importlib.import_module(sys.argv[1])\n"
    "v = getattr(m, '__version__', None)\n"
    "if v is None:\n"
    "    v = getattr(getattr(m, 'version', None), '__version__', None)\n"
    "print(v or 'installato')\n"
)


def _import_version(module: str) -> str | None:
    """Versione del modulo, o None se non importabile. L'import gira in un
    subprocess: Essentia è pesante e ha già il suo worker separato, non va
    caricata nel processo che serve le richieste."""
    return _run_version([sys.executable, "-c", _VERSION_SNIPPET, module])


def _probe_python_module(c: Component) -> dict:
    version = _import_version(c.python_module or "")
    return {"present": version is not None, "version": version,
            "source": "venv" if version else None}


def _probe_slskd() -> dict:
    """Il demone non è un binario da cercare nel PATH: o risponde al suo URL
    o non c'è. L'URL vuoto significa 'feature disattiva', non 'errore'."""
    url = runtime_settings.slskd_url()
    if not url:
        return {"present": False, "version": None, "source": None}
    import httpx
    try:
        res = httpx.get(f"{url.rstrip('/')}/health", timeout=_PROBE_TIMEOUT_S)
        return {"present": res.status_code < 500, "version": None, "source": "daemon"}
    except httpx.HTTPError:
        return {"present": False, "version": None, "source": None}


def _probe_one(c: Component) -> dict:
    if c.python_module:
        detected = _probe_python_module(c)
    elif c.kind == "daemon":
        detected = _probe_slskd()
    else:
        detected = _probe_binary(c)
    return {
        "key": c.key, "kind": c.kind, "severity": c.severity,
        "unlocks": list(c.unlocks), "auto_installable": c.auto_installable,
        "install_command": recipe_for(c), "docs": c.docs, **detected,
    }


_cache: tuple[float, list[dict]] | None = None


def probe_all(force: bool = False) -> list[dict]:
    """Stato di tutti i componenti. Cache TTL breve: la pagina del wizard
    ricarica spesso e ogni giro lancia subprocess."""
    global _cache
    now = time.monotonic()
    if not force and _cache and now - _cache[0] < _CACHE_TTL_S:
        return _cache[1]
    result = [_probe_one(c) for c in REGISTRY]
    _cache = (now, result)
    return result


def invalidate_cache() -> None:
    """Svuota la cache del probe: da chiamare dopo un evento che cambia lo
    stato dei componenti (es. un'installazione riuscita), così la prossima
    `probe_all()` ri-rileva invece di servire il risultato in cache."""
    global _cache
    _cache = None
