"""Servizio native_picker (porting da Cratory): subprocess sempre mockato."""
import subprocess

import pytest

from app.services import native_picker as np


def _proc(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr="")


def _force_available(monkeypatch):
    monkeypatch.setattr(np, "picker_available", lambda: True)


def test_available_solo_su_darwin_con_osascript(monkeypatch):
    monkeypatch.setattr(np.sys, "platform", "darwin")
    monkeypatch.setattr(np.shutil, "which", lambda _: "/usr/bin/osascript")
    assert np.picker_available() is True


def test_available_falso_senza_osascript(monkeypatch):
    monkeypatch.setattr(np.sys, "platform", "darwin")
    monkeypatch.setattr(np.shutil, "which", lambda _: None)
    assert np.picker_available() is False


def test_available_falso_su_linux(monkeypatch):
    monkeypatch.setattr(np.sys, "platform", "linux")
    monkeypatch.setattr(np.shutil, "which", lambda _: "/usr/bin/osascript")
    assert np.picker_available() is False


def test_pick_folder_strippa_newline_e_slash_finale(monkeypatch):
    _force_available(monkeypatch)
    got = np.pick_path("folder", runner=lambda *a, **k: _proc(stdout="/Users/x/Music/\n"))
    assert got == "/Users/x/Music"


def test_pick_file_non_strippa_il_nome(monkeypatch):
    _force_available(monkeypatch)
    got = np.pick_path("file", runner=lambda *a, **k: _proc(stdout="/Users/x/slskd.yml\n"))
    assert got == "/Users/x/slskd.yml"


def test_pick_folder_root_resta_root(monkeypatch):
    _force_available(monkeypatch)
    got = np.pick_path("folder", runner=lambda *a, **k: _proc(stdout="/\n"))
    assert got == "/"


def test_annullo_utente_ritorna_none(monkeypatch):
    # osascript esce con codice 1 (error -128) quando l'utente annulla
    _force_available(monkeypatch)
    assert np.pick_path("folder", runner=lambda *a, **k: _proc(returncode=1)) is None


def test_timeout_ritorna_none(monkeypatch):
    _force_available(monkeypatch)

    def runner(*a, **k):
        raise subprocess.TimeoutExpired(cmd="osascript", timeout=np.SUBPROCESS_TIMEOUT_SECONDS)

    assert np.pick_path("folder", runner=runner) is None


def test_non_disponibile_solleva(monkeypatch):
    monkeypatch.setattr(np, "picker_available", lambda: False)
    with pytest.raises(np.PickerUnavailableError):
        np.pick_path("folder")


def test_lock_occupato_solleva_busy(monkeypatch):
    _force_available(monkeypatch)
    assert np._lock.acquire(blocking=False)
    try:
        with pytest.raises(np.PickerBusyError):
            np.pick_path("folder", runner=lambda *a, **k: _proc(stdout="/x\n"))
    finally:
        np._lock.release()


def test_lock_rilasciato_dopo_il_pick(monkeypatch):
    _force_available(monkeypatch)
    np.pick_path("folder", runner=lambda *a, **k: _proc(stdout="/x\n"))
    assert np._lock.acquire(blocking=False)  # se il lock fosse rimasto preso, fallirebbe
    np._lock.release()


def test_runner_riceve_subprocess_timeout_e_osascript(monkeypatch):
    _force_available(monkeypatch)
    seen: dict = {}

    def runner(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["timeout"] = kwargs.get("timeout")
        return _proc(stdout="/x\n")

    np.pick_path("folder", runner=runner)
    assert seen["cmd"][0] == "osascript"
    assert seen["timeout"] == np.SUBPROCESS_TIMEOUT_SECONDS


def test_build_script_folder_vs_file():
    assert "choose folder" in np.build_script("folder", None, None)
    assert "choose file" in np.build_script("file", None, None)


def test_build_script_contiene_timeout_esplicito_a_300s():
    for kind in ("folder", "file"):
        script = np.build_script(kind, None, None)
        assert "with timeout of 300 seconds" in script
        assert "end timeout" in script


def test_build_script_start_esistente_diventa_default_location(tmp_path):
    script = np.build_script("folder", str(tmp_path), None)
    assert f'default location (POSIX file "{tmp_path}")' in script


def test_build_script_start_inesistente_ignorato():
    script = np.build_script("folder", "/nope/does/not/exist", None)
    assert "default location" not in script


def test_build_script_prompt_con_escape_dei_doppi_apici():
    script = np.build_script("folder", None, 'Cartella "libreria"')
    assert 'with prompt "Cartella \\"libreria\\""' in script
