"""Rilevamento dei componenti esterni: è la base del passo 1 del wizard."""
import stat
import sys

import pytest

from app.core import config
from app.services import system_probe as sp


@pytest.fixture(autouse=True)
def _no_slskd_network_call(monkeypatch):
    """Forza slskd_url() a ritornare stringa vuota, disattivando la feature.
    Evita che test_probe_all_ha_una_voce_per_componente e
    test_la_cache_evita_di_riesaminare_a_ogni_render facciano chiamate di rete
    incontrollate a un demone slskd."""
    monkeypatch.setattr(config.settings, "slskd_url", "")
    # Pulisce la cache globale prima di ogni test per evitare eredità di risultati
    # da run precedenti.
    sp._cache = None
    yield
    sp._cache = None


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


def test_binario_venv_trovato_nella_cartella_dell_interprete(tmp_path, monkeypatch):
    """yt-dlp vive nel venv: se il backend parte senza `source .venv/bin/activate`
    il PATH non contiene `<venv>/bin`, ma il binario va trovato lo stesso guardando
    la cartella di sys.executable — altrimenti il wizard lo segnala come assente
    pur essendo installato (bug osservato in produzione)."""
    fake_venv_bin = tmp_path / "venv-bin"
    fake_venv_bin.mkdir()
    fake = fake_venv_bin / "yt-dlp"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(sp.sys, "executable", str(fake_venv_bin / "python"))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.resolve_binary("yt-dlp", venv=True) == str(fake)


def test_binario_system_non_guarda_la_cartella_dell_interprete(tmp_path, monkeypatch):
    """ffmpeg e fpcalc sono tool di sistema (kind="system"): anche se per caso
    esistesse un file con lo stesso nome nella cartella dell'interprete, non va
    considerato — solo PATH (o CRATORY_BIN_DIR) sono legittimi per loro."""
    fake_venv_bin = tmp_path / "venv-bin"
    fake_venv_bin.mkdir()
    fake = fake_venv_bin / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(sp.sys, "executable", str(fake_venv_bin / "python"))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.resolve_binary("ffmpeg", venv=False) is None


def test_env_override_vince_sulla_cartella_dell_interprete(tmp_path, monkeypatch):
    """La precedenza esistente non va toccata: un override esplicito del
    componente resta più forte anche della cartella dell'interprete."""
    fake_venv_bin = tmp_path / "venv-bin"
    fake_venv_bin.mkdir()
    (fake_venv_bin / "yt-dlp").write_text("")
    custom = tmp_path / "yt-dlp-custom"
    custom.write_text("")
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setenv("YTDLP_BIN", str(custom))
    monkeypatch.setattr(sp.sys, "executable", str(fake_venv_bin / "python"))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.resolve_binary("yt-dlp", env_override="YTDLP_BIN", venv=True) == str(custom)


def test_bin_dir_vince_sulla_cartella_dell_interprete(tmp_path, monkeypatch):
    """La precedenza esistente non va toccata: CRATORY_BIN_DIR (bundle Tauri)
    resta più forte della cartella dell'interprete."""
    fake_venv_bin = tmp_path / "venv-bin"
    fake_venv_bin.mkdir()
    (fake_venv_bin / "yt-dlp").write_text("")
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    bundled = bundle_dir / "yt-dlp"
    bundled.write_text("")
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(bundle_dir))
    monkeypatch.setattr(sp.sys, "executable", str(fake_venv_bin / "python"))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.resolve_binary("yt-dlp", venv=True) == str(bundled)


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


def test_probe_all_ha_una_voce_per_componente(monkeypatch, tmp_path):
    # `_run_version` va neutralizzato insieme a `which`: Essentia si rileva con
    # un import in subprocess, e su una macchina che ce l'ha davvero il test
    # passerebbe o fallirebbe a seconda dell'ambiente.
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp, "_run_version", lambda argv: None)
    # yt-dlp (kind="venv") ora viene cercato anche nella cartella
    # dell'interprete: su questa macchina di sviluppo il venv reale ce l'ha
    # davvero, quindi va puntato altrove per mantenere il test indipendente
    # dall'ambiente, come tutto il resto della funzione già fa per which/_run_version.
    monkeypatch.setattr(sp.sys, "executable", str(tmp_path / "python"))
    result = sp.probe_all(force=True)
    assert [c["key"] for c in result] == [c.key for c in sp.REGISTRY]
    # slskd_url() è forzato empty dalla fixture, quindi non fa rete e ritorna
    # "non present".
    assert all(c["present"] is False for c in result)


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
