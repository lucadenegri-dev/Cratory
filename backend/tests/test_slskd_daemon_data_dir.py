"""I quattro ancoraggi di `slskd_daemon` (config di fallback quando
`slskd_config_path` è vuota, cartella download di default, pid file, log
file) sono dati di Cratory, non dell'utente: devono seguire `paths.DATA_DIR`,
non restare fissi sotto `BACKEND_DIR` — altrimenti un bundle di sola lettura
non potrebbe scriverli. `slskd_config_path()` stessa resta fuori: è la config
di un altro programma, deliberatamente fuori da questo seam.

File separato da `test_slskd_daemon.py` apposta: quel modulo ha una fixture
autouse che monkeypatcha proprio `pid_file`/`log_file` per isolare gli altri
test dal vero `data/`, il che nasconderebbe la regressione che questi test
devono invece far vedere. Stesso stile di `test_managed_bin_dir.py`:
`paths.DATA_DIR` monkeypatchata come attributo di modulo, mai importata per
nome — un nome importato si legherebbe una volta sola all'import."""
from app.core import paths
from app.services import slskd_daemon as sd


def test_default_config_path_segue_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sd.runtime_settings, "slskd_config_path", lambda: "")
    assert sd.default_config_path() == tmp_path / "data" / "slskd.yml"


def test_cartella_download_default_segue_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    assert sd._cartella_download_default() == tmp_path / "data" / "slskd-downloads"


def test_pid_file_segue_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    assert sd.pid_file() == tmp_path / "data" / "slskd.pid"


def test_log_file_segue_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    assert sd.log_file() == tmp_path / "data" / "slskd.log"
