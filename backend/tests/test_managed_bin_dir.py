"""La cartella dei binari gestiti sta coi dati, non col codice: in un bundle
`backend/` è di sola lettura e l'installer non potrebbe scriverci."""
from app.core import paths
from app.services import system_probe


def test_bin_dir_relativa_si_ancora_ai_dati(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setenv(system_probe.BIN_DIR_ENV, "bin-relativa")
    assert system_probe.managed_bin_dir() == tmp_path / "bin-relativa"


def test_bin_dir_assoluta_passa_intatta(monkeypatch, tmp_path):
    """È il caso del bundle Tauri: la variabile punta dentro l'app."""
    bundle = tmp_path / "Cratory.app" / "Contents" / "Resources" / "bin"
    monkeypatch.setenv(system_probe.BIN_DIR_ENV, str(bundle))
    assert system_probe.managed_bin_dir() == bundle


def test_non_tocca_il_filesystem(monkeypatch, tmp_path):
    """Gira su praticamente ogni resolve_binary: un mkdir qui trasformerebbe un
    GET /api/services in un 500 su un mount di sola lettura."""
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setenv(system_probe.BIN_DIR_ENV, "bin-relativa")
    system_probe.managed_bin_dir()
    assert not (tmp_path / "bin-relativa").exists()
