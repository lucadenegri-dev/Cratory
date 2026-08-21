"""Il manifesto è dati puri: la sua correttezza è che i pin ci siano tutti e
che la selezione per piattaforma non peschi la build sbagliata."""
from app.services import binary_manifest as bm


def test_tag_di_piattaforma(monkeypatch):
    monkeypatch.setattr(bm.sys, "platform", "darwin")
    monkeypatch.setattr(bm.platform, "machine", lambda: "arm64")
    assert bm.platform_tag() == "darwin-arm64"


def test_tag_normalizza_i_sinonimi_di_architettura(monkeypatch):
    """`platform.machine()` dice 'AMD64' su Windows e 'x86_64' altrove per la
    stessa architettura: senza normalizzazione il manifesto avrebbe due chiavi
    per la stessa cosa e Windows non troverebbe mai la sua build."""
    monkeypatch.setattr(bm.sys, "platform", "win32")
    monkeypatch.setattr(bm.platform, "machine", lambda: "AMD64")
    assert bm.platform_tag() == "win32-x86_64"


def test_fpcalc_c_e_per_ogni_piattaforma_supportata():
    for tag in ("darwin-arm64", "darwin-x86_64", "linux-x86_64",
                "linux-arm64", "win32-x86_64"):
        assert bm.entry_for("fpcalc", tag) is not None, tag


def test_macos_non_ha_una_voce_per_ffmpeg():
    """Decisione esplicita della spec: non esiste una build statica arm64
    nativa con checksum pubblicato, e spedire un binario Intel dipendente da
    Rosetta come componente NECESSARIO è peggio di un buco dichiarato."""
    assert bm.entry_for("ffmpeg", "darwin-arm64") is None
    assert bm.entry_for("ffmpeg", "darwin-x86_64") is None
    assert bm.entry_for("ffmpeg", "linux-x86_64") is not None


def test_piattaforma_sconosciuta_non_esplode():
    assert bm.entry_for("fpcalc", "haiku-m68k") is None


def test_componente_sconosciuto():
    assert bm.entry_for("pippo", "linux-x86_64") is None


def test_ogni_voce_e_pinnata_e_verificabile():
    """Un URL senza hash, o un hash della lunghezza sbagliata, renderebbe la
    verifica una formalità. E un URL che punta a un tag mobile (`latest`)
    rende l'hash impossibile da mantenere, perché il file cambia sotto."""
    for key, per_tag in bm.MANIFEST.items():
        for tag, d in per_tag.items():
            assert d.url.startswith("https://"), (key, tag)
            assert len(d.sha256) == 64, (key, tag)
            assert all(c in "0123456789abcdef" for c in d.sha256), (key, tag)
            assert "/latest/" not in d.url, (key, tag)
            assert d.version, (key, tag)
            assert d.member, (key, tag)
            assert d.version_flag, (key, tag)


def test_slskd_non_usa_il_flag_di_ffmpeg_e_fpcalc():
    """slskd accetta solo `-v`/`--version`: pinnare `-version` (quello buono
    per fpcalc e ffmpeg) farebbe fallire sempre la prova di esecuzione per
    uno dei due componenti `bundle` del manifesto (l'altro è ffmpeg)."""
    for tag, d in bm.MANIFEST["slskd"].items():
        assert d.version_flag == "--version", tag
    for tag, d in bm.MANIFEST["fpcalc"].items():
        assert d.version_flag == "-version", tag
    for tag, d in bm.MANIFEST["ffmpeg"].items():
        assert d.version_flag == "-version", tag


def test_slskd_e_un_bundle_non_un_singolo_file():
    """55 MB di applicazione .NET con le sue dipendenze: estrarre solo
    l'eseguibile lo lascerebbe senza le librerie che gli servono."""
    d = bm.entry_for("slskd", "darwin-arm64")
    assert d.layout == "bundle"


def test_fpcalc_e_un_singolo_file():
    assert bm.entry_for("fpcalc", "darwin-arm64").layout == "single"
