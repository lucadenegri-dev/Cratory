"""Un archivio è dato non fidato: può contenere percorsi che puntano fuori
dalla cartella di destinazione. Va provato per tar E per zip separatamente,
perché `tarfile` ha il filtro `data` e `zipfile` non ha niente."""
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from app.services import binary_installer as bi
from app.services.binary_manifest import Download


def _tar(percorso: Path, membri: dict[str, bytes], compressione: str = "gz") -> None:
    with tarfile.open(percorso, f"w:{compressione}") as t:
        for nome, dati in membri.items():
            info = tarfile.TarInfo(nome)
            info.size = len(dati)
            info.mode = 0o755
            t.addfile(info, io.BytesIO(dati))


def _zip(percorso: Path, membri: dict[str, bytes]) -> None:
    with zipfile.ZipFile(percorso, "w") as z:
        for nome, dati in membri.items():
            z.writestr(nome, dati)


def _d(archive: str, member: str, layout: str) -> Download:
    return Download("1.0", "https://esempio.invalid/a", "0" * 64,
                    archive, member, layout)


def test_tar_single_estrae_solo_il_binario(tmp_path):
    a = tmp_path / "a.tar.gz"
    _tar(a, {"cartella/fpcalc": b"BIN", "cartella/LEGGIMI": b"x"})
    dest = tmp_path / "out"
    dest.mkdir()
    exe = bi.extract(a, _d("tar.gz", "fpcalc", "single"), dest)
    assert exe == dest / "fpcalc"
    assert exe.read_bytes() == b"BIN"
    assert not (dest / "LEGGIMI").exists()


def test_tar_trova_il_membro_a_qualsiasi_profondita(tmp_path):
    """Il percorso interno delle release di ffmpeg contiene il numero di build
    e cambia a ogni versione: si cerca per basename, non per percorso."""
    a = tmp_path / "a.tar.gz"
    _tar(a, {"ffmpeg-N-999-abc-linux64-gpl/bin/ffmpeg": b"BIN"})
    dest = tmp_path / "out"
    dest.mkdir()
    exe = bi.extract(a, _d("tar.gz", "ffmpeg", "single"), dest)
    assert exe.read_bytes() == b"BIN"


def test_zip_single(tmp_path):
    a = tmp_path / "a.zip"
    _zip(a, {"fpcalc.exe": b"BIN"})
    dest = tmp_path / "out"
    dest.mkdir()
    exe = bi.extract(a, _d("zip", "fpcalc.exe", "single"), dest)
    assert exe.read_bytes() == b"BIN"


def test_bundle_estrae_tutto_e_punta_all_eseguibile(tmp_path):
    a = tmp_path / "a.zip"
    _zip(a, {"slskd": b"BIN", "libreria.dll": b"LIB"})
    dest = tmp_path / "out"
    dest.mkdir()
    exe = bi.extract(a, _d("zip", "slskd", "bundle"), dest)
    assert exe.read_bytes() == b"BIN"
    # Il runtime .NET sta accanto all'eseguibile: senza, non parte.
    assert (exe.parent / "libreria.dll").read_bytes() == b"LIB"


def test_tar_con_traversal_rifiutato(tmp_path):
    a = tmp_path / "a.tar.gz"
    _tar(a, {"../fuori": b"MALE"})
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(bi.UnsafeArchive):
        bi.extract(a, _d("tar.gz", "fuori", "bundle"), dest)
    assert not (tmp_path / "fuori").exists()


def test_zip_con_traversal_rifiutato(tmp_path):
    """zipfile non ha il filtro `data` di tarfile: la validazione qui è nostra
    e va provata a parte, altrimenti si copre solo metà del rischio."""
    a = tmp_path / "a.zip"
    _zip(a, {"../fuori": b"MALE"})
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(bi.UnsafeArchive):
        bi.extract(a, _d("zip", "fuori", "bundle"), dest)
    assert not (tmp_path / "fuori").exists()


def test_zip_con_percorso_assoluto_rifiutato(tmp_path):
    a = tmp_path / "a.zip"
    _zip(a, {"/etc/cattivo": b"MALE"})
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(bi.UnsafeArchive):
        bi.extract(a, _d("zip", "cattivo", "bundle"), dest)


def test_membro_mancante(tmp_path):
    a = tmp_path / "a.tar.gz"
    _tar(a, {"altro": b"x"})
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(bi.InstallError):
        bi.extract(a, _d("tar.gz", "fpcalc", "single"), dest)
