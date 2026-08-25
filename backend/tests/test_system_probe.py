"""Rilevamento dei componenti esterni: è la base del passo 1 del wizard."""
import stat
import sys

import pytest

from app.core import config
from app.services import system_probe as sp


@pytest.fixture(autouse=True)
def _no_slskd_network_call(monkeypatch):
    """Forza slskd_url() a ritornare stringa vuota, disattivando la feature.

    Da sola non basta più a evitare chiamate di rete: con la ricaduta
    sull'indirizzo di default (fix "un demone già acceso non deve restare
    invisibile"), URL vuoto porta comunque _probe_slskd a tentare
    http://localhost:5030/health. Un demone slskd vero in ascolto lì
    sull'host di sviluppo (caso reale: è così che gira anche il nostro)
    renderebbe questi test dipendenti dalla macchina che li esegue — per
    questo httpx.get è mockato qui, non solo l'URL. I test che vogliono
    provare la ricaduta la sovrascrivono da soli, dopo questa fixture.

    Ripulisce anche FPCALC e CRATORY_BIN_DIR: resolve_binary li consulta PRIMA
    del PATH, quindi uno sviluppatore con uno dei due impostati nell'ambiente
    (es. per lavorare sul bundle Tauri) farebbe fallire i test che assumono
    "niente di preinstallato" — l'indipendenza dall'host non e' negoziabile.
    """
    import httpx

    monkeypatch.setattr(config.settings, "slskd_url", "")
    monkeypatch.delenv("FPCALC", raising=False)
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)

    def _nessun_demone(*_a, **_k):
        raise httpx.ConnectError("nessun demone nei test")

    monkeypatch.setattr(httpx, "get", _nessun_demone)
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
    """Il fallback "*" copre ogni piattaforma non elencata esplicitamente: si
    verifica con un componente sintetico, perché fra i tre binari superstiti
    nessuno lo usa più (era la scorciatoia di yt-dlp/essentia, installati con
    lo stesso comando pip ovunque)."""
    finto = sp.Component(key="finto", kind="system", severity="optional",
                         unlocks=(), recipes={"*": [sys.executable, "-m", "pip", "install", "-U", "finto"]})
    monkeypatch.setattr(sp.sys, "platform", "sunos5")
    assert sp.recipe_for(finto) == [sys.executable, "-m", "pip", "install", "-U", "finto"]


def _senza_ricette() -> sp.Component:
    """Un componente che non ha ricette su nessuna piattaforma. Prima questo
    ruolo lo faceva slskd, che pero' non e' piu' un componente: dipendere da
    lui legava un test sulle ricette a una decisione di tutt'altra natura."""
    return sp.Component(key="finto", kind="system", severity="optional",
                        unlocks=(), recipes={}, binary="finto")


def test_ricetta_assente_ritorna_none(monkeypatch):
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    assert sp.recipe_for(_senza_ricette()) is None


def test_probe_all_ha_una_voce_per_componente(monkeypatch):
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp, "_run_version", lambda argv: None)
    result = sp.probe_all(force=True)
    assert [c["key"] for c in result] == [c.key for c in sp.REGISTRY]
    # slskd_url() è forzato empty dalla fixture e httpx.get è mockato per
    # fallire sempre: niente demone trovato, "non present".
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


def test_il_registry_contiene_solo_binari_di_sistema():
    """yt-dlp ed essentia sono in requirements.txt: li installa pip, non il
    wizard. Tenerli qui significava mostrare due righe già a posto e dare
    all'installer un lavoro che non è suo.

    slskd non è qui per un motivo diverso: la sua presenza non è un file su
    PATH ma una risposta HTTP, e configurarlo vuol dire credenziali, un file
    YAML e un demone da avviare — cose da servizio, non da componente. Vive in
    `routers/services.py`, e la sua riga sa fare tutto il percorso."""
    assert [c.key for c in sp.REGISTRY] == ["ffmpeg", "fpcalc"]
    assert {c.kind for c in sp.REGISTRY} == {"system"}


def test_il_probe_dice_se_sappiamo_installarlo(monkeypatch):
    """Su macOS ffmpeg non ha una build nel manifesto: la UI deve poterlo
    sapere per non offrire un bottone che non può funzionare."""
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp.binary_manifest, "platform_tag", lambda: "darwin-arm64")
    per_chiave = {r["key"]: r for r in sp.probe_all(force=True)}
    assert per_chiave["fpcalc"]["installable"] is True
    assert per_chiave["ffmpeg"]["installable"] is False


def test_su_linux_ffmpeg_e_installabile(monkeypatch):
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp.binary_manifest, "platform_tag", lambda: "linux-x86_64")
    per_chiave = {r["key"]: r for r in sp.probe_all(force=True)}
    assert per_chiave["ffmpeg"]["installable"] is True


# --- Le tre vie: download, ricetta di sistema, comando manuale -------------

def test_con_manifesto_la_via_e_download(monkeypatch):
    """fpcalc ha sempre un manifesto: la via è "download" indipendentemente
    dal fatto che una ricetta di sistema sia anche disponibile."""
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/opt/homebrew/bin/" + name)
    per_chiave = {r["key"]: r for r in sp.probe_all(force=True)}
    assert per_chiave["fpcalc"]["install_method"] == "download"


def test_senza_manifesto_ma_con_ricetta_disponibile_la_via_e_ricetta(monkeypatch):
    """ffmpeg su macOS non ha un manifesto: se `brew` è presente sul sistema
    (qui simulato), la via diventa "recipe", non più "manual" come prima di
    questo cambiamento."""
    monkeypatch.setattr(sp.binary_manifest, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)
    per_chiave = {r["key"]: r for r in sp.probe_all(force=True)}
    assert per_chiave["ffmpeg"]["install_method"] == "recipe"
    assert per_chiave["ffmpeg"]["installable"] is True
    assert per_chiave["ffmpeg"]["auto_installable"] is True


def test_senza_manifesto_e_senza_ricetta_disponibile_la_via_e_manuale(monkeypatch):
    """Né manifesto né `brew` sul sistema: resta il comando da copiare a
    mano, niente bottone (Finding del design doc: `brew` non è
    preinstallato)."""
    monkeypatch.setattr(sp.binary_manifest, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    per_chiave = {r["key"]: r for r in sp.probe_all(force=True)}
    assert per_chiave["ffmpeg"]["install_method"] == "manual"
    assert per_chiave["ffmpeg"]["installable"] is False
    assert per_chiave["ffmpeg"]["auto_installable"] is False
    # Il comando resta comunque nel payload: è quello che la UI mostra da
    # copiare a mano.
    assert per_chiave["ffmpeg"]["install_command"] == ["brew", "install", "ffmpeg"]


def test_available_recipe_richiede_il_comando_presente(monkeypatch):
    ffmpeg = sp.get("ffmpeg")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.available_recipe(ffmpeg) is None
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/opt/homebrew/bin/brew")
    assert sp.available_recipe(ffmpeg) == ["brew", "install", "ffmpeg"]


def test_available_recipe_none_se_non_ce_ricetta(monkeypatch):
    """Un componente senza ricette: `available_recipe` non deve nemmeno
    provare a chiamare `shutil.which` con un comando inesistente."""
    slskd = _senza_ricette()

    def esplodi(name):
        raise AssertionError("non doveva controllare nessun comando")

    monkeypatch.setattr(sp.shutil, "which", esplodi)
    assert sp.available_recipe(slskd) is None


def test_dice_se_stiamo_scavalcando_una_copia_di_sistema(tmp_path, monkeypatch):
    """L'utente installa ffmpeg con brew dopo di noi: il nostro continua a
    vincere. Silenzio qui significa un utente che non capisce perché la sua
    installazione non ha effetto."""
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    (tmp_path / "ffmpeg").write_text("")
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(sp, "_run_version", lambda argv: "ffmpeg 1.0")
    esito = sp._probe_binary(sp.get("ffmpeg"))
    assert esito["source"] == "bundle"
    assert esito["shadowing"] == "/opt/homebrew/bin/ffmpeg"


def test_niente_da_segnalare_se_usiamo_quella_di_sistema(monkeypatch):
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(sp, "_run_version", lambda argv: "ffmpeg 1.0")
    assert sp._probe_binary(sp.get("ffmpeg"))["shadowing"] is None


def test_ogni_componente_ha_un_link_alla_documentazione():
    """slskd non ha una ricetta: senza link, chi non ce l'ha legge 'non
    trovato' e non ha nessun posto dove andare."""
    for c in sp.REGISTRY:
        assert c.docs.startswith("https://"), f"{c.key} senza documentazione"


def test_il_probe_espone_il_link(monkeypatch):
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp, "_run_version", lambda argv: None)
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


def test_managed_bin_dir_non_crea_la_cartella(tmp_path, monkeypatch):
    """La lookup resta pura: nessun mkdir, altrimenti un controllo di
    disponibilità (fpcalc_available, GET /api/services, ...) creerebbe
    cartelle come effetto collaterale, o esploderebbe su un mount read-only."""
    target = tmp_path / "mai-creata"
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(target))
    assert sp.managed_bin_dir() == target
    assert not target.exists()


def test_la_cartella_viene_creata(tmp_path, monkeypatch):
    """L'installer ci scriverà dentro: `ensure_bin_dir()` deve farla esistere
    senza che nessuno la crei a mano dopo un clone o un git clean."""
    target = tmp_path / "mai-creata"
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(target))
    assert sp.ensure_bin_dir().is_dir()


def test_probe_binario_in_cartella_gestita_di_default_e_bundle(tmp_path, monkeypatch):
    """Riproduce il Finding 1: CRATORY_BIN_DIR non impostata (il caso normale
    una volta che l'installer scarica dentro la cartella di default), ma il
    binario vive comunque in settings.bin_dir. Il probe deve riportarlo come
    "bundle", non come "path": altrimenti il wizard direbbe all'utente che un
    binario scaricato da noi viene dal sistema."""
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(config.settings, "bin_dir", str(tmp_path))
    fake = tmp_path / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    result = sp._probe_binary(sp.get("ffmpeg"))
    assert result["source"] == "bundle"


def test_un_binario_nella_cartella_gestita_viene_trovato(tmp_path, monkeypatch):
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    (tmp_path / "ffmpeg").write_text("")
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    assert sp.resolve_binary("ffmpeg") == str(tmp_path / "ffmpeg")


def test_ogni_riga_di_probe_all_ha_le_stesse_chiavi(monkeypatch):
    """Tutte le righe di probe_all() devono avere lo stesso insieme di chiavi,
    indipendentemente dal tipo di componente (binario, daemon, etc.) e dal suo
    stato (presente o no). Questo previene divergenze come quella risolta
    aggiungendo `shadowing` a _probe_slskd."""
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp, "_run_version", lambda argv: None)
    result = sp.probe_all(force=True)

    # Tutte le righe hanno almeno una chiave
    assert result, "probe_all() non ha ritornato nessun risultato"

    # La prima riga fissa lo schema
    schema = set(result[0].keys())

    # Tutte le altre righe hanno esattamente lo stesso insieme di chiavi
    for i, row in enumerate(result[1:], start=1):
        righe_chiavi = set(row.keys())
        assert righe_chiavi == schema, (
            f"Riga {i} ({row['key']}) ha chiavi diverse: "
            f"mancano {schema - righe_chiavi}, extra {righe_chiavi - schema}"
        )
