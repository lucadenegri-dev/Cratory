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
import stat
from pathlib import Path

from ruamel.yaml import YAML

from app.core import runtime_settings
from app.core.config import BACKEND_DIR

log = logging.getLogger(__name__)

DEFAULT_PORT = 5030


class DaemonError(Exception):
    pass


def _yaml() -> YAML:
    yaml = YAML()  # round-trip: preserva commenti e formato
    yaml.preserve_quotes = True
    return yaml


def default_config_path() -> Path:
    """Il percorso configurato, se c'è; altrimenti quello nostro sotto data/."""
    configurato = runtime_settings.slskd_config_path()
    return Path(configurato) if configurato else BACKEND_DIR / "data" / "slskd.yml"


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
