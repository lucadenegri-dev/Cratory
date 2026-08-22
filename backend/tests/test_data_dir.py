"""La cartella dei dati è distinta da quella del codice.

Senza la variabile coincidono e nessuno se ne accorge; con la variabile
divergono, che è la condizione per girare da un .app di sola lettura."""
import stat
from pathlib import Path

import pytest

from app.core import paths


def test_senza_variabile_e_la_cartella_del_codice():
    """La guardia di non-regressione: chi non usa il seam non lo vede."""
    assert paths.risolvi_data_dir(None) == paths.BACKEND_DIR
    assert paths.risolvi_data_dir("") == paths.BACKEND_DIR
    assert paths.risolvi_data_dir("   ") == paths.BACKEND_DIR


def test_percorso_assoluto_usato_com_e(tmp_path):
    assert paths.risolvi_data_dir(str(tmp_path)) == tmp_path


def test_tilde_espansa():
    """Come già fa expand_user_paths in config.py per library_root."""
    atteso = Path.home() / "Library" / "Application Support" / "Cratory"
    assert paths.risolvi_data_dir("~/Library/Application Support/Cratory") == atteso


def test_percorso_relativo_solleva():
    """Risolverlo contro la cwd metterebbe i dati dove capita: meglio non
    partire che partire scrivendo altrove."""
    with pytest.raises(RuntimeError) as errore:
        paths.risolvi_data_dir("./dati")
    assert paths.DATA_DIR_ENV in str(errore.value)
    assert "assoluto" in str(errore.value)


def test_data_dir_di_default_e_backend_dir(monkeypatch):
    """La costante di modulo, non solo la funzione."""
    monkeypatch.delenv(paths.DATA_DIR_ENV, raising=False)
    assert paths.risolvi_data_dir(None) == paths.BACKEND_DIR


def test_verifica_scrivibile_crea_la_cartella_mancante(tmp_path):
    nuova = tmp_path / "non" / "esiste" / "ancora"
    paths.verifica_scrivibile(nuova)
    assert nuova.is_dir()


def test_verifica_scrivibile_non_lascia_la_sonda(tmp_path):
    """Un file di prova dimenticato finirebbe nella cartella dati dell'utente."""
    paths.verifica_scrivibile(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_verifica_scrivibile_solleva_leggibile(tmp_path):
    """In un'app impacchettata questo messaggio è tutto ciò che l'utente vedrà:
    deve nominare la cartella e la variabile da cui cambiarla."""
    bloccata = tmp_path / "sola-lettura"
    bloccata.mkdir()
    bloccata.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(RuntimeError) as errore:
            paths.verifica_scrivibile(bloccata)
        assert str(bloccata) in str(errore.value)
        assert paths.DATA_DIR_ENV in str(errore.value)
    finally:
        bloccata.chmod(stat.S_IRWXU)
