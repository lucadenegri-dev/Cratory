"""Scarica, verifica, estrae e prova i binari esterni dell'app.

Ordine non negoziabile: si scarica in streaming calcolando l'hash mentre il
file scorre, si confronta con quello pinnato nel manifesto, si estrae in una
directory temporanea e solo alla fine — quando il binario ha dimostrato di
partire — si sposta nella cartella gestita. Un'installazione interrotta non
lascia mezzo binario in giro.

Lo spostamento finale (`_installa_singolo`/`_installa_bundle`) rispetta lo
stesso principio a un livello più fine: prima si copia nella cartella
gestita, in una posizione affiancata a quella definitiva, poi si scambia con
una rename. La parte che attraversa i filesystem — spesso da un mount
temporaneo di sistema alla cartella del progetto — è quella con probabilità
di guasto reali, e non tocca mai un'installazione già funzionante; lo scambio
vero e proprio è solo rename sullo stesso filesystem, l'operazione con meno
probabilità di fallire di tutta la procedura. Un'installazione precedente
sopravvive quindi a qualunque guasto in quella successiva.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import stat
import subprocess
import tarfile
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Callable

import httpx

from app.services import binary_manifest, system_probe
from app.services.binary_manifest import Download
from app.services.job_spawn import spawn

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
            try:
                if d.layout == "bundle":
                    # `filter="data"` rifiuta link, device e percorsi
                    # assoluti; la validazione qui sopra copre comunque il
                    # caso zip, che un filtro equivalente non ce l'ha.
                    t.extractall(dest_dir, filter="data")
                else:
                    t.extract(interno, dest_dir, filter="data")
            except tarfile.FilterError as exc:
                # Il filtro rifiuta con le proprie classi, non sottoclassi
                # di InstallError: le si traduce qui perché il contratto di
                # extract() è "contenuto non sicuro -> UnsafeArchive", non
                # "eccezione qualunque di tarfile". Un tarfile.TarError che
                # non sia un rifiuto del filtro (archivio corrotto, lettura
                # fallita) resta quello che è: non è la stessa cosa.
                raise UnsafeArchive(str(exc)) from exc

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


MAX_LOG_LINES = 500
_PROVA_TIMEOUT_S = 20.0


class UnknownComponent(InstallError):
    pass


class NoBuildForPlatform(InstallError):
    """Non abbiamo una build per questa piattaforma. Non è un errore da
    nascondere: la UI mostra il comando manuale."""


class DoesNotRun(InstallError):
    """Installato ma non eseguibile: firma o architettura."""


class AlreadyRunning(InstallError):
    pass


def _prova_esecuzione(percorso: Path, version_flag: str) -> str:
    """Esegue il binario appena installato. È il vero criterio di riuscita:
    download, hash ed estrazione possono essere andati e il file può ancora
    non partire.

    Il flag non è lo stesso per tutti: fpcalc e ffmpeg accettano `-version`,
    slskd solo `-v`/`--version`. Un flag sconosciuto non fa fallire il
    processo per un motivo comodo da distinguere: a seconda del binario esce
    con errore (bene, lo intercettiamo) oppure — è il caso di slskd, che è un
    demone — ignora l'argomento e parte per davvero, restando in vita fino al
    timeout sotto. Da qui l'obbligo di passare il flag giusto per componente,
    non uno hardcoded.
    """
    try:
        proc = subprocess.run([str(percorso), version_flag], capture_output=True,
                              text=True, timeout=_PROVA_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DoesNotRun(str(exc)) from exc
    if proc.returncode != 0:
        raise DoesNotRun((proc.stderr or proc.stdout or "").strip()[:200]
                         or f"uscito con {proc.returncode}")
    return (proc.stdout or proc.stderr or "").strip().splitlines()[0][:120]


def installed_path(key: str) -> Path | None:
    """Dove sta l'eseguibile di questo componente nella cartella gestita, se
    c'è. Conosce il layout: i bundle stanno in una sottocartella loro."""
    d = binary_manifest.entry_for(key)
    if d is None:
        return None
    base = system_probe.managed_bin_dir()
    percorso = (base / key / d.member) if d.layout == "bundle" else (base / d.member)
    return percorso if percorso.is_file() else None


def _installa_singolo(sorgente: Path, finale: Path) -> None:
    """Mette `sorgente` (un file dentro la directory temporanea di lavoro,
    quasi certamente un mount diverso da `finale`) al posto di `finale`.

    La copia che attraversa i filesystem è la parte che può interrompersi a
    metà (disco pieno, processo ucciso): la si scrive in un file affiancato a
    `finale`, mai su `finale` stesso, cosi' un guasto li' non tocca
    l'eseguibile gia' installato. Solo a copia riuscita si scambia, con una
    `replace` nella STESSA cartella — una rename, non una copia: o avviene
    per intero o non avviene, non esiste uno stato intermedio da osservare.
    """
    staging = finale.with_name(finale.name + ".new")
    staging.unlink(missing_ok=True)  # residuo di un tentativo precedente interrotto
    try:
        shutil.copy2(sorgente, staging)
        staging.replace(finale)
    finally:
        staging.unlink(missing_ok=True)


def _installa_bundle(sorgente: Path, finale: Path) -> None:
    """Come `_installa_singolo`, ma per una cartella intera (slskd, che porta
    con sé il runtime .NET): una rename non può sostituire una directory non
    vuota, quindi lo scambio finale è in due mosse anziché una, ma resta
    fatto solo di rename nella stessa cartella — mai una copia sopra
    l'installazione precedente.

    Ordine, ed è quello che conta:
    1. si copia (costoso, può fallire a metà: attraversa da temp di sistema
       a qui) in una cartella affiancata a `finale`, MAI dentro `finale`;
    2. solo se la copia è arrivata intera, la vecchia `finale` (se c'è) si
       sposta da parte e la nuova prende il suo posto — due rename, non due
       copie: economiche, e sulla stessa cartella non hanno un mount da
       attraversare, quindi non c'è la finestra "a metà" che ha cancellato
       l'installazione precedente nel bug del reviewer.
    Se il passo 1 fallisce, `finale` non è mai stata toccata. Se fallisce il
    secondo rename (nella pratica, quasi mai: sono rename sullo stesso
    filesystem), si tenta di rimettere la vecchia installazione al suo posto
    invece di lasciare la cartella gestita vuota.
    """
    staging = finale.with_name(finale.name + ".new")
    vecchio = finale.with_name(finale.name + ".old")
    # Residui di una run precedente interrotta prima di arrivare alla pulizia
    # finale: non devono restare in giro né confondere questa run.
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(vecchio, ignore_errors=True)
    try:
        shutil.copytree(sorgente, staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    try:
        if finale.exists():
            finale.rename(vecchio)
        staging.rename(finale)
    except Exception:
        if vecchio.exists() and not finale.exists():
            vecchio.rename(finale)  # rollback: la vecchia installazione torna al suo posto
        raise
    finally:
        shutil.rmtree(vecchio, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)


def install(key: str, client: httpx.Client | None = None,
            on_log: Callable[[str], None] | None = None) -> Path:
    """Scarica, verifica, estrae, prova e infine installa. Tutto avviene in
    una directory temporanea: nella cartella gestita si sposta solo alla fine."""
    if key not in binary_manifest.MANIFEST:
        raise UnknownComponent(key)
    d = binary_manifest.entry_for(key)
    if d is None:
        raise NoBuildForPlatform(f"{key}: nessuna build per {binary_manifest.platform_tag()}")

    def log_riga(msg: str) -> None:
        if on_log:
            on_log(msg)

    destinazione = system_probe.ensure_bin_dir()  # qui si scrive: va creata
    with tempfile.TemporaryDirectory(prefix="cratory-install-") as tmp:
        tmpdir = Path(tmp)
        archivio = tmpdir / "archivio"
        log_riga(f"scarico {d.url}")
        download_verified(
            d, archivio, client=client,
            on_progress=lambda fatto, totale: log_riga(
                f"scaricati {fatto // 1024} / {totale // 1024} KB"),
        )
        log_riga(f"hash verificato ({d.sha256[:12]}…)")

        lavoro = tmpdir / "estratto"
        lavoro.mkdir()
        exe = extract(archivio, d, lavoro)
        log_riga("estratto")

        exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        versione = _prova_esecuzione(exe, d.version_flag)
        log_riga(f"il binario parte: {versione}")

        finale = (destinazione / key) if d.layout == "bundle" else (destinazione / d.member)
        if d.layout == "bundle":
            _installa_bundle(exe.parent, finale)
            finale = finale / d.member
        else:
            _installa_singolo(exe, finale)
        log_riga(f"installato in {finale}")

    system_probe.invalidate_cache()
    return finale


_lock = threading.Lock()
_state: dict = {"key": None, "status": "idle", "log": [], "detail": None}


def reset() -> None:
    with _lock:
        _state.update({"key": None, "status": "idle", "log": [], "detail": None})


def status() -> dict:
    with _lock:
        return {**_state, "log": list(_state["log"])}


def _append(line: str) -> None:
    with _lock:
        _state["log"].append(line)
        if len(_state["log"]) > MAX_LOG_LINES:
            del _state["log"][0:len(_state["log"]) - MAX_LOG_LINES]


def start(key: str) -> dict:
    """Avvia l'installazione in background. Un job alla volta."""
    if key not in binary_manifest.MANIFEST:
        raise UnknownComponent(key)
    with _lock:
        if _state["status"] == "running":
            raise AlreadyRunning(_state["key"])
        _state.update({"key": key, "status": "running", "log": [], "detail": None})

    def run() -> None:
        try:
            install(key, on_log=_append)
            with _lock:
                _state.update({"status": "done", "detail": None})
        except Exception as exc:  # noqa: BLE001 - ampio di proposito
            # Qualunque eccezione non gestita qui morirebbe in questo thread
            # lasciando lo stato su "running": ogni richiesta successiva
            # riceverebbe 409 fino al riavvio del backend.
            log.warning("installazione di %s fallita: %s", key, exc)
            with _lock:
                _state.update({"status": "error", "detail": str(exc)})

    spawn(run)
    return status()
