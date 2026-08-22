"""Costruisce il runtime Python rilocabile che il bundle Tauri porta con se'.

Uso:
    python3 src-tauri/scripts/costruisci_runtime.py <destinazione>

Lascia in `<destinazione>/python/` un CPython funzionante e potato, con dentro
tutte le dipendenze di `backend/requirements.txt` (compresa `essentia`, la
libreria C++ pinnata per l'analisi BPM/key). Il Task 5 (assemblaggio del
bundle) lo chiama.

Perche' un interprete vero e non PyInstaller: `essentia_engine.py` lancia
`[sys.executable, "-m", "app.integrations.essentia_worker", path]`. In un
eseguibile congelato `sys.executable` e' l'eseguibile stesso, che non accetta
`-m` — servirebbe riscrivere codice di produzione per accontentare il
packager. Con un interprete vero quella riga funziona senza toccarla.

I console script sotto `bin/` (es. `bin/uvicorn`) NON sono rilocabili: il loro
shebang porta il percorso assoluto della macchina di build. Per questo la
verifica qui sotto importa i moduli invece di lanciare gli script di `bin/`,
ed e' anche per questo che il guscio Tauri (Task 4) dovra' invocare tutto come
`python3 -m <modulo>`.

Idempotente: se `<destinazione>/python` esiste gia' viene ricostruito da
zero, non aggiornato in place.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------
# Pin del runtime: build "install_only" (nessun oggetto di debug/PGO, la piu'
# piccola che espone comunque un interprete completo) del 20260814 di
# python-build-standalone, per aarch64-apple-darwin.
#
# Stessa disciplina di backend/app/services/binary_manifest.py: l'hash e'
# FISSATO qui, non riletto al momento del download. Un digest preso al volo
# verrebbe dalla stessa fonte che una release compromessa a monte
# controllerebbe. Per aggiornare il pin:
#   gh api repos/astral-sh/python-build-standalone/releases/tags/<tag> \
#     --jq '.assets[] | select(.name | test("aarch64-apple-darwin-install_only.tar.gz$")) | "\(.name) \(.digest)"'
# poi si aggiornano insieme URL, versione nel commento e hash qui sotto.
RUNTIME_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    "20260814/cpython-3.11.16%2B20260814-aarch64-apple-darwin-install_only.tar.gz"
)
RUNTIME_SHA256 = "fcba9f3f676c83e07225e38116649f0c6eb94cb4fcc166632cf92769462b6e39"

# Cartella della stdlib dentro l'albero estratto, es. lib/python3.11/. Va di
# pari passo con RUNTIME_URL: se cambia la minor va aggiornata anche questa.
_PY_VERSION_DIR = "python3.11"

# Cosa potare dopo l'installazione. Elenco vincolato dal task: pip e
# setuptools non servono a runtime (nessuna installazione avviene nel
# bundle), pytest/_pytest/pygments sono dipendenze di sviluppo trascinate
# dentro da altri pacchetti, non da requirements.txt direttamente.
_PACCHETTI_DA_RIMUOVERE = ("pip", "setuptools", "pkg_resources", "pytest", "_pytest", "pygments")
_CARTELLE_STDLIB_DA_RIMUOVERE = ("test", "idlelib", "tkinter", "lib2to3")
_CARTELLE_TOPLEVEL_DA_RIMUOVERE = ("share", "include")

# Moduli che devono importare nel runtime finale, potatura compresa. E' la
# verifica reale: un albero che si estrae e si installa senza errori puo'
# comunque produrre un interprete che non importa essentia (wheel sbagliata,
# libreria nativa mancante, ...).
_MODULI_DA_VERIFICARE = ("essentia.standard", "fastapi", "uvicorn", "yt_dlp", "shazamio", "mutagen", "PIL", "acoustid")


def _scarica_e_verifica(cartella_tmp: Path) -> Path:
    """Scarica l'archivio del runtime in `cartella_tmp` e ne verifica lo SHA256.

    Fallisce con un errore leggibile se l'hash non corrisponde al pin: puo'
    significare un rilascio cambiato a monte o un download corrotto, in
    entrambi i casi non si procede a estrarlo.
    """
    archivio = cartella_tmp / "cpython-runtime.tar.gz"
    richiesta = urllib.request.Request(RUNTIME_URL, headers={"User-Agent": "cratory-costruisci-runtime/1.0"})
    hasher = hashlib.sha256()
    with urllib.request.urlopen(richiesta) as risposta, open(archivio, "wb") as f:
        while True:
            chunk = risposta.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest != RUNTIME_SHA256:
        raise RuntimeError(
            f"SHA256 non corrisponde per {RUNTIME_URL}\n"
            f"  atteso:   {RUNTIME_SHA256}\n"
            f"  ottenuto: {digest}\n"
            "L'archivio scaricato non e' quello pinnato (rilascio cambiato a monte "
            "o download corrotto): mi fermo, non lo estraggo."
        )
    return archivio


def _estrai(archivio: Path, destinazione: Path) -> Path:
    """Estrae l'archivio dentro `destinazione`.

    I tarball "install_only" di python-build-standalone hanno gia' `python/`
    come cartella di primo livello, quindi estrarre dentro `destinazione`
    produce direttamente `destinazione/python/` senza bisogno di rinominare.
    """
    kwargs: dict[str, str] = {}
    # Il parametro `filter` (PEP 706) non esiste sulle stdlib piu' vecchie che
    # potrebbero lanciare questo script: lo si passa solo se disponibile,
    # invece di forzare una versione minima di Python sulla macchina di build.
    if "filter" in inspect.signature(tarfile.TarFile.extractall).parameters:
        kwargs["filter"] = "data"
    with tarfile.open(archivio, "r:gz") as tf:
        tf.extractall(destinazione, **kwargs)
    python_dir = destinazione / "python"
    python_bin = python_dir / "bin" / "python3"
    if not python_bin.exists():
        raise RuntimeError(f"Estrazione fallita: {python_bin} non esiste dopo l'estrazione dell'archivio.")
    return python_dir


def _installa_requisiti(python_bin: Path, requirements: Path) -> None:
    """Installa `backend/requirements.txt` dentro il runtime appena estratto."""
    if not requirements.exists():
        raise RuntimeError(f"requirements.txt non trovato: {requirements}")
    esito = subprocess.run([str(python_bin), "-m", "pip", "install", "-r", str(requirements)])
    if esito.returncode != 0:
        raise RuntimeError(
            f"'{python_bin} -m pip install -r {requirements}' e' fallito (rc={esito.returncode}); "
            "vedi l'output di pip sopra per il pacchetto che ha rotto l'installazione."
        )


def _rimuovi(percorso: Path) -> None:
    if percorso.is_symlink() or percorso.is_file():
        percorso.unlink()
    elif percorso.is_dir():
        shutil.rmtree(percorso)


def _potare(python_dir: Path) -> None:
    """Toglie dal runtime tutto cio' che serve solo a costruirlo o a testarlo,
    non a farlo girare: circa 100 MB fra pip/setuptools, la test suite della
    stdlib, gli strumenti GUI (idle/tkinter) e i metadata dei pacchetti."""
    site_packages = python_dir / "lib" / _PY_VERSION_DIR / "site-packages"

    for nome in _PACCHETTI_DA_RIMUOVERE:
        _rimuovi(site_packages / nome)

    # *.dist-info: metadata di installazione (versione, entry points, RECORD
    # dei file). Non serve a importare i pacchetti, solo a introspezione che
    # qui non serve.
    for dist_info in site_packages.glob("*.dist-info"):
        _rimuovi(dist_info)

    lib_dir = python_dir / "lib" / _PY_VERSION_DIR
    for nome in _CARTELLE_STDLIB_DA_RIMUOVERE:
        _rimuovi(lib_dir / nome)

    for nome in _CARTELLE_TOPLEVEL_DA_RIMUOVERE:
        _rimuovi(python_dir / nome)

    # Ogni __pycache__ residuo in tutto l'albero (stdlib e site-packages): i
    # .pyc si rigenerano al primo import, non serve spedirli.
    for pycache in list(python_dir.rglob("__pycache__")):
        _rimuovi(pycache)


def _verifica_import(python_bin: Path) -> None:
    """Verifica ESEGUENDO, non ispezionando: un albero che si e' estratto e
    installato senza errori puo' comunque avere una wheel sbagliata o una
    libreria nativa mancante che si scopre solo importando davvero.

    La verifica gira DOPO la potatura (per lo stesso ordine del task), quindi
    senza precauzioni gli import di questo comando rigenererebbero da soli i
    `__pycache__` appena tolti: PYTHONDONTWRITEBYTECODE tiene la verifica di
    sola lettura sull'albero che sta controllando.
    """
    codice = "import " + ", ".join(_MODULI_DA_VERIFICARE)
    ambiente = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    esito = subprocess.run([str(python_bin), "-c", codice], capture_output=True, text=True, env=ambiente)
    if esito.returncode != 0:
        raise RuntimeError(
            "Il runtime potato non importa tutte le dipendenze richieste "
            f"({', '.join(_MODULI_DA_VERIFICARE)}).\n"
            f"Comando: {python_bin} -c \"{codice}\"\n"
            f"Stderr:\n{esito.stderr.strip()}"
        )


def _dimensione(cartella: Path) -> str:
    """Dimensione su disco di `cartella`, stessa convenzione di `du -sh`
    (blocchi da 4 KB su APFS, non la somma esatta dei byte): decine di
    migliaia di file piccoli fanno una differenza reale fra le due (~180 MB
    di byte "apparenti" contro ~195 MB su disco in questo runtime), ed e' la
    seconda quella confrontabile con quanto occupa davvero nel bundle e con
    quanto misurato dallo spike.

    Se `du` non c'e' (piattaforma inattesa) si ripiega sulla somma dei byte
    apparenti pur di non far fallire lo script per un dettaglio di reporting:
    a quel punto la verifica funzionale (import) e' gia' passata."""
    try:
        esito = subprocess.run(["du", "-sh", str(cartella)], capture_output=True, text=True, check=True)
        return esito.stdout.split()[0]
    except (OSError, subprocess.CalledProcessError, IndexError):
        totale = 0
        for root, _dirs, files in os.walk(cartella, followlinks=False):
            for nome in files:
                try:
                    totale += (Path(root) / nome).lstat().st_size
                except OSError:
                    continue
        return f"{totale / (1024 * 1024):.1f}M (stima sui byte apparenti: 'du' non disponibile)"


def costruisci(destinazione: Path) -> None:
    destinazione = destinazione.resolve()
    destinazione.mkdir(parents=True, exist_ok=True)

    python_dir = destinazione / "python"
    if python_dir.exists():
        print(f"'{python_dir}' esiste gia': lo ricostruisco da zero (idempotente).")
        shutil.rmtree(python_dir)

    radice_repo = Path(__file__).resolve().parents[2]
    requirements = radice_repo / "backend" / "requirements.txt"

    with tempfile.TemporaryDirectory(prefix="cratory-runtime-dl-") as tmp:
        tmp_path = Path(tmp)
        print(f"Scarico {RUNTIME_URL} ...")
        archivio = _scarica_e_verifica(tmp_path)
        print(f"SHA256 verificato ({RUNTIME_SHA256[:12]}...).")
        print(f"Estraggo in {destinazione} ...")
        python_dir = _estrai(archivio, destinazione)

    python_bin = python_dir / "bin" / "python3"

    print(f"Installo {requirements} ...")
    _installa_requisiti(python_bin, requirements)

    print("Poto pip/setuptools, dist-info, test suite della stdlib, idle/tkinter, __pycache__ ...")
    _potare(python_dir)

    print("Verifico importando i moduli chiave dal runtime potato ...")
    _verifica_import(python_bin)
    print("Import verificati: il runtime potato funziona.")

    dimensione = _dimensione(python_dir)
    print(f"Dimensione finale di {python_dir}: {dimensione}")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Uso: {sys.argv[0]} <destinazione>", file=sys.stderr)
        raise SystemExit(2)
    try:
        costruisci(Path(sys.argv[1]))
    except RuntimeError as errore:
        # I fallimenti previsti (hash sbagliato, import mancante, ...) hanno
        # gia' un messaggio che dice cosa e' andato storto: un traceback sopra
        # non aggiunge informazione, la nasconde nel rumore.
        print(f"ERRORE: {errore}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
