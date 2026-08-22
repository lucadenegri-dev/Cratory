import pytest

from app.organize.integrations import integrity
from app.organize.integrations.integrity import IntegrityResult, check_file, parse_result
from app.services import system_probe as sp


def test_parse_clean_decode_is_ok():
    r = parse_result(0, "")
    assert r.ok is True
    assert r.detail is None


def test_parse_nonzero_exit_is_corrupt():
    # exit != 0 = ffmpeg non riesce a decodificare (illeggibile/troncato)
    r = parse_result(1, "")
    assert r.ok is False


def test_parse_benign_header_missing_is_ok():
    # 'Header missing' a inizio MP3: intoppo transitorio, il file suona -> ok
    err = ("[mp3float @ 0x0] Header missing\n"
           "[aist#0:0/mp3 @ 0x0] Error submitting packet to decoder: "
           "Invalid data found when processing input")
    r = parse_result(0, err)
    assert r.ok is True
    assert r.detail is None


def test_parse_cover_art_error_is_ok():
    # errore sullo stream copertina (immagine), non sull'audio -> ok
    r = parse_result(0, "[png @ 0x0] Invalid PNG signature 0xFFD8FFE000104A46.")
    assert r.ok is True


def test_parse_real_frame_corruption_is_corrupt():
    err = ("[flac @ 0x0] invalid residual\n"
           "[flac @ 0x0] decode_frame() failed")
    r = parse_result(0, err)
    assert r.ok is False
    assert "invalid residual" in r.detail


def test_parse_flac_sync_error_is_corrupt():
    r = parse_result(0, "[flac @ 0x0] invalid sync code")
    assert r.ok is False


def test_check_file_uses_injected_runner():
    def fake_runner(path, timeout):
        return (0, "")  # (returncode, stderr)
    r = check_file("/whatever.flac", runner=fake_runner)
    assert r == IntegrityResult(ok=True, detail=None)


def test_check_file_timeout_is_corrupt():
    def fake_runner(path, timeout):
        raise TimeoutError()
    r = check_file("/whatever.flac", runner=fake_runner)
    assert r.ok is False
    assert r.detail == "timeout"


# --- Seam Tauri: _subprocess_runner (l'esecutore reale, non iniettato) deve -
# --- risolvere ffmpeg con resolve_binary, non invocarlo nudo ----------------
#
# ffmpeg_available() (sopra, testato in test_system_probe.py) usa gia' il
# seam per dire se il controllo integrita' e' disponibile: se l'esecutore
# vero invoca "ffmpeg" nudo invece del percorso risolto, il job si annuncia
# disponibile (CRATORY_BIN_DIR) e fallisce comunque all'uso (PATH minimo di
# un'app lanciata dal Finder).


def test_subprocess_runner_usa_il_seam_per_risolvere_ffmpeg(tmp_path, monkeypatch):
    fake = tmp_path / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)

    catturato = {}

    class _Esito:
        returncode = 0
        stderr = ""

    def _run_finto(cmd, **kwargs):
        catturato["cmd"] = cmd
        return _Esito()

    monkeypatch.setattr(integrity.subprocess, "run", _run_finto)

    rc, stderr = integrity._subprocess_runner("/whatever.flac", 10)

    assert catturato["cmd"][0] == str(fake)
    assert (rc, stderr) == (0, "")


def test_subprocess_runner_solleva_se_ffmpeg_non_risolvibile(tmp_path, monkeypatch):
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))  # vuota: nessun ffmpeg dentro
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)

    def _esplodi(cmd, **kwargs):
        raise AssertionError("non doveva invocare subprocess senza un binario risolto")

    monkeypatch.setattr(integrity.subprocess, "run", _esplodi)

    with pytest.raises(FileNotFoundError):
        integrity._subprocess_runner("/whatever.flac", 10)
