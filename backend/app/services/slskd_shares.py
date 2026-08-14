"""Flag "Condividi libreria": scrive `shares.directories` nel config di slskd.

slskd non consente di cambiare le share via API a runtime (solo `listenPort`/
`listenIpAddress`, ed effimeri): l'unica via persistente è lo YAML. Cratory lo
edita in round-trip (preserva commenti/ordine/permessi del file con credenziali),
con backup, e poi forza un rescan sul demone. Vedi
`docs/archive/superpowers/specs/2026-07-23-settings-editor-and-library-sharing-design.md`.
"""
from __future__ import annotations

import io
import logging
import os
import stat
from pathlib import Path

from ruamel.yaml import YAML

from app.core import runtime_settings

logger = logging.getLogger(__name__)


class ShareError(Exception):
    """Precondizione mancante per (dis)attivare la condivisione della libreria."""


def _yaml() -> YAML:
    yaml = YAML()  # round-trip di default: preserva commenti e formato
    yaml.preserve_quotes = True
    return yaml


def edit_shares_yaml(config_path: Path | str, library: str, *, enabled: bool) -> bool:
    """Aggiunge (`enabled`) o rimuove `library` da `shares.directories` in
    `config_path`. Round-trip non distruttivo, con backup `.bak`, scrittura
    atomica e permessi preservati. Idempotente. Ritorna True se dopo l'edit la
    libreria è tra le share. Non tocca il demone (il rescan è di `set_library_share`).
    """
    config_path = Path(config_path)
    yaml = _yaml()
    original_text = config_path.read_text()
    data = yaml.load(original_text) or {}

    shares = data.get("shares")
    if shares is None:
        shares = {}
        data["shares"] = shares
    directories = shares.get("directories")
    if directories is None:
        directories = []
        shares["directories"] = directories

    present = library in directories
    if enabled and not present:
        directories.append(library)
        present = True
    elif not enabled and present:
        while library in directories:
            directories.remove(library)
        present = False

    # Backup dell'originale prima di sovrascrivere (rollback banale).
    backup = config_path.with_suffix(config_path.suffix + ".bak")
    backup.write_text(original_text)

    # Scrittura atomica preservando i permessi (il file ha le credenziali: 600).
    mode = stat.S_IMODE(os.stat(config_path).st_mode)
    buf = io.StringIO()
    yaml.dump(data, buf)
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.write_text(buf.getvalue())
    os.chmod(tmp, mode)
    os.replace(tmp, config_path)
    return present


def _rescan_best_effort() -> bool:
    """Forza il rescan sul demone se slskd è configurato. Best-effort: demone giù
    o errore → False, senza propagare (lo YAML è comunque scritto e persiste)."""
    if not runtime_settings.slskd_url():
        return False
    try:
        from app.integrations.slskd import get_slskd_client
        client = get_slskd_client()
        try:
            client.rescan_shares()
            return True
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001 — best-effort, qualsiasi errore è soft
        logger.warning("Rescan share slskd fallito (share scritta comunque): %s", exc)
        return False


def set_library_share(enabled: bool) -> dict:
    """Applica il flag "Condividi libreria": edita il config di slskd con
    `library_root` e forza il rescan. Solleva `ShareError` sulle precondizioni
    (config assente/non scrivibile, oppure attivazione senza `library_root`)."""
    config_path = Path(runtime_settings.slskd_config_path())
    library = runtime_settings.library_root()
    if not config_path.is_file():
        raise ShareError(f"Config slskd non trovato: {config_path}")
    if not os.access(config_path, os.W_OK):
        raise ShareError(f"Config slskd non scrivibile: {config_path}")
    if enabled and not library:
        raise ShareError("library_root non impostato: niente da condividere.")

    present = edit_shares_yaml(config_path, library, enabled=enabled)
    rescan = _rescan_best_effort()
    return {"applied_to_yaml": True, "rescan": rescan, "share_present": present}
