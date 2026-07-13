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


def test_organizer_url_without_scheme_gets_http_prefix():
    """ORGANIZER_URL='localhost:3010' senza schema va reso assoluto, altrimenti
    il browser tratta l'href come path relativo e il link "Apri Sortory" si rompe."""
    s = Settings(organizer_url="localhost:3010")
    assert s.organizer_url == "http://localhost:3010"


def test_organizer_url_with_scheme_unchanged():
    assert Settings(organizer_url="http://x").organizer_url == "http://x"
    assert Settings(organizer_url="https://x").organizer_url == "https://x"


def test_organizer_url_empty_stays_empty():
    assert Settings(organizer_url="").organizer_url == ""
