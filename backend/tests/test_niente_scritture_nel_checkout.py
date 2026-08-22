"""Con CRATORY_DATA_DIR impostata, sotto backend/ non compare niente di nuovo.

Non è la somma dei test precedenti: quelli verificano cinque percorsi noti,
questo verifica la proprietà. È l'unico che si accorge di un sesto punto di
scrittura aggiunto in futuro senza riancorarlo.

Subprocess e non monkeypatch: `settings` e `DATA_DIR` sono singleton costruiti
a import-time, quindi cambiare la variabile dentro il processo di pytest non
rifà i calcoli. Il subprocess prova il percorso d'avvio vero, che è poi quello
che eseguirà Tauri.
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


_ESERCITA_LE_SCRITTURE = (
    "from app.core.config import setup_logging;"
    "from app.db import ensure_schema;"
    "from app.organize.services import thumbs, cover_cache;"
    "from app.services import system_probe;"
    "setup_logging();"
    "ensure_schema();"
    "thumbs.thumb_path(1);"
    "cover_cache.thumb_path(1);"
    "system_probe.ensure_bin_dir();"
    "print('fatto')"
)


def test_niente_di_nuovo_sotto_backend(tmp_path):
    prima = _fotografia(paths.BACKEND_DIR)

    # DATABASE_URL va tolta: conftest.py la punta a un file temporaneo, e con
    # quella impostata il default ancorato a DATA_DIR non verrebbe esercitato.
    ambiente = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    ambiente["CRATORY_DATA_DIR"] = str(tmp_path)
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
    ambiente = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    ambiente["CRATORY_DATA_DIR"] = str(tmp_path)
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
