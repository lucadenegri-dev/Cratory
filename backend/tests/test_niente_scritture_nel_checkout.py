"""Con CRATORY_DATA_DIR impostata, sotto backend/ non compare niente di nuovo —
per i percorsi di scrittura che `_ESERCITA_LE_SCRITTURE` esercita davvero.

Non è la somma dei test precedenti: quelli verificano che ciascun percorso
noto risolva sotto DATA_DIR uno per uno; questo fotografa l'intero albero di
BACKEND_DIR prima e dopo, quindi si accorge anche di una riscrittura silenziosa
di un file già esistente, non solo di un nome nuovo comparso dal nulla.

Ma resta una guardia di regressione sui percorsi che `_ESERCITA_LE_SCRITTURE`
mette in moto esplicitamente — NON un rilevatore automatico di un punto di
scrittura non ancora enumerato lì dentro. Un ancoraggio dimenticato in quello
script resta invisibile a questo test, che resta verde: è successo per
davvero con i quattro percorsi propri del demone slskd (config di fallback,
cartella download di default, pid file, log file), rimasti ancorati a
BACKEND_DIR per l'intera durata di questo lavoro senza che questo test se ne
accorgesse, perché nessuno di quei quattro compariva in
`_ESERCITA_LE_SCRITTURE`. Chi aggiunge un nuovo punto di scrittura DEVE
aggiungerlo anche lì, o questo test non lo vedrà mai.

Subprocess e non monkeypatch: `settings` e `DATA_DIR` sono singleton costruiti
a import-time, quindi cambiare la variabile dentro il processo di pytest non
rifà i calcoli. Il subprocess prova il percorso d'avvio vero, che è poi quello
che eseguirà Tauri.

Attenzione se gira `uvicorn --reload` sulla porta 8000 (il flusso di sviluppo
documentato) mentre questo test è in esecuzione: la fotografia osserva
*l'intero* checkout, compresi `logs/djassistant.log` e `data/djassistant.db`,
che un server di sviluppo vero scrive per conto suo in parallelo. Un rosso che
nomina un file che il subprocess di questo test non ha mai toccato non è una
regressione: è quel server concorrente. Fermarlo e rilanciare, non inseguire
il fantasma.
"""
import os
import subprocess
import sys
from pathlib import Path

from app.core import paths

# `.venv` escluso per velocità (decine di migliaia di file nel checkout
# principale); `__pycache__` e `.pyc` perché sarebbe il test stesso a sporcare
# l'albero che sta osservando, e diventerebbe intermittente.
_IGNORATI = {"__pycache__", ".venv"}


def _fotografia(radice: Path) -> set[tuple[str, int, int]]:
    """Percorso, dimensione e mtime — non il solo percorso.

    Un confronto fra soli nomi e' cieco sul caso piu' probabile. I cinque
    ancoraggi riusano nomi fissi (`djassistant.log`, `djassistant.db`), quindi
    su qualunque macchina che abbia gia' avviato l'app in sviluppo quei file
    esistono gia': una regressione che ci riscrive dentro non fa comparire
    nessun nome nuovo, e un confronto fra insiemi di nomi resta verde mentre la
    regressione e' viva. Con dimensione e mtime la riscrittura si vede.

    Leggere un file non ne cambia l'mtime, quindi niente falsi positivi da
    lettura. Le cartelle entrano col solo nome: il loro mtime cambia anche
    quando ci compare dentro un `__pycache__` che abbiamo gia' escluso, e
    quello si', sarebbe un falso positivo.
    """
    voci: set[tuple[str, int, int]] = set()
    for percorso in radice.rglob("*"):
        rel = percorso.relative_to(radice)
        if set(rel.parts) & _IGNORATI or percorso.suffix == ".pyc":
            continue
        if percorso.is_dir():
            voci.add((str(rel), -1, -1))
            continue
        try:
            stato = percorso.stat()
        except OSError:
            continue
        voci.add((str(rel), stato.st_size, stato.st_mtime_ns))
    return voci


_ESERCITA_LE_SCRITTURE = """\
from app.core.config import setup_logging
from app.db import ensure_schema
from app.organize.services import thumbs, cover_cache
from app.services import system_probe, slskd_daemon

setup_logging()
ensure_schema()
thumbs.thumb_path(1)
cover_cache.thumb_path(1)
system_probe.ensure_bin_dir()

# Guardia strutturale (finding A della review finale). default_config_path()
# e' l'unico percorso, qui dentro, DERIVATO da un'impostazione utente
# (slskd_config_path(), default non vuoto ~/.config/slskd/slskd.yml): oggi
# resta dentro CRATORY_DATA_DIR solo perche' _ambiente_di_prova() sotto in
# questo file azzera SLSKD_CONFIG_PATH nell'ambiente del sottoprocesso. Quel
# guardrail e' ambientale: un pydantic-settings con env_ignore_empty=True, un
# .env piazzato sotto la cartella dati, o un futuro override da DB lo
# aggirerebbero tutti senza toccare questo script. E la prima asserzione dei
# due test sotto fotografa solo BACKEND_DIR: una scrittura fuori di li' non la
# farebbe fallire, resterebbe verde mentre danneggia un file vero
# dell'utente -- e' successo per davvero, ha azzerato
# ~/.config/slskd/slskd.yml. Questo controllo non e' cautela di principio: e'
# cio' che impedisce a questo script di rifarlo. La guardia d'ambiente sopra
# resta comunque: qui e' la cintura, li' la bretella.
import os
from pathlib import Path

_DATA_DIR = Path(os.environ["CRATORY_DATA_DIR"]).resolve()


def _dentro_data_dir(percorso):
    percorso = Path(percorso).resolve()
    if percorso != _DATA_DIR and _DATA_DIR not in percorso.parents:
        raise SystemExit(
            f"RIFIUTATO: {percorso} e' fuori da CRATORY_DATA_DIR "
            f"({_DATA_DIR}); non scrivo li'."
        )
    return percorso


# I quattro ancoraggi propri del demone slskd (finding: restavano fissi sotto
# BACKEND_DIR). Toccati direttamente via le loro funzioni, non via
# write_config()/start(), per non dipendere da un binario slskd installato ne'
# da SLSKD_DOWNLOAD_DIR ereditata dall'ambiente dell'host.
_dentro_data_dir(slskd_daemon.default_config_path())
slskd_daemon.default_config_path().parent.mkdir(parents=True, exist_ok=True)
slskd_daemon.default_config_path().write_text("")
slskd_daemon._cartella_download_default().mkdir(parents=True, exist_ok=True)
slskd_daemon.pid_file().parent.mkdir(parents=True, exist_ok=True)
slskd_daemon.pid_file().write_text("esercitato")
slskd_daemon.log_file().parent.mkdir(parents=True, exist_ok=True)
slskd_daemon.log_file().touch()
print("fatto")
"""


def _ambiente_di_prova(tmp_path: Path) -> dict[str, str]:
    # DATABASE_URL va tolta: conftest.py la punta a un file temporaneo, e con
    # quella impostata il default ancorato a DATA_DIR non verrebbe esercitato.
    ambiente = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    ambiente["CRATORY_DATA_DIR"] = str(tmp_path)
    # slskd_config_path ha un default non vuoto (~/.config/slskd/slskd.yml):
    # senza azzerarlo qui, default_config_path() risolverebbe a quel percorso
    # utente invece che al fallback sotto DATA_DIR, e i due test non
    # eserciterebbero mai quell'ancoraggio — indipendentemente da cosa c'è nel
    # .env vero della macchina che esegue i test.
    ambiente["SLSKD_CONFIG_PATH"] = ""
    return ambiente


def test_niente_di_nuovo_sotto_backend(tmp_path):
    prima = _fotografia(paths.BACKEND_DIR)

    ambiente = _ambiente_di_prova(tmp_path)
    esito = subprocess.run(
        [sys.executable, "-c", _ESERCITA_LE_SCRITTURE],
        cwd=str(paths.BACKEND_DIR), env=ambiente,
        capture_output=True, text=True,
    )
    assert esito.returncode == 0, esito.stderr
    assert esito.stdout.strip().endswith("fatto")

    scritti = _fotografia(paths.BACKEND_DIR) - prima
    assert not scritti, (
        "scritti o modificati dentro il checkout: "
        f"{sorted({v[0] for v in scritti})}"
    )


def test_e_invece_tutto_e_atterrato_nella_cartella_dei_dati(tmp_path):
    """Il complemento del test sopra: senza questo, un backend che non scrive
    da nessuna parte passerebbe la prima asserzione a pieni voti."""
    ambiente = _ambiente_di_prova(tmp_path)
    esito = subprocess.run(
        [sys.executable, "-c", _ESERCITA_LE_SCRITTURE],
        cwd=str(paths.BACKEND_DIR), env=ambiente,
        capture_output=True, text=True,
    )
    assert esito.returncode == 0, esito.stderr

    assert (tmp_path / "logs" / "djassistant.log").is_file()
    assert (tmp_path / "data" / "djassistant.db").is_file()
    assert (tmp_path / "data" / "bin").is_dir()
    assert (tmp_path / "data" / "thumb_cache").is_dir()
    assert (tmp_path / "data" / "cover_cache").is_dir()
    assert (tmp_path / "data" / "slskd.yml").is_file()
    assert (tmp_path / "data" / "slskd-downloads").is_dir()
    assert (tmp_path / "data" / "slskd.pid").is_file()
    assert (tmp_path / "data" / "slskd.log").is_file()
