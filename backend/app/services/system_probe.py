"""Rilevamento dei componenti esterni di cui Cratory ha bisogno.

Un registry dichiarativo, una voce per componente: come si rileva, che cosa
sblocca, se è installabile in automatico e con quale comando. Il registry NON
contiene prosa — solo chiavi: descrizioni e istruzioni vivono nei dizionari
i18n del frontend.

Confine Tauri: `resolve_binary` guarda prima `CRATORY_BIN_DIR`, poi il PATH.
Quando i binari arriveranno impacchettati nel bundle basterà far partire il
processo con quella variabile impostata — qui non cambia nulla.
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
from app.services import binary_manifest

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
    # `sys.platform` -> argv. La chiave "*" vale per ogni piattaforma.
    recipes: dict[str, list[str]] = field(default_factory=dict)
    binary: str | None = None
    version_flag: str = "--version"
    env_override: str | None = None
    # Dove leggere se la ricetta non fa al caso proprio (o non esiste).
    docs: str = ""


REGISTRY: tuple[Component, ...] = (
    Component(
        key="ffmpeg", kind="system", severity="required",
        unlocks=("audio_hash", "shazam", "soundcloud_download"),
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
        recipes={
            "darwin": ["brew", "install", "chromaprint"],
            "linux": ["sudo", "apt", "install", "-y", "libchromaprint-tools"],
            "win32": ["winget", "install", "-e", "--id", "AcoustID.Chromaprint"],
        },
        binary="fpcalc", version_flag="-version", env_override="FPCALC",
        docs="https://acoustid.org/chromaprint",
    ),
    Component(
        key="slskd", kind="daemon", severity="optional",
        unlocks=("soulseek_download", "library_share"),
        # Nessuna ricetta: e' un demone separato, si scarica dalle sue release
        # e si configura a parte. Il link e' l'unica indicazione che possiamo
        # dare, e va data.
        docs="https://github.com/slskd/slskd/releases",
    ),
)

_BY_KEY = {c.key: c for c in REGISTRY}


def get(key: str) -> Component | None:
    return _BY_KEY.get(key)


def managed_bin_dir() -> Path:
    """La cartella dove l'app tiene (o terrà) i binari che ha scaricato lei.

    È lo stesso posto che `resolve_binary` consulta per primo: la cartella
    gestita non è un meccanismo parallelo al seam `CRATORY_BIN_DIR`, ne è il
    valore di default. Solo lettura del percorso, niente filesystem: questa
    funzione gira su praticamente ogni `resolve_binary`/probe, quindi anche
    su un semplice `GET /api/services`, e un `mkdir` qui trasformerebbe un
    controllo di disponibilità in un errore 500 su un mount read-only o senza
    permessi di scrittura — oltre a creare cartelle nel repo reale a ogni run
    dei test. Chi deve scriverci dentro chiama `ensure_bin_dir()`.
    """
    from app.core.config import BACKEND_DIR, settings
    raw = os.environ.get(BIN_DIR_ENV) or settings.bin_dir
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path


def ensure_bin_dir() -> Path:
    """Come `managed_bin_dir()`, ma crea la cartella se non esiste.

    Da chiamare solo da chi sta per scrivere binari nella cartella (l'installer,
    in un task successivo) — dopo un clone o un `git clean -fdx` la cartella
    non c'è, e serve poterci scrivere subito. Nessun chiamante in questo
    commit: è previsto, l'installer arriva più avanti.
    """
    path = managed_bin_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_binary(name: str, env_override: str | None = None) -> str | None:
    """Percorso del binario, o None. Ordine: env specifica del componente →
    CRATORY_BIN_DIR (bundle) → PATH."""
    if env_override:
        custom = os.environ.get(env_override)
        if custom and Path(custom).is_file():
            return custom
    bundled = os.environ.get(BIN_DIR_ENV) or str(managed_bin_dir())
    candidate = Path(bundled) / name
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
    path = resolve_binary(c.binary or c.key, c.env_override)
    if not path:
        return {"present": False, "version": None, "source": None,
                "shadowing": None}
    resolved = Path(path)
    # Confronto per directory/percorso esatto, non prefisso di stringa: con
    # CRATORY_BIN_DIR="/opt/bin" un prefisso di stringa etichetterebbe come
    # bundle anche "/opt/binaries/ffmpeg", che non ci vive affatto.
    override = os.environ.get(c.env_override) if c.env_override else None
    # La cartella gestita, non la env grezza: CRATORY_BIN_DIR può benissimo
    # essere assente (il caso normale) e resolve_binary aver comunque pescato
    # dalla cartella di default (settings.bin_dir) — un binario scaricato lì
    # dall'installer va etichettato "bundle" anche in quel caso, non "path"
    # come se venisse dal sistema.
    if override and resolved == Path(override):
        source = "override"
    elif resolved.parent == managed_bin_dir():
        source = "bundle"
    else:
        source = "path"
    # Se stiamo usando la nostra copia (cartella gestita) ma il sistema ne ha
    # un'altra nel PATH, la UI deve poterlo dire: altrimenti l'utente installa
    # ffmpeg con brew, non vede cambiare niente e non ha modo di capire perché.
    di_sistema = shutil.which(c.binary or c.key) if source == "bundle" else None
    return {"present": True, "version": _run_version([path, c.version_flag]),
            "source": source, "shadowing": di_sistema}


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
    if c.kind == "daemon":
        detected = _probe_slskd()
    else:
        detected = _probe_binary(c)
    installabile = binary_manifest.entry_for(c.key) is not None
    return {
        "key": c.key, "kind": c.kind, "severity": c.severity,
        "unlocks": list(c.unlocks),
        # `auto_installable` ora significa "l'app sa installarlo da sola", e
        # per un binario esterno questo dipende solo dall'avere una build per
        # questa piattaforma: niente build, niente bottone.
        "auto_installable": installabile,
        "installable": installabile,
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
