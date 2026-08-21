"""L'installazione riesce solo se il binario parte: download, hash ed
estrazione riusciti non bastano — un file può ancora non eseguire per firma
o architettura sbagliata."""
import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

import httpx
import pytest

from app.services import binary_installer as bi
from app.services import binary_manifest as bm
from app.services import system_probe as sp
from app.services.binary_manifest import Download


def _archivio(contenuto: bytes = b"#!/bin/sh\necho ok\n") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo("fpcalc")
        info.size = len(contenuto)
        info.mode = 0o755
        t.addfile(info, io.BytesIO(contenuto))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _pulisci():
    bi.reset()
    yield
    bi.reset()


@pytest.fixture
def bin_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    return tmp_path


def _manifest(monkeypatch, sha: str):
    d = Download("1.0", "https://esempio.invalid/a.tar.gz", sha,
                 "tar.gz", "fpcalc", "single", "-version")
    monkeypatch.setattr(bm, "MANIFEST", {"fpcalc": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    return d


def _fabbrica_popen(monkeypatch, righe: list[str], returncode: int) -> list[dict]:
    """Sostituto di `subprocess.Popen` per i test della ricetta di sistema:
    nessun processo vero parte, solo le righe di stdout e il codice di uscita
    che il test vuole simulare. Ritorna la lista delle chiamate (argv +
    kwargs) cosi' il test puo' verificare che l'argv sia esattamente quello
    del registry, mai una stringa da shell."""
    chiamate: list[dict] = []

    class _PopenFinto:
        def __init__(self, argv, **kw):
            chiamate.append({"argv": argv, "kwargs": kw})
            self.stdout = iter(righe)

        def wait(self) -> int:
            return returncode

    monkeypatch.setattr(bi.subprocess, "Popen", _PopenFinto)
    return chiamate


def test_installazione_riuscita(bin_dir, monkeypatch):
    dati = _archivio()
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso, flag: "fpcalc 1.0")
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        percorso = bi.install("fpcalc", client=c)
    assert percorso == bin_dir / "fpcalc"
    assert percorso.is_file()


def test_il_binario_installato_e_eseguibile(bin_dir, monkeypatch):
    dati = _archivio()
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso, flag: "ok")
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        percorso = bi.install("fpcalc", client=c)
    assert percorso.stat().st_mode & 0o111, "manca il bit di esecuzione"


def test_hash_sbagliato_non_lascia_niente_nella_cartella(bin_dir, monkeypatch):
    """L'invariante che conta: la cartella gestita non deve MAI contenere
    qualcosa che non ha superato tutti i controlli."""
    dati = _archivio()
    _manifest(monkeypatch, "0" * 64)
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        with pytest.raises(bi.ChecksumMismatch):
            bi.install("fpcalc", client=c)
    assert list(bin_dir.iterdir()) == []


def test_binario_che_non_parte_fa_fallire_l_installazione(bin_dir, monkeypatch):
    """È la lezione della prova su fpcalc: scaricato, integro ed estratto può
    ancora non eseguire (firma assente, architettura sbagliata)."""
    dati = _archivio()
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())

    def non_parte(percorso, flag):
        raise bi.DoesNotRun("Bad CPU type in executable")

    monkeypatch.setattr(bi, "_prova_esecuzione", non_parte)
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        with pytest.raises(bi.DoesNotRun):
            bi.install("fpcalc", client=c)
    assert list(bin_dir.iterdir()) == []


def test_piattaforma_senza_build_non_tocca_la_rete(bin_dir, monkeypatch):
    """Nessun manifesto per questa piattaforma E nessuna ricetta col comando
    presente (qui simulato azzerando `shutil.which`, indipendente dal fatto
    che questa macchina abbia o no Homebrew davvero installato): resta
    `NoBuildForPlatform`, niente da scaricare né da eseguire."""
    monkeypatch.setattr(bm, "MANIFEST", {"ffmpeg": {}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)

    def esplodi(req):
        raise AssertionError("non doveva scaricare niente")

    def esplodi_subprocess(*a, **kw):
        raise AssertionError("non doveva eseguire nessuna ricetta")

    monkeypatch.setattr(bi.subprocess, "Popen", esplodi_subprocess)
    with httpx.Client(transport=httpx.MockTransport(esplodi)) as c:
        with pytest.raises(bi.NoBuildForPlatform):
            bi.install("ffmpeg", client=c)


def test_componente_sconosciuto():
    with pytest.raises(bi.UnknownComponent):
        bi.install("pippo")


def test_un_job_alla_volta(bin_dir, monkeypatch):
    monkeypatch.setattr(bi, "spawn", lambda fn: None)  # resta "running"
    _manifest(monkeypatch, "0" * 64)
    bi.start("fpcalc")
    with pytest.raises(bi.AlreadyRunning):
        bi.start("fpcalc")


def test_il_job_riporta_l_errore_invece_di_restare_appeso(bin_dir, monkeypatch):
    """Se il thread muore senza spostare lo stato, ogni richiesta successiva
    riceve 409 finché non si riavvia il backend."""
    _manifest(monkeypatch, "0" * 64)
    monkeypatch.setattr(bi, "spawn", lambda fn: fn())
    # `**kw` e non `client=None`: `start()` chiama `install(key, on_log=…)`,
    # e una firma piu' stretta farebbe fallire il test per il motivo sbagliato.
    monkeypatch.setattr(bi, "install",
                        lambda key, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    bi.start("fpcalc")
    assert bi.status()["status"] == "error"
    assert "boom" in bi.status()["detail"]


def test_installed_path_conosce_il_layout(bin_dir, monkeypatch):
    d = Download("1.0", "https://esempio.invalid/a.zip", "0" * 64,
                 "zip", "slskd", "bundle", "--version")
    monkeypatch.setattr(bm, "MANIFEST", {"slskd": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    (bin_dir / "slskd").mkdir()
    (bin_dir / "slskd" / "slskd").write_text("")
    assert bi.installed_path("slskd") == bin_dir / "slskd" / "slskd"


def _script_che_pretende(flag_atteso: str) -> bytes:
    """Un eseguibile finto che si comporta come i veri binari testati a mano:
    esce 0 solo se invocato con il flag che si aspetta, altrimenti fallisce.
    Non è un monkeypatch di `_prova_esecuzione`: è l'unico modo di accorgersi
    se il flag passato dall'installer è quello sbagliato."""
    return f"""#!/bin/sh
if [ "$1" = "{flag_atteso}" ]; then
    echo "finto binario, versione 1.0"
    exit 0
fi
exit 1
""".encode()


def test_il_flag_di_versione_viene_dal_manifesto_non_hardcoded(bin_dir, monkeypatch):
    """Non monkeypatcha `_prova_esecuzione`: con `-version` hardcoded in
    quella funzione (il bug del finding), questo test fallirebbe per il
    componente che pretende `--version`, esattamente come slskd nella vita
    vera — e nel caso peggiore, se il flag sbagliato fosse interpretato come
    "parti pure", il test resterebbe appeso fino al timeout."""
    dati = _archivio(_script_che_pretende("--version"))
    d = Download("1.0", "https://esempio.invalid/a.tar.gz",
                 hashlib.sha256(dati).hexdigest(),
                 "tar.gz", "fpcalc", "single", "--version")
    monkeypatch.setattr(bm, "MANIFEST", {"fpcalc": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        percorso = bi.install("fpcalc", client=c)
    assert percorso.is_file()


def test_flag_sbagliato_nel_manifesto_fa_fallire_l_installazione(bin_dir, monkeypatch):
    """Simmetrico al test sopra: il finto binario accetta solo `--version` (il
    caso di slskd), pinnare `-version` nel manifesto (il flag buono per fpcalc
    e ffmpeg, sbagliato per slskd) deve far fallire la prova di esecuzione,
    non passare silenziosamente."""
    dati = _archivio(_script_che_pretende("--version"))
    d = Download("1.0", "https://esempio.invalid/a.tar.gz",
                 hashlib.sha256(dati).hexdigest(),
                 "tar.gz", "fpcalc", "single", "-version")
    monkeypatch.setattr(bm, "MANIFEST", {"fpcalc": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        with pytest.raises(bi.DoesNotRun):
            bi.install("fpcalc", client=c)


def test_dopo_install_il_probe_vede_il_bundle_installato(bin_dir, monkeypatch):
    """L'invariante che il finding B1 ha trovato mancante: `installed_path()`
    conosce il layout bundle, ma prima di questo fix era l'unica funzione a
    conoscerlo — il probe (`resolve_binary`) si fermava a `<bin_dir>/<name>` e
    un ffmpeg installato (layout bundle, in `<bin_dir>/ffmpeg/ffmpeg`) restava
    `present: False` per sempre: download, hash ed estrazione riusciti, il
    bottone che non converge mai. Si prova sul componente vero (`ffmpeg`,
    `required` nel registry), non su un doppio inventato, cosi' la stessa
    Component che il wizard usa per davvero e' quella verificata qui."""
    script = _script_che_pretende("-version")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ffmpeg", script)
    dati = buf.getvalue()
    d = Download("1.0", "https://esempio.invalid/a.zip",
                 hashlib.sha256(dati).hexdigest(),
                 "zip", "ffmpeg", "bundle", "-version")
    monkeypatch.setattr(bm, "MANIFEST", {"ffmpeg": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    sp._cache = None

    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        percorso = bi.install("ffmpeg", client=c)
    assert percorso.is_file()

    esito = sp._probe_one(sp.get("ffmpeg"))
    assert esito["present"] is True, "il probe deve vedere il bundle appena installato"
    assert esito["source"] == "bundle", "deve venire riportato come dalla cartella gestita"


def test_bundle_fallito_a_meta_copia_non_distrugge_quello_gia_installato(bin_dir, monkeypatch):
    """Riproduce lo scenario del reviewer: un bundle già installato e
    funzionante, un guasto durante la copia della nuova versione (lo stesso
    che capita quando `shutil.move` tra filesystem diversi ricade su
    copia-e-cancella e la copia si interrompe). L'invariante che conta è che
    quello vecchio resti al suo posto — non una cartella vuota, non un
    ibrido a metà tra vecchio e nuovo."""
    vecchia = bin_dir / "slskd"
    vecchia.mkdir()
    (vecchia / "slskd").write_text("vecchio binario funzionante")
    (vecchia / "libfoo.so").write_text("dipendenza del vecchio binario")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("slskd", b"#!/bin/sh\necho nuovo\nexit 0\n")
    dati = buf.getvalue()
    d = Download("2.0", "https://esempio.invalid/a.zip",
                 hashlib.sha256(dati).hexdigest(),
                 "zip", "slskd", "bundle", "--version")
    monkeypatch.setattr(bm, "MANIFEST", {"slskd": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso, flag: "ok")

    def esplode(*a, **kw):
        raise OSError("disco pieno a metà copia")

    # Si rompono entrambi i meccanismi con cui uno spostamento di una cartella
    # può fallire: `copytree` è il passo costoso della versione corretta,
    # `move` è quello che il reviewer ha rotto per riprodurre il bug nella
    # versione precedente (che chiamava `shutil.move` direttamente sul
    # sorgente, senza passare da una copia in stage).
    monkeypatch.setattr(bi.shutil, "copytree", esplode)
    monkeypatch.setattr(bi.shutil, "move", esplode)

    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        with pytest.raises(OSError):
            bi.install("slskd", client=c)

    assert (vecchia / "slskd").read_text() == "vecchio binario funzionante"
    assert (vecchia / "libfoo.so").read_text() == "dipendenza del vecchio binario"
    assert not (bin_dir / "slskd.new").exists()
    assert not (bin_dir / "slskd.old").exists()


def test_binario_che_esce_zero_ma_non_stampa_nulla(bin_dir, monkeypatch):
    """Un binario che esce 0 senza output è considerato funzionante: nulla da
    leggere per la versione, il criterio di riuscita è che sia partito."""
    dati = _archivio(b"#!/bin/sh\nexit 0\n")
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        percorso = bi.install("fpcalc", client=c)
    assert percorso.is_file()


# --- La seconda via: la ricetta di sistema, quando non c'è un manifesto ----
#
# Nessuno di questi test lancia un gestore di pacchetti vero: `subprocess.Popen`
# è sempre sostituito da `_fabbrica_popen`, e `shutil.which` è sempre
# azzerato/riscritto esplicitamente — mai lasciato leggere l'ambiente reale
# (su questa stessa macchina di sviluppo `brew` esiste davvero, e un test che
# lo lasciasse trapelare eseguirebbe un install per davvero).

def test_manifesto_vince_sulla_ricetta_anche_se_disponibile(bin_dir, monkeypatch):
    """Un componente con un manifesto per questa piattaforma scarica sempre,
    anche quando una ricetta di sistema sarebbe anche lei disponibile (qui
    simulato: fpcalc ha una ricetta brew per macOS). Il download resta dentro
    la cartella gestita, rimovibile cancellandola — la ricetta è solo il
    ripiego per ciò che non possiamo fornire noi stessi."""
    dati = _archivio()
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso, flag: "fpcalc 1.0")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/opt/homebrew/bin/" + name)

    def esplodi_subprocess(*a, **kw):
        raise AssertionError("non doveva shellare fuori: il manifesto vince")

    monkeypatch.setattr(bi.subprocess, "Popen", esplodi_subprocess)
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        percorso = bi.install("fpcalc", client=c)
    assert percorso == bin_dir / "fpcalc"


def test_senza_manifesto_esegue_la_ricetta_disponibile(monkeypatch):
    """ffmpeg su macOS non ha un manifesto: se `brew` è presente sul sistema
    (qui simulato), l'installer esegue la ricetta invece di sollevare
    `NoBuildForPlatform`."""
    monkeypatch.setattr(bm, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    monkeypatch.setattr(sp.shutil, "which",
                        lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)
    chiamate = _fabbrica_popen(monkeypatch, ["==> Installing ffmpeg", "🍺  ffmpeg installato"], 0)
    monkeypatch.setattr(sp, "resolve_binary", lambda name, override=None: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso, flag: "ffmpeg version 6.0")

    righe_log: list[str] = []
    percorso = bi.install("ffmpeg", on_log=righe_log.append)

    assert percorso == Path("/opt/homebrew/bin/ffmpeg")
    assert chiamate[0]["argv"] == ["brew", "install", "ffmpeg"]
    assert "eseguo brew install ffmpeg" in righe_log
    assert "==> Installing ffmpeg" in righe_log
    assert any("parte" in r for r in righe_log)


def test_ricetta_che_fallisce_fa_fallire_l_installazione(monkeypatch):
    """Un `brew install` che esce con un codice diverso da zero non arriva
    nemmeno a provare il binario: la ricetta stessa ha già detto che non è
    andata."""
    monkeypatch.setattr(bm, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    monkeypatch.setattr(sp.shutil, "which",
                        lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)
    _fabbrica_popen(monkeypatch, ["Error: ffmpeg: no bottle available"], 1)

    def esplodi(*a, **kw):
        raise AssertionError("non doveva arrivare a verificare l'esecuzione: la ricetta è già fallita")

    monkeypatch.setattr(sp, "resolve_binary", esplodi)
    monkeypatch.setattr(bi, "_prova_esecuzione", esplodi)

    with pytest.raises(bi.RecipeFailed):
        bi.install("ffmpeg")


def test_ricetta_riuscita_ma_binario_introvabile_fallisce_lo_stesso(monkeypatch):
    """L'exit code del gestore di pacchetti da solo non basta: se il binario
    non risulta comunque sul PATH, l'installazione fallisce (`DoesNotRun`),
    anche se `brew` è uscito con successo."""
    monkeypatch.setattr(bm, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    monkeypatch.setattr(sp.shutil, "which",
                        lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)
    _fabbrica_popen(monkeypatch, ["ffmpeg installato"], 0)
    monkeypatch.setattr(sp, "resolve_binary", lambda name, override=None: None)

    def esplodi(*a, **kw):
        raise AssertionError("non doveva provare a eseguire un binario introvabile")

    monkeypatch.setattr(bi, "_prova_esecuzione", esplodi)

    with pytest.raises(bi.DoesNotRun):
        bi.install("ffmpeg")


def test_ricetta_riuscita_ma_binario_non_parte_fallisce_lo_stesso(monkeypatch):
    """Variante del test sopra: il binario risulta sul PATH ma non parte
    (firma, architettura...). Stesso esito: l'exit code di `brew` da solo non
    certifica niente."""
    monkeypatch.setattr(bm, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    monkeypatch.setattr(sp.shutil, "which",
                        lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)
    _fabbrica_popen(monkeypatch, ["ffmpeg installato"], 0)
    monkeypatch.setattr(sp, "resolve_binary", lambda name, override=None: "/opt/homebrew/bin/ffmpeg")

    def non_parte(percorso, flag):
        raise bi.DoesNotRun("Bad CPU type in executable")

    monkeypatch.setattr(bi, "_prova_esecuzione", non_parte)

    with pytest.raises(bi.DoesNotRun):
        bi.install("ffmpeg")


def test_la_cache_del_probe_e_invalidata_prima_di_verificare(monkeypatch):
    """Il binario ora vive sul PATH di sistema, non nella cartella gestita:
    la cache del probe (TTL 10s) può ancora ricordare "assente" da un giro
    precedente. Deve essere invalidata PRIMA del controllo di risolvibilità,
    altrimenti il controllo stesso non significa niente."""
    monkeypatch.setattr(bm, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    monkeypatch.setattr(sp.shutil, "which",
                        lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)
    _fabbrica_popen(monkeypatch, [], 0)

    ordine: list[str] = []
    monkeypatch.setattr(sp, "invalidate_cache", lambda: ordine.append("invalidata"))

    def resolve_finto(name, override=None):
        ordine.append("verificata")
        return "/opt/homebrew/bin/ffmpeg"

    monkeypatch.setattr(sp, "resolve_binary", resolve_finto)
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso, flag: "ok")

    bi.install("ffmpeg")
    assert ordine == ["invalidata", "verificata"]


def test_run_recipe_trasmette_le_righe_in_streaming(monkeypatch):
    _fabbrica_popen(monkeypatch, ["riga uno", "riga due  \n"], 0)
    righe: list[str] = []
    bi.run_recipe(["echo", "ciao"], on_log=righe.append)
    assert righe == ["riga uno", "riga due"]


def test_run_recipe_argv_come_lista_niente_shell(monkeypatch):
    """Stessa disciplina del download: l'argv arriva dal registry come lista,
    mai come stringa interpretata da una shell — e nessun input dell'utente
    ci entra."""
    chiamate = _fabbrica_popen(monkeypatch, [], 0)
    bi.run_recipe(["brew", "install", "ffmpeg"])
    assert chiamate[0]["argv"] == ["brew", "install", "ffmpeg"]
    assert chiamate[0]["kwargs"].get("shell", False) is False


def test_run_recipe_solleva_se_il_comando_fallisce(monkeypatch):
    _fabbrica_popen(monkeypatch, ["Error: bottle unavailable"], 1)
    with pytest.raises(bi.RecipeFailed):
        bi.run_recipe(["brew", "install", "ffmpeg"])
