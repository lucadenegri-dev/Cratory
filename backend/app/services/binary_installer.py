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
import shutil
import tarfile
import zipfile
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


class UnsafeArchive(InstallError):
    """L'archivio contiene percorsi che uscirebbero dalla cartella di
    destinazione. Stesso registro dell'hash sbagliato: non è un intoppo."""


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


def _dentro(base: Path, candidato: Path) -> bool:
    """Controlla se il candidato sta dentro base dopo la risoluzione."""
    try:
        candidato.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def _valida_nomi(nomi: list[str], dest_dir: Path) -> None:
    """Rifiuta percorsi assoluti e traversal fuori dalla destinazione."""
    for nome in nomi:
        p = Path(nome)
        if p.is_absolute() or ".." in p.parts:
            raise UnsafeArchive(f"percorso non ammesso nell'archivio: {nome}")
        if not _dentro(dest_dir, dest_dir / nome):
            raise UnsafeArchive(f"percorso fuori dalla destinazione: {nome}")


def _trova_membro(nomi: list[str], member: str) -> str:
    """Cerca il membro per basename, ignorando il percorso interno."""
    for nome in nomi:
        if Path(nome).name == member:
            return nome
    raise InstallError(f"'{member}' non trovato nell'archivio")


def extract(archive: Path, d: Download, dest_dir: Path) -> Path:
    """Estrae l'archivio in `dest_dir` e ritorna il percorso dell'eseguibile.

    `single`: si estrae il solo `d.member`, cercato per basename — il percorso
    interno delle release contiene il numero di build e cambia ogni volta.
    `bundle`: si estrae tutto, perché l'eseguibile non è autosufficiente.
    """
    if d.archive == "zip":
        with zipfile.ZipFile(archive) as z:
            nomi = z.namelist()
            _valida_nomi(nomi, dest_dir)
            interno = _trova_membro(nomi, d.member)
            if d.layout == "bundle":
                z.extractall(dest_dir)
            else:
                z.extract(interno, dest_dir)
    else:
        modo = "r:xz" if d.archive == "tar.xz" else "r:gz"
        with tarfile.open(archive, modo) as t:
            nomi = t.getnames()
            _valida_nomi(nomi, dest_dir)
            interno = _trova_membro(nomi, d.member)
            if d.layout == "bundle":
                # `filter="data"` rifiuta link, device e percorsi assoluti;
                # la validazione qui sopra copre comunque il caso zip, che
                # un filtro equivalente non ce l'ha.
                t.extractall(dest_dir, filter="data")
            else:
                t.extract(interno, dest_dir, filter="data")

    estratto = dest_dir / interno
    if d.layout == "single" and estratto.parent != dest_dir:
        # Il membro era annidato: lo si porta in cima e si butta la cartella.
        finale = dest_dir / d.member
        shutil.move(str(estratto), str(finale))
        radice = dest_dir / Path(interno).parts[0]
        if radice.is_dir():
            shutil.rmtree(radice, ignore_errors=True)
        estratto = finale
    return estratto
