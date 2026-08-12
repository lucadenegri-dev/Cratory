"""E8: i path di config con `~` vanno espansi, altrimenti un LIBRARY_ROOT
'~/Music' non risolve e indicizzazione/download falliscono in silenzio."""
from pathlib import Path

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

