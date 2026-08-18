"""Rilevamento dei componenti esterni: è la base del passo 1 del wizard."""
import os
import stat
import sys

from app.services import system_probe as sp


def test_binario_assente(monkeypatch):
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.resolve_binary("ffmpeg") is None


def test_binario_dal_path(monkeypatch):
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/usr/bin/" + name)
    assert sp.resolve_binary("ffmpeg") == "/usr/bin/ffmpeg"


def test_bin_dir_vince_sul_path(tmp_path, monkeypatch):
    """È il gancio Tauri: coi binari nel bundle, CRATORY_BIN_DIR deve avere la
    precedenza sul PATH di sistema."""
    fake = tmp_path / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/usr/bin/" + name)
    assert sp.resolve_binary("ffmpeg") == str(fake)


def test_env_override_specifico(tmp_path, monkeypatch):
    """fpcalc ha già una sua env FPCALC letta da organize: il probe la rispetta."""
    fake = tmp_path / "fpcalc-custom"
    fake.write_text("")
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setenv("FPCALC", str(fake))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.resolve_binary("fpcalc", env_override="FPCALC") == str(fake)


def test_ricetta_per_piattaforma(monkeypatch):
    ffmpeg = sp.get("ffmpeg")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    assert sp.recipe_for(ffmpeg) == ["brew", "install", "ffmpeg"]


def test_ricetta_jolly_vale_ovunque(monkeypatch):
    ytdlp = sp.get("yt-dlp")
    monkeypatch.setattr(sp.sys, "platform", "sunos5")
    assert sp.recipe_for(ytdlp) == [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"]


def test_ricetta_assente_ritorna_none(monkeypatch):
    slskd = sp.get("slskd")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    assert sp.recipe_for(slskd) is None


def test_probe_all_ha_una_voce_per_componente(monkeypatch):
    # `_run_version` va neutralizzato insieme a `which`: Essentia si rileva con
    # un import in subprocess, e su una macchina che ce l'ha davvero il test
    # passerebbe o fallirebbe a seconda dell'ambiente.
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp, "_run_version", lambda argv: None)
    result = sp.probe_all(force=True)
    assert [c["key"] for c in result] == [c.key for c in sp.REGISTRY]
    assert all(c["present"] is False for c in result if c["kind"] != "daemon")


def test_la_cache_evita_di_riesaminare_a_ogni_render(monkeypatch):
    chiamate = {"n": 0}

    def conta(name):
        chiamate["n"] += 1
        return None

    monkeypatch.setattr(sp.shutil, "which", conta)
    monkeypatch.setattr(sp, "_run_version", lambda argv: None)  # niente subprocess veri
    sp.probe_all(force=True)
    prime = chiamate["n"]
    sp.probe_all()
    assert chiamate["n"] == prime, "la seconda chiamata doveva usare la cache"
    sp.probe_all(force=True)
    assert chiamate["n"] > prime


def test_essentia_ha_il_pin_e_il_flag_only_binary():
    """Senza --only-binary pip compila da sorgente dove manca la wheel cp311:
    il wizard resterebbe appeso venti minuti su un log illeggibile."""
    recipe = sp.recipe_for(sp.get("essentia"))
    assert "--only-binary=:all:" in recipe
    assert "essentia==2.1b6.dev1389" in recipe
