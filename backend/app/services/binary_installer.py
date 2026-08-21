"""Scarica, verifica, estrae e prova i binari esterni dell'app.

Ordine non negoziabile: si scarica in streaming calcolando l'hash mentre il
file scorre, si confronta con quello pinnato nel manifesto, si estrae in una
directory temporanea e solo alla fine — quando il binario ha dimostrato di
partire — si sposta nella cartella gestita. Un'installazione interrotta non
lascia mezzo binario in giro.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable

import httpx

from app.services.binary_manifest import Download

log = logging.getLogger(__name__)

_CHUNK = 1024 * 256
_TIMEOUT_S = 120.0


class InstallError(Exception):
    pass


class DownloadFailed(InstallError):
    pass


class ChecksumMismatch(InstallError):
    """Il file scaricato non è quello atteso. Non è un intoppo di rete: o il
    pin è sbagliato, o quello che è arrivato non è ciò che abbiamo pinnato."""


def download_verified(
    d: Download,
    dest: Path,
    on_progress: Callable[[int, int], None] | None = None,
    client: httpx.Client | None = None,
) -> None:
    """Scarica `d.url` in `dest` verificando lo SHA256. In caso di errore
    `dest` non esiste: si scrive su un file affiancato e lo si rinomina solo
    a verifica superata."""
    owned = client is None
    client = client or httpx.Client(follow_redirects=True)
    parziale = dest.with_name(dest.name + ".parziale")
    digest = hashlib.sha256()
    scaricati = 0
    try:
        with client.stream("GET", d.url, timeout=_TIMEOUT_S,
                           follow_redirects=True) as res:
            if res.status_code != 200:
                raise DownloadFailed(f"HTTP {res.status_code} da {d.url}")
            totale = int(res.headers.get("content-length") or 0)
            with parziale.open("wb") as fh:
                for blocco in res.iter_bytes(_CHUNK):
                    fh.write(blocco)
                    digest.update(blocco)
                    scaricati += len(blocco)
                    if on_progress:
                        on_progress(scaricati, totale or scaricati)
    except httpx.HTTPError as exc:
        parziale.unlink(missing_ok=True)
        raise DownloadFailed(str(exc)) from exc
    except OSError as exc:
        parziale.unlink(missing_ok=True)
        raise DownloadFailed(str(exc)) from exc
    finally:
        if owned:
            client.close()

    ottenuto = digest.hexdigest()
    if ottenuto != d.sha256:
        parziale.unlink(missing_ok=True)
        raise ChecksumMismatch(
            f"atteso {d.sha256}, ottenuto {ottenuto}")
    parziale.replace(dest)
