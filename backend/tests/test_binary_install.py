"""L'installazione riesce solo se il binario parte: download, hash ed
estrazione riusciti non bastano — un file può ancora non eseguire per firma
o architettura sbagliata."""
import hashlib
import io
import tarfile
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
                 "tar.gz", "fpcalc", "single")
    monkeypatch.setattr(bm, "MANIFEST", {"fpcalc": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    return d


def test_installazione_riuscita(bin_dir, monkeypatch):
    dati = _archivio()
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso: "fpcalc 1.0")
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        percorso = bi.install("fpcalc", client=c)
    assert percorso == bin_dir / "fpcalc"
    assert percorso.is_file()


def test_il_binario_installato_e_eseguibile(bin_dir, monkeypatch):
    dati = _archivio()
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso: "ok")
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

    def non_parte(percorso):
        raise bi.DoesNotRun("Bad CPU type in executable")

    monkeypatch.setattr(bi, "_prova_esecuzione", non_parte)
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        with pytest.raises(bi.DoesNotRun):
            bi.install("fpcalc", client=c)
    assert list(bin_dir.iterdir()) == []


def test_piattaforma_senza_build_non_tocca_la_rete(bin_dir, monkeypatch):
    monkeypatch.setattr(bm, "MANIFEST", {"ffmpeg": {}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "darwin-arm64")

    def esplodi(req):
        raise AssertionError("non doveva scaricare niente")

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
                 "zip", "slskd", "bundle")
    monkeypatch.setattr(bm, "MANIFEST", {"slskd": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    (bin_dir / "slskd").mkdir()
    (bin_dir / "slskd" / "slskd").write_text("")
    assert bi.installed_path("slskd") == bin_dir / "slskd" / "slskd"
