"""E8: i path di config con `~` vanno espansi, altrimenti un LIBRARY_ROOT
'~/Music' non risolve e indicizzazione/download falliscono in silenzio."""
from pathlib import Path

from app.core import paths
from app.core.config import Settings


def test_tilde_paths_are_expanded():
    home = str(Path.home())
    s = Settings(
        library_root="~/Music/Cratory",
        archive_root="~/Archivio",
        slskd_download_dir="~/Downloads",
    )
    assert s.library_root == f"{home}/Music/Cratory"
    assert s.archive_root == f"{home}/Archivio"
    assert s.slskd_download_dir == f"{home}/Downloads"


def test_empty_path_stays_empty():
    """Vuoto = feature disattiva: non deve diventare '.' o la home."""
    s = Settings(library_root="", archive_root="", slskd_download_dir="")
    assert s.library_root == ""
    assert s.archive_root == ""
    assert s.slskd_download_dir == ""


def test_absolute_path_unchanged():
    s = Settings(library_root="/mnt/music", slskd_download_dir="/var/dl")
    assert s.library_root == "/mnt/music"
    assert s.slskd_download_dir == "/var/dl"


def test_cache_relative_si_ancorano_a_data_dir(monkeypatch, tmp_path):
    """I default testuali non cambiano: cambia la radice contro cui si
    risolvono. È così che il bundle li sposta senza toccare le impostazioni."""
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    s = Settings(cover_cache_dir="./data/cover_cache",
                 thumb_cache_dir="./data/thumb_cache",
                 bin_dir="./data/bin")
    assert s.cover_cache_dir == (tmp_path / "data/cover_cache").resolve().as_posix()
    assert s.thumb_cache_dir == (tmp_path / "data/thumb_cache").resolve().as_posix()
    assert s.bin_dir == (tmp_path / "data/bin").resolve().as_posix()


def test_database_relativo_si_ancora_a_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    s = Settings(database_url="sqlite:///data/djassistant.db")
    atteso = (tmp_path / "data/djassistant.db").resolve().as_posix()
    assert s.database_url == f"sqlite:///{atteso}"


def test_percorso_assoluto_dell_utente_non_viene_riancorato(monkeypatch, tmp_path):
    """Chi ha messo un percorso assoluto nel proprio .env non deve vederselo
    spostare sotto la cartella dei dati: i validator riancorano solo i relativi.

    Il confronto passa da `.resolve()` perche' e' quello che il validator fa,
    su relativi e assoluti indifferentemente: su macOS /var e' un symlink a
    /private/var, e un'uguaglianza col letterale fallirebbe per la
    normalizzazione dei symlink invece che per il riancoraggio, cioe' per il
    motivo sbagliato."""
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    s = Settings(bin_dir="/opt/cratory/bin", cover_cache_dir="/var/cover")
    assert s.bin_dir == Path("/opt/cratory/bin").resolve().as_posix()
    assert s.cover_cache_dir == Path("/var/cover").resolve().as_posix()
    # Il punto del test: nessuno dei due e' finito sotto DATA_DIR.
    assert not s.bin_dir.startswith(str(tmp_path))
    assert not s.cover_cache_dir.startswith(str(tmp_path))


def test_backend_dir_resta_importabile_da_config():
    """core/version.py e services/system_probe.py lo prendono da qui."""
    from app.core.config import BACKEND_DIR
    assert BACKEND_DIR == paths.BACKEND_DIR

