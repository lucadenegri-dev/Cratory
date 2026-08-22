"""Assembla il bundle `.app` di Cratory: build del frontend, runtime Python,
binari esterni, sorgente del backend, e infine `tauri build`.

Uso:
    python3 src-tauri/scripts/assembla.py

A differenza dei suoi due fratelli (`costruisci_runtime.py`,
`costruisci_binari.py`), questo script NON prende un argomento di
destinazione: la decide lui stesso, `<radice_repo>/src-tauri/target/staging/`,
perche' `tauri.conf.json` deve poter puntare a un percorso fisso in
`bundle.resources` -- non puo' ricevere un argomento a runtime.
`src-tauri/target/` e' gia' ignorato da git (vedi `src-tauri/.gitignore`),
quindi lo staging non rischia di finire in un commit.

In ordine:
    0. Preflight (`_prerequisiti_ffmpeg`, importato da `costruisci_binari.py`):
       Homebrew/ffmpeg installati, otool/install_name_tool/codesign sul PATH.
       Fatto qui, per primo, cosi' una macchina senza i prerequisiti fallisce
       in pochi secondi invece che dopo i ~5 minuti del passo 2.
    1. Build del frontend in export statico (`_costruisci_frontend`): vedi
       li' per il perche' `NEXT_PUBLIC_API_URL` va passata al comando di
       build e non all'ambiente del guscio.
    2. `costruisci_runtime.py` -> `<staging>/python/`.
    3. `costruisci_binari.py` -> `<staging>/bin/`.
    4. Firma ad-hoc di ogni Mach-O trovato sotto `<staging>/python/` e
       `<staging>/bin/` (`_firma_ad_hoc_ricorsiva`): vedi li' per il perche'
       serve anche qui, non solo dentro `costruisci_binari.py`.
    5. Copia di `backend/app` e `backend/requirements.txt` in
       `<staging>/backend/`, escludendo `tests/`, `__pycache__/`, `data/`,
       `logs/` (`_copia_backend`).
    6. `npm run tauri:build` (che fa `cd ..` e lancia `tauri build` dalla
       radice del repo -- vedi lo script `tauri:build` in
       `frontend/package.json`).

`tauri.conf.json` dichiara le quattro cartelle dello staging (piu'
`frontend/out`, gia' prodotta dal passo 1 e riferita li' direttamente, senza
una copia in piu') come risorse del bundle in `bundle.resources`: finiscono
tutte sotto `Contents/Resources/` nel `.app` finale, nel layout che
`src-tauri/src/backend.rs` si aspetta (`resource_dir()/backend`,
`resource_dir()/bin`, `resource_dir()/python`).

Idempotente quanto lo sono i suoi passi: `costruisci_runtime.py` e
`costruisci_binari.py` ricostruiscono le proprie sottocartelle da zero, e il
passo 5 fa lo stesso per `<staging>/backend/`.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

_RADICE_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = Path(__file__).resolve().parent
_STAGING = _RADICE_REPO / "src-tauri" / "target" / "staging"

# Import diretto (non subprocess) del preflight di costruisci_binari.py: lo
# stesso script gira comunque piu' avanti (passo 3, via subprocess, per
# costruire davvero i binari), ma qui serve chiamare SOLO il controllo, prima
# di spendere ~5 minuti nel runtime Python (passo 2). `_SCRIPTS_DIR` e' gia'
# `sys.path[0]` quando questo file gira come script principale, ma lo si
# inserisce comunque esplicitamente per non dipendere da quel dettaglio
# implicito se in futuro questo modulo venisse importato da altrove.
sys.path.insert(0, str(_SCRIPTS_DIR))
from costruisci_binari import _prerequisiti_ffmpeg  # noqa: E402

# Cosa NON copiare di backend/app nello staging: dati di sviluppo e
# artefatti, non parte del bundle che l'utente riceve. tests/, data/ e
# logs/ sono in realta' gia' fuori da backend/app/ (sono cartelle sorelle,
# sotto backend/ -- vedi la copia in _copia_backend, che parte proprio da
# backend/app e non da backend/), ma restano nell'elenco per difesa: se in
# futuro qualcosa le spostasse dentro app/, o ne comparisse una copia li',
# questo filtro le tiene comunque fuori. __pycache__ invece compare per
# davvero, e ripetutamente, dentro backend/app/ (in ogni sottopacchetto che
# e' stato importato almeno una volta durante lo sviluppo).
_ESCLUSIONI_BACKEND = shutil.ignore_patterns("tests", "__pycache__", "data", "logs")


def _esegui_streaming(argv: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    """Esegue un comando esterno ereditando stdout/stderr, cosi' l'utente
    vede l'avanzamento in diretta: sono tutti passi lenti (download,
    compilazione Rust) su cui un silenzio di minuti sembrerebbe un blocco.
    Solleva RuntimeError se il comando fallisce -- stesso stile leggibile
    degli altri due script."""
    esito = subprocess.run(argv, cwd=cwd, env=env)
    if esito.returncode != 0:
        raise RuntimeError(f"comando fallito: {' '.join(argv)} (codice {esito.returncode})")


def _esegui_catturando(argv: list[str]) -> str:
    """Come `_esegui_streaming`, ma cattura l'output invece di lasciarlo
    scorrere: per comandi che girano una volta per ogni file di un albero
    (la firma ad-hoc sotto), dove mostrare l'output di ognuno sarebbe rumore
    e non progresso. Stesso stile di `costruisci_binari.py`."""
    esito = subprocess.run(argv, capture_output=True, text=True)
    if esito.returncode != 0:
        raise RuntimeError(
            f"comando fallito: {' '.join(argv)} (codice {esito.returncode})\n{esito.stderr.strip()}"
        )
    return esito.stdout


def _costruisci_frontend() -> None:
    """`CRATORY_STATIC_EXPORT=1` e soprattutto `NEXT_PUBLIC_API_URL` vanno
    passate QUI, al comando di build, non all'ambiente del guscio (dove
    invece vivono le tre variabili del backend, vedi `backend.rs`): Next.js
    inlinea le `NEXT_PUBLIC_*` nei bundle JS a build time, non le rilegge a
    runtime da `process.env`. Se finissero nell'ambiente del processo
    backend -- il seam sbagliato, perche' e' un processo Python separato che
    quella variabile non la legge nemmeno -- il frontend esportato non le
    vedrebbe mai: l'app si aprirebbe su una pagina che non fa nessuna
    chiamata API, senza un solo errore che lo dica."""
    print("--- frontend (export statico) ---")
    ambiente = dict(
        os.environ,
        CRATORY_STATIC_EXPORT="1",
        NEXT_PUBLIC_API_URL="http://127.0.0.1:8000",
    )
    _esegui_streaming(["npm", "run", "build"], cwd=_RADICE_REPO / "frontend", env=ambiente)
    out_dir = _RADICE_REPO / "frontend" / "out"
    if not out_dir.is_dir():
        raise RuntimeError(f"'{out_dir}' non esiste dopo 'npm run build': l'export statico e' fallito in silenzio?")


def _rendi_scrivibile_ricorsivo(cartella: Path) -> int:
    """Aggiunge il bit di scrittura per il proprietario a ogni file regolare
    sotto `cartella`, ricorsivamente. Ritorna quanti file ha dovuto toccare.

    Necessario per `bin/ffmpeg/`: `costruisci_binari.py` copia l'eseguibile
    e le sue dylib da Homebrew con `shutil.copy2`, che preserva anche i
    permessi della sorgente -- e Homebrew installa molti file nel Cellar
    senza il bit di scrittura per il proprietario (`-r-xr-xr-x`). Copiare un
    file cosi' dentro il bundle produce una destinazione con lo stesso
    permesso ristretto: la PRIMA `tauri build` su uno staging pulito
    funziona comunque (scrive file nuovi), ma una seconda `tauri build` che
    sovrascrive lo stesso bundle gia' assemblato fallisce con "Permission
    denied" nel tentativo di aprire in scrittura una destinazione che ha
    ereditato quel permesso -- verificato di persona su questa macchina.
    Senza questo passo lo script non sarebbe idempotente per davvero: solo
    la primissima esecuzione da uno staging vuoto funzionerebbe."""
    toccati = 0
    for root, _dirs, nomi in os.walk(cartella, followlinks=False):
        for nome in nomi:
            percorso = Path(root) / nome
            if percorso.is_symlink() or not percorso.is_file():
                continue
            modo = percorso.stat().st_mode
            if not modo & stat.S_IWUSR:
                percorso.chmod(modo | stat.S_IWUSR)
                toccati += 1
    return toccati


def _e_mach_o(percorso: Path) -> bool:
    """True se `percorso` e' un binario Mach-O (eseguibile o dylib, incluso
    universale/fat): l'unico tipo di file a cui una firma di codice si
    applica. Il resto dell'albero (sorgenti .py, file dati, i .pyc che si
    rigenerano da soli) non ha firma da apporre ne' da verificare.

    I symlink si escludono a monte (vedi `_firma_ad_hoc_ricorsiva`, che non
    li passa nemmeno a questa funzione): `is_file()` li seguirebbe comunque,
    ma un symlink punta a un file reale che la stessa camminata visita gia'
    per conto suo -- firmarlo due volte (una volta per il link, una per il
    bersaglio) non aggiunge niente."""
    if not percorso.is_file():
        return False
    try:
        with open(percorso, "rb") as f:
            magic = f.read(4)
    except OSError:
        return False
    return magic in (
        b"\xcf\xfa\xed\xfe",  # Mach-O 64-bit
        b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe",  # Mach-O 32-bit
        b"\xfe\xed\xfa\xce",
        b"\xca\xfe\xba\xbe",  # fat/universal binary (magic big-endian)
        b"\xbe\xba\xfe\xca",
    )


def _firma_ad_hoc_ricorsiva(cartella: Path) -> list[Path]:
    """Firma ad-hoc (`codesign --force --sign -`) ogni Mach-O sotto
    `cartella`, ricorsivamente. Ritorna i percorsi firmati.

    Necessaria anche qui, non solo dentro `costruisci_binari.py`: quello
    script firma le sole dylib di ffmpeg che ha appena rilocato con
    `install_name_tool` (che invalida la firma di ogni file che tocca), ma
    non tocca fpcalc, ne' slskd, ne' nessuna delle centinaia di .so/.dylib
    delle wheel che `costruisci_runtime.py` installa dentro `python/`
    (numpy, essentia, ...), molte delle quali arrivano da PyPI senza firma.
    Su Apple Silicon un Mach-O senza firma non parte affatto, e `tauri
    build` non ripara la cosa da solo: la firma finale del bundle sigilla
    gli hash dei file sotto `Resources/` come dati opachi (per verificare
    che il bundle non sia stato manomesso), non inietta una firma di codice
    dentro un eseguibile annidato che non ne aveva gia' una -- per questo va
    fatto qui, PRIMA di quel passo, non dopo (vedi lo Step 6 del brief).

    `os.walk` di default non segue i symlink (`followlinks=False`): un
    symlink che punta fuori dallo staging non deve far uscire la camminata
    da li'."""
    firmati: list[Path] = []
    for root, _dirs, nomi in os.walk(cartella):
        for nome in nomi:
            percorso = Path(root) / nome
            if percorso.is_symlink():
                continue
            if _e_mach_o(percorso):
                _esegui_catturando(["codesign", "--force", "--sign", "-", str(percorso)])
                firmati.append(percorso)
    return firmati


def _copia_backend(staging: Path) -> None:
    """Copia `backend/app` e `backend/requirements.txt` in
    `<staging>/backend/`, escludendo `_ESCLUSIONI_BACKEND`.

    Ricostruita da zero ad ogni run (idempotente, come i due fratelli):
    senza, un file tolto dal sorgente resterebbe nello staging di una run
    precedente e finirebbe comunque nel bundle."""
    print("--- backend (sorgente) ---")
    backend_staging = staging / "backend"
    if backend_staging.exists():
        shutil.rmtree(backend_staging)
    backend_staging.mkdir(parents=True)

    app_sorgente = _RADICE_REPO / "backend" / "app"
    requirements_sorgente = _RADICE_REPO / "backend" / "requirements.txt"
    if not app_sorgente.is_dir():
        raise RuntimeError(f"'{app_sorgente}' non esiste")
    if not requirements_sorgente.is_file():
        raise RuntimeError(f"'{requirements_sorgente}' non esiste")

    shutil.copytree(app_sorgente, backend_staging / "app", ignore=_ESCLUSIONI_BACKEND)
    shutil.copy2(requirements_sorgente, backend_staging / "requirements.txt")


def _dimensione(cartella: Path) -> str:
    """Dimensione su disco, stessa convenzione (`du -sh`) degli altri due
    script: solo per il messaggio finale, non per nessuna decisione qui."""
    try:
        esito = subprocess.run(["du", "-sh", str(cartella)], capture_output=True, text=True, check=True)
        return esito.stdout.split()[0]
    except (OSError, subprocess.CalledProcessError, IndexError):
        totale = sum(
            (Path(root) / nome).lstat().st_size
            for root, _dirs, nomi in os.walk(cartella, followlinks=False)
            for nome in nomi
        )
        return f"{totale / (1024 * 1024):.1f}M (stima sui byte apparenti: 'du' non disponibile)"


def assembla() -> None:
    # Preflight PRIMA di tutto il resto: senza Homebrew/ffmpeg/Xcode Command
    # Line Tools su questa macchina, costruisci_binari.py (passo 3) fallira'
    # comunque -- ma solo dopo che il passo 2 (costruisci_runtime.py) ha gia'
    # speso circa 5 minuti a scaricare e installare il runtime Python. Con
    # questo controllo qui, in testa, una macchina senza i prerequisiti
    # fallisce in pochi secondi invece che dopo il runtime.
    print("--- preflight (Homebrew/ffmpeg/Xcode Command Line Tools) ---")
    _prerequisiti_ffmpeg()

    _STAGING.mkdir(parents=True, exist_ok=True)

    _costruisci_frontend()

    print("--- runtime Python ---")
    _esegui_streaming([sys.executable, str(_SCRIPTS_DIR / "costruisci_runtime.py"), str(_STAGING)])

    print("--- binari esterni ---")
    _esegui_streaming([sys.executable, str(_SCRIPTS_DIR / "costruisci_binari.py"), str(_STAGING)])

    resi_scrivibili = _rendi_scrivibile_ricorsivo(_STAGING / "bin")
    if resi_scrivibili:
        print(f"Resi scrivibili {resi_scrivibili} file sotto bin/ (Homebrew li installa in sola lettura).")

    print("--- firma ad-hoc (python/ + bin/) ---")
    firmati = _firma_ad_hoc_ricorsiva(_STAGING / "python") + _firma_ad_hoc_ricorsiva(_STAGING / "bin")
    print(f"Firmati {len(firmati)} Mach-O.")

    _copia_backend(_STAGING)

    print(f"Staging completo in {_STAGING} ({_dimensione(_STAGING)}).")

    print("--- tauri build ---")
    _esegui_streaming(["npm", "run", "tauri:build"], cwd=_RADICE_REPO / "frontend")

    app = next(iter((_RADICE_REPO / "src-tauri" / "target").glob("**/Cratory.app")), None)
    if app is None:
        raise RuntimeError(
            "'tauri build' e' uscito con successo ma nessun Cratory.app si trova sotto src-tauri/target/."
        )
    print(f"Fatto: {app} ({_dimensione(app)}).")


def main() -> None:
    try:
        assembla()
    except RuntimeError as errore:
        # I fallimenti previsti (build del frontend fallita, comando esterno
        # fallito, ...) hanno gia' un messaggio che dice cosa e' andato
        # storto: un traceback sopra non aggiunge informazione, la nasconde
        # nel rumore.
        print(f"ERRORE: {errore}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
