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
    incontrollate a un demone slskd.

    Ripulisce anche FPCALC e CRATORY_BIN_DIR: resolve_binary li consulta PRIMA
    del PATH, quindi uno sviluppatore con uno dei due impostati nell'ambiente
    (es. per lavorare sul bundle Tauri) farebbe fallire i test che assumono
    "niente di preinstallato" — l'indipendenza dall'host non e' negoziabile.
    """
    monkeypatch.setattr(config.settings, "slskd_url", "")
    monkeypatch.delenv("FPCALC", raising=False)
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
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


def test_bin_dir_richiede_un_file_non_una_directory(tmp_path, monkeypatch):
    """resolve_binary deve richiedere un file, non un percorso qualsiasi:
    altrimenti potrebbe disaccordarsi con fpcalc_available (os.path.isfile)
    su una CRATORY_BIN_DIR/nome che risulta essere una cartella."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "ffmpeg").mkdir()  # non un binario, solo una cartella omonima
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(bundle_dir))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.resolve_binary("ffmpeg") is None


def test_probe_binario_non_si_lascia_ingannare_da_prefisso_di_stringa(tmp_path, monkeypatch):
    """CRATORY_BIN_DIR=".../bin" non deve etichettare come "bundle" un binario
    trovato in ".../binaries": il vecchio confronto era un prefisso di stringa,
    che "/bin" soddisfa anche per "/binaries/ffmpeg"."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()  # resta vuota: ffmpeg non ci vive, si ricade sul PATH
    other_dir = tmp_path / "binaries"
    other_dir.mkdir()
    fake = other_dir / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(bin_dir))
    monkeypatch.setattr(sp.shutil, "which", lambda name: str(fake))
    result = sp._probe_binary(sp.get("ffmpeg"))
    assert result["source"] == "path"


def test_probe_binario_bundle_riconosciuto_per_directory_esatta(tmp_path, monkeypatch):
    """Caso normale: il binario vive davvero dentro CRATORY_BIN_DIR."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    fake = bundle_dir / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(bundle_dir))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    result = sp._probe_binary(sp.get("ffmpeg"))
    assert result["source"] == "bundle"


def test_probe_binario_override_riportato_come_override(tmp_path, monkeypatch):
    """Un binario trovato tramite l'env override specifica del componente
    (es. FPCALC) va riportato come tale, non genericamente come "path"."""
    fake = tmp_path / "fpcalc-custom"
    fake.write_text("")
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setenv("FPCALC", str(fake))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    result = sp._probe_binary(sp.get("fpcalc"))
    assert result["source"] == "override"


def test_fpcalc_available_delega_al_seam_bin_dir(tmp_path, monkeypatch):
    """acoustid.fpcalc_available() deve vedere lo stesso binario del probe
    quando arriva da CRATORY_BIN_DIR: prima delle due fonti erano due
    implementazioni indipendenti che potevano disaccordarsi."""
    from app.organize.integrations import acoustid

    fake = tmp_path / "fpcalc"
    fake.write_text("")
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert acoustid.fpcalc_available() is True


def test_integrity_ffmpeg_available_delega_al_seam_bin_dir(tmp_path, monkeypatch):
    """organize/integrations/integrity.ffmpeg_available() idem, per ffmpeg."""
    from app.organize.integrations import integrity

    fake = tmp_path / "ffmpeg"
    fake.write_text("")
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert integrity.ffmpeg_available() is True


def test_downloads_ffmpeg_available_delega_al_seam_bin_dir(tmp_path, monkeypatch):
    """routers/downloads._ffmpeg_available() idem."""
    from app.routers import downloads

    fake = tmp_path / "ffmpeg"
    fake.write_text("")
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert downloads._ffmpeg_available() is True


def test_dj_sets_deps_available_delega_al_seam_bin_dir(tmp_path, monkeypatch):
    """routers/dj_sets._deps_available() idem per la parte ffmpeg; yt-dlp e
    shazamio sono neutralizzati per restare indipendenti dall'ambiente."""
    from app.routers import dj_sets

    fake = tmp_path / "ffmpeg"
    fake.write_text("")
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(dj_sets.importlib.util, "find_spec", lambda name: object())
    assert dj_sets._deps_available() is True


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


# --- Rilevamento dei pacchetti Python -----------------------------------
# yt-dlp ed Essentia nel codice sono `import`, non eseguibili: vanno rilevati
# importandoli, e la presenza la decide il codice di uscita, non l'output.

def _finto(key: str, module: str) -> sp.Component:
    return sp.Component(key=key, kind="venv", severity="optional",
                        unlocks=(), auto_installable=False, python_module=module)


def test_modulo_python_assente_non_risulta_presente():
    """Regressione del falso verde: `_run_version` ripiegava su stderr, quindi
    l'ImportError veniva letto come versione ('Traceback (most recent call
    last):') e il componente risultava installato. Un wizard che dice verde su
    un componente mancante e' peggio di un wizard che non lo cerca."""
    esito = sp._probe_python_module(_finto("finto", "modulo_che_non_esiste_davvero"))
    assert esito["present"] is False
    assert esito["version"] is None


def test_modulo_python_presente_risulta_presente():
    esito = sp._probe_python_module(_finto("finto", "json"))
    assert esito["present"] is True
    assert esito["source"] == "venv"


def test_yt_dlp_rilevato_per_import_non_per_binario(monkeypatch):
    """Nel codice yt-dlp e' solo `import yt_dlp`. Un eseguibile nel PATH senza
    il modulo nel venv (il caso di chi fa `brew install yt-dlp`) farebbe dire
    verde al wizard mentre ogni funzione che lo usa continua a fallire."""
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/opt/homebrew/bin/yt-dlp")
    monkeypatch.setattr(sp, "_import_version", lambda module: None)
    assert sp._probe_one(sp.get("yt-dlp"))["present"] is False


def test_dispatch_non_dipende_dalla_chiave(monkeypatch):
    """`_probe_one` riconosceva Essentia con un `if c.key == "essentia"`: un
    pacchetto Python aggiunto al registry sarebbe stato cercato come binario."""
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp._probe_one(_finto("nuovo", "json"))["present"] is True


def test_ogni_componente_ha_un_link_alla_documentazione():
    """slskd non ha una ricetta: senza link, chi non ce l'ha legge 'non
    trovato' e non ha nessun posto dove andare."""
    for c in sp.REGISTRY:
        assert c.docs.startswith("https://"), f"{c.key} senza documentazione"


def test_il_probe_espone_il_link(monkeypatch):
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp, "_import_version", lambda module: None)
    for riga in sp.probe_all(force=True):
        assert riga["docs"], f"{riga['key']} senza docs nel payload"


# --- Cartella gestita dei binari -------------------------------------------

def test_la_cartella_gestita_e_il_seam_esistente(tmp_path, monkeypatch):
    """CRATORY_BIN_DIR non è un meccanismo separato dalla cartella gestita:
    è la stessa cosa. Impostare la env deve spostare la cartella, così il
    bundle Tauri continua a funzionare senza codice dedicato."""
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    assert sp.managed_bin_dir() == tmp_path


def test_senza_env_usa_il_default_sotto_backend(monkeypatch):
    from app.core.config import BACKEND_DIR, settings
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(settings, "bin_dir", "./data/bin")
    assert sp.managed_bin_dir() == BACKEND_DIR / "data" / "bin"


def test_la_cartella_viene_creata(tmp_path, monkeypatch):
    """L'installer ci scriverà dentro: deve esistere senza che nessuno la crei
    a mano dopo un clone o un git clean."""
    target = tmp_path / "mai-creata"
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(target))
    assert sp.managed_bin_dir().is_dir()


def test_un_binario_nella_cartella_gestita_viene_trovato(tmp_path, monkeypatch):
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    (tmp_path / "ffmpeg").write_text("")
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    assert sp.resolve_binary("ffmpeg") == str(tmp_path / "ffmpeg")
